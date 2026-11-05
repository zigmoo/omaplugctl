"""Exercise URL discovery, complete-commit scanning and pinned installation."""
import datetime
import json
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from test_php import php

ROOT = pathlib.Path(__file__).resolve().parent
REPO = 'https://github.com/example/plugin'


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = pathlib.Path(self.temp.name)
        self.upstream = self.base / 'upstream'; self.upstream.mkdir()
        self.git('init', '--initial-branch=master', self.upstream)
        self.git('-C', self.upstream, 'config', 'user.name', 'Fixture')
        self.git('-C', self.upstream, 'config', 'user.email', 'fixture@example.invalid')
        (self.upstream / 'manifest.json').write_text(json.dumps({
            'schemaVersion': 1, 'id': 'example.plugin', 'name': '<b>Plugin</b>', 'version': '1',
            'kinds': ['service'], 'entryPoints': {'service': 'Service.qml'}}))
        (self.upstream / 'Service.qml').write_text('import QtQuick\nItem {}\n')
        self.commit()
        self.bin = self.base / 'bin'; self.bin.mkdir()
        for name in ('git', 'curl', 'clamscan', 'omarchy-plugin-list', 'omarchy-shell', 'omarchy'):
            target = self.bin / name
            target.write_text('#!/bin/bash\nexec /usr/bin/python3 ' +
                              shlex.quote(str(ROOT / 'tests/source_fixture.py')) + ' ' + name + ' "$@"\n')
            target.chmod(0o755)
        self.state = self.base / 'state/omarchy/omaplugctl'
        database = self.state / 'clamav'; database.mkdir(parents=True)
        (database / 'daily.cvd').write_text('fixture')
        (database / 'last-check.json').write_text(json.dumps({'checkedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}))
        switch = patch.dict(os.environ, HOME=str(self.base), SOURCE_FIXTURE=str(self.base),
                            XDG_STATE_HOME=str(self.base / 'state'), XDG_DATA_HOME=str(self.base / 'data'),
                            PATH=str(self.bin) + ':' + os.environ['PATH'])
        switch.start(); self.addCleanup(switch.stop)

    def git(self, *args):
        return subprocess.check_output(['/usr/bin/git', *map(str, args)], text=True, stderr=subprocess.DEVNULL).strip()

    def commit(self):
        self.git('-C', self.upstream, 'add', '.')
        self.git('-C', self.upstream, 'commit', '-m', 'Fixture')

    def invoke(self, function, *args):
        return php('Sources\\' + function, *args)['result']

    def check(self):
        return self.invoke('check', REPO)['sourceEntries'][0]

    def test_url_allowlist_and_repository_normalization(self):
        for suffix in ('', '.git', '/', '/tree/master', '/blob/master/README.md', '?tab=readme'):
            self.assertEqual(self.invoke('repository', REPO + suffix), REPO)
        for url in ('http://github.com/a/b', 'https://github.com.evil.test/a/b',
                    'https://github.com/a/../b', 'https://user@github.com/a/b', 'file:///x',
                    'https://github.com/a/b;touch-bad', 'https://github.com:443/a/b'):
            self.assertIsNone(self.invoke('repository', url))
        for url in ('https://x.com/name/status/123?s=20', 'https://twitter.com/name/status/123',
                    'https://x.com/i/web/status/123'):
            self.assertEqual(self.invoke('post_id', url), '123')

    def test_x_expanded_links_evaluate_without_installing(self):
        result = self.invoke('check', 'https://x.com/name/status/123')['sourceEntries'][0]
        self.assertTrue(result['installable'])
        self.assertFalse((self.base / '.config/omarchy/plugins').exists())

    def test_text_links_ignore_profile_and_media_links(self):
        self.assertEqual(self.invoke('post_links', {'text': 'Try https://github.com/example/plugin.',
                         'user': {'url': 'https://github.com/other/repo'}}), [REPO])

    def test_scan_and_install_exact_commit_then_enable_with_readback(self):
        row = self.check(); self.assertTrue(row['installable'], row)
        self.assertFalse(row['verified'])
        pinned = row['verifiedCommit']
        (self.upstream / 'later').write_text('new remote commit'); self.commit()
        result = self.invoke('install', row['evaluation'])['sourceEntries'][0]
        target = self.base / '.config/omarchy/plugins/example.plugin'
        self.assertEqual(self.git('-C', target, 'rev-parse', 'HEAD'), pinned)
        self.assertEqual(self.git('-C', target, 'remote', 'get-url', 'origin'), str(self.upstream))
        self.assertTrue(result['installed']); self.assertFalse(result['enabled'])
        self.assertTrue(self.invoke('enable', row['evaluation'])['sourceEntries'][0]['enabled'])

    def test_symlinks_block_installation(self):
        (self.upstream / 'link').symlink_to('/etc/passwd'); self.commit()
        row = self.check(); self.assertFalse(row['installable']); self.assertIn('symlinks', row['description'])

    def test_invalid_manifest_blocks_installation(self):
        (self.upstream / 'manifest.json').write_text('{}'); self.commit()
        self.assertFalse(self.check()['installable'])

    def test_missing_entrypoint_blocks_installation(self):
        (self.upstream / 'Service.qml').unlink(); self.commit()
        self.assertFalse(self.check()['installable'])

    def test_export_ignored_malware_is_scanned(self):
        (self.upstream / '.gitattributes').write_text('hidden export-ignore\n')
        (self.upstream / 'hidden').write_text('EICAR-SOURCE-FIXTURE'); self.commit()
        row = self.check(); self.assertFalse(row['installable']); self.assertIn('detected', row['description'])

    def test_scanner_failure_blocks_installation(self):
        with patch.dict(os.environ, SOURCE_SCANNER_CODE='2'):
            row = self.check()
        self.assertFalse(row['installable']); self.assertIn('could not complete', row['description'])

    def test_changes_and_ignored_files_invalidate_evaluation(self):
        for name in ('Service.qml', 'untracked.txt'):
            row = self.check()
            (self.state / 'sources' / row['evaluation'] / 'tree' / name).write_text('changed')
            with self.assertRaisesRegex(RuntimeError, 'files changed'):
                self.invoke('install', row['evaluation'])

    def test_existing_destination_is_preserved(self):
        row = self.check(); target = self.base / '.config/omarchy/plugins/example.plugin'
        target.mkdir(parents=True); (target / 'mine').write_text('preserve')
        with self.assertRaisesRegex(RuntimeError, 'already exists'):
            self.invoke('install', row['evaluation'])
        self.assertEqual((target / 'mine').read_text(), 'preserve')

    def test_expired_or_forged_evaluations_are_rejected(self):
        row = self.check(); path = self.state / 'sources' / row['evaluation'] / 'evaluation.json'
        value = json.loads(path.read_text()); value['checkedAt'] = 0; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(RuntimeError, 'expired'):
            self.invoke('install', row['evaluation'])
        with self.assertRaises(ValueError): self.invoke('install', '../../bad')

    def test_failed_enable_readback_reports_error(self):
        row = self.check(); self.invoke('install', row['evaluation'])
        with patch.dict(os.environ, SOURCE_IGNORE_ENABLE='1'), self.assertRaisesRegex(RuntimeError, 'not confirmed'):
            self.invoke('enable', row['evaluation'])

    def test_lazy_commit_metadata_and_cache(self):
        result = self.invoke('details', REPO)['details']
        self.assertEqual(result['lastCommitAt'], '2026-11-05T12:00:00Z')
        self.assertEqual(result['commitAuthor'], '<b>Author</b>')
        (self.bin / 'curl').unlink()
        self.assertEqual(self.invoke('details', REPO)['details'], result)
        with self.assertRaises(ValueError): self.invoke('details', 'https://evil.test/repo')

    def discover_posts(self, posts):
        script = r'''require $argv[1]; $request=json_decode(stream_get_contents(STDIN),true);
        try { echo json_encode(OmaPlugCtl\Sources\discover('https://x.com/name/status/123',
            function($id)use($request){if(!isset($request[$id]))throw new RuntimeException('Unavailable post');return $request[$id];})); }
        catch(Throwable $error){echo json_encode(['error'=>$error->getMessage()]);}'''
        result = subprocess.run(['php', '-n', '-r', script, str(ROOT / 'controller.php')],
                                input=json.dumps(posts), text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_thread_links_parents_quotes_and_deduplication(self):
        posts = {'123': {'text': 'Continue https://x.com/name/status/456',
                         'in_reply_to_status_id_str': '456',
                         'quoted_tweet': {'text': 'https://github.com/example/plugin.git'}},
                 '456': {'text': REPO, 'in_reply_to_status_id_str': '123'}}
        self.assertEqual(self.discover_posts(posts), [REPO])

    def test_no_link_and_unavailable_posts_have_actionable_errors(self):
        self.assertIn('No GitHub', self.discover_posts({'123': {'text': 'Hello'}})['error'])
        self.assertIn('Unavailable', self.discover_posts({})['error'])

    def test_thread_repository_limit_is_explicit(self):
        posts = {'123': {'text': ' '.join('https://github.com/example/repo' + str(i) for i in range(6))}}
        self.assertIn('too many', self.discover_posts(posts)['error'])
