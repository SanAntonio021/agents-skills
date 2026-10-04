"""Fault injection for IO acknowledgement; live persistence is checked separately."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, VerificationError
from test_lifecycle import Clock
import test_local_edits


def saved(version=8, **changes):
    value = dict(available=True, signature='b8586b42', initialized=True, applied_version=version,
                 pending=0, ordered_pending=0, processing=False, offline=False,
                 save_state='saved', http_pending=0)
    value.update(changes)
    return value


def fence(ack=True):
    return dict(signature='b8586b42', before_applied_version=8, requires_ack=ack)


class NativeSave(unittest.TestCase):
    def waiting_runner(self, clock, receipt):
        runner = Runner.__new__(Runner)
        runner.timeout = 5
        runner.exports = []
        runner.editor = lambda op: dict(nodes=[], seq=0, savedSeq=0, native_save=receipt(clock.now))
        runner.export = lambda: runner.exports.append(clock.now) or ({'nodes':[]}, 'raw.json')
        return runner

    def wait(self, runner, clock, barrier, minimum_stable_seconds=0):
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
            return runner.settle([], minimum_stable_seconds=minimum_stable_seconds, save_fence=barrier)

    def test_equal_legacy_sequences_and_saved_icon_cannot_skip_debounced_queue(self):
        clock = Clock()
        runner = self.waiting_runner(clock, lambda t: saved(8 if t<2 else 9,
                                                           ordered_pending=1 if t<1 else 0))
        self.wait(runner, clock, fence())
        self.assertEqual(clock.now, 2)
        self.assertEqual(runner.exports, [2])

    def test_multi_transaction_queue_empty_before_ack_still_waits_version(self):
        clock = Clock()
        runner = self.waiting_runner(clock, lambda t: saved(8 if t<3 else 10,
                                                           ordered_pending=2 if t==0 else 0,
                                                           processing=t==1))
        self.wait(runner, clock, fence())
        self.assertEqual(clock.now, 3)
        self.assertEqual(runner.last_save_evidence['native_save']['applied_version'], 10)

    def test_version_advance_does_not_skip_unsent_or_processing_transactions(self):
        for flag in ('pending', 'ordered_pending', 'processing', 'http_pending'):
            with self.subTest(flag=flag):
                clock = Clock()
                changes = lambda t: {flag:bool(t<2) if flag=='processing' else int(t<2)}
                runner = self.waiting_runner(clock, lambda t: saved(9, **changes(t)))
                self.wait(runner, clock, fence())
                self.assertEqual(clock.now, 2)
                self.assertEqual(runner.exports, [2])

    def test_queue_drain_without_this_operation_version_advance_times_out(self):
        clock = Clock()
        runner = self.waiting_runner(clock, lambda t: saved(8))
        with self.assertRaisesRegex(VerificationError, 'did not converge'):
            self.wait(runner, clock, fence())
        self.assertEqual(clock.now, 5)
        self.assertEqual(runner.exports, [])

    def test_stability_resets_on_native_queue_without_extending_deadline(self):
        clock = Clock()
        runner = self.waiting_runner(clock, lambda t: saved(9, ordered_pending=int(t==1)))
        with self.assertRaises(VerificationError):
            self.wait(runner, clock, fence(), minimum_stable_seconds=3)
        self.assertEqual(clock.now, 5)
        self.assertEqual(runner.last_save_deadline, 5)

    def test_unchanged_content_does_not_require_new_ack_but_still_drains_queue(self):
        clock = Clock()
        runner = self.waiting_runner(clock, lambda t: saved(8, ordered_pending=int(t<2)))
        self.wait(runner, clock, fence(False))
        self.assertEqual(clock.now, 2)
        self.assertEqual(runner.last_save_evidence['native_save']['applied_version'], 8)

    def test_invalid_save_interface_or_fence_does_not_export(self):
        for receipt, barrier in ((saved(signature='changed'), fence()),
                                 (saved(), dict(fence(), before_applied_version=True)),
                                 (saved(), dict(fence(), requires_ack=1))):
            with self.subTest(receipt=receipt, barrier=barrier):
                clock = Clock()
                runner = self.waiting_runner(clock, lambda t: receipt)
                with self.assertRaises(VerificationError):
                    self.wait(runner, clock, barrier)
                self.assertEqual(runner.exports, [])

    def width_runner(self, directory):
        op = dict(kind='caption_format', id='line', width=200)
        runner = test_local_edits.DeleteUndoRunnerTests('runTest').make_runner([op], curve=None)
        runner.request.update(document_url='https://tenant.feishu.cn/docx/DocTest', whiteboard_token='BoardTest')
        runner.output, runner.proxy = Path(directory), 'http://127.0.0.1:3456'
        old_editor, width = runner.editor, 180
        def editor(operation, expected=None):
            nonlocal width
            if operation['kind']=='caption_format':
                width = operation['width']
                value = editor({'kind':'inspect'})
                value.update(content_write_started=True, save_fence=fence())
                return value
            value = old_editor(operation, expected)
            next(n for n in value['nodes'] if n['id']=='line').update(caption_width=width, caption_size_mode=1)
            value['native_save'] = saved(9 if width==200 else 8)
            return value
        runner.editor = editor
        runner.hydrate = lambda raw: editor({'kind':'inspect'})
        return runner

    def reader_initializer(self, writer, width=200, timeout_close=False, late_clock=None, startup_clock=None, startup_seconds=0):
        def initialize(reader, request, output, proxy, timeout):
            reader.output = Path(output)
            reader.timeout = timeout
            reader.request = request
            reader.uncertain = False
            reader.token, reader.task, reader.tab = 'secret', 'reader-task', 'reader-tab'
            reader.report = dict(status='running', pages=[dict(task_id=reader.task,tab_id=reader.tab)], cleanup_receipts=[])
            def open_page():
                if startup_clock is not None:
                    startup_clock.now += startup_seconds
            reader.open_page = open_page
            def hydrate(raw, minimum_applied_version=None):
                self.assertEqual(minimum_applied_version, 9)
                if startup_clock is not None:
                    self.assertEqual(reader.timeout, writer.last_save_deadline-startup_clock.now)
                value = copy.deepcopy(writer.last_saved_state)
                next(n for n in value['nodes'] if n['id']=='line')['caption_width'] = width
                if late_clock is not None:
                    late_clock.now = writer.last_save_deadline
                return value
            reader.hydrate = hydrate
            reader.write = lambda *args: None
            def call(path, data):
                if timeout_close:
                    raise TimeoutError('Read-only witness close timed out')
                return dict(taskId=reader.task,state='completed',keep=False,closed=1,released=0)
            reader.call = call
        return initialize

    def test_old_width_on_fresh_witness_remains_unknown_and_retains_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = self.width_runner(directory)
            with patch.object(Runner, '__init__', self.reader_initializer(writer, width=180)), self.assertRaisesRegex(VerificationError, 'save remains unknown'):
                writer.run()
            step = writer.report['steps'][0]
            self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']), ('unknown','failed','native_persistence'))
            self.assertTrue(writer.uncertain)
            self.assertEqual(writer.report['cleanup_receipts'][0]['page_status'], 'closed')
            writer.close()
            self.assertEqual(writer.report['cleanup_receipts'][-1]['page_status'], 'released')

    def test_witness_close_timeout_does_not_change_confirmed_save_fact(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = self.width_runner(directory)
            with patch.object(Runner, '__init__', self.reader_initializer(writer, timeout_close=True)):
                writer.run()
            step = writer.report['steps'][0]
            self.assertEqual((step['save_status'],step['verification_status']), ('confirmed','passed'))
            self.assertFalse(writer.uncertain)
            self.assertEqual(writer.report['cleanup_receipts'][0]['status'], 'unknown')
            self.assertNotIn('secret', str(writer.report))

    def test_native_witness_uses_remaining_original_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = self.width_runner(directory)
            clock = Clock()
            with patch('whiteboard.time.monotonic',clock.monotonic), patch('whiteboard.time.sleep',clock.sleep), \
                    patch.object(Runner,'__init__',self.reader_initializer(writer,late_clock=clock)), \
                    self.assertRaisesRegex(VerificationError,'exceeded the save deadline'):
                writer.run()
            self.assertEqual(clock.now, 1)
            self.assertEqual(writer.report['steps'][0]['save_status'], 'unknown')
            self.assertEqual(writer.report['steps'][0]['failure_phase'], 'native_persistence')

    def test_witness_startup_time_is_subtracted_before_hydrate(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = self.width_runner(directory)
            clock = Clock()
            with patch('whiteboard.time.monotonic',clock.monotonic), patch('whiteboard.time.sleep',clock.sleep), \
                    patch.object(Runner,'__init__',self.reader_initializer(writer,startup_clock=clock,startup_seconds=.75)):
                writer.run()
            self.assertEqual(clock.now,.75)
            self.assertEqual(writer.report['steps'][0]['save_status'],'confirmed')

    def test_witness_startup_exhaustion_stops_before_hydrate(self):
        with tempfile.TemporaryDirectory() as directory:
            writer = self.width_runner(directory)
            clock = Clock()
            with patch('whiteboard.time.monotonic',clock.monotonic), patch('whiteboard.time.sleep',clock.sleep), \
                    patch.object(Runner,'__init__',self.reader_initializer(writer,startup_clock=clock,startup_seconds=2)), \
                    self.assertRaisesRegex(VerificationError,'exceeded the save deadline'):
                writer.run()
            self.assertEqual(writer.report['steps'][0]['save_status'],'unknown')
            self.assertTrue(writer.uncertain)


if __name__ == '__main__':
    unittest.main()
