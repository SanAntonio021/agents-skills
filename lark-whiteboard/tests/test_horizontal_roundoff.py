"""Exact native attachment evidence is required for zero-height rounding."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_nodes import compile_diagram
from whiteboard import check_raw_preservation, projection, VerificationError


def fixture(kind='text'):
    before = compile_diagram({'shapes':[
        dict(id='source',text='old',x=740,y=350,width=170,height=100),
        dict(id='end',text='keep',x=1000,y=330,width=180,height=380)],
        'connectors':[dict(id='line',start_id='source',end_id='end',
                           end_anchor={'side':'left','offset':.18421052396297455},label='old label')]})
    line=before['nodes'][-1]
    line.update(y=400,height=0)
    after=copy.deepcopy(before)
    after['nodes'][-1]['height']=2.4000000848900527e-6
    op=dict(kind=kind,id='source' if kind=='text' else 'line',text='new\nsecond')
    if kind=='text':after['nodes'][0]['text']['text']=op['text']
    else:after['nodes'][-1]['connector']['captions']['data'][0]['text']=op['text']
    native_before,native_after=projection(before),projection(after)
    for nodes in (native_before,native_after):
        n=next(n for n in nodes if n['id']=='line')
        n['end_anchor']['position']['y']=.18421052
    next(n for n in native_after if n['id']=='line').update(y=399.99999760000003,height=2.399999971203215e-6)
    ends_before={'start':{'x':910,'y':400},'end':{'x':1000,'y':400}}
    ends_after={'start':{'x':910,'y':400},'end':{'x':1000,'y':399.99999760000003}}
    expected=copy.deepcopy(ends_after)
    def bindings(ends):
        return [dict(id='line',valid=True,**{side:dict(valid=True,actual=copy.deepcopy(ends[side]),expected=copy.deepcopy(expected[side])) for side in ('start','end')})]
    evidence=dict(native_before=native_before,native_after=native_after,
                  native_endpoints_before={'line':ends_before},native_endpoints_after={'line':ends_after},
                  bindings_before=bindings(ends_before),bindings_after=bindings(ends_after))
    return before,after,op,evidence


class HorizontalAttachmentRoundoff(unittest.TestCase):
    def test_text_and_existing_caption_record_only_measured_exception(self):
        for kind in ('text','caption'):
            before,after,op,evidence=fixture(kind)
            exceptions=check_raw_preservation(before,after,op,group_evidence=evidence)
            self.assertEqual(len(exceptions),1)
            self.assertEqual(exceptions[0]['normalization'],'bound_text_horizontal_zero_height_roundoff')
            self.assertEqual(exceptions[0]['before_raw_height'],0)
            self.assertEqual(exceptions[0]['after_raw_height'],2.4000000848900527e-6)
            self.assertLess(exceptions[0]['maximum_native_endpoint_difference'],1e-5)

    def test_absent_and_incomplete_or_invalid_evidence_rejects(self):
        before,after,op,evidence=fixture()
        cases=[None,{}]
        for key in evidence:
            changed=copy.deepcopy(evidence);changed.pop(key);cases.append(changed)
        for key in ('bindings_before','bindings_after'):
            changed=copy.deepcopy(evidence);changed[key][0]['valid']=False;cases.append(changed)
            changed=copy.deepcopy(evidence);changed[key][0]['end']['valid']=False;cases.append(changed)
        changed=copy.deepcopy(evidence);changed['bindings_after'][0]['end']['actual']['y']+=.001;cases.append(changed)
        changed=copy.deepcopy(evidence);changed['bindings_after'][0]['end']['expected']['y']+=.001;cases.append(changed)
        changed=copy.deepcopy(evidence);changed['native_endpoints_after']['line']['end']['y']-=.001;cases.append(changed)
        changed=copy.deepcopy(evidence);next(n for n in changed['native_after'] if n['id']=='end')['width']+=1;cases.append(changed)
        changed=copy.deepcopy(evidence);next(n for n in changed['native_after'] if n['id']=='line')['points']=[dict(x=950,y=400)];cases.append(changed)
        changed=copy.deepcopy(evidence);next(n for n in changed['native_after'] if n['id']=='line')['end_id']='source';cases.append(changed)
        changed=copy.deepcopy(evidence);next(n for n in changed['native_before'] if n['id']=='line')['end_id']='';cases.append(changed)
        for changed in cases:
            with self.subTest(evidence=changed),self.assertRaises(VerificationError):
                check_raw_preservation(before,after,op,group_evidence=changed)

    def test_bigger_negative_nonzero_or_unrelated_raw_changes_reject(self):
        before,after,op,evidence=fixture()
        cases=[]
        for value in (-2.4e-6,1e-5,float('nan')):
            changed=copy.deepcopy(after);changed['nodes'][-1]['height']=value;cases.append((before,changed,op,evidence))
        changed=copy.deepcopy(before);changed['nodes'][-1]['height']=1e-7;cases.append((changed,after,op,evidence))
        for field,value in [('x',911),('angle',1),('width',91),('locked',True)]:
            changed=copy.deepcopy(after);changed['nodes'][-1][field]=value;cases.append((before,changed,op,evidence))
        changed=copy.deepcopy(after);changed['nodes'][1]['text']['text']='unrequested';cases.append((before,changed,op,evidence))
        changed=copy.deepcopy(before);changed['nodes'][-1]['connector']['shape']='curve';cases.append((changed,after,op,evidence))
        changed=copy.deepcopy(evidence);next(n for n in changed['native_before'] if n['id']=='line')['start_id']='other';cases.append((before,after,op,changed))
        for a,b,c,d in cases:
            with self.subTest(after=b),self.assertRaises(VerificationError):
                check_raw_preservation(a,b,c,group_evidence=d)


if __name__=='__main__':unittest.main()
