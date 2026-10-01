"""Visual edit postconditions and preservation boundaries (live tests are separate)."""
import copy
import sys
import unittest
import json
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from whiteboard import Runner, projection, check_scope, check_raw_preservation, VerificationError, validate_target
from native_nodes import compile_diagram

class VisualEditor(unittest.TestCase):
    def test_style_is_verified_and_opacity_preserved(self):
        a={'nodes':[{'id':'s','type':'composite_shape','style':{'border_color':'#000000','border_color_type':0,'border_opacity':70}}]}
        b=copy.deepcopy(a)
        b['nodes'][0]['style'].update(border_color='#ff8800',border_color_type=1)
        op={'kind':'style','id':'s','style':{'border_color':'#ff8800'}}
        check_scope(projection(a),projection(b),op)
        check_raw_preservation(a,b,op)
        b['nodes'][0]['style']['border_opacity']=100
        with self.assertRaises(VerificationError):check_raw_preservation(a,b,op)

    def test_anchors_preserve_binding_ids(self):
        e={'id':'s','snap_to':'right','position':{'x':1,'y':.5}}
        a={'nodes':[{'id':'c','type':'connector','connector':{'start_object':e,'start':{'attached_object':copy.deepcopy(e)}}}]}
        b=copy.deepcopy(a)
        anchor={'snap_to':'bottom','position':{'x':.4,'y':1}}
        b['nodes'][0]['connector']['start_object'].update(anchor)
        b['nodes'][0]['connector']['start']['attached_object'].update(anchor)
        op={'kind':'anchors','id':'c','start':anchor}
        check_scope(projection(a),projection(b),op)
        check_raw_preservation(a,b,op)
        b['nodes'][0]['connector']['start_object']['id']='other'
        with self.assertRaises(VerificationError):check_scope(projection(a),projection(b),op)
        with self.assertRaises(VerificationError):check_raw_preservation(a,b,op)

    def test_style_noop_fails(self):
        p=[{'id':'s','style':{'fill_color':'#ffffff'}}]
        with self.assertRaises(VerificationError):check_scope(p,p,{'kind':'style','id':'s','style':{'fill_color':'#000000'}})

    def test_block_target_rejects_selector_injection(self):
        with self.assertRaises(ValueError):validate_target({'document_url':'https://test.feishu.cn/docx/abc','whiteboard_token':'def','block_id':'x"] *'})

    def test_append_accepts_upward_noncentral_anchor_geometry(self):
        payload=compile_diagram({'shapes':[{'id':'a','text':'a','x':300,'y':300,'width':100,'height':80},{'id':'b','text':'b','x':50,'y':20,'width':100,'height':80}], 'connectors':[{'id':'c','start_id':'a','end_id':'b','start_anchor':{'side':'top','offset':.25},'end_anchor':{'side':'bottom','offset':.7},'shape':'right_angled_polyline'}]})
        runner=Runner.__new__(Runner)
        runner.request={'operations':[]}
        runner.export=lambda:({'nodes':[]},'before.json')
        def reached():raise RuntimeError('passed-validation')
        runner.open_page=reached
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'native.json';p.write_text(json.dumps(payload),encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'passed-validation'):runner.append(p)

if __name__=='__main__':unittest.main()
