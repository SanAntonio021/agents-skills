"""Fault-boundary tests; these do not substitute for live board acceptance."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from whiteboard import Runner, NotReady, VerificationError, projection, main
from native_nodes import compile_diagram
import test_local_edits as local_edits


class Clock:
    def __init__(self):
        self.now = 0
    def monotonic(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class Lifecycle(unittest.TestCase):
    def runner(self, operations):
        return local_edits.DeleteUndoRunnerTests('runTest').make_runner(operations)

    def test_native_prewrite_rejection_records_not_written_and_closes(self):
        runner = self.runner([{'kind':'text','id':'b','text':'changed'}])
        editor = runner.editor
        def reject(op, expected=None):
            if op['kind'] == 'text':
                error = VerificationError('Rejected before native content call')
                error.content_write_started = False
                raise error
            return editor(op, expected)
        runner.editor = reject
        with self.assertRaises(VerificationError):
            runner.run()
        step = runner.report['steps'][0]
        self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']), ('not_written','failed','execute'))
        self.assertFalse(runner.uncertain)
        runner.close()
        self.assertEqual(runner.report['cleanup_receipts'][-1]['page_status'],'closed')

    def test_lost_response_keeps_submitted_step_and_unknown_writer(self):
        runner = local_edits.DeleteUndoRunnerTests('runTest').make_runner([{'kind':'text','id':'b','text':'changed'}], fail_operation='text')
        with self.assertRaises(OSError):
            runner.run()
        self.assertEqual(len(runner.report['steps']),1)
        self.assertEqual(runner.report['steps'][0]['save_status'],'unknown')
        runner.close()
        self.assertEqual(runner.report['cleanup_receipts'][0]['requested_action'],'release')
        self.assertEqual(runner.report['released_tab'],'tab-1')

    def test_saved_protection_failure_preserves_save_fact_and_closes(self):
        runner = self.runner([{'kind':'text','id':'b','text':'changed'}])
        export, changed = runner.export, False
        editor = runner.editor
        def edit(op, expected=None):
            nonlocal changed
            result = editor(op, expected)
            if op['kind'] == 'text':
                changed = True
            return result
        def read():
            raw,name = export()
            if changed:
                local_edits.line(raw,'a')['locked'] = True
            return raw,name
        runner.editor,runner.export = edit,read
        with self.assertRaises(VerificationError):
            runner.run()
        step = runner.report['steps'][0]
        self.assertEqual((step['save_status'],step['failure_phase']),('confirmed','protection'))
        self.assertIn('after_raw',step)
        self.assertFalse(runner.uncertain)
        runner.close()
        self.assertEqual(runner.report['cleanup_receipts'][0]['requested_action'],'close')

    def test_close_timeout_records_own_identity_without_credentials(self):
        runner = self.runner([])
        runner.token,runner.task,runner.tab = 'secret-token','known-task','known-tab'
        runner.call = lambda *args,**kwargs: (_ for _ in ()).throw(TimeoutError('Close timeout'))
        runner.close()
        record = runner.report['cleanup_receipts'][0]
        self.assertEqual((record['task_id'],record['tab_id'],record['status']),('known-task','known-tab','unknown'))
        self.assertEqual(runner.report['page_status'],'unknown')
        self.assertNotIn('secret-token',json.dumps(runner.report))
        self.assertIsNone(runner.token)

    def test_completed_task_without_own_page_close_count_is_not_closed(self):
        runner = self.runner([])
        runner.token,runner.task,runner.tab = 'secret-token','known-task','known-tab'
        runner.call = lambda *args,**kwargs: dict(taskId='known-task',state='completed',keep=False,closed=0,released=0)
        runner.close()
        self.assertEqual(runner.report['page_status'],'unknown')
        self.assertEqual(runner.report['cleanup_receipts'][0]['status'],'unknown')

    def test_terminal_unknown_receipt_is_not_claimed_closed(self):
        runner = self.runner([])
        runner.token,runner.task,runner.tab = 'secret-token','known-task','known-tab'
        runner.call = lambda *args,**kwargs: dict(taskId='known-task',state='completed',keep=False,closed=0,released=0,unknownResult=True,retainedAsUserTabs=1)
        runner.close()
        self.assertEqual(runner.report['page_status'],'unknown')
        self.assertTrue(runner.report['cleanup_receipts'][0]['receipt']['unknownResult'])

    def test_completion_receipt_must_match_task_and_valid_close_counts(self):
        for change in (dict(taskId='different-task'),dict(closed=-1),dict(released=1)):
            with self.subTest(change=change):
                runner = self.runner([])
                runner.token,runner.task,runner.tab = 'secret-token','known-task','known-tab'
                receipt = dict(taskId='known-task',state='completed',keep=False,closed=1,released=0,**{})
                receipt.update(change)
                runner.call = lambda *args,**kwargs: receipt
                runner.close()
                self.assertEqual(runner.report['page_status'],'unknown')

    def test_stability_window_restarts_after_unsaved_without_extending_timeout(self):
        runner,clock = Runner.__new__(Runner),Clock()
        runner.timeout = 6
        runner.editor = lambda op: dict(nodes=[],seq=2,savedSeq=1 if clock.now==1 else 2)
        runner.export = lambda: ({'nodes':[]},'raw.json')
        with patch('whiteboard.time.monotonic',clock.monotonic),patch('whiteboard.time.sleep',clock.sleep):
            runner.settle([],minimum_stable_seconds=3)
        self.assertEqual(clock.now,5)
        runner.timeout,clock.now = 4,0
        with patch('whiteboard.time.monotonic',clock.monotonic),patch('whiteboard.time.sleep',clock.sleep),self.assertRaises(VerificationError):
            runner.settle([],minimum_stable_seconds=3)
        self.assertEqual(clock.now,4)

    def test_stability_window_restarts_after_not_ready(self):
        runner,clock = Runner.__new__(Runner),Clock()
        runner.timeout = 6
        runner.editor = lambda op: dict(nodes=[],seq=2,savedSeq=2)
        def export():
            if clock.now==1:
                raise NotReady('Transient raw read')
            return {'nodes':[]},'raw.json'
        runner.export = export
        with patch('whiteboard.time.monotonic',clock.monotonic),patch('whiteboard.time.sleep',clock.sleep):
            runner.settle([],minimum_stable_seconds=3)
        self.assertEqual(clock.now,5)

    def test_actual_attachment_cannot_be_replaced_by_unchanged_endpoint_copy(self):
        point = {'x':100,'y':40}
        state = {'nodes':[{'id':'line','kind':'connector','start_id':'a'}],
                 'line_endpoints':{'line':{'start':point}},
                 'binding_geometry':[{'id':'line','valid':True,'start':{'valid':True,'actual':point,'expected':{'x':120,'y':40}}}]}
        with self.assertRaisesRegex(VerificationError,'actual attachment'):
            Runner.verify_native_bindings(state,{'line'})
        state['binding_geometry'][0]['start']['expected'] = point
        Runner.verify_native_bindings(state,{'line'})

    def test_group_move_requires_every_member_world_displacement_and_size(self):
        nodes = [{'id':'g','kind':'group','children':['a','b']},{'id':'a','kind':'shape','parent_id':'g'},{'id':'b','kind':'shape','parent_id':'g'}]
        before = {'nodes':nodes,'world_geometry':{ident:dict(x=i*100,y=0,width=80,height=40,angle=0) for i,ident in enumerate(('a','b'))}}
        after = copy.deepcopy(before)
        for value in after['world_geometry'].values():
            value['x'] += 20
        Runner.verify_group_world(before,after,dict(kind='move',ids=['g'],dx=20,dy=0))
        after['world_geometry']['b']['width'] += 1
        with self.assertRaises(VerificationError):
            Runner.verify_group_world(before,after,dict(kind='move',ids=['g'],dx=20,dy=0))

    def test_invalid_last_step_never_opens_board_and_reports_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory)/'request.json'
            output = Path(directory)/'result'
            request.write_text(json.dumps(dict(document_url='https://tenant.feishu.cn/docx/abc',whiteboard_token='abc',operations=[dict(kind='text',id='a',text='new'),dict(kind='move',ids=['a'],dx=True,dy=0)])),encoding='utf-8')
            with patch('sys.argv',['whiteboard','--request',str(request),'--output-dir',str(output),'--proxy-url','http://127.0.0.1:3456']),patch.object(Runner,'open_page') as opened:
                self.assertEqual(main(),1)
                opened.assert_not_called()
            report = json.loads((output/'result.json').read_text(encoding='utf-8'))
            self.assertEqual((report['save_status'],report['verification_status'],report['failure_phase']),('not_written','failed','preflight'))

    def append_runner(self, directory, drift=None):
        runner = Runner.__new__(Runner)
        runner.request = dict(document_url='https://tenant.feishu.cn/docx/abc',whiteboard_token='abc',operations=[],capture_preview=True)
        runner.timeout,runner.output,runner.index = 3,Path(directory),0
        runner.report,runner.uncertain = dict(status='running',steps=[]),False
        runner.token=runner.task=runner.tab=None
        before = compile_diagram(dict(shapes=[dict(id='old',text='old',x=0,y=0,width=100,height=80)]))
        payload = compile_diagram(dict(shapes=[dict(id='a',text='start',x=200,y=0,width=100,height=80),dict(id='b',text='end',x=400,y=0,width=100,height=80)],connectors=[dict(id='c',start_id='a',end_id='b',label='signal')]))
        mapping = {'a':'server-a','b':'server-b','c':'server-c'}
        added = copy.deepcopy(payload['nodes'])
        for node in added:
            node['id'] = mapping[node['id']]
            if node['type']=='connector':
                for side in ('start','end'):
                    new_id = mapping[node['connector'][side+'_object']['id']]
                    node['connector'][side+'_object']['id'] = new_id
                    node['connector'][side]['attached_object']['id'] = new_id
        latest = {'nodes':copy.deepcopy(before['nodes'])+added}
        runner.mutations,runner.polls,runner.opens = [],0,0
        def export():
            runner.index += 1
            if runner.index==1:
                return copy.deepcopy(before),'before.json'
            runner.polls += 1
            if runner.polls==1:
                raise NotReady('Readback pending')
            return copy.deepcopy(latest),'after.json'
        def open_page():
            runner.opens += 1
            runner.token,runner.task,runner.tab = 'in-memory','task-'+str(runner.opens),'tab-'+str(runner.opens)
        def state(raw):
            nodes = projection(raw)
            result = dict(nodes=nodes,seq=2,savedSeq=2,
                          render_alpha={n['id']:dict(border=1,text=1) for n in nodes},line_endpoints={},binding_geometry=[])
            for raw_node in raw['nodes']:
                if raw_node['type']=='connector':
                    ident,c = raw_node['id'],raw_node['connector']
                    lookup = {n['id']:n for n in raw['nodes']}
                    ends = {}
                    for side in ('start','end'):
                        endpoint = c[side+'_object']
                        shape,p = lookup[endpoint['id']],endpoint['position']
                        ends[side] = dict(x=shape['x']+shape['width']*p['x'],y=shape['y']+shape['height']*p['y'])
                    result['line_endpoints'][ident] = ends
                    result['binding_geometry'].append(dict(id=ident,valid=True,**{side:dict(valid=True,actual=copy.deepcopy(ends[side]),expected=copy.deepcopy(ends[side])) for side in ('start','end')}))
            if runner.opens==2 and drift=='alpha':
                result['render_alpha']['server-a']['text'] = 0
            if runner.opens==2 and drift=='binding':
                result['binding_geometry'][0]['start']['expected']['x'] += 20
            return result
        runner.export,runner.open_page,runner.hydrate = export,open_page,state
        def command(args):
            runner.mutations.append(args)
            submitted = json.loads((Path(directory)/'append-input.json').read_text(encoding='utf-8'))
            lookup = {n['id']:n for n in latest['nodes']}
            for n in submitted['nodes']:
                lookup[mapping[n['id']]]['z_index'] = n['z_index']
            return dict(ok=True)
        runner.command = command
        runner.call = lambda path,data: dict(taskId=runner.task,state='completed',keep=data['keep'],closed=1 if not data['keep'] else 0,released=1 if data['keep'] else 0)
        runner.editor = lambda op,expected=None: state(latest)
        def unavailable_preview():
            raise VerificationError('Preview unavailable')
        runner.capture_preview = unavailable_preview
        filename = Path(directory)/'payload.json'
        filename.write_text(json.dumps(payload),encoding='utf-8')
        return runner,filename

    def test_append_submits_once_then_reopens_native_and_honors_preview(self):
        with tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
            runner,filename = self.append_runner(directory)
            runner.append(filename)
            # Two submission polls plus the full raw check after reopening.
            self.assertEqual((len(runner.mutations),runner.polls,runner.opens),(1,3,2))
            self.assertEqual(runner.report['status'],'verified')
            self.assertEqual(runner.report['steps'][0]['save_status'],'confirmed')
            self.assertEqual(runner.report['steps'][0]['verification_status'],'passed')
            self.assertEqual(runner.report['visual_status'],'unavailable')
            self.assertEqual(runner.report['id_mapping']['c'],'server-c')
            self.assertEqual(runner.report['append_layer_assignment'],{'a':2,'b':3,'c':4})
            self.assertEqual(json.loads((Path(directory)/'append-input.json').read_text())['nodes'][0]['z_index'],2)

    def test_append_native_failure_keeps_confirmed_save_without_repeating_append(self):
        for drift in ('alpha','binding'):
            with self.subTest(drift=drift),tempfile.TemporaryDirectory() as directory,patch('whiteboard.time.sleep'):
                runner,filename = self.append_runner(directory,drift)
                with self.assertRaises(VerificationError):
                    runner.append(filename)
                self.assertEqual(len(runner.mutations),1)
                step = runner.report['steps'][0]
                self.assertEqual((step['save_status'],step['verification_status'],step['failure_phase']),('confirmed','failed','reopen'))
                self.assertFalse(runner.uncertain)
                runner.close()
                self.assertEqual(runner.report['cleanup_receipts'][-1]['requested_action'],'close')


if __name__ == '__main__':
    unittest.main()
