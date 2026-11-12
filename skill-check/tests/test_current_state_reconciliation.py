import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import current_state_reconciliation as current
import successor_reconciliation as evidence


def run(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=True).stdout


def save(root, name, value):
    path = root / name
    path.write_text(json.dumps(value), encoding='utf-8')
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def case(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    run(source, 'init')
    run(source, 'config', 'user.name', 'Fixture')
    run(source, 'config', 'user.email', 'fixture@example.invalid')
    (source / 'demo').mkdir()
    (source / 'demo/SKILL.md').write_text('Original reference repair\n', encoding='utf-8')
    run(source, 'add', 'demo/SKILL.md')
    run(source, 'commit', '-m', 'Original repair')
    old = run(source, 'rev-parse', 'HEAD').decode().strip()
    (source / 'demo/SKILL.md').write_text('Original reference repair; current behavior\n', encoding='utf-8')
    run(source, 'add', 'demo/SKILL.md')
    run(source, 'commit', '-m', 'Current accepted version')
    sha = run(source, 'rev-parse', 'HEAD').decode().strip()
    run(source, 'update-ref', 'refs/remotes/origin/main', sha)
    roots = {}
    for layer in ['cc_switch', 'claude', 'codex']:
        roots[layer] = tmp_path / layer
        (roots[layer] / 'demo').mkdir(parents=True)
        (roots[layer] / 'demo/SKILL.md').write_bytes(run(source, 'show', sha + ':demo/SKILL.md'))
    args = SimpleNamespace(skills_root=source, reports_root=tmp_path,
                           state=tmp_path / 'weekly-review-state.json')
    original = {'remote_sha': old, 'outcome': 'blocked', 'recorded_at': '2026-11-01'}
    finding = {'id': 'old', 'status': 'waiting_evidence', 'execution': original}
    review = {'finding_id': 'old', 'original_execution_fingerprint': evidence.fingerprint(original),
              'skills': {'demo': {'conclusion': 'Original repair retained in accepted current version',
                                 'checks': [{'path': 'SKILL.md', 'contains': ['Original reference repair']}]}}}
    receipt = {'ok': True, 'exit_code': 0, 'status': 'runtime_active', 'expected_remote_commit': sha,
               'cc_switch_metadata': {'valid': True, 'issues': []},
               'skills': [{'name': 'demo', 'verified': True}], 'errors': []}
    report = {'complete': True, 'date': '2026-11-08', 'generated_at': '2026-11-08T12:00:00+08:00',
              'scope_fingerprint': 'fixture-scope'}
    report_ref = save(tmp_path, 'weekly-review.json', report)
    args.test_state = {'runs': [dict(complete=True, date=report['date'],
                                   completed_at=report['generated_at'], scope_fingerprint='fixture-scope',
                                   report_ref='weekly-review.json')]}
    proposal = {'kind': 'current_state', 'skills': ['demo'],
                'original_execution_fingerprint': evidence.fingerprint(original),
                'scan_evidence': save(tmp_path, 'scan.json', {'status': 'scanned', 'complete': True,
                                                           'state': args.state.name, 'scan_report': 'weekly-review.json',
                                                           'date': '2026-11-08'}),
                'scan_report_evidence': report_ref,
                'semantic_review_evidence': save(tmp_path, 'review.json', review),
                'releases': [{'commit': sha, 'skills': ['demo'],
                              'sync_evidence': save(tmp_path, 'sync.json', dict(receipt, verify_only=False)),
                              'verify_evidence': save(tmp_path, 'verify.json', dict(receipt, verify_only=True))}]}
    return args, finding, proposal, {'skills': ['demo']}, roots


def test_current_state_accepts_later_version_and_preserves_original(case):
    args, finding, proposal, item, roots = case
    before = copy.deepcopy(finding)
    commits, manifests = current.validate_current(args, finding, proposal, item, roots, args.test_state)
    assert commits['demo'] != finding['execution']['remote_sha']
    assert set(manifests['demo']) == {'source', 'cc_switch', 'claude', 'codex'}
    assert finding == before


@pytest.mark.parametrize('failure', ['runtime_edit', 'runtime_extra', 'dirty_source', 'missing_sync',
                                   'scope', 'semantic', 'incomplete_scan', 'wrong_state', 'old_scan',
                                   'bad_metadata', 'string_assertion', 'no_run', 'changed_parameters', 'remote_change'])
def test_contradictory_current_evidence_is_refused(case, failure):
    args, finding, proposal, item, roots = case
    if failure == 'runtime_edit':
        (roots['claude'] / 'demo/SKILL.md').write_text('changed', encoding='utf-8')
    elif failure == 'runtime_extra':
        (roots['codex'] / 'demo/extra.txt').write_text('extra', encoding='utf-8')
    elif failure == 'dirty_source':
        (args.skills_root / 'demo/extra.txt').write_text('unpublished', encoding='utf-8')
    elif failure == 'missing_sync':
        proposal['releases'][0]['sync_evidence'] = proposal['releases'][0]['verify_evidence']
    elif failure == 'scope':
        item['skills'] = ['unrelated']
    elif failure == 'semantic':
        path = Path(proposal['semantic_review_evidence']['path'])
        review = json.loads(path.read_text())
        review['skills']['demo']['checks'][0]['contains'] = ['lost behavior']
        proposal['semantic_review_evidence'] = save(args.reports_root, path.name, review)
    elif failure == 'bad_metadata':
        ref = proposal['releases'][0]['verify_evidence']
        receipt = json.loads(Path(ref['path']).read_text())
        receipt['cc_switch_metadata'] = {'valid': False, 'issues': ['wrong source']}
        proposal['releases'][0]['verify_evidence'] = save(args.reports_root, 'bad-meta.json', receipt)
    elif failure == 'string_assertion':
        ref = proposal['semantic_review_evidence']
        review = json.loads(Path(ref['path']).read_text())
        review['skills']['demo']['checks'][0]['contains'] = 'Original'
        proposal['semantic_review_evidence'] = save(args.reports_root, 'bad-review.json', review)
    elif failure == 'no_run':
        args.test_state = {'runs': []}
    elif failure == 'changed_parameters':
        ref = proposal['releases'][0]['verify_evidence']
        receipt = json.loads(Path(ref['path']).read_text())
        receipt['expected_runtime_local_files'] = ['demo/excluded']
        proposal['releases'][0]['verify_evidence'] = save(args.reports_root, 'bad-params.json', receipt)
    elif failure == 'remote_change':
        original_head = run(args.skills_root, 'rev-parse', 'HEAD').decode().strip()
        (args.skills_root / 'demo/SKILL.md').write_text('New remote behavior\n', encoding='utf-8')
        run(args.skills_root, 'add', 'demo/SKILL.md')
        run(args.skills_root, 'commit', '-m', 'New remote version')
        run(args.skills_root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
        run(args.skills_root, 'checkout', '--detach', original_head)
    else:
        scan = {'complete': failure != 'incomplete_scan', 'state': args.state.name, 'date': '2026-11-08'}
        if failure == 'wrong_state':
            scan['state'] = 'other-state.json'
        if failure == 'old_scan':
            scan['date'] = '2026-10-01'
        proposal['scan_evidence'] = save(args.reports_root, 'bad-scan.json', scan)
    with pytest.raises(ValueError):
        current.validate_current(args, finding, proposal, item, roots, args.test_state)


def test_missing_old_sha_only_allowed_after_scan_resolved(case):
    args, finding, proposal, item, roots = case
    finding['execution']['remote_sha'] = None
    fp = evidence.fingerprint(finding['execution'])
    proposal['original_execution_fingerprint'] = fp
    path = Path(proposal['semantic_review_evidence']['path'])
    review = json.loads(path.read_text())
    review['original_execution_fingerprint'] = fp
    proposal['semantic_review_evidence'] = save(args.reports_root, path.name, review)
    with pytest.raises(ValueError, match='independently resolved'):
        current.validate_current(args, finding, proposal, item, roots, args.test_state)
    finding['status'] = 'resolved'
    current.validate_current(args, finding, proposal, item, roots, args.test_state)


def test_publication_uses_current_receipt_without_rewriting_failure():
    import run_weekly_skill_review as review
    execution = {'outcome': 'blocked', 'sync_status': 'not_run', 'remote_sha': 'a' * 40}
    finding = {'id': 'old', 'status': 'historical', 'execution': execution,
               'successor_reconciliations': [{'kind': 'current_state', 'status': 'superseded_current_verified',
                                            'original_execution_fingerprint': review.fingerprint(execution),
                                            'recorded_at': '2026-11-08'}]}
    state = {'findings': {'old': finding}}
    result = review.publication_status(state)
    assert result['status'] == 'verified'
    assert result['items'][0]['original_history_proven'] is False
    assert result['items'][0]['original_execution_status'] == 'blocked'
    assert execution['outcome'] == 'blocked'
    execution['remote_sha'] = 'b' * 40
    assert review.publication_status(state)['status'] == 'blocked'


@pytest.mark.parametrize('invalid', [False, True])
def test_official_desktop_requires_bound_current_metadata(case, invalid):
    args, finding, proposal, item, roots = case
    release = proposal['releases'][0]
    row = {'id': 'local:demo', 'name': 'demo', 'directory': 'demo',
           'apps': {'claude': True, 'codex': True}}
    source = {'commit': release['commit'], 'manifest': current.source_manifest(args.skills_root, release['commit'], 'demo'),
              'repository': 'fixture/repository', 'official_source': row}
    release['source_receipts'] = {'demo': save(args.reports_root, 'source-receipt.json', source)}
    query = {'status': 'queried', 'exit_code': 0, 'backend': 'official-desktop-cdp',
             'contract_version': 16, 'skills': [copy.deepcopy(row)]}
    if invalid:
        query['skills'][0]['apps']['claude'] = False
    release['metadata_evidence'] = save(args.reports_root, 'official-list.json', query)
    for key in ['sync', 'verify']:
        ref = release[key + '_evidence']
        receipt = json.loads(Path(ref['path']).read_text())
        receipt.update(cc_switch_metadata=None, backend='official-desktop-cdp', helper_contract_version=16,
                       source_repository='fixture/repository')
        receipt['skills'][0]['layers'] = {'cc_switch': True, 'claude': True, 'codex': True}
        release[key + '_evidence'] = save(args.reports_root, key + '-desktop.json', receipt)
    if invalid:
        with pytest.raises(ValueError, match='metadata/source receipt mismatch'):
            current.validate_current(args, finding, proposal, item, roots, args.test_state)
    else:
        current.validate_current(args, finding, proposal, item, roots, args.test_state)


def use_home(case, monkeypatch, storage):
    """Rebuild the runtime under a fixture home so validate_current resolves its own roots."""
    args, _, _, _, roots = case
    home = args.reports_root / 'home'
    monkeypatch.setattr(current.Path, 'home', lambda: home)
    for name in ('CC_SWITCH_CONFIG_DIR', 'CLAUDE_CONFIG_DIR', 'CODEX_HOME'):
        monkeypatch.delenv(name, raising=False)
    blob = (roots['claude'] / 'demo/SKILL.md').read_bytes()
    for directory in ('.claude/skills', '.codex/skills', storage):
        (home / directory / 'demo').mkdir(parents=True)
        (home / directory / 'demo/SKILL.md').write_bytes(blob)
    return home


def name_paths(args, proposal, paths):
    release = proposal['releases'][0]
    for key in ['sync', 'verify']:
        receipt = json.loads(Path(release[key + '_evidence']['path']).read_text())
        receipt['resolved_paths'] = paths
        release[key + '_evidence'] = save(args.reports_root, key + '-paths.json', receipt)


@pytest.mark.parametrize('key', ['cc_switch_skills_root', 'cc_switch_root'])
def test_cc_switch_layer_is_measured_at_the_storage_root_the_receipt_names(case, monkeypatch, key):
    args, finding, proposal, item, _ = case
    home = use_home(case, monkeypatch, '.agents/skills')
    leftover = home / '.cc-switch/skills/demo'
    leftover.mkdir(parents=True)
    (leftover / 'SKILL.md').write_text('stale copy left by a storage migration\n', encoding='utf-8')
    name_paths(args, proposal, {'source_root': str(args.skills_root), key: str(home / '.agents' / 'skills')})
    _, manifests = current.validate_current(args, finding, proposal, item, state=args.test_state)
    assert manifests['demo']['cc_switch'] == manifests['demo']['source']
    name_paths(args, proposal, {key: str(leftover.parent)})
    with pytest.raises(ValueError, match='runtime manifest mismatch: demo/cc_switch'):
        current.validate_current(args, finding, proposal, item, state=args.test_state)


@pytest.mark.parametrize('named', ['exact copy elsewhere', 'relative', 7])
def test_receipt_cannot_point_the_cc_switch_layer_outside_known_storage(case, monkeypatch, named):
    args, finding, proposal, item, roots = case
    use_home(case, monkeypatch, '.agents/skills')
    if named == 'exact copy elsewhere':
        named = str(roots['cc_switch'])
    elif named == 'relative':
        named = '.agents/skills'
    name_paths(args, proposal, {'cc_switch_skills_root': named})
    with pytest.raises(ValueError, match='unknown CC Switch storage root'):
        current.validate_current(args, finding, proposal, item, state=args.test_state)


def test_receipt_without_a_storage_root_keeps_the_config_root_default(case, monkeypatch):
    args, finding, proposal, item, _ = case
    home = use_home(case, monkeypatch, '.cc-switch/skills')
    assert not (home / '.agents').exists()
    current.validate_current(args, finding, proposal, item, state=args.test_state)
    name_paths(args, proposal, {'source_root': str(args.skills_root)})
    current.validate_current(args, finding, proposal, item, state=args.test_state)
