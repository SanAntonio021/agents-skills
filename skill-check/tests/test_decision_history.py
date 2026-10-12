import copy
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/run_weekly_skill_review.py'
SPEC = importlib.util.spec_from_file_location('decision_history_review', SCRIPT)
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


def observation(evidence='old'):
    return {'id': 'stable-item', 'source': 'hygiene', 'severity': 'critical',
            'queueable': True, 'evidence_fingerprint': evidence,
            'proposal_fingerprint': 'proposal', 'source_fingerprint': 'source',
            'proposal': {'summary': 'Review item'}, 'evidence_summary': evidence}


def test_changed_evidence_archives_rationale_facts_and_execution_without_reapproval():
    state = REVIEW.new_state()
    REVIEW.merge_observations(state, [observation()], '2026-09-05')
    current = state['findings']['stable-item']
    current.update(status='completed', decision={'value': 'approved', 'reason_summary': 'Exact user authorization'},
                   facts=[{'answer_summary': 'Known historical material'}],
                   execution={'outcome': 'success', 'commit': 'abc'})
    previous = copy.deepcopy(current)
    REVIEW.merge_observations(state, [observation('new')], '2026-09-08')
    archived = current['history'][-1]['previous']
    for key in ('decision', 'execution', 'facts', 'status', 'proposal', 'evidence_fingerprint'):
        assert archived[key] == previous[key]
    assert 'decision' not in current and 'execution' not in current
    assert current['status'] != 'completed'
    current['facts'].append({'answer_summary': 'New fact'})
    assert archived['facts'] == previous['facts']


def test_unchanged_evidence_keeps_rejection_without_new_history_or_question():
    state = REVIEW.new_state()
    REVIEW.merge_observations(state, [observation()], '2026-09-05')
    current = state['findings']['stable-item']
    current.update(status='rejected', decision={'value': 'rejected', 'reason_summary': 'No benefit'})
    state['queue'] = []
    REVIEW.merge_observations(state, [observation()], '2026-09-08')
    assert current['decision']['reason_summary'] == 'No benefit'
    assert current['status'] == 'rejected'
    assert current['history'] == [] and state['queue'] == []


def test_resolved_unreviewed_candidate_reappears_and_requeues_once():
    state = REVIEW.new_state()
    item = observation()
    item.update(source='upstream', severity='medium')
    REVIEW.merge_observations(state, [item], '2026-10-10')
    current = state['findings'][item['id']]
    REVIEW.merge_observations(state, [], '2026-10-11')
    assert current['status'] == 'resolved' and state['queue'] == []
    # Routine quota does not suppress an already admitted candidate returning.
    for index in range(REVIEW.ROUTINE_QUEUE_LIMIT):
        state['findings'][f'quota-{index}'] = {'routine_admitted_date': '2026-10-12'}
    result = REVIEW.merge_observations(state, [item], '2026-10-12')
    assert current['status'] == 'queued'
    assert result['requeued_routine'] == 1
    assert state['queue'] == [item['id']]
    assert 'resolved_date' not in current
    saved = copy.deepcopy(current)
    REVIEW.merge_observations(state, [item], '2026-10-12')
    assert current == saved and state['queue'] == [item['id']]


def test_resolved_reviewed_or_executed_items_do_not_reappear_as_unreviewed():
    for retained in ({'decision': {'value': 'approved'}},
                     {'execution': {'outcome': 'failed'}},
                     {'facts': [{'answer_summary': 'User fact'}]}):
        state = REVIEW.new_state()
        item = observation()
        REVIEW.merge_observations(state, [item], '2026-10-10')
        current = state['findings'][item['id']]
        current.update(status='resolved', **retained)
        state['queue'] = []
        REVIEW.merge_observations(state, [item], '2026-10-12')
        assert current['status'] == 'resolved' and state['queue'] == []
        for key, value in retained.items():
            assert current[key] == value


def test_returning_to_exact_historical_fact_closure_reuses_facts_only():
    state = REVIEW.new_state()
    item = observation()
    REVIEW.merge_observations(state, [item], '2026-10-10')
    current = state['findings'][item['id']]
    decision = {'value': 'closed_after_facts', 'reason_summary': 'Verified maintenance text'}
    facts = [{'answer_summary': 'Not a business request'}]
    current.update(status='closed', decision=copy.deepcopy(decision), facts=copy.deepcopy(facts))
    REVIEW.merge_observations(state, [observation('other-window')], '2026-10-12')
    assert current['status'] == 'queued' and 'decision' not in current
    REVIEW.merge_observations(state, [item], '2026-10-10')
    assert current['status'] == 'closed' and state['queue'] == []
    assert current['decision'] == decision and current['facts'] == facts
    assert 'execution' not in current
    saved = copy.deepcopy(current)
    REVIEW.merge_observations(state, [item], '2026-10-10')
    assert current == saved
    current['facts'][0]['answer_summary'] = 'Mutated active copy'
    assert current['history'][0]['previous']['facts'] == facts


def test_historical_closure_requires_all_three_fingerprints():
    for key in ('evidence_fingerprint', 'proposal_fingerprint', 'source_fingerprint'):
        state = REVIEW.new_state()
        item = observation()
        REVIEW.merge_observations(state, [item], '2026-10-10')
        current = state['findings'][item['id']]
        current.update(status='closed', decision={'value': 'closed_after_facts'})
        REVIEW.merge_observations(state, [observation('other')], '2026-10-12')
        changed = copy.deepcopy(item)
        changed[key] = 'new-fingerprint'
        REVIEW.merge_observations(state, [changed], '2026-10-10')
        assert current['status'] == 'queued' and 'decision' not in current


def test_history_never_reuses_approval_rejection_or_executed_closure():
    for status, decision, execution in (
        ('completed', 'approved', {'outcome': 'success'}),
        ('rejected', 'rejected', None),
        ('closed', 'closed_after_facts', {'outcome': 'failed'}),
    ):
        state = REVIEW.new_state()
        item = observation()
        REVIEW.merge_observations(state, [item], '2026-10-10')
        current = state['findings'][item['id']]
        current.update(status=status, decision={'value': decision})
        if execution:
            current['execution'] = execution
        REVIEW.merge_observations(state, [observation('other')], '2026-10-12')
        REVIEW.merge_observations(state, [item], '2026-10-10')
        assert current['status'] == 'queued'
        assert 'decision' not in current and 'execution' not in current


def test_newer_nonclosure_supersedes_old_exact_closure():
    state = REVIEW.new_state()
    item = observation()
    REVIEW.merge_observations(state, [item], '2026-10-10')
    current = state['findings'][item['id']]
    current.update(status='closed', decision={'value': 'closed_after_facts'})
    REVIEW.merge_observations(state, [observation('other')], '2026-10-12')
    newer_review = {**copy.deepcopy(item), 'status': 'rejected',
                    'decision': {'value': 'rejected'}}
    current['history'].append({'event': 'fingerprint_changed', 'previous': newer_review})
    REVIEW.merge_observations(state, [item], '2026-10-10')
    assert current['status'] == 'queued' and 'decision' not in current


def test_incomplete_historical_fingerprints_do_not_prove_identical_evidence():
    state = REVIEW.new_state()
    item = observation()
    item['proposal_fingerprint'] = None
    REVIEW.merge_observations(state, [item], '2026-10-10')
    current = state['findings'][item['id']]
    current.update(status='closed', decision={'value': 'closed_after_facts'})
    REVIEW.merge_observations(state, [observation('other')], '2026-10-12')
    del current['history'][0]['previous']['proposal_fingerprint']
    REVIEW.merge_observations(state, [item], '2026-10-10')
    assert current['status'] == 'queued' and 'decision' not in current


def test_existing_legacy_reopened_queue_recovers_on_same_evidence_scan():
    for status in ('queued', 'deferred', 'facts'):
        state = REVIEW.new_state()
        item = observation()
        REVIEW.merge_observations(state, [item], '2026-10-10')
        current = state['findings'][item['id']]
        closed = {**copy.deepcopy(item), 'status': 'closed',
                  'decision': {'value': 'closed_after_facts', 'reason_summary': 'Known false positive'},
                  'facts': [{'answer_summary': 'Verified original context'}]}
        # Persisted result of the old merger processing A(closed) -> B -> A.
        current['history'] = [
            {'event': 'fingerprint_changed', 'previous': closed},
            {'event': 'fingerprint_changed', 'previous': {**observation('B'), 'status': 'queued'}},
            {'event': 'fingerprint_changed', 'previous': {**copy.deepcopy(item), 'status': 'queued', 'facts': []}},
        ]
        current['status'] = status
        before_history = copy.deepcopy(current['history'])
        REVIEW.merge_observations(state, [item], '2026-10-10')
        assert current['status'] == 'closed' and state['queue'] == []
        assert current['decision'] == closed['decision']
        assert current['facts'] == closed['facts']
        assert current['history'] == before_history


def test_legacy_reopened_queue_with_new_facts_keeps_them_for_review():
    state = REVIEW.new_state()
    item = observation()
    REVIEW.merge_observations(state, [item], '2026-10-10')
    current = state['findings'][item['id']]
    current['history'] = [{'previous': {**copy.deepcopy(item), 'status': 'closed',
                           'decision': {'value': 'closed_after_facts'}}}]
    current.update(status='facts', facts=[{'answer_summary': 'New user clarification'}])
    REVIEW.merge_observations(state, [item], '2026-10-10')
    assert current['status'] == 'facts'
    assert current['facts'] == [{'answer_summary': 'New user clarification'}]
    assert 'decision' not in current
