import importlib.util
import sys
import os
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_skill_tree.py"
SPEC = importlib.util.spec_from_file_location("sibling_dependency_audit", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def fixture(tmp_path):
    source = tmp_path / "source"
    skill = source / "lark-doc"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        '---\nname: lark-doc\ndescription: Documents\n---\n'
        '[shared](../lark-shared/SKILL.md)\n'
        '[drive](../lark-drive/SKILL.md)\n'
        '[missing](references/missing.md)\n', encoding="utf-8")
    dependencies = tmp_path / "installed"
    for name in ("lark-shared", "lark-drive"):
        package = dependencies / name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text("# dependency", encoding="utf-8")
    return AUDIT.discover_skill_records(source), dependencies


def test_only_explicit_installed_siblings_resolve(tmp_path):
    records, root = fixture(tmp_path)
    assert len(AUDIT.scan_link_or_path_issues(records)) == 3
    receipts = []
    issues = AUDIT.scan_link_or_path_issues(records, (root,), receipts)
    assert len(issues) == 1 and "references/missing.md" in issues[0]["detail"]
    assert {x["target"] for x in receipts} == {
        "../lark-shared/SKILL.md", "../lark-drive/SKILL.md"}


def test_broken_local_package_is_not_masked(tmp_path):
    records, root = fixture(tmp_path)
    (records[0].path.parent / "lark-shared").mkdir()
    issues = AUDIT.scan_link_or_path_issues(records, (root,))
    assert len(issues) == 2


def test_missing_dependency_and_traversal_remain_unresolved(tmp_path):
    records, root = fixture(tmp_path)
    (root / "lark-drive/SKILL.md").unlink()
    assert len(AUDIT.scan_link_or_path_issues(records, (root,))) == 2
    for target in ("../../installed/lark-shared/SKILL.md", "../lark-shared/references/x.md",
                   "../lark-shared/../lark-drive/SKILL.md", str(root / "lark-shared/SKILL.md")):
        assert AUDIT.resolve_sibling_dependency(records[0], target, (root,)) is None


def symlink_or_skip(link, target, directory=False):
    import pytest
    try:
        os.symlink(target, link, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def test_dependency_symlink_cannot_escape_root(tmp_path):
    records, root = fixture(tmp_path)
    (root / "lark-shared/SKILL.md").unlink()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    symlink_or_skip(root / "lark-shared/SKILL.md", outside)
    assert AUDIT.resolve_sibling_dependency(records[0], "../lark-shared/SKILL.md", (root,)) is None


def test_dangling_local_package_cannot_be_masked(tmp_path):
    records, root = fixture(tmp_path)
    link = records[0].path.parent / "lark-shared"
    symlink_or_skip(link, tmp_path / "not-present", directory=True)
    assert AUDIT.resolve_sibling_dependency(records[0], "../lark-shared/SKILL.md", (root,)) is None


def test_nonexistent_root_does_not_suppress_findings(tmp_path):
    records, _ = fixture(tmp_path)
    assert len(AUDIT.scan_link_or_path_issues(records, (tmp_path / "absent",))) == 3


REVIEW_SPEC = importlib.util.spec_from_file_location(
    "weekly_dependency_review", SCRIPT.with_name("run_weekly_skill_review.py"))
REVIEW = importlib.util.module_from_spec(REVIEW_SPEC)
REVIEW_SPEC.loader.exec_module(REVIEW)


def capture_audits(tmp_path, monkeypatch, **options):
    calls = {}
    def run(name, command, cwd, summary):
        calls[name] = command
        return {}
    monkeypatch.setattr(REVIEW, "run_process", run)
    REVIEW.run_audits(
        agents_root=tmp_path, skills_root=tmp_path / "skills", reports_root=tmp_path / "reports",
        date="2026-11-01", usage_window_start="a", usage_window_end="b",
        usage_timezone="Asia/Shanghai", reuse_reports=options.pop("reuse_reports", False),
        private_skills_root=tmp_path / "private-skills", private_registry=tmp_path / "private.toml",
        **options)
    return calls


def test_weekly_defaults_and_explicit_override_reach_only_hygiene(tmp_path, monkeypatch):
    monkeypatch.setattr(REVIEW.Path, "home", lambda: tmp_path)
    installed = tmp_path / ".cc-switch/skills"
    installed.mkdir(parents=True)
    for roots in (None, (tmp_path / "one", tmp_path / "two"), ()):
        calls = capture_audits(tmp_path, monkeypatch, dependency_roots=roots)
        expected = (installed,) if roots is None else roots
        for name, command in calls.items():
            if name.startswith("hygiene"):
                actual = [command[i + 1] for i, arg in enumerate(command) if arg == "--dependency-root"]
                assert actual == [str(p.resolve()) for p in expected]
            else:
                assert "--dependency-root" not in command


def test_weekly_absent_default_and_reuse_do_not_resolve(tmp_path, monkeypatch):
    monkeypatch.setattr(REVIEW.Path, "home", lambda: tmp_path)
    calls = capture_audits(tmp_path, monkeypatch)
    assert all("--dependency-root" not in cmd for cmd in calls.values())
    assert capture_audits(tmp_path, monkeypatch, reuse_reports=True,
                          dependency_roots=(tmp_path / "installed",)) == {}


def test_weekly_cli_accepts_repeated_roots_and_exclusive_disable():
    import pytest
    args = REVIEW.parse_args(["scan", "--dependency-root", "one", "--dependency-root", "two"])
    assert args.dependency_root == [Path("one"), Path("two")]
    assert REVIEW.parse_args(["scan", "--no-installed-dependencies"]).no_installed_dependencies
    with pytest.raises(SystemExit):
        REVIEW.parse_args(["scan", "--dependency-root", "one", "--no-installed-dependencies"])


def test_scan_entry_forwards_dependency_configuration_without_writing_state(tmp_path, monkeypatch):
    import pytest
    class Captured(Exception):
        pass
    calls = []
    def capture(**kwargs):
        calls.append(kwargs["dependency_roots"])
        raise Captured
    monkeypatch.setattr(REVIEW, "run_audits", capture)
    cases = [([], None), (["--dependency-root", "one", "--dependency-root", "two"],
                          (Path("one"), Path("two"))), (["--no-installed-dependencies"], ())]
    for flags, expected in cases:
        args = REVIEW.parse_args(["scan", "--agents-root", str(tmp_path),
                                  "--state", str(tmp_path / "state.json"), *flags])
        with pytest.raises(Captured):
            REVIEW.scan_command(args)
        assert calls[-1] == expected
        assert not (tmp_path / "state.json").exists()
