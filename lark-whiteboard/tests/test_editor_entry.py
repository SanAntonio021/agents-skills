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
        runner.ensure_document_edit_mode = lambda: switched.append(True) or {
            'value': {'clicked': True, 'menu_option_selected': True}}
        state = runner.enter_editor()
        self.assertTrue(state['entered'])
        self.assertEqual(switched, [True])
        self.assertEqual(runner.calls, ['inspect', 'inspect', 'enter'])
        trace = runner.report['editor_entry']
        self.assertIn({'stage':'document_mode_switch', 'clicked':True,
                       'menu_option_selected':True}, trace)
        self.assertIn({'stage':'native_entry_result', 'can_edit':True,
                       'resources_loaded':True, 'entered':True}, trace)

    def test_mode_probe_and_permission_denial_are_reported(self):
        clock = Clock()
        entered = False
        def observe(op, _clock):
            nonlocal entered
            entered = entered or op['kind'] == 'enter'
            return {'can_edit':False, 'entered':entered}
        runner = self.runner(clock, observe)
        runner.timeout = 5
        runner.ensure_document_edit_mode = lambda: {'value': {
            'clicked':False, 'reason':'DOCUMENT_MODE_CONTROL_UNAVAILABLE', 'count':0}}

        with self.assertRaisesRegex(VerificationError, 'permission is denied'):
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
                runner.enter_editor()

        trace = runner.report['editor_entry']
        self.assertIn({'stage':'document_mode_switch', 'clicked':False,
                       'reason':'DOCUMENT_MODE_CONTROL_UNAVAILABLE', 'count':0}, trace)
        self.assertIn({'stage':'native_entry_result', 'can_edit':False,
                       'resources_loaded':True, 'entered':True}, trace)
        self.assertEqual(runner.calls.count('enter'), 1)
        self.assertGreaterEqual(clock.now, 2)

    def test_permission_update_after_native_entry_is_polled(self):
        clock = Clock()
        entry_invoked = False
        def observe(op, _clock):
            if op['kind'] == 'enter':
                nonlocal entry_invoked
                entry_invoked = True
                return {'can_edit':False, 'entered':True}
            if entry_invoked and clock.now >= 2.25:
                return {'can_edit':True, 'entered':True}
            return {'can_edit':False, 'entered':False}
        runner = self.runner(clock, observe)
        runner.timeout = 5
        runner.ensure_document_edit_mode = lambda: {'value': {
            'clicked':True, 'menu_option_selected':True}}
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            state = runner.enter_editor()
        self.assertTrue(state['can_edit'])
        self.assertTrue(state['entered'])
        self.assertEqual(runner.calls.count('enter'), 1)
        self.assertEqual(clock.now, 2.25)

    def mode_runner(self, responses):
        runner = Runner.__new__(Runner)
        runner.tab = 'tab-1'
        runner.calls = []
        runner.responses = list(responses)
        runner.transport_timeout = lambda timeout: timeout
        runner.require_time = lambda: None

        def call(path, data=None):
            runner.calls.append((path, data))
            if not runner.responses:
                raise AssertionError(f'Unexpected browser call: {path}')
            return runner.responses.pop(0)

        runner.call = call
        return runner

    def test_selects_document_edit_menu_before_native_entry(self):
        runner = self.mode_runner([
            {'value': 'complete'},
            {'value': {'clicked': True, 'text': '编辑', 'x': 120, 'y': 24}},
            {'clicked': True},
            {'value': {'options': [{'text': '编辑 可编辑文档', 'x': 130, 'y': 70}]}},
            {'clicked': True},
        ])

        result = runner.ensure_document_edit_mode()

        self.assertEqual([path.rsplit('/', 1)[-1] for path, _ in runner.calls],
                         ['eval', 'eval', 'click-at', 'eval', 'click-at'])
        self.assertEqual(runner.calls[2][1], {'x': 120, 'y': 24})
        self.assertEqual(runner.calls[4][1], {'x': 130, 'y': 70})
        self.assertTrue(result['value']['menu_option_selected'])
        self.assertEqual(result['value']['menu_option'], '编辑 可编辑文档')
        self.assertEqual(runner.responses, [])

    def test_missing_or_ambiguous_mode_button_does_not_click(self):
        for response in (
            {'value': {'clicked': False, 'reason': 'DOCUMENT_MODE_CONTROL_UNAVAILABLE', 'count': 0}},
            {'value': {'clicked': False, 'reason': 'DOCUMENT_MODE_CONTROL_AMBIGUOUS', 'count': 2}},
            {'value': {'clicked': False, 'reason': 'DOCUMENT_MODE_NOT_READ_MODE', 'text': '阅读'}},
        ):
            with self.subTest(response=response):
                runner = self.mode_runner([{'value': 'complete'}, response])
                result = runner.ensure_document_edit_mode()
                self.assertEqual(len(runner.calls), 2)
                self.assertFalse(result['value']['clicked'])

    def test_ambiguous_menu_or_unconfirmed_click_is_rejected(self):
        prefix = [
            {'value': 'complete'},
            {'value': {'clicked': True, 'text': '编辑', 'x': 120, 'y': 24}},
            {'clicked': True},
        ]
        runner = self.mode_runner(prefix + [
            {'value': {'options': [
                {'text': '编辑 可编辑文档', 'x': 130, 'y': 70},
                {'text': '编辑 可编辑文档', 'x': 130, 'y': 90},
            ]}},
        ])
        with self.assertRaisesRegex(VerificationError, 'ambiguous'):
            runner.ensure_document_edit_mode()
        self.assertEqual(len(runner.calls), 4)

        runner = self.mode_runner([
            {'value': 'complete'},
            {'value': {'clicked': True, 'text': '编辑', 'x': 120, 'y': 24}},
            {'clicked': False},
        ])
        with self.assertRaisesRegex(VerificationError, 'click was not confirmed'):
            runner.ensure_document_edit_mode()
        self.assertEqual(len(runner.calls), 3)

        runner = self.mode_runner([
            {'value': 'complete'},
            {'value': {'clicked': True, 'text': '编辑', 'x': 120, 'y': 24}},
            {'clicked': True},
            {'value': {'options': [{'text': '编辑 可编辑文档', 'x': 130, 'y': 70}]}},
            {'clicked': False},
        ])
        with self.assertRaisesRegex(VerificationError, 'menu selection was not confirmed'):
            runner.ensure_document_edit_mode()
        self.assertEqual(len(runner.calls), 5)

    def test_missing_menu_option_times_out_without_selecting(self):
        clock = Clock()
        runner = self.mode_runner([
            {'value': 'complete'},
            {'value': {'clicked': True, 'text': '编辑', 'x': 120, 'y': 24}},
            {'clicked': True},
            *([{'value': {'options': []}}] * 24),
        ])
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaisesRegex(VerificationError, 'did not appear'):
                runner.ensure_document_edit_mode()
        self.assertEqual(clock.now, 4)
        self.assertEqual(sum(path.endswith('/click-at') for path, _ in runner.calls), 1)

    def test_page_load_timeout_stops_before_mode_click(self):
        clock = Clock()
        runner = self.mode_runner([{'value': 'loading'}] * 40)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaisesRegex(VerificationError, 'did not finish loading'):
                runner.ensure_document_edit_mode()
        self.assertEqual(clock.now, 5)
        self.assertTrue(all(path.endswith('/eval') for path, _ in runner.calls))

    def test_offscreen_menu_gets_one_background_frame_before_selection(self):
        runner = self.mode_runner([
            {'value':'complete'},
            {'value':{'clicked':True,'text':'编辑','x':120,'y':24}},
            {'clicked':True},
            {'value':{'options':[],'offscreen_matches':1}},
            {'value':{'options':[{'text':'编辑 可编辑文档','x':130,'y':70}]}},
            {'clicked':True},
        ])
        captures = []
        runner.screenshot = lambda timeout: captures.append(timeout)
        result = runner.ensure_document_edit_mode()
        self.assertEqual(len(captures), 1)
        self.assertTrue(result['value']['menu_render_capture'])
        self.assertTrue(result['value']['menu_option_selected'])

    def test_offscreen_menu_does_not_recapture_or_extend_deadline(self):
        clock = Clock()
        runner = self.mode_runner([
            {'value':'complete'},
            {'value':{'clicked':True,'text':'编辑','x':120,'y':24}},
            {'clicked':True},
            *([{'value':{'options':[],'offscreen_matches':1}}] * 24),
        ])
        captures = []
        runner.screenshot = lambda timeout: captures.append(timeout)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaisesRegex(VerificationError, 'outside the page viewport'):
                runner.ensure_document_edit_mode()
        self.assertEqual(len(captures), 1)
        self.assertEqual(clock.now, 4)
        self.assertEqual(sum(path.endswith('/click-at') for path, _ in runner.calls), 1)

    def test_late_menu_frame_cannot_select_a_now_visible_option(self):
        clock = Clock()
        runner = self.mode_runner([
            {'value':'complete'},
            {'value':{'clicked':True,'text':'编辑','x':120,'y':24}},
            {'clicked':True},
            {'value':{'options':[],'offscreen_matches':1}},
            {'value':{'options':[{'x':130,'y':70}]}},
        ])
        runner.screenshot = lambda timeout: clock.sleep(4)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            with self.assertRaisesRegex(VerificationError, 'did not appear'):
                runner.ensure_document_edit_mode()
        self.assertEqual(sum(path.endswith('/click-at') for path, _ in runner.calls), 1)

    def test_mode_transport_error_records_failing_stage(self):
        runner = self.mode_runner([])
        def fail(path, data=None):
            raise RuntimeError('probe failed')
        runner.call = fail
        with self.assertRaisesRegex(RuntimeError, 'probe failed') as caught:
            runner.ensure_document_edit_mode()
        self.assertEqual(caught.exception.mode_stage, 'document_ready_state')

    def test_permission_is_required_after_actual_entry(self):
        for value in (False, None):
            clock = Clock()
            entered = False
            def observe(op, _clock):
                nonlocal entered
                entered = entered or op['kind'] == 'enter'
                return {'can_edit':value, 'entered':entered}
            runner = self.runner(clock, observe)
            runner.timeout = 5
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
                with self.assertRaisesRegex(VerificationError, 'permission'):
                    runner.enter_editor()
            self.assertEqual(runner.calls.count('enter'), 1)
            self.assertEqual(clock.now >= 2, value is False)

    def test_already_entered_denied_or_missing_permission_never_reenters(self):
        for value in (False, None):
            clock = Clock()
            runner = self.runner(clock, lambda op,c: {'can_edit':value, 'entered':True})
            runner.timeout = 5
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
                with self.assertRaisesRegex(VerificationError, 'permission'):
                    runner.enter_editor()
            self.assertEqual(runner.calls.count('enter'), 0)
            expected_inspects = 9 if value is False else 1
            self.assertEqual(runner.calls.count('inspect'), expected_inspects)
            self.assertEqual(clock.now >= 2, value is False)

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
