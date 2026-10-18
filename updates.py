"""Source checks and explicit fast-forward updates of running plugin checkouts."""
import concurrent.futures
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import fcntl


def git(directory, *args, timeout=10):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0',
               GIT_SSH_COMMAND='ssh -oBatchMode=yes -oConnectTimeout=7')
    process = subprocess.run(['git', '-C', str(directory), *args], capture_output=True,
                             text=True, timeout=timeout, env=env)
    if process.returncode:
        raise RuntimeError('Could not read or contact the source repository.')
    return process.stdout.strip()


def cache_path():
    root = pathlib.Path(os.environ.get('XDG_STATE_HOME') or pathlib.Path.home() / '.local/state')
    return root / 'omarchy/omaplugctl/updates.json'


def load_cache():
    try:
        value = json.loads(cache_path().read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(value):
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement prevents a refresh from reading half a check result.
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.updates-', delete=False) as file:
        json.dump(value, file)
        temporary = file.name
    os.replace(temporary, path)


def operations():
    result = {}
    for path in (cache_path().parent / 'operations').glob('*.json'):
        try:
            if path.stat().st_size <= 8192:
                value = json.loads(path.read_text())
                result[value['plugin']] = value
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return result


def save_operation(pid, **fields):
    path = cache_path().parent / 'operations' / (hashlib.sha256(pid.encode()).hexdigest() + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {**fields, 'plugin': pid, 'changedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.update-', delete=False) as file:
        json.dump(value, file)
        temporary = file.name
    os.replace(temporary, path)


def source(plugin, metadata):
    directory = pathlib.Path(metadata.get('sourceDir') or '')
    if not metadata.get('sourceDir') or not directory.is_dir():
        return None
    first_party = bool(plugin.get('firstParty')) and not plugin.get('clonedFrom')
    if not first_party and not (directory / '.git').exists():
        return None
    try:
        root = pathlib.Path(git(directory, 'rev-parse', '--show-toplevel')).resolve()
        if not first_party and root != directory.resolve():
            return None
        remote = git(root, 'remote', 'get-url', 'origin')
        head = git(root, 'rev-parse', 'HEAD')
        branch = git(root, 'branch', '--show-current')
        target = 'HEAD'
        tracking = False
        try:
            target = git(root, 'config', '--get', 'branch.' + branch + '.merge')
            configured_remote = git(root, 'config', '--get', 'branch.' + branch + '.remote')
            tracking = bool(branch and configured_remote == 'origin' and target.startswith('refs/heads/'))
        except RuntimeError:
            pass
        if not tracking:
            target = 'HEAD'
        dirty = bool(git(root, 'status', '--porcelain', '--untracked-files=normal'))
        return {'root': str(root), 'head': head, 'target': target,
                'identity': hashlib.sha256((str(root) + '\n' + remote + '\n' + target + '\n' + branch).encode()).hexdigest(),
                'branch': branch, 'tracking': tracking,
                'kind': 'omarchy' if first_party else 'plugin', 'dirty': dirty}
    except (RuntimeError, subprocess.SubprocessError, OSError):
        return None


def cached_status(plugin, metadata, cache):
    info = source(plugin, metadata)
    if info is None:
        return {'status': 'system' if plugin.get('firstParty') else 'local', 'canUpdate': False}
    value = cache.get(plugin['id'], {})
    value = value if isinstance(value, dict) else {}
    if value.get('identity') != info['identity'] or value.get('head') != info['head']:
        return {'status': 'unchecked', 'kind': info['kind'], 'canUpdate': False}
    value = dict(value)
    if value.get('status') == 'current':
        try:
            checked = datetime.datetime.fromisoformat(value['checkedAt'])
            if datetime.datetime.now(datetime.timezone.utc) - checked > datetime.timedelta(days=1):
                return {'status': 'unchecked', 'kind': info['kind'], 'canUpdate': False}
        except (KeyError, ValueError, TypeError):
            return {'status': 'unchecked', 'kind': info['kind'], 'canUpdate': False}
    value['dirty'] = info['dirty']
    value['canUpdate'] = value.get('status') == 'available' and not info['dirty'] and info['tracking'] and info['kind'] == 'plugin'
    if value.get('status') in ('available', 'diverged') and value.get('remoteHead') and not value.get('latestDate'):
        try:
            value.update(update_details(info, value['remoteHead'], metadata))
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
            pass
    return value


def plugin_paths(metadata, root):
    manifest = pathlib.Path(metadata['manifestPath'])
    if manifest.name == 'manifest.json':
        paths = [manifest.parent]
    else:
        document = json.loads(manifest.read_text())
        entries = document.get('entryPoints') or {}
        paths = [manifest] + [manifest.parent / name for name in entries.values() if isinstance(name, str)]
        clone_paths = (document.get('omarchy') or {}).get('clonePaths') or []
        paths += [manifest.parent / entry['source'] for entry in clone_paths
                  if isinstance(entry, dict) and isinstance(entry.get('source'), str)]
    return [str(path.resolve().relative_to(pathlib.Path(root).resolve())) for path in paths]


def fetch_source(info):
    git(info['root'], 'fetch', '--quiet', '--no-tags', 'origin', info['target'], timeout=12)
    return git(info['root'], 'rev-parse', 'FETCH_HEAD')


def compare_source(info, remote_head, metadata):
    ahead, behind = map(int, git(info['root'], 'rev-list', '--left-right', '--count',
                                info['head'] + '...' + remote_head).split())
    status = 'diverged' if ahead and behind else 'ahead' if ahead else 'available' if behind else 'current'
    if status == 'available' and info['kind'] == 'omarchy':
        changes = git(info['root'], 'diff', '--name-only', info['head'], remote_head,
                      '--', *plugin_paths(metadata, info['root']))
        if not changes:
            status = 'current'
    details = update_details(info, remote_head, metadata) if status in ('available', 'diverged') else {}
    return {**info, **details, 'status': status, 'remoteHead': remote_head,
            'checkedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'canUpdate': status == 'available' and not info['dirty'] and info['tracking'] and info['kind'] == 'plugin'}


def apply_update(plugin, metadata):
    initial = source(plugin, metadata)
    if not initial or initial['kind'] != 'plugin':
        raise RuntimeError('This plugin is updated with Omarchy, not an independent plugin Git checkout.')
    lock = cache_path().parent / ('update-' + hashlib.sha256(initial['root'].encode()).hexdigest() + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('This plugin repository is already being updated.')
        before = source(plugin, metadata)
        if not before or before['identity'] != initial['identity']:
            raise RuntimeError('The running plugin source changed. Refresh before updating.')
        if before['dirty']:
            raise RuntimeError('Local changes block this update; your files were preserved.')
        if not before['tracking']:
            raise RuntimeError('Choose an attached branch tracking origin before updating this plugin.')
        remote = fetch_source(before)
        current = source(plugin, metadata)
        if not current or current['identity'] != before['identity'] or current['head'] != before['head'] or current['dirty']:
            raise RuntimeError('The plugin checkout changed during the source check. No update applied.')
        status = compare_source(before, remote, metadata)
        if status['status'] == 'diverged':
            raise RuntimeError('Local and upstream history diverged. No files were changed.')
        if status['status'] == 'ahead':
            raise RuntimeError('This checkout has local commits ahead of upstream. No files were changed.')
        if status['status'] == 'available':
            # The fetched object is pinned; never create a merge, rebase or stash.
            git(before['root'], '-c', 'core.hooksPath=/dev/null', 'merge', '--ff-only', '--no-edit', remote, timeout=30)
        after = source(plugin, metadata)
        if not after or after['head'] != remote or after['dirty'] or after['identity'] != before['identity']:
            raise RuntimeError('Could not confirm the updated checkout. Refresh its status.')
        cache = load_cache()
        cache[plugin['id']] = compare_source(after, remote, metadata)
        save_cache(cache)
        return {'head': after['head'], 'changed': after['head'] != before['head']}


def update_details(info, remote_head, metadata):
    paths = plugin_paths(metadata, info['root']) if info['kind'] == 'omarchy' else []
    arguments = ['log', '--max-count=3', '--format=%cs%x1f%s', info['head'] + '..' + remote_head]
    if paths:
        arguments += ['--', *paths]
    lines = git(info['root'], *arguments).splitlines()
    notes = []
    date = ''
    for line in lines:
        stamp, separator, subject = line.partition('\x1f')
        if separator:
            if not date: date = stamp
            notes.append(subject[:240])
    return {'latestDate': date, 'notes': notes}


def check_all(plugins, metadata):
    cache = load_cache()
    sources = {}
    groups = {}
    for plugin in plugins:
        info = source(plugin, metadata.get(plugin['id'], {}))
        if info:
            sources[plugin['id']] = info
            groups.setdefault(info['identity'], info)
    fetched = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch_source, info): key for key, info in groups.items()}
        for future in concurrent.futures.as_completed(jobs):
            try:
                fetched[jobs[future]] = future.result()
            except (RuntimeError, OSError, subprocess.SubprocessError):
                fetched[jobs[future]] = None
    for pid, info in sources.items():
        remote_head = fetched[info['identity']]
        try:
            if remote_head is None:
                raise RuntimeError('Source check failed.')
            cache[pid] = compare_source(info, remote_head, metadata[pid])
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
            cache[pid] = {**info, 'status': 'error', 'canUpdate': False}
    save_cache(cache)
    return cache
