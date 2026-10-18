import json
from pathlib import Path
P=Path(r'D:/BaiduSyncdisk/Paper/202607_THz_freq_planning/过程文件/实验方案精简/第一节框图/功率与放大级标签_20261013/正式修改_20261014/edit_001')
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
old,new=read('raw-005.json'),read('raw-006.json')
pre,post=read('inspect-000.json'),read('editor-001.json')
line='c3:11'
report={'before_raw':next(n for n in old['nodes'] if n['id']==line),
        'after_raw':next(n for n in new['nodes'] if n['id']==line),
        'native_before':next(n for n in pre['nodes'] if n['id']==line),
        'native_after':next(n for n in post['nodes'] if n['id']==line),
        'endpoints_before':pre['line_endpoints'][line],'endpoints_after':post['line_endpoints'][line],
        'bindings_before':next(n for n in pre['binding_geometry'] if n['id']==line),
        'bindings_after':next(n for n in post['binding_geometry'] if n['id']==line),
        'world_before':pre['world_geometry'][line],'world_after':post['world_geometry'][line]}
Path(__file__).with_name('business-roundoff-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
