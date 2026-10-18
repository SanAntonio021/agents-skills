import json
import re
import subprocess
from pathlib import Path

root = Path(r'D:\BaiduSyncdisk\.agents\skills')
skill = root / 'pptx'
files = [skill / 'SKILL.md', *[skill / 'references' / p for p in
    ('ppt-master-integration.md', 'presentation-workflow.md', 'upstream-sources.md')]]
missing = []
for file in files:
    for target in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#') or '<' in target:
            continue
        path = target.split('#', 1)[0]
        if path and not (file.parent / path).exists():
            missing.append({'file': str(file), 'target': target})
evals = json.loads((skill / 'evals/evals.json').read_text(encoding='utf-8'))
cases = evals['evals']
assert len({case['id'] for case in cases}) == len(cases)
for case in cases:
    assert all(k in case for k in ('id', 'prompt', 'expected_output', 'files', 'expectations'))
assert not missing, missing
result = {'local_links': 'PASS', 'eval_cases': len(cases), 'eval_structure': 'PASS'}
(Path(__file__).parent / 'source-checks.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
