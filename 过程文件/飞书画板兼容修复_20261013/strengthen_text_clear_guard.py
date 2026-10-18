from pathlib import Path
ROOT=Path(r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard')
p=ROOT/'scripts/editor.js';s=p.read_text(encoding='utf-8')
old="      if(n.type===3 && op.text==='')fail('INDEPENDENT_TEXT_CLEAR_NOT_VERIFIED');\n"
assert s.count(old)==1;s=s.replace(old,'')
old='  ids.forEach(node);\n'
assert s.count(old)==1;s=s.replace(old,old+"  if(op.kind==='text' && node(op.id).type===3 && op.text==='')fail('INDEPENDENT_TEXT_CLEAR_NOT_VERIFIED');\n")
p.write_text(s,encoding='utf-8')
p=ROOT/'tests/test_editor_guards.cjs';s=p.read_text(encoding='utf-8')
old="const emptyTextGuard=run({kind:'text',id:independentTextGuard.id,text:''});"
new="""independentTextGuard.parent=group;
const selectedBeforeEmpty=[...selected];
"""+old
assert s.count(old)==1;s=s.replace(old,new)
old='assert.equal(emptyTextGuard.content_write_started,false);assert.equal(contentCalls,0);'
new=old+'\nassert.deepEqual(selected,selectedBeforeEmpty);\nindependentTextGuard.parent=undefined;'
assert s.count(old)==1;s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
