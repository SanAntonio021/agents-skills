"""Validate evidence for a mirror-only diagnostic without inventing publication."""
import re
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path

import successor_reconciliation as evidence


def _git(root, *arguments):
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True)
    if result.returncode:
        raise ValueError('mirror Git verification failed')
    return result.stdout.decode('utf-8').strip()


def validate(finding, batch, item, scan, upstream, mirror, run, registry_source):
    """Require the frozen approval, a later completed scan, and matching live mirror.

    This validator does not change state or claim a Skill was published.
    """
    decision = finding.get('decision') or {}
    if not (finding.get('kind') == 'upstream_diagnostic'
            and finding.get('purpose') == 'repair-mirror_blocked'
            and finding.get('status') == 'execution_pending'
            and batch.get('status') in {'ready', 'partial_failed'}
            and batch.get('decided_at') and item.get('status') == 'pending'
            and not finding.get('execution') and not item.get('execution')
            and decision.get('value') == 'approved'
            and decision.get('evidence_fingerprint') == item.get('evidence_fingerprint') == finding.get('evidence_fingerprint')
            and decision.get('proposal_fingerprint') == item.get('proposal_fingerprint') == finding.get('proposal_fingerprint')
            and item.get('source_fingerprint') == finding.get('source_fingerprint')
            and '不变更技能正文' in decision.get('reason_summary', '')
            and '接受基线' in decision.get('reason_summary', '')):
        raise ValueError('unchanged approved mirror-only scope required')
    if not (scan.get('complete') is True and run.get('complete') is True
            and scan.get('date') == run.get('date')
            and scan.get('scope_fingerprint') == run.get('scope_fingerprint')
            and scan.get('generated_at') == run.get('completed_at')
            and scan.get('components', {}).get('upstream', {}).get('complete') is True):
        raise ValueError('completed matching upstream scan required')
    try:
        if datetime.fromisoformat(scan['generated_at']) <= datetime.fromisoformat(batch['decided_at']):
            raise ValueError('scan must follow approval')
    except (KeyError, TypeError) as exc:
        raise ValueError('scan timestamps required') from exc
    skill, separator, source = finding.get('subject', '').partition(':')
    if not (separator and registry_source.get('id') == source
            and registry_source.get('skill') == skill
            and upstream.get('source') == source and upstream.get('skill') == skill
            and upstream.get('status') == 'up_to_date'
            and upstream.get('tracking') == 'stable_tags'
            and registry_source.get('mirror_id') == mirror.get('id')
            and registry_source.get('repo_url') == mirror.get('repo_url') == mirror.get('local_origin')
            and mirror.get('tracking') == 'stable_tags'
            and mirror.get('status') == 'already_up_to_date'
            and mirror.get('local_dirty') is False and mirror.get('remote_reachable') is True
            and mirror.get('local_repo_valid') is True and mirror.get('git_dir_matches_registry') is True):
        raise ValueError('matching healthy registered mirror required')
    commit = upstream.get('current_commit')
    tag = upstream.get('current_release_tag')
    if not (isinstance(commit, str) and re.fullmatch('[0-9a-f]{40}', commit)
            and isinstance(tag, str) and re.fullmatch(r'v?[0-9]+(?:\.[0-9]+)+', tag)
            and commit == upstream.get('accepted_commit') == registry_source.get('accepted_commit')
            == mirror.get('local_head') == mirror.get('remote_head') == mirror.get('after_head')
            and tag == mirror.get('local_stable_tag') == mirror.get('remote_tag')
            and mirror.get('stable_tags', {}).get(tag) == commit):
        raise ValueError('stable tag and accepted baseline mismatch')
    root = Path(mirror['local_path'])
    if (_git(root, 'rev-parse', 'HEAD') != commit
            or _git(root, 'rev-parse', 'refs/tags/' + tag + '^{}') != commit
            or _git(root, 'remote', 'get-url', 'origin') != mirror['repo_url']
            or _git(root, 'status', '--porcelain', '--untracked-files=all')):
        raise ValueError('live mirror no longer matches evidence')
    return {'source': source, 'skill': skill, 'commit': commit, 'stable_tag': tag}


def record(args, api):
    """Append a factual resolution under the normal lock; preserve the approval."""
    state_path = args.state.resolve()
    try:
        with api.StateLock(state_path, args.lock_timeout):
            state, created = api.load_state(state_path)
            if created:
                raise ValueError('state not initialized')
            batch = api.find_batch(state, args.batch_id)
            finding = state['findings'].get(args.finding_id)
            item = api.batch_item(batch, args.finding_id) if batch else None
            if not finding or not item or batch.get('batch_fingerprint') != args.expected_batch_fingerprint:
                raise ValueError('exact frozen batch and finding required')
            if len(batch.get('items', [])) != 1 or any(
                    finding['id'] in (other.get('proposal') or {}).get('dependencies', [])
                    for key, other in state['findings'].items() if key != finding['id']):
                raise ValueError('mirror resolution with dependent items requires separate review')
            if args.expected_proposal_fingerprint != item.get('proposal_fingerprint'):
                raise ValueError('proposal fingerprint mismatch')
            proposal = evidence.load_evidence(args.evidence, args.expected_evidence_sha256, args.reports_root)
            if proposal.get('finding_id') != finding['id'] or proposal.get('batch_id') != batch['id']:
                raise ValueError('evidence identity mismatch')
            scan_ref = proposal.get('scan', {})
            scan = evidence.load_evidence(scan_ref.get('path', ''), scan_ref.get('sha256'), args.reports_root)
            runs = state.get('runs', [])
            if not runs or runs[-1].get('complete') is not True or Path(scan_ref['path']).resolve() != (args.reports_root / runs[-1]['report_ref']).resolve():
                raise ValueError('latest state scan must be complete')
            run = runs[-1]
            upstream_ref = proposal.get('upstream', {})
            if Path(upstream_ref.get('path', '')).resolve() != (args.reports_root / scan['components']['upstream']['report_ref']).resolve():
                raise ValueError('upstream report identity mismatch')
            upstream = evidence.load_evidence(upstream_ref['path'], upstream_ref.get('sha256'), args.reports_root)
            freshness = scan['components']['upstream'].get('freshness', {})
            if (upstream.get('generated_at') != freshness.get('generated_at')
                    or datetime.fromisoformat(upstream['generated_at']) <= datetime.fromisoformat(batch['decided_at'])):
                raise ValueError('fresh upstream report after approval required')
            mirror_ref = proposal.get('mirror', {})
            if Path(mirror_ref.get('path', '')).resolve() != (args.reports_root / scan['date'] / 'mirror-results.json').resolve():
                raise ValueError('mirror report identity mismatch')
            mirror = evidence.load_evidence(mirror_ref['path'], mirror_ref.get('sha256'), args.reports_root)
            if upstream.get('report_complete') is not True or mirror.get('exit_code') != 0:
                raise ValueError('complete source and mirror reports required')
            registry_path = args.agents_root / 'upstream' / 'skill-sources.toml'
            registry = tomllib.loads(registry_path.read_text(encoding='utf-8'))
            mirror_registry = tomllib.loads((args.agents_root / 'upstream' / 'repo-mirrors.toml').read_text(encoding='utf-8'))
            skill, _, source = finding['subject'].partition(':')
            entries = [{**s, 'skill': row.get('name')} for row in registry['skill']
                       for s in row.get('source', []) if row.get('name') == skill and s.get('id') == source]
            sources = [r for r in upstream.get('sources', []) if r.get('skill') == skill and r.get('source') == source]
            mirrors = [r for r in mirror.get('mirrors', []) if entries and r.get('id') == entries[0].get('mirror_id')]
            if len(entries) != 1 or len(sources) != 1 or len(mirrors) != 1:
                raise ValueError('unique registry, source and mirror required')
            registered_mirrors = [r for r in mirror_registry['mirror'] if r.get('id') == entries[0].get('mirror_id')]
            if len(registered_mirrors) != 1 or any(
                    registered_mirrors[0].get(key) != mirrors[0].get(key)
                    for key in ('tracking', 'repo_url', 'local_path', 'git_dir_path')):
                raise ValueError('mirror report does not match registered mirror')
            result = validate(finding, batch, item, scan, sources[0], mirrors[0], run, entries[0])
            resolution = {'kind': 'mirror_only_verified', 'recorded_at': api.now_iso(),
                          'evidence_sha256': args.expected_evidence_sha256, **result,
                          'publication_claimed': False}
            if finding.get('resolution'):
                finding.setdefault('history', []).append({'event': 'previous_resolution_preserved', 'resolution': finding['resolution']})
            finding.setdefault('history', []).append({'event': 'mirror_only_verified', **resolution})
            finding['resolution'] = resolution
            finding['status'] = 'resolved'
            item['status'] = 'resolved_no_publication'
            item['resolution'] = resolution
            state['queue'] = [key for key in state['queue'] if key != finding['id']]
            api.refresh_batch_status(batch)
            api.save_state(state_path, state)
            return {'status': 'resolved_no_publication', 'finding_id': finding['id'],
                    'batch_status': batch['status'], 'publication_claimed': False}, 0
    except (ValueError, OSError, KeyError, TypeError, api.StateError, api.LockConflict) as exc:
        return {'status': 'resolution_refused', 'error': str(exc)}, 4
