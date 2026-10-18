from pathlib import Path
import json
import sys
import hashlib
import subprocess

root = Path(__file__).resolve().parent
work = root / 'main-checks-v02'
scripts = Path(r'D:\BaiduSyncdisk\.agents\skills\xlsx\scripts')
sys.path.insert(0, str(scripts))
from patch_ooxml import patch_workbook
from libreoffice_headless import convert, find_soffice
from verify_xlsx import inspect_workbook, compare_workbooks

source = root / 'fixtures/calculated.xlsx'
baseline = inspect_workbook(source)
current = inspect_workbook(work / 'numeric-final.xlsx')
assert current['formula_count'] == current['formula_cache_count'] == 5
assert current['formula_error_count'] == 0
assert float(current['sheets']['计算表']['cells']['E3']['cached']) == 45
assert float(current['sheets']['计算表']['cells']['E5']['cached']) == 105
protected = [p for p in baseline['package_entries'] if not p.startswith('xl/worksheets/sheet')]
assert compare_workbooks(baseline, current, {'allowed_cells': ['计算表!B3'],
    'allow_formula_cache_changes': True, 'required_unchanged_entries': protected})['ok']
formatted = work / 'format-only.xlsx'
format_report = inspect_workbook(formatted)
assert compare_workbooks(baseline, format_report, {'allowed_row_heights': ['计算表!3'],
    'allow_formula_cache_changes': False, 'required_unchanged_entries': protected})['ok']
format_pdf = work / 'format-preview.pdf'
convert('pdf', formatted, format_pdf, find_soffice(None), 120)
pdf_python = r'C:\Users\SanAn\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
for name in ('numeric-print', 'format-preview'):
    args = [pdf_python, str(scripts / 'verify_pdf.py'), str(work / f'{name}.pdf'),
            '--expected-pages', '1', '--landscape', '--render-dir', str(work / name),
            '--pdftoppm', r'C:\Users\SanAn\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe',
            '--json-out', str(work / f'{name}.json')]
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
    (work / f'{name}.stdout.txt').write_text(result.stdout, encoding='utf-8')
    (work / f'{name}.stderr.txt').write_text(result.stderr, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
values = root / 'fixtures/values.xlsx'
value_output = work / 'values-output.xlsx'
patch_workbook(values, value_output, {'sheets': {'清单': {'cells': {'C2': {'kind': 'number', 'value': 4}}}}}, False)
assert inspect_workbook(value_output)['formula_count'] == 0
assert inspect_workbook(value_output)['sheets']['清单']['cells']['C2']['value'] == '4'
test = subprocess.run([sys.executable, str(scripts / 'verify_xlsx.py'),
    str(root / 'fixtures/missing-cache.xlsx')], capture_output=True, text=True, encoding='utf-8')
assert test.returncode == 2 and not json.loads(test.stdout)['ok']
hashes = json.loads((root / 'fixture-hashes.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((root / 'fixtures' / name).read_bytes()).hexdigest() == sha for name, sha in hashes.items())
results = {'status': 'PASS', 'numeric_change': {'A_sum': 45, 'total': 105},
    'format_no_recalc_preserved': True, 'no_formula_no_recalc': True,
    'missing_cache_rejected': True, 'protected_fixtures_unchanged': True,
    'pdfs_rendered': 2, 'visual_inspection': 'pending'}
(work / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results))
