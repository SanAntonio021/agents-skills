"""Export only completed technical outputs, with treatment and host hidden."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
collection = json.loads((ROOT / 'collection.json').read_text(encoding='utf-8'))
cases = {c['id']: c for c in json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['cases']}
rows, mapping = [], {}
for row in collection['rows']:
    if row['category'] != 'technical':
        continue
    opaque = hashlib.sha256(('technical-independent-check:' + row['key']).encode()).hexdigest()[:12]
    mapping[opaque] = {'key': row['key'], 'output_sha256': row['output_sha256']}
    rows.append({'id': opaque, 'case': row['case'], 'prompt': cases[row['case']]['prompt'],
                 'review': cases[row['case']]['review'],
                 'output': (ROOT / row['path'] / 'final.md').read_text(encoding='utf-8')})
assert len(rows) == 24, f'All 24 technical outputs needed, got {len(rows)}'
data = {'instructions': 'Review task compliance, not resemblance to a celebrity style. Separate fact/condition preservation from concision. Do not infer an order regression solely from an ordinary sequential phrase; flag genuine ambiguity separately. No aggregate ranking.',
        'outputs': sorted(rows, key=lambda r: r['id'])}
(ROOT / 'technical-blind-input.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
(ROOT / 'technical-blind-key.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
print('Exported 24 anonymous technical outputs.')
