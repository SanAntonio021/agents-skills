import tempfile
import unittest

from test_execution import Fixture
from zotero_library.errors import LibraryError
from zotero_library.request import validate


class MembershipManagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(self.tmp.name)
        self.f.control(seed=[{'itemType': 'journalArticle', 'fields': {'title': 'SCIS article'}}],
            seedCollections=[
                {'key': 'WORKSPC1', 'name': '100Gbps1km'},
                {'key': 'PAPERS01', 'name': '论文', 'parentCollection': 'WORKSPC1'},
                {'key': 'SCIS2026', 'name': 'SCIS 2026 IQ-MIMO｜论文参考文献',
                 'parentCollection': 'PAPERS01'},
                {'key': 'OTHERWS1', 'name': 'Other workspace'},
                {'key': 'OLDCAT01', 'name': 'old topic', 'parentCollection': 'PAPERS01',
                 'itemIndexes': [0]},
                {'key': 'OTHERREF', 'name': '论文', 'parentCollection': 'OTHERWS1',
                 'itemIndexes': [0]},
            ])

    def tearDown(self):
        self.f.close()
        self.tmp.cleanup()

    def request(self, **changes):
        item_key = self.f.control()['items'][0]['key']
        item = self.f.client().get({'type': 'user'}, item_key, children=False)
        self.item_key = item_key
        request = {'schema': 1, 'library': {'type': 'user'}, 'key': item['key'],
            'expected_version': item['version'],
            'expected_collections': item['data']['collections'],
            'workspace_root': 'WORKSPC1', 'target_collection': 'SCIS2026'}
        request.update(changes)
        return request

    def test_moves_only_within_workspace_and_preserves_other_workspace(self):
        result = self.f.executor().run(self.request(), 'membership')
        self.assertEqual(result['state'], 'completed', result)
        saved = self.f.client().get({'type': 'user'}, self.item_key, children=False)
        self.assertEqual(set(saved['data']['collections']), {'SCIS2026', 'OTHERREF'})
        self.assertTrue(result['readback_verified'])

    def test_stale_item_version_stops_before_write(self):
        request = self.request(expected_version=999)
        before = self.f.control()['events']
        result = self.f.executor().run(request, 'membership')
        self.assertEqual(result['error'], 'membership_state_changed_requires_review')
        self.assertEqual(before, self.f.control()['events'])

    def test_repeated_request_recognizes_already_applied_target(self):
        request = self.request()
        first = self.f.executor().run(request, 'membership')
        self.assertEqual(first['state'], 'completed', first)
        second = self.f.executor().run(request, 'membership')
        self.assertEqual(second['state'], 'completed', second)
        writes = [event for event in self.f.control()['events']
                  if event.get('event') == 'api_write' and event.get('resource') == 'items']
        self.assertEqual(len(writes), 1)

    def test_target_must_be_within_workspace_root(self):
        result = self.f.executor().run(self.request(target_collection='OTHERREF'), 'membership')
        self.assertEqual(result['error'], 'membership_target_outside_workspace')

    def test_request_rejects_duplicate_old_memberships(self):
        request = self.request()
        request['expected_collections'] *= 2
        with self.assertRaisesRegex(LibraryError, 'invalid_expected_collections'):
            validate(request, 'membership')


if __name__ == '__main__':
    unittest.main()
