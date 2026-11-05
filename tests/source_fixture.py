"""Offline source-install adapter. Plugin code is never executed."""
import json
import os
import pathlib
import sys
import tarfile

name, *args = sys.argv[1:]
base = pathlib.Path(os.environ['SOURCE_FIXTURE'])
plugins = base / '.config/omarchy/plugins'
if name == 'git':
    args = [str(base / 'upstream') if a == 'https://github.com/example/plugin' else a for a in args]
    os.execv('/usr/bin/git', ['git', '-c', 'protocol.file.allow=always', *args])
elif name == 'curl':
    if 'api.github.com' in args[-1]:
        print(json.dumps([{'sha': 'a' * 40, 'commit': {
            'committer': {'date': '2026-11-05T12:00:00Z'},
            'author': {'name': '<b>Author</b>'}, 'message': 'Change\nMore'}}]))
    else:
        print(json.dumps({'id_str': args[-1].split('id=')[1].split('&')[0], 'text': '',
                          'entities': {'urls': [{'expanded_url': 'https://github.com/example/plugin'}]}}))
    print('200', end='')
elif name == 'clamscan':
    if '--version' in args:
        print('ClamAV fixture'); sys.exit()
    with tarfile.open(fileobj=sys.stdin.buffer, mode='r|*') as archive:
        for member in archive:
            if b'EICAR-SOURCE-FIXTURE' in archive.extractfile(member).read(): sys.exit(1)
    sys.exit(int(os.environ.get('SOURCE_SCANNER_CODE', '0')))
elif name == 'omarchy-plugin-list':
    print(json.dumps([{'id': p.name, 'enabled': (p / '.git/enabled-fixture').exists()}
                      for p in plugins.glob('*') if (p / 'manifest.json').is_file()]))
elif name == 'omarchy-shell':
    print('ok')
elif name == 'omarchy' and args[:2] == ['plugin', 'enable']:
    if not os.environ.get('SOURCE_IGNORE_ENABLE'):
        (plugins / args[2] / '.git/enabled-fixture').write_text('yes')
else:
    raise SystemExit(f'Unexpected fixture call: {name} {args}')
