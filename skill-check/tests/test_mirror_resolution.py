import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mirror_resolution as module


@pytest.fixture
def case(monkeypatch, tmp_path):
    sha = 'a' * 40
    decision = {'value': 'approved', 'evidence_fingerprint': 'e', 'proposal_fingerprint': 'p',
                'reason_summary': '不变更技能正文或接受基线'}
    finding = {'kind': 'upstream_diagnostic', 'purpose': 'repair-mirror_blocked',
               'status': 'execution_pending', 'decision': decision, 'evidence_fingerprint': 'e',
               'proposal_fingerprint': 'p', 'source_fingerprint': 's', 'subject': 'pptx:source'}
    batch = {'status': 'ready', 'decided_at': '2026-11-15T19:00:00+08:00'}
    item = {'status': 'pending', 'evidence_fingerprint': 'e', 'proposal_fingerprint': 'p', 'source_fingerprint': 's'}
    scan = {'complete': True, 'date': '2026-11-15', 'scope_fingerprint': 'scope',
            'generated_at': '2026-11-15T20:00:00+08:00', 'components': {'upstream': {'complete': True}}}
    run = {'complete': True, 'date': scan['date'], 'scope_fingerprint': 'scope', 'completed_at': scan['generated_at']}
    upstream = {'source': 'source', 'skill': 'pptx', 'status': 'up_to_date', 'tracking': 'stable_tags',
                'current_commit': sha, 'accepted_commit': sha, 'current_release_tag': 'v1.0.0'}
    mirror = {'id': 'mirror', 'repo_url': 'https://example.test/repo', 'local_origin': 'https://example.test/repo',
              'tracking': 'stable_tags', 'status': 'already_up_to_date', 'local_dirty': False,
              'remote_reachable': True, 'local_repo_valid': True, 'git_dir_matches_registry': True,
              'local_head': sha, 'remote_head': sha, 'after_head': sha, 'local_stable_tag': 'v1.0.0',
              'remote_tag': 'v1.0.0', 'stable_tags': {'v1.0.0': sha}, 'local_path': str(tmp_path)}
    registry = {'id': 'source', 'skill': 'pptx', 'mirror_id': 'mirror',
                'repo_url': mirror['repo_url'], 'accepted_commit': sha}
    monkeypatch.setattr(module, '_git', lambda root, *args: '' if args[0] == 'status' else
                        mirror['repo_url'] if args[0] == 'remote' else sha)
    return [finding, batch, item, scan, upstream, mirror, run, registry]


def test_factual_mirror_resolution_has_no_publication_claim(case):
    assert module.validate(*case) == {'source': 'source', 'skill': 'pptx', 'commit': 'a' * 40, 'stable_tag': 'v1.0.0'}


@pytest.mark.parametrize('index,key,value', [
    (0, 'purpose', 'repair-source'), (0, 'status', 'approved'),
    (1, 'status', 'stale'), (2, 'proposal_fingerprint', 'changed'),
    (3, 'complete', False), (4, 'status', 'review_required'),
    (4, 'accepted_commit', 'b' * 40), (5, 'local_dirty', True),
    (5, 'remote_reachable', False), (5, 'remote_head', 'b' * 40),
    (6, 'scope_fingerprint', 'changed'), (7, 'mirror_id', 'other')])
def test_rejects_stale_or_unrelated_evidence(case, index, key, value):
    case[index][key] = value
    with pytest.raises(ValueError):
        module.validate(*case)


def test_rejects_scan_before_approval(case):
    case[1]['decided_at'] = '2026-11-15T21:00:00+08:00'
    with pytest.raises(ValueError):
        module.validate(*case)


def test_rejects_live_mirror_drift(case, monkeypatch):
    monkeypatch.setattr(module, '_git', lambda *args: 'changed')
    with pytest.raises(ValueError):
        module.validate(*case)


def test_does_not_accept_broad_approval(case):
    case[0]['decision'] = copy.deepcopy(case[0]['decision'])
    case[0]['decision']['reason_summary'] = '同意修改技能正文并发布'
    with pytest.raises(ValueError):
        module.validate(*case)
