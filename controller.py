#!/usr/bin/python3
"""OmaPlugCtl: argv-only commands with datasource readback."""
import argparse, datetime, json, os, pathlib, re, subprocess, sys, time, urllib.request
import updates
SELF = 'moo.omaplugctl'
SECTIONS = ('left', 'centerBegin', 'center', 'centerEnd', 'right', 'tray')
EDGES = ('top', 'bottom', 'left', 'right')
SORT_ORDERS = ('name', 'screen', 'updates')

def configured_sort():
    config = json.loads((pathlib.Path.home()/'.config/omarchy/shell.json').read_text())
    for entries in config.get('bar', {}).get('layout', {}).values():
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get('id') == SELF:
                return entry.get('sortOrder') if entry.get('sortOrder') in SORT_ORDERS else 'name'
    return 'name'

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
            return (update.get('status') not in ('available', 'diverged'), -date, name(plugin))
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
    description = '\n\n'.join(descriptions)
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

def plugin_details(metadata):
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
    return {'author': plugin_author(manifest), 'updatedDate': updated}

def inventory():
    plugins = json.loads(run(['omarchy-shell', 'shell', 'listPlugins']))
    catalog = json.loads(run(['omarchy-plugin-catalog']))
    metadata = {p['id']: p for p in catalog if isinstance(p, dict) and isinstance(p.get('id'), str)}
    update_cache = updates.load_cache()
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
        p.update(plugin_details(metadata.get(p['id'], {})))
        p['isSelf'] = p['id'] == SELF
        p['canDisable'] = not p['isSelf'] and p.get('canDisable', True)
        p['canRemove'] = not p['isSelf'] and not p['firstParty'] and (pathlib.Path.home()/'.config/omarchy/plugins'/p['id']).exists()
        p['update'] = updates.cached_status(p, metadata.get(p['id'], {}), update_cache)
        result.append(p)
    return result

def check_updates():
    plugins = inventory()
    metadata = {p['id']: p for p in json.loads(run(['omarchy-plugin-catalog']))}
    updates.check_all(plugins, metadata)
    plugins = inventory()
    available = sum(p['update']['status'] in ('available', 'diverged') for p in plugins)
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
    update_target(pid)
    subprocess.Popen(['omarchy-launch-tui', 'python3', str(pathlib.Path(__file__).resolve()), 'review-update', pid],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return {'plugins': inventory(), 'message': 'Update review opened in a terminal. Review the changes and confirm there.'}

def review_update(pid):
    plugin, source = update_target(pid)
    if plugin['firstParty'] and not plugin.get('clonedFrom'):
        print('This plugin ships with Omarchy. The Omarchy updater updates the system and its built-in plugins.')
        if input('Open the Omarchy system updater? [y/N] ').strip().lower() != 'y':
            return 0
        command = ['omarchy-update']
    else:
        # A local checkout can be ahead or diverged; the supported updater
        # presents its diff and only applies a fast-forward after confirmation.
        command = ['omarchy', 'plugin', 'update', pid]
    code = subprocess.run(command).returncode
    cache = updates.load_cache()
    cache.pop(pid, None)
    if code == 0:
        try:
            metadata = next(p for p in json.loads(run(['omarchy-plugin-catalog'])) if p['id'] == pid)
            refreshed = updates.source(plugin, metadata)
            if refreshed:
                cache[pid] = updates.compare_source(refreshed, updates.git(refreshed['root'], 'rev-parse', 'FETCH_HEAD'), metadata)
        except (RuntimeError, OSError, ValueError, StopIteration, subprocess.SubprocessError):
            pass
    updates.save_cache(cache)
    # Plugin updates rescan the shell, recreating this manager. This terminal
    # process survives that rescan and brings the menu back for the user.
    for attempt in range(40):
        try:
            run(['omarchy-shell', SELF, 'show'])
            state = json.loads(run(['omarchy-shell', SELF, 'status']))
            if state.get('open') and state.get('anchored'):
                break
        except (RuntimeError, OSError, subprocess.SubprocessError):
            time.sleep(0.2)
    return code

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
    parser.add_argument('action', choices=['list', 'position', 'sort', 'check-updates', 'update', 'review-update', 'enable', 'disable', 'move', 'remove', 'about'])
    parser.add_argument('id', nargs='?')
    parser.add_argument('--edge', choices=EDGES)
    parser.add_argument('--section'); parser.add_argument('--source'); parser.add_argument('--index', type=int)
    parser.add_argument('--confirmed', action='store_true')
    a = parser.parse_args()
    try:
        if a.action == 'review-update':
            return review_update(a.id)
        if a.action == 'position':
            data = set_bar_position(a.edge)
        else:
            if a.action == 'list': data = {'plugins': inventory(), 'message': ''}
            elif a.action == 'sort': data = set_sort(a.id)
            elif a.action == 'check-updates': data = check_updates()
            elif a.action == 'update': data = launch_update(a.id)
            else: data = execute(a.action, a.id, a.section, a.source, a.index, a.confirmed)
            data['barPosition'] = bar_position()
        data['sortOrder'] = configured_sort()
        data['plugins'] = sort_plugins(data['plugins'], data['sortOrder'])
        print(json.dumps({'ok': True, **data}))
    except Exception as e:
        print(json.dumps({'ok': False, 'message': str(e)})); return 1
    return 0

if __name__ == '__main__': sys.exit(main())
