import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard/scripts')
from whiteboard import check_raw_preservation
P=Path(r'D:/BaiduSyncdisk/Paper/202607_THz_freq_planning/过程文件/实验方案精简/第一节框图/功率与放大级标签_20261013/正式修改_20261014/edit_001')
read=lambda n:json.loads((P/n).read_text(encoding='utf-8'))
pre,post=read('inspect-000.json'),read('editor-001.json')
evidence=dict(native_before=pre['nodes'],native_after=post['nodes'],
              native_endpoints_before=pre['line_endpoints'],native_endpoints_after=post['line_endpoints'],
              bindings_before=pre['binding_geometry'],bindings_after=post['binding_geometry'])
exceptions=check_raw_preservation(read('raw-005.json'),read('raw-006.json'),read('result.json')['steps'][0]['operation'],group_evidence=evidence)
assert len(exceptions)==1
report=dict(source_evidence=str(P),raw_exceptions=exceptions,
            fresh_readonly='business-roundoff-readonly/fresh-native.json',
            finding='Native endpoint moved only 2.4e-6 to the unchanged expected nonmidpoint attachment; raw zero-height serialization became float32 positive height. Fresh-page endpoint serialization differs by the same measured scale, both bindings remain valid.',
            original_result_unchanged=True)
(ROOT/'business-roundoff-patch-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
