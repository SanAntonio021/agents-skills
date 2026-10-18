import json
import hashlib
from pathlib import Path
from zipfile import ZipFile
from pptx import Presentation

root = Path(__file__).resolve().parent
def read(name):
    return json.loads((root / name).read_text(encoding='utf-8-sig'))
manifest = read('production-manifest.json')
deck = Path(manifest['final_pptx'])
native = read('native-gate-v03.json')
typeaudit = read('typography-audit-v03.json')
assert native['ok'] and typeaudit['summary']['failures'] == 0
assert 'All validations PASSED!' in (root/'static-validate-v03-retry.txt').read_text(encoding='utf-8-sig')
assert hashlib.sha256(deck.read_bytes()).hexdigest() == manifest['final_sha256']
prs = Presentation(deck)
texts = []
titles = []
for i, slide in enumerate(prs.slides, 1):
    texts.append(f'<!-- Slide number: {i} -->\n'+'\n'.join(s.text for s in slide.shapes if s.has_text_frame and s.text.strip()))
    if i in (2, 3):
        pair = {s.name:s for s in slide.shapes if s.name in ('Title','SectionHeader')}
        assert pair['SectionHeader'].text.startswith('   ')
        assert pair['Title'].text_frame.paragraphs[0].runs[0].font.size.pt == 36
        assert pair['SectionHeader'].text_frame.paragraphs[0].runs[0].font.size.pt == 28
        titles.append({'slide': i, 'Title': pair['Title'].text, 'SectionHeader': pair['SectionHeader'].text, 'sizes_pt':[36,28]})
(root/'content-extraction-v03.md').write_text('\n\n'.join(texts),encoding='utf-8')
with ZipFile(root/'20261014_日报样例_技能流程测试_v01.pptx') as old, ZipFile(deck) as new:
    unchanged = {part: old.read(part)==new.read(part) for part in old.namelist() if part.startswith('ppt/') and part not in ('ppt/slides/slide2.xml','ppt/slides/slide3.xml')}
    assert all(unchanged.values())
result = {
 'final_pptx':str(deck),'sha256':manifest['final_sha256'],
 'CONTENT_PASS':True,'STATIC_PASS':True,'TYPOGRAPHY_PASS':True,
 'EDITABILITY_PASS':True,'NATIVE_OPEN_PASS':True,'NATIVE_RENDER_PASS':True,
 'VISUAL_PASS':True,'slide_count':4,'title_objects':titles,
 'unaffected_package_parts_unchanged':all(unchanged.values()),
 'typography_failures':0,'exceptions':[],
 'native_receipt':'native-gate-v03.json',
 'visual_review':'User reports that the main agent inspected v03 native PNG pages 2 and 3 and accepted the visuals; pages 1 and 4 unchanged from previously reviewed v01.',
 'not_verified':['LibreOffice compatibility render not run','Simulation raw data/model not supplied; no independent recomputation'],
 'scope_notes':['Initial v01 static validation used the system temporary directory; validator cleaned it automatically.',
 'v03 first validation exited on temporary-directory cleanup WinError32; bounded retry passed.',
 'Automatic policy rejected the broad temporary-directory cleanup command; no such deletion was performed. Existing residual temporary files retained.']
}
(root/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
manifest.update(powerpoint='PASS',visual='PASS',static='PASS',typography='PASS',acceptance='acceptance.json',native_png_directory=str(root/'native-png-v03'))
(root/'production-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'验收说明.md').write_text('''# 日报样例 v03 验收

最终产物：20261014_日报样例_技能流程测试_v03.pptx，4页。标题、正文、图注为原生可编辑文字；两张原图为独立可替换图片，图内像素不可逐项编辑。

第2、3页项目Title为36 pt，主题SectionHeader为28 pt；同一行保留三个ASCII空格间距。无豁免，未改技能或检查器。750 MBaud已更正；2026-10-12仿真明确标作本期分析证据；两种接收连接分开进行。

- 内容核对：通过。
- OOXML结构：有界重试通过，退出码0。首次失败为临时文件清理WinError32，原始输出保留。
- 字号：通过，0失败、无豁免，最低12 pt。
- 可编辑性：通过，两个独立图片，无整页扁平化。
- 画布：12192000×6858000 EMU，沿用已通过的16:9检查，当前文件尺寸未变。
- PowerPoint原生打开、4页PNG导出：通过，源文件哈希前后一致。
- 视觉：已检查v03修改页2、3；页1、4及其余包内容与已审v01相同。

未验证：LibreOffice兼容渲染未执行；未提供仿真原始数据和模型，不做独立复算。私人词表不在许可资料范围，未做个人词表审计。无硬件实测验收。

实际操作：produce.py使用原内置生成器生成，再在样例内拆分标题对象；python_runtime_preflight.py选择C:/Python313/python.exe；office/validate.py、typography_audit.py、pptx_editability_audit.py实际检查，完整结果保存在同目录带v03名称文件中；office_native_gate.py使用已验签的Microsoft POWERPNT.EXE打开隔离副本，PNG位于native-png-v03。图文依据见deck-brief.md，源图及工具哈希见production-manifest.json。

操作范围偏差：首轮v01静态检查未定向TEMP，产生的系统临时解包目录已由校验器清理。后续操作已定向production。清理残留临时目录的宽泛命令被自动安全审核拒绝，未执行删除，残留材料保留。
''',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
