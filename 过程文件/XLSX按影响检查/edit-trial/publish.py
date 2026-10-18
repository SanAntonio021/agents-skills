from pathlib import Path
import os,json,subprocess,hashlib,zipfile
import openpyxl
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'fixtures'/'calculated.xlsx'
SCRIPTS=Path(r'D:\BaiduSyncdisk\.agents\skills\xlsx\scripts')
PYTHON=r'C:\Python313\python.exe'
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
outputs=[]
for candidate,name,expected in [('note-draft.xlsx','备注修改_v01.xlsx',25),('category-candidate-v02.xlsx','类别修改_v01.xlsx',85)]:
    argv=[PYTHON,str(SCRIPTS/'publish_output.py'),str(ROOT/candidate),str(ROOT/name)]
    r=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8')
    with (ROOT/'commands.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps({'argv':argv,'cwd':str(ROOT),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr},ensure_ascii=False)+'\n')
    assert r.returncode==0,r.stdout+r.stderr
    result=json.loads(r.stdout)
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest().lower()==result['published_sha256'].lower()
    assert (ROOT/name).read_bytes()==(ROOT/candidate).read_bytes()
    assert zipfile.ZipFile(ROOT/name).testzip() is None
    wb=openpyxl.load_workbook(ROOT/name,data_only=True)
    assert wb['计算表']['E3'].value==expected and wb['计算表']['E5'].value==85
    outputs.append(result)
baseline=json.loads((ROOT/'baseline.json').read_text(encoding='utf-8'))
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest().lower()==baseline['workbook']['sha256'].lower()
record={'source':str(SOURCE),'source_sha256':baseline['workbook']['sha256'],'source_unchanged':True,'outputs':outputs,'STATIC_PASS':True,'LO_RENDER_PASS':True,'NATIVE_OPEN':'not_requested_no_COM','formula_count_each':5,'cache_count_each':5,'error_count_each':0,'initial_category_recalc':'tool_returned_success_but_E3_stale_25_rejected_by_numeric_assertion','category_recovery':'clear_formula_caches_on_calculation_copy_then_runner_recalc_and_signature_checked_cache_merge','final_category_E3':85,'note_E3':25,'E5_both':85,'visual_review':'Both actual LibreOffice rendered PNGs viewed; changed cells and surrounding table text complete, no clipping or overlap. PDFs are internal previews only.'}
with (ROOT/'execution-result.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
text='''# 执行记录

- 输入：`../fixtures/calculated.xlsx`，源文件哈希核对未变。
- 输出：`备注修改_v01.xlsx` 只改 F3 原备注→新备注；`类别修改_v01.xlsx` 只改 A4 B→A，以及其依赖 E3 的公式缓存 25→85。
- 两个版本均独立基于源文件，5 个公式、5 个有效缓存、0 个错误；D3/D4/D5 为 20/60/5，E5 全表合计保持 85。
- 定点补丁使用技能 patch_ooxml；类别计算使用隔离 libreoffice_headless recalc 与 merge_formula_caches。首次 recalc 虽返回成功，E3 仍为 25，被实际数值断言拦截；保留该过程文件。恢复步骤只清空专用计算副本的 5 个缓存，重算后签名核对并回填到权威候选。
- verify_xlsx 与包级比较通过：只改 xl/worksheets/sheet1.xml；备注版仅 F3 值变化，类别版仅 A4 值及 E3 缓存变化。公式文本、全部样式、批注、VML、验证规则、行高、列宽与其他包条目保持。
- 已查看两个候选的实际 LibreOffice 渲染，目标单元格和周边文字完整，无裁切或重叠。辅助 PDF/PNG 仅留在过程目录，无 PDF 交付。
- 正式文件经 publish_output 发布，并复核发布哈希、ZIP 完整性、openpyxl 可读取性与代表性数值。未运行 Excel 原生检查，未使用 Excel COM 或用户窗口。
- 实际工具 argv、工作目录、退出码、标准输出和错误详见 commands.jsonl；补丁、政策、重算及核验 JSON 均保留。Python 为 C:\\Python313\\python.exe；子进程设置 PYTHONUTF8=1、PYTHONDONTWRITEBYTECODE=1；LibreOffice TEMP/TMP 指向本目录 temp。runner 使用其固定全局槽锁（工具内部状态）；所有任务产物和隔离转换目录在 edit-trial 内。
'''
with (ROOT/'执行记录.md').open('x',encoding='utf-8') as f:f.write(text)
print(json.dumps(record,ensure_ascii=False,indent=2))
