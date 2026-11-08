"""Validate append-only reconciliation evidence without changing history."""
import hashlib
import json
import re
import subprocess
from pathlib import Path


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def validate(original, proposal):
    """Return a reason on missing/contradictory evidence; never infer success."""
    if proposal.get('original_execution_fingerprint') != fingerprint(original):
        return 'original execution fingerprint mismatch'
    sha = original.get('remote_sha')
    if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{40}', sha):
        return 'original remote SHA unavailable'
    if proposal.get('commit') != sha:
        return 'successor commit differs from original release'
    skills = proposal.get('skills')
    if not isinstance(skills, list) or not skills or any(not isinstance(s, str) or not s for s in skills):
        return 'exact Skill scope required'
    if len(set(skills)) != len(skills):
        return 'duplicate Skill scope'
    for key, mode in (('sync', False), ('verify', True)):
        receipt = proposal.get(key, {})
        if not isinstance(receipt, dict):
            return 'invalid receipt'
        if not (receipt.get('ok') is True and receipt.get('exit_code') == 0
                and receipt.get('status') == 'runtime_active'
                and receipt.get('verify_only') is mode
                and receipt.get('expected_remote_commit') == sha):
            return key + ' does not verify exact release'
        rows = receipt.get('skills', [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            return 'invalid receipt Skill rows'
        if sorted(r.get('name', '') for r in rows) != sorted(skills):
            return 'receipt Skill scope mismatch'
    manifests = proposal.get('manifests', {})
    if not isinstance(manifests, dict) or set(manifests) != set(skills):
        return 'complete per-Skill manifests required'
    for layers in manifests.values():
        if not isinstance(layers, dict) or set(layers) != {'source', 'cc_switch', 'claude', 'codex'}:
            return 'four layers required'
        source = layers['source']
        if not isinstance(source, dict) or 'SKILL.md' not in source:
            return 'source file manifest required'
        if any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in source.values()):
            return 'invalid file digest'
        if any(files != source for files in layers.values()):
            return 'four-layer manifest mismatch'
    scan = proposal.get('scan', {})
    if not isinstance(scan, dict) or scan.get('complete') is not True:
        return 'complete scan evidence required'
    return None


def load_evidence(path, expected_hash, reports_root):
    path = Path(path).resolve()
    if not path.is_relative_to(Path(reports_root).resolve()):
        raise ValueError('evidence must be inside reports root')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('evidence fingerprint mismatch')
    value = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('evidence must be an object')
    return value


def validate_source(root, proposal):
    sha = proposal['commit']
    def git(*args):
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
        if result.returncode:
            raise ValueError('source Git evidence unavailable')
        return result.stdout
    git('merge-base', '--is-ancestor', sha, 'refs/remotes/origin/main')
    for skill in proposal['skills']:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', skill):
            raise ValueError('invalid Skill name')
        paths = git('ls-tree', '-r', '--name-only', '-z', sha, '--', skill).decode('utf-8').split('\0')
        actual = {}
        for name in filter(None, paths):
            if not name.startswith(skill + '/'):
                raise ValueError('source scope mismatch')
            actual[name[len(skill)+1:]] = hashlib.sha256(git('show', sha + ':' + name)).hexdigest()
        if actual != proposal['manifests'][skill]['source']:
            raise ValueError('source manifest does not match release Git blobs')


def record(args, api):
    state_path = args.state.resolve()
    try:
        with api.StateLock(state_path, args.lock_timeout):
            state, created = api.load_state(state_path)
            if created:
                raise ValueError('state not initialized')
            finding = state['findings'].get(args.finding_id)
            if not finding or not finding.get('execution'):
                raise ValueError('original execution unavailable')
            proposal = load_evidence(args.evidence, args.expected_evidence_sha256, args.reports_root)
            if proposal.get('finding_id') != args.finding_id:
                raise ValueError('finding identity mismatch')
            batch = api.find_batch(state, proposal.get('batch_id'))
            item = api.batch_item(batch, args.finding_id) if batch else None
            if not item or not batch.get('decided_at'):
                raise ValueError('authorized frozen item unavailable')
            if sorted(item.get('skills', [])) != sorted(proposal.get('skills', [])):
                raise ValueError('frozen Skill scope mismatch')
            for key in ('sync', 'verify', 'scan'):
                ref = proposal.get(key + '_evidence', {})
                proposal[key] = load_evidence(ref.get('path', ''), ref.get('sha256'), args.reports_root)
            error = validate(finding['execution'], proposal)
            if error:
                raise ValueError(error)
            scan = proposal['scan']
            if scan.get('state') != state_path.name or not scan.get('date'):
                raise ValueError('scan state identity/date unavailable')
            if scan['date'] < finding['execution'].get('recorded_at', '')[:10]:
                raise ValueError('scan predates original execution')
            validate_source(args.skills_root, proposal)
            entry = dict(evidence_sha256=args.expected_evidence_sha256,
                         original_execution_fingerprint=fingerprint(finding['execution']),
                         commit=proposal['commit'], skills=proposal['skills'],
                         status='successor_verified', recorded_at=api.now_iso())
            history = finding.setdefault('successor_reconciliations', [])
            if any(row.get('evidence_sha256') == args.expected_evidence_sha256 for row in history):
                return {'status': 'already_recorded', 'finding_id': args.finding_id}, 0
            history.append(entry)
            api.save_state(state_path, state)
            return {'status': 'successor_verified', 'finding_id': args.finding_id,
                    'original_execution_unchanged': True}, 0
    except (ValueError, OSError, api.StateError, api.LockConflict) as exc:
        return {'status': 'reconciliation_refused', 'error': str(exc)}, 4
