import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard/scripts')
from whiteboard import Runner
parent=Path(r'D:/BaiduSyncdisk/Paper/202607_THz_freq_planning/过程文件/实验方案精简/第一节框图/功率与放大级标签_20261013/正式修改_20261014')
request=json.loads((parent/'request.json').read_text(encoding='utf-8'))
request['operations']=[];request.pop('capture_preview',None)
r=Runner(request,ROOT/'business-roundoff-readonly','http://127.0.0.1:3456')
try:
    raw,name=r.export();r.open_page();state=r.hydrate(raw);r.write('fresh-native.json',state)
    r.report.update(status='readonly_verified',initial_raw=name)
    print(json.dumps({'status':'readonly_verified','line':next(n for n in state['nodes'] if n['id']=='c3:11'),
                      'endpoints':state['line_endpoints']['c3:11'],'bindings':next(n for n in state['binding_geometry'] if n['id']=='c3:11')},ensure_ascii=False,indent=2))
finally:r.close()
