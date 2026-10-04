"""Saved observation must reject white frames and must not replay an edit."""
import copy
import base64
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, VerificationError, png_has_board_ink


def png(dark=None, filter_type=0):
    width, height, channels = 16, 16, 3
    prior, rows = bytearray(width*channels), []
    for y in range(height):
        row = bytearray([255]*(width*channels))
        if dark and dark[1] <= y < dark[3]:
            for x in range(dark[0], dark[2]):
                row[x*channels:x*channels+3] = b'\x20\x30\x40'
        encoded = bytearray(row)
        for i in range(len(row)):
            a = row[i-channels] if i >= channels else 0
            b = prior[i]
            c = prior[i-channels] if i >= channels else 0
            p = a+b-c
            predictor = (0, a, b, (a+b)//2, min((a,b,c),key=lambda v:abs(p-v)))[filter_type]
            encoded[i] = (row[i]-predictor) & 255
        rows.append(bytes([filter_type])+encoded)
        prior = row
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))


class Preview(unittest.TestCase):
    def test_white_board_and_surrounding_ui_do_not_count_as_rendered(self):
        rect = dict(x=4,y=4,width=8,height=8)
        self.assertFalse(png_has_board_ink(png(),rect))
        self.assertFalse(png_has_board_ink(png((0,0,4,16)),rect))
        self.assertFalse(png_has_board_ink(b'not png',rect))

    def test_all_png_filters_and_device_scale_keep_real_board_ink(self):
        for filter_type in range(5):
            with self.subTest(filter_type=filter_type):
                self.assertTrue(png_has_board_ink(png((4,4,12,12),filter_type),dict(x=2,y=2,width=4,height=4),2))

    def runner(self, directory):
        runner = object.__new__(Runner)
        runner.output, runner.timeout, runner.report, runner.request = Path(directory), 45, {}, {}
        # Exercise the browser-first fallback branches separately from the
        # production native preference, without altering returned page data.
        runner.prefer_native_preview = False
        state = dict(nodes=[dict(id='a',x=1)],render_alpha={'a':{'border':1}},
                     line_endpoints={},seq=1,savedSeq=1,
                     viewport=dict(rect=dict(x=4,y=4,width=8,height=8),device_pixel_ratio=1))
        runner.editor = lambda op, expected=None: self.assertIn(op['kind'],('inspect','observe')) or copy.deepcopy(state)
        runner.screenshot = lambda **kwargs: png((4,4,12,12))
        return runner, state

    def test_two_stable_frames_require_human_image_review(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner, _ = self.runner(directory)
            runner.capture_preview()
            self.assertEqual(runner.report['visual_status'],'needs_review')
            self.assertTrue((runner.output/'preview.png').is_file())
            self.assertTrue((runner.output/'visual-feedback.json').is_file())

    def test_native_preference_avoids_browser_capture_lock(self):
        with tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
            runner,state = self.runner(directory)
            runner.prefer_native_preview = True
            state['viewport']['rect'] = dict(x=0,y=0,width=16,height=16)
            frame = png((4,4,12,12))
            def editor(op,expected=None):
                if op['kind']=='canvas_preview':
                    return dict(viewport=copy.deepcopy(state['viewport']),
                                data_url='data:image/png;base64,'+base64.b64encode(frame).decode())
                return copy.deepcopy(state)
            runner.editor = editor
            runner.screenshot = lambda **kwargs: self.fail('Native preference must not start browser capture')
            runner.capture_preview()
            self.assertEqual(runner.report['preview_source'],'native_canvas')
            self.assertEqual(runner.report['visual_status'],'needs_review')
            self.assertEqual((runner.output/'preview.png').read_bytes(),frame)

    def test_observation_drift_stops_without_edit_replay(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner, state = self.runner(directory)
            changed = copy.deepcopy(state)
            changed['nodes'][0]['x'] = 50
            calls = []
            runner.editor = lambda op, expected=None: calls.append(op) or (state if op['kind']=='observe' or len(calls)==1 else changed)
            with self.assertRaisesRegex(VerificationError,'Board changed'):
                runner.capture_preview()
            self.assertEqual(calls,[{'kind':'inspect'},{'kind':'observe'},{'kind':'inspect'}])
            self.assertFalse((runner.output/'preview.png').exists())

    def test_white_transition_timeout_is_unavailable_not_visual_pass(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'), patch('whiteboard.time.monotonic',side_effect=[0,0,0,21]):
            runner, _ = self.runner(directory)
            runner.screenshot = lambda **kwargs: png()
            runner.capture_preview()
            self.assertEqual(runner.report['visual_status'],'unavailable')
            self.assertFalse((runner.output/'preview.png').exists())

    def test_offscreen_edited_label_is_not_a_reviewable_preview(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner, state = self.runner(directory)
            state['nodes'] = [dict(id='line',kind='connector',caption_texts=['caption'])]
            state['label_geometry'] = {'line':dict(available=True,screen_rect=dict(x=20,y=4,width=8,height=8))}
            runner.capture_preview()
            self.assertEqual(runner.report['visual_status'],'unavailable')
            self.assertIn('outside',runner.report['visual_reason'])
            self.assertFalse((runner.output/'preview.png').exists())

    def test_preview_exception_preserves_saved_data_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, _ = self.runner(directory)
            runner.report = dict(status='verified',steps=[dict(after_raw='saved.json')])
            def failure():
                raise VerificationError('Screenshot unavailable')
            runner.capture_preview = failure
            runner.observe_saved()
            self.assertEqual(runner.report['status'],'verified')
            self.assertEqual(runner.report['steps'][0]['after_raw'],'saved.json')
            self.assertEqual(runner.report['visual_status'],'unavailable')

    def test_visible_ui_or_other_objects_cannot_replace_target_label_pixels(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'), patch('whiteboard.time.monotonic',side_effect=[0,0,0,21]):
            runner, state = self.runner(directory)
            state['nodes'] = [dict(id='line',kind='connector',caption_texts=['caption'])]
            state['label_geometry'] = {'line':dict(available=True,screen_rect=dict(x=4,y=4,width=4,height=4))}
            runner.screenshot = lambda **kwargs: png((8,4,12,12))
            runner.capture_preview()
            self.assertEqual(runner.report['visual_status'],'unavailable')
            self.assertFalse((runner.output/'preview.png').exists())

    def test_transport_failure_uses_original_native_canvas_with_correct_origin(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner, state = self.runner(directory)
            state['nodes'] = [dict(id='line',kind='connector',caption_texts=['caption'])]
            state['viewport']['rect'] = dict(x=10,y=20,width=16,height=16)
            state['label_geometry'] = {'line':dict(available=True,screen_rect=dict(x=14,y=24,width=8,height=8))}
            frame = png((4,4,12,12))
            calls = []
            def screenshot(**kwargs):
                calls.append('screenshot')
                self.assertGreater(kwargs['timeout'],0)
                self.assertLessEqual(kwargs['timeout'],5)
                raise OSError('Transport failure')
            def editor(op, expected=None):
                if op['kind'] == 'canvas_preview':
                    self.assertEqual(expected,state['nodes'])
                    return dict(data_url='data:image/png;base64,'+base64.b64encode(frame).decode(), viewport=copy.deepcopy(state['viewport']))
                self.assertIn(op['kind'],('inspect','observe'))
                return copy.deepcopy(state)
            runner.editor, runner.screenshot = editor, screenshot
            runner.capture_preview()
            self.assertEqual(calls,['screenshot'])
            self.assertEqual(runner.report['preview_source'],'native_canvas')
            self.assertEqual(runner.report['visual_status'],'needs_review')
            self.assertEqual((runner.output/'preview.png').read_bytes(),frame)

    def test_hidden_content_save_sequence_change_stops_after_screenshot(self):
        with tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
            runner,state = self.runner(directory)
            inspections = 0
            def editor(op,expected=None):
                nonlocal inspections
                result = copy.deepcopy(state)
                if op['kind']=='inspect':
                    inspections += 1
                    if inspections>=3:
                        result.update(seq=2,savedSeq=2)
                return result
            runner.editor = editor
            with self.assertRaisesRegex(VerificationError,'Board changed'):
                runner.capture_preview()
            self.assertFalse((runner.output/'preview.png').exists())

    def native_saved_state(self, state):
        state.update(seq=0,savedSeq=0,native_save=dict(available=True,signature='b8586b42',
                     initialized=True,applied_version=10,pending=0,ordered_pending=0,
                     processing=False,offline=False,save_state='saved',http_pending=0))

    def test_unchanged_nodes_with_native_version_change_stop_before_or_after_frame(self):
        for changed_inspection in (2,3):
            with self.subTest(changed_inspection=changed_inspection),tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
                runner,state = self.runner(directory)
                self.native_saved_state(state)
                inspections,captures = 0,[]
                def editor(op,expected=None):
                    nonlocal inspections
                    result = copy.deepcopy(state)
                    if op['kind']=='inspect':
                        inspections += 1
                        if inspections>=changed_inspection:
                            result['native_save']['applied_version'] = 11
                    return result
                runner.editor = editor
                runner.screenshot = lambda **kwargs: captures.append('frame') or png((4,4,12,12))
                with self.assertRaisesRegex(VerificationError,'Board changed'):
                    runner.capture_preview()
                self.assertEqual(inspections,changed_inspection)
                self.assertEqual(len(captures),changed_inspection-2)
                self.assertFalse((runner.output/'preview.png').exists())

    def test_zero_legacy_sequence_with_pending_native_io_stops_before_or_after_frame(self):
        for changed_inspection in (2,3):
            with self.subTest(changed_inspection=changed_inspection),tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
                runner,state = self.runner(directory)
                self.native_saved_state(state)
                inspections,captures = 0,[]
                def editor(op,expected=None):
                    nonlocal inspections
                    result = copy.deepcopy(state)
                    if op['kind']=='inspect':
                        inspections += 1
                        if inspections>=changed_inspection:
                            result['native_save']['ordered_pending'] = 1
                    return result
                runner.editor = editor
                runner.screenshot = lambda **kwargs: captures.append('frame') or png((4,4,12,12))
                with self.assertRaisesRegex(VerificationError,'Board changed'):
                    runner.capture_preview()
                self.assertEqual(inspections,changed_inspection)
                self.assertEqual(len(captures),changed_inspection-2)
                self.assertFalse((runner.output/'preview.png').exists())

    def test_unsaved_native_baseline_stops_before_observe(self):
        with tempfile.TemporaryDirectory() as directory:
            runner,state = self.runner(directory)
            self.native_saved_state(state)
            state['native_save']['pending'] = 1
            calls = []
            runner.editor = lambda op,expected=None: calls.append(op['kind']) or copy.deepcopy(state)
            runner.screenshot = lambda **kwargs: self.fail('Unsaved baseline must not capture')
            with self.assertRaisesRegex(VerificationError,'not saved'):
                runner.capture_preview()
            self.assertEqual(calls,['inspect'])
            self.assertFalse((runner.output/'preview.png').exists())

    def test_unstable_browser_frames_use_bounded_real_canvas_readback(self):
        with tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
            runner,state = self.runner(directory)
            state['viewport']['rect'] = dict(x=0,y=0,width=16,height=16)
            frames = iter([png((2,2,12,12)),png((3,2,12,12)),png((4,2,12,12))])
            calls = []
            def screenshot(**kwargs):
                calls.append('browser')
                return next(frames)
            frame = png((4,4,12,12))
            def editor(op,expected=None):
                if op['kind']=='canvas_preview':
                    calls.append('canvas')
                    return dict(viewport=copy.deepcopy(state['viewport']),
                                data_url='data:image/png;base64,'+base64.b64encode(frame).decode())
                return copy.deepcopy(state)
            runner.screenshot,runner.editor = screenshot,editor
            runner.capture_preview()
            self.assertEqual(calls,['browser']*3+['canvas']*2)
            self.assertEqual(runner.report['preview_source'],'native_canvas')
            self.assertEqual(runner.report['preview_fallback_reason'],'browser_unstable_frames')
            self.assertEqual((runner.output/'preview.png').read_bytes(),frame)

    def test_viewport_and_dpr_change_resamples_before_matching_frames(self):
        with tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
            runner,state = self.runner(directory)
            inspections,screenshots = 0,0
            def editor(op,expected=None):
                nonlocal inspections
                result = copy.deepcopy(state)
                if op['kind']=='inspect':
                    inspections += 1
                    if inspections>=3:
                        result['viewport']['device_pixel_ratio'] = 1.01
                return result
            def screenshot(**kwargs):
                nonlocal screenshots
                screenshots += 1
                return png((4,4,12,12))
            runner.editor,runner.screenshot = editor,screenshot
            runner.capture_preview()
            self.assertEqual(screenshots,3)
            feedback = __import__('json').loads((runner.output/'visual-feedback.json').read_text(encoding='utf-8'))
            self.assertEqual(feedback['viewport']['device_pixel_ratio'],1.01)

    def test_native_canvas_changed_viewport_is_not_cropped_with_old_geometry(self):
        with tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'),patch('whiteboard.time.monotonic',side_effect=[0,0,0,21]):
            runner,state = self.runner(directory)
            runner.screenshot = lambda **kwargs: (_ for _ in ()).throw(OSError('Screenshot transport'))
            def editor(op,expected=None):
                if op['kind']=='canvas_preview':
                    viewport = copy.deepcopy(state['viewport'])
                    viewport['device_pixel_ratio'] = 1.01
                    return dict(viewport=viewport,data_url='data:image/png;base64,'+base64.b64encode(png((4,4,12,12))).decode())
                return copy.deepcopy(state)
            runner.editor = editor
            runner.capture_preview()
            self.assertEqual(runner.report['visual_status'],'unavailable')
            self.assertFalse((runner.output/'preview.png').exists())


if __name__ == '__main__':
    unittest.main()
