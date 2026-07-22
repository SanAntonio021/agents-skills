from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "manage_repo_mirrors.py"
SPEC = importlib.util.spec_from_file_location("manage_repo_mirrors", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import guard
    raise RuntimeError(f"Cannot load {SCRIPT_PATH}")
mirror_manager = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mirror_manager
SPEC.loader.exec_module(mirror_manager)


def make_mirror(mirror_id: str = "example") -> mirror_manager.MirrorConfig:
    return mirror_manager.MirrorConfig(
        id=mirror_id,
        repo_url=f"https://example.test/{mirror_id}.git",
        branch="main",
        local_path=Path(f"C:/repo-mirrors/{mirror_id}"),
        git_dir_path=Path(f"C:/git-dirs/{mirror_id}.git"),
        exposure_policy="zero",
        tracked_upstream_skills=("upstream-skill",),
        custom_wrappers=("local-skill",),
    )


def current_registry_text(mirror_id: str = "example", local_path: str | None = None) -> str:
    local_path = local_path or f"C:/repo-mirrors/{mirror_id}"
    return f'''[[mirror]]
id = "{mirror_id}"
repo_url = "https://example.test/{mirror_id}.git"
branch = "main"
local_path = "{local_path}"
git_dir_path = "C:/git-dirs/{mirror_id}.git"
exposure_policy = "zero"
tracked_upstream_skills = ["upstream-skill"]
custom_wrappers = ["local-skill"]
'''


class MirrorManagerTests(unittest.TestCase):
    def test_git_timeout_defaults_to_twenty_seconds(self) -> None:
        expired = subprocess.TimeoutExpired(["git", "status"], 20, output="partial output")
        with patch.object(mirror_manager.subprocess, "run", side_effect=expired) as run:
            result = mirror_manager.run_git(["git", "status"])

        self.assertEqual(run.call_args.kwargs["timeout"], 20.0)
        self.assertEqual(result["exit_code"], mirror_manager.TIMEOUT_EXIT_CODE)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["timeout_seconds"], 20.0)
        self.assertIn("partial output", result["output"])
        self.assertIn("timed out after 20 seconds", result["output"])

    def test_remote_fallback_shares_one_total_timeout_budget(self) -> None:
        failed = {
            "exit_code": 1,
            "output": "schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS",
        }
        succeeded = {"exit_code": 0, "output": "ok"}
        with (
            patch.object(mirror_manager, "run_git", side_effect=[failed, succeeded]) as run,
            patch.object(mirror_manager.time, "monotonic", side_effect=[100.0, 100.0, 115.0]),
        ):
            result = mirror_manager.run_git_with_remote_fallback(
                ["git", "ls-remote", "https://example.test/repo.git"], timeout_seconds=20.0
            )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(run.call_args_list[0].kwargs["timeout_seconds"], 20.0)
        self.assertEqual(run.call_args_list[1].kwargs["timeout_seconds"], 5.0)

    def test_one_check_failure_does_not_block_other_mirrors(self) -> None:
        mirrors = [make_mirror("bad"), make_mirror("good")]

        def fake_check(mirror: mirror_manager.MirrorConfig, timeout_seconds: float) -> dict[str, object]:
            if mirror.id == "bad":
                raise RuntimeError("simulated failure")
            return {"id": mirror.id, "status": "up_to_date"}

        with patch.object(mirror_manager, "check_one", side_effect=fake_check):
            results = mirror_manager.process_mirrors(mirrors, "check")

        self.assertEqual([result["id"] for result in results], ["bad", "good"])
        self.assertEqual(results[0]["status"], "check_failed")
        self.assertIn("simulated failure", results[0]["error"])
        self.assertEqual(results[1]["status"], "up_to_date")

    def test_parallel_check_worker_count_is_capped_at_four(self) -> None:
        recorded: dict[str, int] = {}

        class ImmediateFuture:
            def __init__(self, result: dict[str, object]) -> None:
                self._result = result

            def result(self) -> dict[str, object]:
                return self._result

        class RecordingExecutor:
            def __init__(self, max_workers: int, thread_name_prefix: str) -> None:
                recorded["max_workers"] = max_workers

            def __enter__(self) -> "RecordingExecutor":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def submit(self, function: object, *args: object) -> ImmediateFuture:
                return ImmediateFuture(function(*args))  # type: ignore[operator]

        mirrors = [make_mirror(str(index)) for index in range(6)]
        with (
            patch.object(mirror_manager, "ThreadPoolExecutor", RecordingExecutor),
            patch.object(
                mirror_manager,
                "check_one",
                side_effect=lambda mirror, timeout: {"id": mirror.id, "status": "up_to_date"},
            ),
        ):
            mirror_manager.process_mirrors(mirrors, "check")

        self.assertEqual(recorded["max_workers"], 4)

    def test_parallel_sync_worker_count_is_capped_at_four(self) -> None:
        recorded: dict[str, int] = {}

        class ImmediateFuture:
            def __init__(self, result: dict[str, object]) -> None:
                self._result = result

            def result(self) -> dict[str, object]:
                return self._result

        class RecordingExecutor:
            def __init__(self, max_workers: int, thread_name_prefix: str) -> None:
                recorded["max_workers"] = max_workers
                recorded["prefix"] = thread_name_prefix  # type: ignore[assignment]

            def __enter__(self) -> "RecordingExecutor":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def submit(self, function: object, *args: object) -> ImmediateFuture:
                return ImmediateFuture(function(*args))  # type: ignore[operator]

        mirrors = [make_mirror(str(index)) for index in range(6)]
        with (
            patch.object(mirror_manager, "ThreadPoolExecutor", RecordingExecutor),
            patch.object(
                mirror_manager,
                "sync_one",
                side_effect=lambda mirror, timeout: {"id": mirror.id, "status": "already_up_to_date"},
            ),
        ):
            results = mirror_manager.process_mirrors(mirrors, "sync")

        self.assertEqual(recorded["max_workers"], 4)
        self.assertEqual(recorded["prefix"], "mirror-sync")
        self.assertEqual(len(results), 6)

    def test_status_reports_up_to_date_and_update_available(self) -> None:
        mirror = make_mirror()
        local = {
            "local_exists": True,
            "local_repo_valid": True,
            "local_head": "a" * 40,
            "local_branch": "main",
            "local_dirty": False,
            "local_origin": mirror.repo_url,
        }

        up_to_date_remote = {"remote_reachable": True, "remote_head": "a" * 40}
        update_remote = {"remote_reachable": True, "remote_head": "b" * 40}

        self.assertEqual(mirror_manager.summarize_status(local, up_to_date_remote, mirror), "up_to_date")
        self.assertEqual(mirror_manager.summarize_status(local, update_remote, mirror), "update_available")

    def test_dirty_origin_and_branch_anomalies_take_precedence(self) -> None:
        mirror = make_mirror()
        remote = {"remote_reachable": True, "remote_head": "a" * 40}
        local = {
            "local_exists": True,
            "local_repo_valid": True,
            "local_head": "a" * 40,
            "local_branch": "main",
            "local_dirty": True,
            "local_origin": mirror.repo_url,
        }
        self.assertEqual(mirror_manager.summarize_status(local, remote, mirror), "dirty_mirror")
        local["local_dirty"] = False
        local["local_origin"] = "https://example.test/wrong.git"
        self.assertEqual(mirror_manager.summarize_status(local, remote, mirror), "origin_mismatch")
        local["local_origin"] = mirror.repo_url
        local["local_branch"] = "other"
        self.assertEqual(mirror_manager.summarize_status(local, remote, mirror), "branch_mismatch")

    def test_dirty_mirror_is_refused_without_fetching(self) -> None:
        mirror = make_mirror()
        dirty_state = {
            "local_exists": True,
            "local_repo_valid": True,
            "local_head": "a" * 40,
            "local_branch": "main",
            "local_dirty": True,
            "local_origin": mirror.repo_url,
            "local_error": None,
        }

        with (
            patch.object(mirror_manager, "get_local_repo_state", return_value=dirty_state),
            patch.object(mirror_manager, "run_local_git") as run_local_git,
        ):
            result = mirror_manager.sync_one(mirror)

        self.assertEqual(result["status"], "sync_failed")
        self.assertIn("uncommitted changes", result["error"])
        self.assertEqual(result["local_head"], "a" * 40)
        self.assertTrue(result["local_dirty"])
        run_local_git.assert_not_called()

    def test_sync_refuses_origin_or_branch_mismatch(self) -> None:
        mirror = make_mirror()
        base_state = {
            "local_exists": True,
            "local_repo_valid": True,
            "local_head": "a" * 40,
            "local_branch": "main",
            "local_dirty": False,
            "local_origin": "https://example.test/wrong.git",
            "local_error": None,
        }
        with patch.object(mirror_manager, "get_local_repo_state", return_value=base_state):
            result = mirror_manager.sync_one(mirror)
        self.assertEqual(result["status"], "sync_failed")
        self.assertIn("origin", result["error"])

        branch_state = {**base_state, "local_origin": mirror.repo_url, "local_branch": "other"}
        with patch.object(mirror_manager, "get_local_repo_state", return_value=branch_state):
            result = mirror_manager.sync_one(mirror)
        self.assertEqual(result["status"], "sync_failed")
        self.assertIn("branch", result["error"])

    def test_current_registry_shape_and_json_output_remain_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "repo-mirrors.toml"
            registry.write_text(
                current_registry_text(local_path=(Path(temp_dir) / "example").as_posix()),
                encoding="utf-8",
            )

            loaded = mirror_manager.load_registry(registry)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].tracked_upstream_skills, ("upstream-skill",))

            output = io.StringIO()
            with (
                patch.object(
                    mirror_manager,
                    "process_mirrors",
                    return_value=[{"id": "example", "status": "up_to_date"}],
                ),
                redirect_stdout(output),
            ):
                exit_code = mirror_manager.main(["check", "--registry", str(registry), "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "check")
        self.assertEqual(payload["summary"], {"up_to_date": 1})
        self.assertEqual(payload["mirrors"][0]["id"], "example")

    def test_cli_returns_nonzero_but_keeps_json_when_one_mirror_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "repo-mirrors.toml"
            registry.write_text(
                current_registry_text(local_path=(Path(temp_dir) / "example").as_posix()),
                encoding="utf-8",
            )
            output = io.StringIO()
            with (
                patch.object(
                    mirror_manager,
                    "process_mirrors",
                    return_value=[{"id": "example", "status": "remote_check_failed"}],
                ),
                redirect_stdout(output),
            ):
                exit_code = mirror_manager.main(["check", "--registry", str(registry), "--json"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["mirrors"][0]["status"], "remote_check_failed")

    def test_zero_exposure_registry_rejects_runtime_or_external_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "repo-mirrors.toml"
            registry.write_text(
                current_registry_text(local_path="C:/Users/example/.codex/skills/upstream"),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                mirror_manager.load_registry(registry)


if __name__ == "__main__":
    unittest.main()
