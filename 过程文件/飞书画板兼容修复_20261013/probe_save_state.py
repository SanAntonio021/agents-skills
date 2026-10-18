import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'candidate/lark-whiteboard/scripts'))
from whiteboard import Runner
request=json.loads((ROOT/'isolated-target.json').read_text(encoding='utf-8'))
r=Runner(request,ROOT/'save-state-probe','http://127.0.0.1:3456')
timeline=[]
try:
    r.open_page()
    for n in range(12):
        t=time.monotonic();state=r.editor({'kind':'inspect'})
        timeline.append(dict(n=n,elapsed=t,native_save=state['native_save']))
        r.write('timeline.json',timeline)
        if n==3:
            try:timeline.append(dict(entry=r.editor({'kind':'enter'})))
            except Exception as e:timeline.append(dict(entry_error=str(e)))
        time.sleep(.5)
    print(json.dumps(timeline,ensure_ascii=False,indent=2))
finally:r.close()
