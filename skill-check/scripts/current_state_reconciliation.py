"""Close superseded workflows using measured current state, not invented history."""
import hashlib
import os
from pathlib import Path
import re
import subprocess

import successor_reconciliation as evidence


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError('current source Git evidence unavailable')
    return result.stdout


def source_manifest(root, commit, skill):
    paths = git(root, 'ls-tree', '-r', '--name-only', '-z', commit, '--', skill)
    return {name[len(skill) + 1:]: hashlib.sha256(git(root, 'show', commit + ':' + name)).hexdigest()
            for name in paths.decode('utf-8').split('\0') if name.startswith(skill + '/')}


def runtime_manifest(root, skill):
    directory = root / skill
    if not directory.is_dir():
        raise ValueError('current runtime Skill unavailable: ' + skill)
    files = {}
    for path in directory.rglob('*'):
        if path.is_file():
            relative = path.relative_to(directory)
            if '__pycache__' in relative.parts and path.suffix == '.pyc':
                continue
            files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def default_runtime_roots():
    home = Path.home()
    return {
        'cc_switch': Path(os.environ.get('CC_SWITCH_CONFIG_DIR') or home / '.cc-switch') / 'skills',
        'claude': Path(os.environ.get('CLAUDE_CONFIG_DIR') or home / '.claude') / 'skills',
        'codex': Path(os.environ.get('CODEX_HOME') or home / '.codex') / 'skills',
    }


def validate_scan(args, original, proposal, state):
    ref = proposal.get('scan_evidence', {})
    scan = evidence.load_evidence(ref.get('path', ''), ref.get('sha256'), args.reports_root)
    state_ref = args.state.resolve().relative_to(args.reports_root.resolve()).as_posix()
    if (scan.get('status') != 'scanned' or scan.get('complete') is not True
            or scan.get('state') != state_ref or not scan.get('date')
            or scan['date'] < original.get('recorded_at', '')[:10]):
        raise ValueError('complete original-state scan evidence required')
    report_ref = proposal.get('scan_report_evidence', {})
    report_path = (args.reports_root / str(scan.get('scan_report', ''))).resolve()
    if Path(report_ref.get('path', '')).resolve() != report_path:
        raise ValueError('scan report identity mismatch')
    report = evidence.load_evidence(report_path, report_ref.get('sha256'), args.reports_root)
    if (report.get('complete') is not True or report.get('date') != scan['date']
            or not report.get('scope_fingerprint') or not report.get('generated_at')
            or not any(r.get('complete') is True and r.get('date') == scan['date']
                       and r.get('scope_fingerprint') == report['scope_fingerprint']
                       and r.get('completed_at') == report['generated_at']
                       and r.get('report_ref') == scan.get('scan_report')
                       for r in state.get('runs', []))):
        raise ValueError('scan report has no matching completed state run')


def validate_desktop_metadata(args, release, receipts, manifests):
    ref = release.get('metadata_evidence', {})
    query = evidence.load_evidence(ref.get('path', ''), ref.get('sha256'), args.reports_root)
    if (query.get('status') != 'queried' or query.get('exit_code') != 0
            or query.get('backend') != 'official-desktop-cdp' or query.get('contract_version') != 16):
        raise ValueError('official metadata query required')
    refs = release.get('source_receipts', {})
    if set(refs) != set(release['skills']):
        raise ValueError('exact desktop source receipts required')
    for skill in release['skills']:
        ref = refs[skill]
        source = evidence.load_evidence(ref.get('path', ''), ref.get('sha256'), args.reports_root)
        rows = [r for r in query.get('skills', []) if r.get('directory') == skill]
        if len(rows) != 1:
            raise ValueError('current metadata Skill identity mismatch')
        row = rows[0]
        official = source.get('official_source') or {}
        if (source.get('commit') != release['commit'] or source.get('manifest') != manifests[skill]
                or source.get('repository') != receipts[0].get('source_repository')
                or row.get('id') != 'local:' + skill or row.get('name') != skill
                or any(row.get(k) != official.get(k) for k in ('id', 'name', 'directory', 'apps'))
                or any(row.get('apps', {}).get(app) is not True for app in ('claude', 'codex'))):
            raise ValueError('current desktop metadata/source receipt mismatch')


def validate_current(args, finding, proposal, item, runtime_roots=None, state=None):
    original = finding['execution']
    if proposal.get('original_execution_fingerprint') != evidence.fingerprint(original):
        raise ValueError('original execution fingerprint mismatch')
    skills = proposal.get('skills')
    if (not isinstance(skills, list) or not skills
            or any(not isinstance(s, str) for s in skills) or len(set(skills)) != len(skills)):
        raise ValueError('exact nonempty current Skill scope required')
    if sorted(skills) != sorted(item.get('skills', [])):
        raise ValueError('frozen Skill scope mismatch')
    if finding.get('status') in {'approved', 'execution_pending', 'retry_pending'}:
        raise ValueError('active execution must use its normal execution workflow')
    if not original.get('remote_sha') and finding.get('status') not in {'resolved', 'historical'}:
        raise ValueError('missing original SHA requires an independently resolved finding')
    validate_scan(args, original, proposal, state or {})
    review_ref = proposal.get('semantic_review_evidence', {})
    review = evidence.load_evidence(review_ref.get('path', ''), review_ref.get('sha256'), args.reports_root)
    if (review.get('finding_id') != finding['id']
            or review.get('original_execution_fingerprint') != evidence.fingerprint(original)
            or set(review.get('skills', {})) != set(skills)):
        raise ValueError('semantic review identity/scope mismatch')
    releases = proposal.get('releases')
    if not isinstance(releases, list) or not releases:
        raise ValueError('current release receipts required')
    roots = runtime_roots or default_runtime_roots()
    measured = {}
    commits = {}
    covered = []
    for release in releases:
        if not isinstance(release, dict):
            raise ValueError('invalid current release')
        commit = release.get('commit', '')
        targets = release.get('skills', [])
        if (not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit)
                or not isinstance(targets, list) or not targets
                or any(not isinstance(s, str) for s in targets)):
            raise ValueError('exact current release identity required')
        git(args.skills_root, 'merge-base', '--is-ancestor', commit, 'refs/remotes/origin/main')
        old_sha = original.get('remote_sha')
        if old_sha:
            git(args.skills_root, 'merge-base', '--is-ancestor', old_sha, commit)
        receipts = []
        for key, mode in [('sync', False), ('verify', True)]:
            ref = release.get(key + '_evidence', {})
            receipt = evidence.load_evidence(ref.get('path', ''), ref.get('sha256'), args.reports_root)
            rows = receipt.get('skills', [])
            if (not isinstance(rows, list) or not rows or any(not isinstance(row, dict) for row in rows)):
                raise ValueError('invalid current receipt Skill rows')
            if not (receipt.get('ok') is True and receipt.get('exit_code') == 0
                    and receipt.get('status') == 'runtime_active'
                    and receipt.get('verify_only') is mode
                    and receipt.get('expected_remote_commit') == commit
                    and sorted(row.get('name', '') for row in rows) == sorted(targets)
                    and all(row.get('verified') is True for row in rows)
                    and not receipt.get('errors')):
                raise ValueError('current ' + key + ' receipt mismatch')
            metadata = receipt.get('cc_switch_metadata')
            if metadata is not None and (not isinstance(metadata, dict)
                    or metadata.get('valid') is not True or metadata.get('issues')):
                raise ValueError('current receipt metadata invalid')
            if metadata is None and not (receipt.get('backend') == 'official-desktop-cdp'
                    and receipt.get('helper_contract_version') == 16
                    and all(row.get('layers') == {'cc_switch': True, 'claude': True, 'codex': True}
                            for row in rows)):
                raise ValueError('current receipt metadata unavailable')
            receipts.append(receipt)
        for field in ('source_mode', 'source_repository', 'expected_base_commit',
                      'expected_worktree_exceptions', 'expected_runtime_local_files',
                      'allow_historical_commit', 'allow_historical_subset', 'backend', 'resolved_paths'):
            if receipts[0].get(field) != receipts[1].get(field):
                raise ValueError('sync and verify parameters differ: ' + field)
        for skill in targets:
            if skill not in skills or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', skill):
                raise ValueError('invalid current Skill scope')
            if (git(args.skills_root, 'diff', commit, 'HEAD', '--', skill)
                    or git(args.skills_root, 'diff', commit, 'refs/remotes/origin/main', '--', skill)):
                raise ValueError('current release is superseded: ' + skill)
            if git(args.skills_root, 'status', '--porcelain', '--untracked-files=all', '--', skill):
                raise ValueError('current source has unpublished edits: ' + skill)
            manifest = source_manifest(args.skills_root, commit, skill)
            if 'SKILL.md' not in manifest:
                raise ValueError('current source entry unavailable')
            layers = {'source': manifest}
            for layer, root in roots.items():
                layers[layer] = runtime_manifest(root, skill)
                if layers[layer] != manifest:
                    raise ValueError('current runtime manifest mismatch: ' + skill + '/' + layer)
            assessment = review['skills'][skill]
            if (not isinstance(assessment, dict) or not assessment.get('conclusion')
                    or not isinstance(assessment.get('checks'), list) or not assessment['checks']):
                raise ValueError('specific semantic review and checks required')
            for check in assessment['checks']:
                if not isinstance(check, dict):
                    raise ValueError('invalid semantic check')
                path = check.get('path', '')
                if path not in manifest:
                    raise ValueError('semantic evidence path is not in current release')
                text = git(args.skills_root, 'show', commit + ':' + skill + '/' + path).decode('utf-8')
                present, absent = check.get('contains', []), check.get('absent', [])
                if (not isinstance(present, list) or not isinstance(absent, list)
                        or (not present and not absent)
                        or any(not isinstance(s, str) or not s for s in [*present, *absent])):
                    raise ValueError('specific semantic assertions required')
                if any(token not in text for token in present) or any(token in text for token in absent):
                    raise ValueError('semantic assertion failed: ' + skill + '/' + path)
            measured[skill] = layers
            commits[skill] = commit
        if any(receipt.get('cc_switch_metadata') is None for receipt in receipts):
            validate_desktop_metadata(args, release, receipts,
                                      {skill: measured[skill]['source'] for skill in targets})
        covered.extend(targets)
    if sorted(covered) != sorted(skills):
        raise ValueError('current releases must cover each frozen Skill exactly once')
    return commits, measured


def record_current(args, api, state, finding, proposal, item):
    commits, manifests = validate_current(args, finding, proposal, item, state=state)
    entry = {
        'kind': 'current_state', 'status': 'superseded_current_verified',
        'evidence_sha256': args.expected_evidence_sha256,
        'original_execution_fingerprint': evidence.fingerprint(finding['execution']),
        'original_status': finding['status'], 'commits': commits,
        'skills': proposal['skills'], 'manifests_fingerprint': evidence.fingerprint(manifests),
        'recorded_at': api.now_iso(), 'original_history_proven': False,
    }
    history = finding.setdefault('successor_reconciliations', [])
    if any(row.get('evidence_sha256') == args.expected_evidence_sha256 for row in history):
        return {'status': 'already_recorded', 'finding_id': finding['id']}, 0
    history.append(entry)
    finding['status'] = 'historical'
    state['queue'] = [key for key in state['queue'] if key != finding['id']]
    api.save_state(args.state.resolve(), state)
    return {'status': entry['status'], 'finding_id': finding['id'],
            'original_execution_unchanged': True, 'original_history_proven': False}, 0
