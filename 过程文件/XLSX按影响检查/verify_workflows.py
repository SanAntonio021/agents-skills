from pathlib import Path
import json
import sys
import hashlib
import subprocess

root = Path(__file__).resolve().parent
work = root / 'main-checks-v02'
work.mkdir(exist_ok=True)
scripts = Path(r'D:\BaiduSyncdisk\.agents\skills\xlsx\scripts')
sys.path.insert(0, str(scripts))
from patch_ooxml import patch_workbook
from libreoffice_headless import convert, find_soffice
from merge_formula_caches import merge_caches
from verify_xlsx import inspect_workbook, compare_workbooks
from verify_pdf import inspect_pdf, render_pdf, find_pdftoppm

source = root / 'fixtures/calculated.xlsx'
baseline = inspect_workbook(source)
numeric = work / 'numeric-draft.xlsx'
patch_workbook(source, numeric, {'sheets': {'计算表': {'cells': {'B3': {'kind': 'number', 'value': 4}}}}}, False)
stale = inspect_workbook(numeric)
assert float(stale['sheets']['计算表']['cells']['E3']['cached']) == 25
# An intact old cache is not proof of correctness after an input change.
recalculated = work / 'numeric-recalculated.xlsx'
calculation_input = work / 'numeric-calculation-input.xlsx'
formula_patches = {ref: {'kind': 'formula', 'formula': cell['formula']['text']}
    for ref, cell in stale['sheets']['计算表']['cells'].items() if cell.get('formula')}
assert all(not cell['formula']['attributes'] for cell in stale['sheets']['计算表']['cells'].values() if cell.get('formula'))
patch_workbook(numeric, calculation_input, {'sheets': {'计算表': {'cells': formula_patches}}}, False)
report = convert('recalc', calculation_input, recalculated, find_soffice(None), 120)
(work / 'numeric-recalc.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
final = work / 'numeric-final.xlsx'
merge_caches(numeric, recalculated, final)
current = inspect_workbook(final)
cells = current['sheets']['计算表']['cells']
assert float(cells['E3']['cached']) == 45
assert float(cells['E5']['cached']) == 105
assert current['formula_count'] == current['formula_cache_count'] == 5
assert current['formula_error_count'] == 0
policy = {'allowed_cells': ['计算表!B3'], 'allow_formula_cache_changes': True,
          'required_unchanged_entries': [p for p in baseline['package_entries'] if not p.startswith('xl/worksheets/sheet')]}
comparison = compare_workbooks(baseline, current, policy)
assert comparison['ok'], comparison
formatted = work / 'format-only.xlsx'
patch_workbook(source, formatted, {'sheets': {'计算表': {'row_heights': {'3': 42}}}}, False)
format_report = inspect_workbook(formatted)
comparison_format = compare_workbooks(baseline, format_report, {
    'allowed_row_heights': ['计算表!3'], 'allow_formula_cache_changes': False,
    'required_unchanged_entries': policy['required_unchanged_entries']})
assert comparison_format['ok'], comparison_format
for name, source_file in [('numeric-print', final), ('format-preview', formatted)]:
    pdf = work / f'{name}.pdf'
    convert('pdf', source_file, pdf, find_soffice(None), 120)
    pdf_report = inspect_pdf(pdf, 1, 'landscape', [], [], 1)
    assert pdf_report['ok'], pdf_report
    images = render_pdf(pdf, work / name, 150, find_pdftoppm(Path(
        r'C:\Users\SanAn\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe')), 1)
    pdf_report['rendered_pages'] = images
    (work / f'{name}.json').write_text(json.dumps(pdf_report, ensure_ascii=False, indent=2), encoding='utf-8')

values = root / 'fixtures/values.xlsx'
assert inspect_workbook(values)['formula_count'] == 0
value_output = work / 'values-output.xlsx'
patch_workbook(values, value_output, {'sheets': {'清单': {'cells': {'C2': {'kind': 'number', 'value': 4}}}}}, False)
assert inspect_workbook(value_output)['sheets']['清单']['cells']['C2']['value'] == '4'
missing = root / 'fixtures/missing-cache.xlsx'
test = subprocess.run([sys.executable, str(scripts / 'verify_xlsx.py'), str(missing)], capture_output=True, text=True, encoding='utf-8')
missing_report = json.loads(test.stdout)
assert test.returncode == 2 and not missing_report['ok']
hashes = json.loads((root / 'fixture-hashes.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((root / 'fixtures' / name).read_bytes()).hexdigest() == sha for name, sha in hashes.items())
results = {'status': 'PASS', 'numeric_change': {'A_sum': 45, 'total': 105},
    'format_no_recalc_preserved': True, 'no_formula_no_recalc': True,
    'missing_cache_rejected': True, 'protected_fixtures_unchanged': True,
    'pdfs_rendered': 2, 'visual_inspection': 'pending'}
(work / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results))
