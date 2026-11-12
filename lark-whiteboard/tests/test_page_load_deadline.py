"""Slow background page loads use the shared loading deadline, not fixed short waits."""
import io
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, VerificationError
from test_lifecycle import Clock


def proxy_error(status, code):
    body = ('{"error":{"code":"%s","message":"test"}}' % code).encode()
    return urllib.error.HTTPError('http://127.0.0.1/wait', status, 'error', {}, io.BytesIO(body))


class PageLoadDeadline(unittest.TestCase):
    def open_runner(self, clock, slow_waits, error=None):
        """Runner whose first `slow_waits` selector waits end with the given proxy error."""
        runner = Runner.__new__(Runner)
        runner.request = dict(document_url='https://test.feishu.cn/docx/DocTest', whiteboard_token='BoardTest',
                              section_id='SectionTest', block_id='BlockTest', operations=[])
        runner.report = {'pages': [], 'document_routes': []}
        runner.timeout = 120
        runner.verify_document = lambda url: dict(docx_token='DocTest', whiteboard_token='BoardTest', block_id='BlockTest')
        runner.calls = []
        runner.pending = slow_waits

        def call(path, data=None, auth=True):
            runner.calls.append((path, data))
            if path == '/v2/tasks':
                return {'taskToken': 'private', 'taskId': 'task'}
            if path == '/v2/tabs':
                return {'targetId': 'tab'}
            if path.endswith('/wait'):
                if runner.pending:
                    runner.pending -= 1
                    clock.sleep(data['timeoutMs'] / 1000)
                    raise error or proxy_error(408, 'WAIT_TIMEOUT')
                return {'ok': True, 'condition': 'selector'}
            if path.endswith('/eval'):
                return {'value': {'origin': 'https://test.feishu.cn', 'href': 'https://test.feishu.cn/docx/DocTest'}}
            return {}

        runner.call = call
        return runner

    def waits(self, runner):
        return [data for path, data in runner.calls if path.endswith('/wait')]

    def test_slow_outline_is_awaited_within_the_shared_deadline(self):
        clock = Clock()
        runner = self.open_runner(clock, slow_waits=4)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            runner.open_page()
        page = runner.report['pages'][0]
        self.assertEqual(page['open_status'], 'ready')
        self.assertEqual(page['load_wait_attempts'], {'outline_link': 5})
        self.assertEqual(clock.now, 60)
        self.assertEqual(len(self.waits(runner)), 7)
        self.assertTrue(all(data['timeoutMs'] <= 15000 for data in self.waits(runner)))
        self.assertEqual(sum(path.endswith('/click') for path, _ in runner.calls), 1)

    def test_missing_element_stops_at_the_shared_deadline_before_clicking(self):
        clock = Clock()
        runner = self.open_runner(clock, slow_waits=1000)
        runner.timeout = 40
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaisesRegex(VerificationError, 'did not appear before the loading deadline: outline_link'):
                runner.open_page()
        self.assertEqual(clock.now, 40)
        self.assertEqual([data['timeoutMs'] for data in self.waits(runner)], [15000, 15000, 10000])
        self.assertFalse(any(path.endswith('/click') for path, _ in runner.calls))
        self.assertNotEqual(runner.report['pages'][0]['open_status'], 'ready')

    def test_other_proxy_errors_are_not_retried(self):
        for error in (proxy_error(409, 'WAIT_CANCELLED'), proxy_error(408, 'OTHER_CODE'), proxy_error(504, 'UNKNOWN_RESULT')):
            clock = Clock()
            runner = self.open_runner(clock, slow_waits=1, error=error)
            with self.subTest(code=error.code), patch('whiteboard.time.monotonic', clock.monotonic), \
                    patch('whiteboard.time.sleep', clock.sleep):
                with self.assertRaises(urllib.error.HTTPError):
                    runner.open_page()
                self.assertEqual(len(self.waits(runner)), 1)

    def test_without_a_shared_deadline_the_single_wait_is_kept(self):
        clock = Clock()
        runner = self.open_runner(clock, slow_waits=1)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaises(urllib.error.HTTPError):
                runner._open_page()
        self.assertEqual([data['timeoutMs'] for data in self.waits(runner)], [15000])

    def mode_runner(self, responses, deadline):
        runner = Runner.__new__(Runner)
        runner.tab = 'tab-1'
        runner.calls = []
        runner.responses = list(responses)
        runner.deadline = deadline

        def call(path, data=None):
            runner.calls.append((path, data))
            if not runner.responses:
                raise AssertionError(f'Unexpected browser call: {path}')
            return runner.responses.pop(0)

        runner.call = call
        return runner

    def test_ready_state_is_awaited_within_the_shared_deadline(self):
        clock = Clock()
        runner = self.mode_runner([{'value': 'interactive'}] * 150 + [
            {'value': 'complete'},
            {'value': {'clicked': False, 'reason': 'DOCUMENT_MODE_CONTROL_UNAVAILABLE', 'count': 0}},
        ], deadline=60)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            mode = runner.ensure_document_edit_mode()
        self.assertEqual(mode['value']['reason'], 'DOCUMENT_MODE_CONTROL_UNAVAILABLE')
        self.assertAlmostEqual(clock.now, 30)
        self.assertEqual(mode['value']['ready_wait_ms'], 30000)
        self.assertFalse(any(path.endswith('/click-at') for path, _ in runner.calls))

    def test_ready_state_timeout_at_the_shared_deadline_stops_before_mode_click(self):
        clock = Clock()
        runner = self.mode_runner([{'value': 'loading'}] * 100, deadline=12)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaisesRegex(VerificationError, 'did not finish loading'):
                runner.ensure_document_edit_mode()
        self.assertAlmostEqual(clock.now, 12)
        self.assertTrue(all(path.endswith('/eval') for path, _ in runner.calls))


if __name__ == '__main__':
    unittest.main()
