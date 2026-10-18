from pathlib import Path
import os, json, subprocess, hashlib, zipfile
import openpyxl

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'fixtures' / 'calculated.xlsx'
SCRIPTS = Path(r'D:\BaiduSyncdisk\.agents\skills\xlsx\scripts')
PYTHON = r'C:\Python313\python.exe'
env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', TEMP=str(ROOT / 'temp'), TMP=str(ROOT / 'temp'))
(ROOT / 'temp').mkdir(exist_ok=True)
LOG = ROOT / 'commands.jsonl'

def run(script, *args):
    command = [PYTHON, str(SCRIPTS / script), *map(str,args)]
    r = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
    with LOG.open('a',encoding='utf-8') as f:
        f.write(json.dumps({'argv':command,'cwd':str(ROOT),'environment_overrides':{k:env[k] for k in ['PYTHONUTF8','PYTHONDONTWRITEBYTECODE','TEMP','TMP']},'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},ensure_ascii=False)+'\n')
    print(script, r.returncode, flush=True)
    if r.returncode: raise RuntimeError(r.stderr or r.stdout)
    return json.loads(r.stdout)

def write_json(name, data):
    p = ROOT / name
    with p.open('x',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
    return p

source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
parts = zipfile.ZipFile(SOURCE).namelist()
for name, cell, value in [('note','F3','新备注'),('category','A4','A')]:
    spec = write_json(name+'-patch.json',{'sheets':{'计算表':{'cells':{cell:{'kind':'string','value':value}}}}})
    policy = write_json(name+'-policy.json',{'allowed_cells':['计算表!'+cell], 'allowed_package_entries':[], 'required_unchanged_entries':[p for p in parts if p!='xl/worksheets/sheet1.xml'], 'allow_formula_cache_changes':name=='category','expected':{'formula_count':5,'formula_cache_count':5,'formula_error_count':0}})
    draft = ROOT / (name+'-draft.xlsx')
    run('patch_ooxml.py', SOURCE, draft, '--spec', spec)
    candidate = draft
    if name=='category':
        recalculated = ROOT / 'category-recalculated.xlsx'
        run('libreoffice_headless.py','recalc',draft,recalculated,'--json-out',ROOT/'category-recalc.json')
        candidate = ROOT/'category-candidate.xlsx'
        run('merge_formula_caches.py',draft,recalculated,candidate)
    result = run('verify_xlsx.py',candidate,'--baseline',SOURCE,'--policy',policy,'--json-out',ROOT/(name+'-verification.json'))
    assert result['ok']
    formula = openpyxl.load_workbook(candidate,data_only=False)
    cached = openpyxl.load_workbook(candidate,data_only=True)
    assert formula['计算表'][cell].value == value
    assert cached['计算表']['E3'].value == (25 if name=='note' else 85)
    assert cached['计算表']['E5'].value == 85
    expected = {'D3':20,'D4':60,'D5':5}
    assert all(cached['计算表'][c].value==v for c,v in expected.items())
    run('libreoffice_headless.py','pdf',candidate,ROOT/(name+'-preview.pdf'),'--json-out',ROOT/(name+'-render.json'))
    import fitz
    pdf = fitz.open(ROOT/(name+'-preview.pdf'))
    assert len(pdf)==1
    pdf[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(ROOT/(name+'-preview.png'))
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==source_hash
write_json('result-before-visual.json',{'source_sha256':source_hash,'note_E3':25,'category_E3':85,'E5_both':85,'formulas_each':5,'caches_each':5,'errors_each':0,'source_unchanged':True,'visual_review':'pending','native_open':'not_requested'})
