"""Actual native entry, permission and one absolute loading deadline."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import DeadlineExceeded, Runner, VerificationError
from test_lifecycle import Clock


class EditorEntry(unittest.TestCase):
    def runner(self, clock, observe):
        runner = Runner.__new__(Runner)
        runner.timeout = 3
        runner.calls = []
        runner.captures = []
        runner.screenshot = lambda timeout: runner.captures.append(timeout)
        runner.ensure_document_edit_mode = lambda: {'value': {'clicked': False, 'reason': 'TEST_NO_DOCUMENT_MODE'}}
        def editor(op):
            runner.calls.append(op['kind'])
            return {**dict(can_edit=True, resources_loaded=True, entered=False), **observe(op, clock)}
        runner.editor = editor
        return runner

    def test_entry_is_invoked_once_then_actual_state_is_polled(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {'entered':c.now >= 1})
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            state = runner.enter_editor()
        self.assertTrue(state['entered'])
        self.assertEqual(runner.calls.count('enter'), 1)
        self.assertGreater(runner.calls.count('inspect'), 1)

    def test_no_op_entry_times_out_without_replaying(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {})
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaises(DeadlineExceeded):
                runner.enter_editor()
        self.assertEqual(runner.calls.count('enter'), 1)
        self.assertEqual(clock.now, 3)

    def test_resources_are_observed_before_entry(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {'resources_loaded':c.now >= 1, 'entered':op['kind']=='enter'})
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            runner.enter_editor()
        self.assertEqual(clock.now, 1)
        self.assertEqual(runner.calls[-1], 'enter')

    def test_loading_false_permission_waits_until_resources_are_loaded(self):
        clock = Clock()
        def observe(op,c):
            if c.now < 1:
                return {'can_edit':False, 'resources_loaded':False}
            return {'can_edit':True, 'resources_loaded':True, 'entered':op['kind']=='enter'}
        runner = self.runner(clock, observe)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            state = runner.enter_editor()
        self.assertTrue(state['entered'])
        self.assertEqual(clock.now, 1)
        self.assertEqual(runner.calls.count('enter'), 1)

    def test_loading_false_permission_times_out_without_entry(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {'can_edit':False, 'resources_loaded':False})
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaises(DeadlineExceeded):
                runner.enter_editor()
        self.assertEqual(runner.calls.count('enter'), 0)
        self.assertEqual(clock.now, 3)

    def test_preview_permission_does_not_block_entry(self):
        for value in (False, None):
            clock = Clock()
            runner = self.runner(clock, lambda op,c: {
                'can_edit':True if op['kind']=='enter' else value,
                'entered':op['kind']=='enter'})
            self.assertTrue(runner.enter_editor()['can_edit'])
            self.assertEqual(runner.calls, ['inspect', 'enter'])

    def test_read_mode_is_switched_before_native_entry(self):
        clock = Clock()
        switched = []
        def observe(op, _clock):
            if switched:
                return {'can_edit': True, 'entered': op['kind'] == 'enter'}
            return {'can_edit': False, 'entered': False}
        runner = self.runner(clock, observe)
        runner.ensure_document_edit_mode = lambda: switched.append(True) or {'value': {'clicked': True}}
        state = runner.enter_editor()
        self.assertTrue(state['entered'])
        self.assertEqual(switched, [True])
        self.assertEqual(runner.calls, ['inspect', 'inspect', 'enter'])

    def test_permission_is_required_after_actual_entry(self):
        for value in (False, None):
            clock = Clock()
            runner = self.runner(clock, lambda op,c: {
                'can_edit':value, 'entered':op['kind']=='enter'})
            with self.assertRaisesRegex(VerificationError, 'permission'):
                runner.enter_editor()
            self.assertEqual(runner.calls, ['inspect', 'enter'])

    def test_already_entered_denied_or_missing_permission_never_reenters(self):
        for value in (False, None):
            clock = Clock()
            runner = self.runner(clock, lambda op,c: {'can_edit':value, 'entered':True})
            with self.assertRaisesRegex(VerificationError, 'permission'):
                runner.enter_editor()
            self.assertEqual(runner.calls, ['inspect'])

    def test_one_background_capture_resumes_first_frame(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {
            'resources_loaded':bool(runner.captures), 'entered':op['kind']=='enter'})
        self.assertTrue(runner.enter_editor()['entered'])
        self.assertEqual(len(runner.captures), 1)
        self.assertEqual(runner.calls, ['inspect', 'inspect', 'enter'])

    def test_capture_is_not_repeated_when_loading_stays_pending(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {'resources_loaded':False})
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaises(DeadlineExceeded):
                runner.enter_editor()
        self.assertEqual(len(runner.captures), 1)
        self.assertNotIn('enter', runner.calls)

    def test_late_capture_receipt_is_rejected(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {'resources_loaded':False})
        runner.screenshot = lambda timeout: clock.sleep(3)
        with patch('whiteboard.time.monotonic', clock.monotonic):
            with self.assertRaises(DeadlineExceeded):
                runner.enter_editor()
        self.assertEqual(runner.calls, ['inspect'])

    def test_load_returns_final_entry_state(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {'entered':True})
        runner.hydrate = lambda raw: dict(can_edit=False, resources_loaded=True, entered=False)
        state = runner.load_editor({'nodes':[]}, enter=True)
        self.assertTrue(state['entered'])
        self.assertTrue(state['can_edit'])

    def test_already_entered_does_not_invoke_entry(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {'entered':True})
        runner.enter_editor()
        self.assertEqual(runner.calls, ['inspect'])

    def test_loading_and_entry_share_deadline_and_reject_late_receipt(self):
        for late in (False, True):
            clock = Clock()
            def observe(op,c):
                if late and op['kind']=='enter':
                    c.sleep(2)
                    return {'entered':True}
                return {}
            runner = self.runner(clock, observe)
            def hydrate(raw):
                clock.sleep(2)
                return dict(can_edit=True, resources_loaded=True, entered=False)
            runner.hydrate = hydrate
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
                with self.assertRaises(DeadlineExceeded):
                    runner.load_editor({'nodes':[]}, enter=True)
            self.assertEqual(runner.calls.count('enter'), 1)
            self.assertLessEqual(runner.calls.count('inspect'), 4)

    def test_readonly_load_does_not_require_edit_permission(self):
        clock = Clock()
        runner = self.runner(clock, lambda op,c: {})
        runner.hydrate = lambda raw: {'can_edit':False, 'nodes':[]}
        self.assertFalse(runner.load_editor({'nodes':[]})['can_edit'])
        self.assertEqual(runner.calls, [])


if __name__ == '__main__':
    unittest.main()
