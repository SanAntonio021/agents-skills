import json
import importlib.util
from pathlib import Path

root = Path(__file__).parent
skill = root.parent / 'candidate' / 'lark-whiteboard'
specmod = importlib.util.spec_from_file_location('native_nodes', skill / 'scripts' / 'native_nodes.py')
module = importlib.util.module_from_spec(specmod)
specmod.loader.exec_module(module)
document = json.loads((root / 'create-result.json').read_text(encoding='utf-8-sig'))['data']['document']
spec = {
  'shapes': [
    {'id':'o1013ind:1','text':'发射处理模块','shape':'round_rect','x':80,'y':160,'width':240,'height':110,'font_size':24},
    {'id':'o1013ind:2','text':'接收处理模块','shape':'round_rect','x':540,'y':160,'width':240,'height':110,'font_size':24},
    {'id':'o1013ind:3','text':'观察模块\n保持原样','shape':'rect','x':1180,'y':160,'width':240,'height':110,'font_size':24,'fill_color':'#F1F3F5','border_color':'#606670'}
  ],
  'connectors': [
    {'id':'c1013ind:1','start_id':'o1013ind:1','end_id':'o1013ind:2'},
    {'id':'c1013ind:2','start_id':'o1013ind:2','end_id':'o1013ind:3','label':'初始 LO 标签'}
  ]
}
raw = module.compile_diagram(spec)
text = dict(raw['nodes'][0]['text'])
text.update(text='初始测试记录', horizontal_align='left', vertical_align='top')
raw['nodes'].append(dict(id='t1013ind:1',type='text_shape',x=80,y=360,width=280,height=58,angle=0,z_index=3,text=text))
request = {'document_url':document['url'],'whiteboard_token':document['new_blocks'][0]['block_token'],'operations':[],'capture_preview':True}
for filename,data in [('diagram.json',spec),('native.json',raw),('append-request.json',request)]:
  (root/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
