#!/usr/bin/python3
"""OmaPlugCtl: argv-only commands with datasource readback."""
import argparse, datetime, json, os, pathlib, re, stat, subprocess, sys, time, urllib.request, fcntl
import updates
import malware
SELF = 'moo.omaplugctl'
SECTIONS = ('left', 'centerBegin', 'center', 'centerEnd', 'right', 'tray')
EDGES = ('top', 'bottom', 'left', 'right')
SORT_ORDERS = ('name', 'screen', 'updates')


def scan_before_update():
    config = json.loads((pathlib.Path.home()/'.config/omarchy/shell.json').read_text())
    for entries in config.get('bar', {}).get('layout', {}).values():
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get('id') == SELF:
                return entry.get('scanBeforeUpdate', True) is not False
    return True


def set_scan_before_update(value):
    if value not in ('true', 'false'):
        raise ValueError('Choose whether to scan updates before installation.')
    run(['omarchy', 'bar', 'set', SELF, 'scanBeforeUpdate', value, '--json'])
    if scan_before_update() != (value == 'true'):
        raise RuntimeError('The malware scan preference was not confirmed.')
    return {'plugins': inventory(), 'message': 'Malware scan preference saved.'}

def configured_sort():
    config = json.loads((pathlib.Path.home()/'.config/omarchy/shell.json').read_text())
    for entries in config.get('bar', {}).get('layout', {}).values():
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get('id') == SELF:
                return entry.get('sortOrder') if entry.get('sortOrder') in SORT_ORDERS else 'screen'
    return 'screen'

def sort_plugins(plugins, order):
    def name(plugin): return str(plugin.get('name') or plugin['id']).casefold()
    if order == 'screen':
        def placement(plugin):
            positions = [(SECTIONS.index(p['section']), p['index']) for p in plugin.get('instances', []) if p['section'] in SECTIONS]
            return (*min(positions, default=(len(SECTIONS), 0)), name(plugin))
        return sorted(plugins, key=placement)
    if order == 'updates':
        def pending(plugin):
            update = plugin.get('update') or {}
            try: date = datetime.date.fromisoformat(update.get('latestDate', '')).toordinal()
            except (ValueError, TypeError): date = 0
            return (update.get('status') not in ('available', 'rewritten', 'diverged'), -date, name(plugin))
        return sorted(plugins, key=pending)
    return sorted(plugins, key=name)

def set_sort(order):
    if order not in SORT_ORDERS:
        raise ValueError('Choose name, screen, or updates.')
    run(['omarchy', 'bar', 'set', SELF, 'sortOrder', order])
    if configured_sort() != order:
        raise RuntimeError('The selected sort order was not confirmed.')
    return {'plugins': inventory(), 'message': ''}

def bar_position():
    position = run(['omarchy', 'bar', 'position'])
    if position not in EDGES:
        raise RuntimeError('Could not read the current bar position.')
    return position

def set_bar_position(edge):
    if edge not in EDGES:
        raise ValueError('Choose top, bottom, left, or right.')
    run(['omarchy', 'bar', 'position', edge])
    position = bar_position()
    if position != edge:
        raise RuntimeError('New bar position was not confirmed. Try Refresh.')
    return {'plugins': inventory(), 'barPosition': position, 'message': 'Bar position confirmed.'}

def builtin_about_url(pid):
    # HEAD follows GitHub's default branch instead of assuming a branch name.
    base = 'https://github.com/omacom/omarchy'
    root = pathlib.Path(os.environ.get('OMARCHY_PATH') or pathlib.Path.home()/'.local/share/omarchy')
    for manifest in (root/'shell/plugins').rglob('*manifest.json'):
        try:
            data = json.loads(manifest.read_text())
        except (OSError, ValueError):
            continue
        if data.get('id') == pid:
            source = manifest.parent if manifest.name == 'manifest.json' else manifest
            kind = 'tree' if source == manifest.parent else 'blob'
            return base + '/' + kind + '/HEAD/' + source.relative_to(root).as_posix()
    return base

def run(argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=25)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or f'Command failed ({p.returncode})')
    return p.stdout.strip()

def readme_description(metadata):
    directory = metadata.get('sourceDir')
    if not isinstance(directory, str) or not directory:
        return ''
    # Single-file built-ins share a directory; its README is not per-plugin.
    manifest = metadata.get('manifestPath')
    if isinstance(manifest, str) and pathlib.Path(manifest).name != 'manifest.json':
        return ''
    try:
        path = pathlib.Path(directory) / 'README.md'
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(descriptor, 'rb') as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 256 * 1024:
                return ''
            content = file.read(256 * 1024 + 1)
        if len(content) > 256 * 1024:
            return ''
        lines = content.decode('utf-8-sig').splitlines()
    except (OSError, UnicodeError, ValueError):
        return ''
    fence = None
    sections = []
    paragraph = []
    collecting = False
    finished = False
    for line in lines:
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            if collecting:
                finished = True
            continue
        heading = re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*$', line)
        if heading:
            title = re.sub(r'\s+#+$', '', heading[2]).strip()
            collecting = heading[1] == '##' and title.casefold() == 'description for agents'
            if collecting:
                paragraph = []
                sections.append(paragraph)
            finished = False
            continue
        if not collecting or finished:
            continue
        text = line.strip()
        if not text:
            if paragraph:
                finished = True
        elif line.startswith(('    ', '\t')) or re.match(r'^(?:>|[-*+]\s|\d+[.)]\s|!\[)', text):
            finished = True
        else:
            paragraph.append(text)
    # Ambiguous repeated sections or invalid blocks fall back to the manifest.
    return ' '.join(' '.join(sections[0]).split()) if len(sections) == 1 else ''


def plugin_description(metadata):
    widget = metadata.get('barWidget')
    widget = widget if isinstance(widget, dict) else {}
    descriptions = []
    for value in (metadata.get('description'), widget.get('description')):
        if not isinstance(value, str):
            continue
        text = ' '.join(value.split())
        if text and not any(text.casefold() in existing.casefold() for existing in descriptions):
            descriptions.append(text)
    description = readme_description(metadata) or '\n\n'.join(descriptions)
    return description if len(description) <= 1200 else description[:1199] + '…'

def plugin_author(manifest):
    value = manifest.get('author') or manifest.get('authors')
    if not isinstance(value, list):
        value = [value]
    names = []
    for author in value:
        if isinstance(author, dict):
            author = author.get('name')
        if isinstance(author, str) and author.strip():
            names.append(' '.join(author.split()))
    return ', '.join(names)[:200]

def local_update_date(path, manifest):
    # Single-file built-ins share a widgets directory: only their manifest
    # and declared entry points belong to their update date.
    if path.name != 'manifest.json':
        entries = manifest.get('entryPoints', {})
        entries = entries if isinstance(entries, dict) else {}
        files = [path] + [path.parent / entry for entry in entries.values() if isinstance(entry, str)]
    else:
        files = []
        ignored = {'__pycache__', 'archive', 'node_modules', 'build'}
        for directory, dirs, names in os.walk(path.parent):
            dirs[:] = [name for name in dirs if not name.startswith('.') and name not in ignored]
            files.extend(pathlib.Path(directory) / name for name in names if not name.startswith('.') and not name.endswith(('.pyc', '.pyo')))
            if len(files) > 8192:
                return ''
    timestamps = []
    for file in files:
        try:
            if file.is_file():
                timestamps.append(file.stat().st_mtime)
        except OSError:
            continue
    try:
        return datetime.datetime.fromtimestamp(max(timestamps)).date().isoformat() if timestamps else ''
    except (ValueError, OverflowError, OSError):
        return ''

def plugin_details(metadata, history_cache=None):
    manifest = {}
    path = metadata.get('manifestPath')
    if isinstance(path, str):
        try:
            document = json.loads(pathlib.Path(path).read_text())
            if isinstance(document, dict):
                manifest = document
        except (OSError, ValueError):
            pass
    updated = local_update_date(pathlib.Path(path), manifest) if isinstance(path, str) and manifest else ''
    author = plugin_author(manifest)
    result = {'author': author, 'updatedDate': updated}
    if not author or author.casefold() in ('omarchy', 'omarchy team', 'omacom'):
        inferred = first_commit_author(metadata, history_cache if history_cache is not None else author_cache())
        if inferred:
            result.update(inferred)
    return result


def first_commit_author(metadata, cache):
    directory = metadata.get('sourceDir')
    manifest = metadata.get('manifestPath')
    if not directory or not manifest:
        return {}
    try:
        root = pathlib.Path(updates.git(directory, 'rev-parse', '--show-toplevel')).resolve()
        head = updates.git(root, 'rev-parse', 'HEAD')
        paths = [pathlib.Path(manifest)]
        for entry in (metadata.get('entryPoints') or {}).values():
            if isinstance(entry, str): paths.append(pathlib.Path(manifest).parent / entry)
        paths = sorted({str(path.resolve().relative_to(root)) for path in paths})
        key = str(root) + '\n' + head + '\n' + '\n'.join(paths)
        if key in cache:
            return cache[key]
        candidates = []
        for path in paths:
            rows = updates.git(root, 'log', '--follow', '--diff-filter=A', '--format=%H%x1f%an%x1f%ct', '--', path, timeout=20).splitlines()
            if rows:
                commit, author, timestamp = rows[-1].split('\x1f')
                candidates.append((int(timestamp), commit, ' '.join(author.split())[:200]))
        if not candidates:
            cache[key] = {}
            return {}
        timestamp, commit, author = min(candidates)
        result = {'author': author, 'authorSource': 'first-commit', 'authorCommit': commit,
                  'authorDate': datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).date().isoformat(),
                  'authorHistoryShallow': updates.git(root, 'rev-parse', '--is-shallow-repository') == 'true'}
        cache[key] = result
        return result
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
        return {}


def author_cache():
    try:
        path = updates.cache_path().with_name('authors.json')
        if path.stat().st_size < 1_000_000:
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def inventory():
    plugins = json.loads(run(['omarchy-shell', 'shell', 'listPlugins']))
    catalog = json.loads(run(['omarchy-plugin-catalog']))
    metadata = {p['id']: p for p in catalog if isinstance(p, dict) and isinstance(p.get('id'), str)}
    update_cache = updates.load_cache()
    operations = updates.operations()
    history = author_cache()
    previous_history = dict(history)
    config = json.loads((pathlib.Path.home()/'.config/omarchy/shell.json').read_text())
    layout = config.get('bar', {}).get('layout', {})
    result = []
    for p in plugins:
        if 'bar-widget' not in p['kinds']:
            continue
        instances = []
        for section in SECTIONS:
            for index, entry in enumerate(layout.get(section, [])):
                eid = entry if isinstance(entry, str) else entry.get('id', '')
                if eid == p['id']:
                    instances.append({'section': section, 'index': index})
        p['instances'] = instances
        p['description'] = plugin_description(metadata.get(p['id'], {}))
        p.update(plugin_details(metadata.get(p['id'], {}), history))
        p['isSelf'] = p['id'] == SELF
        p['canDisable'] = not p['isSelf'] and p.get('canDisable', True)
        p['canRemove'] = not p['isSelf'] and not p['firstParty'] and (pathlib.Path.home()/'.config/omarchy/plugins'/p['id']).exists()
        p['update'] = updates.cached_status(p, metadata.get(p['id'], {}), update_cache)
        p['operation'] = operations.get(p['id'], {})
        result.append(p)
    if history != previous_history:
        path = updates.cache_path().with_name('authors.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        # Reuse the same atomic-cache writer with an explicit destination.
        updates.save_cache(history, path=path)
    return result

def check_updates():
    plugins = inventory()
    metadata = {p['id']: p for p in json.loads(run(['omarchy-plugin-catalog']))}
    updates.check_all(plugins, metadata)
    plugins = inventory()
    available = sum(p['update']['status'] in ('available', 'rewritten', 'diverged') for p in plugins)
    failed = sum(p['update']['status'] == 'error' for p in plugins)
    return {'plugins': plugins, 'message': f'{available} updates available. {failed} source checks failed.'}

def update_target(pid):
    if not isinstance(pid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', pid) or '..' in pid:
        raise ValueError('Invalid plugin id.')
    plugin = next((p for p in inventory() if p['id'] == pid), None)
    if plugin is None:
        raise ValueError('Unknown bar plugin.')
    metadata = next((p for p in json.loads(run(['omarchy-plugin-catalog'])) if p['id'] == pid), {})
    source = updates.source(plugin, metadata)
    if source is None:
        if plugin['firstParty'] and not plugin.get('clonedFrom'):
            return plugin, None
        raise RuntimeError('No independent Git update repository is configured for this plugin.')
    if source['dirty']:
        raise RuntimeError('This source has local changes. Review them before updating; no files were changed.')
    return plugin, source

def launch_update(pid):
    plugin, source = update_target(pid)
    if source is None or source['kind'] != 'plugin':
        raise RuntimeError('Built-in plugins are updated with Omarchy.')
    if not source['tracking']:
        raise RuntimeError('Choose a branch tracking origin before updating this plugin.')
    log = updates.cache_path().parent / 'operations' / 'launcher.lock'
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = updates.operations().get(pid, {})
        if previous.get('status') == 'working':
            changed = datetime.datetime.fromisoformat(previous['changedAt'])
            if (datetime.datetime.now(datetime.timezone.utc) - changed).total_seconds() < 120:
                return {'plugins': inventory(), 'message': 'This plugin is already updating.'}
        updates.save_operation(pid, status='working', message='Updating plugin…')
        try:
            subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), 'finish-update', pid],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except Exception as exc:
            updates.save_operation(pid, status='error', message=str(exc)[:1200])
            raise
    return {'plugins': inventory(), 'message': 'Updating plugin…'}


def apply_update(pid):
    plugin, source = update_target(pid)
    metadata = next(p for p in json.loads(run(['omarchy-plugin-catalog'])) if p['id'] == pid)
    result = updates.apply_update(plugin, metadata, scan=scan_before_update())
    # User plugin files are watched by Omarchy; a rescan also picks up manifest
    # changes. Failure to rescan does not undo a successfully verified Git update.
    message = 'Updated to ' + result['head'][:8] + '.' if result['changed'] else 'Already up to date.'
    if result.get('backup'):
        message += ' Upstream history reconciled; previous version backed up.'
    if result.get('scan', {}).get('status') == 'no-threats-detected':
        message += ' ClamAV: no threats detected.'
    updates.save_operation(pid, status='done', message=message, backup=result.get('backup', ''), scan=result.get('scan', {}))
    if result['changed']:
        try:
            run(['omarchy-shell', 'shell', 'rescanPlugins'])
        except (RuntimeError, OSError, subprocess.SubprocessError):
            message += ' Refresh the shell to reload the plugin.'
    return {'plugins': inventory(), 'message': message}

def about_url(p):
    directory = pathlib.Path.home()/'.config/omarchy/plugins'/p['id']
    if directory.exists():
        manifest = json.loads((directory/'manifest.json').read_text())
        for key in ('homepage', 'website', 'repository', 'repo'):
            value = manifest.get(key)
            if isinstance(value, dict): value = value.get('url')
            if isinstance(value, str) and value.startswith('https://'):
                return value
        if (directory/'.git').exists():
            value = run(['git', '-C', str(directory), 'remote', 'get-url', 'origin'])
            if value.startswith('https://'): return value.removesuffix('.git')
            if value.startswith('git@github.com:'): return 'https://github.com/' + value.split(':', 1)[1].removesuffix('.git')
    if p['firstParty'] or p.get('clonedFrom', '').startswith('omarchy.'):
        return builtin_about_url(p.get('clonedFrom') or p['id'])
    with urllib.request.urlopen('https://plugins.omarchy.org/catalog.json', timeout=12) as response:
        catalog = json.load(response)
    for entry in catalog['plugins']:
        if entry['id'] == p['id'] and str(entry.get('repo', '')).startswith('https://'):
            return entry['repo']
    raise RuntimeError('No source page found for this plugin.')

def execute(action, pid, section=None, source=None, index=None, confirmed=False):
    before = inventory()
    p = next((p for p in before if p['id'] == pid), None)
    if not p: raise ValueError('Unknown bar plugin.')
    if p.get('isSelf') and action in ('disable', 'remove'):
        raise ValueError('OmaPlugCtl must remain enabled to manage plugins.')
    if action == 'about':
        url = about_url(p)
        run(['xdg-open', url])
        return {'plugins': before, 'message': 'Opened source page.'}
    if action == 'remove':
        if not p['canRemove'] or not confirmed: raise ValueError('Uninstall requires confirmation and an installed third-party plugin.')
        run(['omarchy-plugin-remove', pid, '--yes'])
    elif action in ('enable', 'disable'):
        run(['omarchy-plugin-' + action, pid])
    elif action == 'move':
        if section not in SECTIONS or source not in SECTIONS or index is None:
            raise ValueError('Move requires destination and source instance.')
        if {'section': source, 'index': index} not in p['instances']:
            raise ValueError('Widget layout changed; refresh and select again.')
        placement = {'section': section, 'fromSection': source, 'fromIndex': index}
        output = run(['omarchy-shell', 'shell', 'moveBarWidget', pid, json.dumps(placement)])
        if output != 'ok': raise RuntimeError(output)
    else: raise ValueError('Unsupported action.')
    after = inventory()
    q = next((q for q in after if q['id'] == pid), None)
    if action == 'remove':
        deadline = time.monotonic() + 5
        while q is not None and time.monotonic() < deadline:
            time.sleep(0.2)
            after = inventory()
            q = next((q for q in after if q['id'] == pid), None)
        if q is not None: raise RuntimeError('Plugin removal was not confirmed by the registry; try Refresh.')
    if action in ('enable', 'disable') and (q is None or q['enabled'] != (action == 'enable')):
        raise RuntimeError('Plugin state was not confirmed by the registry.')
    if action == 'move':
        count = lambda plugin, region: sum(i['section'] == region for i in plugin['instances'])
        if q is None or count(q, section) != count(p, section) + (source != section):
            raise RuntimeError('New widget placement was not confirmed.')
    return {'plugins': after, 'message': 'Change confirmed.'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['list', 'position', 'sort', 'set-scan', 'check-updates', 'update', 'finish-update', 'update-status', 'enable', 'disable', 'move', 'remove', 'about'])
    parser.add_argument('id', nargs='?')
    parser.add_argument('--edge', choices=EDGES)
    parser.add_argument('--section'); parser.add_argument('--source'); parser.add_argument('--index', type=int)
    parser.add_argument('--confirmed', action='store_true')
    a = parser.parse_args()
    try:
        if a.action == 'update-status':
            print(json.dumps({'ok': True, 'operations': updates.operations()}))
            return 0
        if a.action == 'finish-update':
            try:
                apply_update(a.id)
                return 0
            except Exception as exc:
                updates.save_operation(a.id, status='error', message=str(exc)[:1200])
                return 1
        if a.action == 'position':
            data = set_bar_position(a.edge)
        else:
            if a.action == 'list': data = {'plugins': inventory(), 'message': ''}
            elif a.action == 'sort': data = set_sort(a.id)
            elif a.action == 'set-scan': data = set_scan_before_update(a.id)
            elif a.action == 'check-updates': data = check_updates()
            elif a.action == 'update': data = launch_update(a.id)
            else: data = execute(a.action, a.id, a.section, a.source, a.index, a.confirmed)
            data['barPosition'] = bar_position()
        data['sortOrder'] = configured_sort()
        data['scanBeforeUpdate'] = scan_before_update()
        data['scannerStatus'] = malware.status()
        data['plugins'] = sort_plugins(data['plugins'], data['sortOrder'])
        print(json.dumps({'ok': True, **data}))
    except Exception as e:
        print(json.dumps({'ok': False, 'message': str(e)})); return 1
    return 0

if __name__ == '__main__': sys.exit(main())
