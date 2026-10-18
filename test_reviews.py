import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controller
import reviews
import updates


class ReviewerTests(unittest.TestCase):
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
            def command(argv, **kwargs):
                events.append(argv)
                if argv[:2] == ['task_tool', 'create']: return 'OK | DIL-9999 | created'
                return 'https://example.invalid/record'
            def dispatch(argv, **kwargs):
                events.append(argv)
                pathlib.Path(argv[argv.index('--output') + 1]).write_text('No findings. Context limited. Proceed to human review.')
                return subprocess.CompletedProcess(argv, 0)
            source = {'root': tmp, 'head': 'a' * 40, 'identity': 'source', 'dirty': False}
            with patch.object(reviews, 'reviewer', return_value={'dil': True, 'agent': 'registered-agent', 'binding': 'registered-mini', 'label': 'Mini'}), \
                 patch.object(reviews, 'scratch', return_value=directory), patch.object(reviews, 'snapshot', return_value=('immutable diff', 'b' * 40)), \
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

    def test_failed_review_records_failure_and_never_opens_updater(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            def command(argv, **kwargs):
                events.append((argv, kwargs.get('body', '')))
                return 'DIL-9999' if argv[:2] == ['task_tool', 'create'] else ''
            with patch.object(reviews, 'reviewer', return_value={'dil': True, 'binding': 'mini'}), \
                 patch.object(reviews, 'scratch', return_value=pathlib.Path(tmp)), patch.object(reviews, 'command', side_effect=command), \
                 patch.object(reviews, 'snapshot', side_effect=RuntimeError('offline')), patch.object(reviews.subprocess, 'run') as dispatch:
                with self.assertRaisesRegex(RuntimeError, 'offline'):
                    reviews.run_review({'id': 'example.widget'}, {}, {})
                dispatch.assert_not_called()
            self.assertIn('did not complete', events[-1][1])

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


if __name__ == '__main__': unittest.main()
