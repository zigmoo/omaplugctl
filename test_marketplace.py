import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import marketplace as m


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = pathlib.Path(self.temporary.name) / 'marketplace.json'
        self.cache_patch = patch.object(m, 'cache_path', return_value=self.path)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def plugin(self, **fields):
        return {'id': 'example.radio', 'name': 'Radio', 'description': 'Listen to stations',
                'author': 'Jane', 'tags': ['music'], 'repo': 'https://github.com/example/radio',
                'verificationStatus': 'verified', 'verificationSnapshotStatus': 'verified',
                'verificationCoverage': 'snapshot-verified', 'verificationCommit': 'a' * 40,
                'listingValidatedCommit': 'a' * 40, 'upstreamObservedCommit': 'a' * 40,
                'repositoryLayout': 'root-plugin', 'installAvailable': True, **fields}

    def cache(self):
        value = {'schema': 1, 'entries': m.normalize({'plugins': [self.plugin()]}),
                 'fetchedAt': '2026-10-19T04:00:00+00:00'}
        self.path.write_text(json.dumps(value))
        return value

    def test_verification_requires_exact_snapshot_and_current_upstream(self):
        self.assertTrue(m.normalize({'plugins': [self.plugin()]})[0]['verified'])
        for fields in ({'upstreamObservedCommit': 'b' * 40}, {'listingValidatedCommit': 'b' * 40},
                       {'verificationSnapshotStatus': 'unverified'}, {'verificationCommit': ''},
                       {'verificationStatus': 'unverified'}, {'verificationCoverage': 'update-unverified'}):
            with self.subTest(fields=fields):
                self.assertFalse(m.normalize({'plugins': [self.plugin(**fields)]})[0]['verified'])
        row = m.normalize({'plugins': [self.plugin(verificationStatus='unverified', verificationCoverage='update-unverified')]})[0]
        self.assertEqual(row['coverage'], 'update-unverified')

    def test_untrusted_commands_urls_and_text_are_data_only(self):
        markup = '<img src="https://example.invalid/tracker">'
        row = m.normalize({'plugins': [self.plugin(name=markup, description='x' * 5000,
                           repo='https://github.com/example/radio;touch /oops', installCommand='touch /oops') ]})[0]
        self.assertEqual(row['name'], markup)
        self.assertEqual(len(row['description']), 1200)
        self.assertEqual(row['repo'], '')
        self.assertFalse(row['installable'])
        self.assertNotIn('installCommand', row)
        self.assertIn('jane', row['searchText'])
        self.assertIn('music', row['searchText'])

    def test_invalid_duplicate_builtin_and_nonroot_entries(self):
        entries = [self.plugin(), self.plugin(name='Duplicate'), self.plugin(id='../bad'),
                   self.plugin(id='omarchy.clock', builtIn=True), self.plugin(id='manual', repositoryLayout='monorepo')]
        rows = m.normalize({'plugins': entries})
        self.assertEqual(len(rows), 2)
        self.assertFalse(next(row for row in rows if row['id'] == 'manual')['installable'])
        for invalid in ([], {'plugins': {}}, {'plugins': []}):
            with self.assertRaises(ValueError): m.normalize(invalid)
        with patch.object(m, 'MAX_PLUGINS', 1), self.assertRaises(ValueError): m.normalize({'plugins': entries})

    def test_cached_search_and_state_never_contact_network(self):
        self.cache()
        with patch.object(m.urllib.request, 'urlopen') as network, patch.object(m, 'installed_plugins', return_value={'example.radio': {'enabled': False}}):
            result = m.state()
            self.assertTrue(result['entries'][0]['installed'])
            self.assertFalse(result['entries'][0]['enabled'])
            network.assert_not_called()

    def test_refresh_failure_keeps_the_last_catalog_and_timestamp(self):
        cached = self.cache()
        with patch.object(m.urllib.request, 'urlopen', side_effect=OSError('offline')):
            value, warning = m.load(refresh=True)
        self.assertEqual(value, cached)
        self.assertIn('Refresh failed', warning)
        self.assertEqual(json.loads(self.path.read_text()), cached)

    def test_download_limit_and_redirects_fail_without_a_cache(self):
        class Response(io.BytesIO):
            def geturl(self): return m.CATALOG_URL
        with patch.object(m, 'MAX_BYTES', 20), patch.object(m.urllib.request, 'urlopen', return_value=Response(b'x' * 21)):
            with self.assertRaisesRegex(RuntimeError, 'Could not load'): m.load()
        class Redirect(Response):
            def geturl(self): return 'https://elsewhere.invalid/catalog'
        with patch.object(m.urllib.request, 'urlopen', return_value=Redirect(b'{}')):
            with self.assertRaisesRegex(RuntimeError, 'Could not load'): m.load()
        self.assertFalse(self.path.exists())

    def test_successful_download_saves_a_normalized_atomic_cache(self):
        class Response(io.BytesIO):
            def geturl(self): return m.CATALOG_URL
        with patch.object(m.urllib.request, 'urlopen', return_value=Response(json.dumps({'plugins': [self.plugin()]}).encode())):
            result, warning = m.load()
        self.assertEqual(warning, '')
        self.assertEqual(result['entries'][0]['id'], 'example.radio')
        self.assertEqual(m.read_cache(), result)

    def test_install_uses_native_argv_without_enabling_and_confirms_readback(self):
        self.cache()
        with patch.object(m, 'installed_plugins', side_effect=[{}, {'example.radio': {'enabled': False}}, {'example.radio': {'enabled': False}}]), patch.object(m, 'command') as command:
            result = m.install('example.radio')
        command.assert_called_once_with(['omarchy', 'plugin', 'add', 'https://github.com/example/radio', '--yes'], timeout=180)
        self.assertTrue(result['entries'][0]['installed'])
        self.assertFalse(result['entries'][0]['enabled'])

    def test_duplicate_invalid_or_manual_install_does_not_mutate(self):
        cached = self.cache()
        with patch.object(m, 'command') as command:
            for invalid in ('../bad', '--help', None, 'missing'):
                with self.assertRaises(ValueError): m.install(invalid)
            with patch.object(m, 'installed_plugins', return_value={'example.radio': {}}):
                with self.assertRaisesRegex(ValueError, 'already installed'): m.install('example.radio')
            cached['entries'][0]['installable'] = False
            self.path.write_text(json.dumps(cached))
            with self.assertRaisesRegex(ValueError, 'manual setup'): m.install('example.radio')
            command.assert_not_called()

    def test_failed_install_readback_does_not_claim_success(self):
        self.cache()
        for after in ({}, {'example.radio': {'enabled': True}}):
            with patch.object(m, 'installed_plugins', side_effect=[{}, after]), patch.object(m, 'command'):
                with self.assertRaises(RuntimeError): m.install('example.radio')

    def test_enable_requires_and_verifies_the_native_installed_state(self):
        self.cache()
        with patch.object(m, 'installed_plugins', return_value={}), patch.object(m, 'command') as command:
            with self.assertRaises(ValueError): m.enable('example.radio')
            command.assert_not_called()
        with patch.object(m, 'installed_plugins', return_value={'example.radio': {'enabled': False}}), patch.object(m, 'command'):
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'): m.enable('example.radio')
        with patch.object(m, 'installed_plugins', return_value={'example.radio': {'enabled': True}}), patch.object(m, 'command') as command:
            self.assertTrue(m.enable('example.radio')['entries'][0]['enabled'])
            command.assert_called_once_with(['omarchy', 'plugin', 'enable', 'example.radio'])

    def test_cached_repository_is_revalidated_before_launching(self):
        cached = self.cache()
        cached['entries'][0]['repo'] = 'ext::touch /oops'
        self.path.write_text(json.dumps(cached))
        with patch.object(m, 'command') as command:
            with self.assertRaises(ValueError): m.source('example.radio')
            command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
