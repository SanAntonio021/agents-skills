"""Append-only tags on isolated Zotero API fixtures."""
import tempfile
import unittest

from test_execution import Fixture


class TagManagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(self.tmp.name)
        self.f.control(seed=[{'key': 'PAPER001', 'itemType': 'journalArticle',
                              'tags': [{'tag': 'existing', 'type': 1}],
                              'fields': {'title': 'Kept article'}},
                             {'key': 'NOTE0001', 'itemType': 'note',
                              'fields': {'parentItem': 'PAPER001', 'note': 'Keep me'}}])

    def tearDown(self):
        self.f.close()
        self.tmp.cleanup()

    def request(self):
        item = self.f.client().get({'type': 'user'}, 'PAPER001', children=False)
        return {'schema': 1, 'library': {'type': 'user'}, 'key': 'PAPER001',
                'expected_version': item['version'], 'tags': ['new']}

    def test_append_preserves_existing_content_and_is_idempotent(self):
        request = self.request()
        executor = self.f.executor()
        result = executor.run(request, 'tags')
        self.assertEqual(result['state'], 'completed', result)
        result = executor.run(request, 'tags')
        self.assertEqual(result['state'], 'completed', result)
        item = self.f.client().get({'type': 'user'}, 'PAPER001')
        self.assertEqual(item['data']['tags'], [{'tag': 'existing', 'type': 1}, {'tag': 'new'}])
        self.assertEqual(item['children'][0]['data']['note'], 'Keep me')
        writes = [e for e in self.f.control()['events'] if e['event'] == 'api_write']
        self.assertEqual(len(writes), 1)

    def test_stale_version_does_not_write(self):
        request = self.request()
        request['expected_version'] += 1
        result = self.f.executor().run(request, 'tags')
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(result['error'], 'tag_state_changed_requires_review')
        self.assertFalse([e for e in self.f.control()['events'] if e['event'] == 'api_write'])

    def test_disconnect_recovers_without_duplicate_write(self):
        request = self.request()
        self.f.control(config={'patchDisconnect': True})
        executor = self.f.executor()
        result = executor.run(request, 'tags')
        self.assertEqual(result['state'], 'unknown', result)
        result = executor.resume(result['operation_id'])
        self.assertEqual(result['state'], 'completed', result)
        self.assertTrue(result['readback_verified'])
        writes = [e for e in self.f.control()['events'] if e['event'] == 'api_write']
        self.assertEqual(len(writes), 1)


if __name__ == '__main__':
    unittest.main()
