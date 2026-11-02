"""Executable download-layer correction using the shared identity resolver."""
import copy
import hashlib
import json
import unittest
import uuid
from unittest.mock import patch
import test_finalize


class HandoffTests(unittest.TestCase):
    setUp = test_finalize.FinalizeTests.setUp
    tearDown = test_finalize.FinalizeTests.tearDown
    imports = test_finalize.FinalizeTests.imports
    def seed_pair(self):
        state = self.f.control(seed=[
            {'itemType': 'journalArticle', 'fields': {'title': 'Winzer 2018', 'DOI': '10.1234/winzer'}, 'tags': [{'tag': 'keep'}]},
            {'itemType': 'attachment', 'parentID': 1, 'contentType': 'application/pdf', 'file': str(self.f.pdf)},
            {'itemType': 'note', 'parentID': 1, 'note': '<p>Protected reading note</p>'},
            {'itemType': 'annotation', 'parentID': 2, 'note': 'Protected annotation'},
            {'itemType': 'journalArticle', 'fields': {'title': 'Verified article', 'DOI': '10.1234/fixture'}}],
            seedCollections=[{'name': 'Protected workspace', 'itemIndexes': [0]}])
        self.request['parent_key'] = state['items'][0]['key']
        self.request_path.write_text(json.dumps(self.request))
        return state

    def test_assistant_wrong_key_corrects_and_retries_once_wrong_tree_unchanged(self):
        from zotero_archive import archive_request
        before = self.seed_pair()
        wrong_tree = copy.deepcopy(before['items'][:4])
        file_path = self.root / 'storage' / (wrong_tree[1]['key'] + '.pdf')
        original_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        executor = self.f.executor()
        for _ in range(2):
            result = archive_request(executor, self.request, 'assistant')
            self.assertEqual(result['archive']['state'], 'completed', result)
            self.assertEqual(result['correction']['original_key'], wrong_tree[0]['key'])
            self.assertEqual(result['correction']['parent_key'], before['items'][4]['key'])
        after = self.f.control()
        self.assertEqual(after['items'][:4], wrong_tree)
        self.assertEqual(hashlib.sha256(file_path.read_bytes()).hexdigest(), original_hash)
        self.assertEqual(self.imports(), 1)

    def test_unknown_original_operation_never_changes_target(self):
        from zotero_archive import archive_request
        from zotero_library.request import digest, validate
        before = self.seed_pair()
        self.request['operation_id'] = str(uuid.uuid4())
        original = validate(self.request)
        self.f.store.save({'schema': 1, 'operation_id': original['operation_id'], 'kind': 'archive',
            'request_hash': digest({'kind': 'archive', 'request': original}), 'request': original,
            'input_request': original, 'state': 'unknown', 'attempts': [],
            'connection': self.f.client().binding})
        result = archive_request(self.f.executor(), self.request, 'assistant')
        self.assertEqual(result['stage'], 'reconcile_original_operation', result)
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], self.f.control()[field])

    def test_implicit_unknown_without_sha_never_changes_target_or_operation(self):
        from zotero_archive import archive_request
        from zotero_library.request import validate
        self.seed_pair()
        executor = self.f.executor()
        request = validate(self.request)
        operation_id, request_hash = executor.identify(request)
        self.f.store.save({'schema': 1, 'operation_id': operation_id, 'kind': 'archive',
            'request_hash': request_hash, 'request': request, 'input_request': request,
            'state': 'unknown', 'attempts': [], 'connection': executor.client.binding})
        result = archive_request(executor, self.request, 'assistant')
        self.assertEqual(result['stage'], 'reconcile_original_operation', result)
        self.assertEqual(result['archive']['operation_id'], operation_id)
        self.assertEqual(len(list(self.f.store.root.glob('*.json'))), 1)
        self.assertEqual(self.imports(), 0)

    def test_existing_same_target_without_sha_uses_the_original_operation(self):
        from zotero_archive import archive_request
        executor = self.f.executor()
        original = executor.run(self.request)
        result = archive_request(executor, self.request)
        self.assertEqual(result['stage'], 'completed', result)
        self.assertEqual(original['operation_id'], result['archive']['operation_id'])
        self.assertEqual(len(list(self.f.store.root.glob('*.json'))), 1)
        self.assertEqual(self.imports(), 1)

    def test_finished_zero_write_operation_allows_corrected_new_request(self):
        from zotero_archive import archive_request
        before = self.seed_pair()
        self.request['operation_id'] = str(uuid.uuid4())
        executor = self.f.executor()
        original = executor.run(self.request)
        self.assertEqual(original['state'], 'failed', original)
        self.assertFalse(original['native']['contentWritesStarted'])
        for _ in range(2):
            result = archive_request(executor, self.request, 'assistant')
            self.assertEqual(result['stage'], 'completed', result)
            self.assertNotEqual(result['archive']['operation_id'], original['operation_id'])
        self.assertEqual(before['items'][:4], self.f.control()['items'][:4])
        self.assertEqual(self.imports(), 1)

    def test_explicit_handoff_id_is_not_reused_for_a_changed_target(self):
        from zotero_archive import archive_request
        self.seed_pair()
        self.request['operation_id'] = str(uuid.uuid4())
        for _ in range(2):
            result = archive_request(self.f.executor(), self.request, 'assistant')
            self.assertEqual(result['stage'], 'completed', result)
            self.assertNotEqual(result['archive']['operation_id'], self.request['operation_id'])
        self.assertEqual(self.imports(), 1)

    def test_multiple_correct_candidates_do_not_autocorrect(self):
        from zotero_archive import archive_request
        self.seed_pair()
        before = self.f.control(seed=[{'itemType': 'journalArticle',
            'fields': {'title': 'Verified article', 'DOI': '10.1234/fixture'}}])
        result = archive_request(self.f.executor(), self.request, 'assistant')
        self.assertEqual(result['stage'], 'identity_review_required', result)
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], self.f.control()[field])

    def test_direct_archive_rejects_wrong_pdf_and_wrong_requested_version(self):
        from zotero_archive import archive_request
        self.f.article_pdf('Unrelated paper', '10.1234/unrelated')
        result = archive_request(self.f.executor(), self.request)
        self.assertEqual(result['reason'], 'pdf_identity_requires_review', result)
        self.f.article_pdf()
        result = archive_request(self.f.executor(), self.request, required_version='preprint')
        self.assertEqual(result['reason'], 'pdf_version_mismatch', result)
        self.assertEqual(self.f.control()['items'], [])
        self.assertEqual(self.f.control()['events'], [])

    def test_finalize_rejects_wrong_pdf_and_wrong_requested_version(self):
        from institutional_access.finalize import finalize
        self.f.article_pdf('Unrelated paper', '10.1234/unrelated')
        session = self.sessions.read('fixture')
        session['validation']['sha256'] = hashlib.sha256(self.f.pdf.read_bytes()).hexdigest()
        self.sessions.write('fixture', session)
        result = finalize(self.args)
        self.assertEqual(result['reason'], 'pdf_identity_requires_review', result)
        self.f.article_pdf()
        session['validation']['sha256'] = hashlib.sha256(self.f.pdf.read_bytes()).hexdigest()
        self.sessions.write('fixture', session)
        self.args.required_version = 'preprint'
        result = finalize(self.args)
        self.assertEqual(result['reason'], 'pdf_version_mismatch', result)
        self.assertEqual(self.f.control()['items'], [])
        self.assertEqual(self.f.control()['events'], [])

    def test_user_wrong_key_requires_answer_and_preserves_all_library_content(self):
        from zotero_archive import archive_request
        before = self.seed_pair()
        result = archive_request(self.f.executor(), self.request, 'user')
        self.assertEqual(result['stage'], 'identity_review_required')
        after = self.f.control()
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], after[field])

    def test_finalize_corrects_assistant_key_then_closes_and_replay_is_idempotent(self):
        from institutional_access.finalize import finalize
        before = self.seed_pair(); self.args.parent_key_source = 'assistant'
        with patch('institutional_access.cli.browser_for_session', return_value=test_finalize.ClosureClient()):
            result = finalize(self.args)
        self.assertEqual(result['stage'], 'completed', result)
        self.assertEqual(result['correction']['parent_key'], before['items'][4]['key'])
        with patch('zotero_library.operations.Executor.run', side_effect=AssertionError('archive replay')):
            self.assertEqual(finalize(self.args)['stage'], 'completed')
        self.assertEqual(self.f.control()['items'][:4], before['items'][:4])
        self.assertEqual(self.imports(), 1)

    def test_finalize_user_key_conflict_never_closes(self):
        from institutional_access.finalize import finalize
        before = self.seed_pair()
        with patch('institutional_access.cli.browser_for_session', side_effect=AssertionError('premature closure')):
            result = finalize(self.args)
        self.assertEqual(result['stage'], 'identity_review_required', result)
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], self.f.control()[field])
