"""Public database coordination, legacy receipts and conditional recycle recovery."""
import copy
import uuid
import unittest
from unittest.mock import patch

import test_execution
from zotero_library.errors import LibraryError
from zotero_library.files import inspect_pdf
from zotero_library.operations import Coordination, Executor, Store
from zotero_library.objects import Objects


class APIRecoveryTests(unittest.TestCase):
    setUp = test_execution.NativeExecutionTests.setUp
    tearDown = test_execution.NativeExecutionTests.tearDown

    def test_new_parent_reports_external_attachment_without_deleting_it(self):
        original = Objects.attachment
        added = []
        def attach(objects, parent, create):
            result = original(objects, parent, create)
            state = self.f.control(seed=[{'itemType': 'attachment', 'parentKey': parent['key'],
                'linkMode': 'linked_url', 'contentType': 'text/html',
                'fields': {'title': 'Externally added reference', 'url': 'https://example.invalid'}}])
            added.append(state['items'][-1]['key'])
            return result
        with patch.object(Objects, 'attachment', attach):
            result = self.f.executor().run(self.f.request())
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['native']['external_children_preserved'], added)
        self.assertFalse(self.f.client().get({'type': 'user'}, added[0])['data'].get('deleted'))

    def test_database_lock_is_shared_across_receipt_directories(self):
        first = self.f.executor()
        other = Executor(self.f.client(), Store(self.f.root / 'other-receipts'))
        with Coordination(first.client.api.server_id).lock():
            with self.assertRaisesRegex(LibraryError, 'database_operation_busy'):
                other.run(self.f.request())
        self.assertEqual(self.f.control()['items'], [])

    def test_failed_reservation_does_not_release_another_operation(self):
        self.f.control(config={'uploadDisconnect': True})
        first = self.f.executor().run(self.f.request())
        self.assertEqual(first['state'], 'unknown', first)
        coord = Coordination(first['database_id'])
        original = coord.pending_path.read_bytes()
        other = Executor(self.f.client(), Store(self.f.root / 'other-receipts'))
        request = self.f.request('Another article', '10.1234/another')
        blocked = other.run(request)
        self.assertEqual(blocked['error'], 'database_operation_pending')
        self.assertEqual(coord.pending_path.read_bytes(), original)
        same = other.run(self.f.request())
        self.assertEqual(same['error'], 'operation_pending_in_other_state_directory')
        self.assertEqual(coord.pending_path.read_bytes(), original)
        self.assertEqual(self.f.executor().resume(first['operation_id'])['state'], 'completed')
        self.assertFalse(coord.pending_path.exists())

    def test_lost_registration_reply_confirms_file_without_reupload(self):
        self.f.control(config={'registerDisconnect': True})
        result = self.f.executor().run(self.f.request())
        self.assertEqual(result['state'], 'unknown', result)
        self.f.pdf.unlink()
        result = self.f.executor().resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_completed_legacy_receipt_is_read_back_without_writes(self):
        executor = self.f.executor()
        result = executor.run(self.f.request())
        result.pop('executor_version'); result.pop('backend')
        self.f.store.save(result)
        before = copy.deepcopy(self.f.control()['events'])
        checked = executor.status(result['operation_id'])
        self.assertEqual(checked['state'], 'completed', checked)
        self.assertTrue(checked['legacy_preferences_not_modified'])
        self.assertEqual(self.f.control()['events'], before)

    def test_legacy_unknown_without_process_proof_is_not_replayed(self):
        executor = self.f.executor()
        request = self.f.request()
        oid, digest = executor.identify(request)
        receipt = {'schema': 1, 'operation_id': oid, 'request_hash': digest,
            'request': request, 'input_request': request, 'kind': 'archive',
            'connection': executor.client.binding, 'state': 'unknown',
            'attempts': [{'id': str(uuid.uuid4())}]}
        self.f.store.save(receipt)
        result = executor.resume(oid)
        self.assertEqual(result['state'], 'unknown', result)
        self.assertEqual(result['error'], 'legacy_original_process_unresolved')
        self.assertEqual(self.f.control()['items'], [])

    def test_legacy_prepared_receipt_migrates_without_bridge(self):
        executor = self.f.executor(); request = self.f.request()
        oid, digest = executor.identify(request)
        self.f.store.save({'schema': 1, 'operation_id': oid, 'request_hash': digest,
            'request': request, 'input_request': request, 'kind': 'archive',
            'connection': executor.client.binding, 'state': 'prepared', 'attempts': []})
        result = executor.resume(oid)
        self.assertEqual(result['state'], 'completed', result)
        self.assertTrue(result['legacy_migrated'])

    def prune_request(self):
        request = self.f.request(); result = self.f.executor().run(request)
        state = self.f.control(seed=[{'itemType': 'attachment',
            'parentKey': result['native']['parentKey'], 'contentType': 'application/pdf',
            'file': str(self.f.pdf)}])
        def spec(key):
            return {'key': key, 'sha256': inspect_pdf(self.f.pdf)['sha256'],
                    'version': 'official', 'evidence': ['Same PDF verified']}
        prune = {k: request[k] for k in ('schema', 'library', 'identity')}
        prune.update(parent_key=result['native']['parentKey'],
            keep=spec(result['native']['attachment']['key']),
            candidates=[spec(state['items'][-1]['key'])])
        return prune

    def test_reading_added_after_recycle_restores_candidate(self):
        request = self.prune_request()
        self.f.control(config={'afterTrashNote': True})
        result = self.f.executor().run(request, 'prune')
        key = request['candidates'][0]['key']
        item = self.f.client().get(request['library'], key)
        self.assertFalse(item['data'].get('deleted'))
        self.assertNotEqual(result['state'], 'completed')
        self.assertEqual(sum(x['event'] == 'trash' for x in self.f.control()['events']), 1)
        resumed = self.f.executor().resume(result['operation_id'])
        self.assertEqual(resumed['state'], 'completed', resumed)
        self.assertEqual(resumed['native']['trashed'], [])
        self.assertEqual(resumed['native']['skipped'][0]['reason'], 'candidate_has_linked_notes')

    def test_unconfirmed_recycle_never_restores_someone_elses_change(self):
        request = self.prune_request(); executor = self.f.executor()
        original = executor.client.api.json
        def conflict(path, **kw):
            if kw.get('method') == 'POST' and kw.get('body', [{}])[0].get('deleted'):
                self.f.control(update={'key': request['candidates'][0]['key'], 'fields': {'deleted': True}})
                raise LibraryError('local_api_version_conflict')
            return original(path, **kw)
        with patch.object(executor.client.api, 'json', side_effect=conflict):
            result = executor.run(request, 'prune')
        self.f.control(seed=[{'itemType': 'note', 'note': request['candidates'][0]['key']}])
        result = executor.resume(result['operation_id'])
        self.assertNotEqual(result['state'], 'completed', result)
        item = executor.client.get(request['library'], request['candidates'][0]['key'])
        self.assertTrue(item['data']['deleted'])
        self.assertFalse(any(x['name'].startswith('restore:') for x in result['api_stages']))

    def test_failed_restoration_is_unknown(self):
        request = self.prune_request(); executor = self.f.executor()
        self.f.control(config={'afterTrashNote': True})
        original = executor.client.api.json
        def reject_restore(path, **kw):
            if kw.get('method') == 'PATCH' and kw.get('body') == {'deleted': False}:
                raise LibraryError('local_api_version_conflict')
            return original(path, **kw)
        with patch.object(executor.client.api, 'json', side_effect=reject_restore):
            result = executor.run(request, 'prune')
        self.assertEqual(result['state'], 'unknown', result)
        self.assertEqual(result['error'], 'trash_restore_unknown')


if __name__ == '__main__':
    unittest.main()
