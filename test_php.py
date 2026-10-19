"""Exercise PHP against the existing contracts and real isolated Git fixtures."""
import base64
import datetime
import io
import json
import os
import pathlib
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import controller as reference
import marketplace as marketplace_reference
import test_updates as repository_contracts

ROOT = pathlib.Path(__file__).resolve().parent


def php(function, *arguments):
    result = subprocess.run(['php', '-n', str(ROOT / 'tests/php_bridge.php')],
                            input=json.dumps({'function': function, 'args': arguments}, default=str),
                            text=True, capture_output=True, timeout=70)
    if result.stderr:
        raise AssertionError('PHP emitted diagnostics: ' + result.stderr)
    response = json.loads(result.stdout)
    if not response['ok']:
        raise (ValueError if response['invalid'] else RuntimeError)(response['message'])
    return response


class PhpUpdates:
    def __getattr__(self, name):
        def invoke(*args, **kwargs):
            if name == 'git':
                args = (str(args[0]), list(args[1:]), kwargs.get('timeout', 10), kwargs.get('body'), kwargs.get('raw', False))
            elif name == 'apply_update':
                args = (*args, kwargs.get('scan', True))
            elif name == 'save_cache' and kwargs:
                args = (*args, kwargs.get('path'))
            return php('Updates\\' + name, *args)['result']
        return invoke


PHP_UPDATES = PhpUpdates()


class PhpRepositoryTests(unittest.TestCase):
    """Reuse the repository contract cases with PHP as their implementation."""
    command = repository_contracts.UpdateTests.command
    configure = repository_contracts.UpdateTests.configure
    commit = repository_contracts.UpdateTests.commit
    advance_remote = repository_contracts.UpdateTests.advance_remote
    rewritten_remote = repository_contracts.UpdateTests.rewritten_remote
    check = repository_contracts.UpdateTests.check

    def setUp(self):
        repository_contracts.UpdateTests.setUp(self)
        switch = patch.object(repository_contracts, 'updates', PHP_UPDATES)
        switch.start(); self.addCleanup(switch.stop)
        # A local scanner fixture reads the actual tar, preserving scan coverage.
        bin_dir = self.base / 'bin'; bin_dir.mkdir()
        scanner = bin_dir / 'clamscan'
        scanner.write_text('#!/usr/bin/python3\n'
                           'import os,sys,tarfile\n'
                           'if "--version" in sys.argv: print("ClamAV fixture");sys.exit()\n'
                           'with tarfile.open(fileobj=sys.stdin.buffer,mode="r|*") as archive:\n'
                           ' for member in archive:\n'
                           '  body=archive.extractfile(member).read()\n'
                           '  if b"EICAR-PHP-FIXTURE" in body: sys.exit(1)\n'
                           'if os.environ.get("PHP_MUTATE_INSTALLED"):\n'
                           ' import pathlib;pathlib.Path(os.environ["PHP_MUTATE_INSTALLED"],"local-during-scan.txt").write_text("preserve this edit")\n'
                           'sys.exit(int(os.environ.get("PHP_SCANNER_CODE","0")))\n')
        scanner.chmod(0o755)
        env = patch.dict(os.environ, {'PATH': str(bin_dir) + ':' + os.environ['PATH']})
        env.start(); self.addCleanup(env.stop)
        database = self.base / 'state/omarchy/omaplugctl/clamav'; database.mkdir(parents=True)
        (database / 'daily.cvd').write_text('fixture signatures')
        (database / 'last-check.json').write_text(json.dumps({'checkedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}))

    def test_failed_fetch_reports_error(self):
        self.command('git', '-C', str(self.installed), 'remote', 'set-url', 'origin', str(self.base / 'unavailable'))
        self.assertEqual(self.check()['status'], 'error')

    def test_real_scan_detection_preserves_checkout(self):
        (self.writer / 'detected.txt').write_text('EICAR-PHP-FIXTURE')
        self.commit(self.writer, 'Detected fixture'); self.command('git', '-C', str(self.writer), 'push')
        before = PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(RuntimeError, 'detected a threat'):
            PHP_UPDATES.apply_update(self.plugin, self.metadata)
        self.assertEqual(PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD'), before)

    def test_scan_error_preserves_checkout(self):
        self.advance_remote()
        before = PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD')
        with patch.dict(os.environ, {'PHP_SCANNER_CODE': '2'}), self.assertRaisesRegex(RuntimeError, 'could not complete'):
            PHP_UPDATES.apply_update(self.plugin, self.metadata)
        self.assertEqual(PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD'), before)

    def test_local_change_during_scan_preserves_checkout(self):
        self.advance_remote()
        before = PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD')
        with patch.dict(os.environ, {'PHP_MUTATE_INSTALLED': str(self.installed)}), self.assertRaisesRegex(RuntimeError, 'changed during malware'):
            PHP_UPDATES.apply_update(self.plugin, self.metadata)
        self.assertEqual(PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD'), before)
        self.assertEqual((self.installed / 'local-during-scan.txt').read_text(), 'preserve this edit')

    def test_archive_includes_export_ignored_files_and_symlink_text(self):
        (self.installed / '.gitattributes').write_text('hidden.txt export-ignore\n')
        (self.installed / 'hidden.txt').write_text('must be scanned')
        (self.installed / 'external-link').symlink_to('/etc/passwd')
        self.commit(self.installed, 'Complete snapshot fixture')
        directory = self.base / 'snapshot'
        path, count = php('Malware\\snapshot', str(self.installed), PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD'), str(directory))['result']
        with tarfile.open(path) as archive:
            bodies = [archive.extractfile(member).read() for member in archive]
        self.assertEqual(count, len(bodies))
        self.assertIn(b'must be scanned', bodies)
        self.assertIn(b'/etc/passwd', bodies)

    def test_lfs_snapshot_fails_closed(self):
        (self.installed / 'lfs').write_text('version https://git-lfs.github.com/spec/v1\noid sha256:abc\n')
        self.commit(self.installed, 'LFS fixture')
        with self.assertRaisesRegex(RuntimeError, 'LFS payloads'):
            php('Malware\\snapshot', str(self.installed), PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD'), str(self.base / 'snapshot'))


for _name in (
    'remote_update_is_detected_without_installing_it', 'current_repository_and_cache',
    'dirty_repository_cannot_update', 'diverged_history_cannot_update',
    'changed_local_head_invalidates_cached_result', 'old_up_to_date_result_requires_a_new_check',
    'builtin_checks_are_scoped_to_the_plugin', 'missing_source_repository_is_explicit',
    'click_fast_forwards_running_symlinked_checkout', 'apply_preserves_dirty_and_diverged_checkouts',
    'update_follows_checked_out_tracking_branch_instead_of_remote_head', 'detached_checkout_is_preserved',
    'shared_omarchy_repo_is_never_updated_by_plugin_click', 'git_update_does_not_run_a_post_merge_hook',
    'rewritten_history_updates_with_verified_backup', 'whitespace_changes_are_not_treated_as_equivalent',
    'empty_commit_is_not_silently_discarded', 'ignored_local_file_is_preserved_during_reconciliation',
):
    setattr(PhpRepositoryTests, 'test_' + _name, getattr(repository_contracts.UpdateTests, 'test_' + _name))


class PhpParityTests(unittest.TestCase):
    def test_unicode_casefold_and_author_names(self):
        for value in ('ÉLODIE', 'Straße', 'İstanbul', 'Aether'):
            self.assertEqual(php('fold', value)['result'], value.casefold())
        for manifest in ({'author': 'Jason'}, {'authors': ['Jane', {'name': 'Élodie'}]}, {'author': {'name': 'Person'}}, {}):
            self.assertEqual(php('plugin_author', manifest)['result'], reference.plugin_author(manifest))

    def test_descriptions_and_literal_markup(self):
        for metadata in ({}, {'description': '<img src=x>'}, {'description': 'A' * 1400},
                         {'description': 'Widget', 'barWidget': {'description': 'More widget details'}}):
            self.assertEqual(php('plugin_description', metadata)['result'], reference.plugin_description(metadata))

    def test_readme_sections_match_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary); metadata = {'sourceDir': temporary, 'manifestPath': str(path / 'manifest.json')}
            for content in ('## Description for Agents\n\nOne paragraph.\nContinued.\n\nIgnore this.\n',
                            '```md\n## Description for Agents\nWrong\n```\n',
                            '## Description for Agents\n# Other\n',
                            '## Description for Agents\n<b>Literal</b>\n',
                            '## Description for Agents\nFirst\n## Description for Agents\nSecond\n'):
                (path / 'README.md').write_text(content)
                self.assertEqual(php('readme_description', metadata)['result'], reference.readme_description(metadata))
            (path / 'README.md').unlink(); (path / 'README.md').symlink_to('/etc/passwd')
            self.assertEqual(php('readme_description', metadata)['result'], '')

    def test_marketplace_normalization_matches_verification_contract(self):
        base = {'id': 'example.theme', 'name': 'Élodie', 'author': 'Person', 'tags': ['music'],
                'repo': 'https://github.com/example/theme.git', 'verificationStatus': 'verified',
                'verificationSnapshotStatus': 'verified', 'verificationCoverage': 'snapshot-verified',
                'verificationCommit': 'a' * 40, 'listingValidatedCommit': 'a' * 40,
                'upstreamObservedCommit': 'a' * 40, 'repositoryLayout': 'root-plugin', 'installAvailable': True}
        for fields in ({}, {'upstreamObservedCommit': 'b' * 40}, {'repo': 'https://github.com/example/x;touch bad'},
                       {'verificationCoverage': 'update-unverified'}, {'description': '<b>Literal</b>'}):
            payload = {'plugins': [{**base, **fields}]}
            self.assertEqual(php('Marketplace\\normalize', payload)['result'], marketplace_reference.normalize(payload))

    def test_sorting_matches_name_screen_and_update_order(self):
        rows = [{'id':'b','name':'Élodie','instances':[{'section':'right','index':1}], 'update':{}},
                {'id':'a','name':'Alpha','instances':[{'section':'centerEnd','index':0}], 'update':{'status':'available','latestDate':'2026-10-01'}},
                {'id':'c','name':'charlie','instances':[], 'update':{'status':'available','latestDate':'2026-10-10'}}]
        for order in ('name','screen','updates'):
            actual = php('sort_plugins', rows, order)['result']
            for row in actual:
                if row.get('update') == []: row['update'] = {}
            self.assertEqual(actual, reference.sort_plugins(rows, order))

    def test_invalid_identifiers_and_settings_fail_before_native_calls(self):
        for value in ('../bad', 'x;touch bad', '--help', ''):
            with self.assertRaises(ValueError): php('update_target', value)
        for value in ('49', '201', 'true', ''):
            with self.assertRaises(ValueError): php('set_bar_icon_scale', value)
        for value in ('-1', '11', '1.2'):
            with self.assertRaises(ValueError): php('set_workspace_count', value)


if __name__ == '__main__':
    unittest.main()

class PhpNativeStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = pathlib.Path(self.temporary.name)
        self.bin = self.base / 'bin'; self.bin.mkdir()
        commands = ['omarchy', 'omarchy-shell', 'omarchy-plugin-catalog', 'omarchy-plugin-list',
                    'omarchy-plugin-enable', 'omarchy-plugin-disable', 'omarchy-plugin-remove']
        import shlex
        for name in commands:
            target = self.bin / name
            target.write_text('#!/bin/bash\nexec /usr/bin/python3 ' + shlex.quote(str(ROOT / 'tests/native_fixture.py')) + ' ' + name + ' "$@"\n')
            target.chmod(0o755)
        for pid in ['moo.omaplugctl', 'moo.workspaces', 'example.radio', 'example.music']:
            path = self.base / '.config/omarchy/plugins' / pid; path.mkdir(parents=True)
            metadata = dict(id=pid, name=pid, author='Fixture Author', kinds=['bar-widget'], entryPoints={})
            if pid == 'moo.workspaces':
                metadata.update(omarchy={'clonedFrom': 'omarchy.workspaces'}, barWidget={
                    'defaults': {'pinnedCount': 5}, 'schema': [{'key': 'pinnedCount', 'type': 'integer'}]})
            (path / 'manifest.json').write_text(json.dumps(metadata))
        self.config_path = self.base / '.config/omarchy/shell.json'
        self.config_path.write_text(json.dumps({'bar': {'layout': {
            'left': [{'id': 'example.radio'}, {'id': 'example.radio'}],
            'centerBegin': [], 'center': [], 'centerEnd': [{'id': 'moo.workspaces', 'pinnedCount': 5}],
            'tray': [], 'right': [{'id': 'moo.omaplugctl', 'scanBeforeUpdate': False}]}}}))
        self.native_path = self.base / 'native.json'
        self.native_path.write_text(json.dumps({'position': 'top', 'plugins': [
            dict(id=pid, name=pid, enabled=True, firstParty=False, kinds=['bar-widget'])
            for pid in ['moo.omaplugctl', 'moo.workspaces', 'example.radio']]}))
        self.env = dict(os.environ, HOME=str(self.base), XDG_STATE_HOME=str(self.base / 'state'),
                        XDG_DATA_HOME=str(self.base / 'data'), PHP_NATIVE_ROOT=str(self.base),
                        PATH=str(self.bin) + ':' + os.environ['PATH'])
        switch = patch.dict(os.environ, self.env); switch.start(); self.addCleanup(switch.stop)

    def invoke(self, *args):
        completed = subprocess.run(['php', '-n', str(ROOT / 'controller.php'), *args],
                                   env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(completed.stderr, '')
        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode == 0, result['ok'])
        return result

    def test_settings_and_workspace_changes_are_read_back(self):
        self.assertEqual(self.invoke('settings'), {'ok': True, 'barIconScale': 100})
        self.assertEqual(self.invoke('icon-scale', '125')['barIconScale'], 125)
        self.assertEqual(self.invoke('workspace-count', '8')['workspaceSettings'], {'id': 'moo.workspaces', 'count': 8})
        self.assertEqual(self.invoke('sort', 'name')['sortOrder'], 'name')
        self.assertTrue(self.invoke('set-scan', 'true')['scanBeforeUpdate'])
        self.assertEqual(self.invoke('position', '--edge', 'left')['barPosition'], 'left')

    def test_legacy_bar_position_reads_saved_state_and_confirms_writes(self):
        state = json.loads(self.native_path.read_text()); state['legacyPosition'] = True
        self.native_path.write_text(json.dumps(state))
        config = json.loads(self.config_path.read_text()); config['bar']['position'] = 'bottom'
        self.config_path.write_text(json.dumps(config))
        self.assertEqual(self.invoke('list')['barPosition'], 'bottom')
        self.assertEqual(self.invoke('position', '--edge', 'left')['barPosition'], 'left')
        config = json.loads(self.config_path.read_text()); config['bar']['position'] = 'invalid'
        self.config_path.write_text(json.dumps(config))
        self.assertFalse(self.invoke('list')['ok'])
        state['legacyPosition'] = False; state['positionError'] = True
        self.native_path.write_text(json.dumps(state))
        self.assertFalse(self.invoke('list')['ok'])

    def test_failed_setting_readback_is_an_error(self):
        state = json.loads(self.native_path.read_text()); state['ignoreWrites'] = True
        self.native_path.write_text(json.dumps(state))
        for args in [('icon-scale', '150'), ('workspace-count', '9'), ('set-scan', 'true'),
                     ('sort', 'name'), ('position', '--edge', 'bottom')]:
            with self.subTest(args=args): self.assertFalse(self.invoke(*args)['ok'])

    def test_enable_disable_and_selected_duplicate_move_are_confirmed(self):
        result = self.invoke('disable', 'example.radio'); self.assertTrue(result['ok'])
        self.assertFalse(next(p for p in result['plugins'] if p['id'] == 'example.radio')['enabled'])
        self.assertTrue(self.invoke('enable', 'example.radio')['ok'])
        result = self.invoke('move', 'example.radio', '--section', 'right', '--source', 'left', '--index', '1')
        self.assertTrue(result['ok'])
        row = next(p for p in result['plugins'] if p['id'] == 'example.radio')
        self.assertEqual(row['instances'], [{'section': 'left', 'index': 0}, {'section': 'right', 'index': 1}])
        self.assertFalse(self.invoke('move', 'example.radio', '--section', 'right', '--source', 'left', '--index', '7')['ok'])

    def test_failed_state_readback_and_self_removal_are_blocked(self):
        self.assertFalse(self.invoke('disable', 'moo.omaplugctl')['ok'])
        self.assertFalse(self.invoke('remove', 'moo.omaplugctl', '--confirmed')['ok'])
        self.assertFalse(self.invoke('remove', 'example.radio')['ok'])
        state = json.loads(self.native_path.read_text()); state['ignoreWrites'] = True
        self.native_path.write_text(json.dumps(state))
        self.assertFalse(self.invoke('disable', 'example.radio')['ok'])

    def test_confirmed_removal_uses_native_registry(self):
        result = self.invoke('remove', 'example.radio', '--confirmed')
        self.assertTrue(result['ok']); self.assertNotIn('example.radio', [p['id'] for p in result['plugins']])

    def test_catalog_install_and_enable_are_separate(self):
        payload = {'plugins': [dict(id='example.music', name='Music', repo='https://github.com/example/music',
                                   installAvailable=True, repositoryLayout='root-plugin')]}
        entries = php('Marketplace\\normalize', payload)['result']
        php('save_json', {'schema': 1, 'entries': entries, 'fetchedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()},
            str(self.base / 'state/omarchy/omaplugctl/marketplace.json'))
        result = self.invoke('catalog-install', 'example.music')
        self.assertTrue(result['ok']); self.assertTrue(result['entries'][0]['installed']); self.assertFalse(result['entries'][0]['enabled'])
        self.assertTrue(self.invoke('catalog-enable', 'example.music')['entries'][0]['enabled'])
        self.assertFalse(self.invoke('catalog-install', 'example.music')['ok'])

    def test_detached_update_finishes_after_launcher_returns(self):
        import time
        path = self.base / '.config/omarchy/plugins/example.radio'
        def git(*args):
            return subprocess.check_output(['git', *map(str,args)], stderr=subprocess.DEVNULL, text=True).strip()
        git('init', '--initial-branch=master', path)
        git('-C', path, 'config', 'user.name', 'Fixture Author')
        git('-C', path, 'config', 'user.email', 'fixture@example.invalid')
        git('-C', path, 'add', '.'); git('-C', path, 'commit', '-m', 'Initial plugin')
        remote = self.base / 'origin.git'; git('clone', '--bare', path, remote)
        git('-C', path, 'remote', 'add', 'origin', remote)
        git('-C', path, 'fetch', 'origin'); git('-C', path, 'branch', '--set-upstream-to=origin/master', 'master')
        writer = self.base / 'writer'; git('clone', remote, writer)
        git('-C', writer, 'config', 'user.name', 'Fixture Author');git('-C', writer, 'config', 'user.email', 'fixture@example.invalid')
        (writer / 'Widget.qml').write_text('updated')
        git('-C', writer, 'add', '.');git('-C', writer, 'commit', '-m', 'Update fixture');git('-C', writer, 'push')
        expected = git('-C', writer, 'rev-parse', 'HEAD')
        self.assertTrue(self.invoke('update', 'example.radio')['ok'])
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            operation = self.invoke('update-status')['operations'].get('example.radio', {})
            if operation.get('status') in ('done', 'error'): break
            time.sleep(.05)
        self.assertEqual(operation.get('status'), 'done', operation)
        self.assertEqual(git('-C', path, 'rev-parse', 'HEAD'), expected)
