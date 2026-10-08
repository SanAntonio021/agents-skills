import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('adapter', HERE / 'build.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((HERE / 'ask-first.json').read_text())
        self.source = (HERE.parent.parent / 'ask-first/SKILL.md').read_bytes()
        self.revision = '992a217f29cdc8e04dc06dcb8d5c113cb8d43bdb'

    def build(self):
        return adapter.build(self.source, self.config, self.revision, (HERE / 'build.py').read_bytes())

    def test_deterministic(self):
        self.assertEqual(self.build(), self.build())

    def test_source_drift(self):
        self.source += b'changed'
        with self.assertRaisesRegex(ValueError, 'source hash changed'):
            self.build()

    def test_explicit_only_and_reviewable_transform(self):
        result = self.build()
        self.assertIn(b'allow_implicit_invocation: false', result['agents/openai.yaml'])
        self.assertNotIn(b'disable-model-invocation', result['SKILL.md'])
        actual = result['SKILL.md'].decode()
        actual = actual.removesuffix(self.config['append_body'])
        for item in reversed(self.config['replacements']):
            actual = actual.replace(item['after'], item['before'])
        actual = actual.replace('\n---\n', '\ndisable-model-invocation: true\n---\n', 1)
        self.assertEqual(actual.encode(), self.source)

    def test_changed_anchor_requires_review(self):
        self.config['replacements'][0]['before'] = 'missing anchor'
        with self.assertRaisesRegex(ValueError, 'anchor mismatch'):
            self.build()

    def test_manifest_hashes(self):
        result = self.build()
        manifest = json.loads(result[adapter.MANIFEST])
        self.assertEqual(manifest['source_sha256'], adapter.sha(self.source))
        for name, digest in manifest['generated_sha256'].items():
            self.assertEqual(adapter.sha(result[name]), digest)

    def test_snapshot_drift_and_idempotence(self):
        # Generic file fixtures exercise the planner, not a skill installation or validator.
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / 'example.txt').write_text('original')
            before = adapter.snapshot(target)
            output = {'example.txt': b'generated'}
            self.assertEqual(adapter.plan(target, output, before)[1], ['example.txt'])
            (target / 'example.txt').write_text('concurrent edit')
            with self.assertRaisesRegex(ValueError, 'target drift'):
                adapter.plan(target, output, before)
            self.assertEqual((target / 'example.txt').read_text(), 'concurrent edit')
            (target / 'example.txt').write_bytes(output['example.txt'])
            self.assertEqual(adapter.plan(target, output, adapter.snapshot(target))[1], [])

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / 'link').symlink_to('missing')
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                adapter.snapshot(target)

    def test_revision_requires_full_sha(self):
        self.revision = 'main'
        with self.assertRaisesRegex(ValueError, 'full commit SHA'):
            self.build()


if __name__ == '__main__':
    unittest.main()
