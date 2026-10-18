import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from urllib.parse import unquote

report = Path(__file__).resolve().parent
repo = report.parents[1]
skill = repo / 'web-access'
allowed = {'web-access/SKILL.md', 'web-access/README.md', 'web-access/evals/evals.json',
           'web-access/references/cdp-api.md', 'web-access/references/migration-dual-proxy.2.md'}
baseline = json.loads((report / 'baseline-files.json').read_text(encoding='utf-8-sig'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest().upper()
unchanged = []
for item in baseline:
    if item['path'] not in allowed:
        assert sha(repo / item['path']) == item['sha256'], item['path']
        unchanged.append(item['path'])
private = json.loads((report / 'local-files-before.json').read_text(encoding='utf-8-sig'))
for item in private:
    assert sha(Path(item['path'])) == item['sha256'], item['path']

def anchors(text):
    out = set()
    for heading in re.findall(r'^#{1,6}\s+(.+)$', text, re.M):
        heading = heading.strip().lower().replace(' ', '-')
        heading = ''.join(c for c in heading if c in '-_' or unicodedata.category(c)[0] in 'LN')
        out.add(heading)
    return out

links = []
for rel in sorted(allowed):
    path = repo / rel
    if path.suffix != '.md':
        continue
    text = path.read_text(encoding='utf-8')
    assert len(re.findall(r'^```', text, re.M)) % 2 == 0, rel
    for target in re.findall(r'(?<!!)\[[^\]\n]*\]\(([^)\s]+)\)', text):
        if re.match(r'^[a-z]+:', target, re.I):
            continue
        name, _, anchor = target.partition('#')
        dest = (path.parent / unquote(name)).resolve() if name else path
        assert dest.exists(), (rel, target)
        if anchor and dest.suffix == '.md':
            assert unquote(anchor) in anchors(dest.read_text(encoding='utf-8')), (rel, target)
        links.append([rel, target])

evals = json.loads((skill / 'evals/evals.json').read_text(encoding='utf-8'))
assert evals['skill_name'] == 'web-access'
assert len({x['id'] for x in evals['evals']}) == len(evals['evals']) == 26
for case in evals['evals']:
    assert set(('id', 'prompt', 'expected_output', 'files', 'expectations')) <= case.keys()
    assert case['prompt'] and case['expected_output'] and case['expectations']

old = subprocess.check_output(['git', '-C', str(repo), 'show', '6918df5:web-access/SKILL.md']).decode('utf-8')
current = (skill / 'SKILL.md').read_text(encoding='utf-8')
integration = json.loads((report / 'integration.json').read_text(encoding='utf-8-sig'))
real = json.loads((report / 'real-edge.json').read_text(encoding='utf-8-sig'))
assert integration['passed'] == 45 and integration['failed'] == 0
assert real['passed'] and len(real['checks']) == 9
output = {'source_checks_passed': True, 'entry_lines_before': len(old.splitlines()),
          'entry_lines_after': len(current.splitlines()), 'entry_chars_before': len(old),
          'entry_chars_after': len(current), 'local_links_checked': len(links),
          'eval_cases': len(evals['evals']), 'unchanged_tracked_files': unchanged,
          'private_files_unchanged': len(private), 'integration_passed': 45, 'real_edge_checks': 9,
          'limits': 'Static and existing program checks; independent behavior acceptance recorded separately.'}
(report / 'file-validation.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(output, ensure_ascii=False))
