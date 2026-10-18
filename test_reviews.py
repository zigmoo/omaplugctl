import json
import os
import re
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controller
import reviews
import updates
import native_reviewers
import fcntl


class ReviewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'XDG_STATE_HOME': self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        settings = patch.object(reviews, 'bar_settings', return_value={})
        settings.start()
        self.addCleanup(settings.stop)
        provenance = patch.object(reviews, 'source_context', return_value={})
        provenance.start()
        self.addCleanup(provenance.stop)

    def test_partition_preserves_all_bytes_and_character_boundaries(self):
        source = 'diff --git a/large b/large\n@@ -1 +1 @@\n+' + '🦊é' * 500 + '\n'
        parts = reviews.partition(source, 113)
        self.assertGreater(len(parts), 2)
        self.assertEqual(''.join(p['text'] for p in parts), source)
        self.assertEqual(parts[-1]['end'], len(source.encode()))
        self.assertTrue(all(len(p['text'].encode()) <= 113 for p in parts))
        self.assertTrue(any('diff --git' in p['context'] for p in parts[1:]))

    def test_duplicate_click_cannot_dispatch_a_second_review(self):
        lock = reviews.status_path('example.widget').with_suffix('.lock')
        lock.parent.mkdir(parents=True)
        with lock.open('a') as file, patch.object(reviews, 'reviewer') as reviewer:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'already running'):
                reviews.run_review({'id': 'example.widget'}, {}, {})
            reviewer.assert_not_called()

    def test_partition_prefers_file_boundaries(self):
        a = 'diff --git a/one b/one\n+first\n'
        b = 'diff --git a/two b/two\n+second\n'
        parts = reviews.partition(a + b, len(a.encode()) + 4)
        self.assertEqual([p['text'] for p in parts], [a, b])

    def test_report_action_opens_generated_https_knowledge_url(self):
        reviews.save_status('example.widget', artifact='/memory/review.md', status='complete')
        with patch.object(reviews, 'command', side_effect=['https://example.invalid/review', '']) as command:
            reviews.open_report('example.widget')
            self.assertEqual(command.call_args.args[0], ['xdg-open', 'https://example.invalid/review'])

    def test_report_action_rejects_missing_result_and_non_https_url(self):
        with self.assertRaises(RuntimeError): reviews.open_report('example.widget')
        reviews.save_status('example.widget', artifact='/memory/review.md')
        with patch.object(reviews, 'command', return_value='javascript:unsafe') as command:
            with self.assertRaises(RuntimeError): reviews.open_report('example.widget')
            self.assertEqual(command.call_count, 1)

    def test_machine_preference_overrides_shared_default(self):
        with patch.object(reviews, 'machine_name', return_value='testbox'), patch.object(reviews, 'command', return_value='{"value":"machine-mini"}') as command:
            self.assertEqual(reviews.preference(), ('machine-mini', 'defaultPreferredReviewer.testbox'))
            self.assertEqual(command.call_count, 1)

    def test_missing_machine_preference_uses_shared_default(self):
        with patch.object(reviews, 'machine_name', return_value='testbox'), patch.object(reviews, 'command', side_effect=['', '{"value":"shared-mini"}']):
            self.assertEqual(reviews.preference(), ('shared-mini', 'defaultPreferredReviewer'))

    def test_default_source_matches_dil_availability(self):
        with patch.object(reviews, 'bar_settings', return_value={}), patch.object(reviews, 'dil_available', return_value=True):
            self.assertEqual(reviews.selection_source(), 'dil')
        with patch.object(reviews, 'bar_settings', return_value={}), patch.object(reviews, 'dil_available', return_value=False):
            self.assertEqual(reviews.selection_source(), 'omarchy')

    def test_native_config_works_without_dil(self):
        option = native_reviewers.option('codex', 'locally-listed-model', 'Listed model')
        with patch.object(reviews, 'selection_source', return_value='omarchy'), patch.object(reviews, 'dil_available', return_value=False), \
             patch.object(reviews, 'native_options', return_value=([option], 'codex', [])), patch.object(reviews, 'bar_settings', return_value={'nativeReviewer': option['id']}):
            result = reviews.reviewer_config()
            self.assertEqual(result['sourceType'], 'omarchy')
            self.assertTrue(result['standalone'])
            self.assertEqual(result['selected'], option['id'])

    def test_source_cannot_show_saved_state_before_confirmed(self):
        with patch.object(reviews, 'dil_available', return_value=True), patch.object(reviews, 'command') as command, patch.object(reviews, 'bar_settings', return_value={}):
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'): reviews.set_source('omarchy')
            self.assertEqual(command.call_args.args[0][-2:], ['reviewerSource', 'omarchy'])

    def test_native_adapter_never_interpolates_model_into_shell(self):
        route = dict(agent='codex', model='$(touch unsafe)', dil=False, effort='default')
        argv, writes = native_reviewers.argv(route, 'Review', pathlib.Path('/input'), pathlib.Path('/report'), pathlib.Path('/work'))
        self.assertIn('$(touch unsafe)', argv)
        self.assertIn('read-only', argv)
        self.assertTrue(writes)

    def test_native_models_come_from_omarchy_and_cli_output(self):
        def command(argv, **kwargs):
            if argv == ['omarchy', 'commands', '--json']:
                return '{"commands":[{"route":"omarchy default agent","args":"[cursor-agent]"}]}'
            if argv == ['omarchy', 'default', 'agent']: return 'cursor-agent'
            if argv == ['cursor-agent', '--list-models']: return 'Available models\nlisted-mini - Listed Mini\n'
            self.fail(str(argv))
        with patch.object(native_reviewers.shutil, 'which', return_value='/installed'):
            options, preferred, errors = native_reviewers.discover(command)
        self.assertEqual(preferred, 'cursor-agent')
        self.assertEqual([o['model'] for o in options], ['', 'listed-mini'])
        self.assertEqual(errors, [])
    def resolve(self, binding=None, setting='registered-mini', harnesses=None):
        binding = binding or {'binding_id': 'registered-mini', 'dispatch_enabled': True, 'status': 'active',
                              'harness': 'cursor-agent', 'agent_tool_name': 'cursor-agent', 'display_name': 'Mini'}
        harnesses = harnesses if harnesses is not None else [{'id': 'cursor', 'triggers': ['cursor-agent'], 'binary': 'cursor-agent'}]
        def command(argv, **kwargs):
            if argv[0] == 'settings_tool': return json.dumps({'value': setting})
            if argv[0] == 'agent_dispatch_binding_registry_tool': return json.dumps(binding)
            if argv[0] == 'harness_registry_tool': return json.dumps({'harnesses': harnesses})
            self.fail(f'Unexpected command {argv}')
        with patch.object(reviews.shutil, 'which', return_value='/bin/tool'), patch.object(reviews, 'command', side_effect=command):
            return reviews.reviewer()

    def test_setting_resolves_registered_binding_and_harness_trigger(self):
        self.assertEqual(self.resolve()['binding'], 'registered-mini')

    def test_disabled_binding_does_not_fall_back(self):
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            self.resolve(binding={'dispatch_enabled': False, 'status': 'active'})

    def test_inactive_harness_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.resolve(harnesses=[])

    def test_malformed_setting_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'binding ID'):
            self.resolve(setting='mini; touch nope')

    def test_missing_setting_does_not_silently_choose_agent(self):
        with patch.object(reviews.shutil, 'which', return_value='/bin/tool'), patch.object(reviews, 'command', side_effect=RuntimeError('setting missing')):
            with self.assertRaisesRegex(RuntimeError, 'setting missing'): reviews.reviewer()

    def test_standalone_uses_installed_codex_configured_default(self):
        with patch.object(reviews.shutil, 'which', side_effect=lambda name: '/bin/codex' if name == 'codex' else None):
            self.assertFalse(reviews.reviewer()['dil'])

    def test_partial_dil_installation_cannot_bypass_task_evidence(self):
        with patch.object(reviews.shutil, 'which', side_effect=lambda name: '/bin/tool' if name in ('task_tool', 'codex') else None):
            with self.assertRaisesRegex(RuntimeError, 'settings_tool'): reviews.reviewer()

    def test_terminal_output_cannot_contain_escape_sequences(self):
        result = reviews.terminal_text('hello\x1b]52;c;evil\x07\nreport')
        self.assertNotIn('\x1b', result)
        self.assertNotIn('\x07', result)
        self.assertIn('\nreport', result)

    def test_review_evidence_precedes_dispatch_and_success_is_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            events = []
            receipts = []
            def command(argv, **kwargs):
                events.append(argv)
                if argv[:2] == ['task_tool', 'create']: return 'OK | DIL-9999 | created'
                if argv[:2] == ['task_tool', 'show']: return '\n'.join(receipts)
                return 'https://example.invalid/record'
            def dispatch(argv, **kwargs):
                events.append(argv)
                instructions = argv[argv.index('--prompt') + 1]
                receipts.append(re.search(r'OMAPLUGCTL_AGENT_WORK [\w-]+ [\w-]+', instructions)[0])
                pathlib.Path(argv[argv.index('--output') + 1]).write_text('No findings. Context limited. Proceed to human review.')
                return subprocess.CompletedProcess(argv, 0)
            source = {'root': tmp, 'head': 'a' * 40, 'identity': 'source', 'dirty': False}
            large = 'diff --git a/large b/large\n@@ -1 +1 @@\n+' + 'x' * 260_000
            with patch.object(reviews, 'reviewer', return_value={'dil': True, 'agent': 'registered-agent', 'binding': 'registered-mini', 'label': 'Mini'}), \
                 patch.object(reviews, 'scratch', return_value=directory), patch.object(reviews, 'snapshot', return_value=(large, 'b' * 40)), \
                 patch.object(reviews, 'source_context', return_value={'repository': 'https://github.com/owner/repo', 'upstream': 'https://github.com/owner/repo/commit/' + 'b' * 40}), \
                 patch.object(reviews, 'command', side_effect=command), patch.object(reviews, 'compose', return_value=directory / 'report.md'), \
                 patch.object(reviews.subprocess, 'run', side_effect=dispatch), patch.object(updates, 'source', return_value=source), \
                 patch.object(updates, 'compare_source', return_value={'status': 'available'}):
                self.assertTrue(reviews.run_review({'id': 'example.widget'}, source, {}))
            review_index = next(i for i, argv in enumerate(events) if argv[0] == 'agent_tool')
            self.assertTrue(any(argv[:2] == ['task_tool', 'append-note'] for argv in events[:review_index]))
            argv = events[review_index]
            self.assertIn('--binding-id', argv)
            self.assertEqual(argv[argv.index('--binding-id') + 1], 'registered-mini')
            self.assertIn('--task-id', argv)
            self.assertTrue(any(argv[:2] == ['task_tool', 'append-note'] for argv in events[review_index + 1:]))
            self.assertFalse(any(argv[:3] == ['omarchy', 'plugin', 'update'] for argv in events))
            calls = [argv for argv in events if argv[0] == 'agent_tool']
            self.assertEqual(len(calls), 3)  # Two complete source parts and one synthesis.
            self.assertTrue(all(pathlib.Path(argv[argv.index('--file')+1]).stat().st_size <= reviews.LIMIT for argv in calls))
            self.assertEqual(sum(argv[:2] == ['task_tool', 'create'] for argv in events), 1)
            self.assertTrue(all('task_tool pickup' in argv[argv.index('--prompt')+1] for argv in calls))
            self.assertEqual(reviews.statuses()['example.widget']['status'], 'complete')
            manifest = json.loads((directory / 'coverage.json').read_text())
            self.assertEqual(manifest['parts'][-1]['end'], len(large.encode()))
            self.assertIn('[Open repository](https://github.com/owner/repo)', (directory / 'review-report.txt').read_text())

    def test_failed_review_records_failure_and_never_opens_updater(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            def command(argv, **kwargs):
                events.append((argv, kwargs.get('body', '')))
                return 'DIL-9999' if argv[:2] == ['task_tool', 'create'] else ''
            with patch.object(reviews, 'reviewer', return_value={'dil': True, 'agent': 'registered-agent', 'binding': 'mini', 'label': 'Mini'}), \
                 patch.object(reviews, 'scratch', return_value=pathlib.Path(tmp)), patch.object(reviews, 'command', side_effect=command), \
                 patch.object(reviews, 'snapshot', side_effect=RuntimeError('offline')), patch.object(reviews.subprocess, 'run') as dispatch:
                with self.assertRaisesRegex(RuntimeError, 'offline'):
                    reviews.run_review({'id': 'example.widget'}, {}, {})
                dispatch.assert_not_called()
            self.assertIn('did not complete', events[-1][1])

    def test_report_without_agent_task_work_receipt_is_not_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            def command(argv, **kwargs):
                return 'DIL-9999' if argv[:2] == ['task_tool', 'create'] else ''
            def dispatch(argv, **kwargs):
                pathlib.Path(argv[argv.index('--output') + 1]).write_text('A report without task work.')
                return subprocess.CompletedProcess(argv, 0)
            with patch.object(reviews, 'reviewer', return_value={'dil': True, 'agent': 'reviewer', 'binding': 'mini', 'label': 'Mini'}), \
                 patch.object(reviews, 'scratch', return_value=directory), patch.object(reviews, 'snapshot', return_value=('diff', 'b' * 40)), \
                 patch.object(reviews, 'command', side_effect=command), patch.object(reviews, 'compose', return_value=directory / 'request.md'), \
                 patch.object(reviews.subprocess, 'run', side_effect=dispatch):
                with self.assertRaisesRegex(RuntimeError, 'without recording'):
                    reviews.run_review({'id': 'example.widget'}, {'head': 'a' * 40, 'dirty': False}, {})
            self.assertEqual(reviews.statuses()['example.widget']['status'], 'failed')
            self.assertNotIn('artifact', reviews.statuses()['example.widget'])

    def test_agent_review_failure_never_reaches_installer(self):
        with patch.object(controller, 'update_target', return_value=({'id': 'example.widget'}, {})), \
             patch.object(controller, 'run', return_value='[{"id":"example.widget"}]'), \
             patch.object(reviews, 'run_review', side_effect=RuntimeError('review failed')), patch.object(controller.subprocess, 'run') as install:
            with self.assertRaisesRegex(RuntimeError, 'review failed'): controller.review_update('example.widget')
            install.assert_not_called()

    def test_user_can_read_report_and_decline_updater(self):
        with patch.object(controller, 'update_target', return_value=({'id': 'example.widget'}, {})), \
             patch.object(controller, 'run', return_value='[{"id":"example.widget"}]'), \
             patch.object(reviews, 'run_review', return_value=True), patch('builtins.input', return_value='n'), \
             patch.object(controller.subprocess, 'run') as install:
            self.assertEqual(controller.review_update('example.widget'), 0)
            install.assert_not_called()


class SourceUrlTests(unittest.TestCase):
    def test_https_and_ssh_origins_normalize_to_the_same_repository(self):
        expected = 'https://github.com/promaaa/sync-calendar-omarchy'
        for remote in ('https://github.com/promaaa/sync-calendar-omarchy.git',
                       'git@github.com:promaaa/sync-calendar-omarchy.git',
                       'ssh://git@github.com/promaaa/sync-calendar-omarchy.git'):
            self.assertEqual(reviews.repository_url(remote), expected)

    def test_credentials_and_query_tokens_never_enter_report_links(self):
        result = reviews.repository_url('https://person:secret@github.com/owner/repo.git?token=private#fragment')
        self.assertEqual(result, 'https://github.com/owner/repo')

    def test_local_or_unsafe_origins_do_not_get_invented_web_links(self):
        for remote in ('/work/remote.git', 'file:///work/remote.git', 'javascript:alert(1)', 'https://example.com/../repo'):
            self.assertEqual(reviews.repository_url(remote), '')

    def test_report_links_pin_both_commits_and_use_two_dot_tree_comparison(self):
        info = {'root': '/source', 'head': 'a' * 40}
        with patch.object(updates, 'git', return_value='git@github.com:owner/repo.git'):
            context = reviews.source_context(info, 'b' * 40)
        self.assertEqual(context['upstream'], 'https://github.com/owner/repo/commit/' + 'b' * 40)
        self.assertEqual(context['comparison'], 'https://github.com/owner/repo/compare/' + 'a' * 40 + '..' + 'b' * 40)
        self.assertIn('Source repository: [Open repository](https://github.com/owner/repo)', reviews.source_markdown(context))
        self.assertIn('Reviewed upstream commit:', reviews.source_markdown(context))

    def test_unknown_host_gets_repository_link_without_invented_routes(self):
        with patch.object(updates, 'git', return_value='https://git.example.org/team/project.git'):
            context = reviews.source_context({'root': '/source', 'head': 'a' * 40}, 'b' * 40)
        self.assertEqual(context, {'repository': 'https://git.example.org/team/project'})


if __name__ == '__main__': unittest.main()
