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

    def test_denied_or_missing_permission_never_invokes_entry(self):
        for value in (False, None):
            clock = Clock()
            runner = self.runner(clock, lambda op,c: {'can_edit':value})
            with self.assertRaisesRegex(VerificationError, 'permission'):
                runner.enter_editor()
            self.assertEqual(runner.calls, ['inspect'])

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
