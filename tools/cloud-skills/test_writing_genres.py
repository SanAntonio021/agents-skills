"""Offline source-retention and runtime-boundary tests for four writing genres."""
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import sys
import types
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('genre_cloud_adapter', HERE / 'build.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
REV = 'f225f4dd7ede29f3d27b99e09d59f1b390541d66'
NAMES = ('technical-writing', 'project-writing', 'research-report', 'meeting-notes')


def configs():
    return [json.loads((HERE / (name + '.json')).read_text()) for name in NAMES]


def generate(config):
    return adapter.build((adapter.ROOT / config['source_path']).read_bytes(),
                         config, REV, (HERE / 'build.py').read_bytes())


class GenreCloudTests(unittest.TestCase):
    def test_four_genres_deterministic_and_pinned(self):
        for config in configs():
            with self.subTest(skill=config['skill']):
                first = generate(config)
                self.assertEqual(first, generate(config))
                manifest = json.loads(first[adapter.MANIFEST])
                self.assertEqual(manifest['source_revision'], REV)
                for path, digest in manifest['source_files_sha256'].items():
                    self.assertEqual(adapter.sha((adapter.ROOT / path).read_bytes()), digest)
                for path, digest in manifest['generated_sha256'].items():
                    self.assertEqual(adapter.sha(first[path]), digest)

    def test_exact_source_and_reversible_transformations(self):
        for config in configs():
            output = generate(config)
            self.assertEqual(output['references/cloud-source/original-skill.md'],
                             (adapter.ROOT / config['source_path']).read_bytes())
            for item in config['files']:
                with self.subTest(skill=config['skill'], target=item['target']):
                    source = (adapter.ROOT / item['source']).read_text()
                    if item.get('select'):
                        source = ''.join(
                            source[source.index(s['start']):
                                   source.index(s['end'], source.index(s['start']) + len(s['start']))
                                   if s['end'] else len(source)]
                            for s in item['select'])
                        self.assertEqual(adapter.sha(source.encode()), item['selected_sha256'])
                    staged, operations = source, []
                    for replacement in item.get('replacements', []):
                        self.assertIn('count', replacement)
                        self.assertEqual(staged.count(replacement['before']), replacement['count'])
                        positions = [m.start() for m in re.finditer(
                            re.escape(replacement['before']), staged)]
                        delta = len(replacement['after']) - len(replacement['before'])
                        operations.append(([p + i * delta for i, p in enumerate(positions)], replacement))
                        staged = staged.replace(replacement['before'], replacement['after'])
                    actual = output[item['target']].decode()
                    if item['target'] == 'SKILL.md':
                        actual = actual.removesuffix(config['append_body'])
                    self.assertEqual(actual, staged)
                    for positions, replacement in reversed(operations):
                        for position in reversed(positions):
                            self.assertEqual(actual[position:position + len(replacement['after'])],
                                             replacement['after'])
                            actual = (actual[:position] + replacement['before'] +
                                      actual[position + len(replacement['after']):])
                    self.assertEqual(actual, source)

    def test_all_runtime_relative_links_and_fragments_resolve(self):
        for config in configs():
            output = generate(config)
            for name, data in output.items():
                if not name.endswith('.md') or '/cloud-source/' in name:
                    continue
                for url in re.findall(r'\]\(([^)]+)\)', data.decode()):
                    if re.match(r'[a-z]+:', url):
                        continue
                    path, _, fragment = url.partition('#')
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
                    self.assertIn(target, output, (config['skill'], name, url))
                    if fragment:
                        headings = re.findall(r'^#{1,6} (.+)$', output[target].decode(), re.M)
                        slugs = [re.sub(r'[^\w\-\s]', '', h.lower()).replace(' ', '-') for h in headings]
                        self.assertIn(fragment, slugs, (config['skill'], name, url))

    def test_genre_core_and_runtime_boundaries(self):
        for config in configs():
            output = generate(config)
            main = output['SKILL.md'].decode()
            for line in (adapter.ROOT / config['source_path']).read_text().splitlines():
                if line.startswith('## ') and line not in ('## 入口',):
                    self.assertIn(line, main)
            self.assertIn('未执行个人词表审计', main)
            self.assertIn('不代表当前环境已验证', main)
            self.assertIn('Permission is hereby granted',
                          output['references/writing-common/LICENSE'].decode())
            for path, data in output.items():
                if not path.endswith('.md') or '/cloud-source/' in path:
                    continue
                self.assertNotIn('D:\\BaiduSyncdisk', data.decode(), path)
                self.assertNotIn('--allow-office-com', data.decode(), path)
                self.assertNotIn('../../docx/', data.decode(), path)

    def test_lab_fragment_is_the_actual_source_section(self):
        config = next(c for c in configs() if c['skill'] == 'technical-writing')
        output = generate(config)
        selected = output['references/lab-step-order.md'].decode()
        self.assertTrue(selected.startswith('## 开始与写入\n'))
        self.assertIn('按实际执行顺序放回原位置', selected)
        self.assertNotIn('4. ', selected)
        self.assertNotIn('link-test', selected)
        self.assertNotIn('#逐步准备实验', output['SKILL.md'].decode())
        self.assertIn('Permission is hereby granted',
                      output['references/engineering-validation-source.md'].decode())

    def test_original_audit_script_retained_and_modes_still_differ(self):
        config = next(c for c in configs() if c['skill'] == 'research-report')
        data = generate(config)['scripts/audit_report.py']
        self.assertEqual(data, (adapter.ROOT / 'research-report/scripts/audit_report.py').read_bytes())
        module = types.ModuleType('genre_generated_report_audit')
        sys.modules[module.__name__] = module
        try:
            exec(compile(data, 'generated_audit_report.py', 'exec'), module.__dict__)
            text = '# 方案选择\n\n## 建议\n\n建议优先验证候选方案。\n'
            evidence = module.audit_text(text, document_role='evidence-report')
            decision = module.audit_text(text, document_role='decision-report')
            self.assertIn('ACTION_DIRECTIVE', {f['code'] for f in evidence['findings']})
            self.assertNotIn('ACTION_DIRECTIVE', {f['code'] for f in decision['findings']})
            citation = module.audit_text('## 结果\n\n2026 年公布两项结果。[3]\n')
            self.assertIn('UNRESOLVED_NUMERIC_CITATION', {f['code'] for f in citation['findings']})
        finally:
            sys.modules.pop(module.__name__, None)


if __name__ == '__main__':
    unittest.main()
