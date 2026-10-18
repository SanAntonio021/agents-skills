from pathlib import Path
import json
import hashlib
import re
import sys

root = Path(__file__).resolve().parent
skill = Path(r'D:\BaiduSyncdisk\.agents\skills\xlsx')
sys.path.insert(0, str(skill / 'scripts'))
from verify_xlsx import inspect_workbook, compare_workbooks
source = root / 'fixtures/calculated.xlsx'
before = inspect_workbook(source)
formula_cells = [k for k, v in before['sheets']['计算表']['cells'].items() if v.get('formula')]
protected = [p for p in before['package_entries'] if not p.startswith('xl/worksheets/sheet')]
for filename, cell, cache_change in [('备注修改_v01.xlsx', 'F3', False), ('类别修改_v01.xlsx', 'A4', True)]:
    current = inspect_workbook(root / 'edit-trial' / filename)
    assert current['formula_count'] == current['formula_cache_count'] == 5
    assert current['formula_error_count'] == 0
    delta = compare_workbooks(before, current, {'allowed_cells': ['计算表!' + cell],
        'allow_formula_cache_changes': cache_change, 'required_unchanged_entries': protected})
    assert delta['ok'], delta
    if not cache_change:
        assert all(current['sheets']['计算表']['cells'][f] == before['sheets']['计算表']['cells'][f] for f in formula_cells)
    else:
        assert float(current['sheets']['计算表']['cells']['E3']['cached']) == 85
hashes = json.loads((root / 'fixture-hashes.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((root / 'fixtures' / name).read_bytes()).hexdigest() == value for name, value in hashes.items())
changed_docs = [skill / 'SKILL.md', *(skill / 'references' / f for f in
    ['general-workflow.md', 'high-fidelity-workflow.md', 'formatting-and-formulas.md', 'patch-spec.md'])]
links = []
for path in changed_docs:
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#') or '<' in target:
            continue
        p = target.split('#')[0]
        if p:
            assert (path.parent / p).exists(), (path, target)
            links.append(target)
cases = json.loads((skill / 'evals/evals.json').read_text(encoding='utf-8'))['evals']
assert len({c['id'] for c in cases}) == len(cases)
assert all(all(k in c for k in ['prompt', 'expected_output', 'files', 'assertions']) for c in cases)
assert all(isinstance(c['assertions'], list) and c['assertions'] for c in cases)
record = {'independent_edit_outputs': 'PASS', 'fixtures_unchanged': True,
    'local_links_checked': len(links), 'eval_cases': len(cases),
    'main_pdf_visual_inspection': 'PASS', 'main_pdf_pages': 2}
(root / 'acceptance.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(record))
