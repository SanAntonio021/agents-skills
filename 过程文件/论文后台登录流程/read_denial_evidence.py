"""Read only policy-denial fragments from this chat's tool results."""
import json
import re
from pathlib import Path
path=Path(r'C:\Users\SanAn\.codex\sessions\2026\09\30\rollout-2026-09-30T16-05-04-01a0f158-7fa1-7583-876e-932aecf37ef6.jsonl')
for line in path.open(encoding='utf-8'):
 try:
  obj=json.loads(line);p=obj.get('payload',{})
  if obj.get('type')!='response_item' or p.get('type') not in ['function_call_output','custom_tool_call_output']:continue
  out=p.get('output','')
  if not isinstance(out,str):continue
  for match in re.finditer(r'.{0,30}(?:blocked by policy|could not determine the current browser URL).{0,160}',out,re.I):
   print(json.dumps({'timestamp':obj.get('timestamp'),'denial_fragment':match.group()},ensure_ascii=False))
 except (ValueError,TypeError):continue
