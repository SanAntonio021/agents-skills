from __future__ import annotations

import json
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]


def test_office_security_boundary_is_canonical_and_runtime_paths_are_not_named() -> None:
    boundary = SKILLS_ROOT / "docx" / "references" / "office-security-boundary.md"
    raw = boundary.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    for fragment in (
        "unique `UserInstallation`",
        "Direct launch of `soffice`",
        "standing task authorization",
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


def test_word_export_requires_an_explicit_format_confirmation() -> None:
    contract = (
        SKILLS_ROOT / "writing-router" / "references" / "markdown-docx-contract.md"
    ).read_text(
        encoding="utf-8"
    )
    assert "推荐一套" in contract
    assert "等待用户确认或提出调整要求后再导出" in contract
    assert "所有导出均套用模板" in contract
