import unittest
import json
import pathlib
import tempfile
import io
import contextlib
from unittest.mock import patch
import controller as c

class ControllerTests(unittest.TestCase):
    def test_scan_toggle_saves_booleans_and_reads_back_the_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            configuration = home / '.config/omarchy/shell.json'
            configuration.parent.mkdir(parents=True)
            configuration.write_text(json.dumps({'bar': {'layout': {'right': [{'id': c.SELF}]}}}))

            def save_setting(arguments):
                self.assertEqual(arguments[:5], ['omarchy', 'bar', 'set', c.SELF, 'scanBeforeUpdate'])
                # Mirror the Omarchy CLI's distinction between string and JSON input.
                value = json.loads(arguments[5]) if '--json' in arguments[6:] else arguments[5]
                data = json.loads(configuration.read_text())
                data['bar']['layout']['right'][0]['scanBeforeUpdate'] = value
                configuration.write_text(json.dumps(data))

            with patch.object(c.pathlib.Path, 'home', return_value=home), \
                 patch.object(c, 'run', side_effect=save_setting), \
                 patch.object(c, 'inventory', return_value=[]):
                for requested in ('false', 'true'):
                    with self.subTest(requested=requested):
                        c.set_scan_before_update(requested)
                        saved = json.loads(configuration.read_text())['bar']['layout']['right'][0]['scanBeforeUpdate']
                        self.assertIs(saved, requested == 'true')
                        self.assertIs(c.scan_before_update(), saved)

    def test_scan_toggle_reports_a_failed_save_without_changing_confirmed_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            configuration = home / '.config/omarchy/shell.json'
            configuration.parent.mkdir(parents=True)
            configuration.write_text(json.dumps({'bar': {'layout': {'right': [{'id': c.SELF, 'scanBeforeUpdate': True}]}}}))
            with patch.object(c.pathlib.Path, 'home', return_value=home), patch.object(c, 'run'):
                with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
                    c.set_scan_before_update('false')
                self.assertTrue(c.scan_before_update())

    def test_scan_toggle_rejects_invalid_values_before_saving(self):
        with patch.object(c, 'run') as run:
            with self.assertRaises(ValueError):
                c.set_scan_before_update('off')
            run.assert_not_called()

    def test_sort_by_name_is_case_insensitive(self):
        plugins = [{'id': 'z', 'name': 'alpha'}, {'id': 'a', 'name': 'Bravo'}]
        self.assertEqual([p['id'] for p in c.sort_plugins(plugins, 'name')], ['z', 'a'])

    def test_sort_by_screen_includes_center_regions_and_disabled_last(self):
        plugins = [
            {'id': 'disabled', 'name': 'A', 'instances': []},
            {'id': 'right', 'name': 'B', 'instances': [{'section': 'right', 'index': 0}]},
            {'id': 'center', 'name': 'C', 'instances': [{'section': 'center', 'index': 0}]},
            {'id': 'before', 'name': 'D', 'instances': [{'section': 'centerBegin', 'index': 0}]},
            {'id': 'left', 'name': 'Z', 'instances': [{'section': 'left', 'index': 1}]},
        ]
        self.assertEqual([p['id'] for p in c.sort_plugins(plugins, 'screen')], ['left', 'before', 'center', 'right', 'disabled'])

    def test_sort_pending_updates_by_newest_date(self):
        plugins = [
            {'id': 'none', 'name': 'A', 'update': {'status': 'current'}},
            {'id': 'old', 'name': 'B', 'update': {'status': 'available', 'latestDate': '2026-01-01'}},
            {'id': 'new', 'name': 'C', 'update': {'status': 'diverged', 'latestDate': '2026-10-18'}},
        ]
        self.assertEqual([p['id'] for p in c.sort_plugins(plugins, 'updates')], ['new', 'old', 'none'])

    def test_sort_requires_confirmed_storage(self):
        with patch.object(c, 'run') as run, patch.object(c, 'configured_sort', return_value='name'):
            with self.assertRaises(RuntimeError): c.set_sort('screen')
            self.assertEqual(run.call_args.args[0], ['omarchy', 'bar', 'set', c.SELF, 'sortOrder', 'screen'])

    def test_author_accepts_declared_names_without_guessing(self):
        self.assertEqual(c.plugin_author({'author': '  Jane\nDoe  '}), 'Jane Doe')
        self.assertEqual(c.plugin_author({'authors': [{'name': 'Jane'}, 'John']}), 'Jane, John')
        self.assertEqual(c.plugin_author({'author': 12}), '')
        self.assertEqual(c.plugin_details({}), {'author': '', 'updatedDate': ''})

    def test_local_update_ignores_git_and_generated_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = root / 'manifest.json'
            manifest.write_text('{"author":"Jane"}')
            source = root / 'Widget.qml'
            source.write_text('import QtQuick')
            (root / '.git').mkdir()
            cache = root / '.git/FETCH_HEAD'
            cache.write_text('newer metadata is not a plugin change')
            (root / '__pycache__').mkdir()
            generated = root / '__pycache__/controller.pyc'
            generated.write_text('ignored')
            old = c.datetime.datetime(2026, 3, 1, 12).timestamp()
            recent = c.datetime.datetime(2026, 3, 15, 12).timestamp()
            newest = c.datetime.datetime(2026, 3, 20, 12).timestamp()
            c.os.utime(manifest, (old, old))
            c.os.utime(source, (recent, recent))
            for file in (cache, generated): c.os.utime(file, (newest, newest))
            self.assertEqual(c.plugin_details({'manifestPath': str(manifest)}), {'author': 'Jane', 'updatedDate': '2026-03-15'})

    def test_shared_builtin_directory_date_is_scoped_to_its_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            manifest = root / 'Clock.manifest.json'
            manifest.write_text('{}')
            clock = root / 'Clock.qml'; clock.write_text('clock')
            other = root / 'Other.qml'; other.write_text('unrelated')
            older = c.datetime.datetime(2026, 3, 1, 12).timestamp()
            newer = c.datetime.datetime(2026, 3, 20, 12).timestamp()
            for file in (manifest, clock): c.os.utime(file, (older, older))
            c.os.utime(other, (newer, newer))
            self.assertEqual(c.local_update_date(manifest, {'entryPoints': {'barWidget': 'Clock.qml'}}), '2026-03-01')

    def test_unreadable_manifest_does_not_invent_metadata(self):
        self.assertEqual(c.plugin_details({'manifestPath': '/does/not/exist/manifest.json'}), {'author': '', 'updatedDate': ''})

    def test_description_includes_function_and_distinct_widget_details(self):
        metadata = {'description': '  Adjust a webcam.\n', 'barWidget': {'description': 'Live preview and zoom.'}}
        self.assertEqual(c.plugin_description(metadata), 'Adjust a webcam.\n\nLive preview and zoom.')
        metadata['barWidget']['description'] = 'Adjust a webcam.'
        self.assertEqual(c.plugin_description(metadata), 'Adjust a webcam.')

    def test_missing_and_malformed_descriptions_are_empty(self):
        self.assertEqual(c.plugin_description({}), '')
        self.assertEqual(c.plugin_description({'description': 42, 'barWidget': 'invalid'}), '')

    def test_description_is_bounded_and_preserves_literal_markup(self):
        markup = '<img src="https://example.invalid/tracker">'
        self.assertEqual(c.plugin_description({'description': markup}), markup)
        result = c.plugin_description({'description': 'x' * 2000})
        self.assertEqual(len(result), 1200)
        self.assertTrue(result.endswith('…'))

    def test_inventory_joins_description_from_local_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            config = home / '.config/omarchy/shell.json'
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({'bar': {'layout': {}}}))
            plugin = self.plugin()
            catalog = [{'id': plugin['id'], 'description': 'Shows useful desktop information.'}]
            with patch.object(c.pathlib.Path, 'home', return_value=home), patch.object(c, 'run', side_effect=[json.dumps([plugin]), json.dumps(catalog)]) as run, patch.object(c.urllib.request, 'urlopen') as network:
                self.assertEqual(c.inventory()[0]['description'], 'Shows useful desktop information.')
                self.assertEqual(run.call_args_list[1].args[0], ['omarchy-plugin-catalog'])
                network.assert_not_called()

    def test_bar_position_confirms_every_edge(self):
        for edge in c.EDGES:
            with self.subTest(edge=edge), patch.object(c, 'inventory', return_value=[]), patch.object(c, 'run', side_effect=['Bar position set', edge]) as run:
                result = c.set_bar_position(edge)
                self.assertEqual(result['barPosition'], edge)
                self.assertEqual(run.call_args_list[0].args[0], ['omarchy', 'bar', 'position', edge])
                self.assertEqual(run.call_args_list[1].args[0], ['omarchy', 'bar', 'position'])

    def test_invalid_bar_edge_does_not_mutate(self):
        for edge in (None, 'center', 'top; touch nope'):
            with self.subTest(edge=edge), patch.object(c, 'run') as run:
                with self.assertRaises(ValueError): c.set_bar_position(edge)
                run.assert_not_called()

    def test_unconfirmed_bar_position_is_failure(self):
        with patch.object(c, 'run', side_effect=['Bar position set', 'left']):
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
                c.set_bar_position('top')

    def test_bar_command_failure_is_reported(self):
        with patch.object(c, 'run', side_effect=RuntimeError('Cannot save bar config')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot save'):
                c.set_bar_position('right')

    def test_unknown_saved_bar_position_is_failure(self):
        with patch.object(c, 'run', return_value='unexpected output'):
            with self.assertRaisesRegex(RuntimeError, 'Could not read'):
                c.bar_position()

    def test_list_response_includes_saved_bar_position(self):
        output = io.StringIO()
        with patch.object(c.sys, 'argv', ['controller.py', 'list']), patch.object(c, 'inventory', return_value=[]), patch.object(c, 'bar_position', return_value='bottom'), patch.object(c, 'configured_sort', return_value='name'), contextlib.redirect_stdout(output):
            self.assertEqual(c.main(), 0)
        self.assertEqual(json.loads(output.getvalue())['barPosition'], 'bottom')

    def test_cli_position_failure_does_not_claim_success(self):
        output = io.StringIO()
        with patch.object(c.sys, 'argv', ['controller.py', 'position', '--edge', 'top']), patch.object(c, 'set_bar_position', side_effect=RuntimeError('not confirmed')), contextlib.redirect_stdout(output):
            self.assertEqual(c.main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {'ok': False, 'message': 'not confirmed'})

    def test_builtin_about_matches_manifest_and_tracks_default_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)/'shell/plugins/panels/tailscale'
            directory.mkdir(parents=True)
            (directory/'manifest.json').write_text(json.dumps({'id':'omarchy.tailscale'}))
            with patch.dict(c.os.environ, {'OMARCHY_PATH':tmp}):
                self.assertEqual(c.builtin_about_url('omarchy.tailscale'),
                                 'https://github.com/omacom/omarchy/tree/HEAD/shell/plugins/panels/tailscale')
                self.assertEqual(c.builtin_about_url('omarchy.unknown'), 'https://github.com/omacom/omarchy')

    def test_builtin_clone_about_uses_original_id(self):
        with patch.object(c.pathlib.Path,'exists',return_value=False), patch.object(c,'builtin_about_url',return_value='source') as url:
            self.assertEqual(c.about_url({'id':'custom.tailscale','firstParty':False,'clonedFrom':'omarchy.tailscale'}),'source')
            url.assert_called_once_with('omarchy.tailscale')

    def plugin(self, **kwargs):
        return dict(id='example.widget', name='Example', kinds=['bar-widget'], enabled=True,
                    firstParty=False, canRemove=True, instances=[{'section':'right','index':3}], **kwargs)

    def test_move_targets_selected_duplicate(self):
        p=self.plugin(); p['instances'].append({'section':'left','index':1})
        q={**p,'instances':[{'section':'left','index':1},{'section':'center','index':0}]}
        with patch.object(c,'inventory',side_effect=[[p],[q]]), patch.object(c,'run',return_value='ok') as run:
            c.execute('move',p['id'],'center','right',3)
            placement=__import__('json').loads(run.call_args.args[0][-1])
            self.assertEqual(placement,{'section':'center','fromSection':'right','fromIndex':3})

    def test_stale_instance_does_not_mutate(self):
        p=self.plugin()
        with patch.object(c,'inventory',return_value=[p]), patch.object(c,'run') as run:
            with self.assertRaises(ValueError): c.execute('move',p['id'],'center','right',7)
            run.assert_not_called()

    def test_uninstall_requires_confirmation(self):
        p=self.plugin()
        with patch.object(c,'inventory',return_value=[p]), patch.object(c,'run') as run:
            with self.assertRaises(ValueError): c.execute('remove',p['id'])
            run.assert_not_called()

    def test_builtin_cannot_be_removed_even_if_confirmed(self):
        p=self.plugin(); p['firstParty']=True; p['canRemove']=False
        with patch.object(c,'inventory',return_value=[p]), patch.object(c,'run') as run:
            with self.assertRaises(ValueError): c.execute('remove',p['id'],confirmed=True)
            run.assert_not_called()

    def test_disable_unconfirmed_readback_is_failure(self):
        p=self.plugin()
        with patch.object(c,'inventory',return_value=[p]), patch.object(c,'run',return_value='Disabled'):
            with self.assertRaises(RuntimeError): c.execute('disable',p['id'])

    def test_disable_confirmed_readback(self):
        p=self.plugin(); q={**p,'enabled':False,'instances':[]}
        with patch.object(c,'inventory',side_effect=[[p],[q]]), patch.object(c,'run',return_value='Disabled'):
            self.assertEqual(c.execute('disable',p['id'])['plugins'],[q])

    def test_command_arguments_never_use_shell(self):
        with patch.object(c.subprocess,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout='ok'
            c.run(['test', '$(touch nope)'])
            self.assertEqual(run.call_args.args[0],['test','$(touch nope)'])
            self.assertNotIn('shell',run.call_args.kwargs)

if __name__=='__main__': unittest.main()
