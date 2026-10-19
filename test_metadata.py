import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controller


class ReadmeDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.readme = self.root / 'README.md'
        self.metadata = {'sourceDir': str(self.root),
                         'manifestPath': str(self.root / 'manifest.json'),
                         'description': 'Manifest fallback.'}

    def test_explicit_section_overrides_manifest_and_stops_at_next_paragraph(self):
        self.readme.write_text('# Plugin\n\n## Description for Agents\n\n'
                               'Adjust the camera.\nPreview changes live.\n\n'
                               'Developer instructions do not belong in the tooltip.\n')
        self.assertEqual(controller.plugin_description(self.metadata),
                         'Adjust the camera. Preview changes live.')

    def test_heading_is_case_insensitive_and_next_heading_ends_description(self):
        self.readme.write_text('## description FOR agents ###\nShows the weather.\n## Install\nRun setup.\n')
        self.assertEqual(controller.plugin_description(self.metadata), 'Shows the weather.')

    def test_examples_inside_backtick_and_tilde_fences_are_ignored(self):
        for fence in ('```', '~~~~'):
            with self.subTest(fence=fence):
                self.readme.write_text(f'{fence}markdown\n## Description for Agents\n'
                                       f'Example only.\n{fence}\n\n'
                                       '## Description for Agents\nActual description.\n')
                self.assertEqual(controller.plugin_description(self.metadata), 'Actual description.')

    def test_missing_empty_duplicate_and_nonparagraph_sections_fall_back(self):
        for text in ('# Plugin\nA general introduction.',
                     '## Description for Agents\n\n## Install\nOther content.',
                     '## Description for Agents\nOne.\n## Description for Agents\nTwo.',
                     '## Description for Agents\n- A list item.',
                     '## Description for Agents\n```\nAn example.\n```',
                     '## Description for Agents\n    An indented example.'):
            with self.subTest(text=text):
                self.readme.write_text(text)
                self.assertEqual(controller.plugin_description(self.metadata), 'Manifest fallback.')

    def test_invalid_encoding_and_oversized_readmes_fall_back(self):
        for data in (b'## Description for Agents\n\xff',
                     b'## Description for Agents\n' + b'x' * (256 * 1024)):
            with self.subTest(size=len(data)):
                self.readme.write_bytes(data)
                self.assertEqual(controller.plugin_description(self.metadata), 'Manifest fallback.')

    def test_description_is_bounded_and_markup_stays_literal(self):
        markup = '<img src="https://example.invalid/tracker">'
        self.readme.write_text('## Description for Agents\n' + markup)
        self.assertEqual(controller.plugin_description(self.metadata), markup)
        self.readme.write_text('## Description for Agents\n' + 'x' * 2000)
        value = controller.plugin_description(self.metadata)
        self.assertEqual(len(value), 1200)
        self.assertTrue(value.endswith('…'))

    def test_symlinked_checkout_works_but_readme_symlinks_are_not_followed(self):
        self.readme.write_text('## Description for Agents\nControls the light.')
        link = self.root / 'installed'
        link.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(controller.plugin_description({**self.metadata, 'sourceDir': str(link)}),
                         'Controls the light.')
        other = self.root / 'outside.md'
        self.readme.rename(other)
        self.readme.symlink_to(other)
        self.assertEqual(controller.plugin_description(self.metadata), 'Manifest fallback.')

    def test_nonregular_files_do_not_block(self):
        os.mkfifo(self.readme)
        self.assertEqual(controller.plugin_description(self.metadata), 'Manifest fallback.')

    def test_shared_builtin_directory_does_not_supply_another_plugins_description(self):
        self.readme.write_text('## Description for Agents\nShared directory description.')
        metadata = {**self.metadata, 'manifestPath': str(self.root / 'audio.json')}
        self.assertEqual(controller.plugin_description(metadata), 'Manifest fallback.')

    def test_inventory_reads_readme_description_without_network(self):
        home = self.root / 'home'
        config = home / '.config/omarchy/shell.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"bar":{"layout":{}}}')
        self.readme.write_text('## Description for Agents\nControls the light.')
        plugin = {'id': 'test.light', 'name': 'Light', 'kinds': ['bar-widget'], 'firstParty': False}
        metadata = {**self.metadata, 'id': plugin['id']}
        with patch.object(controller.pathlib.Path, 'home', return_value=home), \
             patch.object(controller, 'run', side_effect=[json.dumps([plugin]), json.dumps([metadata])]), \
             patch.object(controller.urllib.request, 'urlopen') as network:
            self.assertEqual(controller.inventory()[0]['description'], 'Controls the light.')
        network.assert_not_called()


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
