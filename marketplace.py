"""Bounded marketplace discovery and explicit native Omarchy installation."""
import datetime
import fcntl
import json
import pathlib
import re
import subprocess
import urllib.request

import updates

CATALOG_URL = 'https://plugins.omarchy.org/catalog.json'
MAX_BYTES = 32 * 1024 * 1024
MAX_PLUGINS = 10_000
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,159}')
REPO = re.compile(r'https://github\.com/[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+(?:\.git)?')
COMMIT = re.compile(r'[0-9a-f]{40}')


def cache_path():
    return updates.cache_path().with_name('marketplace.json')


def text(value, limit):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def normalize(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('plugins'), list):
        raise ValueError('The marketplace returned an invalid catalog.')
    if len(payload['plugins']) > MAX_PLUGINS:
        raise ValueError('The marketplace catalog exceeds the plugin limit.')
    entries, seen = [], set()
    for item in payload['plugins']:
        if not isinstance(item, dict):
            continue
        pid = item.get('id')
        if not isinstance(pid, str) or not ID.fullmatch(pid) or '..' in pid or pid in seen:
            continue
        seen.add(pid)
        if item.get('builtIn') or item.get('sourceType') == 'builtin':
            continue
        repo = item.get('repo', '')
        repo = repo.removesuffix('.git') if isinstance(repo, str) and REPO.fullmatch(repo) else ''
        snapshot = item.get('verificationCommit', '')
        listed = item.get('listingValidatedCommit', '')
        upstream = item.get('upstreamObservedCommit', '')
        snapshot = snapshot if isinstance(snapshot, str) and COMMIT.fullmatch(snapshot) else ''
        # Never promote an old snapshot to a currently verified upstream listing.
        verified = bool(snapshot and snapshot == listed == upstream
                        and item.get('verificationStatus') == 'verified'
                        and item.get('verificationSnapshotStatus') == 'verified'
                        and item.get('verificationCoverage') == 'snapshot-verified')
        coverage = 'snapshot-verified' if verified else (
            'update-unverified' if snapshot and item.get('verificationCoverage') == 'update-unverified'
            else 'unverified')
        tags = item.get('tags', [])
        tags = [text(tag, 60) for tag in tags[:20]] if isinstance(tags, list) else []
        entry = {
            'id': pid, 'name': text(item.get('name'), 160) or pid,
            'description': text(item.get('description'), 1200),
            'author': text(item.get('author'), 160), 'tags': tags,
            'category': text(item.get('category'), 80), 'repo': repo,
            'verified': verified, 'coverage': coverage, 'verifiedCommit': snapshot,
            'installable': bool(repo and item.get('installAvailable') is True
                                and item.get('repositoryLayout') == 'root-plugin'),
            'installNote': text(item.get('installNote'), 500),
        }
        entry['searchText'] = ' '.join([pid, entry['name'], entry['description'],
                                      entry['author'], entry['category'], *tags]).lower()
        entries.append(entry)
    if not entries:
        raise ValueError('The marketplace catalog contains no community plugins.')
    return sorted(entries, key=lambda entry: (entry['name'].casefold(), entry['id']))


def read_cache():
    try:
        path = cache_path()
        if path.stat().st_size > MAX_BYTES:
            return None
        value = json.loads(path.read_text())
        if value.get('schema') == 1 and isinstance(value.get('entries'), list) and len(value['entries']) <= MAX_PLUGINS:
            # Revalidate cached rows too; the cache is data, never authority for commands.
            if (isinstance(value.get('fetchedAt'), str) and all(
                    isinstance(p, dict)
                    and all(isinstance(p.get(key), str) for key in ('id', 'name', 'description', 'author', 'searchText', 'coverage', 'repo'))
                    and ID.fullmatch(p['id']) and '..' not in p['id']
                    and type(p.get('verified')) is bool and type(p.get('installable')) is bool
                    and p['coverage'] in ('snapshot-verified', 'update-unverified', 'unverified')
                    for p in value['entries'])):
                datetime.datetime.fromisoformat(value['fetchedAt'])
                return value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def load(refresh=False):
    cached = read_cache()
    warning = ''
    if cached is None or refresh:
        try:
            request = urllib.request.Request(CATALOG_URL, headers={'User-Agent': 'OmaPlugCtl/0.15'})
            with urllib.request.urlopen(request, timeout=25) as response:
                if response.geturl().split('?', 1)[0] != CATALOG_URL:
                    raise ValueError('The marketplace redirected away from its catalog.')
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError('The marketplace catalog exceeds the download limit.')
            entries = normalize(json.loads(raw))
            cached = {'schema': 1, 'entries': entries,
                      'fetchedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            updates.save_cache(cached, path=cache_path())
        except (OSError, ValueError) as error:
            if cached is None:
                raise RuntimeError('Could not load the marketplace. Check your connection and try Refresh.') from error
            warning = 'Refresh failed; showing the saved catalog.'
    return cached, warning


def command(argv, timeout=25):
    process = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL)
    if process.returncode:
        raise RuntimeError((process.stderr.strip() or process.stdout.strip()
                            or 'Omarchy could not complete the action.')[-1800:])
    return process.stdout.strip()


def installed_plugins():
    plugins = json.loads(command(['omarchy-plugin-list', '--json']))
    if not isinstance(plugins, list):
        raise RuntimeError('Could not read the installed plugins.')
    return {p['id']: p for p in plugins if isinstance(p, dict) and isinstance(p.get('id'), str)}


def state(refresh=False):
    catalog, warning = load(refresh)
    installed = installed_plugins()
    return {'entries': [{**p, 'installed': p['id'] in installed,
                         'enabled': installed.get(p['id'], {}).get('enabled') is True}
                        for p in catalog['entries']],
            'fetchedAt': catalog['fetchedAt'], 'message': warning}


def entry(pid):
    if not isinstance(pid, str) or not ID.fullmatch(pid) or '..' in pid:
        raise ValueError('Invalid marketplace plugin id.')
    catalog, _ = load()
    found = next((p for p in catalog['entries'] if p['id'] == pid), None)
    if found is None:
        raise ValueError('This plugin is not in the saved marketplace catalog. Refresh and try again.')
    if not isinstance(found.get('repo'), str) or not REPO.fullmatch(found['repo']):
        raise ValueError('No supported HTTPS source repository is available for this plugin.')
    return found


def install(pid):
    plugin = entry(pid)
    if not plugin.get('installable'):
        raise ValueError('This plugin requires manual setup. Open its source page for instructions.')
    lock_path = cache_path().with_suffix('.install.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if pid in installed_plugins():
            raise ValueError('This plugin is already installed. Refresh the list.')
        # Do not execute catalog installCommand strings, and do not enable the
        # fetched checkout. Omarchy owns validation, placement and installation.
        command(['omarchy', 'plugin', 'add', plugin['repo'], '--yes'], timeout=180)
        installed = installed_plugins().get(pid)
        if installed is None:
            raise RuntimeError('Installation did not confirm the expected plugin id. Refresh and inspect the installed plugins.')
        if installed.get('enabled'):
            raise RuntimeError('The plugin was installed but is already enabled. Inspect its state in Plugins.')
    result = state()
    result['message'] = plugin['name'] + ' installed, disabled. Click Enable when ready.'
    return result


def enable(pid):
    plugin = entry(pid)
    if pid not in installed_plugins():
        raise ValueError('Install this plugin before enabling it.')
    command(['omarchy', 'plugin', 'enable', pid])
    if installed_plugins().get(pid, {}).get('enabled') is not True:
        raise RuntimeError('Enabling was not confirmed by Omarchy. Refresh and try again.')
    result = state()
    result['message'] = plugin['name'] + ' enabled.'
    return result


def source(pid):
    plugin = entry(pid)
    command(['xdg-open', plugin['repo']])
    return {'message': 'Opened source page.'}
