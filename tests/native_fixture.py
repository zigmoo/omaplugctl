"""Isolated Omarchy command adapter for PHP controller contract checks."""
import json
import os
import pathlib
import sys

root = pathlib.Path(os.environ['PHP_NATIVE_ROOT'])
name, *args = sys.argv[1:]
state_path = root / 'native.json'
state = json.loads(state_path.read_text())
config_path = root / '.config/omarchy/shell.json'
config = json.loads(config_path.read_text())
layout = config['bar']['layout']


def catalog():
    rows = []
    for plugin in state['plugins']:
        directory = root / '.config/omarchy/plugins' / plugin['id']
        rows.append(dict(json.loads((directory / 'manifest.json').read_text()),
                         manifestPath=str(directory / 'manifest.json'), sourceDir=str(directory)))
    return rows


def emit(value):
    print(json.dumps(value))

def select_bar(target):
    for plugin in state['plugins']:
        if 'bar' in plugin['kinds']:
            plugin['active'] = plugin['enabled'] = plugin['id'] == target


if name == 'omarchy-plugin-catalog':
    emit(catalog())
elif name == 'omarchy-plugin-list' or (name == 'omarchy-shell' and args == ['shell', 'listPlugins']):
    pending = state.get('pendingBar')
    if pending and pending['reads'] == 0:
        select_bar(pending['target'])
        del state['pendingBar']
    elif pending:
        pending['reads'] -= 1
    pending_install = state.get('pendingInstall')
    if pending_install and pending_install['reads'] == 0:
        state['plugins'].append(pending_install['plugin'])
        del state['pendingInstall']
    elif pending_install:
        pending_install['reads'] -= 1
    emit(state['plugins'])
elif name == 'omarchy-shell' and args[:2] == ['shell', 'moveBarWidget']:
    pid, target = args[2], json.loads(args[3])
    if not state.get('ignoreWrites'):
        layout[target['fromSection']].pop(target['fromIndex'])
        layout[target['section']].append({'id': pid})
    print('ok')
elif name in ('omarchy-plugin-enable', 'omarchy-plugin-disable', 'omarchy-plugin-remove'):
    if not state.get('ignoreWrites'):
        if name.endswith('remove'):
            state['plugins'] = [p for p in state['plugins'] if p['id'] != args[0]]
        else:
            for plugin in state['plugins']:
                if plugin['id'] == args[0]:
                    plugin['enabled'] = name.endswith('enable')
elif name == 'omarchy' and args[:2] in (['bar', 'use'], ['bar', 'reset']):
    state.setdefault('barCommands', []).append(args)
    target = 'omarchy.bar' if args[1] == 'reset' else args[2]
    if not state.get('ignoreWrites'):
        state['pendingBar'] = {'target': target, 'reads': state.get('barReadbackDelay', 0)}
        if target == 'omarchy.bar':
            config['bar'].pop('id', None)
        else:
            config['bar']['id'] = target
elif name == 'omarchy' and args[:2] == ['bar', 'position']:
    if len(args) == 2 and state.get('legacyPosition'):
        print('omarchy-bar: position is required', file=sys.stderr); sys.exit(1)
    if len(args) == 2 and state.get('positionError'):
        print('Could not read shell configuration', file=sys.stderr); sys.exit(1)
    if len(args) > 2 and not state.get('ignoreWrites'):
        state['position'] = args[2]
        config['bar']['position'] = args[2]
    print(state['position'])
elif name == 'omarchy' and args[:2] == ['bar', 'set']:
    if not state.get('ignoreWrites'):
        for entries in layout.values():
            for entry in entries:
                if isinstance(entry, dict) and entry['id'] == args[2]:
                    entry[args[3]] = json.loads(args[4]) if '--json' in args else args[4]
elif name == 'omarchy' and args[:2] == ['plugin', 'add']:
    state['installAttempts'] = state.get('installAttempts', 0) + 1
    if not state.get('ignoreWrites'):
        plugin = dict(id='example.music', name='Music', kinds=['bar-widget'], enabled=False, firstParty=False)
        directory = root / '.config/omarchy/plugins' / plugin['id']
        directory.mkdir()
        (directory / 'manifest.json').write_text(json.dumps(plugin))
        state['pendingInstall'] = {'plugin': plugin, 'reads': state.get('installDiscoveryDelay', 0)}
elif name == 'omarchy' and args[:2] == ['plugin', 'enable']:
    if not state.get('ignoreWrites'):
        for plugin in state['plugins']:
            if plugin['id'] == args[2]:
                plugin['enabled'] = True
elif name == 'omarchy-shell' and args == ['shell', 'rescanPlugins']:
    print('ok')
elif name == 'systemctl' and args[0] == '--user':
    action = args[1]
    units = args[args.index('--') + 1:]
    if action == 'show':
        for unit in units:
            active = state.get('services', {}).get(unit)
            print(f'Id={unit}\nNames={unit}\nLoadState={"loaded" if active else "not-found"}')
            print(f'ActiveState={active or "inactive"}\nCanStart={"yes" if active else "no"}\nCanStop=yes\n')
    elif action in ('start', 'stop') and units[0] in state.get('services', {}):
        state['services'][units[0]] = 'active' if action == 'start' else 'inactive'
        state.setdefault('serviceCommands', []).append(args)
    else:
        raise SystemExit('Unexpected systemctl call')
elif name == 'omarchy-shell' and args[0] == 'moo.webcamtuner':
    if args[1] == 'status':
        emit({'outputReady': True, 'outputBusy': False})
    elif args[1] in ('outputStart', 'outputStop'):
        state.setdefault('cameraCommands', []).append(args[1])
        services = state.setdefault('services', {})
        if args[1] == 'outputStart':
            services['webcamtuner-output.service'] = 'active'
        else:
            services.pop('webcamtuner-output.service', None)
    else:
        raise SystemExit('Unexpected camera service call')
elif name == 'omarchy-shell' and args == ['shell', 'debugBarGeometry']:
    emit(state.get('barGeometry', []))
elif name == 'omarchy-shell' and args[:2] == ['shell', 'summon']:
    state.setdefault('summons', []).append(args[2:])
    print('unavailable' if state.get('summonError') else 'ok')
elif name == 'xdg-open':
    state.setdefault('openedUrls', []).append(args)
elif name == 'wl-copy':
    if args[:-1] != ['--type', 'text/plain;charset=utf-8', '--']:
        raise SystemExit('Unexpected clipboard arguments')
    state.setdefault('copiedUrls', []).append(args[-1])
elif name == 'curl':
    prefix = 'https://api.github.com'
    if not args[-1].startswith(prefix + '/'):
        raise SystemExit(22)
    document = state.get('githubApi', {}).get(args[-1].removeprefix(prefix))
    if document is None:
        raise SystemExit(22)
    emit(document)
else:
    raise SystemExit('Unsupported fixture call: ' + repr((name, args)))

state_path.write_text(json.dumps(state))
config_path.write_text(json.dumps(config))
