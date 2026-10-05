"""Fault-boundary regressions; these are not live whiteboard acceptance."""
import base64
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, NotReady, VerificationError, projection, main
import test_lifecycle as lifecycle
import test_local_edits as local_edits
import test_native_save as native_save
import test_preview as preview_tests


class Process:
    """An already-created child, including failure while reading its pipes."""
    def __init__(self, error=None):
        self.error = error
        self.args = ['native-cli.exe', 'whiteboard']
        self.returncode = None
        self.pid = 4242
        self.killed = self.waited = False
        self.timeouts = []
        self.output = '{"ok":true}'
        self.error_output = ''
        self.stdout, self.stderr = io.StringIO(), io.StringIO()
        self.failed_once = False

    def communicate(self, timeout=None):
        self.timeouts.append(timeout)
        if self.error is not None and not self.failed_once:
            self.failed_once = True
            raise self.error
        self.returncode = -9 if self.killed else 0
        return (self.output, self.error_output)

    def kill(self):
        self.killed = True
        self.returncode = -9

    def terminate(self):
        self.kill()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.waited = True
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stdout.close()
        self.stderr.close()


class ExecutionContract(unittest.TestCase):
    def runner(self, operations):
        return local_edits.DeleteUndoRunnerTests('runTest').make_runner(operations, curve=None)

    def bare_runner(self, directory):
        runner = Runner.__new__(Runner)
        runner.request = dict(document_url='https://tenant.feishu.cn/docx/DocTest',
                              whiteboard_token='BoardTest', operations=[])
        runner.output, runner.timeout, runner.index = Path(directory), 5, 0
        runner.cli, runner.adapter = 'native-cli.exe', '(request)=>({})'
        runner.proxy = 'http://127.0.0.1:3456'
        runner.token, runner.task, runner.tab = 'memory-only', 'own-task', 'own-tab'
        runner.uncertain = False
        runner.report = dict(status='running', steps=[], pages=[], cleanup_receipts=[])
        return runner

    def assert_unwritten_failure(self, runner):
        self.assertEqual(runner.report['status'], 'unverified')
        self.assertTrue(runner.report.get('failure_phase'))
        steps = runner.report.get('steps', [])
        if steps:
            self.assertTrue(all(s['save_status'] == 'not_written' for s in steps))
            self.assertEqual(steps[-1]['verification_status'], 'failed')
            self.assertTrue(steps[-1]['failure_phase'])
        else:
            self.assertEqual(runner.report.get('save_status'), 'not_written')
            self.assertEqual(runner.report.get('verification_status'), 'failed')
        self.assertFalse(runner.uncertain)

    def connect_runner(self, clock=None, late_read=False):
        """Run the real two-stage connect over an in-memory saved board."""
        op = dict(kind='connect', start_id='a', end_id='b')
        runner = self.runner([op])
        runner.request.update(document_url='https://tenant.feishu.cn/docx/DocTest',
                              whiteboard_token='BoardTest')
        runner.timeout = 3
        raw = local_edits.board()
        runner.append_calls = 0

        def state():
            nodes = projection(raw)
            return dict(nodes=nodes, seq=0, savedSeq=0,
                        native_save=native_save.saved(8 + runner.append_calls),
                        render_alpha={n['id']: dict(border=1, text=1) for n in nodes},
                        line_endpoints={n['id']: dict(start=dict(x=n['x'], y=n['y']),
                            end=dict(x=n['x'] + n['width'], y=n['y'] + n['height']))
                            for n in nodes if n['kind'] == 'connector'},
                        binding_geometry=[], world_geometry={}, object_bounds={})

        def export():
            runner.index += 1
            if late_read and runner.append_calls:
                clock.now = 4
            return copy.deepcopy(raw), 'raw-%03d.json' % runner.index

        def command(args):
            self.assertIn('+update', args)
            runner.append_calls += 1
            filename = args[args.index('--source') + 1].removeprefix('@')
            raw['nodes'].extend(copy.deepcopy(runner.writes[filename]['nodes']))
            return dict(ok=True)

        def editor(op, expected=None):
            runner.events.append(('editor', runner.task, op['kind']))
            if op['kind'] in ('inspect', 'enter'):
                return state()
            self.assertEqual(op['kind'], 'reconnect')
            error = VerificationError('Binding rejected before its content call')
            error.content_write_started = False
            raise error

        runner.export, runner.command, runner.editor = export, command, editor
        runner.hydrate = lambda *args, **kwargs: state()
        return runner

    def test_initial_read_or_load_failure_records_unwritten_phase(self):
        for boundary in ('export', 'open_page', 'hydrate', 'inspect'):
            with self.subTest(boundary=boundary):
                runner = self.runner([dict(kind='text', id='b', text='new')])
                if boundary == 'inspect':
                    original = runner.editor

                    def editor(op, expected=None):
                        if op['kind'] == 'inspect':
                            raise OSError('Initial inspection failed')
                        return original(op, expected)

                    runner.editor = editor
                else:
                    setattr(runner, boundary, lambda *a, **k: (_ for _ in ()).throw(OSError('Initial read failure')))
                with self.assertRaises(OSError):
                    runner.run()
                self.assert_unwritten_failure(runner)
                runner.close()
                self.assertFalse(any(r['requested_action'] == 'release'
                                     for r in runner.report.get('cleanup_receipts', [])))

    def test_next_step_read_failure_keeps_completed_step_and_records_unwritten_step(self):
        for failed_inspection in (1, 2):
            with self.subTest(failed_inspection=failed_inspection):
                runner = self.runner([dict(kind='text', id='b', text='first'),
                                      dict(kind='text', id='a', text='second')])
                original, count = runner.editor, 0

                def editor(op, expected=None):
                    nonlocal count
                    if op['kind'] == 'inspect' and runner.report['steps'] and runner.report['steps'][0]['verification_status'] == 'passed':
                        count += 1
                        if count == failed_inspection:
                            raise OSError('Next-step inspection failed')
                    return original(op, expected)

                runner.editor = editor
                with self.assertRaises(OSError):
                    runner.run()
                first, failed = runner.report['steps']
                self.assertEqual((first['save_status'], first['verification_status']), ('confirmed', 'passed'))
                self.assertEqual((failed['save_status'], failed['verification_status'], failed['failure_phase']),
                                 ('not_written', 'failed', 'preflight'))
                self.assertEqual(runner.report['failure_phase'], 'preflight')
                self.assertFalse(runner.uncertain)

    def test_failed_undo_preflight_finalizes_deferred_delete_verification(self):
        runner = self.runner([dict(kind='delete', ids=['other-line'], delete_ids=['other-line']), dict(kind='undo')])
        original = runner.editor

        def editor(op, expected=None):
            steps = runner.report['steps']
            if op['kind'] == 'inspect' and steps and steps[0]['save_status'] == 'confirmed' and steps[0]['verification_status'] == 'pending':
                raise OSError('Lost inspection before undo')
            return original(op, expected)

        runner.editor = editor
        with self.assertRaises(OSError):
            runner.run()
        deleted, undo = runner.report['steps']
        self.assertEqual((deleted['save_status'], deleted['verification_status']), ('confirmed', 'failed'))
        self.assertTrue(deleted['failure_phase'])
        self.assertEqual((undo['save_status'], undo['verification_status'], undo['failure_phase']),
                         ('not_written', 'failed', 'preflight'))
        self.assertFalse(runner.uncertain)

    def test_append_invalid_payload_is_a_recorded_zero_submission_failure(self):
        for content in ('{"nodes":[]}', '{invalid json'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
                filename.write_text(content, encoding='utf-8')
                with self.assertRaises((ValueError, VerificationError)):
                    runner.append(filename)
                self.assert_unwritten_failure(runner)
                self.assertEqual(runner.report['steps'][0]['failure_phase'], 'preflight')
                self.assertEqual((len(runner.mutations), runner.opens), (0, 0))

    def test_append_prepare_file_failure_closes_unwritten_page(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
            original = runner.write

            def write(name, data):
                if name == 'append-input.json':
                    raise OSError('Local input-file lock')
                return original(name, data)

            runner.write = write
            with self.assertRaises(OSError):
                runner.append(filename)
            self.assert_unwritten_failure(runner)
            self.assertEqual(len(runner.mutations), 0)
            runner.close()
            self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'close')

    def test_first_connection_local_rejection_never_retains_unwritten_page(self):
        for failure in ('locked_endpoint', 'input_file'):
            with self.subTest(failure=failure):
                runner = self.runner([dict(kind='connect', start_id='a', end_id='b')])
                runner.request['whiteboard_token'] = 'BoardTest'
                if failure == 'locked_endpoint':
                    original = runner.export

                    def export():
                        raw, name = original()
                        local_edits.line(raw, 'a')['locked'] = True
                        return raw, name

                    runner.export = export
                else:
                    original = runner.write

                    def write(name, data):
                        if name.startswith('connect-input-'):
                            raise OSError('Local connection input-file lock')
                        return original(name, data)

                    runner.write = write
                with self.assertRaises((OSError, VerificationError)):
                    runner.run()
                self.assert_unwritten_failure(runner)
                runner.close()
                self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'close')

    def test_cli_launch_failure_is_unwritten(self):
        for error in (FileNotFoundError('Missing executable'), PermissionError('Execution denied')):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                runner = self.runner([dict(kind='connect', start_id='a', end_id='b')])
                runner.request['whiteboard_token'] = 'BoardTest'
                runner.cli, runner.output = 'native-cli.exe', Path(directory)
                runner.command = lambda args: Runner.command(runner, args)
                with patch('whiteboard.subprocess.Popen', side_effect=error) as launch, self.assertRaises(OSError):
                    runner.run()
                launch.assert_called_once()
                self.assert_unwritten_failure(runner)
                runner.close()
                self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'close')

    def test_started_cli_pipe_error_or_timeout_stays_unknown_and_reaps_process(self):
        for error in (OSError('Pipe read failed'), subprocess.TimeoutExpired(['cli'], 1)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                runner = self.runner([dict(kind='connect', start_id='a', end_id='b')])
                runner.request['whiteboard_token'] = 'BoardTest'
                runner.cli, runner.output = 'native-cli.exe', Path(directory)
                runner.command = lambda args: Runner.command(runner, args)
                process = Process(error)
                with patch('whiteboard.subprocess.Popen', return_value=process) as launch, self.assertRaises((OSError, subprocess.TimeoutExpired)):
                    runner.run()
                launch.assert_called_once()
                self.assertEqual(runner.report['steps'][0]['save_status'], 'unknown')
                self.assertEqual(runner.report['steps'][0]['verification_status'], 'failed')
                self.assertTrue(runner.uncertain)
                self.assertTrue(process.killed or process.waited)
                runner.close()
                self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'release')

    def test_started_cli_invalid_json_or_error_keeps_started_receipt_and_unknown_save(self):
        for output in ('not JSON', '{"ok":false,"error":{"code":"BAD_REQUEST","message":"Rejected"}}'):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as directory:
                runner = self.runner([dict(kind='connect', start_id='a', end_id='b')])
                runner.request['whiteboard_token'] = 'BoardTest'
                runner.cli, runner.output = 'native-cli.exe', Path(directory)
                runner.command = lambda args: Runner.command(runner, args)
                process = Process()
                process.output = output
                with patch('whiteboard.subprocess.Popen', return_value=process) as launch, self.assertRaises(VerificationError) as caught:
                    runner.run()
                launch.assert_called_once()
                self.assertIs(getattr(caught.exception, 'cli_process_started', None), True)
                self.assertIsNot(getattr(caught.exception, 'content_write_started', None), False)
                self.assertEqual((runner.report['steps'][0]['save_status'], runner.report['steps'][0]['verification_status']), ('unknown', 'failed'))
                self.assertTrue(runner.uncertain)
                receipts = [value for name, value in runner.writes.items() if name.startswith('connect-receipt-')]
                self.assertEqual(len(receipts), 1)
                self.assertIsNot(receipts[0].get('content_write_started'), False)
                runner.close()
                self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'release')

    def test_confirmed_connection_append_survives_binding_prewrite_rejection(self):
        runner = self.connect_runner()
        with self.assertRaises(VerificationError):
            runner.run()
        step = runner.report['steps'][0]
        self.assertEqual(runner.append_calls, 1)
        self.assertEqual((step['save_status'], step['verification_status']), ('confirmed', 'failed'))
        self.assertTrue(step.get('append_id'))
        self.assertFalse(runner.uncertain)
        runner.close()
        self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'close')

    def test_witness_cleanup_and_result_file_errors_preserve_save_and_page_receipts(self):
        helper = native_save.NativeSave('runTest')
        for close_error, result_error in ((True, False), (False, True), (True, True)):
            with self.subTest(close_error=close_error, result_error=result_error), tempfile.TemporaryDirectory() as directory:
                writer = helper.width_runner(directory)
                initialize = helper.reader_initializer(writer, timeout_close=close_error)

                def reader_initializer(reader, *args, **kwargs):
                    initialize(reader, *args, **kwargs)
                    if result_error:
                        def write(name, data):
                            if name == 'result.json':
                                raise OSError('Witness result-file lock')
                        reader.write = write

                with patch.object(Runner, '__init__', reader_initializer):
                    writer.run()
                step = writer.report['steps'][0]
                self.assertEqual((step['save_status'], step['verification_status']), ('confirmed', 'passed'))
                self.assertFalse(writer.uncertain)
                self.assertTrue(any(p['task_id'] == 'reader-task' for p in writer.report['pages']))
                receipts = [r for r in writer.report['cleanup_receipts'] if r['task_id'] == 'reader-task']
                self.assertEqual(len(receipts), 1)
                self.assertEqual(receipts[0]['status'], 'unknown' if close_error else 'confirmed')
                self.assertNotIn('secret', json.dumps(writer.report))
                if result_error:
                    self.assertIn('OSError', json.dumps(step['native_persistence']))

    def test_final_result_file_failure_does_not_override_saved_data_or_page_close(self):
        runner = self.runner([])
        runner.token, runner.task, runner.tab = 'memory-only', 'own-task', 'own-tab'
        runner.report.update(status='verified', steps=[dict(save_status='confirmed', verification_status='passed')])
        runner.write = lambda *a: (_ for _ in ()).throw(OSError('Final result-file lock'))
        runner.close()
        self.assertEqual(runner.report['status'], 'verified')
        self.assertEqual(runner.report['steps'][0]['save_status'], 'confirmed')
        self.assertEqual(runner.report['cleanup_receipts'][0]['status'], 'confirmed')
        self.assertEqual(runner.report.get('report_write_status'), 'failed')

    def test_main_result_file_failure_emits_complete_save_report_to_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = self.runner([dict(kind='text', id='b', text='saved change')])
            runner.request.update(document_url='https://tenant.feishu.cn/docx/DocTest',
                                  whiteboard_token='BoardTest')
            runner.output = Path(directory) / 'run'
            request = Path(directory) / 'request.json'
            request.write_text(json.dumps(runner.request), encoding='utf-8')
            original, output = runner.write, io.StringIO()

            def write(name, data):
                if name == 'result.json':
                    raise OSError('Final result-file lock')
                return original(name, data)

            runner.write = write
            runner.run()
            # Exercise main's final reporting over a genuinely completed fake
            # operation without altering the class allocator used by witnesses.
            runner.run = lambda: None
            arguments = ['whiteboard', '--request', str(request), '--output-dir', str(runner.output),
                         '--proxy-url', 'http://127.0.0.1:3456']
            with patch('whiteboard.Runner', return_value=runner), \
                    patch('sys.argv', arguments), patch('sys.stdout', output):
                code = main()
            summary = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(summary['status'], 'verified')
            self.assertEqual(summary['report']['steps'], runner.report['steps'])
            self.assertEqual((summary['report']['steps'][0]['save_status'], summary['report']['steps'][0]['verification_status']), ('confirmed', 'passed'))
            self.assertEqual(summary['report']['cleanup_receipts'], runner.report['cleanup_receipts'])
            self.assertNotIn('memory-only', output.getvalue())

    def test_witness_startup_exhaustion_does_not_start_a_later_hydrate(self):
        helper, clock = native_save.NativeSave('runTest'), lifecycle.Clock()
        with tempfile.TemporaryDirectory() as directory:
            writer = helper.width_runner(directory)
            initialize = helper.reader_initializer(writer, startup_clock=clock, startup_seconds=2)
            hydrated = []

            def reader_initializer(reader, *args, **kwargs):
                initialize(reader, *args, **kwargs)
                original = reader.hydrate

                def hydrate(*args, **kwargs):
                    hydrated.append(True)
                    return original(*args, **kwargs)

                reader.hydrate = hydrate

            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep), \
                    patch.object(Runner, '__init__', reader_initializer), self.assertRaises(VerificationError):
                writer.run()
            self.assertEqual(hydrated, [])
            self.assertEqual(writer.report['steps'][0]['save_status'], 'unknown')
            self.assertEqual(writer.report['steps'][0]['failure_phase'], 'native_persistence')
            self.assertTrue(writer.uncertain)

    def test_append_preview_entry_failure_does_not_reclassify_data_pass(self):
        with tempfile.TemporaryDirectory() as directory, patch('whiteboard.time.sleep'):
            runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
            original = runner.editor

            def editor(op, expected=None):
                if op['kind'] == 'enter':
                    error = VerificationError('Preview-only entry rejected')
                    error.content_write_started = False
                    raise error
                return original(op, expected)

            runner.editor = editor
            runner.append(filename)
            step = runner.report['steps'][0]
            self.assertEqual((step['save_status'], step['verification_status']), ('confirmed', 'passed'))
            self.assertEqual((runner.report['status'], runner.report['visual_status']), ('verified', 'unavailable'))
            self.assertIsNone(step['failure_phase'])
            self.assertEqual(len(runner.mutations), 1)

    def test_save_does_not_accept_raw_returned_after_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, clock = self.bare_runner(directory), lifecycle.Clock()
            runner.editor = lambda op: dict(nodes=[], seq=0, savedSeq=0, native_save=native_save.saved())

            def export():
                clock.now = 6
                return {'nodes': []}, 'late.json'

            runner.export = export
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep), self.assertRaises(VerificationError):
                runner.settle([])
            self.assertEqual(runner.last_save_deadline, 5)
            self.assertEqual(clock.now, 6)

    def test_hydrate_does_not_read_again_after_inspect_exhausts_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, clock = self.bare_runner(directory), lifecycle.Clock()
            runner.write = lambda *a: None
            reads = []

            def editor(op):
                clock.now = 6
                return dict(nodes=[], seq=0, savedSeq=0, native_save=native_save.saved())

            runner.editor = editor
            runner.export = lambda: reads.append('raw') or ({'nodes': []}, 'raw.json')
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep), self.assertRaises(VerificationError):
                runner.hydrate({'nodes': []})
            self.assertEqual(reads, [])

    def test_append_readback_does_not_accept_late_complete_raw_or_repeat_write(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
            runner.request['capture_preview'] = False
            original, clock = runner.export, lifecycle.Clock()

            def export():
                if runner.index == 0:
                    return original()
                try:
                    value = original()
                except NotReady:
                    value = original()
                clock.now = 4
                return value

            runner.export = export
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep), self.assertRaises(VerificationError):
                runner.append(filename)
            self.assertEqual(len(runner.mutations), 1)
            self.assertEqual((runner.report['steps'][0]['save_status'], runner.report['steps'][0]['verification_status']), ('unknown', 'failed'))
            self.assertTrue(runner.uncertain)

    def test_append_returned_then_read_cli_launch_failure_remains_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, filename = lifecycle.Lifecycle('runTest').append_runner(directory)
            runner.cli = 'native-cli.exe'
            original = runner.export

            def export():
                if not runner.mutations:
                    return original()
                # Failure to start this read does not undo the returned write.
                return Runner.command(runner, ['whiteboard', '+export'])

            runner.export = export
            with patch('whiteboard.subprocess.Popen', side_effect=FileNotFoundError('Read executable unavailable')) as launch, self.assertRaises(FileNotFoundError):
                runner.append(filename)
            launch.assert_called_once()
            self.assertEqual(len(runner.mutations), 1)
            self.assertEqual((runner.report['steps'][0]['save_status'], runner.report['steps'][0]['verification_status']), ('unknown', 'failed'))
            self.assertTrue(runner.uncertain)
            runner.close()
            self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'], 'release')

    def test_connection_readback_does_not_confirm_late_append(self):
        clock = lifecycle.Clock()
        runner = self.connect_runner(clock=clock, late_read=True)
        with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep), self.assertRaises(VerificationError):
            runner.run()
        self.assertEqual(runner.append_calls, 1)
        self.assertEqual((runner.report['steps'][0]['save_status'], runner.report['steps'][0]['verification_status']), ('unknown', 'failed'))
        self.assertTrue(runner.uncertain)

    def test_late_second_native_frame_is_unavailable_without_changing_saved_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, state = preview_tests.Preview('runTest').runner(directory)
            runner.timeout, runner.prefer_native_preview = 3, True
            runner.report.update(status='verified', steps=[dict(save_status='confirmed', verification_status='passed')])
            state['viewport']['rect'] = dict(x=0, y=0, width=16, height=16)
            state['native_save'] = native_save.saved()
            frame, clock, captures = preview_tests.png((4, 4, 12, 12)), lifecycle.Clock(), 0

            def editor(op, expected=None):
                nonlocal captures
                if op['kind'] == 'canvas_preview':
                    captures += 1
                    if captures == 2:
                        clock.now = 4
                    return dict(viewport=copy.deepcopy(state['viewport']),
                                data_url='data:image/png;base64,' + base64.b64encode(frame).decode())
                return copy.deepcopy(state)

            runner.editor = editor
            with patch('whiteboard.time.monotonic', clock.monotonic), patch('whiteboard.time.sleep', clock.sleep):
                runner.observe_saved()
            self.assertEqual(runner.report['visual_status'], 'unavailable')
            self.assertEqual(runner.report['status'], 'verified')
            self.assertEqual(runner.report['steps'][0]['save_status'], 'confirmed')
            self.assertFalse((runner.output / 'preview.png').exists())

    def test_nested_budgets_keep_the_earliest_absolute_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, clock = self.bare_runner(directory), lifecycle.Clock()
            with patch('whiteboard.time.monotonic', clock.monotonic):
                with runner.time_budget(deadline=5):
                    clock.now = 1
                    with runner.time_budget(seconds=100):
                        self.assertEqual(runner.require_time(), 4)
                    clock.now = 2
                    with runner.time_budget(deadline=3):
                        self.assertEqual(runner.require_time(), 1)
                    self.assertEqual(runner.require_time(), 3)
                    clock.now = 5
                    with self.assertRaises(VerificationError):
                        runner.require_time()

    def test_http_and_cli_transports_receive_only_the_remaining_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, clock, process = self.bare_runner(directory), lifecycle.Clock(), Process()
            with patch('whiteboard.time.monotonic', clock.monotonic), runner.time_budget(deadline=5):
                clock.now = 4.5
                with patch('whiteboard.urllib.request.urlopen', return_value=io.BytesIO(b'{"ok":true}')) as request:
                    runner.call('/v2/tasks', {}, auth=False)
                self.assertGreater(request.call_args.kwargs['timeout'], 0)
                self.assertLessEqual(request.call_args.kwargs['timeout'], .5)
                with patch('whiteboard.subprocess.Popen', return_value=process):
                    runner.command(['whiteboard', '+export'])
                self.assertGreater(process.timeouts[0], 0)
                self.assertLessEqual(process.timeouts[0], .5)

    def test_http_chunk_reads_refresh_socket_budget_and_reject_a_late_chunk(self):
        for late in (False, True):
            with self.subTest(late=late), tempfile.TemporaryDirectory() as directory:
                runner, clock, socket_timeouts = self.bare_runner(directory), lifecycle.Clock(), []
                socket = SimpleNamespace(settimeout=lambda value: socket_timeouts.append((clock.now, value)))

                class Response:
                    def __init__(self):
                        self.fp = SimpleNamespace(raw=SimpleNamespace(_sock=socket))
                        self.read_calls, self.closed = 0, False

                    def read1(self, amount):
                        self.read_calls += 1
                        if late:
                            clock.now = 6
                            return b'{"ok":true}'
                        now, chunk = ((1, b'{"ok":'), (3, b'true}'), (4, b''))[self.read_calls - 1]
                        clock.now = now
                        return chunk

                    read = read1

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        self.closed = True

                response = Response()
                with patch('whiteboard.time.monotonic', clock.monotonic), runner.time_budget(deadline=5), \
                        patch('whiteboard.urllib.request.urlopen', return_value=response) as request:
                    if late:
                        with self.assertRaises(VerificationError):
                            runner.call('/v2/tasks', {}, auth=False)
                    else:
                        self.assertEqual(runner.call('/v2/tasks', {}, auth=False), {'ok': True})
                request.assert_called_once()
                self.assertTrue(response.closed)
                self.assertEqual(response.read_calls, 1 if late else 3)
                self.assertEqual(socket_timeouts, [(0, 5)] if late else [(0, 5), (1, 4), (3, 2)])

    def test_expired_budget_starts_no_http_request_or_cli_process(self):
        with tempfile.TemporaryDirectory() as directory:
            runner, clock = self.bare_runner(directory), lifecycle.Clock()
            with patch('whiteboard.time.monotonic', clock.monotonic), runner.time_budget(deadline=5):
                clock.now = 5
                with patch('whiteboard.urllib.request.urlopen') as request, self.assertRaises(VerificationError):
                    runner.call('/v2/tasks', {}, auth=False)
                request.assert_not_called()
                with patch('whiteboard.subprocess.Popen') as launch, self.assertRaises(VerificationError):
                    runner.command(['whiteboard', '+export'])
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
