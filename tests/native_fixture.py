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


if name == 'omarchy-plugin-catalog':
    emit(catalog())
elif name == 'omarchy-plugin-list' or (name == 'omarchy-shell' and args == ['shell', 'listPlugins']):
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
elif name == 'omarchy' and args[:2] == ['bar', 'position']:
    if len(args) > 2 and not state.get('ignoreWrites'):
        state['position'] = args[2]
    print(state['position'])
elif name == 'omarchy' and args[:2] == ['bar', 'set']:
    if not state.get('ignoreWrites'):
        for entries in layout.values():
            for entry in entries:
                if isinstance(entry, dict) and entry['id'] == args[2]:
                    entry[args[3]] = json.loads(args[4]) if '--json' in args else args[4]
elif name == 'omarchy' and args[:2] == ['plugin', 'add']:
    if not state.get('ignoreWrites'):
        state['plugins'].append(dict(id='example.music', name='Music', kinds=['bar-widget'], enabled=False, firstParty=False))
elif name == 'omarchy' and args[:2] == ['plugin', 'enable']:
    if not state.get('ignoreWrites'):
        for plugin in state['plugins']:
            if plugin['id'] == args[2]:
                plugin['enabled'] = True
elif name == 'omarchy-shell' and args == ['shell', 'rescanPlugins']:
    print('ok')
else:
    raise SystemExit('Unsupported fixture call: ' + repr((name, args)))

state_path.write_text(json.dumps(state))
config_path.write_text(json.dumps(config))
