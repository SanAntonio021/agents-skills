import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'candidate/lark-whiteboard/scripts'))
from native_nodes import compile_diagram
from whiteboard import validate_append_payload
target=json.loads((ROOT/'isolated-target.json').read_text(encoding='utf-8'))
target['capture_preview']=True
(ROOT/'seed-request.json').write_text(json.dumps(target,ensure_ascii=False,indent=2),encoding='utf-8')
raw=compile_diagram({'shapes':[
 {'id':'o101301:1','text':'目标形状\n初始文字','x':50,'y':80,'width':180,'height':90},
 {'id':'o101301:2','text':'保护模块','x':700,'y':80,'width':180,'height':90},
 {'id':'o101301:3','text':'保持原样\n非目标观察','x':700,'y':400,'width':180,'height':90}],
 'connectors':[
 {'id':'c101301:1','start_id':'o101301:1','end_id':'o101301:2'},
 {'id':'c101301:2','start_id':'o101301:1','end_id':'o101301:3','label':'已有标签\n原第二行'}]})
raw['nodes'].append({'id':'t101301:1','type':'text_shape','x':50,'y':400,'width':220,'height':50,'angle':0,'z_index':1,
                    'text':dict(raw['nodes'][0]['text'],text='独立文本初始')})
validate_append_payload(raw)
(ROOT/'seed-native.json').write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding='utf-8')
