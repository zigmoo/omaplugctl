import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controller
import updates
import reviews


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.env = patch.dict(os.environ, {'XDG_STATE_HOME': str(self.base / 'state')})
        self.env.start()
        self.addCleanup(self.env.stop)
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

    def test_review_snapshot_pins_both_commits_without_installing(self):
        self.advance_remote()
        source = updates.source(self.plugin, self.metadata)
        body, remote = reviews.snapshot(self.plugin, source, self.metadata)
        self.assertIn(source['head'], body)
        self.assertIn(remote, body)
        self.assertIn('+new remote version', body)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), source['head'])
        self.assertEqual((self.installed / 'Widget.qml').read_text(), 'initial')

    def test_large_snapshot_is_partitioned_without_dropping_source(self):
        self.advance_remote()
        source = updates.source(self.plugin, self.metadata)
        body, remote = reviews.snapshot(self.plugin, source, self.metadata)
        parts = reviews.partition(body, budget=40)
        self.assertGreater(len(parts), 1)
        self.assertEqual(''.join(p['text'] for p in parts), body)
        self.assertEqual(updates.git(self.installed, 'rev-parse', 'HEAD'), source['head'])

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

    def test_launch_runs_detached_without_terminal_or_auto_confirmation(self):
        with patch.object(controller, 'update_target', return_value=(self.plugin, {})), patch.object(controller.reviews, 'reviewer', return_value={'label': 'Registered reviewer'}), patch.object(controller, 'inventory', return_value=[self.plugin]), patch.object(controller.subprocess, 'Popen') as launch:
            controller.launch_update('example.widget')
            argv = launch.call_args.args[0]
            self.assertNotIn('omarchy-launch-tui', argv)
            self.assertEqual(argv[1], '-u')
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(launch.call_args.kwargs['stdin'], subprocess.DEVNULL)
            self.assertEqual(argv[-2:], ['review-update', 'example.widget'])
            self.assertNotIn('--yes', argv)

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
