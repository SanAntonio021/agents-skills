import base64
import json
import urllib.request
import uuid
from pathlib import Path

root = Path(__file__).parent
proxy = 'http://127.0.0.1:3456'
token = None
task = None
report = {'purpose':'Display the unmodified original native PNG against a white viewer background','source':'02_edit/preview.png'}

def request(method,path,body=None,timeout=10):
    headers={}
    if token:
        headers['Authorization']='Bearer '+token
    if method!='GET':
        headers.update({'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())})
    req=urllib.request.Request(proxy+path,data=None if body is None else json.dumps(body).encode(),headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=timeout) as response:
        data=response.read()
        return json.loads(data) if 'json' in response.headers.get('Content-Type','') else data

try:
    created=request('POST','/v2/tasks',{})
    token=created['taskToken']; task=created['taskId']
    report['task_id']=task
    tab=request('POST','/v2/tabs',{'url':'about:blank','background':True})
    target=tab['targetId']; report['tab_id']=target
    original=base64.b64encode((root/'02_edit'/'preview.png').read_bytes()).decode()
    html='<html><head><title>Original native PNG — white viewer</title></head><body style="margin:0;background:#fff"><img id="original" style="display:block;width:100%;height:auto" src="data:image/png;base64,'+original+'"></body></html>'
    expression='document.open();document.write('+json.dumps(html)+');document.close();true'
    request('POST','/v2/tabs/'+target+'/eval',{'expression':expression})
    metadata=request('POST','/v2/tabs/'+target+'/eval',{'expression':'JSON.stringify({title:document.title,complete:document.images[0].complete,naturalWidth:document.images[0].naturalWidth,naturalHeight:document.images[0].naturalHeight,background:getComputedStyle(document.body).backgroundColor})'})
    report['viewer_metadata']=metadata
    screenshot=request('GET','/v2/tabs/'+target+'/screenshot?format=png',timeout=5)
    if not isinstance(screenshot,bytes) or not screenshot.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Viewer screenshot did not return PNG')
    (root/'original-png-white-viewer.png').write_bytes(screenshot)
    report['viewer_screenshot']='original-png-white-viewer.png'
    report['status']='captured'
except Exception as error:
    report.update(status='failed',error=type(error).__name__)
finally:
    if task:
        try:
            receipt=request('POST','/v2/tasks/'+task+'/complete',{'keep':False})
            report['cleanup_receipt']=receipt
            report['page_status']='closed' if receipt.get('closed')==1 and receipt.get('released')==0 else 'unknown'
        except Exception as error:
            report.update(page_status='unknown',cleanup_error=type(error).__name__)
    (root/'original-png-white-viewer-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
