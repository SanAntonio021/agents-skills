import importlib.util
import json
from pathlib import Path
import posixpath
import re
import tempfile
import unittest
import yaml

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('batch_adapter', HERE / 'build.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
REV = 'd7fd64fd52406ad38eada3975adb33889979e4af'


def generate(config):
    return adapter.build((adapter.ROOT / config['source_path']).read_bytes(), config,
                         REV, (HERE / 'build.py').read_bytes())


class BatchTests(unittest.TestCase):
    def configs(self):
        return [json.loads(p.read_text()) for p in sorted(HERE.glob('*.json'))]

    def test_all_configs_deterministic(self):
        self.assertEqual(len(self.configs()), 7)
        for c in self.configs():
            self.assertEqual(generate(c), generate(c))

    def test_exact_source_preserved(self):
        for c in self.configs():
            out = generate(c)
            self.assertEqual(out['references/cloud-source/original-skill.md'],
                             (adapter.ROOT / c['source_path']).read_bytes())
            if c['schema_version'] != 2:
                continue
            for item in c['files']:
                actual = out[item['target']].decode()
                if item['target'] == 'SKILL.md':
                    actual = actual.removesuffix(c['append_body'])
                source = (adapter.ROOT / item['source']).read_text()
                if item.get('select'):
                    source = ''.join(source[source.index(s['start']):source.index(s['end'], source.index(s['start']) + len(s['start'])) if s['end'] else len(source)] for s in item['select'])
                staged, operations = source, []
                for r in item.get('replacements', []):
                    positions = [m.start() for m in re.finditer(re.escape(r['before']), staged)]
                    delta = len(r['after']) - len(r['before'])
                    operations.append(([v+i*delta for i,v in enumerate(positions)],r))
                    staged = staged.replace(r['before'],r['after'])
                self.assertEqual(actual, staged)
                for positions,r in reversed(operations):
                    for pos in reversed(positions):
                        self.assertEqual(actual[pos:pos+len(r['after'])],r['after'])
                        actual=actual[:pos]+r['before']+actual[pos+len(r['after']):]
                self.assertEqual(actual, source, item['source'])

    def test_all_generated_hashes_and_provenance(self):
        for c in self.configs():
            out = generate(c)
            m = json.loads(out[adapter.MANIFEST])
            self.assertIsNone(m['materialized_sha256'])
            for name, digest in m['generated_sha256'].items():
                self.assertEqual(adapter.sha(out[name]), digest)
            for src, digest in m['source_files_sha256'].items():
                self.assertEqual(adapter.sha((adapter.ROOT/src).read_bytes()), digest)

    def test_runtime_links_resolve(self):
        for c in self.configs():
            out = generate(c)
            for name, data in out.items():
                if not name.endswith('.md') or '/cloud-source/' in name or name.endswith('upstream-sources.md'):
                    continue  # Historical provenance links are not runtime routing.
                for url in re.findall(r'\]\(([^)]+)\)', data.decode()):
                    path = url.split('#')[0]
                    if not path or re.match(r'[a-z]+:', path):
                        continue
                    dest = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
                    self.assertIn(dest, out, (c.get('skill'), name, url))

    def test_humanizer_entire_catalog(self):
        c = json.loads((HERE/'humanizer.json').read_text())
        s = (adapter.ROOT/c['source_path']).read_text()
        result = generate(c)['SKILL.md'].decode()
        catalog = s[s.index('## CONTENT PATTERNS'):]
        self.assertIn(catalog, result)
        self.assertEqual(len(re.findall(r'^### \d+\.', s, re.M)), 33)

    def test_reference_core_retained(self):
        c = json.loads((HERE/'paper-review.json').read_text())
        out = generate(c)
        source = (adapter.ROOT/'paper-review/references/source-check.md').read_text()
        for line in source.splitlines():
            if line.startswith('- ') and not line.startswith(('- 先定位原文', '- 原文缺失')):
                self.assertIn(line, out['references/source-check.md'].decode())
        for text in ('A 类', 'B 类', 'C 类', 'source_check'):
            self.assertIn(text, out['SKILL.md'].decode())
        self.assertIn('## 术语选择', out['references/sci-terminology-bank.md'].decode())
        self.assertIn(b'Permission is hereby granted',out['references/engineering-validation-source.md'])

    def test_no_runtime_private_paths_or_broken_cdp(self):
        for c in self.configs():
            out = generate(c)
            for name, data in out.items():
                if name.endswith('.md') and '/cloud-source/' not in name and not name.endswith('upstream-sources.md'):
                    self.assertNotIn('D:\\BaiduSyncdisk', data.decode(),name)
                    self.assertNotIn('](references/cdp-api.md', data.decode(),name)

    def test_source_and_section_drift(self):
        c = json.loads((HERE/'paper-search.json').read_text())
        c['files'][1]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'source hash changed'):
            generate(c)
        c = json.loads((HERE/'paper-search.json').read_text())
        next(x for x in c['files'] if x.get('select'))['selected_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'selected source hash changed'):
            generate(c)

    def test_paths_reject_escape(self):
        for p in ('../x','/tmp/x','x/../y','x\\y','./x',''):
            with self.assertRaises(ValueError): adapter.safe_path(p)

    def fixture(self, path):
        c = json.loads((HERE/'handoff.json').read_text())
        out = generate(c)
        for n,b in out.items():
            p=path/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        host=yaml.safe_load(out['agents/openai.yaml'])
        host['interface']['icon_small']='assets/icon.svg'
        host['interface']['icon_large']='assets/icon.svg'
        host['policy']['products']=['chatgpt','codex','api','atlas']
        (path/'assets').mkdir();(path/'assets/icon.svg').write_text('<svg/>')
        (path/'agents/openai.yaml').write_text(yaml.safe_dump(host,sort_keys=False,allow_unicode=True))
        return out

    def test_host_normalization_and_repeat_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);out=self.fixture(target)
            state=adapter.snapshot(target)
            manifest=adapter.verify_materialized(target,out,state)
            self.assertNotEqual(json.loads(manifest)['generated_sha256']['agents/openai.yaml'],json.loads(manifest)['materialized_sha256']['agents/openai.yaml'])
            (target/adapter.MANIFEST).write_bytes(manifest)
            self.assertEqual(adapter.plan(target,out,adapter.snapshot(target))[1],[])
            with self.assertRaisesRegex(ValueError,'explicit review'):
                adapter.plan(target,out,state)

    def test_materialized_drift_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);out=self.fixture(target)
            (target/adapter.MANIFEST).write_bytes(adapter.verify_materialized(target,out,adapter.snapshot(target)))
            (target/'SKILL.md').write_text('unauthorized edit')
            with self.assertRaisesRegex(ValueError,'materialized target drift'):
                adapter.plan(target,out,adapter.snapshot(target))

    def test_unknown_extra_file_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);out=self.fixture(target);(target/'extra.txt').write_text('unknown')
            with self.assertRaisesRegex(ValueError,'unexpected materialized files'):
                adapter.verify_materialized(target,out,adapter.snapshot(target))

    def test_host_managed_semantic_change_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);out=self.fixture(target)
            p=target/'agents/openai.yaml';h=yaml.safe_load(p.read_text());h['policy']['allow_implicit_invocation']=False;p.write_text(yaml.safe_dump(h))
            with self.assertRaisesRegex(ValueError,'managed value'):
                adapter.verify_materialized(target,out,adapter.snapshot(target))

    def test_unknown_host_key_or_product_rejected(self):
        for section,key,value in [('interface','surprise','value'),('policy','products',['unknown-product'])]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as temp:
                target=Path(temp);out=self.fixture(target);p=target/'agents/openai.yaml';h=yaml.safe_load(p.read_text());h[section][key]=value;p.write_text(yaml.safe_dump(h))
                with self.assertRaises(ValueError):adapter.verify_materialized(target,out,adapter.snapshot(target))


    def test_unmanaged_drift_without_output_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);(target/'managed.txt').write_bytes(b'fixed')
            old=adapter.snapshot(target);(target/'unknown.txt').write_text('extra')
            with self.assertRaisesRegex(ValueError,'target drift'):
                adapter.plan(target,{'managed.txt':b'fixed'},old)

    def test_host_icon_changes_require_review_but_not_redeployment(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);out=self.fixture(target)
            (target/adapter.MANIFEST).write_bytes(adapter.verify_materialized(target,out,adapter.snapshot(target)))
            before=adapter.snapshot(target)
            (target/'assets/icon.svg').write_text('<svg><!-- regenerated host icon --></svg>')
            with self.assertRaisesRegex(ValueError,'explicit review'):
                adapter.plan(target,out,before)
            self.assertEqual(adapter.plan(target,out,adapter.snapshot(target))[1],[])
            self.assertNotIn('assets/icon.svg',json.loads((target/adapter.MANIFEST).read_bytes())['materialized_sha256'])

    def test_identity_comes_only_from_frontmatter(self):
        self.assertEqual(adapter.skill_name(b'---\nname: other\ndescription: Test\n---\nname: handoff\n'),'other')
        for content in (b'---\ndescription: Test\n---\nname: handoff\n',b'---\nname: other\nname: handoff\n---\n',b'---\nname: other\n"name": handoff\n---\n'):
            with self.assertRaises(ValueError):adapter.skill_name(content)

    def test_mutable_manifest_does_not_hide_source_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);out=self.fixture(target)
            m=json.loads(adapter.verify_materialized(target,out,adapter.snapshot(target)))
            (target/'SKILL.md').write_text('edited body')
            m['materialized_sha256']={p:h for p,h in adapter.files_snapshot(target,exclude_manifest=True).items() if p in m['generated_sha256']}
            (target/adapter.MANIFEST).write_bytes(adapter.json_bytes(m))
            with self.assertRaisesRegex(ValueError,'generated bytes differ'):
                adapter.plan(target,out,adapter.snapshot(target))

    def test_duplicate_yaml_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp);out=self.fixture(target);p=target/'agents/openai.yaml'
            p.write_text(p.read_text().replace('policy:\n','policy:\n  allow_implicit_invocation: false\n'))
            with self.assertRaisesRegex(ValueError,'duplicate host YAML key'):
                adapter.verify_materialized(target,out,adapter.snapshot(target))


if __name__ == '__main__': unittest.main()
