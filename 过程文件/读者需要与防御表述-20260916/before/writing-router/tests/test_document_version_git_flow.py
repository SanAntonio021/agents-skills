from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable not found")
    env = os.environ.copy()
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"
    return subprocess.run(
        [git, "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def changed_files(repo: Path, revision: str = "HEAD") -> list[str]:
    output = run(repo, "show", "--pretty=format:", "--name-only", revision).stdout
    return sorted(line for line in output.splitlines() if line)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="document-version-git-flow-") as temp:
        repo = Path(temp).resolve()
        run(repo, "init", "-b", "main")
        run(repo, "config", "user.name", "Version Protection Test")
        run(repo, "config", "user.email", "version-protection@example.invalid")

        (repo / ".gitignore").write_text(
            "*.pptx\n*.pptm\n*.ppam\n~$*\nfigures/generated/\n",
            encoding="utf-8",
        )
        (repo / "proposal.md").write_text("initial manuscript\n", encoding="utf-8")
        (repo / "budget.xlsx").write_bytes(b"initial budget")
        run(repo, "add", "--", ".gitignore", "proposal.md", "budget.xlsx")
        run(repo, "commit", "-m", "test: initial repository")

        (repo / "raw.pptx").write_bytes(b"large presentation placeholder")
        generated = repo / "figures" / "generated"
        generated.mkdir(parents=True)
        (generated / "draft.png").write_bytes(b"generated image placeholder")
        if run(repo, "check-ignore", "--", "raw.pptx").returncode != 0:
            raise AssertionError("PPTX is not ignored")
        if run(repo, "check-ignore", "--", "figures/generated/draft.png").returncode != 0:
            raise AssertionError("generated figure directory is not ignored")

        (repo / "proposal.md").write_text("user changes before agent work\n", encoding="utf-8")
        (repo / "budget.xlsx").write_bytes(b"unrelated staged budget change")
        run(repo, "add", "--", "budget.xlsx")

        run(repo, "commit", "--only", "-m", "文稿：应用场景｜修改前基线", "--", "proposal.md")
        baseline = run(repo, "rev-parse", "HEAD").stdout.strip()
        if changed_files(repo) != ["proposal.md"]:
            raise AssertionError("baseline commit included unrelated files")
        if run(repo, "diff", "--cached", "--name-only").stdout.splitlines() != ["budget.xlsx"]:
            raise AssertionError("unrelated staged file changed after baseline commit")

        (repo / "proposal.md").write_text("verified revised application scenario\n", encoding="utf-8")
        (repo / "appendix.tex").write_text("new tracked appendix\n", encoding="utf-8")
        run(repo, "add", "--", "appendix.tex")
        run(repo, "diff", "--check", "--", "proposal.md")
        run(repo, "diff", "--cached", "--check", "--", "proposal.md", "appendix.tex")
        run(
            repo,
            "commit",
            "--only",
            "-m",
            "文稿：应用场景｜收紧部署条件",
            "--",
            "proposal.md",
            "appendix.tex",
        )
        revised = run(repo, "rev-parse", "HEAD").stdout.strip()
        if changed_files(repo) != ["appendix.tex", "proposal.md"]:
            raise AssertionError("revision commit included unrelated files")
        if run(repo, "diff", "--cached", "--name-only").stdout.splitlines() != ["budget.xlsx"]:
            raise AssertionError("unrelated staged file changed after revision commit")

        tag_name = "milestone/20260712-153045-投稿候选"
        run(repo, "tag", "-a", tag_name, "-m", "里程碑：应用场景｜投稿候选", revised)
        if run(repo, "cat-file", "-t", tag_name).stdout.strip() != "tag":
            raise AssertionError("milestone tag is not annotated")
        if run(repo, "rev-list", "-n", "1", tag_name).stdout.strip() != revised:
            raise AssertionError("milestone tag points to the wrong commit")

        run(repo, "restore", f"--source={baseline}", "--", "proposal.md")
        run(repo, "diff", "--check", "--", "proposal.md")
        run(repo, "commit", "--only", "-m", "文稿：应用场景｜恢复至修改前基线", "--", "proposal.md")
        restored = run(repo, "rev-parse", "HEAD").stdout.strip()
        if restored in {baseline, revised}:
            raise AssertionError("restore did not create a new commit")
        if changed_files(repo) != ["proposal.md"]:
            raise AssertionError("restore commit included unrelated files")
        if (repo / "proposal.md").read_text(encoding="utf-8") != "user changes before agent work\n":
            raise AssertionError("restored manuscript content is incorrect")
        if run(repo, "diff", "--cached", "--name-only").stdout.splitlines() != ["budget.xlsx"]:
            raise AssertionError("unrelated staged file changed after restore commit")
        if run(repo, "remote").stdout.strip():
            raise AssertionError("test repository unexpectedly has a remote")

    print("document version Git flow integration test passed")


if __name__ == "__main__":
    main()
