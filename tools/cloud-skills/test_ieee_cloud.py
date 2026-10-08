"""Offline contracts for the deterministic IEEE manuscript cloud adaptation."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('ieee_cloud_adapter', HERE / 'build.py')
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)
REVISION = 'f225f4dd7ede29f3d27b99e09d59f1b390541d66'


def generate():
    config = json.loads((HERE / 'ieee-manuscript-edit.json').read_text())
    outputs = adapter.build((adapter.ROOT / config['source_path']).read_bytes(), config,
                            REVISION, (HERE / 'build.py').read_bytes())
    return config, outputs


class IeeeCloudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config, cls.outputs = generate()

    def test_build_and_manifest_are_deterministic(self):
        self.assertEqual(self.outputs, generate()[1])
        manifest = json.loads(self.outputs[adapter.MANIFEST])
        self.assertEqual(manifest['source_revision'], REVISION)
        self.assertIsNone(manifest['materialized_sha256'])
        for path, digest in manifest['generated_sha256'].items():
            self.assertEqual(adapter.sha(self.outputs[path]), digest)
        self.assertEqual(self.outputs['references/cloud-source/original-skill.md'],
                         (adapter.ROOT / self.config['source_path']).read_bytes())

    def test_every_counted_transform_can_be_reversed_exactly(self):
        for item in self.config['files']:
            source = (adapter.ROOT / item['source']).read_text()
            self.assertEqual(adapter.sha((adapter.ROOT / item['source']).read_bytes()), item['sha256'])
            staged, operations = source, []
            for change in item.get('replacements', []):
                self.assertIn('count', change, (item['source'], change['id']))
                positions = [m.start() for m in re.finditer(re.escape(change['before']), staged)]
                self.assertEqual(len(positions), change['count'])
                delta = len(change['after']) - len(change['before'])
                operations.append(([p + i * delta for i, p in enumerate(positions)], change))
                staged = staged.replace(change['before'], change['after'])
            actual = self.outputs[item['target']].decode()
            if item['target'] == 'SKILL.md':
                actual = actual.removesuffix(self.config['append_body'])
            self.assertEqual(actual, staged)
            for positions, change in reversed(operations):
                for position in reversed(positions):
                    self.assertEqual(actual[position:position + len(change['after'])], change['after'])
                    actual = actual[:position] + change['before'] + actual[position + len(change['after']):]
            self.assertEqual(actual, source, item['source'])

    def test_runtime_links_are_closed(self):
        for name, data in self.outputs.items():
            if not name.endswith('.md') or '/cloud-source/' in name:
                continue
            for url in re.findall(r'\]\(([^)]+)\)', data.decode()):
                path = url.split('#')[0]
                if not path or re.match(r'[a-z]+:', path):
                    continue
                destination = posixpath.normpath(posixpath.join(posixpath.dirname(name), path))
                self.assertIn(destination, self.outputs, (name, url))

    def test_runtime_has_no_private_machine_paths_or_external_tooling(self):
        for name, data in self.outputs.items():
            if name.endswith(('.md', '.py')) and '/cloud-source/' not in name:
                self.assertNotIn('D:\\BaiduSyncdisk', data.decode(), name)
        self.assertNotIn('scripts/run_draft_refine.py', self.outputs)
        for name in ('audit_manuscript_conventions.py', 'audit_writing_memory.py'):
            source = self.outputs['scripts/' + name].decode()
            self.assertNotIn('parents[4]', source)
            self.assertNotIn('tooling.', source)
            modules = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    modules.update(x.name.split('.')[0] for x in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.add(node.module.split('.')[0])
            self.assertTrue(modules <= sys.stdlib_module_names, modules - sys.stdlib_module_names)

    def test_language_and_evidence_boundaries_remain(self):
        text = self.outputs['SKILL.md'].decode()
        source = (adapter.ROOT / self.config['source_path']).read_text()
        for start, end in (('## 中文主稿与英文同步', '## 共同红线'),
                           ('## 共同红线', '## 流程'),
                           ('## `audit_only`', '## 输出'),
                           ('## 完成条件', None)):
            piece = source[source.index(start):source.index(end, source.index(start)) if end else len(source)]
            self.assertIn(piece, text)
        for value in ('zh_paper', 'en_paper', 'final_audit', 'audit_only',
                      'documents', 'orbit:docs-artifact', 'Presentations',
                      'Spreadsheets', '未完成'):
            self.assertIn(value, text)
        self.assertEqual(self.outputs['scripts/audit_manuscript_conventions.py'],
                         (adapter.ROOT / 'ieee-manuscript-edit/scripts/audit_manuscript_conventions.py').read_bytes())

    def test_all_exact_template_dependencies_are_explicitly_unavailable(self):
        cache = self.outputs['references/ieee-official-template-cache.md'].decode()
        required = (
            'transactions-journals-letters/word-extracted/ieee-transactions-template.docx',
            'transactions-journals-letters/latex-extracted/bare_jrnl_new_sample4.tex',
            'transactions-journals-letters/latex-extracted/IEEEtran.cls',
            'ieee-access/Access_Word_Template.docx',
            'ieee-access/latex-extracted/ACCESS_latex_template_20240429/access.tex',
            'ieee-access/latex-extracted/ACCESS_latex_template_20240429/ieeeaccess.cls',
            'ieee-journal-of-microwaves/JMW_Word_Template.docx',
            'ieee-journal-of-microwaves/latex-extracted/IEEE_JMW_LaTex_Template_Oct18_2021/JMW_template.tex',
            'ieee-journal-of-microwaves/latex-extracted/IEEE_JMW_LaTex_Template_Oct18_2021/IEEEjmw.cls',
        )
        self.assertIn('均未捆绑、未安装', cache)
        for path in required:
            self.assertIn(path, cache)
            self.assertNotIn('assets/ieee-official-templates/' + path, self.outputs)
        self.assertFalse(any(name.startswith('assets/ieee-official-templates/') for name in self.outputs))
        self.assertIn('保持未完成', cache)
        self.assertIn('https://template-selector.ieee.org/', cache)

    def test_licenses_and_attribution_are_present(self):
        self.assertIn(b'Permission is hereby granted', self.outputs['references/writing-common/LICENSE'])
        self.assertIn(b'Permission is hereby granted', self.outputs['references/engineering-validation-source.md'])
        attribution = self.outputs['references/sainani-sentence-review.md'].decode()
        for value in ('Lorena A. Barba', '8a57fa73d541bdcf7d8501db61c018cb454e9afa',
                      'Wang Weipeng', 'https://creativecommons.org/licenses/by/4.0/'):
            self.assertIn(value, attribution)

    def run_script(self, directory, script, arguments):
        script_path = directory / script
        script_path.write_bytes(self.outputs['scripts/' + script])
        return subprocess.run([sys.executable, '-B', str(script_path)] + arguments,
                              capture_output=True, text=True, check=False)

    def test_convention_audit_cli_is_read_only_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paper = root / 'paper.md'
            content = '# Results\n\nIt can be seen that RF remains undefined.\n\nFig. 1. RF result.\n'
            paper.write_text(content)
            args = ['--input', str(paper), '--format', 'json']
            first = self.run_script(root, 'audit_manuscript_conventions.py', args)
            second = self.run_script(root, 'audit_manuscript_conventions.py', args)
            self.assertEqual(first.returncode, 1, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(paper.read_text(), content)
            report = json.loads(first.stdout)
            self.assertEqual(report['input']['sha256'], hashlib.sha256(paper.read_bytes()).hexdigest())
            for category in ('review_candidates', 'protected_qualifiers', 'unresolved'):
                for finding in report[category]:
                    self.assertNotIn('span', finding)
                    self.assertNotIn('replacement', finding)
            clean = root / 'clean.md'
            clean.write_text('The measured link remained stable throughout the experiment.\n')
            result = self.run_script(root, 'audit_manuscript_conventions.py', ['--input', str(clean), '--format', 'json'])
            self.assertEqual(result.returncode, 0, result.stdout)
            bad = root / 'bad.md'
            bad.write_bytes(b'\xff')
            result = self.run_script(root, 'audit_manuscript_conventions.py', ['--input', str(bad), '--format', 'json'])
            self.assertEqual(result.returncode, 2)

    def test_style_audit_requires_explicit_available_vocabulary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paper = root / 'paper.md'
            paper.write_text('The robust link leverages prior work.\n')
            args = ['--file', str(paper), '--language', 'en', '--document-kind', 'paper']
            missing = self.run_script(root, 'audit_writing_memory.py', args)
            self.assertEqual(missing.returncode, 2)
            self.assertIn('--vocab-root', json.loads(missing.stdout)['errors'][0]['message'])
            missing = self.run_script(root, 'audit_writing_memory.py', args + ['--vocab-root', str(root / 'absent')])
            self.assertEqual(missing.returncode, 2)
            self.assertEqual(json.loads(missing.stdout)['status'], 'error')
            self.assertFalse((root / 'absent').exists())
            vocab = root / 'vocab'
            (vocab / '英文').mkdir(parents=True)
            header = '| 不建议 | 建议 | 例外 |\n|---|---|---|\n'
            (vocab / '英文/通用.md').write_text(header + '| leverage | use | finance |\n| robust | reliable | statistics |\n')
            (vocab / '英文/论文.md').write_text(header + '| robust | stable | robust control |\n')
            (vocab / '维护.md').write_text('## 检查补充\n\n| 条目 | 匹配 |\n|---|---|\n')
            before = paper.read_bytes()
            review = self.run_script(root, 'audit_writing_memory.py', args + ['--vocab-root', str(vocab)])
            self.assertEqual(review.returncode, 1, review.stdout)
            report = json.loads(review.stdout)
            robust = [match for match in report['matches'] if match['not_recommended'] == 'robust']
            self.assertEqual(len(robust), 1)
            self.assertEqual(robust[0]['rule_scope'], 'paper')
            self.assertEqual(robust[0]['suggestion'], 'stable')
            self.assertEqual(paper.read_bytes(), before)
            self.assertEqual(len(report['rule_files']), 3)


if __name__ == '__main__':
    unittest.main()
