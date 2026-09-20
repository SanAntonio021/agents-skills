"""Synthetic request-origin cases; no user transcript or local source paths."""
import copy
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get('AUDIT_SKILL_ROOT', Path(__file__).resolve().parents[1]))
def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result
AUDIT = module('audit_skill_usage')
REVIEW = module('run_weekly_skill_review')
PREFIXES = (
    'The following is the Codex agent history added since your last approval assessment.',
    'The following is the Codex agent history whose request action you are assessing.',
)

class RequestOriginTests(unittest.TestCase):
    def audit(self, origin, text):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ['skills/alpha', 'skills/beta', 'codex', 'claude', 'telemetry']:
                (root / folder).mkdir(parents=True)
            for name, desc in [('alpha', 'alpha task'), ('beta', 'frequency spectrum curve plotting')]:
                (root / 'skills' / name / 'SKILL.md').write_text(
                    f'---\nname: {name}\ndescription: {desc}\n---\n', encoding='utf-8')
            rows = [
                {'type':'session_meta','payload':{'id':'synthetic', **origin}},
                {'type':'event_msg','timestamp':'2026-01-01T00:01:00Z','payload':{
                    'type':'item_completed','turn_id':'request-1','item':{
                        'type':'UserMessage','id':'message-1','content':text}}},
                {'type':'event_msg','timestamp':'2026-01-01T00:01:01Z','payload':{
                    'type':'item_completed','turn_id':'request-1','item':{
                        'type':'CommandExecution','id':'read-1','command':f'Get-Content {root / "skills/alpha/SKILL.md"}',
                        'status':'completed','exit_code':0}}},
            ]
            (root / 'codex/sample.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            args=AUDIT.parse_args(['--reports-root',str(root/'reports'),'--date','2026-01-03',
                '--window-start','2025-12-27T14:00:00+08:00','--window-end','2026-01-03T14:00:00+08:00',
                '--skills-root',str(root/'skills'),'--codex-sessions-root',str(root/'codex'),
                '--claude-projects-root',str(root/'claude'),'--claude-telemetry-root',str(root/'telemetry')])
            return AUDIT.audit(args)

    def test_guardian_origins_exclude_entire_request(self):
        origins = [
            {'source':{'subagent':{'other':'guardian'}},'thread_source':'guardian_review'},
            {'source':{'subagent':{'other':'guardian'}}},
            {'thread_source':'guardian_review'},
        ]
        for origin in origins:
            for prefix in PREFIXES:
                with self.subTest(origin=origin,prefix=prefix):
                    result=self.audit(origin,prefix+'\n$alpha frequency spectrum curve plotting')
                    self.assertEqual(result['usage_evidence'],{})
                    self.assertEqual(result['classifications']['疑似漏用'],[])
                    self.assertEqual(result['warnings']['approval_review_excluded_count'],1)
                    self.assertEqual(result['warnings']['bridge_copy_excluded_count'],0)

    def test_ordinary_user_quoting_prefixes_keeps_real_usage_and_candidates(self):
        for origin in [{},{'source':'cli'}, {'source':{'subagent':{'other':'worker'}},'thread_source':'chat'}]:
            for prefix in PREFIXES:
                with self.subTest(origin=origin,prefix=prefix):
                    result=self.audit(origin,prefix+'\n$alpha frequency spectrum curve plotting')
                    evidence=result['usage_evidence']['alpha']
                    self.assertEqual(len(evidence),1)
                    self.assertEqual(evidence[0]['evidence_kinds'],['explicit_user_invocation','observed_skill_read'])
                    self.assertTrue(result['classifications']['疑似漏用'])
                    self.assertEqual(result['warnings'].get('approval_review_excluded_count',0),0)

    def test_semantics_migration_preserves_prior_decisions_and_resets_streak(self):
        state=REVIEW.new_state()
        state['usage_semantics_version']=2
        state['unseen_streaks']={'alpha':{'count':3,'last_counted_date':'2026-08-15','last_window_end':'2026-08-15T14:00:00+08:00'}}
        state['findings']={'old-closed':{'status':'closed','decisions':[{'classification':'reject'}]}}
        state['batches']={'old-completed':{'status':'completed'}}
        protected=copy.deepcopy((state['findings'],state['batches']))
        usage={'version':'skill-usage-audit-v3','configuration':{'count_unit':'request'},
            'window':{'start':'2026-08-15T14:00:00+08:00','end':'2026-08-22T14:00:00+08:00'},
            'skill_inventory':[{'skill':'alpha','active_hosts':['codex']}],
            'classifications':{'已用':[],'历史内未见使用':[{'skill':'alpha','active_hosts':['codex']}]}}
        counts, reason=REVIEW.update_unseen_streaks(state,usage,complete=True,scope_value='same',date='2026-08-22')
        self.assertEqual(reason,'usage_semantics_changed')
        self.assertEqual(counts,{'alpha':1})
        self.assertEqual(state['usage_semantics_version'],3)
        self.assertEqual((state['findings'],state['batches']),protected)
        counts,reason=REVIEW.update_unseen_streaks(state,usage,complete=True,scope_value='same',date='2026-08-22')
        self.assertEqual(counts,{'alpha':1})
        self.assertIsNone(reason)

    def test_real_audit_output_satisfies_weekly_summary_contract(self):
        result=self.audit({'source':'cli'}, '$alpha frequency spectrum curve plotting')
        self.assertEqual(REVIEW.summary_is_valid(result,'usage','2026-01-03'),(True,None))
        stale=copy.deepcopy(result)
        stale['version']='skill-usage-audit-v2'
        self.assertFalse(REVIEW.summary_is_valid(stale,'usage','2026-01-03')[0])

    def test_minimal_scan_cli_accepts_real_v3_audit_output(self):
        usage=self.audit({'source':'cli'}, '$alpha frequency spectrum curve plotting')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            reports=root/'reports'
            summaries={
                '2026-01-03/summary.json':{'schema_version':1,'date':'2026-01-03','sources':[],'check_error_count':0},
                'manifests/2026-01-03/summary.json':{'version':'flat-skill-tree-v1','date':'2026-01-03','findings':{}},
                'usage/manifests/2026-01-03/summary.json':usage,
            }
            for rel,data in summaries.items():
                dest=reports/rel; dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_text(json.dumps(data),encoding='utf-8')
            (root/'skills').mkdir()
            result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'scripts/run_weekly_skill_review.py'),
                'scan','--agents-root',str(root),'--skills-root',str(root/'skills'),
                '--reports-root',str(reports),'--state',str(reports/'state.json'),
                '--date','2026-01-03','--reuse-reports','--json'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            receipt=json.loads(result.stdout)
            self.assertTrue(receipt['complete'])
            self.assertTrue(receipt['dashboard']['valid'])
            report=json.loads((reports/'2026-01-03/weekly-review.json').read_text(encoding='utf-8'))
            self.assertTrue(report['validation']['usage']['valid'])

if __name__=='__main__': unittest.main()
