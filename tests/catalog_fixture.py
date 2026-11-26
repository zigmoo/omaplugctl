"""Offline UI fixture: never contacts or changes the real Omarchy shell."""
import json
import pathlib
import sys
import time

path = pathlib.Path(__file__).with_name('fixture-state.json')
try:
    saved = json.loads(path.read_text())
except FileNotFoundError:
    saved = {'installed': False, 'enabled': False}
action = sys.argv[1]
time.sleep(0.25)
if action == 'open' and sys.argv[2] == 'example.setup':
    print(json.dumps({'ok': True, 'message': 'Open requested.'}))
    sys.exit()
if action == 'source-details':
    print(json.dumps({'ok': True, 'repo': sys.argv[2], 'details': {
        'lastCommitAt': '2026-11-05T12:00:00Z', 'commit': 'b' * 40,
        'commitAuthor': '<b>Commit Person</b>', 'commitSubject': 'Latest change', 'error': ''}}))
    sys.exit()
if action.startswith('source-'):
    if action == 'source-check':
        row = {'id': 'example.url', 'name': '<b>URL Plugin</b>', 'description': 'Evaluated source',
               'author': 'Person', 'repo': 'https://github.com/example/url', 'verified': False,
               'coverage': 'locally-validated', 'installable': True, 'directSource': True,
               'evaluation': 'a' * 32, 'validation': 'Manifest valid; scanned commit abc123.',
               'installed': False, 'enabled': False}
        if sys.argv[2] == 'https://plugins.omarchy.org/plugin.html?id=example.setup':
            row.update(id='example.setup', name='Setup Plugin', opensWithoutBar=True,
                       installNote='Run the documented setup before enabling.')
        saved['source'] = row
    else:
        row = saved['source']
        if action == 'source-install': row['installed'] = True
        if action == 'source-enable': row['enabled'] = True
    path.write_text(json.dumps(saved))
    print(json.dumps({'ok': True, 'sourceEntries': [row], 'message': 'Source action confirmed.'}))
    sys.exit()
if action == 'catalog-install' and sys.argv[2] == 'example.retry':
    if not saved.get('retryAttempted'):
        saved['retryAttempted'] = True
        path.write_text(json.dumps(saved))
        print(json.dumps({'ok': False, 'message': 'Fixture is on disk. Click Retry to check again.'}))
        sys.exit(1)
    row = {'id': 'example.retry', 'name': 'Retry Fixture', 'description': 'Checks retry actions.', 'author': 'Person',
           'verified': True, 'coverage': 'snapshot-verified', 'searchText': 'retry fixture',
           'installed': True, 'enabled': False, 'installable': True, 'repo': 'https://github.com/example/fixture'}
    print(json.dumps({'ok': True, 'entries': [row], 'message': 'Fixture installed. Click Enable when ready.'}))
    sys.exit()
if action == 'catalog-install':
    saved['installed'] = True
if action == 'catalog-enable':
    saved['enabled'] = True
path.write_text(json.dumps(saved))
rows = [
    {'id': 'example.radio', 'name': 'Radio', 'description': 'Listen to stations.', 'author': 'Jane',
     'verified': True, 'coverage': 'snapshot-verified', 'searchText': 'radio jane music stations', **saved},
    {'id': 'example.clock', 'name': 'Clocks', 'description': 'A clock update.', 'author': 'Other',
     'verified': False, 'coverage': 'update-unverified', 'searchText': 'clocks time', 'installed': False, 'enabled': False},
    {'id': 'example.markup', 'name': '<img src="https://example.invalid/tracker">',
     'description': '<b>Literal markup</b>', 'author': '<i>Person</i>', 'verified': True,
     'coverage': 'snapshot-verified', 'searchText': 'markup', 'installed': False, 'enabled': False},
]
for row in rows:
    row.update(repo='https://github.com/example/fixture', installable=True)
message = 'Opened fixture source.' if action == 'catalog-source' else 'Fixture catalog refreshed.'
print(json.dumps({'ok': True, 'entries': rows, 'fetchedAt': '2026-10-19T04:00:00+00:00', 'message': message}))
