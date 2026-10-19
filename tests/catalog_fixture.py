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
