import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controller
import updates
import malware


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.env = patch.dict(os.environ, {'XDG_STATE_HOME': str(self.base / 'state')})
        self.env.start()
        self.addCleanup(self.env.stop)
        scanner = patch.object(malware, 'scan_commit', return_value={'status': 'no-threats-detected'})
        scanner.start()
        self.addCleanup(scanner.stop)
        self.remote = self.base / 'remote.git'
        self.writer = self.base / 'writer'
        self.installed = self.base / 'installed'
        self.command('git', 'init', '--bare', '--initial-branch=master', str(self.remote))
        self.command('git', 'init', '--initial-branch=master', str(self.writer))
        self.configure(self.writer)
        (self.writer / 'manifest.json').write_text('{"id":"example.widget"}')
        (self.writer / 'Widget.qml').write_text('initial')
        self.commit(self.writer, 'Initial plugin')
        self.command('git', '-C', str(self.writer), 'remote', 'add', 'origin', str(self.remote))
        self.command('git', '-C', str(self.writer), 'push', '-u', 'origin', 'master')
        self.command('git', 'clone', str(self.remote), str(self.installed))
        self.configure(self.installed)
        self.plugin = {'id': 'example.widget', 'firstParty': False, 'clonedFrom': ''}
        self.metadata = {'sourceDir': str(self.installed), 'manifestPath': str(self.installed / 'manifest.json')}

    def command(self, *argv):
        return subprocess.check_output(argv, stderr=subprocess.DEVNULL, text=True).strip()

    def configure(self, directory):
        self.command('git', '-C', str(directory), 'config', 'user.name', 'Test Author')
        self.command('git', '-C', str(directory), 'config', 'user.email', 'test@example.invalid')

    def commit(self, directory, message):
        self.command('git', '-C', str(directory), 'add', '.')
        self.command('git', '-C', str(directory), 'commit', '-m', message)

    def advance_remote(self, path='Widget.qml'):
        file = self.writer / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('new remote version')
        self.commit(self.writer, 'Update source')
        self.command('git', '-C', str(self.writer), 'push')

    def check(self):
        return updates.check_all([self.plugin], {self.plugin['id']: self.metadata})[self.plugin['id']]

    def test_remote_update_is_detected_without_installing_it(self):
        old_head = updates.git(self.installed, 'rev-parse', 'HEAD')
        self.advance_remote()
        result = self.check()
        self.assertEqual(result['status'], 'available')
        self.assertTrue(result['canUpdate'])
        self.assertTrue(result['latestDate'])
        self.assertEqual(result['notes'], ['Update source'])
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), old_head)
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'initial')

    def test_current_repository_and_cache(self):
        self.assertEqual(self.check()['status'], 'current')
        with patch.object(updates, 'fetch_source') as fetch:
            result = updates.cached_status(self.plugin, self.metadata, updates.load_cache())
            self.assertEqual(result['status'], 'current')
            fetch.assert_not_called()

    def test_dirty_repository_cannot_update(self):
        self.advance_remote()
        (self.installed / 'Widget.qml').write_text('personal edits')
        result = self.check()
        self.assertEqual(result['status'], 'available')
        self.assertFalse(result['canUpdate'])
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'personal edits')

    def test_diverged_history_cannot_update(self):
        self.advance_remote()
        (self.installed / 'local.txt').write_text('personal commit')
        self.commit(self.installed, 'Local commit')
        result = self.check()
        self.assertEqual(result['status'], 'diverged')
        self.assertFalse(result['canUpdate'])

    def test_changed_local_head_invalidates_cached_result(self):
        self.check()
        (self.installed / 'local.txt').write_text('personal commit')
        self.commit(self.installed, 'Local commit')
        result = updates.cached_status(self.plugin, self.metadata, updates.load_cache())
        self.assertEqual(result['status'], 'unchecked')

    def test_old_up_to_date_result_requires_a_new_check(self):
        self.check()
        cache = updates.load_cache()
        cache[self.plugin['id']]['checkedAt'] = '2020-01-01T00:00:00+00:00'
        self.assertEqual(updates.cached_status(self.plugin, self.metadata, cache)['status'], 'unchecked')

    def test_failed_fetch_does_not_claim_up_to_date(self):
        with patch.object(updates, 'fetch_source', side_effect=RuntimeError('offline')):
            result = self.check()
        self.assertEqual(result['status'], 'error')
        self.assertFalse(result['canUpdate'])

    def test_builtin_checks_are_scoped_to_the_plugin(self):
        self.plugin['firstParty'] = True
        self.metadata = {'sourceDir': str(self.installed / 'audio'), 'manifestPath': str(self.installed / 'audio/manifest.json')}
        directory = self.installed / 'audio'; directory.mkdir()
        (directory / 'manifest.json').write_text('{}')
        self.commit(self.installed, 'Add audio')
        self.command('git', '-C', str(self.installed), 'push')
        self.command('git', '-C', str(self.writer), 'pull', '--ff-only')
        self.advance_remote('unrelated.txt')
        self.assertEqual(self.check()['status'], 'current')
        (self.writer / 'audio/Widget.qml').write_text('new audio widget')
        self.commit(self.writer, 'Update audio')
        self.command('git', '-C', str(self.writer), 'push')
        self.assertEqual(self.check()['status'], 'available')

    def test_missing_source_repository_is_explicit(self):
        directory = self.base / 'local'; directory.mkdir()
        self.assertEqual(updates.cached_status(self.plugin, {'sourceDir': str(directory)}, {}), {'status': 'local', 'canUpdate': False})

    def test_click_fast_forwards_running_symlinked_checkout(self):
        link = self.base / 'active-plugin'; link.symlink_to(self.installed)
        self.metadata['sourceDir'] = str(link)
        self.advance_remote()
        result = updates.apply_update(self.plugin, self.metadata)
        self.assertTrue(result['changed'])
        self.assertEqual((link / 'Widget.qml').read_text(), 'new remote version')
        self.assertEqual(result['head'], updates.git(self.writer, 'rev-parse', 'HEAD'))
        self.assertEqual(self.check()['status'], 'current')
        self.assertEqual(updates.git(self.installed, 'status', '--porcelain'), '')

    def test_apply_preserves_dirty_and_diverged_checkouts(self):
        self.advance_remote()
        (self.installed / 'Widget.qml').write_text('personal edits')
        head = updates.git(self.installed, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(RuntimeError, 'Local changes'):
            updates.apply_update(self.plugin, self.metadata)
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'personal edits')
        self.commit(self.installed, 'Local edits')
        head = updates.git(self.installed, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(RuntimeError, 'diverged'):
            updates.apply_update(self.plugin, self.metadata)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), head)

    def test_update_follows_checked_out_tracking_branch_instead_of_remote_head(self):
        self.command('git', '-C', str(self.writer), 'switch', '-c', 'testing')
        (self.writer / 'Widget.qml').write_text('testing branch')
        self.commit(self.writer, 'Testing version')
        self.command('git', '-C', str(self.writer), 'push', '-u', 'origin', 'testing')
        self.command('git', '-C', str(self.installed), 'fetch', 'origin')
        self.command('git', '-C', str(self.installed), 'switch', '--track', 'origin/testing')
        self.advance_remote()
        result = updates.apply_update(self.plugin, self.metadata)
        self.assertTrue(result['changed'])
        self.assertEqual(updates.git(self.installed, 'branch', '--show-current'), 'testing')
        self.assertEqual(result['head'], updates.git(self.writer, 'rev-parse', 'HEAD'))

    def test_detached_checkout_is_preserved(self):
        self.command('git', '-C', str(self.installed), 'checkout', '--detach')
        self.advance_remote()
        with self.assertRaisesRegex(RuntimeError, 'tracking origin'):
            updates.apply_update(self.plugin, self.metadata)
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'initial')

    def test_shared_omarchy_repo_is_never_updated_by_plugin_click(self):
        self.plugin['firstParty'] = True
        self.advance_remote()
        with self.assertRaisesRegex(RuntimeError, 'updated with Omarchy'):
            updates.apply_update(self.plugin, self.metadata)
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'initial')

    def test_git_update_does_not_run_a_post_merge_hook(self):
        hook = self.installed / '.git/hooks/post-merge'
        sentinel = self.base / 'hook-ran'
        hook.write_text('#!/bin/sh\ntouch "' + str(sentinel) + '"\n')
        hook.chmod(0o755)
        self.advance_remote()
        updates.apply_update(self.plugin, self.metadata)
        self.assertFalse(sentinel.exists())

    def rewritten_remote(self, replacement=None):
        self.advance_remote()
        self.command('git', '-C', str(self.installed), 'pull', '--ff-only')
        old = updates.git(self.installed, 'rev-parse', 'HEAD')
        if replacement is not None:
            (self.writer / 'Widget.qml').write_text(replacement)
            self.command('git', '-C', str(self.writer), 'add', '.')
        self.command('git', '-C', str(self.writer), 'commit', '--amend', '-m', 'Reissued upstream commit')
        (self.writer / 'new.txt').write_text('new release')
        self.commit(self.writer, 'New upstream release')
        self.command('git', '-C', str(self.writer), 'push', '--force', 'origin', 'master')
        return old

    def test_rewritten_history_updates_with_verified_backup(self):
        old = self.rewritten_remote()
        result = self.check()
        self.assertEqual(result['status'], 'rewritten')
        self.assertTrue(result['canUpdate'])
        result = updates.apply_update(self.plugin, self.metadata)
        self.assertEqual(updates.git(self.installed, 'rev-parse', result['backup']), old)
        self.assertEqual(result['head'], updates.git(self.writer, 'rev-parse', 'HEAD'))
        self.assertEqual(updates.git(self.installed, 'branch', '--show-current'), 'master')
        self.assertEqual(updates.git(self.installed, 'config', 'branch.master.merge'), 'refs/heads/master')
        self.assertEqual((self.installed / 'new.txt').read_text(), 'new release')
        self.assertEqual(self.check()['status'], 'current')

    def test_threat_blocks_update_before_any_checkout_change(self):
        self.advance_remote()
        before = updates.git(self.installed, 'rev-parse', 'HEAD')
        with patch.object(malware, 'scan_commit', side_effect=RuntimeError('ClamAV detected a threat')):
            with self.assertRaisesRegex(RuntimeError, 'detected a threat'):
                updates.apply_update(self.plugin, self.metadata)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), before)
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'initial')

    def test_whitespace_changes_are_not_treated_as_equivalent(self):
        old = self.rewritten_remote(' new remote version')
        # Git cherry ignores whitespace, but our comparison must preserve it.
        self.check()
        self.assertTrue(updates.git(self.installed, 'cherry', 'origin/master', 'HEAD').startswith('-'))
        with self.assertRaisesRegex(RuntimeError, 'not all reproduced'):
            updates.apply_update(self.plugin, self.metadata)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), old)
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'new remote version')

    def test_empty_commit_is_not_silently_discarded(self):
        self.rewritten_remote()
        self.command('git', '-C', str(self.installed), 'commit', '--allow-empty', '-m', 'Local metadata marker')
        old = updates.git(self.installed, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(RuntimeError, 'not all reproduced'):
            updates.apply_update(self.plugin, self.metadata)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), old)

    def test_ignored_local_file_is_preserved_during_reconciliation(self):
        old = self.rewritten_remote()
        (self.installed / '.git/info/exclude').write_text('new.txt\n')
        (self.installed / 'new.txt').write_text('personal ignored data')
        with self.assertRaisesRegex(RuntimeError, 'previous version is preserved'):
            updates.apply_update(self.plugin, self.metadata)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), old)
        self.assertEqual((self.installed / 'new.txt').read_text(), 'personal ignored data')

    def test_edit_during_history_verification_is_preserved(self):
        old = self.rewritten_remote()
        def verify(*args):
            (self.installed / 'Widget.qml').write_text('concurrent personal edit')
            return True
        with patch.object(updates, 'equivalent_history', side_effect=verify):
            with self.assertRaisesRegex(RuntimeError, 'plugin changed'):
                updates.apply_update(self.plugin, self.metadata)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), old)
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'concurrent personal edit')

    def test_launch_detaches_update_without_terminal_agent_or_prompt(self):
        with patch.object(controller, 'update_target', return_value=(self.plugin, {'kind':'plugin','tracking':True})), \
             patch.object(controller, 'inventory', return_value=[]), patch.object(controller.subprocess, 'Popen') as launch:
            controller.launch_update('example.widget')
            controller.launch_update('example.widget')
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(launch.call_args.args[0][-2:], ['finish-update', 'example.widget'])
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(launch.call_args.kwargs['stdin'], subprocess.DEVNULL)

    def test_controller_cannot_disable_or_remove_itself(self):
        plugin = {'id': controller.SELF, 'isSelf': True}
        for action in ('disable', 'remove'):
            with self.subTest(action=action), patch.object(controller, 'inventory', return_value=[plugin]), patch.object(controller, 'run') as run:
                with self.assertRaises(ValueError):
                    controller.execute(action, controller.SELF, confirmed=True)
                run.assert_not_called()

    def test_update_target_rejects_invalid_ids_before_any_command(self):
        with patch.object(controller, 'inventory') as inventory:
            with self.assertRaises(ValueError): controller.update_target('x; touch nope')
            inventory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
