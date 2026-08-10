from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_local_distribution.py"
SPEC = importlib.util.spec_from_file_location("validate_local_distribution", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

COMMIT = "f7151330bda7d82936941a1b9b9aab49ca230eec"
SOURCE_REPO_URL = "https://github.com/hang-jin/editaplot.git"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ValidateLocalDistributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.skill_root = self.root / "skills" / "editaplot"
        scripts = self.skill_root / "scripts"
        scripts.mkdir(parents=True)
        for name in ("SKILL.md", "LICENSE", "NOTICE", "editaplot.cmd"):
            (self.skill_root / name).write_text(name, encoding="utf-8")
        (scripts / "bootstrap_editaplot.py").write_text("# fixture\n", encoding="utf-8")
        (scripts / "requirements-runtime.lock").write_text("fixture==1.0\n", encoding="utf-8")
        self.engine_home = self.root / "runtimes" / "editaplot" / COMMIT
        self._create_runtime(self.engine_home)
        self.config_path = self.skill_root / ".editaplot-local.json"
        self._write_config(self.engine_home)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_runtime(self, engine_home: Path) -> None:
        package = engine_home / "src" / "origin_sciplot"
        package.mkdir(parents=True)
        lock = engine_home / "requirements-runtime.lock"
        lock.write_text("fixture==1.0\n", encoding="utf-8")
        init = package / "__init__.py"
        init.write_text("__version__ = 'fixture'\n", encoding="utf-8")
        files = []
        for path in (lock, init):
            files.append(
                {
                    "path": path.relative_to(engine_home).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
        manifest = {
            "schema_version": "1.0",
            "source_policy": "fixture",
            "file_count": len(files),
            "files": files,
        }
        (engine_home / "runtime-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        environment = engine_home / ".editaplot-venv"
        (environment / "Scripts").mkdir(parents=True)
        (environment / "Scripts" / "python.exe").write_bytes(b"fixture")
        (environment / ".editaplot-environment.json").write_text(
            json.dumps({"dependency_lock_sha256": sha256(lock)}), encoding="utf-8"
        )

    def _write_config(self, engine_home: Path, manifest_sha256: str | None = None) -> None:
        manifest_hash = manifest_sha256 or sha256(engine_home / "runtime-manifest.json")
        self.config_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "engine_home": str(engine_home),
                    "source_repo_url": SOURCE_REPO_URL,
                    "expected_commit": COMMIT,
                    "expected_runtime_manifest_sha256": manifest_hash,
                    "generated_by": "test",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def validate(self) -> dict[str, object]:
        return MODULE.validate_distribution(self.skill_root, self.config_path)

    def test_accepts_commit_named_snapshot_with_matching_manifest(self) -> None:
        result = self.validate()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["checked_runtime_files"], 2)
        self.assertEqual(result["expected_commit"], COMMIT)

    def test_rejects_unexpected_manifest(self) -> None:
        self._write_config(self.engine_home, "0" * 64)
        result = self.validate()
        self.assertFalse(result["ok"])
        self.assertIn("runtime_manifest_hash_mismatch", result["errors"])

    def test_rejects_runtime_file_drift(self) -> None:
        (self.engine_home / "src" / "origin_sciplot" / "__init__.py").write_text(
            "__version__ = 'changed'\n", encoding="utf-8"
        )
        result = self.validate()
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(str(error).startswith("runtime_file_") for error in result["errors"])
        )

    def test_rejects_mutable_mirror_path(self) -> None:
        mirror_runtime = self.root / "upstream" / "hang-jin-editaplot" / "runtime"
        self._create_runtime(mirror_runtime)
        self._write_config(mirror_runtime)
        result = self.validate()
        self.assertFalse(result["ok"])
        self.assertIn("engine_home_not_versioned_snapshot", result["errors"])


if __name__ == "__main__":
    unittest.main()
