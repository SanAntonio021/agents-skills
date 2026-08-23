from __future__ import annotations

import json
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]


def test_shared_markdown_docx_contract_is_referenced_by_content_skills() -> None:
    contract = SKILLS_ROOT / "writing-router" / "references" / "markdown-docx-contract.md"
    assert contract.is_file()
    text = contract.read_text(encoding="utf-8")
    for fragment in (
        "content_status",
        "content_open_items",
        "content_confirmed",
        "STATIC_PASS",
        "LO_RENDER_PASS",
        "NATIVE_OPEN_PASS",
        "NATIVE_RENDER_PASS",
        "OUTPUT_COLLISION",
        "OfficeCLI",
        "MCP",
    ):
        assert fragment in text

    for skill_name in ("writing-router", "research-report", "meeting-notes", "ieee-manuscript-edit", "project-writing"):
        skill_text = (SKILLS_ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert "markdown-docx-contract.md" in skill_text


def test_office_security_boundary_is_canonical_and_runtime_paths_are_not_named() -> None:
    boundary = SKILLS_ROOT / "docs" / "office-security-boundary.md"
    raw = boundary.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    for fragment in (
        "unique `UserInstallation`",
        "Direct launch of `soffice`",
        "允许本次 Word 验收",
        "UNSAFE_OFFICE_PROCESS",
        "%TEMP%/codex-docx-gates",
        "Reject symbolic links",
    ):
        assert fragment in text


def test_mcp_trial_is_documented_as_non_production() -> None:
    trial = (SKILLS_ROOT / "docx" / "references" / "office-mcp-trial.md").read_text(encoding="utf-8")
    assert "不进入生产依赖" in trial
    assert "MCP_NOT_ADMITTED" in trial
    assert "MCP_NONDETERMINISTIC" in trial
    assert "三次" in trial
