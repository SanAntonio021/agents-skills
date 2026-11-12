from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_feishu_official_skills.py"
SPEC = importlib.util.spec_from_file_location("check_feishu_official_skills", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


class Fixture:
    """A fake official site plus a fake machine, all inside one temp directory."""

    def __init__(self, tmp: Path) -> None:
        self.site = tmp / "site"
        self.home = tmp / "home"
        self.root = tmp / "agents"
        self.out = tmp / "out"
        self.lock: dict[str, dict[str, str]] = {}
        self.registry: list[tuple[str, str]] = []
        self.index: dict[str, list[str]] = {}
        (self.root / "skills").mkdir(parents=True)
        (self.home / ".agents" / "skills").mkdir(parents=True)

    @property
    def index_url(self) -> str:
        return (self.site / "index.json").as_uri()

    def official(self, name: str, files: dict[str, bytes | str]) -> None:
        self.index[name] = list(files)
        for rel, data in files.items():
            write(self.site / name / rel, data)

    def install(self, name: str, files: dict[str, bytes | str], layers: tuple[str, ...] = ("claude", "codex")) -> None:
        """Officially installed package: entity plus identical runtime layers and a lock entry."""
        self.lock[name] = {"sourceType": "well-known", "source": "open.feishu.cn"}
        for base in [self.home / ".agents" / "skills", *[self.home / f".{layer}" / "skills" for layer in layers]]:
            for rel, data in files.items():
                write(base / name / rel, data)

    def localize(self, name: str, baseline: dict[str, bytes | str], entity: dict[str, bytes | str],
                 with_baseline: bool = True, in_lock: bool = True) -> None:
        """Locally taken-over package: self-owned source, localized registration, accepted baseline."""
        self.registry.append((name, "localized"))
        if in_lock:
            self.lock[name] = {"sourceType": "well-known", "source": "open.feishu.cn"}
        for rel, data in entity.items():
            write(self.root / "skills" / name / rel, data)
            write(self.home / ".agents" / "skills" / name / rel, data)
        if with_baseline:
            base = self.root / "upstream" / "official-baselines" / name
            manifest = {}
            for rel, data in baseline.items():
                raw = data.encode("utf-8") if isinstance(data, str) else data
                manifest[rel] = sha(raw)
                write(base / "files" / rel, raw)
            write(base / "baseline.json", json.dumps({
                "schema_version": 1, "skill": name, "index_url": self.index_url,
                "accepted_at": "2026-10-18T00:00:00+00:00", "files": manifest,
            }))

    def self_built(self, name: str, status: str = "none") -> None:
        self.registry.append((name, status))
        write(self.root / "skills" / name / "SKILL.md", "self built")

    def finish(self) -> None:
        write(self.site / "index.json", json.dumps(
            {"skills": [{"name": name, "files": files} for name, files in self.index.items()]}))
        write(self.home / ".agents" / ".skill-lock.json", json.dumps({"skills": self.lock}))
        body = "".join(f'[[skill]]\nname = "{name}"\nstatus = "{status}"\n\n' for name, status in self.registry)
        write(self.root / "upstream" / "skill-sources.toml", body)

    def config(self, **overrides) -> "MODULE.Config":
        values = dict(agents_root=self.root, out=self.out, home=self.home, index_url=self.index_url,
                      retry_waits=(), refetch=2, workers=2)
        values.update(overrides)
        return MODULE.Config(**values)

    def run(self, fetch=None, **overrides):
        self.finish()
        return MODULE.run_check(self.config(**overrides), fetch)


class CheckFeishuOfficialSkillsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fx = Fixture(Path(self._tmp.name))

    def test_no_changes(self) -> None:
        files = {"SKILL.md": "official\n", "references/a.md": "ref\n"}
        self.fx.official("lark-im", files)
        self.fx.install("lark-im", files)
        self.fx.official("lark-base", files)
        self.fx.localize("lark-base", baseline=files, entity={**files, "references/local.md": "local\n"})
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_NO_CHANGES)
        self.assertEqual(report["status"], "no_changes")
        self.assertTrue(report["complete"])
        self.assertEqual(report["official_installed"], ["lark-im"])
        self.assertEqual(report["localized"], ["lark-base"])
        self.assertEqual(report["counts"]["downloaded_files"], 4)
        self.assertTrue((self.fx.out / "official" / "lark-base" / "references" / "a.md").is_file())
        saved = json.loads((self.fx.out / "comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["exit_code"], 0)
        self.assertTrue(report["lock_unchanged"])

    def test_official_installed_added_removed_changed(self) -> None:
        self.fx.official("lark-im", {"SKILL.md": "new text\n", "references/added.md": "added\n"})
        self.fx.install("lark-im", {"SKILL.md": "old text\n", "references/gone.md": "gone\n"})
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_CHANGES)
        change = report["changed_skills"]["lark-im"]
        self.assertEqual(change["kind"], "official_installed")
        self.assertEqual(change["official_added"], ["references/added.md"])
        self.assertEqual(change["official_removed"], ["references/gone.md"])
        self.assertEqual(change["changed"], ["SKILL.md"])
        diff = (self.fx.out / "diffs" / "lark-im" / "SKILL.md.diff").read_text(encoding="utf-8")
        self.assertIn("-old text", diff)
        self.assertIn("+new text", diff)

    def test_localized_is_compared_with_baseline_not_entity(self) -> None:
        baseline = {"SKILL.md": "v1\n", "references/a.md": "a1\n", "references/old.md": "old\n"}
        entity = {"SKILL.md": "v1 plus local edit\n", "references/a.md": "a1\n", "references/local.md": "local\n"}
        self.fx.official("lark-doc", {"SKILL.md": "v1\n", "references/a.md": "a2\n", "references/new.md": "new\n"})
        self.fx.localize("lark-doc", baseline=baseline, entity=entity)
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_CHANGES)
        change = report["changed_skills"]["lark-doc"]
        self.assertEqual(change["kind"], "localized")
        self.assertEqual(change["official_added"], ["references/new.md"])
        self.assertEqual(change["official_removed"], ["references/old.md"])
        # SKILL.md differs in the entity only: a local edit must not be reported as an official change.
        self.assertEqual(change["changed"], ["references/a.md"])
        row = next(r for r in report["skills"] if r["skill"] == "lark-doc")
        self.assertEqual(row["compared_with"], "accepted_baseline")
        self.assertNotIn("layers", row)
        diff = (self.fx.out / "diffs" / "lark-doc" / "references" / "a.md.diff").read_text(encoding="utf-8")
        self.assertIn("baseline/lark-doc/references/a.md", diff)

    def test_localized_unchanged_even_when_entity_has_local_additions(self) -> None:
        baseline = {"SKILL.md": "v1\n"}
        self.fx.official("lark-base", baseline)
        self.fx.localize("lark-base", baseline=baseline, entity={"SKILL.md": "v1 local\n", "LICENSE": "MIT\n"})
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_NO_CHANGES)
        self.assertEqual(report["changed_skills"], {})

    def test_download_failure_is_incomplete_not_unchanged(self) -> None:
        files = {"SKILL.md": "same\n", "references/a.md": "a\n"}
        self.fx.official("lark-im", files)
        self.fx.install("lark-im", files)
        self.fx.finish()
        (self.fx.site / "lark-im" / "references" / "a.md").unlink()
        report, code = MODULE.run_check(self.fx.config())
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["incomplete_skills"], ["lark-im"])
        self.assertEqual([e["path"] for e in report["download_errors"]], ["references/a.md"])
        row = report["skills"][0]
        # The missing download must not be reported as a file the official side removed.
        self.assertEqual(row["official_removed"], [])
        self.assertEqual(row["status"], "incomplete")

    def test_index_download_failure_is_incomplete(self) -> None:
        self.fx.official("lark-im", {"SKILL.md": "x\n"})
        self.fx.install("lark-im", {"SKILL.md": "x\n"})
        self.fx.finish()
        (self.fx.site / "index.json").unlink()
        report, code = MODULE.run_check(self.fx.config())
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertEqual(report["errors"][0]["code"], "index_download_failed")
        self.assertTrue((self.fx.out / "comparison.json").is_file())

    def _alternating_fetch(self, url_suffix: str, variants: list[bytes]):
        real = MODULE.make_fetch(10)
        calls = {"n": 0}

        def fetch(url: str) -> bytes:
            if url.endswith(url_suffix):
                data = variants[calls["n"] % len(variants)]
                calls["n"] += 1
                return data
            return real(url)

        return fetch

    def test_unstable_response_matching_target_is_listed_but_not_a_change(self) -> None:
        self.fx.official("lark-apps", {"SKILL.md": "s\n", "assets/index.html": "idc=hl\n"})
        self.fx.install("lark-apps", {"SKILL.md": "s\n", "assets/index.html": "idc=hl\n"})
        fetch = self._alternating_fetch("lark-apps/assets/index.html", [b"idc=lf\n", b"idc=hl\n"])
        report, code = self.fx.run(fetch=fetch)
        self.assertEqual(code, MODULE.EXIT_NO_CHANGES)
        self.assertEqual(report["unstable_matching_target"], {"lark-apps": ["assets/index.html"]})
        row = report["skills"][0]
        self.assertTrue(row["unstable_matching_target"][0]["unstable_response"])
        self.assertEqual(len(row["unstable_matching_target"][0]["variants"]), 2)

    def test_unstable_response_never_matching_target_is_a_change(self) -> None:
        self.fx.official("lark-apps", {"SKILL.md": "s\n", "assets/index.html": "placeholder\n"})
        self.fx.install("lark-apps", {"SKILL.md": "s\n", "assets/index.html": "idc=old\n"})
        fetch = self._alternating_fetch("lark-apps/assets/index.html", [b"idc=lf\n", b"idc=hl\n"])
        report, code = self.fx.run(fetch=fetch)
        self.assertEqual(code, MODULE.EXIT_CHANGES)
        self.assertEqual(report["changed_skills"]["lark-apps"]["changed"], ["assets/index.html"])
        record = report["skills"][0]["changed"][0]
        self.assertTrue(record["unstable_response"])
        self.assertFalse(record["matches_target"])

    def test_eol_only_change_is_flagged(self) -> None:
        self.fx.official("lark-im", {"SKILL.md": b"line1\r\nline2\r\n"})
        self.fx.install("lark-im", {"SKILL.md": b"line1\nline2\n"})
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_CHANGES)
        self.assertEqual(report["changed_skills"]["lark-im"]["eol_only"], ["SKILL.md"])

    def test_self_built_skill_is_excluded_and_not_downloaded(self) -> None:
        self.fx.official("lark-whiteboard", {"SKILL.md": "official whiteboard\n"})
        self.fx.self_built("lark-whiteboard")
        self.fx.official("lark-new", {"SKILL.md": "new\n"})
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_NO_CHANGES)
        self.assertEqual(report["excluded_self_built"], ["lark-whiteboard"])
        self.assertEqual(report["not_installed_candidates"], ["lark-new"])
        self.assertEqual(report["counts"]["downloaded_files"], 0)
        self.assertFalse((self.fx.out / "official" / "lark-whiteboard").exists())

    def test_takeover_without_localized_registration_is_an_error(self) -> None:
        files = {"SKILL.md": "x\n"}
        self.fx.official("lark-doc", files)
        self.fx.install("lark-doc", files)
        self.fx.self_built("lark-doc", status="none")
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertEqual([e["code"] for e in report["errors"]], ["unregistered_takeover"])
        self.assertEqual(report["official_installed"], [])

    def test_localized_without_baseline_is_an_error(self) -> None:
        self.fx.official("lark-doc", {"SKILL.md": "x\n"})
        self.fx.localize("lark-doc", baseline={}, entity={"SKILL.md": "x\n"}, with_baseline=False)
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertEqual([e["code"] for e in report["errors"]], ["baseline_missing"])

    def test_baseline_without_localized_registration_is_an_error(self) -> None:
        self.fx.official("lark-doc", {"SKILL.md": "x\n"})
        self.fx.localize("lark-doc", baseline={"SKILL.md": "x\n"}, entity={"SKILL.md": "x\n"})
        self.fx.registry = [("lark-doc", "none")]
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertIn("baseline_not_registered_localized", [e["code"] for e in report["errors"]])

    def test_scope_skill_missing_from_index_is_an_error(self) -> None:
        self.fx.install("lark-im", {"SKILL.md": "x\n"})
        self.fx.official("lark-other", {"SKILL.md": "y\n"})
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertEqual([e["code"] for e in report["errors"]], ["missing_from_index"])

    def test_unsafe_index_path_is_rejected(self) -> None:
        self.fx.install("lark-im", {"SKILL.md": "x\n"})
        self.fx.index["lark-im"] = ["../escape.md"]
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertEqual(report["errors"][0]["code"], "index_unsafe_path")
        self.assertFalse((self.fx.out / "official").exists())

    def test_layer_drift_is_reported(self) -> None:
        files = {"SKILL.md": "same\n"}
        self.fx.official("lark-im", files)
        self.fx.install("lark-im", files)
        write(self.fx.home / ".codex" / "skills" / "lark-im" / "SKILL.md", "stale copy\n")
        report, code = self.fx.run()
        self.assertEqual(code, MODULE.EXIT_CHANGES)
        self.assertEqual(report["changed_skills"], {})
        self.assertEqual(report["layer_drift"]["lark-im"]["codex"]["changed"], ["SKILL.md"])
        layers = report["skills"][0]["layers"]
        self.assertFalse(layers["claude"]["drift"])
        self.assertFalse(layers["cc_switch"]["present"])

    def test_existing_snapshot_requires_overwrite(self) -> None:
        files = {"SKILL.md": "x\n"}
        self.fx.official("lark-im", files)
        self.fx.install("lark-im", files)
        _, first = self.fx.run()
        self.assertEqual(first, MODULE.EXIT_NO_CHANGES)
        write(self.fx.out / "official" / "stale" / "old.md", "stale\n")
        report, code = MODULE.run_check(self.fx.config())
        self.assertEqual(code, MODULE.EXIT_INCOMPLETE)
        self.assertEqual(report["errors"][0]["code"], "output_exists")
        self.assertTrue((self.fx.out / "official" / "stale" / "old.md").is_file())
        report, code = MODULE.run_check(self.fx.config(overwrite=True))
        self.assertEqual(code, MODULE.EXIT_NO_CHANGES)
        self.assertFalse((self.fx.out / "official" / "stale").exists())

    def test_only_writes_inside_out(self) -> None:
        baseline = {"SKILL.md": "v1\n"}
        self.fx.official("lark-doc", {"SKILL.md": "v2\n"})
        self.fx.localize("lark-doc", baseline=baseline, entity={"SKILL.md": "v1 local\n"})
        self.fx.finish()
        watched = [self.fx.home, self.fx.root, self.fx.site]

        def snapshot() -> dict[str, str]:
            return {str(p): sha(p.read_bytes()) for base in watched for p in sorted(base.rglob("*")) if p.is_file()}

        before = snapshot()
        _, code = MODULE.run_check(self.fx.config())
        self.assertEqual(code, MODULE.EXIT_CHANGES)
        self.assertEqual(snapshot(), before)

    def test_cli_prints_summary_and_returns_exit_code(self) -> None:
        files = {"SKILL.md": "x\n"}
        self.fx.official("lark-im", files)
        self.fx.install("lark-im", files)
        self.fx.finish()
        import subprocess
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--agents-root", str(self.fx.root), "--out", str(self.fx.out),
             "--home", str(self.fx.home), "--index-url", self.fx.index_url, "--retry-waits", ""],
            capture_output=True,
        )
        self.assertEqual(completed.returncode, MODULE.EXIT_NO_CHANGES, completed.stderr.decode("utf-8", "replace"))
        summary = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual(summary["status"], "no_changes")
        self.assertNotIn("skills", summary)


if __name__ == "__main__":
    unittest.main()
