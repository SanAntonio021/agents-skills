import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('receipt_review', Path(__file__).resolve().parents[1] / 'scripts/run_weekly_skill_review.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def setup_recovery(tmp_path):
    sha = 'a' * 40
    item = dict(finding_id='f', evidence_fingerprint='e', proposal_fingerprint='p', source_fingerprint='s',
                status='pending', skills=['alpha'], requires_runtime_sync=True, blocked_by=[])
    finding = dict(id='f', source='upstream', status='resolved', severity='high', title='candidate', evidence_summary='approved update', evidence_fingerprint='e',
                   proposal_fingerprint='p', source_fingerprint='s',
                   decision=dict(value='approved', evidence_fingerprint='e', proposal_fingerprint='p'))
    batch = dict(id='b', status='stale', stale_reason='finding no longer appears in the latest scan',
                 decided_at='2026-10-12T15:00:00+08:00', execution_root='isolated', items=[item])
    args = SimpleNamespace(outcome='success', commit=sha, remote_sha=sha)
    layer = dict(exists=True, equal_to_source=True, file_count=2, manifest_sha256='hash', missing=[], extra=[], hash_mismatch=[])
    for option, verify in [('sync_receipt', False), ('verify_receipt', True)]:
        receipt = dict(ok=True, exit_code=0, status='runtime_active', verify_only=verify,
                       expected_remote_commit=sha, source=dict(release_commit=sha, changed_skills=['alpha'], source_root='isolated/source'),
                       non_target_unchanged=None, allow_historical_commit=True, expected_base_commit='', expected_runtime_local_files=[],
                       cc_switch_metadata=dict(valid=True, issues=[]), errors=[],
                       skills=[dict(name='alpha', action='already_current', verified=True, layers={k:copy.deepcopy(layer) for k in ['source','cc_switch','claude','codex']})])
        path = tmp_path / (option+'.json')
        path.write_text(json.dumps(receipt), encoding='utf-8')
        setattr(args, option, path)
        setattr(args, 'expected_'+option+'_sha256', hashlib.sha256(path.read_bytes()).hexdigest())
    return args, batch, item, finding


def test_exact_receipts_allow_record_only_recovery(tmp_path):
    args, batch, item, finding = setup_recovery(tmp_path)
    assert R.missing_observation_recovery_error(args,batch,item,finding) is None
    state = R.new_state(); state['findings']={'f':finding}; state['batches']=[batch]
    path=tmp_path/'state.json'; R.save_state(path,state)
    args.__dict__.update(state=path,lock_timeout=1,batch_id='b',finding_id='f',
        recover_missing_observation=True,expected_proposal_fingerprint='p',synced_skill=['alpha'],sync_status='verified',details='verified receipts')
    result,code=R.record_execution_command(args)
    assert code==0 and result['batch_status']=='completed'
    saved,_=R.load_state(path)
    assert saved['findings']['f']['execution']['recovery']['verify_receipt_sha256']==args.expected_verify_receipt_sha256
    assert saved['batches'][0]['stale_reason']==batch['stale_reason']


def test_recovery_refuses_changed_or_unapproved_scope(tmp_path):
    for field,value in [('stale_reason','fingerprint changed'),('decided_at',None),('execution_root',None)]:
        args,batch,item,finding=setup_recovery(tmp_path);batch[field]=value
        assert R.missing_observation_recovery_error(args,batch,item,finding)
    for field,value in [('source_fingerprint','new'),('evidence_fingerprint','new'),('proposal_fingerprint','new'),('status','rejected')]:
        args,batch,item,finding=setup_recovery(tmp_path);finding[field]=value
        assert R.missing_observation_recovery_error(args,batch,item,finding)
    args,batch,item,finding=setup_recovery(tmp_path);finding['decision']['value']='rejected'
    assert R.missing_observation_recovery_error(args,batch,item,finding)
    args,batch,item,finding=setup_recovery(tmp_path);batch['items'].append(dict(status='pending'))
    assert R.missing_observation_recovery_error(args,batch,item,finding)


def test_receipt_hash_sha_scope_and_layers_are_enforced(tmp_path):
    args,batch,item,finding=setup_recovery(tmp_path);args.expected_verify_receipt_sha256='wrong'
    assert R.missing_observation_recovery_error(args,batch,item,finding)
    for mutation in ['sha','scope','mode','metadata','layer']:
        args,batch,item,finding=setup_recovery(tmp_path)
        receipt=json.loads(args.verify_receipt.read_text())
        if mutation=='sha':receipt['expected_remote_commit']='b'*40
        if mutation=='scope':receipt['source']['changed_skills']=['other']
        if mutation=='mode':receipt['verify_only']=False
        if mutation=='metadata':receipt['cc_switch_metadata']['valid']=False
        if mutation=='layer':receipt['skills'][0]['layers']['codex']['hash_mismatch']=['file']
        args.verify_receipt.write_text(json.dumps(receipt))
        args.expected_verify_receipt_sha256=hashlib.sha256(args.verify_receipt.read_bytes()).hexdigest()
        assert R.missing_observation_recovery_error(args,batch,item,finding)


def test_scan_preserves_only_exact_authorized_execution_pending(tmp_path):
    args,batch,item,finding=setup_recovery(tmp_path)
    batch['status']='ready';finding['status']='execution_pending'
    state=R.new_state();state['batches']=[batch];state['findings']={'f':finding}
    R.merge_observations(state,[], '2026-10-12')
    assert batch['status']=='ready' and finding['status']=='execution_pending'
    finding['source_fingerprint']='changed'
    R.merge_observations(state,[], '2026-10-12')
    assert batch['status']=='stale' and finding['status']=='resolved'


def test_receipt_utf16_missing_invalid_and_scope_mismatch(tmp_path):
    args,batch,item,finding=setup_recovery(tmp_path)
    raw=args.verify_receipt.read_text(encoding='utf-8')
    args.verify_receipt.write_text(raw,encoding='utf-16')
    args.expected_verify_receipt_sha256=hashlib.sha256(args.verify_receipt.read_bytes()).hexdigest()
    assert R.missing_observation_recovery_error(args,batch,item,finding) is None
    for change in ('missing','badjson','badsha','root','base','historical','local'):
        args,batch,item,finding=setup_recovery(tmp_path)
        receipt=json.loads(args.verify_receipt.read_text())
        if change=='missing':args.verify_receipt.unlink()
        elif change=='badjson':args.verify_receipt.write_text('{')
        elif change=='badsha':args.expected_verify_receipt_sha256='invalid'
        elif change=='non_target':
            r=json.loads(args.sync_receipt.read_text());r['non_target_unchanged']=None
            args.sync_receipt.write_text(json.dumps(r));args.expected_sync_receipt_sha256=hashlib.sha256(args.sync_receipt.read_bytes()).hexdigest()
        else:
            if change=='root':receipt['source']['source_root']='other'
            if change=='base':receipt['expected_base_commit']='other'
            if change=='historical':receipt['allow_historical_commit']=False
            if change=='local':receipt['expected_runtime_local_files']=['other']
            args.verify_receipt.write_text(json.dumps(receipt))
        if change not in ('missing','badsha'):args.expected_verify_receipt_sha256=hashlib.sha256(args.verify_receipt.read_bytes()).hexdigest()
        assert R.missing_observation_recovery_error(args,batch,item,finding)


def test_written_sync_requires_non_target_proof(tmp_path):
    args,batch,item,finding=setup_recovery(tmp_path)
    receipt=json.loads(args.sync_receipt.read_text())
    receipt['background']={'processed_skills':['alpha']}
    receipt['skills'][0]['action']='updated'
    for value in (None, False, True):
        receipt['non_target_unchanged']=value
        args.sync_receipt.write_text(json.dumps(receipt))
        args.expected_sync_receipt_sha256=hashlib.sha256(args.sync_receipt.read_bytes()).hexdigest()
        error=R.missing_observation_recovery_error(args,batch,item,finding)
        assert (error is None) is (value is True)


def test_sync_and_verify_must_agree_on_manifest_and_file_count(tmp_path):
    for key, value in [('manifest_sha256', 'other'), ('file_count', 3)]:
        args,batch,item,finding=setup_recovery(tmp_path)
        receipt=json.loads(args.verify_receipt.read_text())
        for layer in receipt['skills'][0]['layers'].values():
            layer[key]=value
        args.verify_receipt.write_text(json.dumps(receipt))
        args.expected_verify_receipt_sha256=hashlib.sha256(args.verify_receipt.read_bytes()).hexdigest()
        assert R.missing_observation_recovery_error(args,batch,item,finding)=='sync and VerifyOnly file manifests differ'


def test_failed_and_malformed_receipt_structures_are_refused(tmp_path):
    for field in ('source', 'cc_switch_metadata', 'background', 'skills', 'layers'):
        args,batch,item,finding=setup_recovery(tmp_path)
        receipt=json.loads(args.verify_receipt.read_text())
        if field=='layers':
            receipt['skills'][0]['layers']=None
        else:
            receipt[field]=None
        args.verify_receipt.write_text(json.dumps(receipt))
        args.expected_verify_receipt_sha256=hashlib.sha256(args.verify_receipt.read_bytes()).hexdigest()
        assert R.missing_observation_recovery_error(args,batch,item,finding)=='invalid verify_receipt structure'
