import json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
oldroot=Path(r'D:/BaiduSyncdisk/.agents/过程文件')
oldselect=json.loads((oldroot/'箭头文字编辑完善/inspect-labels-result.json').read_text(encoding='utf-8'))['value']['selectNodeText']
bundle=(oldroot/'画板局部编辑补齐/editor-bundle.js').read_text(encoding='utf-8')
process='processInput(e){this.inputTextProcessor.processInput(e)}'
assert process in bundle
start=bundle.index('blur(){var e;let r=!(arguments.length>0)')
end=bundle.index('refreshSelection(){',start)
blur=bundle[start:end]
functions=dict(selectNodeText=oldselect,processInput=process,blur=blur)
def fnv(s):
    h=2166136261
    for c in s:h=((h^ord(c))*16777619)&0xffffffff
    return format(h,'x')
current=json.loads((ROOT/'source-read/current-functions.json').read_text(encoding='utf-8'))
report={'old_signature':fnv(''.join(functions.values())),'current_signature':current['signature'],
        'old_sources':functions,'source_evidence':{'selectNodeText':str(oldroot/'箭头文字编辑完善/inspect-labels-result.json'),
        'processInput_and_blur':str(oldroot/'画板局部编辑补齐/editor-bundle.js'),
        'bundle_sha256':hashlib.sha256(bundle.encode()).hexdigest()},
        'unchanged':[k for k,v in functions.items() if v==current['functions'][k]],
        'blur_only_alias_change':blur.replace('w.C.TextNodeFocusStateChange','M.C.TextNodeFocusStateChange')==current['functions']['blur']}
(ROOT/'source-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('old_sources','source_evidence')},ensure_ascii=False))
