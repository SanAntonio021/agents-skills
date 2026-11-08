import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('successor', Path(__file__).resolve().parents[1] / 'scripts/successor_reconciliation.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SuccessorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.original = {'remote_sha': 'a' * 40, 'outcome': 'blocked'}
        receipt = {'ok': True, 'exit_code': 0, 'status': 'runtime_active',
                   'expected_remote_commit': 'a' * 40, 'skills': [{'name': 'test'}]}
        self.proposal = {'original_execution_fingerprint': module.fingerprint(self.original),
                         'commit': 'a' * 40, 'skills': ['test'],
                         'sync': dict(receipt, verify_only=False),
                         'verify': dict(receipt, verify_only=True),
                         'scan': {'complete': True},
                         'manifests': {'test': {layer: {'SKILL.md': 'b' * 64}
                            for layer in ('source', 'cc_switch', 'claude', 'codex')}}}

    def test_complete_evidence_validates_without_mutating_history(self):
        before = copy.deepcopy(self.original)
        self.assertIsNone(module.validate(self.original, self.proposal))
        self.assertEqual(self.original, before)

    def test_manifest_drift_refused(self):
        self.proposal['manifests']['test']['codex']['SKILL.md'] = 'c' * 64
        self.assertIn('mismatch', module.validate(self.original, self.proposal))

    def test_other_commit_refused(self):
        self.proposal['verify']['expected_remote_commit'] = 'c' * 40
        self.assertIsNotNone(module.validate(self.original, self.proposal))

    def test_missing_original_sha_refused(self):
        self.original['remote_sha'] = None
        self.proposal['original_execution_fingerprint'] = module.fingerprint(self.original)
        self.assertIn('unavailable', module.validate(self.original, self.proposal))

    def test_incomplete_scan_refused(self):
        self.proposal['scan']['complete'] = False
        self.assertIsNotNone(module.validate(self.original, self.proposal))

    def test_stale_original_refused(self):
        self.original['details'] = 'changed'
        self.assertIn('fingerprint', module.validate(self.original, self.proposal))
