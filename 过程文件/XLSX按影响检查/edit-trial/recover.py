from pathlib import Path
import os,json,subprocess,hashlib
import openpyxl,fitz
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'fixtures'/'calculated.xlsx'
SCRIPTS=Path(r'D:\BaiduSyncdisk\.agents\skills\xlsx\scripts')
PYTHON=r'C:\Python313\python.exe'
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',TEMP=str(ROOT/'temp'),TMP=str(ROOT/'temp'))
def run(script,*args):
    argv=[PYTHON,str(SCRIPTS/script),*map(str,args)]
    r=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    with (ROOT/'commands.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps({'argv':argv,'cwd':str(ROOT),'environment_overrides':{k:env[k] for k in ['PYTHONUTF8','PYTHONDONTWRITEBYTECODE','TEMP','TMP']},'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},ensure_ascii=False)+'\n')
    print(script,r.returncode,flush=True)
    if r.returncode: raise RuntimeError(r.stderr or r.stdout)
    return json.loads(r.stdout)
wb=openpyxl.load_workbook(ROOT/'category-draft.xlsx',data_only=False)
cells={c.coordinate:{'kind':'formula','formula':c.value[1:]} for row in wb['计算表'] for c in row if c.data_type=='f'}
spec=ROOT/'clear-calculation-copy-caches.json'
with spec.open('x',encoding='utf-8') as f: json.dump({'sheets':{'计算表':{'cells':cells}}},f,ensure_ascii=False,indent=2)
run('patch_ooxml.py',ROOT/'category-draft.xlsx',ROOT/'category-calculation-input.xlsx','--spec',spec)
run('libreoffice_headless.py','recalc',ROOT/'category-calculation-input.xlsx',ROOT/'category-recalculated-v02.xlsx','--json-out',ROOT/'category-recalc-v02.json')
run('merge_formula_caches.py',ROOT/'category-draft.xlsx',ROOT/'category-recalculated-v02.xlsx',ROOT/'category-candidate-v02.xlsx')
result=run('verify_xlsx.py',ROOT/'category-candidate-v02.xlsx','--baseline',SOURCE,'--policy',ROOT/'category-policy.json','--json-out',ROOT/'category-verification-v02.json')
assert result['ok']
cached=openpyxl.load_workbook(ROOT/'category-candidate-v02.xlsx',data_only=True)
assert cached['计算表']['E3'].value==85,cached['计算表']['E3'].value
assert cached['计算表']['E5'].value==85
assert [cached['计算表'][c].value for c in ['D3','D4','D5']]==[20,60,5]
run('libreoffice_headless.py','pdf',ROOT/'category-candidate-v02.xlsx',ROOT/'category-preview.pdf','--json-out',ROOT/'category-render.json')
pdf=fitz.open(ROOT/'category-preview.pdf')
assert len(pdf)==1
pdf[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(ROOT/'category-preview.png')
print('Recovered E3=85, E5=85; visual review pending',flush=True)
