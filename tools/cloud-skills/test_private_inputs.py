"""Synthetic-only private-input contract tests; no account data or live sources."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('private_input_adapter', HERE / 'build.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
PUBLIC_REV = '1' * 40
PRIVATE_REV = '2' * 40
SYNTHETIC_REPOSITORY = 'https://github.com/synthetic-fixtures/private-vocabulary'
SYNTHETIC_MARKER = 'SYNTHETIC-PRIVATE-CONTENT-ONLY'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))


def synthetic_vocab(root):
    style = '| 不建议 | 建议 | 例外 |\n|---|---|---|\n'
    for name in adapter.PRIVATE_VOCAB_FILES:
        if name.startswith(('中文/', '英文/')):
            data = '# Synthetic fixture\n\n' + style
            if name == '英文/通用.md':
                data += '| syntheticobsolete | syntheticcurrent | synthetic quotation |\n'
        elif name == '术语.md':
            data = '# Synthetic terms\n\n| 中文 | 英文 |\n|---|---|\n| 合成测试项 | synthetic test item |\n'
        elif name == '维护.md':
            data = ('# Synthetic maintenance\n\n## 待确认\n\nNone.\n\n## 不采用\n\nNone.\n\n'
                    '## 检查补充\n\n| 条目 | 匹配 |\n|---|---|\n'
                    '| syntheticobsolete | `(?i)\\bsyntheticobsolete\\b` |\n\n'
                    '## 变更记录\n\n' + SYNTHETIC_MARKER + '\n')
        else:
            data = '# Synthetic directory\n\n' + '\n'.join(
                '- [' + p + '](' + p + ')' for p in sorted(adapter.PRIVATE_VOCAB_FILES - {'目录.md'})) + '\n'
        write(root / name, data)
    return root


def make_private_input(root):
    """Reusable synthetic input for other build tests; writes no real user data."""
    root = synthetic_vocab(Path(root))
    manifest = {
        'schema_version': 1, 'contract': 'style-vocab-v1', 'approved': True,
        'source_repository': SYNTHETIC_REPOSITORY, 'source_path': 'vocab',
        'source_revision': PRIVATE_REV,
        'files_sha256': {name: adapter.sha((root / name).read_bytes())
                         for name in adapter.PRIVATE_VOCAB_FILES},
    }
    return {'style_vocab': {'root': root, 'manifest': manifest}}


class PrivateInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source_root = self.base / 'source'
        self.inputs = make_private_input(self.base / 'private-input')
        self.vocab = self.inputs['style_vocab']['root']
        self.manifest = self.inputs['style_vocab']['manifest']
        self.source = b'---\nname: style-vocab\ndescription: Synthetic fixture.\n---\n\n# Synthetic fixture\n'
        write(self.source_root / 'style-vocab/SKILL.md', self.source)
        validator = (adapter.ROOT / adapter.PRIVATE_VALIDATOR_SOURCE).read_bytes()
        write(self.source_root / adapter.PRIVATE_VALIDATOR_SOURCE, validator)
        self.config = {
            'schema_version': 2, 'skill': 'style-vocab',
            'source_repository': 'https://github.com/synthetic-fixtures/public-skills',
            'source_path': 'style-vocab/SKILL.md', 'expected_source_sha256': adapter.sha(self.source),
            'adapter_version': 'synthetic-1', 'interface': {'display_name': 'Synthetic'},
            'files': [
                {'source': 'style-vocab/SKILL.md', 'target': 'SKILL.md', 'sha256': adapter.sha(self.source)},
                {'source': adapter.PRIVATE_VALIDATOR_SOURCE, 'target': 'scripts/audit_writing_memory.py',
                 'sha256': adapter.sha(validator)},
            ],
            'private_inputs': {'style_vocab': {'contract': 'style-vocab-v1', 'required': True}},
        }

    def hashes(self):
        return {name: adapter.sha((self.vocab / name).read_bytes()) for name in adapter.PRIVATE_VOCAB_FILES}

    def generate(self, inputs=True):
        return adapter.build(self.source, self.config, PUBLIC_REV, b'synthetic-adapter',
                             source_root=self.source_root, private_inputs=self.inputs if inputs else None)

    def materialize(self, output):
        target = self.base / 'installed-personal-skill'
        for name, data in output.items():
            write(target / name, data)
        return target

    def test_exact_eleven_resources_are_managed_and_deterministic(self):
        first = self.generate()
        self.assertEqual(first, self.generate())
        private_names = {name for name in first if name.startswith(adapter.PRIVATE_VOCAB_PREFIX)}
        self.assertEqual(private_names, {adapter.PRIVATE_VOCAB_PREFIX + name for name in adapter.PRIVATE_VOCAB_FILES})
        manifest = json.loads(first[adapter.MANIFEST])
        for name in private_names:
            self.assertEqual(manifest['generated_sha256'][name], adapter.sha(first[name]))
        private = manifest['private_inputs']['style_vocab']
        self.assertEqual(private['source_repository'], SYNTHETIC_REPOSITORY)
        self.assertEqual(private['source_revision'], PRIVATE_REV)
        self.assertEqual(private['files_sha256'], self.hashes())
        self.assertEqual(private['validation']['routes'], 14)
        self.assertEqual(private['validation']['style_files'], 8)
        self.assertEqual(private['manifest_sha256'], adapter.sha(adapter.json_bytes(self.manifest)))
        self.assertNotIn(str(self.vocab), first[adapter.MANIFEST].decode())

    def test_private_content_and_provenance_only_in_private_outputs(self):
        for name, data in self.generate().items():
            if name == adapter.MANIFEST or name.startswith(adapter.PRIVATE_VOCAB_PREFIX):
                continue
            self.assertNotIn(SYNTHETIC_REPOSITORY.encode(), data)
            self.assertNotIn(SYNTHETIC_MARKER.encode(), data)
        self.assertNotIn(SYNTHETIC_REPOSITORY, json.dumps(self.config))
        self.assertNotIn(SYNTHETIC_MARKER, json.dumps(self.config))

    def test_public_sources_and_private_inputs_are_read_only(self):
        original = adapter.files_snapshot(self.base)
        self.generate()
        self.assertEqual(adapter.files_snapshot(self.base), original)

    def test_required_absent_stops(self):
        with self.assertRaisesRegex(ValueError, 'required private vocabulary input is absent'):
            self.generate(inputs=False)

    def test_optional_absent_adds_no_private_resources_or_provenance(self):
        self.config['private_inputs']['style_vocab']['required'] = False
        output = self.generate(inputs=False)
        self.assertNotIn('private_inputs', json.loads(output[adapter.MANIFEST]))
        self.assertFalse(any(p.startswith(adapter.PRIVATE_VOCAB_PREFIX) for p in output))

    def test_only_style_vocab_can_opt_in(self):
        self.config['skill'] = 'other-skill'
        with self.assertRaisesRegex(ValueError, 'only for opted-in style-vocab'):
            adapter.private_vocab_inputs(self.config, self.inputs, self.source_root)

    def test_missing_contract_rejects_input(self):
        del self.config['private_inputs']
        with self.assertRaisesRegex(ValueError, 'explicit public contract'):
            self.generate()

    def test_contract_contains_no_private_source_fields(self):
        self.config['private_inputs']['style_vocab']['source_repository'] = SYNTHETIC_REPOSITORY
        with self.assertRaisesRegex(ValueError, 'abstract private vocabulary contract'):
            self.generate()

    def test_unknown_input_or_manifest_fields_fail_closed(self):
        for level, key in ((self.inputs, 'other'), (self.inputs['style_vocab'], 'other'), (self.manifest, 'other')):
            with self.subTest(level=key):
                level[key] = 'unexpected'
                with self.assertRaises(ValueError): self.generate()
                del level[key]

    def test_explicit_approval_required(self):
        for value in (False, 'true', 1, None):
            self.manifest['approved'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'explicit approval'):
                self.generate()

    def test_private_revision_and_repository_validated(self):
        for key, value in (('source_revision', 'main'), ('source_revision', 'abc1234'),
                           ('source_revision', 1), ('source_repository', 'https://example.com/repo'),
                           ('source_repository', 'https://token@github.com/example/repo'),
                           ('source_repository', 'https://github.com/example/repo?token=secret'),
                           ('source_repository', 'https://github.com/example/..')):
            original = self.manifest[key]
            self.manifest[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): self.generate()
            self.manifest[key] = original

    def test_private_source_path_cannot_escape(self):
        for value in ('../vocab', '/tmp/vocab', 'vocab/../other', r'C:\\vocab',
                      'C:/vocab', 'vocab\nother', 'vocab\x00other', './vocab'):
            self.manifest['source_path'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): self.generate()

    def test_private_manifest_exact_file_list_and_valid_hashes(self):
        original = self.manifest['files_sha256']
        for change in ('missing', 'extra', 'bad_hash'):
            hashes = dict(original)
            if change == 'missing': del hashes['目录.md']
            elif change == 'extra': hashes['extra.md'] = '0' * 64
            else: hashes['目录.md'] = 'g' * 64
            self.manifest['files_sha256'] = hashes
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'exact eleven-file set'):
                self.generate()
        self.manifest['files_sha256'] = original

    def test_actual_extra_missing_and_empty_directories_are_rejected(self):
        extra = self.vocab / 'extra.md'
        write(extra, 'synthetic')
        with self.assertRaisesRegex(ValueError, 'unexpected private vocabulary entry'): self.generate()
        extra.unlink()
        (self.vocab / 'unexpected-empty-directory').mkdir()
        with self.assertRaisesRegex(ValueError, 'unexpected private vocabulary entry'): self.generate()
        (self.vocab / 'unexpected-empty-directory').rmdir()
        (self.vocab / '目录.md').unlink()
        with self.assertRaisesRegex(ValueError, 'exact eleven-file set'): self.generate()

    def test_source_content_drift_requires_new_reviewed_hash(self):
        write(self.vocab / '目录.md', 'changed synthetic directory')
        with self.assertRaisesRegex(ValueError, 'source hash changed'): self.generate()

    def test_invalid_structure_rejected_even_with_matching_hash(self):
        invalid = ('| Wrong | Columns |\n|---|---|\n| x | y |\n',
                   '| 不建议 | 建议 | 例外 |\n|---|---|---|\n| duplicate | replacement | |\n| duplicate | other | |\n')
        for contents in invalid:
            write(self.vocab / '英文/通用.md', contents)
            self.manifest['files_sha256'] = self.hashes()
            with self.assertRaisesRegex(ValueError, 'structure validation failed'): self.generate()

    def test_invalid_match_override_rejected(self):
        path = self.vocab / '维护.md'
        write(path, path.read_text().replace('(?i)\\bsyntheticobsolete\\b', '['))
        self.manifest['files_sha256'] = self.hashes()
        with self.assertRaisesRegex(ValueError, 'structure validation failed'): self.generate()

    def test_validator_must_be_explicit_and_source_pinned(self):
        item = self.config['files'].pop()
        with self.assertRaisesRegex(ValueError, 'pinned original validator'): self.generate()
        self.config['files'].append(item)
        write(self.source_root / adapter.PRIVATE_VALIDATOR_SOURCE, b'raise RuntimeError("must not execute")')
        with self.assertRaisesRegex(ValueError, 'source hash changed'): self.generate()

    def test_symlink_file_root_and_ancestor_rejected(self):
        source = self.vocab / '目录.md'
        contents = source.read_bytes()
        external = self.base / 'external.md'
        write(external, contents)
        source.unlink()
        source.symlink_to(external)
        with self.assertRaisesRegex(ValueError, 'symlink'): self.generate()
        source.unlink()
        write(source, contents)
        link = self.base / 'root-link'
        link.symlink_to(self.vocab, target_is_directory=True)
        self.inputs['style_vocab']['root'] = link
        with self.assertRaisesRegex(ValueError, 'symlink'): self.generate()
        parent = self.base / 'parent-link'
        parent.symlink_to(self.base, target_is_directory=True)
        self.inputs['style_vocab']['root'] = parent / self.vocab.name
        with self.assertRaisesRegex(ValueError, 'symlink'): self.generate()

    def test_file_total_and_manifest_size_limits(self):
        with patch.object(adapter, 'PRIVATE_FILE_MAX_BYTES', 8):
            with self.assertRaisesRegex(ValueError, 'file is too large'): self.generate()
        with patch.object(adapter, 'PRIVATE_TOTAL_MAX_BYTES', 8):
            with self.assertRaisesRegex(ValueError, 'input is too large'): self.generate()
        with patch.object(adapter, 'PRIVATE_MANIFEST_MAX_BYTES', 8):
            with self.assertRaisesRegex(ValueError, 'manifest is too large'): self.generate()

    def test_directory_requires_nonempty_utf8(self):
        for value in (b'', b'  \n', b'\xff', b'bad\x00text'):
            write(self.vocab / '目录.md', value)
            with self.subTest(value=value), self.assertRaises(ValueError): self.generate()

    def test_validation_uses_snapshot_and_rechecks_input_for_races(self):
        original = adapter.validate_private_vocab
        def validate_then_change(*args):
            result = original(*args)
            write(self.vocab / '目录.md', 'changed during validation')
            return result
        with patch.object(adapter, 'validate_private_vocab', side_effect=validate_then_change):
            with self.assertRaisesRegex(ValueError, 'changed during validation'): self.generate()

    def test_public_mappings_cannot_write_into_private_namespace(self):
        self.config['files'][1]['target'] = adapter.PRIVATE_VOCAB_PREFIX + 'surprise.md'
        with self.assertRaisesRegex(ValueError, 'reserved output'): self.generate()

    def test_private_manifest_loader_rejects_duplicates_and_unpaired_paths(self):
        path = self.base / 'private-manifest.json'
        write(path, adapter.json_bytes(self.manifest))
        self.assertEqual(adapter.private_inputs_from_paths(path, self.vocab), self.inputs)
        self.assertIsNone(adapter.private_inputs_from_paths())
        for arguments in ((path, None), (None, self.vocab)):
            with self.assertRaisesRegex(ValueError, 'supplied together'):
                adapter.private_inputs_from_paths(*arguments)
        write(path, '{"approved":true,"approved":false}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): adapter.private_manifest_from_file(path)

    def test_preview_redacts_private_data_and_private_provenance(self):
        output = self.generate()
        for name in (adapter.MANIFEST, adapter.PRIVATE_VOCAB_PREFIX + '维护.md'):
            preview = adapter.preview_diff(name, b'', output[name])
            self.assertIn('contents omitted', preview)
            self.assertNotIn(SYNTHETIC_MARKER, preview)
            self.assertNotIn(SYNTHETIC_REPOSITORY, preview)
            self.assertNotIn(PRIVATE_REV, preview)
        self.assertIn('+new', adapter.preview_diff('public.md', b'old\n', b'new\n'))

    def test_materialized_private_files_participate_in_drift_checks(self):
        output = self.generate()
        target = self.materialize(output)
        write(target / adapter.MANIFEST, adapter.verify_materialized(target, output, adapter.snapshot(target)))
        self.assertEqual(adapter.plan(target, output, adapter.snapshot(target))[1], [])
        write(target / adapter.PRIVATE_VOCAB_PREFIX / '目录.md', 'unreviewed edit')
        with self.assertRaisesRegex(ValueError, 'materialized target drift'):
            adapter.plan(target, output, adapter.snapshot(target))

    def test_unknown_installed_private_extra_is_not_accepted(self):
        output = self.generate()
        target = self.materialize(output)
        write(target / adapter.PRIVATE_VOCAB_PREFIX / 'extra.md', 'unexpected')
        with self.assertRaisesRegex(ValueError, 'unexpected materialized files'):
            adapter.verify_materialized(target, output, adapter.snapshot(target))

    def test_mutable_hash_manifest_cannot_bless_private_content_edit(self):
        output = self.generate()
        target = self.materialize(output)
        manifest = json.loads(adapter.verify_materialized(target, output, adapter.snapshot(target)))
        name = adapter.PRIVATE_VOCAB_PREFIX + '目录.md'
        write(target / name, 'unreviewed edit')
        manifest['materialized_sha256'][name] = adapter.sha((target / name).read_bytes())
        write(target / adapter.MANIFEST, adapter.json_bytes(manifest))
        with self.assertRaisesRegex(ValueError, 'generated bytes differ'):
            adapter.plan(target, output, adapter.snapshot(target))

    def test_original_seven_need_no_input_and_empty_argument_is_identical(self):
        names = ('ask-first', 'handoff', 'humanizer', 'web-access', 'paper-search',
                 'paper-review', 'journal-submission')
        for name in names:
            config = json.loads((HERE / (name + '.json')).read_text())
            source = (adapter.ROOT / config['source_path']).read_bytes()
            args = (source, config, PUBLIC_REV, b'synthetic-adapter')
            output = adapter.build(*args)
            self.assertEqual(output, adapter.build(*args, private_inputs={}))
            self.assertNotIn('private_inputs', json.loads(output[adapter.MANIFEST]))


if __name__ == '__main__':
    unittest.main()
