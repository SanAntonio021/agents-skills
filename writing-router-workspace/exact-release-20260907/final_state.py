"""Read-only final committed-source/runtime file comparison after smoke tests."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
COMMITS = {'docx': 'da0c2758ad7577f76974c6bce58e4aa1f77c2a52',
           'writing-router': 'c32d384a879b5870b07af35fd5248cacd15f7adc'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


results = []
for skill, commit in COMMITS.items():
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit, '--', skill],
                                    cwd=REPO).decode().splitlines()
    expected = {name[len(skill) + 1:]: sha(subprocess.check_output(['git', 'show', commit + ':' + name], cwd=REPO))
                for name in names}
    for host in ['.cc-switch', '.claude', '.codex']:
        root = Path.home() / host / 'skills' / skill
        actual = {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in root.rglob('*')
                  if p.is_file() and not ('__pycache__' in p.parts and p.suffix == '.pyc')}
        results.append({'skill': skill, 'commit': commit, 'host': host, 'file_count': len(actual),
                        'equal_to_commit': actual == expected,
                        'missing': sorted(set(expected) - set(actual)),
                        'extra': sorted(set(actual) - set(expected)),
                        'different': [p for p in expected.keys() & actual.keys() if expected[p] != actual[p]]})
staging = subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=REPO).decode().strip()
result = {'layers': results, 'index_empty': not staging,
          'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO).decode().strip()}
(ROOT / 'final-state.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
assert all(r['equal_to_commit'] for r in results) and not staging
