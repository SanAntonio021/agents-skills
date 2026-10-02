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
        state = dict(nodes=[dict(id='a',x=1)],render_alpha={'a':{'border':1}},
                     line_endpoints={},seq=1,savedSeq=1,
                     viewport=dict(rect=dict(x=4,y=4,width=8,height=8),device_pixel_ratio=1))
        runner.editor = lambda op, expected=None: self.assertIn(op['kind'],('inspect','observe')) or copy.deepcopy(state)
        runner.screenshot = lambda: png((4,4,12,12))
        return runner, state

    def test_two_stable_frames_require_human_image_review(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner, _ = self.runner(directory)
            runner.capture_preview()
            self.assertEqual(runner.report['visual_status'],'needs_review')
            self.assertTrue((runner.output/'preview.png').is_file())
            self.assertTrue((runner.output/'visual-feedback.json').is_file())

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
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'), patch('whiteboard.time.monotonic',side_effect=[0,0,13]):
            runner, _ = self.runner(directory)
            runner.screenshot = lambda: png()
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
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'), patch('whiteboard.time.monotonic',side_effect=[0,0,13]):
            runner, state = self.runner(directory)
            state['nodes'] = [dict(id='line',kind='connector',caption_texts=['caption'])]
            state['label_geometry'] = {'line':dict(available=True,screen_rect=dict(x=4,y=4,width=4,height=4))}
            runner.screenshot = lambda: png((8,4,12,12))
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
            def screenshot():
                calls.append('screenshot')
                raise OSError('Transport failure')
            def editor(op, expected=None):
                if op['kind'] == 'canvas_preview':
                    self.assertEqual(expected,state['nodes'])
                    return dict(data_url='data:image/png;base64,'+base64.b64encode(frame).decode())
                self.assertIn(op['kind'],('inspect','observe'))
                return copy.deepcopy(state)
            runner.editor, runner.screenshot = editor, screenshot
            runner.capture_preview()
            self.assertEqual(calls,['screenshot'])
            self.assertEqual(runner.report['preview_source'],'native_canvas')
            self.assertEqual(runner.report['visual_status'],'needs_review')
            self.assertEqual((runner.output/'preview.png').read_bytes(),frame)


if __name__ == '__main__':
    unittest.main()
