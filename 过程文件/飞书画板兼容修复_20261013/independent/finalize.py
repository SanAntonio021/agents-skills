import hashlib
import json
from pathlib import Path

root=Path(__file__).parent
load=lambda path:json.loads((root/path).read_text(encoding='utf-8-sig'))
created=load('create-result.json')['data']['document']
append=load('01_append/result.json')
edit=load('02_edit/result.json')
viewer=load('original-png-white-viewer-result.json')
before={n['id']:n for n in load('01_append/raw-005.json')['nodes']}
after={n['id']:n for n in load('final-raw.json')['nodes']}
latest={n['id']:n for n in load('02_edit/raw-016.json')['nodes']}
assert set(before)==set(after)==set(latest)
assert after==latest
assert before['o2:2']==after['o2:2']
assert before['o2:3']==after['o2:3']
expected={'o2:1':'发射放大级\nPA / LNA','a2:1':'测试记录\nA 端','c2:1':'3–10 dBm','c2:2':'实际 LO：4 fSG\nLO 输入约 +10 dBm'}
for ident,text in expected.items():
    found=after[ident]['connector']['captions']['data'][0]['text'] if after[ident]['type']=='connector' else after[ident]['text']['text']
    assert found==text
bindings={}
for ident in ('c2:1','c2:2'):
    c=after[ident]['connector']
    bindings[ident]={'start':c['start_object'],'end':c['end_object']}
    assert c['start_object']==before[ident]['connector']['start_object']
    assert c['end_object']==before[ident]['connector']['end_object']
    assert c['start']['attached_object']==c['start_object']
    assert c['end']['attached_object']==c['end_object']
assert not before['c2:1']['connector'].get('captions',{}).get('data')
assert before['c2:2']['connector']['captions']['data'][0]['text']=='初始 LO 标签'
receipts=append['cleanup_receipts']+edit['cleanup_receipts']
assert all(r['status']=='confirmed' and r['page_status']=='closed' and r['receipt']['closed']==1 and r['receipt']['released']==0 for r in receipts)
assert viewer['page_status']=='closed' and viewer['cleanup_receipt']['closed']==1 and viewer['cleanup_receipt']['released']==0
report={
 'status':'passed',
 'skill':str(root.parent/'candidate/lark-whiteboard/SKILL.md'),
 'document_url':created['url'],'document_token':created['document_id'],
 'whiteboard_token':created['new_blocks'][0]['block_token'],'block_id':created['new_blocks'][0]['block_id'],
 'node_count':len(after),'native_ids':sorted(after),
 'requested_final_text':expected,
 'initial_caption_states':{'c2:1':'no label','c2:2':'初始 LO 标签'},
 'saves':[{k:s.get(k) for k in ('operation','save_status','verification_status','reopen_status','save_evidence','native_persistence')} for s in append['steps']+edit['steps']],
 'protection':{'node_ids_preserved':True,'second_signal_module_entire_raw_unchanged':True,'observation_module_entire_raw_unchanged':True,'fresh_cli_matches_last_reopened_raw':True,'connector_bindings_unchanged':bindings},
 'visual_review':{'status':'passed','actually_viewed':['02_edit/preview.png','original-png-white-viewer.png','final-preview.jpg'],'original_native_png':'02_edit/preview.png','white_viewer':'original-png-white-viewer.png','service_preview':'final-preview.jpg','finding':'四项请求内容及换行可读，两个模块、观察模块、独立文字和两条绑定线完整可见；线标签未遮挡模块。原生PNG有透明背景，以白底查看器实际显示原图核验。'},
 'results_json':['create-result.json','01_append/result.json','02_edit/result.json','original-png-white-viewer-result.json','final-preview-result.json','final-raw-result.json'],
 'page_cleanup':{'status':'confirmed','total_pages_closed':len(receipts)+1,'released':0,'runner_receipts':receipts,'white_viewer_receipt':viewer['cleanup_receipt']},
 'content_calls_replayed':False,
 'scope':'仅新建与编辑本次临时文档/画板；未修改候选技能源码或其他现有文档'
}
report['evidence_files']=[{'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.rglob('*')) if p.is_file() and p.name!='final-evidence.json']
(root/'final-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ('status','node_count','page_cleanup','document_url')},ensure_ascii=False))
