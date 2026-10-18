"""Isolated skill evaluation. No network, real credentials or Zotero writes."""
import argparse
import json
import time
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('case',choices=['ready','blocked'])
p.add_argument('command',choices=['check','start','status','login','download','import','verify','complete'])
p.add_argument('--root',required=True)
a=p.parse_args()
root=Path(a.root); root.mkdir(parents=True,exist_ok=True)
events=sorted(root.glob(a.case+'_*.event.json'))
state=json.loads(events[-1].read_text('utf-8'))['state'] if events else {'started':False,'access':False,'downloaded':False,'saved':False,'verified':False}
cmd=a.command
result={'simulation':True}
if cmd=='check':
 result.update(stage='ready',credential_available=True,pdf_reader_available=True,has_session=state['started'],browser_autofilled=False)
elif cmd=='start':
 if a.case=='blocked':result.update(stage='host_blocked',reason='blocked by policy',source='fixture approval gate')
 else:state['started']=True;result.update(stage='created')
elif cmd=='status':
 result.update(stage='institutional_access' if state['access'] else 'school_login' if state['started'] else 'no_session')
elif cmd=='login':
 if a.case=='blocked' or not state['started']:result.update(stage='invalid_action')
 else:state['access']=True;result.update(stage='institutional_access')
elif cmd=='download':
 if state['access']:
  state['downloaded']=True
  result.update(stage='downloaded_identity_verified',version='fixture_official',doi='10.0000/fixture-only',file='isolated fixture payload')
 else:result.update(stage='access_required')
elif cmd=='import':
 if state['downloaded']:state['saved']=True;result.update(stage='saved',parent='fixture-parent',attachment='fixture-attachment')
 else:result.update(stage='missing_payload')
elif cmd=='verify':
 if state['saved']:state['verified']=True;result.update(stage='verified',parent='fixture-parent',attachment='fixture-attachment',readable=True)
 else:result.update(stage='not_saved')
elif cmd=='complete':
 result.update(stage='completed',verified=state['verified']);state['started']=False
path=root/(a.case+'_'+str(time.time_ns())+'.event.json')
path.write_text(json.dumps({'command':cmd,'result':result,'state':state},ensure_ascii=False),'utf-8')
print(json.dumps(result,ensure_ascii=False))
