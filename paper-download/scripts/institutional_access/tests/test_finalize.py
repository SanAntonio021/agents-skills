"""Download finalization boundaries against the actual shared native program."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SHARED = Path(__file__).resolve().parents[4] / 'zotero-library'
sys.path.insert(0, str(SHARED / 'tests'))
from test_execution import Fixture
from institutional_access.browser import BrowserError
from institutional_access.cli import OperationError, complete
from institutional_access.finalize import finalize
from institutional_access.session_store import FileSessionStore


class ClosureClient:
    def __init__(self, fail=False):
        self.state = 'active'
        self.calls = 0
        self.fail = fail

    def task(self):
        return {'state': self.state}

    def complete(self):
        self.calls += 1
        if self.fail:
            raise BrowserError('NETWORK', 'Isolated closure failure')
        self.state = 'completed'


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.f = Fixture(self.root)
        self.f.article_pdf()
        self.env = patch.dict(os.environ, {'PAPER_DOWNLOAD_TEST_MODE': '1',
            'PAPER_DOWNLOAD_TEST_STATE_DIR': str(self.root / 'sessions')})
        self.env.start()
        self.sessions = FileSessionStore(self.root / 'sessions')
        self.sessions.write('fixture', {'taskId': 'fixture-task',
            'taskToken': 'synthetic-browser-credential', 'targetId': 'fixture-tab',
            'doi': '10.1234/fixture', 'provider': 'ieee',
            'requestedArticle': 'https://ieeexplore.ieee.org/document/1234567/',
            'stage': 'downloaded_identity_verified',
            'path': str(self.f.pdf),
            'validation': {'sha256': hashlib.sha256(self.f.pdf.read_bytes()).hexdigest()}})
        self.request = self.f.request()
        self.request_path = self.root / 'request.json'
        self.request_path.write_text(json.dumps(self.request), encoding='utf-8')
        self.args = argparse.Namespace(session='fixture', request=str(self.request_path),
            profile=str(self.f.profile), base_url=self.f.base, timeout=2,
            state_dir=str(self.f.store.root), policy=None)
        self.record_path = self.root / 'sessions/finalizations/fixture.json'

    def tearDown(self):
        self.env.stop()
        self.f.close()
        self.tmp.cleanup()

    def imports(self):
        return sum(x['event'] == 'import' for x in self.f.control()['events'])

    def test_close_retry_skips_archive_and_preserves_nonsecret_receipt(self):
        bad = ClosureClient(fail=True)
        with patch('institutional_access.cli.browser_for_session', return_value=bad):
            with self.assertRaises(BrowserError):
                finalize(self.args)
        self.assertEqual(json.loads(self.record_path.read_text())['stage'], 'archive_completed_closure_pending')
        self.assertIsNotNone(self.sessions.read('fixture'))
        with patch('zotero_library.operations.Executor.run', side_effect=AssertionError('archive replay')), \
             patch('institutional_access.cli.browser_for_session', return_value=ClosureClient()):
            result = finalize(self.args)
        self.assertEqual(result['stage'], 'completed')
        self.assertEqual(self.imports(), 1)
        self.assertIsNone(self.sessions.read('fixture'))
        self.assertNotIn('synthetic-browser-credential', self.record_path.read_text())
        self.assertNotIn('synthetic-fixture-credential', self.record_path.read_text())
        with patch('institutional_access.cli.browser_for_session', side_effect=AssertionError('closure replay')):
            self.assertEqual(finalize(self.args)['stage'], 'completed')

    def test_crash_before_final_receipt_retains_session_and_never_rearchives(self):
        original = os.replace
        calls = []
        def replace(source, destination):
            if Path(destination) == self.record_path:
                calls.append(1)
                if len(calls) == 3:
                    raise OSError('isolated receipt commit failure')
            return original(source, destination)
        client = ClosureClient()
        with patch('institutional_access.finalize.os.replace', side_effect=replace), \
             patch('institutional_access.cli.browser_for_session', return_value=client):
            with self.assertRaisesRegex(OperationError, 'finalization_receipt_or_request_invalid'):
                finalize(self.args)
        self.assertIsNotNone(self.sessions.read('fixture'))
        self.assertEqual(json.loads(self.record_path.read_text())['stage'], 'archive_completed_closure_pending')
        with patch('zotero_library.operations.Executor.run', side_effect=AssertionError('archive replay')), \
             patch('institutional_access.cli.browser_for_session', return_value=client):
            self.assertEqual(finalize(self.args)['stage'], 'completed')
        self.assertEqual(client.calls, 1)
        self.assertEqual(self.imports(), 1)

    def test_archive_failure_does_not_close_and_resume_only_fills_missing_pdf(self):
        self.f.control(config={'failImport': 1})
        with patch('institutional_access.cli.browser_for_session', side_effect=AssertionError('premature closure')):
            result = finalize(self.args)
        self.assertEqual(result['stage'], 'archive_pending')
        self.assertEqual(result['archive']['state'], 'failed')
        self.assertEqual(self.f.executor().resume(result['archive']['operation_id'])['state'], 'completed')
        with patch('institutional_access.cli.browser_for_session', return_value=ClosureClient()):
            self.assertEqual(finalize(self.args)['stage'], 'completed')
        self.assertEqual(self.imports(), 1)

    def test_doi_and_file_mismatch_rejected_before_write(self):
        altered = copy.deepcopy(self.request)
        altered['identity']['doi'] = '10.1234/other'
        self.request_path.write_text(json.dumps(altered))
        with self.assertRaisesRegex(OperationError, 'archive DOI differs'):
            finalize(self.args)
        self.request_path.write_text(json.dumps(self.request))
        self.f.pdf.write_bytes(self.f.pdf.read_bytes() + b'\nchanged')
        with self.assertRaisesRegex(OperationError, 'pdf_hash_mismatch'):
            finalize(self.args)
        self.assertEqual(self.f.control()['events'], [])

    def test_completed_session_rejects_different_request(self):
        with patch('institutional_access.cli.browser_for_session', return_value=ClosureClient()):
            self.assertEqual(finalize(self.args)['stage'], 'completed')
        self.request['identity']['evidence'].append('Changed request')
        self.request_path.write_text(json.dumps(self.request))
        with self.assertRaisesRegex(OperationError, 'finalize request differs'):
            finalize(self.args)
        self.assertEqual(self.imports(), 1)

    def test_active_session_cannot_finalize_an_unrelated_local_pdf(self):
        session = self.sessions.read('fixture')
        session['stage'] = 'institutional_access'
        session.pop('validation')
        session.pop('path')
        self.sessions.write('fixture', session)
        with patch('institutional_access.cli.browser_for_session', side_effect=AssertionError('premature closure')):
            with self.assertRaisesRegex(OperationError, 'resume the original session'):
                finalize(self.args)
        self.assertEqual(self.f.control()['events'], [])
        self.assertFalse(self.record_path.exists())

    def test_test_backend_requires_explicit_test_mode_before_write(self):
        with patch.dict(os.environ, {'PAPER_DOWNLOAD_TEST_MODE': '0'}):
            from institutional_access.session_store import SessionError
            with self.assertRaises(SessionError):
                finalize(self.args)
        self.assertEqual(self.f.control()['events'], [])

    def test_standalone_complete_still_deletes_session(self):
        with patch('institutional_access.cli.browser_for_session', return_value=ClosureClient()):
            self.assertEqual(complete(self.args)['stage'], 'completed')
        self.assertIsNone(self.sessions.read('fixture'))
        self.assertFalse(self.record_path.exists())


if __name__ == '__main__':
    unittest.main()
