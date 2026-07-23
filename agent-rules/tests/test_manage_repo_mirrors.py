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


def healthy_local_state(mirror: mirror_manager.MirrorConfig, head: str) -> dict[str, object]:
    return {
        "local_exists": True,
        "local_repo_valid": True,
        "local_head": head,
        "local_branch": mirror.branch,
        "local_dirty": False,
        "local_origin": mirror.repo_url,
        "actual_git_dir_path": mirror.git_dir_path.as_posix() if mirror.git_dir_path else None,
        "git_dir_matches_registry": True if mirror.git_dir_path else None,
        "local_error": None,
    }


def run_real_git(repo: Path | None, *args: str) -> str:
    command = ["git"]
    if repo is not None:
        command.extend(["-C", str(repo)])
    command.extend(args)
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def create_local_remote_fixture(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    source.mkdir()
    run_real_git(source, "init", "-b", "main")
    run_real_git(source, "config", "user.name", "Mirror Test")
    run_real_git(source, "config", "user.email", "mirror-test@example.com")
    tracked = source / "skills" / "upstream-skill"
    tracked.mkdir(parents=True)
    (tracked / "SKILL.md").write_text("# v1\n", encoding="utf-8")
    run_real_git(source, "add", ".")
    run_real_git(source, "commit", "-m", "initial")

    remote = root / "remote.git"
    run_real_git(None, "init", "--bare", str(remote))
    run_real_git(source, "remote", "add", "origin", remote.as_posix())
    run_real_git(source, "push", "-u", "origin", "main")
    run_real_git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    return source, remote


def current_registry_text(
    mirror_id: str = "example",
    local_path: str | None = None,
    git_dir_path: str | None = None,
    include_git_dir: bool = True,
) -> str:
    local_path = local_path or f"C:/repo-mirrors/{mirror_id}"
    git_dir_path = git_dir_path or f"C:/git-dirs/{mirror_id}.git"
    git_dir_line = f'git_dir_path = "{git_dir_path}"\n' if include_git_dir else ""
    return f'''[[mirror]]
id = "{mirror_id}"
repo_url = "https://example.test/{mirror_id}.git"
branch = "main"
local_path = "{local_path}"
{git_dir_line}exposure_policy = "zero"
tracked_upstream_skills = ["upstream-skill"]
custom_wrappers = ["local-skill"]
'''


class MirrorManagerTests(unittest.TestCase):
    def test_git_timeout_defaults_to_twenty_seconds(self) -> None:
        class TimedOutProcess:
            pid = 1234

            def __init__(self) -> None:
                self.wait_calls: list[float] = []

            def wait(self, timeout: float) -> int:
                self.wait_calls.append(timeout)
                if len(self.wait_calls) == 1:
                    raise subprocess.TimeoutExpired(["git", "status"], timeout)
                return 1

            def poll(self) -> None:
                return None

            def kill(self) -> None:
                raise AssertionError("Process-tree termination should handle the timeout")

        process = TimedOutProcess()

        def fake_popen(*_: object, **kwargs: object) -> TimedOutProcess:
            stdout = kwargs["stdout"]
            assert hasattr(stdout, "write")
            stdout.write(b"partial output")
            stdout.flush()
            return process

        with (
            patch.object(mirror_manager.subprocess, "Popen", side_effect=fake_popen) as popen,
            patch.object(mirror_manager, "terminate_process_tree") as terminate,
        ):
            result = mirror_manager.run_git(["git", "status"])

        self.assertEqual(process.wait_calls, [20.0, 5])
        terminate.assert_called_once_with(process)
        self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(result["exit_code"], mirror_manager.TIMEOUT_EXIT_CODE)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["timeout_seconds"], 20.0)
        self.assertIn("partial output", result["output"])
        self.assertIn("timed out after 20 seconds", result["output"])

    def test_windows_timeout_terminates_only_the_spawned_process_tree(self) -> None:
        process = unittest.mock.Mock()
        process.pid = 4321
        process.poll.return_value = None
        with (
            patch.object(mirror_manager.sys, "platform", "win32"),
            patch.object(mirror_manager.subprocess, "run") as taskkill,
        ):
            mirror_manager.terminate_process_tree(process)

        taskkill.assert_called_once()
        self.assertEqual(
            taskkill.call_args.args[0],
            ["taskkill", "/PID", "4321", "/T", "/F"],
        )
        process.kill.assert_not_called()

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

    def test_transient_tls_failure_retries_once_within_total_budget(self) -> None:
        failed = {
            "exit_code": 1,
            "output": "TLS connect error: unexpected eof while reading",
        }
        succeeded = {"exit_code": 0, "output": "ok"}
        with (
            patch.object(mirror_manager, "run_git", side_effect=[failed, succeeded]) as run,
            patch.object(mirror_manager.time, "monotonic", side_effect=[100.0, 100.0, 104.0]),
        ):
            result = mirror_manager.run_git_with_remote_fallback(
                ["git", "ls-remote", "https://example.test/repo.git"],
                timeout_seconds=20.0,
            )

        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(len(run.call_args_list), 2)
        self.assertEqual(run.call_args_list[0].kwargs["timeout_seconds"], 20.0)
        self.assertEqual(run.call_args_list[1].kwargs["timeout_seconds"], 16.0)

    def test_clone_disables_blind_retry_and_preserves_original_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mirror = mirror_manager.MirrorConfig(
                **{
                    **make_mirror().__dict__,
                    "local_path": root / "worktree",
                    "git_dir_path": root / "git" / "mirror.git",
                }
            )
            failed = {
                "exit_code": 1,
                "output": "TLS connect error: unexpected EOF after creating a partial directory",
            }
            with patch.object(
                mirror_manager,
                "run_git_with_remote_fallback",
                return_value=failed,
            ) as remote:
                result = mirror_manager.sync_one(mirror)

        self.assertEqual(result["status"], "sync_failed")
        self.assertEqual(result["error"], failed["output"])
        self.assertFalse(remote.call_args.kwargs["allow_retries"])

    def test_missing_legacy_mirror_check_and_sync_are_consistently_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mirror = mirror_manager.MirrorConfig(
                **{
                    **make_mirror().__dict__,
                    "local_path": root / "missing-worktree",
                    "git_dir_path": None,
                }
            )
            missing = {
                "local_exists": False,
                "local_repo_valid": False,
                "local_head": None,
                "local_branch": None,
                "local_dirty": None,
                "local_origin": None,
                "local_error": None,
            }
            with (
                patch.object(mirror_manager, "get_local_repo_state", return_value=missing),
                patch.object(mirror_manager, "run_git_with_remote_fallback") as clone,
            ):
                checked = mirror_manager.check_one(mirror)
                result = mirror_manager.sync_one(mirror)

        self.assertEqual(checked["status"], "blocked_missing_git_dir")
        self.assertFalse(checked["sync_recommended"])
        self.assertIn("skipped", checked["remote_error"].lower())
        self.assertEqual(result["status"], "blocked_missing_git_dir")
        self.assertIn("git_dir_path is not configured", result["error"])
        clone.assert_not_called()

    def test_tracked_diff_timeout_is_a_structured_sync_failure(self) -> None:
        mirror = make_mirror()
        before_head = "a" * 40
        after_head = "b" * 40
        before = healthy_local_state(mirror, before_head)
        after = healthy_local_state(mirror, after_head)

        def fake_run_local_git(
            _: mirror_manager.MirrorConfig,
            args: list[str],
            **__: object,
        ) -> dict[str, object]:
            if args[0] == "fetch":
                return {"exit_code": 0, "output": "fetched"}
            if args[0] == "rev-parse":
                return {"exit_code": 0, "output": after_head}
            if args[0] in {"merge-base", "merge"}:
                return {"exit_code": 0, "output": "ok"}
            if args[0] == "diff":
                return {
                    "exit_code": mirror_manager.TIMEOUT_EXIT_CODE,
                    "output": "Git command timed out after 20 seconds.",
                    "timed_out": True,
                }
            raise AssertionError(f"Unexpected command: {args}")

        with (
            patch.object(mirror_manager, "get_local_repo_state", side_effect=[before, after]),
            patch.object(mirror_manager, "run_local_git", side_effect=fake_run_local_git),
        ):
            result = mirror_manager.sync_one(mirror)

        self.assertEqual(result["status"], "tracked_diff_failed")
        self.assertEqual(result["before_head"], before_head)
        self.assertEqual(result["after_head"], after_head)
        self.assertEqual(result["changed_tracked_skills"], [])
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["failed_exit_code"], mirror_manager.TIMEOUT_EXIT_CODE)
        self.assertIn("timed out", result["error"])
        self.assertIn("upstream-skill", result["error"])

    def test_real_repositories_clone_with_external_git_dir_and_sync_tracked_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, remote = create_local_remote_fixture(root)
            mirror = mirror_manager.MirrorConfig(
                **{
                    **make_mirror().__dict__,
                    "repo_url": remote.as_posix(),
                    "local_path": root / "mirror-worktree",
                    "git_dir_path": root / "git-metadata" / "mirror.git",
                }
            )

            initialized = mirror_manager.sync_one(mirror)
            self.assertEqual(initialized["status"], "initialized")
            self.assertEqual(initialized["tracked_change_note"], "initial_clone")
            self.assertTrue(mirror.local_path.is_dir())
            self.assertTrue(mirror.git_dir_path.is_dir())
            self.assertTrue((mirror.local_path / ".git").is_file())
            self.assertTrue(initialized["git_dir_matches_registry"])
            self.assertEqual(
                mirror_manager.canonical_path_key(Path(initialized["actual_git_dir_path"])),
                mirror_manager.canonical_path_key(mirror.git_dir_path),
            )

            tracked_file = source / "skills" / "upstream-skill" / "SKILL.md"
            tracked_file.write_text("# v2\n", encoding="utf-8")
            run_real_git(source, "add", ".")
            run_real_git(source, "commit", "-m", "tracked update")
            run_real_git(source, "push", "origin", "main")

            synced = mirror_manager.sync_one(mirror)

        self.assertEqual(synced["status"], "synced")
        self.assertEqual(synced["changed_tracked_skills"], ["upstream-skill"])
        self.assertNotEqual(synced["before_head"], synced["after_head"])

    def test_real_repository_rejects_declared_git_dir_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, remote = create_local_remote_fixture(root)
            worktree = root / "normal-clone"
            run_real_git(None, "clone", "--branch", "main", remote.as_posix(), str(worktree))
            mirror = mirror_manager.MirrorConfig(
                **{
                    **make_mirror().__dict__,
                    "repo_url": remote.as_posix(),
                    "local_path": worktree,
                    "git_dir_path": root / "declared-external.git",
                }
            )

            local = mirror_manager.get_local_repo_state(mirror)
            checked = mirror_manager.check_one(mirror)
            synced = mirror_manager.sync_one(mirror)

        self.assertTrue(local["local_repo_valid"])
        self.assertFalse(local["git_dir_matches_registry"])
        self.assertEqual(checked["status"], "git_dir_mismatch")
        self.assertEqual(synced["status"], "git_dir_mismatch")
        self.assertIn("does not match", synced["error"])

    def test_sync_fetches_once_and_skips_merge_when_already_up_to_date(self) -> None:
        mirror = make_mirror()
        head = "a" * 40
        state = healthy_local_state(mirror, head)
        commands: list[list[str]] = []

        def fake_run_local_git(
            current: mirror_manager.MirrorConfig,
            args: list[str],
            **_: object,
        ) -> dict[str, object]:
            self.assertEqual(current, mirror)
            commands.append(args)
            if args[0] == "fetch":
                return {"exit_code": 0, "output": "fetched"}
            if args[0] == "rev-parse":
                return {"exit_code": 0, "output": head}
            raise AssertionError(f"Unexpected local Git command: {args}")

        with (
            patch.object(mirror_manager, "get_local_repo_state", side_effect=[state, state]),
            patch.object(mirror_manager, "run_local_git", side_effect=fake_run_local_git),
            patch.object(mirror_manager, "summarize_tracked_changes", return_value=([], None)),
        ):
            result = mirror_manager.sync_one(mirror)

        self.assertEqual(result["status"], "already_up_to_date")
        self.assertEqual(sum(command[0] == "fetch" for command in commands), 1)
        self.assertFalse(any(command[0] in {"pull", "merge"} for command in commands))

    def test_fetch_failure_preserves_local_health_and_command_details(self) -> None:
        mirror = make_mirror()
        head = "a" * 40
        state = healthy_local_state(mirror, head)
        failed = {
            "command": "git fetch origin main",
            "exit_code": mirror_manager.TIMEOUT_EXIT_CODE,
            "output": "Git command timed out after 20 seconds.",
            "timed_out": True,
            "timeout_seconds": 20.0,
        }
        with (
            patch.object(mirror_manager, "get_local_repo_state", return_value=state),
            patch.object(mirror_manager, "run_local_git", return_value=failed),
        ):
            result = mirror_manager.sync_one(mirror)

        self.assertEqual(result["status"], "sync_failed")
        self.assertEqual(result["local_head"], head)
        self.assertTrue(result["git_dir_matches_registry"])
        self.assertEqual(result["failed_command"], failed["command"])
        self.assertEqual(result["failed_exit_code"], mirror_manager.TIMEOUT_EXIT_CODE)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["timeout_seconds"], 20.0)

    def test_sync_fetches_once_then_fast_forwards_locally(self) -> None:
        mirror = make_mirror()
        before_head = "a" * 40
        after_head = "b" * 40
        commands: list[list[str]] = []

        def fake_run_local_git(
            current: mirror_manager.MirrorConfig,
            args: list[str],
            **_: object,
        ) -> dict[str, object]:
            self.assertEqual(current, mirror)
            commands.append(args)
            if args[0] == "fetch":
                return {"exit_code": 0, "output": "fetched"}
            if args[0] == "rev-parse":
                return {"exit_code": 0, "output": after_head}
            if args[0] in {"merge-base", "merge"}:
                return {"exit_code": 0, "output": "ok"}
            raise AssertionError(f"Unexpected local Git command: {args}")

        with (
            patch.object(
                mirror_manager,
                "get_local_repo_state",
                side_effect=[
                    healthy_local_state(mirror, before_head),
                    healthy_local_state(mirror, after_head),
                ],
            ),
            patch.object(mirror_manager, "run_local_git", side_effect=fake_run_local_git),
            patch.object(
                mirror_manager,
                "summarize_tracked_changes",
                return_value=(["upstream-skill"], None),
            ),
        ):
            result = mirror_manager.sync_one(mirror)

        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["before_head"], before_head)
        self.assertEqual(result["after_head"], after_head)
        self.assertEqual(sum(command[0] == "fetch" for command in commands), 1)
        self.assertTrue(any(command[:2] == ["merge", "--ff-only"] for command in commands))
        self.assertFalse(any(command[0] == "pull" for command in commands))

    def test_sync_blocks_non_fast_forward_after_single_fetch(self) -> None:
        mirror = make_mirror()
        before_head = "a" * 40
        remote_head = "b" * 40
        commands: list[list[str]] = []

        def fake_run_local_git(
            current: mirror_manager.MirrorConfig,
            args: list[str],
            **_: object,
        ) -> dict[str, object]:
            self.assertEqual(current, mirror)
            commands.append(args)
            if args[0] == "fetch":
                return {"exit_code": 0, "output": "fetched"}
            if args[0] == "rev-parse":
                return {"exit_code": 0, "output": remote_head}
            if args[0] == "merge-base":
                return {"exit_code": 1, "output": ""}
            raise AssertionError(f"Unexpected local Git command: {args}")

        with (
            patch.object(
                mirror_manager,
                "get_local_repo_state",
                return_value=healthy_local_state(mirror, before_head),
            ),
            patch.object(mirror_manager, "run_local_git", side_effect=fake_run_local_git),
        ):
            result = mirror_manager.sync_one(mirror)

        self.assertEqual(result["status"], "sync_failed")
        self.assertIn("not a fast-forward", result["error"])
        self.assertEqual(sum(command[0] == "fetch" for command in commands), 1)
        self.assertFalse(any(command[0] in {"pull", "merge"} for command in commands))

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

    def test_git_dir_path_must_be_absolute_and_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            registry = root / "repo-mirrors.toml"
            registry.write_text(
                current_registry_text(
                    local_path=(root / "relative").as_posix(),
                    git_dir_path="relative/git/example.git",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "git_dir_path must be absolute"):
                mirror_manager.load_registry(registry)

            registry.write_text(
                current_registry_text(
                    "one",
                    local_path=(root / "one").as_posix(),
                    git_dir_path="C:/git-dirs/shared.git",
                )
                + current_registry_text(
                    "two",
                    local_path=(root / "two").as_posix(),
                    git_dir_path="c:/GIT-DIRS/shared.git",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate mirror git_dir_path"):
                mirror_manager.load_registry(registry)

    def test_git_dir_path_rejects_sync_and_skill_runtime_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sync_root = Path(temp_dir) / "BaiduSyncdisk"
            registry = sync_root / ".agents" / "upstream" / "repo-mirrors.toml"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                current_registry_text(
                    local_path=(registry.parent / "example").as_posix(),
                    git_dir_path=(sync_root / "git" / "example.git").as_posix(),
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "outside synchronized root"):
                mirror_manager.load_registry(registry)

            registry = Path(temp_dir) / "repo-mirrors.toml"
            registry.write_text(
                current_registry_text(
                    local_path=(Path(temp_dir) / "example").as_posix(),
                    git_dir_path=(Path.home() / ".codex" / "skills" / "example.git").as_posix(),
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "outside Codex skill runtime"):
                mirror_manager.load_registry(registry)

    def test_existing_legacy_registry_entry_may_omit_git_dir_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "repo-mirrors.toml"
            registry.write_text(
                current_registry_text(
                    local_path=(Path(temp_dir) / "example").as_posix(),
                    include_git_dir=False,
                ),
                encoding="utf-8",
            )

            loaded = mirror_manager.load_registry(registry)

        self.assertIsNone(loaded[0].git_dir_path)


if __name__ == "__main__":
    unittest.main()
