import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=Path(r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard')
CANDIDATE=ROOT/'candidate/lark-whiteboard'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
reports={name:read(ROOT/name/'result.json') for name in ['seed-run','smoke-run','smoke-remainder-run','caption-run','caption-remainder-run','text-run','final-readonly-run']}
final=read(ROOT/'final-readonly-run/inspect-000.json')
initial=read(ROOT/'seed-run/reopened-001.json')
initial_lookup={n['id']:n for n in initial['nodes']};final_lookup={n['id']:n for n in final['nodes']}
protected=['o3:2','o3:3']
assert all(initial_lookup[n]==final_lookup[n] for n in protected)
assert all(initial['render_alpha'][n]==final['render_alpha'][n] for n in protected)
assert initial['line_endpoints']==final['line_endpoints']
finalraw=read(sorted((ROOT/'final-readonly-run').glob('raw-*.json'))[-1])
initialraw=read(ROOT/'seed-run/raw-004.json')
assert all(next(n for n in initialraw['nodes'] if n['id']==i)==next(n for n in finalraw['nodes'] if n['id']==i) for i in protected)
steps={name:[{k:s.get(k) for k in ['operation','save_status','verification_status','failure_phase','reopen_status']} for s in report['steps']] for name,report in reports.items()}
summary={'signature_evidence':'source-comparison.json','isolated_document':read(ROOT/'created.json')['data']['document']['url'],
 'reports':{k:{'status':v['status'],'reason':v.get('reason'),'page_status':v.get('page_status')} for k,v in reports.items()},'steps':steps,
 'final_readonly_confirmation':{'native_save':final['native_save'],'node_count':len(final['nodes']),'protected_raw_and_native_unchanged':protected,
 'all_line_endpoints_unchanged':True,'deleted_during_unsupported_native_text_clear':['a3:1'],'final_captions':{n['id']:n['caption'] for n in final['nodes'] if n['kind']=='connector'}},
 'visual_evidence':{'original_native_png':'final-readonly-run/preview.png','white_background_server_preview':'final-preview.jpg','review':'Both viewed; two multiline line captions are readable and no module overlap; native PNG has transparent background.'},
 'unknown_page':{'task_and_tab':[r for r in reports['text-run']['cleanup_receipts'] if r.get('page_status')=='released'],'state':'Released after unknown content result; subsequent independent native and CLI readbacks confirmed the text object deleted. Released page was not reacquired.'},
 'candidate_sha256':{f:digest(CANDIDATE/'scripts'/f) for f in ['editor.js','whiteboard.py']},
 'source_sha256':{f:digest(SOURCE/'scripts'/f) for f in ['editor.js','whiteboard.py']},
 'source_extra_guard':'Refuse independent-text empty strings before write in Python preflight and native adapter; added failure checks. Candidate remains frozen.',
 'validation':{'python_unittest':{'count':231,'status':'passed'},'node_checks':['test_editor.cjs','test_editor_guards.cjs'],'git_diff_check':'passed'},
 'scope':'Only new isolated whiteboard written; user experiment board not opened for mutation. No commit, push or publication.'}
(ROOT/'acceptance-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:summary[k] for k in ['candidate_sha256','source_sha256','validation']},ensure_ascii=False,indent=2))
