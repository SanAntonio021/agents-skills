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
