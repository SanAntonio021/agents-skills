"""Collection rename and reparent operations against the isolated Local API."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_execution import Fixture
from zotero_library.errors import LibraryError
from zotero_library.objects import plan_collection_update


class CollectionManagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(self.tmp.name)
        self.f.control(seed=[{'itemType': 'journalArticle', 'fields': {'title': 'Kept article'}}],
            seedCollections=[
                {'key': 'WORKSPC1', 'name': '202607_THz_freq_planning'},
                {'key': 'PAPERS01', 'name': '202607_THz_freq_planning|论文参考文献', 'itemIndexes': [0]},
                {'key': 'CHILD001', 'name': 'reading notes', 'parentCollection': 'PAPERS01'},
            ])

    def tearDown(self):
        self.f.close()
        self.tmp.cleanup()

    def request(self, **changes):
        collection = next(x for x in self.f.client().collections({'type': 'user'})
                          if x['key'] == 'PAPERS01')
        request = {'schema': 1, 'library': {'type': 'user'}, 'key': 'PAPERS01',
            'expected_version': collection['version'],
            'expected_name': collection['data']['name'],
            'expected_parent': collection['data']['parentCollection'] or False,
            'name': '论文', 'parentCollection': 'WORKSPC1'}
        request.update(changes)
        return request

    def test_plan_is_read_only_then_rename_and_move_preserve_contents(self):
        request = self.request()
        client = self.f.client()
        before = self.f.control()
        plan = plan_collection_update(client, request)
        self.assertEqual(plan['state'], 'ready')
        self.assertTrue(plan['write_required'])
        self.assertEqual(before['events'], self.f.control()['events'])

        result = self.f.executor().run(request, 'collection')
        self.assertEqual(result['state'], 'completed', result)
        self.assertTrue(result['readback_verified'])
        state = self.f.control()
        by_key = {x['key']: x for x in state['collections']}
        self.assertEqual(by_key['PAPERS01']['name'], '论文')
        self.assertEqual(by_key['PAPERS01']['parentCollection'], 'WORKSPC1')
        self.assertEqual(by_key['CHILD001']['parentCollection'], 'PAPERS01')
        self.assertIn('PAPERS01', state['items'][0]['data']['collections'])
        self.assertEqual(result['native']['collectionUpdate']['before']['name'],
                         '202607_THz_freq_planning|论文参考文献')
        self.assertTrue(result['native']['collectionUpdate']['changed'])

    def test_already_current_is_idempotent(self):
        result = self.f.executor().run(self.request(), 'collection')
        self.assertEqual(result['state'], 'completed', result)
        no_op = self.f.executor().run(self.request(), 'collection')
        self.assertEqual(no_op['state'], 'completed', no_op)

    def test_duplicate_name_and_cycle_are_rejected_without_writes(self):
        self.f.control(seedCollections=[{'key': 'PAPERS02', 'name': '论文',
                                        'parentCollection': 'WORKSPC1'}])
        before = self.f.control()
        with self.assertRaisesRegex(LibraryError, 'collection_name_conflict'):
            plan_collection_update(self.f.client(), self.request())
        cyclic = self.request(parentCollection='CHILD001')
        with self.assertRaisesRegex(LibraryError, 'collection_cycle'):
            plan_collection_update(self.f.client(), cyclic)
        self.assertEqual(before['events'], self.f.control()['events'])

    def test_changed_source_state_requires_a_fresh_plan(self):
        request = self.request()
        self.f.control(updateCollection={'key': 'PAPERS01', 'fields': {'name': 'user renamed'}})
        with self.assertRaisesRegex(LibraryError, 'collection_state_changed_requires_review'):
            plan_collection_update(self.f.client(), request)

    def test_unknown_readback_resumes_without_duplicate_write(self):
        self.f.control(config={'collectionReadbackFailure': True})
        executor = self.f.executor()
        result = executor.run(self.request(), 'collection')
        self.assertEqual(result['state'], 'unknown', result)
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed', result)
        writes = [event for event in self.f.control()['events'] if event['event'] == 'api_write'
                  and event['resource'] == 'collections']
        self.assertEqual(len(writes), 1)

    def test_cli_plan_and_update(self):
        request_path = Path(self.f.root) / 'collection-request.json'
        request_path.write_text(json.dumps(self.request()), encoding='utf-8')
        entry = Path(__file__).resolve().parents[1] / 'scripts' / 'zotero_library.py'
        common = [sys.executable, str(entry), 'collection', '--request', str(request_path),
                  '--profile', str(self.f.profile), '--base-url', self.f.base,
                  '--state-dir', str(self.f.root / 'operations'), '--json']
        plan = subprocess.run(common[:3] + ['plan'] + common[3:], capture_output=True,
                              text=True, check=True)
        self.assertTrue(json.loads(plan.stdout)['write_required'])
        update = subprocess.run(common[:3] + ['update'] + common[3:], capture_output=True,
                                text=True, check=True)
        result = json.loads(update.stdout)
        self.assertEqual(result['state'], 'completed', result)
        self.assertTrue(result['readback_verified'])


if __name__ == '__main__':
    unittest.main()
