"""Official API transport, recovery, citation edits and reading contracts."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from test_execution import Fixture
from zotero_library.authorization import Vault
from zotero_library.citations import cite, entries, export_bib, replace_checked, merge_bib
from zotero_library.errors import LibraryError
from zotero_library.operations import Executor
from zotero_library.reading import page_numbers, read_pdf, search


class MemoryVault:
    value = None
    def get(self): return self.value
    def put(self, value): self.value = value
    def forget(self): self.value = None


class LocalFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(self.tmp.name)

    def tearDown(self):
        self.f.close(); self.tmp.cleanup()

    def archive(self):
        result = self.f.executor().run(self.f.request())
        self.assertEqual(result['state'], 'completed', result)
        return result

    def test_official_transport_and_durable_stages(self):
        result = self.archive()
        state = self.f.control()
        imports = [e for e in state['events'] if e['event'] == 'import']
        self.assertEqual(imports[0]['transport'], 'local_api')
        self.assertTrue(any(e['event'] == 'api_write' and e['resource'] == 'collections' for e in state['events']))
        self.assertEqual(result['backend'], 'local_api')
        self.assertTrue(any(stage['name'].startswith('upload_register:') for stage in result['api_stages']))
        self.assertTrue(self.f.pdf.is_file())

    def test_denied_authorization_does_not_write_or_switch_interfaces(self):
        self.f.control(config={'authorizationStatus': 403})
        result=self.f.executor().run(self.f.request())
        self.assertEqual(result['error'], 'local_api_authorization_denied')
        state = self.f.control()
        self.assertEqual(state['items'], [])
        self.assertEqual([e['event'] for e in state['events']], ['authorize'])

    def test_remembered_authorization_is_vault_only_and_diagnostics_do_not_prompt(self):
        self.f.control(config={'remember': True})
        client = self.f.client(); client.api.vault = vault = MemoryVault()
        executor = Executor(client, self.f.store)
        self.assertFalse(client.api.authorization_present())
        self.assertEqual(self.f.control()['events'], [])
        result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'completed', result)
        self.assertTrue(vault.value)
        public = json.dumps(result) + self.f.store.path(result['operation_id']).read_text()
        self.assertFalse(vault.value in public)
        self.assertNotIn('apiAuthorization', public)
        self.assertNotIn('uploadKey', public)
        self.assertNotIn('/api/local/uploads/', public)
        self.assertTrue(client.api.authorization_present())
        self.assertEqual(sum(e['event'] == 'authorize' for e in self.f.control()['events']), 1)

    def test_all_requests_are_official_and_bound_reads_reject_database_switch(self):
        client=self.f.client()
        original=client.opener.open
        def check(request, **kwargs):
            self.assertIn('/api/', request.full_url)
            return original(request, **kwargs)
        with patch.object(client.opener, 'open', side_effect=check):
            result=Executor(client,self.f.store).run(self.f.request())
        self.assertEqual(result['state'],'completed',result)
        self.f.control(config={'databaseId':'switched-database'})
        with self.assertRaisesRegex(LibraryError,'database_identity_changed'):
            client.get({'type':'user'},result['native']['parentKey'])

    def test_revoked_authorization_needs_explicit_same_operation_resume(self):
        client = self.f.client(); client.api.vault = vault = MemoryVault()
        vault.value = 'synthetic-expired-credential'
        executor = Executor(client, self.f.store)
        result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['native']['error'], 'local_api_authorization_required')
        self.assertEqual(self.f.control()['events'], [])
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed', result)

    def test_database_switch_stops_completed_receipt_before_new_write(self):
        result = self.archive(); before = self.f.control()['events']
        self.f.control(config={'databaseId': 'another-database'})
        with self.assertRaisesRegex(LibraryError, 'database_identity_changed'):
            self.f.executor().resume(result['operation_id'])
        self.assertEqual(before, self.f.control()['events'])

    def test_unknown_upload_resumes_same_placeholder_without_preferences(self):
        self.f.control(config={'uploadDisconnect':True})
        executor=self.f.executor(policy=str(self.f.root/'missing-policy.json'))
        result=executor.run(self.f.request())
        self.assertEqual(result['state'],'unknown',result)
        result=executor.resume(result['operation_id'])
        self.assertEqual(result['state'],'completed',result)
        state=self.f.control()
        self.assertFalse(any(x['event'] in ('pref','forbidden_interface') for x in state['events']))
        self.assertEqual(sum(x['data']['itemType']=='attachment' for x in state['items']),1)

    def test_partial_upload_restart_reuses_placeholder_and_original_snapshot(self):
        self.f.control(config={'failImport': 1})
        executor = self.f.executor(); result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'unknown')
        self.f.control(restart=True)
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(sum(i['data']['itemType'] == 'attachment' for i in self.f.control()['items']), 1)

    def test_existing_reading_snapshot_is_checked_after_restart(self):
        original = self.archive(); request = self.f.request()
        request['collections'] = [{'path': ['Other workspace', '论文']}]
        self.f.control(config={'failImport': 0, 'writeAuthStatus': 403})
        executor = self.f.executor(); result = executor.run(request)
        self.assertEqual(result['state'], 'failed', result)
        self.f.control(restart=True, update={'key': original['native']['parentKey'],
            'fields': {'abstractNote': 'External edit'}}, config={'writeAuthStatus': 0})
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(result['native']['error'], 'protected_parent_changed')

    def test_legacy_receipt_uses_original_backend_and_id(self):
        executor = self.f.executor(); request = self.f.request()
        operation_id, request_hash = executor.identify(request)
        self.f.store.save({'schema': 1, 'operation_id': operation_id, 'request_hash': request_hash,
            'request': copy.deepcopy(request), 'input_request': request, 'kind': 'archive',
            'connection': executor.client.binding, 'state': 'prepared', 'attempts': []})
        result = executor.resume(operation_id)
        self.assertEqual(result['state'], 'completed', result)
        self.assertNotIn('backend', result)
        events = self.f.control()['events']
        self.assertTrue(any(e['event'] == 'api_write' for e in events))
        self.assertEqual(result['operation_id'], operation_id)

    def test_export_and_cite_preserve_bib_and_repeat_without_duplicates(self):
        result = self.archive(); client = self.f.client(); key = result['native']['parentKey']
        bib = self.f.root / 'refs.bib'; existing = b'% Keep this comment\r\n@book{keep,title={Original}}\r\n'
        bib.write_bytes(existing)
        doc = self.f.root / 'draft.md'; doc.write_bytes(b'\xef\xbb\xbfBefore\r\n<!--cite-->\r\nAfter\r\n')
        request = {'schema': 1, 'library': {'type': 'user'}, 'keys': [key], 'style': 'markdown',
            'target': {'path': str(doc), 'anchor': '<!--cite-->', 'placement': 'after'}, 'bibliography': str(bib)}
        first = cite(client, request)
        self.assertIn('fixture_' + key, first['citation'])
        saved = (doc.read_bytes(), bib.read_bytes())
        self.assertTrue(saved[1].startswith(existing))
        second = cite(client, request)
        self.assertFalse(second['changed']); self.assertFalse(second['bibliography_changed'])
        self.assertEqual(saved, (doc.read_bytes(), bib.read_bytes()))
        self.assertTrue(saved[0].startswith(b'\xef\xbb\xbf'))

    def test_conflict_reports_difference_without_editing_either_file(self):
        result = self.archive(); client = self.f.client(); key = result['native']['parentKey']
        bib = self.f.root / 'refs.bib'; bib.write_text('@article{fixture_' + key + ', title={Other}}\n')
        doc = self.f.root / 'draft.tex'; doc.write_text('Insert here.')
        before = (doc.read_bytes(), bib.read_bytes())
        request = {'schema': 1, 'library': {'type': 'user'}, 'keys': [key], 'style': 'latex',
            'target': {'path': str(doc), 'anchor': 'here', 'placement': 'before'}, 'bibliography': str(bib)}
        conflict = cite(client, request)
        self.assertEqual(conflict['state'], 'conflict'); self.assertIn('-@article', conflict['conflicts'][0]['difference'])
        self.assertEqual(before, (doc.read_bytes(), bib.read_bytes()))
        bib.unlink()
        result = cite(client, request)
        self.assertEqual(result['citation'], '\\cite{fixture_' + key + '}')
        self.assertFalse(cite(client, request)['changed'])

    def test_latex_comment_anchor_cannot_silently_hide_citation(self):
        result = self.archive(); client = self.f.client(); key = result['native']['parentKey']
        bib = self.f.root / 'refs.bib'
        doc = self.f.root / 'draft.tex'; original = b'Original prose.\n% cite-here\n'
        doc.write_bytes(original)
        request = {'schema': 1, 'library': {'type': 'user'}, 'keys': [key], 'style': 'latex',
            'target': {'path': str(doc), 'anchor': '% cite-here', 'placement': 'after'}, 'bibliography': str(bib)}
        with self.assertRaisesRegex(LibraryError, 'citation_position_commented'):
            cite(client, request)
        self.assertEqual(doc.read_bytes(), original); self.assertFalse(bib.exists())
        request['target']['placement'] = 'before'
        first = cite(client, request)
        self.assertIn(first['citation'] + '% cite-here', doc.read_text())
        self.assertFalse(cite(client, request)['changed'])
        doc.write_text(r'An escaped \% cite-here', encoding='utf-8')
        request['target'].update(anchor='cite-here', placement='after')
        self.assertTrue(cite(client, request)['changed'])
        doc.write_text(r'A line break \\% cite-here', encoding='utf-8')
        with self.assertRaisesRegex(LibraryError, 'citation_position_commented'):
            cite(client, request)

    def test_bibtex_balanced_parser_and_manuscript_concurrency(self):
        self.assertEqual(set(entries('@string{j="Journal"}\n@book(key, title={A {nested} title})')), {'key'})
        merged, conflicts = merge_bib(b'@article{same, title={A  title}}\n',
                                     {'same': '@article{same, title={A title}}'})
        self.assertIsNone(merged)
        self.assertEqual(len(conflicts), 1)
        path = self.f.root / 'draft.md'; path.write_text('User edit')
        with self.assertRaisesRegex(LibraryError, 'target_changed_during_operation'):
            replace_checked(path, b'Old text', b'Replacement')
        self.assertEqual(path.read_text(), 'User edit')
        self.assertFalse(path.with_name(path.name + '.zotero-library.lock').exists())

    def test_pdf_page_text_ocr_range_and_missing_dependency(self):
        self.f.article_pdf(); result = self.archive(); client = self.f.client()
        read = read_pdf(client, {'type': 'user'}, result['native']['parentKey'], pages='1')
        self.assertIn('Verified article', read['pages'][0]['text'])
        self.assertTrue(read['complete_document']); self.assertEqual(read['pages'][0]['page'], 1)
        with self.assertRaisesRegex(LibraryError, 'invalid_page_range'): page_numbers('0-2', 2)
        with patch.dict('sys.modules', {'pypdf': None}):
            with self.assertRaisesRegex(LibraryError, 'pdf_dependency_missing'):
                read_pdf(client, {'type': 'user'}, result['native']['parentKey'])

    def test_scanned_page_is_explicit_and_note_annotation_search_links_owners(self):
        result = self.archive(); parent = result['native']['parentKey']; attachment = result['native']['attachment']['key']
        self.f.control(seed=[{'itemType': 'note', 'parentKey': parent, 'note': '<p>Phase evidence</p>'},
            {'itemType': 'annotation', 'parentKey': attachment, 'fields': {'annotationText': 'Phase result',
                'annotationComment': 'Verify', 'annotationPageLabel': 'iv',
                'annotationPosition': json.dumps({'pageIndex': 2})}}])
        client = self.f.client(); read = read_pdf(client, {'type': 'user'}, parent)
        self.assertEqual(read['state'], 'ocr_required'); self.assertFalse(read['complete_document'])
        results = search(client, {'type': 'user'}, 'phase')['results']
        self.assertEqual(len(results), 2)
        annotation = next(row for row in results if row['type'] == 'annotation')
        self.assertEqual(annotation['parent']['key'], parent)
        self.assertEqual(annotation['attachment']['key'], attachment)
        self.assertEqual(annotation['page'], 3); self.assertEqual(annotation['page_label'], 'iv')


@unittest.skipUnless(os.name == 'nt', 'Windows Credential Manager')
class WindowsVaultTests(unittest.TestCase):
    def test_store_roundtrip_and_forget_only_own_target(self):
        vault = Vault('isolated-test-' + str(uuid.uuid4()))
        try:
            self.assertIsNone(vault.get())
            vault.put('synthetic-value')
            self.assertTrue(vault.get() == 'synthetic-value')
        finally:
            vault.forget()
        self.assertIsNone(vault.get())


if __name__ == '__main__':
    unittest.main()
