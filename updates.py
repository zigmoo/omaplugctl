"""Source checks for the installed plugin version; no automatic installs."""
import concurrent.futures
import datetime
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile


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


def source(plugin, metadata):
    directory = pathlib.Path(metadata.get('sourceDir') or '')
    if not metadata.get('sourceDir') or not directory.is_dir():
        return None
    first_party = bool(plugin.get('firstParty')) and not plugin.get('clonedFrom')
    if not first_party and not (directory / '.git').is_dir():
        return None
    try:
        root = pathlib.Path(git(directory, 'rev-parse', '--show-toplevel')).resolve()
        if not first_party and root != directory.resolve():
            return None
        remote = git(root, 'remote', 'get-url', 'origin')
        head = git(root, 'rev-parse', 'HEAD')
        target = 'HEAD'
        if first_party:
            branch = git(root, 'branch', '--show-current')
            target = git(root, 'config', '--get', 'branch.' + branch + '.merge')
            configured_remote = git(root, 'config', '--get', 'branch.' + branch + '.remote')
            if configured_remote != 'origin':
                return None
        dirty = bool(git(root, 'status', '--porcelain', '--untracked-files=normal'))
        return {'root': str(root), 'head': head, 'target': target,
                'identity': hashlib.sha256((str(root) + '\n' + remote + '\n' + target).encode()).hexdigest(),
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
    value['canUpdate'] = value.get('status') == 'available' and not info['dirty']
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
            'canUpdate': status == 'available' and not info['dirty']}


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
