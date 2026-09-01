import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).parents[1] / "scripts" / "verify_ppt_master_pin.py"
spec = importlib.util.spec_from_file_location("pptx_ppt_master_pin", MODULE)
verifier = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(verifier)


UPSTREAM = {
    "commit": "c40bca58e168fcef2facdc7612cc352d1233679b",
    "repository": "https://github.com/hugohe3/ppt-master",
    "version": "6.1.0",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def release_record(role: str, marker: str, tag: str) -> dict:
    return {
        "codeload": {"members": 10, "sha256": marker * 64, "size": 1000},
        "distribution_manifest": {"bytes": 0, "files": 0, "sha256": "0" * 64},
        "fork_commit": marker * 40,
        "release_tag": tag,
        "role": role,
        "upstream": copy.deepcopy(UPSTREAM),
    }


def write_distribution(root: Path, release: dict) -> None:
    provenance = {
        "distribution": "ccswitch",
        "fork_repository": "https://github.com/SanAntonio021/ppt-master",
        "icon_storage": "deterministic-zip-stored-shards",
        "release_tag": release["release_tag"],
        "schema_version": 1,
        "upstream_commit": release["upstream"]["commit"],
        "upstream_repository": release["upstream"]["repository"],
        "upstream_version": release["upstream"]["version"],
    }
    files = {
        "LICENSE": b"MIT\n",
        "SKILL.md": b"---\nname: ppt-master\n---\n",
        "ccswitch.provenance.json": (
            json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
    }
    for relative, data in files.items():
        (root / relative).write_bytes(data)
    entries = [
        {"path": relative, "sha256": sha256_bytes(data), "size": len(data)}
        for relative, data in sorted(files.items())
    ]
    manifest = {
        "distribution": "ccswitch",
        "files": entries,
        "schema_version": 1,
        "totals": {"bytes": sum(item["size"] for item in entries), "files": len(entries)},
        "upstream": copy.deepcopy(release["upstream"]),
    }
    manifest_path = root / "distribution.manifest.json"
    write_json(manifest_path, manifest)
    release["distribution_manifest"] = {
        "bytes": manifest["totals"]["bytes"],
        "files": manifest["totals"]["files"],
        "sha256": verifier._sha256(manifest_path),
    }


def write_pin(path: Path, state: str, releases: list[dict]) -> None:
    write_json(
        path,
        {
            "accepted_distributions": releases,
            "policy": {
                "raw_file_identity": "relative_path+size+sha256",
                "system_fallback": False,
            },
            "schema_version": 1,
            "skill_name": "ppt-master",
            "source": {
                "branch": "ccswitch",
                "repository": "https://github.com/SanAntonio021/ppt-master",
            },
            "state": state,
        },
    )


class PptMasterPinTests(unittest.TestCase):
    def fixture(self, state: str, selected_role: str) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
        temporary = tempfile.TemporaryDirectory()
        base = Path(temporary.name)
        root = base / "ppt-master"
        root.mkdir()
        if state == "bootstrap":
            releases = [release_record("candidate", "a", "v6.1.0-ccswitch.1")]
        elif state == "stable":
            releases = [release_record("stable", "b", "v6.1.0-ccswitch.1")]
        else:
            releases = [
                release_record("stable", "c", "v6.0.0-ccswitch.1"),
                release_record("candidate", "d", "v6.1.0-ccswitch.1"),
            ]
        selected = next(release for release in releases if release["role"] == selected_role)
        write_distribution(root, selected)
        pin = base / "pin.json"
        write_pin(pin, state, releases)
        return root, pin, temporary

    def test_bootstrap_accepts_exact_candidate(self):
        root, pin, temporary = self.fixture("bootstrap", "candidate")
        self.addCleanup(temporary.cleanup)
        report = verifier.verify_installed(root, pin)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["pin_state"], "bootstrap")
        self.assertEqual(report["accepted_role"], "candidate")
        self.assertFalse(report["system_fallback"])

    def test_transition_accepts_candidate_while_old_stable_remains_pinned(self):
        root, pin, temporary = self.fixture("transition", "candidate")
        self.addCleanup(temporary.cleanup)
        report = verifier.verify_installed(root, pin)
        self.assertEqual(report["pin_state"], "transition")
        self.assertEqual(report["accepted_role"], "candidate")

    def test_stable_accepts_only_stable_distribution(self):
        root, pin, temporary = self.fixture("stable", "stable")
        self.addCleanup(temporary.cleanup)
        report = verifier.verify_installed(root, pin)
        self.assertEqual(report["pin_state"], "stable")
        self.assertEqual(report["accepted_role"], "stable")

    def test_state_cardinality_fails_closed(self):
        root, pin, temporary = self.fixture("bootstrap", "candidate")
        self.addCleanup(temporary.cleanup)
        payload = json.loads(pin.read_text(encoding="utf-8"))
        payload["state"] = "stable"
        write_json(pin, payload)
        with self.assertRaisesRegex(verifier.PinVerificationError, "requires roles"):
            verifier.verify_installed(root, pin)

    def test_manifest_digest_tamper_fails_before_tree_use(self):
        root, pin, temporary = self.fixture("bootstrap", "candidate")
        self.addCleanup(temporary.cleanup)
        manifest = root / "distribution.manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaisesRegex(verifier.PinVerificationError, "digest is not accepted"):
            verifier.verify_installed(root, pin)

    def test_protected_file_tamper_fails_raw_sha(self):
        root, pin, temporary = self.fixture("bootstrap", "candidate")
        self.addCleanup(temporary.cleanup)
        (root / "SKILL.md").write_bytes(b"tampered\n")
        with self.assertRaisesRegex(verifier.PinVerificationError, "size mismatch|SHA-256 mismatch"):
            verifier.verify_installed(root, pin)

    def test_unexpected_residual_file_fails(self):
        root, pin, temporary = self.fixture("bootstrap", "candidate")
        self.addCleanup(temporary.cleanup)
        (root / "residual.txt").write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(verifier.PinVerificationError, "membership mismatch"):
            verifier.verify_installed(root, pin)

    def test_wrong_upstream_commit_metadata_fails(self):
        root, pin, temporary = self.fixture("bootstrap", "candidate")
        self.addCleanup(temporary.cleanup)
        payload = json.loads(pin.read_text(encoding="utf-8"))
        payload["accepted_distributions"][0]["upstream"]["commit"] = "f" * 40
        write_json(pin, payload)
        with self.assertRaisesRegex(verifier.PinVerificationError, "upstream does not match"):
            verifier.verify_installed(root, pin)

    def test_codeload_member_limit_is_part_of_pin_validation(self):
        root, pin, temporary = self.fixture("bootstrap", "candidate")
        self.addCleanup(temporary.cleanup)
        payload = json.loads(pin.read_text(encoding="utf-8"))
        payload["accepted_distributions"][0]["codeload"]["members"] = 2001
        write_json(pin, payload)
        with self.assertRaisesRegex(verifier.PinVerificationError, "CC Switch limit"):
            verifier.verify_installed(root, pin)


if __name__ == "__main__":
    unittest.main()
