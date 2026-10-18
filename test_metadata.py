import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controller


class AuthorHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name) / 'source'
        self.git('init', '--initial-branch=master', str(self.root), outside=True)
        self.git('config', 'user.name', 'Later Maintainer')
        self.git('config', 'user.email', 'maintainer@example.invalid')
        (self.root / 'Old.qml').write_text('Item {}\n')
        self.commit('Original plugin', 'Original Author', '2025-01-01T00:00:00Z')
        self.original = self.git('rev-parse', 'HEAD')
        self.git('mv', 'Old.qml', 'Widget.qml')
        self.commit('Rename widget', 'Later Maintainer', '2025-02-01T00:00:00Z')
        (self.root / 'manifest.json').write_text(json.dumps({'author': 'Omarchy'}))
        self.commit('Add manifest', 'Later Maintainer', '2025-03-01T00:00:00Z')
        self.metadata = {'sourceDir': str(self.root), 'manifestPath': str(self.root / 'manifest.json'),
                         'entryPoints': {'barWidget': 'Widget.qml'}, 'firstParty': True}

    def git(self, *args, outside=False, env=None):
        argv = ['git'] + ([] if outside else ['-C', str(self.root)]) + list(args)
        return subprocess.check_output(argv, text=True, stderr=subprocess.DEVNULL, env=env).strip()

    def commit(self, message, author, date):
        self.git('add', '.')
        self.git('commit', '-m', message, env=dict(os.environ, GIT_AUTHOR_NAME=author,
                 GIT_AUTHOR_EMAIL='author@example.invalid', GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date))

    def test_default_plugin_author_follows_renames_to_first_file_commit(self):
        value = controller.plugin_details(self.metadata, {})
        self.assertEqual(value['author'], 'Original Author')
        self.assertEqual(value['authorCommit'], self.original)
        self.assertEqual(value['authorSource'], 'first-commit')
        self.assertFalse(value['authorHistoryShallow'])

    def test_explicit_person_attribution_is_preserved(self):
        (self.root / 'manifest.json').write_text('{"author":"Explicit Author"}')
        value = controller.plugin_details(self.metadata, {})
        self.assertEqual(value['author'], 'Explicit Author')
        self.assertNotIn('authorSource', value)

    def test_history_cache_avoids_repeating_log_walk(self):
        cache = {}
        first = controller.first_commit_author(self.metadata, cache)
        with patch.object(controller.updates, 'git', wraps=controller.updates.git) as git:
            self.assertEqual(controller.first_commit_author(self.metadata, cache), first)
        self.assertFalse(any('log' in call.args for call in git.call_args_list))

    def test_shallow_history_is_explicitly_identified(self):
        clone = pathlib.Path(self.temp.name) / 'shallow'
        self.git('clone', '--depth=1', self.root.as_uri(), str(clone), outside=True)
        metadata = {**self.metadata, 'sourceDir': str(clone), 'manifestPath': str(clone / 'manifest.json')}
        value = controller.first_commit_author(metadata, {})
        self.assertTrue(value['authorHistoryShallow'])
        self.assertEqual(value['author'], 'Later Maintainer')


if __name__ == '__main__':
    unittest.main()
