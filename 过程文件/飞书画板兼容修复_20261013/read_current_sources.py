"""Read only the three text functions from this task's new isolated board."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard/scripts')))
from whiteboard import Runner

created=json.loads((ROOT/'created.json').read_text(encoding='utf-8-sig'))['data']['document']
board=created['new_blocks'][0]['block_token']
request=dict(document_url=created['url'],whiteboard_token=board,operations=[],block_id=created['new_blocks'][0]['block_id'])
(ROOT/'isolated-target.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
r=Runner(request,ROOT/'source-read', 'http://127.0.0.1:3456')
try:
    r.open_page()
    expression='''(()=>{
      const matches=[];
      for(const el of document.querySelectorAll('.whiteboard-canvas-container')){
        let f=el[Object.keys(el).find(k=>/^__react(InternalInstance|Fiber)/.test(k))];
        for(let i=0;f&&i<8;i++,f=f.return){const a=f.memoizedProps?.app;
          if(a?.docState?.whiteboardToken===BOARD && a.docState.docxToken===DOC)matches.push(a);}
      }
      const unique=[...new Set(matches)];if(unique.length!==1)throw Error('ISOLATED_BOARD_NOT_UNIQUE');
      const a=unique[0];
      const functions={selectNodeText:a.api.selectNodeText.toString(),processInput:a.inputManager.processInput.toString(),blur:a.inputManager.blur.toString()};
      let h=2166136261; const src=Object.values(functions).join('');for(let i=0;i<src.length;i++){h^=src.charCodeAt(i);h=Math.imul(h,16777619)}
      return {origin:location.origin,path:location.pathname,docx_token:a.docState.docxToken,board_token:a.docState.whiteboardToken,functions,signature:(h>>>0).toString(16)};
    })()'''.replace('BOARD',json.dumps(board)).replace('DOC',json.dumps(created['document_id']))
    value=r.call('/v2/tabs/'+r.tab+'/eval',{'expression':expression})['value']
    r.write('current-functions.json',value)
    print(json.dumps(value,ensure_ascii=False,indent=2))
finally:
    r.close()
