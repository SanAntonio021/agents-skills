from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for path in (SCRIPTS,):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import editaplot  # noqa: E402
import opju_review  # noqa: E402
from editaplot_core import EditaPlotError  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeEnvironment:
    def to_dict(self) -> dict[str, object]:
        return {
            "origin_version": "10.35",
            "origin_product": "2026b",
            "originpro_version": "1.1.15",
            "originext_version": "1.2.5",
            "connection_mode": "new_isolated",
            "session_ownership": "editaplot",
        }


class FakeLayer:
    def plot_list(self) -> list[object]:
        return [object()]


class FakeGraph:
    def __init__(self, name: str = "Graph1", *, export_ok: bool = True) -> None:
        self.name = name
        self.lname = f"Long {name}"
        self.export_ok = export_ok
        self.exported: list[Path] = []

    def __iter__(self):
        return iter([FakeLayer()])

    def get_int(self, prop: str) -> int:
        assert prop == "isEmbedded"
        return 0

    def save_fig(self, path: str, *, type: str, replace: bool, width: int) -> str:
        assert replace is False
        assert width == 2100
        target = Path(path)
        self.exported.append(target)
        if not self.export_ok:
            return ""
        target.write_bytes((f"fake-{type}".encode("ascii")))
        return str(target)


class FakeOrigin:
    def __init__(self, graphs: list[FakeGraph]) -> None:
        self.graphs = graphs
        self.open_calls: list[tuple[str, bool, bool]] = []
        self.attach_called = False
        self.save_called = False

    def open(self, path: str, *, readonly: bool, asksave: bool) -> bool:
        self.open_calls.append((path, readonly, asksave))
        return True

    def graph_list(self, select: str, inc_embed: bool) -> list[FakeGraph]:
        assert select == "p"
        assert inc_embed is True
        return self.graphs

    def attach(self) -> None:  # pragma: no cover - a guard against accidental calls
        self.attach_called = True
        raise AssertionError("review worker must never attach")

    def save(self, *args, **kwargs) -> bool:  # pragma: no cover - a guard against accidental calls
        self.save_called = True
        raise AssertionError("review worker must never save an Origin project")


class FakeSession:
    instances: list["FakeSession"] = []
    graphs: list[FakeGraph] = [FakeGraph()]

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.op = FakeOrigin(self.graphs)
        self.environment = FakeEnvironment()
        self.exited = False
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.exited = True


class OpjuReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "result.opju"
        self.source.write_bytes(b"origin-project-v1")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def prepare(self, *, output_dir: Path | None = None) -> dict[str, object]:
        return opju_review.prepare_opju_review(self.source, output_dir=output_dir)

    def test_prepare_creates_two_copies_and_metadata_without_overwrite(self) -> None:
        result = self.prepare()
        workspace = Path(str(result["workspace_path"]))
        initial = workspace / "figure_initial.opju"
        edit = workspace / "figure_edit.opju"
        metadata = workspace / "review-workspace.json"
        self.assertEqual(initial.read_bytes(), self.source.read_bytes())
        self.assertEqual(edit.read_bytes(), self.source.read_bytes())
        self.assertEqual(digest(initial), digest(edit))
        self.assertTrue(metadata.is_file())
        with self.assertRaisesRegex(EditaPlotError, "already exists"):
            self.prepare(output_dir=workspace)

    def test_prepare_rejects_workspace_inside_source_file_parent_target(self) -> None:
        # A directory named after an existing source file cannot be used as a workspace.
        with self.assertRaises(EditaPlotError) as context:
            self.prepare(output_dir=self.source)
        self.assertEqual(context.exception.code, "opju_workspace_contains_source")

    def test_review_worker_opens_readonly_and_never_attaches_or_saves(self) -> None:
        result = self.prepare()
        workspace = Path(str(result["workspace_path"]))
        review_dir = workspace / "review" / "run"
        review_dir.mkdir(parents=True)
        snapshot = review_dir / "snapshot.opju"
        snapshot.write_bytes((workspace / "figure_edit.opju").read_bytes())
        FakeSession.instances.clear()
        payload = opju_review.run_review_worker(
            snapshot,
            review_dir,
            session_factory=FakeSession,
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["graph_page_count"], 1)
        session = FakeSession.instances[-1]
        self.assertEqual(session.op.open_calls[0], (str(snapshot.resolve()), True, False))
        self.assertFalse(session.op.attach_called)
        self.assertFalse(session.op.save_called)
        self.assertTrue(session.exited)
        for suffix in ("png", "pdf", "tif"):
            self.assertTrue((review_dir / f"graph-001-Graph1.{suffix}").is_file())

    def test_review_worker_rejects_no_graph_pages(self) -> None:
        result = self.prepare()
        workspace = Path(str(result["workspace_path"]))
        review_dir = workspace / "review" / "run"
        review_dir.mkdir(parents=True)
        snapshot = review_dir / "snapshot.opju"
        snapshot.write_bytes(b"snapshot")
        FakeSession.graphs = []
        try:
            with self.assertRaises(EditaPlotError) as context:
                opju_review.run_review_worker(snapshot, review_dir, session_factory=FakeSession)
            self.assertEqual(context.exception.code, "opju_no_graph_pages")
        finally:
            FakeSession.graphs = [FakeGraph()]

    def test_review_worker_reports_export_failure(self) -> None:
        result = self.prepare()
        workspace = Path(str(result["workspace_path"]))
        review_dir = workspace / "review" / "run"
        review_dir.mkdir(parents=True)
        snapshot = review_dir / "snapshot.opju"
        snapshot.write_bytes(b"snapshot")
        FakeSession.graphs = [FakeGraph(export_ok=False)]
        try:
            with self.assertRaises(EditaPlotError) as context:
                opju_review.run_review_worker(snapshot, review_dir, session_factory=FakeSession)
            self.assertEqual(context.exception.code, "opju_export_failed")
        finally:
            FakeSession.graphs = [FakeGraph()]

    def test_review_worker_rejects_output_directory_outside_snapshot_directory(self) -> None:
        result = self.prepare()
        workspace = Path(str(result["workspace_path"]))
        review_dir = workspace / "review" / "run"
        review_dir.mkdir(parents=True)
        snapshot = review_dir / "snapshot.opju"
        snapshot.write_bytes(b"snapshot")
        with self.assertRaises(EditaPlotError) as context:
            opju_review.run_review_worker(snapshot, workspace, session_factory=FakeSession)
        self.assertEqual(context.exception.code, "opju_review_output_contains_snapshot")

    def test_prepare_rejects_source_changed_during_copy(self) -> None:
        workspace = self.root / "review-workspace"
        original_sha = digest(self.source)
        calls = {"count": 0}

        def changing_sha(path: Path) -> str:
            calls["count"] += 1
            if calls["count"] == 2:
                self.source.write_bytes(b"changed-while-copying")
            return original_sha if calls["count"] == 1 else digest(path)

        with mock.patch.object(opju_review, "_sha256", side_effect=changing_sha):
            with self.assertRaises(EditaPlotError) as context:
                self.prepare(output_dir=workspace)
        self.assertEqual(context.exception.code, "opju_source_changed_during_copy")
        self.assertFalse((workspace / "figure_initial.opju").exists())

    def test_review_rejects_changed_initial_baseline(self) -> None:
        result = self.prepare()
        workspace = Path(str(result["workspace_path"]))
        initial = workspace / "figure_initial.opju"
        initial.write_bytes(b"tampered")
        with self.assertRaises(EditaPlotError) as context:
            opju_review.review_opju(workspace / "figure_edit.opju")
        self.assertEqual(context.exception.code, "opju_initial_baseline_changed")

    def test_review_rejects_edit_change_after_snapshot(self) -> None:
        result = self.prepare()
        workspace = Path(str(result["workspace_path"]))
        review_dir = workspace / "review" / "run"

        def fake_worker_command(snapshot, target, **kwargs):
            # Simulate an Origin worker that completed while the user saved again.
            workspace.joinpath("figure_edit.opju").write_bytes(b"changed-during-review")
            return [sys.executable, "-c", "print('{}')"], {}, workspace

        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps({"ok": True}), stderr="")
        with mock.patch.object(opju_review, "_worker_command", side_effect=fake_worker_command):
            with mock.patch.object(opju_review.subprocess, "run", return_value=completed):
                with self.assertRaises(EditaPlotError) as context:
                    opju_review.review_opju(workspace / "figure_edit.opju")
        self.assertEqual(context.exception.code, "opju_edit_changed_during_review")
        self.assertTrue((workspace / "review").is_dir())

    def test_cli_parser_contains_opju_commands(self) -> None:
        parser = editaplot.build_parser()
        self.assertEqual(parser.parse_args(["prepare-opju-review", "x.opju"]).command, "prepare-opju-review")
        self.assertEqual(parser.parse_args(["review-opju", "figure_edit.opju"]).command, "review-opju")


if __name__ == "__main__":
    unittest.main()
