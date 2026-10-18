import copy
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controller
import github_reviews as github
import reviews


class GithubTests(unittest.TestCase):
    commit = 'b' * 40
    repository = 'https://github.com/owner/repo'

    def setUp(self):
        self.comments = []
        self.posts = 0
        self.fail_after_create = False

    def command(self, argv, *, body=None, **kwargs):
        self.assertEqual(argv[:5], ['gh', 'api', '--hostname', 'github.com', '--method'])
        endpoint = argv[argv.index('Accept: application/vnd.github+json') + 1]
        method = argv[5]
        if endpoint == 'user':
            return '{"login":"operator"}'
        if method == 'POST':
            self.posts += 1
            value = {'id': len(self.comments) + 1, 'user': {'login': 'operator'},
                     'commit_id': self.commit, 'body': json.loads(body)['body']}
            value['html_url'] = self.repository + '/commit/' + self.commit + f'#commitcomment-{value["id"]}'
            self.comments.append(value)
            if self.fail_after_create:
                self.fail_after_create = False
                raise subprocess.TimeoutExpired(argv, 60)
            return json.dumps(value)
        if '/comments/' in endpoint:
            value = self.comments[int(endpoint.rsplit('/', 1)[1]) - 1]
            if method == 'PATCH':
                value['body'] = json.loads(body)['body']
            return json.dumps(value)
        return json.dumps(self.comments)

    def test_report_is_posted_at_pinned_commit_and_read_back(self):
        url = github.publish('## Findings\nNo findings; no code executed.', self.repository, self.commit, self.command)
        self.assertEqual(url, self.comments[0]['html_url'])
        self.assertIn('No findings', self.comments[0]['body'])
        self.assertEqual(self.posts, 1)

    def test_ambiguous_post_timeout_is_resumed_without_duplicate(self):
        self.fail_after_create = True
        with self.assertRaises(subprocess.TimeoutExpired):
            github.publish('report', self.repository, self.commit, self.command)
        github.publish('report', self.repository, self.commit, self.command)
        self.assertEqual(self.posts, 1)

    def test_large_unicode_report_is_complete_and_continuations_linked(self):
        report = '🦊 evidence\n' * 20_000
        github.publish(report, self.repository, self.commit, self.command)
        self.assertGreater(len(self.comments), 1)
        self.assertTrue(all(len(c['body'].encode()) < 64_000 for c in self.comments))
        recovered = ''.join(c['body'].split('\n\n', 1)[1].split('\n\nReview continuation:', 1)[0] for c in self.comments)
        self.assertEqual(recovered, report)
        self.assertIn(self.comments[1]['html_url'], self.comments[0]['body'])
        github.publish(report, self.repository, self.commit, self.command)
        self.assertEqual(self.posts, len(self.comments))

    def test_mismatched_server_body_is_not_delivered(self):
        def command(argv, **kwargs):
            result = self.command(argv, **kwargs)
            if '/comments/' in argv[-1]:
                value = json.loads(result); value['body'] = 'different report'
                return json.dumps(value)
            return result
        with self.assertRaisesRegex(RuntimeError, 'did not match'):
            github.publish('report', self.repository, self.commit, command)

    def test_another_actor_cannot_supply_the_publication_receipt(self):
        github.publish('report', self.repository, self.commit, self.command)
        self.comments[0]['user']['login'] = 'someone-else'
        github.publish('report', self.repository, self.commit, self.command)
        self.assertEqual(self.posts, 2)

    def test_non_github_or_unpinned_targets_are_rejected(self):
        for url in ('https://github.com.evil/owner/repo', 'https://github.com/../repo',
                    'https://secret@github.com/owner/repo', 'https://github.com/owner/repo?token=secret'):
            with self.assertRaises(RuntimeError): github.target(url, self.commit)
        with self.assertRaises(RuntimeError): github.target(self.repository, 'master')

    def test_unexpected_response_location_is_rejected(self):
        with self.assertRaises(RuntimeError):
            github.comment_url({'html_url': 'https://evil.invalid', 'id': 1, 'commit_id': self.commit}, 'owner/repo', self.commit)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = pathlib.Path(directory.name)
        env = patch.dict(os.environ, {'XDG_STATE_HOME': directory.name})
        env.start(); self.addCleanup(env.stop)
        report = 'No findings. Advisory review.'
        (self.directory / 'review-report.txt').write_text(report)
        job = self.directory / 'publication.json'
        job.write_text(json.dumps({'repository': 'https://github.com/owner/repo', 'upstream': 'b' * 40,
                                   'reportSha256': hashlib.sha256(report.encode()).hexdigest()}))
        reviews.save_status('example.widget', publicationJob=str(job), artifact='/memory/report.md')

    def test_publication_failure_retains_report_and_retry_never_dispatches_agent(self):
        url = 'https://github.com/owner/repo/commit/' + 'b' * 40 + '#commitcomment-1'
        with patch.object(github, 'publish', side_effect=RuntimeError('authentication unavailable')):
            self.assertFalse(reviews.publish_saved('example.widget'))
        value = reviews.statuses()['example.widget']
        self.assertEqual(value['status'], 'publish_failed')
        self.assertEqual(value['artifact'], '/memory/report.md')
        with patch.object(github, 'publish', return_value=url), patch.object(reviews, 'command') as command, \
             patch.object(reviews, 'reviewer') as agent:
            self.assertTrue(reviews.publish_saved('example.widget'))
            agent.assert_not_called()
            command.assert_called_once_with(['xdg-open', url])
        self.assertEqual(reviews.statuses()['example.widget']['githubUrl'], url)

    def test_view_report_prefers_github_over_dil(self):
        url = 'https://github.com/owner/repo/commit/' + 'b' * 40 + '#commitcomment-1'
        reviews.save_status('example.widget', githubUrl=url)
        with patch.object(reviews, 'command') as command:
            reviews.open_report('example.widget')
            command.assert_called_once_with(['xdg-open', url])

    def test_new_review_launch_has_no_terminal_and_duplicate_queue_is_ignored(self):
        with patch.object(controller, 'inventory', return_value=[]), patch.object(controller.subprocess, 'Popen') as launch:
            controller.start_background('example.widget', 'review-update', 'started')
            controller.start_background('example.widget', 'review-update', 'started')
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(launch.call_args.args[0][-2:], ['review-update', 'example.widget'])
            self.assertTrue(launch.call_args.kwargs['start_new_session'])
            self.assertEqual(launch.call_args.kwargs['stdin'], subprocess.DEVNULL)


if __name__ == '__main__':
    unittest.main()
