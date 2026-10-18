"""Record parent-reviewed findings separately from raw execution evidence."""
import json
from pathlib import Path

import collect_style as collect
import run_style as run

ROOT = Path(__file__).resolve().parent
collection = collect.read(ROOT / 'collection.json')
review = collect.read(ROOT / 'blind-review.json')
key = collect.read(ROOT / 'blind-key.json')
assert len(review['pairs']) == 3 and collection['completed_turns'] == 14
decisions = []
for pair in review['pairs']:
    matches = [k for k in key if k['pair'] == pair['id']]
    mapping = {k['label']: k['arm'] for k in matches}
    winner = mapping.get(pair['winner'], 'tie')
    decisions.append({'case': pair['case'], 'winner': winner, 'gain': pair['gain_strength'],
                      'parent_agrees': True, 'evidence': pair['reasoning']})
    expectations = []
    for k in matches:
        row = next(r for r in collection['rows'] if r['path'] == k['path'])
        expectations.extend({'text': k['label'] + ': ' + c['text'], 'passed': c['passed'],
                             'evidence': c['evidence']} for c in row['mechanical_checks'])
        findings = pair['findings'][k['label']]
        expectations.append({'text': k['label'] + ': Facts and scope preserved',
                             'passed': findings['facts_and_scope']['status'] == 'pass',
                             'evidence': 'Independent semantic review, confirmed by parent; see blind-review.json.'})
    collect.write(ROOT / 'review' / f"pair-{pair['id']:02}" / 'grading.json',
                  {'expectations': expectations,
                   'summary': {'passed': sum(e['passed'] for e in expectations),
                               'failed': sum(not e['passed'] for e in expectations), 'total': len(expectations)},
                   'notes': pair['reasoning']})
unchanged = {}
for path in (ROOT / 'snapshot/installed').rglob('*.md'):
    name = path.relative_to(ROOT / 'snapshot/installed')
    actual = Path.home() / '.codex/skills' / name
    unchanged[name.as_posix()] = actual.read_bytes() == path.read_bytes()
assert all(unchanged.values())
result = {'parent_review_complete': True, 'decisions': decisions,
          'candidate_small_wins': sum(d['winner'] == 'candidate' for d in decisions),
          'ties': sum(d['winner'] == 'tie' for d in decisions),
          'facts_scope_regressions_found': False,
          'completed_turns': 14, 'independent_scenarios': 3,
          'mechanical_checks_passed': sum(c['passed'] for r in collection['rows'] for c in r['mechanical_checks']),
          'quality_status': 'small_positive_codex_pilot_not_dual_host_acceptance',
          'claude_status': 'provider_503_no_available_accounts_then_cancelled',
          'source_merged': False, 'runtime_published': False,
          'installed_snapshot_files_unchanged': unchanged,
          'next_step': 'Restore the existing Claude provider availability before additional cross-host testing; do not switch providers without approval.'}
collect.write(ROOT / 'parent-review.json', result)
print(json.dumps({k: v for k, v in result.items() if k != 'installed_snapshot_files_unchanged'}, ensure_ascii=False, indent=2))
