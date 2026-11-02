"""Identity consistency and zero-content-write rejection in the isolated native model."""
import unittest
import test_execution


class IdentityTests(unittest.TestCase):
    setUp = test_execution.NativeExecutionTests.setUp
    tearDown = test_execution.NativeExecutionTests.tearDown

    def seed(self, fields, **extra):
        state = self.f.control(seed=[{'itemType': 'journalArticle', 'fields': fields, **extra}])
        return state['items'][-1]['key']

    def test_doi_forms_are_equal_in_validation_query_native_and_readback(self):
        from zotero_library.request import validate
        key = self.seed({'title': 'Verified article', 'DOI': ' DOI: HTTP://DX.DOI.ORG/10.1234/Fixture '})
        executor = self.f.executor()
        for value in ['10.1234/FIXTURE', ' doi:10.1234/fixture ', 'https://doi.org/10.1234/fixture',
                      'http://dx.doi.org/10.1234/fixture', ' DOI: https://doi.org/10.1234/fixture ']:
            with self.subTest(value=value):
                request = self.f.request(doi=value)
                self.assertEqual(validate(request)['identity']['doi'], '10.1234/fixture')
                self.assertEqual(executor.client.find(request['library'], doi=value)[0]['key'], key)
                result = executor.run(request)
                self.assertEqual(result['state'], 'completed', result)
                self.assertEqual(result['native']['parentKey'], key)
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)

    def test_missing_stored_doi_reuses_with_independent_identity_without_editing_metadata(self):
        url = 'https://publisher.invalid/verified'
        key = self.seed({'title': 'VERIFIED   article', 'url': url})
        request = self.f.request(); request['identity']['url'] = url
        before = self.f.control()['items'][0]['data']
        result = self.f.executor().run(request)
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['native']['parentKey'], key)
        after = self.f.control()['items'][0]['data']
        for field in ('title', 'DOI', 'url', 'creators', 'tags'):
            self.assertEqual(before.get(field), after.get(field))

    def test_missing_request_doi_uses_title_creators_and_year(self):
        creators = [{'creatorType': 'author', 'firstName': 'A', 'lastName': 'Li'}]
        key = self.seed({'title': 'Verified article', 'DOI': '10.1234/fixture', 'date': '2023-05-01'}, creators=creators)
        request = self.f.request(); del request['identity']['doi']
        request['identity'].update(creators=creators, date='2023')
        result = self.f.executor().run(request)
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['native']['parentKey'], key)

    def test_missing_doi_without_independent_evidence_refuses_title_only_merge(self):
        self.seed({'title': 'Verified article'})
        before = self.f.control()
        result = self.f.executor().run(self.f.request())
        self.assertEqual(result['state'], 'failed', result)
        after = self.f.control()
        self.assertEqual(before['items'], after['items'])
        self.assertEqual(before['collections'], after['collections'])
        self.assertEqual(before['events'], after['events'])

    def test_conflicting_doi_title_author_or_year_never_writes(self):
        creators = [{'creatorType': 'author', 'lastName': 'Li'}]
        key = self.seed({'title': 'Verified article', 'DOI': '10.1234/wrong', 'date': '2023'}, creators=creators)
        before = self.f.control()
        request = self.f.request(); request['parent_key'] = key
        result = self.f.executor().run(request)
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(before['items'], self.f.control()['items'])
        self.assertEqual(before['collections'], self.f.control()['collections'])
        self.assertEqual(before['events'], self.f.control()['events'])

    def test_same_doi_different_title_and_multiple_matches_require_review(self):
        self.seed({'title': 'Different scientific article', 'DOI': '10.1234/fixture'})
        self.seed({'title': 'Verified article', 'DOI': '10.1234/fixture'})
        before = self.f.control()
        result = self.f.executor().run(self.f.request())
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(before['items'], self.f.control()['items'])
        self.assertEqual(before['events'], self.f.control()['events'])

    def test_doi_empty_result_still_finds_title_candidate(self):
        key = self.seed({'title': 'Verified article', 'url': 'https://publisher.invalid/verified'})
        request = self.f.request(); request['identity']['url'] = 'https://publisher.invalid/verified'
        client = self.f.client()
        self.assertEqual(client.find(request['library'], doi=request['identity']['doi']), [])
        resolved = client.resolve(request)
        self.assertEqual(resolved['state'], 'matched', resolved)
        self.assertEqual(resolved['parent_key'], key)

    def test_target_changes_after_lookup_native_refuses_before_content_write(self):
        key = self.seed({'title': 'Verified article', 'DOI': '10.1234/fixture'})
        request = self.f.request(); request['parent_key'] = key
        executor = self.f.executor(); prepare = executor.client.prepare
        def changed(value):
            caps = prepare(value)
            self.f.control(update={'key': key, 'fields': {'DOI': '10.1234/changed'}})
            return caps
        executor.client.prepare = changed
        result = executor.run(request)
        self.assertEqual(result['state'], 'failed', result)
        state = self.f.control()
        self.assertEqual(len(state['items']), 1)
        self.assertEqual(state['collections'], [])
        self.assertFalse(any(x['event'] == 'import' for x in state['events']))

    def test_same_doi_with_author_or_year_conflict_stops(self):
        authors = [{'creatorType': 'author', 'lastName': 'Li'}]
        key = self.seed({'title': 'Verified article', 'DOI': '10.1234/fixture', 'date': '2023'}, creators=authors)
        for change in ({'date': '2024'}, {'creators': [{'creatorType': 'author', 'lastName': 'Other'}]}):
            request = self.f.request(); request['parent_key'] = key
            request['identity'].update(change)
            before = self.f.control()
            self.assertEqual(self.f.client().resolve(request)['state'], 'review_required')
            self.assertEqual(self.f.executor().run(request)['state'], 'failed')
            for field in ('items', 'collections', 'events'):
                self.assertEqual(before[field], self.f.control()[field])

    def test_multiple_matching_parents_are_not_chosen(self):
        for _ in range(2):
            self.seed({'title': 'Verified article', 'DOI': '10.1234/fixture'})
        before = self.f.control()
        self.assertEqual(self.f.client().resolve(self.f.request())['state'], 'review_required')
        result = self.f.executor().run(self.f.request())
        self.assertEqual(result['native']['error'], 'duplicate_parents_require_review')
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], self.f.control()[field])

    def test_read_failure_is_never_treated_as_missing_parent(self):
        from unittest.mock import patch
        from zotero_library.errors import LibraryError
        request = self.f.request(); request['parent_key'] = 'T0000001'
        client = self.f.client()
        with patch.object(client, 'get', side_effect=LibraryError('local_api_read_failed')):
            with self.assertRaisesRegex(LibraryError, 'local_api_read_failed'):
                client.resolve(request)


if __name__ == '__main__':
    unittest.main()
