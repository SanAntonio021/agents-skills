import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
mapping=json.loads((ROOT/'seed-run/result.json').read_text(encoding='utf-8'))['id_mapping']
request=json.loads((ROOT/'isolated-target.json').read_text(encoding='utf-8'))
ops=[]
for local,values in [('o101301:1',['形状改字\n第二行','','形状新增文字\n完成']),('t101301:1',['独立文字\n第二行','','独立文字恢复\n完成']),('c101301:1',['新连线标签\n第二行','改写标签\n新的第二行','','最终标签\n完成']),('c101301:2',['已有标签改写\n保持第二行'])]:
    kind='caption' if local.startswith('c') else 'text'
    ops.extend(dict(kind=kind,id=mapping[local],text=text) for text in values)
request.update(operations=ops,capture_preview=True)
(ROOT/'smoke-request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(mapping,ensure_ascii=False))
