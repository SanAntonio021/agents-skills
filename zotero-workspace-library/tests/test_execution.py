"""HTTP and fixed-native-program integration against an isolated native API model."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from zotero_library.client import Client
from zotero_library.errors import LibraryError
from zotero_library.files import inspect_pdf
from zotero_library.operations import Executor, Store
from zotero_library.request import validate
from pypdf import PdfWriter


class Fixture:
    def __init__(self, root):
        self.root = Path(root)
        self.profile = self.root / 'profile'
        self.profile.mkdir()
        (self.profile / 'prefs.js').write_text(
            'user_pref("extensions.zotero.debug-bridge.token", "synthetic-fixture-credential");\n'
            'user_pref("extensions.zotero.httpServer.localAPI.enabled", true);', encoding='utf-8')
        node = os.environ.get('ZOTERO_TEST_NODE') or shutil.which('node')
        if not node:
            raise RuntimeError('Node is required for native contract tests')
        self.process = subprocess.Popen([node, str(Path(__file__).with_name('fixture_server.cjs')),
            str(self.root / 'storage')], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.base = 'http://127.0.0.1:' + str(json.loads(self.process.stdout.readline())['port'])
        self.store = Store(self.root / 'operations')
        self.pdf = self.root / 'article.pdf'
        writer = PdfWriter(); writer.add_blank_page(612, 792)
        with self.pdf.open('wb') as stream:
            writer.write(stream)

    def close(self):
        self.process.terminate()
        self.process.communicate(timeout=10)

    def article_pdf(self, title='Verified article', doi='10.1234/fixture'):
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer = PdfWriter(); page = writer.add_blank_page(612, 792)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(('BT /F1 12 Tf 40 720 Td (' + title + ') Tj 0 -25 Td (DOI: ' + doi + ') Tj ET').encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
        with self.pdf.open('wb') as output:
            writer.write(output)

    def control(self, **data):
        req = urllib.request.Request(self.base + '/control', data=json.dumps(data).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def client(self, timeout=2, policy=None):
        # Avoid enumerating actual desktop processes during isolated tests.
        with patch('zotero_library.connection.process_status', return_value={'state': 'unknown', 'pids': [], 'executable_paths': []}):
            return Client(str(self.profile), self.base, timeout, policy)

    def request(self, title='Verified article', doi='10.1234/fixture'):
        return {'schema': 1, 'library': {'type': 'user'},
            'identity': {'title': title, 'doi': doi, 'evidence': ['Isolated publisher and PDF identity fixture']},
            'metadata': {'itemType': 'journalArticle'},
            'collections': [{'path': ['Workspace', '论文']}],
            'pdf': {'path': str(self.pdf), 'version': 'official', 'evidence': ['Isolated official-version fixture']}}

    def executor(self, timeout=2, policy=None):
        return Executor(self.client(timeout, policy), self.store)


class NativeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(self.tmp.name)

    def tearDown(self):
        self.f.close(); self.tmp.cleanup()

    def test_environment_binding_and_invalid_profile_never_falls_back(self):
        environment = {'ZOTERO_PROFILE': str(self.f.profile),
            'ZOTERO_LOCAL_BASE_URL': self.f.base,
            'ZOTERO_LIBRARY_STATE_DIR': str(self.f.store.root)}
        with patch.dict(os.environ, environment), patch('zotero_library.connection.process_status',
                return_value={'state': 'unknown', 'pids': [], 'executable_paths': []}):
            client = Client()
            self.assertEqual(client.binding, {'base_url': self.f.base, 'profile': str(self.f.profile)})
            self.assertEqual(Store().root, self.f.store.root)
            result = Executor(client).run(self.f.request())
            self.assertEqual(result['state'], 'completed', result)
            with patch.dict(os.environ, {'ZOTERO_PROFILE': str(self.f.root / 'missing')}):
                with self.assertRaisesRegex(LibraryError, 'explicit_profile_unreadable'):
                    Client()
                self.assertEqual(Client(str(self.f.profile)).base, self.f.base)

    def test_archive_repeat_and_request_conflict(self):
        request = self.f.request(); request['operation_id'] = str(uuid.uuid4())
        executor = self.f.executor()
        first = executor.run(request); self.assertEqual(first['state'], 'completed', first)
        second = executor.run(request); self.assertEqual(second['state'], 'completed', second)
        state = self.f.control()
        self.assertEqual(sum(e['event'] == 'import' for e in state['events']), 1)
        self.assertEqual(len(state['collections']), 2)
        self.assertTrue(self.f.pdf.exists())
        self.assertEqual(first['pdf_verification']['sha256'], hashlib.sha256(self.f.pdf.read_bytes()).hexdigest())
        request['identity']['evidence'].append('different request')
        with self.assertRaisesRegex(LibraryError, 'operation_request_conflict'):
            executor.run(request)

    def installed_command(self, skill, *arguments):
        environment = {**os.environ, 'ZOTERO_PROFILE': str(self.f.profile),
            'ZOTERO_LOCAL_BASE_URL': self.f.base,
            'ZOTERO_LIBRARY_STATE_DIR': str(self.f.store.root)}
        result = subprocess.run([sys.executable, str(skill / 'scripts/zotero_library.py'),
            *arguments], env=environment, capture_output=True, text=True, timeout=30)
        self.assertIn(result.returncode, (0, 2), result.stderr + result.stdout)
        return json.loads(result.stdout)

    def legacy_install(self):
        # The execution package is unchanged by this migration. Run that package
        # in a fresh interpreter from the old layout, then physically relocate it.
        skill = self.f.root / 'legacy-skill'
        shutil.copytree(Path(__file__).resolve().parents[1] / 'scripts', skill / 'scripts',
                        ignore=shutil.ignore_patterns('__pycache__'))
        request = self.f.root / 'request.json'
        request.write_text(json.dumps(self.f.request()), encoding='utf-8')
        return skill, request

    def test_completed_receipt_survives_skill_relocation(self):
        skill, request = self.legacy_install()
        legacy = self.installed_command(skill, 'archive', '--request', str(request))
        self.assertEqual(legacy['state'], 'completed', legacy)
        relocated = self.f.root / 'zotero-workspace-library'
        skill.rename(relocated)
        result = self.installed_command(relocated, 'archive', '--request', str(request))
        self.assertEqual(result['operation_id'], legacy['operation_id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_unknown_receipt_survives_skill_relocation_without_replay(self):
        skill, request = self.legacy_install()
        legacy = self.installed_command(skill, 'archive', '--request', str(request))
        self.assertEqual(legacy['state'], 'completed', legacy)
        receipt = self.f.store.read(legacy['operation_id'])
        receipt['state'] = 'unknown'
        self.f.store.save(receipt)
        self.f.control(clearMarker=True)
        relocated = self.f.root / 'zotero-workspace-library'
        skill.rename(relocated)
        result = self.installed_command(relocated, 'operation', 'resume', '--id', legacy['operation_id'])
        self.assertEqual(result['operation_id'], legacy['operation_id'])
        self.assertEqual(result['state'], 'unknown', result)
        self.assertEqual(len(self.f.store.read(legacy['operation_id'])['attempts']), 1)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_four_business_chains_and_reading_protection(self):
        executor = self.f.executor()
        # Search saves metadata; classification adds only the chosen workspace relationship.
        search = self.f.request(); del search['pdf']; search['collections'] = []
        result = executor.run(search); self.assertEqual(result['state'], 'completed', result)
        parent = result['native']['parentKey']
        classify = copy.deepcopy(search); classify['parent_key'] = parent
        classify['collections'] = [{'path': ['Workspace', '论文']}]
        result = executor.run(classify); self.assertEqual(result['state'], 'completed', result)
        # Existing reading data survives adding a PDF via the download chain.
        state = self.f.control(seed=[{'itemType': 'note', 'parentID': 1, 'note': '<p>Keep reading note</p>'}])
        before = [x for x in state['items'] if x['data']['itemType'] == 'note']
        download = self.f.request(); download['parent_key'] = parent
        result = executor.run(download); self.assertEqual(result['state'], 'completed', result)
        attachment_id = int(result['native']['attachment']['key'][1:])
        self.f.control(seed=[{'itemType': 'annotation', 'parentID': attachment_id, 'note': 'Keep annotation'}])
        linked = copy.deepcopy(classify); linked['collections'] = [{'path': ['Other workspace', '论文']}]
        result = executor.run(linked); self.assertEqual(result['state'], 'completed', result)
        state = self.f.control()
        self.assertEqual(before, [x for x in state['items'] if x['data']['itemType'] == 'note'])
        self.assertEqual(sum(x['data']['itemType'] == 'annotation' for x in state['items']), 1)
        self.assertEqual(len(next(x for x in state['items'] if x['key'] == parent)['data']['collections']), 2)
        # Lab resources provides manufacturer/model/revision evidence and an official URL.
        manual = self.f.request('Manufacturer Model X Manual Rev A'); del manual['identity']['doi']
        manual['identity']['url'] = 'https://manufacturer.invalid/model-x/manual'
        manual['identity']['evidence'] = ['Manufacturer, model X and revision A verified']
        manual['metadata'] = {'itemType': 'document'}; manual['collections'] = [{'path': ['Workspace', '器件手册']}]
        result = executor.run(manual); self.assertEqual(result['state'], 'completed', result)

    def test_missing_import_capability_is_explicit(self):
        self.f.control(config={'noImport': True})
        with self.assertRaisesRegex(LibraryError, 'capability_missing_import_from_file'):
            self.f.executor().run(self.f.request())
        self.assertEqual(self.f.control()['items'], [])

    def test_completed_operation_cannot_be_reused_on_another_connection(self):
        request = self.f.request()
        request['operation_id'] = str(uuid.uuid4())
        executor = self.f.executor()
        self.assertEqual(executor.run(request)['state'], 'completed')
        before = self.f.control()
        executor.client.binding = {**executor.client.binding, 'profile': 'another-profile'}
        with patch.object(executor.client, 'get', side_effect=AssertionError('wrong target readback')):
            with self.assertRaisesRegex(LibraryError, 'operation_connection_mismatch'):
                executor.run(request)
        self.assertEqual(self.f.control(), before)

    def test_authentication_redaction_and_no_connector_fallback(self):
        self.f.control(config={'auth': 401})
        client = self.f.client()
        self.assertEqual(client.status['debug_bridge_error'], 'bridge_authentication_failed')
        with self.assertRaisesRegex(LibraryError, 'bridge_authentication_failed'):
            Executor(client, self.f.store).run(self.f.request())
        self.assertNotIn('synthetic-fixture-credential', json.dumps(client.status))
        self.assertEqual(self.f.control()['events'], [])

    def test_concurrent_batch_refused_and_resume_after_original_finishes(self):
        self.f.control(config={'delay': 170})
        executor = self.f.executor()
        first = executor.run(self.f.request(), wait=0); self.assertEqual(first['state'], 'running')
        second = executor.run(self.f.request('Second article', '10.1234/second'), wait=0)
        self.assertEqual(second['state'], 'failed', second)
        self.assertEqual(second['error'], 'another_batch_active')
        time.sleep(1)
        self.assertEqual(executor.status(first['operation_id'])['state'], 'completed')
        self.assertEqual(executor.resume(second['operation_id'])['state'], 'completed')

    def test_legacy_batch_refused_before_any_write(self):
        self.f.control(legacy='old-batch')
        with self.assertRaisesRegex(LibraryError, 'legacy_batch_active'):
            self.f.executor().run(self.f.request())
        self.assertEqual(self.f.control()['items'], [])

    def test_http_timeout_queries_same_native_job(self):
        self.f.control(config={'replyDelay': 500})
        executor = self.f.executor(timeout=.15)
        result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'unknown', result)
        time.sleep(.6)
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_partial_failure_resume_only_missing_pdf(self):
        self.f.control(config={'failImport': 1})
        executor = self.f.executor()
        result = executor.run(self.f.request()); self.assertEqual(result['state'], 'failed', result)
        result = executor.resume(result['operation_id']); self.assertEqual(result['state'], 'completed', result)
        state = self.f.control()
        self.assertEqual(sum(x['data']['itemType'] == 'journalArticle' for x in state['items']), 1)
        self.assertEqual(sum(x['event'] == 'import' for x in state['events']), 1)

    def test_external_preference_change_preserved(self):
        addon = {'id': 'fixture@invalid', 'version': '1'}
        self.f.control(addons=[addon], config={'external': True})
        policy = self.f.root / 'policy.json'
        policy.write_text(json.dumps({'schema': 1, 'addons': [{**addon,
            'preference_keys': ['extensions.fixture.auto'], 'evidence': 'Reviewed isolated fixture automatic handler'}]}))
        result = self.f.executor(policy=str(policy)).run(self.f.request())
        self.assertEqual(result['state'], 'recovery_required', result)
        self.assertEqual(result['native']['error'], 'automatic_preference_changed')
        state = self.f.control()
        self.assertTrue(state['prefs']['extensions.fixture.auto'])
        self.assertEqual(sum(x['event'] == 'import' for x in state['events']), 0)
        self.assertEqual(result['native']['preferenceRecovery'][0]['recovery'], 'preserved_external_change')

    def test_current_audited_addons_allow_write_without_separate_policy(self):
        # These exact versions were reviewed in the shipped maintenance policy.
        addons = [
            {'id': 'debug-bridge@iris-advies.com', 'version': '3.0.1'},
            {'id': 'better-bibtex@iris-advies.com', 'version': '9.0.74'},
            {'id': 'jasminum@linxzh.com', 'version': '1.1.43'},
            {'id': 'register02@cn.nutstore.net', 'version': '2.1.2'},
            {'id': 'tara@linxzh.com', 'version': '1.0.11'},
            {'id': 'zoplicate@chenglongma.com', 'version': '5.1.1'},
            {'id': 'zotero-format-metadata@northword.cn', 'version': '4.0.4'},
            {'id': 'zoteroAddons@ytshen.com', 'version': '11.0.1'},
            {'id': 'zoterocitation@polygon.org', 'version': '0.5.11'},
            {'id': 'zoteroif@qnscholar', 'version': '7.1.3.1'},
        ]
        self.f.control(addons=addons)
        executor = self.f.executor()
        result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'completed', result)
        state = self.f.control()
        self.assertEqual(sum(x['event'] == 'import' for x in state['events']), 1)
        self.assertFalse(any(x['event'] == 'pref' for x in state['events']))

    def test_unknown_addon_does_not_block_write(self):
        self.f.control(addons=[{'id': 'unknown@invalid', 'version': '99'}])
        result = self.f.executor().run(self.f.request())
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_addon_version_change_during_write_does_not_block(self):
        self.f.control(addons=[{'id': 'debug-bridge@iris-advies.com', 'version': '3.0.1'}],
                       config={'addonsOnStart': [{'id': 'debug-bridge@iris-advies.com', 'version': '3.0.2'}]})
        result = self.f.executor().run(self.f.request())
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_owned_preferences_restore_after_success_and_import_failure(self):
        addon = {'id': 'fixture@invalid', 'version': '1'}
        self.f.control(addons=[addon])
        policy = self.f.root / 'policy.json'
        policy.write_text(json.dumps({'schema': 1, 'addons': [{**addon,
            'preference_keys': ['extensions.fixture.auto'], 'evidence': 'Reviewed fixture automatic handler'}]}))
        executor = self.f.executor(policy=str(policy))
        self.f.control(config={'failImport': 1})
        result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'failed', result)
        self.assertTrue(self.f.control()['prefs']['extensions.fixture.auto'])
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed', result)
        state = self.f.control()
        self.assertTrue(state['prefs']['extensions.fixture.auto'])
        self.assertEqual([e['value'] for e in state['events'] if e['event'] == 'pref'],
                         [False, True, False, True])
        self.assertEqual(result['native']['preferenceRecovery'][0]['recovery'], 'restored')
        # A process exit loses setting ownership; no stale snapshot may be restored or replayed.
        result['state'] = 'unknown'; self.f.store.save(result); self.f.control(restart=True)
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'recovery_required', result)
        self.assertEqual(sum(e['event'] == 'import' for e in self.f.control()['events']), 1)

    def test_missing_marker_same_process_remains_unknown(self):
        executor = self.f.executor(); result = executor.run(self.f.request())
        # Simulate loss of a nonterminal marker; do not invent a fresh operation.
        result['state'] = 'unknown'; self.f.store.save(result); self.f.control(clearMarker=True)
        result = executor.resume(result['operation_id']); self.assertEqual(result['state'], 'unknown')
        self.assertEqual(len(result['attempts']), 1)

    def test_process_restart_reconciles_and_deduplicates(self):
        executor = self.f.executor(); result = executor.run(self.f.request())
        result['state'] = 'unknown'; self.f.store.save(result); self.f.control(restart=True)
        result = executor.resume(result['operation_id']); self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_readback_failure_remains_unknown_then_revalidates(self):
        executor = self.f.executor(); original = executor.client.get
        with patch.object(executor.client, 'get', side_effect=LibraryError('local_api_read_failed')):
            result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'unknown')
        self.assertEqual(self.f.store.read(result['operation_id'])['state'], 'unknown')
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed')
        self.assertNotIn('error', result)
        with patch.object(executor.client, 'get', side_effect=LibraryError('local_api_read_failed')):
            result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'unknown')
        self.assertFalse(result['readback_verified'])
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_prune_trashes_only_verified_unannotated_candidates(self):
        executor = self.f.executor(); request = self.f.request()
        result = executor.run(request); self.assertEqual(result['state'], 'completed', result)
        state = self.f.control(seed=[
            {'itemType': 'attachment', 'parentID': 1, 'contentType': 'application/pdf', 'file': str(self.f.pdf)},
            {'itemType': 'attachment', 'parentID': 1, 'contentType': 'application/pdf', 'file': str(self.f.pdf)}])
        attachments = [x for x in state['items'] if x['data']['itemType'] == 'attachment']
        self.f.control(seed=[{'itemType': 'annotation', 'parentID': int(attachments[2]['key'][1:]), 'note': 'Protected annotation'}])
        def spec(k): return {'key': k, 'sha256': inspect_pdf(self.f.pdf)['sha256'], 'version': 'official', 'evidence': ['Same version verified']}
        prune = {k: request[k] for k in ('schema', 'library', 'identity')}
        prune.update(parent_key=result['native']['parentKey'], keep=spec(attachments[0]['key']),
                     candidates=[spec(attachments[1]['key']), spec(attachments[2]['key']), spec('ZZZZZZZZ')])
        result = executor.run(prune, 'prune'); self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['native']['trashed'], [attachments[1]['key']])
        self.assertEqual(len(result['native']['skipped']), 2)
        self.assertEqual(sum(x['event'] == 'trash' for x in self.f.control()['events']), 1)

    def test_changed_source_cannot_change_original_operation(self):
        executor = self.f.executor(); self.f.control(config={'failImport': 1})
        result = executor.run(self.f.request()); self.assertEqual(result['state'], 'failed')
        self.f.pdf.write_bytes(self.f.pdf.read_bytes() + b'\nchanged')
        with self.assertRaisesRegex(LibraryError, 'pdf_hash_mismatch'):
            executor.resume(result['operation_id'])

    def test_prune_preserves_embedded_annotations_and_linked_independent_notes(self):
        from pypdf.generic import ArrayObject, DictionaryObject, NameObject
        annotated = self.f.root / 'annotated.pdf'
        writer = PdfWriter(); page = writer.add_blank_page(612, 792)
        page[NameObject('/Annots')] = ArrayObject([writer._add_object(DictionaryObject({
            NameObject('/Type'): NameObject('/Annot'), NameObject('/Subtype'): NameObject('/Text')}))])
        with annotated.open('wb') as stream:
            writer.write(stream)
        executor = self.f.executor(); request = self.f.request()
        result = executor.run(request)
        parent = result['native']['parentKey']
        parent_id = int(parent[1:])
        state = self.f.control(seed=[
            {'itemType': 'attachment', 'parentID': parent_id, 'contentType': 'application/pdf', 'file': str(annotated)},
            {'itemType': 'attachment', 'parentID': parent_id, 'contentType': 'application/pdf', 'file': str(self.f.pdf)}])
        candidates = [i['key'] for i in state['items'] if i['data']['itemType'] == 'attachment'][-2:]
        self.f.control(seed=[{'itemType': 'note', 'note': '<p>Reading link zotero://open-pdf/library/items/' + candidates[1] + '</p>'}])
        def spec(k, p): return {'key': k, 'sha256': inspect_pdf(p)['sha256'], 'version': 'official', 'evidence': ['Version verified']}
        prune = {k: request[k] for k in ('schema', 'library', 'identity')}
        prune.update(parent_key=parent, keep=spec(result['native']['attachment']['key'], self.f.pdf),
                     candidates=[spec(candidates[0], annotated), spec(candidates[1], self.f.pdf)])
        result = executor.run(prune, 'prune')
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['native']['trashed'], [])
        self.assertEqual({x['reason'] for x in result['native']['skipped']},
                         {'candidate_pdf_inspection_unknown', 'candidate_has_linked_notes'})

    def test_superseded_version_requires_business_evidence(self):
        executor = self.f.executor(); request = self.f.request(); result = executor.run(request)
        parent = result['native']['parentKey']
        state = self.f.control(seed=[{'itemType': 'attachment', 'parentID': int(parent[1:]),
            'contentType': 'application/pdf', 'file': str(self.f.pdf)}])
        candidate_key = state['items'][-1]['key']
        def spec(k, version): return {'key': k, 'sha256': inspect_pdf(self.f.pdf)['sha256'],
            'version': version, 'evidence': ['Business verified official version supersedes this preprint']}
        prune = {k: request[k] for k in ('schema', 'library', 'identity')}
        prune.update(parent_key=parent, keep=spec(result['native']['attachment']['key'], 'official'),
                     candidates=[spec(candidate_key, 'preprint')])
        with self.assertRaisesRegex(LibraryError, 'prune_version_not_verified'):
            executor.run(prune, 'prune')
        prune['candidates'][0]['disposition'] = 'superseded'
        result = executor.run(prune, 'prune')
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['native']['trashed'], [candidate_key])

    def test_existing_normalized_title_and_doi_are_reused(self):
        self.f.control(seed=[{'itemType': 'journalArticle', 'fields': {
            'title': 'VERIFIED   article', 'DOI': 'http://dx.doi.org/10.1234/fixture'}}])
        executor = self.f.executor()
        self.assertEqual([x['key'] for x in executor.client.find({'type': 'user'}, doi='10.1234/fixture')], ['T0000001'])
        result = executor.run(self.f.request())
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['native']['parentKey'], 'T0000001')

    def test_local_operation_lock(self):
        operation_id = str(uuid.uuid4())
        with self.f.store.lock(operation_id):
            with self.assertRaisesRegex(LibraryError, 'operation_busy'):
                with self.f.store.lock(operation_id):
                    pass


class RequestTests(unittest.TestCase):
    def test_rejects_credentials_javascript_and_weak_identity(self):
        base = {'schema': 1, 'library': {'type': 'user'}, 'identity': {'title': 'X', 'evidence': ['Verified']}}
        with self.assertRaisesRegex(LibraryError, 'identity_evidence_insufficient'):
            validate(base)
        base['identity']['doi'] = '10.1234/example'
        for extra in ({'token': 'secret'}, {'javascript': 'return Zotero'}, {'pdf': {'path': 'relative'}}):
            with self.assertRaises(LibraryError):
                validate({**base, **extra})


if __name__ == '__main__':
    unittest.main()
