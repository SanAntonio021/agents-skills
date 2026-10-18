from pathlib import Path
ROOT=Path(r'D:/BaiduSyncdisk/.agents/skills/lark-whiteboard')
p=ROOT/'scripts/whiteboard.py'
s=p.read_text(encoding='utf-8')
old="        if kind == 'font' and not finite_number(op.get('font_size'), True):"
new="        if kind == 'text' and node.get('kind') == 'text' and op.get('text') == '':\n            raise VerificationError('Clearing an independent text shape is not verified and is refused before the native input call')\n"+old
assert s.count(old)==1
p.write_text(s.replace(old,new),encoding='utf-8')
p=ROOT/'scripts/editor.js';s=p.read_text(encoding='utf-8')
old="      const n=textNode(op.id);text(op.text);if(!['7e805832','d309a450'].includes(textSignature))fail('UNVERIFIED_TEXT_EDITOR_BUILD:'+textSignature);"
new="      const n=textNode(op.id);text(op.text);\n      if(n.type===3 && op.text==='')fail('INDEPENDENT_TEXT_CLEAR_NOT_VERIFIED');\n      if(!['7e805832','d309a450'].includes(textSignature))fail('UNVERIFIED_TEXT_EDITOR_BUILD:'+textSignature);"
assert s.count(old)==1;p.write_text(s.replace(old,new),encoding='utf-8')
p=ROOT/'tests/test_document_identity.py';s=p.read_text(encoding='utf-8')
old="    def test_saved_new_caption_only_accepts_observed_theme_default(self):"
new="""    def test_independent_text_clear_is_rejected_before_editor(self):
        from whiteboard import validate_local_operation
        node=dict(id='text',kind='text',text='existing',x=0,y=0,width=100,height=20)
        with self.assertRaisesRegex(VerificationError,'Clearing an independent'):
            validate_local_operation([node],dict(kind='text',id='text',text=''))
        validate_local_operation([node],dict(kind='text',id='text',text='new text'))
        validate_local_operation([dict(node,kind='shape')],dict(kind='text',id='text',text=''))

"""+old
assert s.count(old)==1;p.write_text(s.replace(old,new),encoding='utf-8')
p=ROOT/'tests/test_editor_guards.cjs';s=p.read_text(encoding='utf-8')
old="const textGuard=run({kind:'text',id:guardFree.id,text:'changed'});"
new="""const independentTextGuard=shape('independent-text-guard');independentTextGuard.type=3;
app.nodeManager.nodeMap.set(independentTextGuard.id,independentTextGuard);
const emptyTextGuard=run({kind:'text',id:independentTextGuard.id,text:''});
assert.match(emptyTextGuard.adapter_error,/INDEPENDENT_TEXT_CLEAR_NOT_VERIFIED/);
assert.equal(emptyTextGuard.content_write_started,false);assert.equal(contentCalls,0);
"""+old
assert s.count(old)==1;p.write_text(s.replace(old,new),encoding='utf-8')
print('Final source guards applied; frozen candidate is unchanged.')
