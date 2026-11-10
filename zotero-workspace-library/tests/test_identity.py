"""Identity consistency and zero-content-write rejection in the isolated native model."""
import unittest
import test_execution


class IdentityTests(unittest.TestCase):
    setUp = test_execution.NativeExecutionTests.setUp
    tearDown = test_execution.NativeExecutionTests.tearDown

    def seed(self, fields, **extra):
        state = self.f.control(seed=[{'itemType': 'journalArticle', 'fields': fields, **extra}])
        return state['items'][-1]['key']

    def manual_request(self, old_title='ACME-A100 bare-die datasheet'):
        authors = [{'creatorType': 'author', 'name': 'Example Devices'}]
        state = self.f.control(seed=[{'itemType': 'document', 'creators': authors,
            'fields': {'title': old_title, 'date': '2022-10-25'}}])
        old = state['items'][-1]
        request = self.f.request('ACME-M100 amplifier module manual')
        del request['identity']['doi']
        request['identity'].update(creators=authors, date='2022-02-24')
        request['metadata'] = {'itemType': 'document'}
        request['collections'] = [{'path': ['Workspace', '器件手册']}]
        review = {'key': old['key'], 'version': old['version'], 'title': old_title,
                  'evidence': ['Both PDF first pages checked: A100 bare die and M100 module are distinct products.']}
        return request, old, review

    def test_different_manual_same_manufacturer_year_needs_documented_review(self):
        request, old, review = self.manual_request()
        client = self.f.client()
        found = client.resolve(request)
        self.assertEqual(found['state'], 'review_required')
        self.assertEqual(found['candidates'][0]['version'], old['version'])
        self.assertEqual(found['candidates'][0]['key'], old['key'])
        request['distinct_candidates'] = [review]
        self.assertEqual(client.resolve(request)['state'], 'not_found')
        before = client.get(request['library'], old['key'])
        result = self.f.executor().run(request)
        self.assertEqual(result['state'], 'completed', result)
        self.assertNotEqual(result['native']['parentKey'], old['key'])
        self.assertEqual(result['native']['distinctCandidates'], [old['key']])
        self.assertEqual(client.get(request['library'], old['key']), before)
        repeated = self.f.executor().run(request)
        self.assertEqual(repeated['native']['parentKey'], result['native']['parentKey'])
        self.assertEqual(sum(x['event'] == 'import' for x in self.f.control()['events']), 1)
        resolved = client.resolve(request)
        self.assertEqual(resolved['state'], 'matched')
        self.assertEqual(resolved['parent_key'], result['native']['parentKey'])

    def test_distinct_review_cannot_exclude_same_doi_or_same_title(self):
        for same in ('doi', 'title', 'url'):
            with self.subTest(same=same):
                request, old, review = self.manual_request()
                fields = ({'DOI': '10.1234/same'} if same == 'doi' else
                          {'title': request['identity']['title']} if same == 'title' else
                          {'url': 'https://publisher.invalid/same'})
                if same == 'doi':
                    request['identity']['doi'] = fields['DOI']
                if same == 'url':
                    request['identity']['url'] = fields['url']
                self.f.control(update={'key': old['key'], 'fields': fields})
                current = self.f.client().get(request['library'], old['key'], children=False)
                review.update(version=current['version'], title=current['data']['title'])
                request['distinct_candidates'] = [review]
                before = self.f.control()
                result = self.f.executor().run(request)
                self.assertEqual(result['state'], 'failed', result)
                self.assertEqual(result['error'], 'distinct_candidate_identity_conflict')
                for field in ('items', 'collections', 'events'):
                    self.assertEqual(before[field], self.f.control()[field])

    def test_distinct_review_rejects_changed_candidate_before_content_write(self):
        request, old, review = self.manual_request()
        request['distinct_candidates'] = [review]
        self.f.control(update={'key': old['key'], 'fields': {'date': '2023-01-01'}})
        before = self.f.control()
        result = self.f.executor().run(request)
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(result['error'], 'distinct_candidate_changed_requires_review')
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], self.f.control()[field])

    def test_reviewing_one_manual_does_not_hide_other_unresolved_candidates(self):
        request, old, review = self.manual_request()
        self.f.control(seed=[{'itemType': 'document', 'creators': request['identity']['creators'],
            'fields': {'title': 'Unverified related manual', 'date': '2022'}}])
        request['distinct_candidates'] = [review]
        before = self.f.control()
        result = self.f.executor().run(request)
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(result['error'], 'identity_candidates_require_review')
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], self.f.control()[field])

    def test_distinct_reviews_require_evidence_pinned_version_and_unique_keys(self):
        from copy import deepcopy
        from zotero_library.request import validate
        from zotero_library.errors import LibraryError
        request, old, review = self.manual_request()
        bad_reviews = [[{**review, 'evidence': []}], [{**review, 'version': True}],
                       [{**review, 'key': '*'}], [review, review]]
        for reviews in bad_reviews:
            with self.subTest(reviews=reviews):
                bad = deepcopy(request); bad['distinct_candidates'] = reviews
                with self.assertRaises(LibraryError):
                    validate(bad)
        request.update(parent_key=old['key'], distinct_candidates=[review])
        with self.assertRaisesRegex(LibraryError, 'distinct_review_with_explicit_parent'):
            validate(request)

    def test_status_does_not_turn_known_prewrite_rejection_into_unknown(self):
        request, old, review = self.manual_request()
        executor = self.f.executor()
        result = executor.run(request)
        self.assertEqual(result['state'], 'failed')
        before = self.f.control()
        checked = executor.status(result['operation_id'])
        self.assertEqual(checked['state'], 'failed', checked)
        self.assertEqual(checked['error'], 'identity_candidates_require_review')
        self.assertFalse(checked['native']['contentWritesStarted'])
        # Also repair a legacy status check that mislabeled this definite failure.
        checked['state'] = 'unknown'; self.f.store.save(checked)
        self.assertEqual(executor.status(result['operation_id'])['state'], 'failed')
        for field in ('items', 'collections', 'events'):
            self.assertEqual(before[field], self.f.control()[field])

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
        def changed(value, backend='native'):
            caps = prepare(value, backend)
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
