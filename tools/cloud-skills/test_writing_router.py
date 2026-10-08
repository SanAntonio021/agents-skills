"""Offline router and private style-vocabulary integration, using synthetic data only."""
import json
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tempfile
import unittest
import build as adapter
from test_private_inputs import synthetic_vocab, SYNTHETIC_REPOSITORY

HERE=Path(__file__).resolve().parent
REV='f225f4dd7ede29f3d27b99e09d59f1b390541d66'

class RouterVocabTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.vocab=synthetic_vocab(self.root/'vocab')
        with (self.vocab/'中文/通用.md').open('a') as f:f.write('| 合成旧词 | 合成通用词 | 原文引用 |\n')
        with (self.vocab/'中文/申报书.md').open('a') as f:f.write('| 合成旧词 | 合成项目词 | 固定名称 |\n')
        self.inputs={'style_vocab':{'root':self.vocab,'manifest':{'schema_version':1,'contract':'style-vocab-v1','approved':True,'source_repository':SYNTHETIC_REPOSITORY,'source_path':'vocab','source_revision':'2'*40,'files_sha256':{n:adapter.sha((self.vocab/n).read_bytes()) for n in adapter.PRIVATE_VOCAB_FILES}}}}
    def generate(self,name):
        c=json.loads((HERE/(name+'.json')).read_text())
        return c,adapter.build((adapter.ROOT/c['source_path']).read_bytes(),c,REV,(HERE/'build.py').read_bytes(),private_inputs=self.inputs if name=='style-vocab' else None)
    def test_router_vocab_deterministic_and_all_relative_links_close(self):
        for name in ('writing-router','style-vocab'):
            c,out=self.generate(name);self.assertEqual(out,self.generate(name)[1])
            for p,b in out.items():
                if not p.endswith('.md') or '/cloud-source/' in p:continue
                for url in re.findall(r'\]\(([^)]+)\)',b.decode()):
                    if re.match(r'[a-z]+:',url):continue
                    q,_,frag=url.partition('#');dest=posixpath.normpath(posixpath.join(posixpath.dirname(p),q)) if q else p
                    self.assertIn(dest,out,(name,p,url))
                    if frag:
                        heads=re.findall(r'^#{1,6} (.+)$',out[dest].decode(),re.M)
                        self.assertIn(frag,[re.sub(r'[^\w\-\s]','',h.lower()).replace(' ','-') for h in heads])
    def test_source_exactly_reversible(self):
        for name in ('writing-router','style-vocab'):
            c,out=self.generate(name)
            for item in c['files']:
                source=(adapter.ROOT/item['source']).read_text();staged=source;ops=[]
                for r in item.get('replacements',[]):
                    positions=[m.start() for m in re.finditer(re.escape(r['before']),staged)]
                    self.assertEqual(len(positions),r['count']);delta=len(r['after'])-len(r['before'])
                    ops.append(([p+i*delta for i,p in enumerate(positions)],r));staged=staged.replace(r['before'],r['after'])
                actual=out[item['target']].decode()
                if item['target']=='SKILL.md':actual=actual.removesuffix(c['append_body'])
                self.assertEqual(actual,staged)
                for positions,r in reversed(ops):
                    for p in reversed(positions):actual=actual[:p]+r['before']+actual[p+len(r['after']):]
                self.assertEqual(actual,source)
    def test_sample_gate_and_missing_resources_are_honest(self):
        for name in ('writing-router','style-vocab'):
            c,out=self.generate(name);common=out['references/writing-common/common-quality.md'].decode()
            self.assertIn('入口和对应文体样稿都标为 `approved`',common)
            self.assertIn('不自动视为认可其文风',common)
            self.assertIn('没有获批样稿时照常执行文体规则',common)
            self.assertFalse(any('writing-samples/' in p for p in out))
        self.assertIn('不能报告 clean',self.generate('style-vocab')[1]['SKILL.md'].decode())
    def test_generated_audit_all_fourteen_routes_and_exclusions(self):
        _,out=self.generate('style-vocab');script=self.root/'audit.py';script.write_bytes(out['scripts/audit_writing_memory.py'])
        draft=self.root/'draft.md';draft.write_text('合成旧词 SYNTHETICOBSOLETE\n')
        for lang in ('zh','en'):
            for kind in ('general','proposal','research-report','paper','review-response','letter','other'):
                result=subprocess.run([sys.executable,str(script),'--file',str(draft),'--vocab-root',str(self.vocab),'--language',lang,'--document-kind',kind,'--output-format','json'],capture_output=True,text=True)
                self.assertEqual(result.returncode,1,result.stderr);j=json.loads(result.stdout);self.assertEqual(j['status'],'review_required')
                if lang=='zh':self.assertEqual(j['matches'][0]['suggestion'],'合成项目词' if kind=='proposal' else '合成通用词')
        draft.write_text('`syntheticobsolete`\n\nhttps://example.invalid/syntheticobsolete\n\n```text\nsyntheticobsolete\n```\n')
        args=[sys.executable,str(script),'--file',str(draft),'--language','en','--document-kind','paper','--output-format','json']
        result=subprocess.run(args+['--vocab-root',str(self.vocab)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'],'clean')
        self.assertEqual(subprocess.run(args,capture_output=True).returncode,2)
    def test_public_configs_contain_no_synthetic_private_data(self):
        for name in ('writing-router','style-vocab'):
            c,out=self.generate(name)
            self.assertNotIn(SYNTHETIC_REPOSITORY,json.dumps(c))
            self.assertNotIn('合成旧词',json.dumps(c,ensure_ascii=False))
            for p,b in out.items():
                if p!=adapter.MANIFEST and not p.startswith(adapter.PRIVATE_VOCAB_PREFIX):
                    self.assertNotIn(b'synthetic-fixtures/private-vocabulary',b)

if __name__=='__main__':unittest.main()
