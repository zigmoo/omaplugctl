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

    def local_edit_review(self):
        source = PHP_UPDATES.source(self.plugin, self.metadata)
        return PHP_UPDATES.review_edits(source)['token']

    def test_stash_update_keeps_index_worktree_and_untracked_edits(self):
        remote = self.advance_remote()
        widget = self.installed / 'Widget.qml'
        widget.write_text('staged edit')
        self.command('git', '-C', str(self.installed), 'add', 'Widget.qml')
        widget.write_text('unstaged edit')
        (self.installed / 'untracked.txt').write_text('private note')
        (self.installed / '.git/info/exclude').write_text('ignored.txt\n')
        (self.installed / 'ignored.txt').write_text('keep')
        result = PHP_UPDATES.apply_update(self.plugin, self.metadata, True, 'stash', self.local_edit_review())
        self.assertTrue(result['changed'])
        self.assertEqual(result['stash'], PHP_UPDATES.git(self.installed, 'rev-parse', 'refs/stash'))
        self.assertEqual(PHP_UPDATES.git(self.installed, 'show', 'refs/stash:Widget.qml'), 'unstaged edit')
        self.assertEqual(PHP_UPDATES.git(self.installed, 'show', 'refs/stash^2:Widget.qml'), 'staged edit')
        self.assertEqual(PHP_UPDATES.git(self.installed, 'show', 'refs/stash^3:untracked.txt'), 'private note')
        self.assertFalse((self.installed / 'untracked.txt').exists())
        self.assertEqual((self.installed / 'ignored.txt').read_text(), 'keep')

    def test_discard_updates_only_after_exact_review(self):
        self.advance_remote()
        widget = self.installed / 'Widget.qml'
        widget.write_text('old local edit')
        reviewed = self.local_edit_review()
        widget.write_text('new local edit')
        with self.assertRaisesRegex(RuntimeError, 'changed after review'):
            PHP_UPDATES.apply_update(self.plugin, self.metadata, True, 'discard', reviewed)
        self.assertEqual(widget.read_text(), 'new local edit')
        (self.installed / '.git/info/exclude').write_text('ignore[.]txt\n')
        (self.installed / 'ignore.txt').write_text('keep ignored')
        (self.installed / 'literal[1].txt').write_text('discard untracked')
        result = PHP_UPDATES.apply_update(self.plugin, self.metadata, True, 'discard', self.local_edit_review())
        self.assertTrue(result['changed'])
        self.assertEqual(result['stash'], '')
        self.assertFalse((self.installed / 'literal[1].txt').exists())
        self.assertEqual((self.installed / 'ignore.txt').read_text(), 'keep ignored')
        self.assertEqual(PHP_UPDATES.git(self.installed, 'stash', 'list'), '')

    def test_scan_failure_preserves_reviewed_edits(self):
        self.advance_remote()
        widget = self.installed / 'Widget.qml'
        widget.write_text('local edit')
        before = PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD')
        with patch.dict(os.environ, PHP_SCANNER_CODE='2'), self.assertRaises(RuntimeError):
            PHP_UPDATES.apply_update(self.plugin, self.metadata, True, 'discard', self.local_edit_review())
        self.assertEqual(widget.read_text(), 'local edit')
        self.assertEqual(PHP_UPDATES.git(self.installed, 'rev-parse', 'HEAD'), before)

    def test_ignored_collision_preserves_reviewed_edits(self):
        (self.writer / 'ignored.txt').write_text('upstream')
        self.commit(self.writer, 'New file')
        self.command('git', '-C', str(self.writer), 'push', 'origin', 'master')
        widget = self.installed / 'Widget.qml'
        widget.write_text('local edit')
        (self.installed / '.git/info/exclude').write_text('ignored.txt\n')
        (self.installed / 'ignored.txt').write_text('ignored local file')
        with self.assertRaisesRegex(RuntimeError, 'An ignored file conflicts'):
            PHP_UPDATES.apply_update(self.plugin, self.metadata, False, 'discard', self.local_edit_review())
        self.assertEqual(widget.read_text(), 'local edit')
        self.assertEqual((self.installed / 'ignored.txt').read_text(), 'ignored local file')

    def test_inventory_git_cache_is_scoped_to_one_snapshot(self):
        import shlex
        calls = self.base / 'git-calls.txt'
        wrapper = self.base / 'bin/git'
        wrapper.write_text('#!/bin/bash\nprintf "call\\n" >> ' + shlex.quote(str(calls)) + '\nexec /usr/bin/git "$@"\n')
        wrapper.chmod(0o755)
        script = r'''require $argv[1]; $root=$argv[2];
        $read=fn()=>OmaPlugCtl\Updates\git($root,['rev-parse','HEAD']);
        $first=OmaPlugCtl\Updates\read_snapshot(fn()=>[$read(),$read()]);
        OmaPlugCtl\Updates\git($root,['commit','--quiet','--allow-empty','-m','Changed between reads']);
        $second=OmaPlugCtl\Updates\read_snapshot($read); $fresh=$read();
        echo json_encode([$first,$second,$fresh]);'''
        result = subprocess.run(['php', '-n', '-r', script, str(ROOT / 'controller.php'), str(self.installed)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stderr, '')
        first, second, fresh = json.loads(result.stdout)
        self.assertEqual(first[0], first[1]); self.assertNotEqual(first[0], second)
        self.assertEqual(second, fresh)
        self.assertEqual(len(calls.read_text().splitlines()), 4)

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
                       {'verificationCoverage': 'update-unverified'}, {'description': '<b>Literal</b>'},
                       {'kind': 'Service + Bar widget'}, {'kind': 'Menu + Bar widget'}, {'kind': 'Overlay'}, {'kind': 'Suite'}):
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
                    'omarchy-plugin-enable', 'omarchy-plugin-disable', 'omarchy-plugin-remove', 'xdg-open', 'wl-copy', 'curl']
        import shlex
        for name in commands:
            target = self.bin / name
            target.write_text('#!/bin/bash\nexec /usr/bin/python3 ' + shlex.quote(str(ROOT / 'tests/native_fixture.py')) + ' ' + name + ' "$@"\n')
            target.chmod(0o755)
        for pid in ['moo.omaplugctl', 'moo.workspaces', 'example.radio']:
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

    def test_bar_visibility_requires_live_slots_and_checks_every_copy(self):
        state = json.loads(self.native_path.read_text())
        state['barGeometry'] = [
            {'id': 'example.radio', 'visible': False, 'itemVisible': False},
            {'id': 'moo.omaplugctl', 'visible': False, 'itemVisible': True},
            {'id': 'moo.omaplugctl', 'visible': True, 'itemVisible': True},
            {'id': 'example.unknown', 'visible': False},
        ]
        self.native_path.write_text(json.dumps(state))
        self.assertEqual(self.invoke('list')['hiddenBarWidgets'], {'example.radio': True})
        self.assertEqual(self.invoke('update-status')['hiddenBarWidgets'], {'example.radio': True})

    def test_installed_links_use_source_and_attributed_profiles(self):
        directory = self.base / '.config/omarchy/plugins/example.radio'
        manifest_path = directory / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest.update(repository={'url': 'git@gitlab.com:fixture/radio.git'},
                        homepage='https://radio.example.com',
                        author={'name': 'Fixture Author', 'github': 'fixture-author'})
        manifest_path.write_text(json.dumps(manifest))
        (directory / 'README.md').write_text(
            '# Radio\n[Project](https://x.com/radio_project)\n\n'
            '## Author\n[Post](https://x.com/wrong/status/1)\n'
            '[Author](https://twitter.com/fixture_author)\n')
        for action in ('about', 'author-github', 'author-x'):
            self.assertTrue(self.invoke(action, 'example.radio')['ok'])
        self.assertEqual(json.loads(self.native_path.read_text())['openedUrls'], [
            ['https://gitlab.com/fixture/radio'], ['https://github.com/fixture-author'],
            ['https://x.com/fixture_author']])
        for action in ('copy-about', 'copy-author-github', 'copy-author-x'):
            self.assertEqual(self.invoke(action, 'example.radio')['message'], 'Link copied.')
        state = json.loads(self.native_path.read_text())
        self.assertEqual(state['copiedUrls'], [url[0] for url in state['openedUrls']])
        self.assertEqual(len(state['openedUrls']), 3)
        self.assertFalse(self.invoke('author-x', 'example.unknown')['ok'])

    def test_author_without_attribution_does_not_open_a_profile(self):
        directory = self.base / '.config/omarchy/plugins/example.radio'
        manifest_path = directory / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['authorX'] = 'https://x.com.example.com/impersonator'
        manifest_path.write_text(json.dumps(manifest))
        (directory / 'README.md').write_text('# Radio\n[Project](https://x.com/radio_project)\n')
        result = self.invoke('author-x', 'example.radio')
        self.assertFalse(result['ok'])
        self.assertIn('No author X profile found', result['message'])
        self.assertNotIn('openedUrls', json.loads(self.native_path.read_text()))

    def test_github_profile_can_use_the_attributed_authors_noreply_commit(self):
        directory = self.base / '.config/omarchy/plugins/example.radio'
        subprocess.run(['git', 'init', '-q', directory], check=True)
        subprocess.run(['git', '-C', directory, 'add', 'manifest.json'], check=True)
        subprocess.run(['git', '-C', directory, '-c', 'user.name=Fixture Author', '-c',
                        'user.email=123+fixture-author@users.noreply.github.com',
                        'commit', '-qm', 'Add plugin'], check=True)
        self.assertTrue(self.invoke('author-github', 'example.radio')['ok'])
        self.assertEqual(json.loads(self.native_path.read_text())['openedUrls'], [['https://github.com/fixture-author']])

    def test_author_lookup_uses_linked_commit_account_and_its_public_x_profile(self):
        directory = self.base / '.config/omarchy/plugins/example.radio'
        subprocess.run(['git', 'init', '-q', directory], check=True)
        subprocess.run(['git', '-C', directory, 'remote', 'add', 'origin', 'https://github.com/other/radio'], check=True)
        subprocess.run(['git', '-C', directory, 'add', 'manifest.json'], check=True)
        subprocess.run(['git', '-C', directory, '-c', 'user.name=Fixture Author', '-c', 'user.email=fixture@example.invalid',
                        'commit', '-qm', 'Add plugin'], check=True)
        commit = subprocess.check_output(['git', '-C', directory, 'rev-parse', 'HEAD'], text=True).strip()
        state = json.loads(self.native_path.read_text())
        state['githubApi'] = {
            f'/repos/other/radio/commits/{commit}': {'sha': commit, 'author': {'login': 'fixture-author', 'type': 'User'}},
            '/users/fixture-author': {'login': 'fixture-author', 'type': 'User', 'twitter_username': 'other_handle'},
        }
        self.native_path.write_text(json.dumps(state))
        self.assertTrue(self.invoke('author-github', 'example.radio')['ok'])
        self.assertTrue(self.invoke('author-x', 'example.radio')['ok'])
        self.assertEqual(json.loads(self.native_path.read_text())['openedUrls'], [
            ['https://github.com/fixture-author'], ['https://x.com/other_handle']])
        cache = self.base / 'state/omarchy/omaplugctl/plugin_data.jsonl'
        self.assertTrue(cache.is_file())
        self.assertIn('https://x.com/other_handle', cache.read_text())
        state = json.loads(self.native_path.read_text())
        state['githubApi'] = {}
        self.native_path.write_text(json.dumps(state))
        self.assertTrue(self.invoke('author-github', 'example.radio')['ok'])
        self.assertTrue(self.invoke('author-x', 'example.radio')['ok'])
        manifest_path = directory / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['authorX'] = 'new_handle'
        manifest_path.write_text(json.dumps(manifest))
        self.assertTrue(self.invoke('author-x', 'example.radio')['ok'])
        self.assertEqual(json.loads(self.native_path.read_text())['openedUrls'][-1], ['https://x.com/new_handle'])

    def test_repository_owner_with_unrelated_name_is_not_product_author(self):
        directory = self.base / '.config/omarchy/plugins/example.radio'
        path = directory / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['repository'] = 'https://github.com/elsewhere/radio'
        path.write_text(json.dumps(manifest))
        state = json.loads(self.native_path.read_text())
        state['githubApi'] = {'/users/elsewhere': {'type': 'User', 'login': 'elsewhere', 'name': 'Unrelated Author'}}
        self.native_path.write_text(json.dumps(state))
        self.assertFalse(self.invoke('author-github', 'example.radio')['ok'])
        state = json.loads(self.native_path.read_text())
        state['githubApi']['/users/elsewhere']['name'] = 'Fixture Author'
        self.native_path.write_text(json.dumps(state))
        self.assertTrue(self.invoke('author-github', 'example.radio')['ok'])
        self.assertEqual(json.loads(self.native_path.read_text())['openedUrls'], [['https://github.com/elsewhere']])

    def test_favorite_persists_through_disable_and_uninstall(self):
        plugin_id = 'example.radio'
        path = self.base / '.config/omarchy/plugins' / plugin_id / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest.update(repository='https://github.com/fixture/radio.git', authorX='@fixture_author')
        path.write_text(json.dumps(manifest))
        self.assertTrue(self.invoke('favorite', plugin_id)['ok'])
        disabled = next(p for p in self.invoke('disable', plugin_id)['plugins'] if p['id'] == plugin_id)
        self.assertTrue(disabled['favorite'])
        self.assertFalse(disabled['enabled'])
        self.assertTrue(self.invoke('remove', plugin_id, '--confirmed')['ok'])
        inventory = self.invoke('list')
        self.assertNotIn(plugin_id, [p['id'] for p in inventory['plugins']])
        saved, = inventory['uninstalledFavorites']
        self.assertEqual(saved['id'], plugin_id)
        self.assertFalse(saved['installed'])
        self.assertTrue(saved['canReinstall'])
        self.assertEqual(saved['repository'], 'https://github.com/fixture/radio')
        self.assertTrue(self.invoke('author-x', plugin_id)['ok'])
        self.assertTrue(self.invoke('copy-author-x', plugin_id)['ok'])
        self.assertEqual(json.loads(self.native_path.read_text())['copiedUrls'], ['https://x.com/fixture_author'])
        self.assertFalse(self.invoke('enable', plugin_id)['ok'])
        self.assertEqual(self.invoke('unfavorite', plugin_id)['uninstalledFavorites'], [])

    def test_favorite_with_no_repository_is_kept_but_cannot_reinstall(self):
        plugin_id = 'example.radio'
        self.assertTrue(self.invoke('favorite', plugin_id)['ok'])
        self.assertTrue(self.invoke('remove', plugin_id, '--confirmed')['ok'])
        saved, = self.invoke('list')['uninstalledFavorites']
        self.assertFalse(saved['canReinstall'])
        self.assertIn('No installable repository', self.invoke('reinstall', plugin_id)['message'])

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

    def test_manager_can_be_paused_with_confirmation_and_reenabled(self):
        result = self.invoke('disable', 'moo.omaplugctl', '--confirmed')
        self.assertTrue(result['ok'], result)
        self.assertFalse(next(p for p in result['plugins'] if p['id'] == 'moo.omaplugctl')['enabled'])
        result = self.invoke('enable', 'moo.omaplugctl')
        self.assertTrue(result['ok'], result)
        self.assertTrue(next(p for p in result['plugins'] if p['id'] == 'moo.omaplugctl')['enabled'])

    def test_confirmed_removal_uses_native_registry(self):
        result = self.invoke('remove', 'example.radio', '--confirmed')
        self.assertTrue(result['ok']); self.assertNotIn('example.radio', [p['id'] for p in result['plugins']])

    def test_catalog_install_and_enable_are_separate(self):
        payload = {'plugins': [dict(id='example.music', name='Music', repo='https://github.com/example/music',
                                   installAvailable=True, repositoryLayout='root-plugin')]}
        entries = php('Marketplace\\normalize', payload)['result']
        php('save_json', {'schema': 1, 'entries': entries, 'fetchedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()},
            str(self.base / 'state/omarchy/omaplugctl/marketplace.json'))
        state = json.loads(self.native_path.read_text())
        state['installDiscoveryDelay'] = 3
        self.native_path.write_text(json.dumps(state))
        result = self.invoke('catalog-install', 'example.music')
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['entries'][0]['installed'])
        self.assertFalse(result['entries'][0]['enabled'])
        self.assertIn('Click Enable', result['message'])
        self.assertTrue(self.invoke('catalog-enable', 'example.music')['entries'][0]['enabled'])
        result = self.invoke('catalog-install', 'example.music')
        self.assertTrue(result['ok'])
        self.assertTrue(result['entries'][0]['enabled'])
        self.assertEqual(json.loads(self.native_path.read_text())['installAttempts'], 1)

    def add_plugin(self, pid, kinds, enabled=True, can_disable=True, active=False):
        directory = self.base / '.config/omarchy/plugins' / pid
        directory.mkdir()
        (directory / 'manifest.json').write_text(json.dumps({
            'id': pid, 'name': pid, 'author': 'Fixture', 'kinds': kinds, 'entryPoints': {}}))
        state = json.loads(self.native_path.read_text())
        state['plugins'].append(dict(id=pid, name=pid, kinds=kinds, enabled=enabled, active=active,
                                     firstParty=False, canDisable=can_disable))
        self.native_path.write_text(json.dumps(state))

    def test_inventory_includes_all_plugin_kinds_with_correct_capabilities(self):
        for kind in ('overlay', 'panel', 'menu', 'service', 'bar'):
            self.add_plugin('example.' + kind, [kind])
        rows = {p['id']: p for p in self.invoke('list')['plugins']}
        for kind in ('overlay', 'panel', 'menu', 'service', 'bar'):
            row = rows['example.' + kind]
            self.assertFalse(row['isBarWidget'])
            self.assertEqual(row['canOpen'], kind in ('overlay', 'panel', 'menu'))
            self.assertEqual(row['instances'], [])
        self.assertTrue(rows['example.radio']['isBarWidget'])
        self.assertFalse(rows['example.radio']['canOpen'])

    def test_catalog_identifies_panel_rows_using_installed_kinds(self):
        self.add_plugin('example.panel', ['panel'])
        self.add_plugin('example.combo', ['panel', 'bar-widget'])
        payload = {'plugins': [dict(id=pid, name=pid, kind='Service')
                                for pid in ['example.panel', 'example.combo']]}
        entries = php('Marketplace\\normalize', payload)['result']
        php('save_json', {'schema': 1, 'entries': entries, 'fetchedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()},
            str(self.base / 'state/omarchy/omaplugctl/marketplace.json'))
        rows = {p['id']: p for p in self.invoke('catalog')['entries']}
        self.assertTrue(rows['example.panel']['opensWithoutBar'])
        self.assertFalse(rows['example.combo']['opensWithoutBar'])

    def test_disabled_plugin_inventory_includes_author_and_search_keywords(self):
        self.add_plugin('example.lookup', ['service'], enabled=False)
        path = self.base / '.config/omarchy/plugins/example.lookup/manifest.json'
        manifest = json.loads(path.read_text())
        manifest.pop('author')
        manifest.update(authors=[{'name': 'Jane Doe'}, 'Riley'],
                        keywords=['  desktop  alerts  ', 123, ''], tags=['desktop alerts', 'focus'])
        path.write_text(json.dumps(manifest))
        plugin = next(row for row in self.invoke('list')['plugins'] if row['id'] == 'example.lookup')
        self.assertFalse(plugin['enabled'])
        self.assertEqual(plugin['author'], 'Jane Doe, Riley')
        self.assertEqual(plugin['keywords'], ['desktop alerts', 'focus'])

    def test_overlay_enable_open_disable_and_remove(self):
        self.add_plugin('example.overlay', ['overlay'], enabled=False)
        self.assertFalse(self.invoke('open', 'example.overlay')['ok'])
        self.assertTrue(self.invoke('enable', 'example.overlay')['ok'])
        self.assertTrue(self.invoke('open', 'example.overlay')['ok'])
        self.assertEqual(json.loads(self.native_path.read_text())['summons'], [['example.overlay', '{}']])
        self.assertTrue(self.invoke('disable', 'example.overlay')['ok'])
        self.assertTrue(self.invoke('remove', 'example.overlay', '--confirmed')['ok'])

    def test_service_open_bar_moves_and_protected_disables_are_rejected(self):
        self.add_plugin('example.service', ['service'])
        self.add_plugin('example.overlay', ['overlay'])
        self.add_plugin('example.protected', ['bar'], can_disable=False)
        self.assertFalse(self.invoke('open', 'example.service')['ok'])
        self.assertFalse(self.invoke('disable', 'example.protected')['ok'])
        self.assertFalse(self.invoke('move', 'example.overlay', '--section', 'left', '--source', 'right', '--index', '0')['ok'])
        self.assertNotIn('summons', json.loads(self.native_path.read_text()))

    def test_open_requires_shell_acknowledgement(self):
        self.add_plugin('example.overlay', ['overlay'])
        state = json.loads(self.native_path.read_text()); state['summonError'] = True
        self.native_path.write_text(json.dumps(state))
        self.assertFalse(self.invoke('open', 'example.overlay')['ok'])

    def test_switches_registered_bars_without_editing_the_widget_layout(self):
        self.add_plugin('omarchy.bar', ['bar'], can_disable=False, active=True)
        self.add_plugin('example.mixed', ['bar', 'bar-widget', 'service'], enabled=False, can_disable=False)
        self.add_plugin('example.alternate', ['bar'], enabled=False, can_disable=False)
        before = json.loads(self.config_path.read_text())['bar']['layout']
        state = json.loads(self.native_path.read_text()); state['barReadbackDelay'] = 2
        self.native_path.write_text(json.dumps(state))
        for action, pid, target in (('use-bar', 'example.mixed', 'example.mixed'),
                                    ('use-bar', 'example.alternate', 'example.alternate'),
                                    ('reset-bar', 'example.alternate', 'omarchy.bar')):
            with self.subTest(action=action, pid=pid):
                result = self.invoke(action, pid)
                self.assertTrue(result['ok'], result)
                self.assertEqual([p['id'] for p in result['plugins'] if p.get('active')], [target])
                self.assertEqual(json.loads(self.config_path.read_text())['bar']['layout'], before)
        result = self.invoke('use-bar', 'omarchy.bar')
        self.assertTrue(next(p for p in result['plugins'] if p['id'] == 'omarchy.bar')['isDefaultBar'])
        self.assertEqual(json.loads(self.native_path.read_text())['barCommands'],
                         [['bar', 'use', 'example.mixed'], ['bar', 'use', 'example.alternate'], ['bar', 'reset']])

    def test_bar_switch_rejects_stale_selection_and_requires_active_readback(self):
        self.add_plugin('omarchy.bar', ['bar'], can_disable=False, active=True)
        self.add_plugin('example.inactive', ['bar'], enabled=False, can_disable=False)
        for action, pid in (('reset-bar', 'example.inactive'), ('reset-bar', 'omarchy.bar'),
                            ('use-bar', 'example.radio'), ('use-bar', 'unknown.bar')):
            self.assertFalse(self.invoke(action, pid)['ok'])
        state = json.loads(self.native_path.read_text())
        self.assertNotIn('barCommands', state)
        state['ignoreWrites'] = True
        self.native_path.write_text(json.dumps(state))
        result = self.invoke('use-bar', 'example.inactive')
        self.assertFalse(result['ok'])
        self.assertIn('did not become active', result['message'])

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
