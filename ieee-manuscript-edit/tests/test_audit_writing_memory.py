from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import audit_writing_memory as audit  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def run_audit(
    tmp_path: Path,
    manuscript: str,
    *,
    domain: str = "control theory",
    include_exception: bool = True,
) -> dict:
    source = write(tmp_path / "paper.md", manuscript)
    vocab = write(
        tmp_path / "vocab.md",
        """| 词条 | 改用 | 场景 | 匹配模式 | 例外语境 |
|---|---|---|---|---|
| robust | stable; reliable | 通用/论文 | `(?i)\\brobust\\b` | 控制理论中的正式术语 |
| leverage | use | 通用/论文 | `(?i)\\bleverag[a-z]*\\b` | |
""",
    )
    terms = write(
        tmp_path / "terms.md",
        """| ID | 状态 | 中文术语 | 推荐英文 | 匹配模式 | 适用领域 | 目标期刊 | 章节功能 | 来源 | 用户审阅 | 例外覆盖用户禁用 |
|---|---|---|---|---|---|---|---|---|---|---|
| TERM-1 | 已确认 | 鲁棒控制 | robust control | `(?i)\\brobust control\\b` | control theory | 通用 | all | user-confirmed | 是 | 否 |
""",
    )
    exceptions = tmp_path / "exceptions.md"
    exception_text = """| ID | 状态 | 词条 | 例外模式 | 适用领域 | 目标期刊 | 章节功能 | 来源 | 用户审阅 | 例外覆盖用户禁用 |
|---|---|---|---|---|---|---|---|---|---|
"""
    if include_exception:
        exception_text += "| EXC-1 | 已确认 | robust | `(?i)\\brobust control\\b` | control theory | 通用 | all | user-confirmed | 是 | 是 |\n"
    write(exceptions, exception_text)
    args = audit.build_parser().parse_args(
        [
            "--file",
            str(source),
            "--domain",
            domain,
            "--journal",
            "IEEE control",
            "--section",
            "results",
            "--vocab-table",
            str(vocab),
            "--term-bank",
            str(terms),
            "--exception-table",
            str(exceptions),
        ]
    )
    return audit.audit(args)


def test_user_hard_deny_wins_without_explicit_term_override(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The robust control loop is stable, but leverage is used.", include_exception=False)
    assert result["counts"]["conflicts"] == 1
    assert result["counts"]["violations"] >= 1
    assert result["counts"]["unresolved"] >= 1
    assert result["pass"] is False


def test_structured_exception_requires_explicit_override(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The robust control loop is stable.")
    assert result["counts"]["exceptions"] == 1
    assert result["counts"]["violations"] == 0
    assert result["counts"]["unresolved"] == 0


def test_cross_domain_term_is_unresolved_and_not_applied(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The robust control loop is stable.", domain="THz imaging")
    assert any(item["type"] == "scope_mismatch" for item in result["unresolved"])
    assert result["pass"] is False


def test_candidate_never_becomes_active_rule(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The leverage method is useful.")
    # The active style table catches it; the test ensures the result remains a
    # real violation rather than being silently accepted as a learned choice.
    assert result["counts"]["violations"] == 1


def test_candidate_ledger_is_reported_but_never_applied(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "The preferred phrase is signal-layer.")
    vocab = write(tmp_path / "vocab.md", "| 词条 | 改用 | 场景 | 匹配模式 |\n|---|---|---|---|\n")
    terms = write(tmp_path / "terms.md", "| 状态 | 中文术语 | 推荐英文 | 匹配模式 | 来源 | 用户审阅 |\n|---|---|---|---|---|---|\n")
    candidates = write(
        tmp_path / "candidates.md",
        "| 状态 | 原始表达 | 推荐表达 | 场景 | 匹配模式 |\n|---|---|---|---|---|\n| 候选 | signal-layer | how the signals are defined | 论文 | `(?i)\\bsignal-layer\\b` |\n",
    )
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "methods", "--vocab-table", str(vocab), "--term-bank", str(terms), "--candidate-ledger", str(candidates)]
    )
    result = audit.audit(args)
    assert any(item["type"] == "candidate_not_active" for item in result["unresolved"])
    assert result["counts"]["violations"] == 0


def test_rejected_candidate_reappearing_is_a_violation(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "The manuscript uses spurious signal.")
    vocab = write(tmp_path / "vocab.md", "| 词条 | 改用 | 场景 | 匹配模式 |\n|---|---|---|---|\n")
    terms = write(tmp_path / "terms.md", "| 状态 | 中文术语 | 推荐英文 | 匹配模式 | 来源 | 用户审阅 |\n|---|---|---|---|---|---|\n")
    candidates = write(
        tmp_path / "candidates.md",
        "| 状态 | 原始表达 | 推荐表达 | 场景 | 匹配模式 |\n|---|---|---|---|---|\n| 已拒绝 | spurious signal | spurious component | 论文 | `(?i)\\bspurious signal\\b` |\n",
    )
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "results", "--vocab-table", str(vocab), "--term-bank", str(terms), "--candidate-ledger", str(candidates)]
    )
    result = audit.audit(args)
    assert result["counts"]["violations"] == 1
    assert result["violations"][0]["reason"] == "previously rejected candidate reappeared"


def test_rejected_candidate_synonym_is_a_violation(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "The manuscript uses a spurious component.")
    vocab = write(tmp_path / "vocab.md", "| 词条 | 改用 | 场景 | 匹配模式 |\n|---|---|---|---|\n")
    terms = write(tmp_path / "terms.md", "| 状态 | 中文术语 | 推荐英文 | 匹配模式 | 来源 | 用户审阅 |\n|---|---|---|---|---|---|\n")
    candidates = write(
        tmp_path / "candidates.md",
        "| 状态 | 原始表达 | 推荐表达 | 匹配模式 | 场景 | 拒绝理由 |\n|---|---|---|---|---|---|\n| 已拒绝 | spurious signal | noise floor | `(?i)\\bspurious (signal|component)s?\\b` | 论文 | 用户要求避免混用术语 |\n",
    )
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "results", "--vocab-table", str(vocab), "--term-bank", str(terms), "--candidate-ledger", str(candidates)]
    )
    result = audit.audit(args)
    assert result["counts"]["violations"] == 1
    assert result["violations"][0]["match"] == "spurious component"


def test_rejected_candidate_without_reason_fails_schema(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "No rejected wording appears here.")
    vocab = write(tmp_path / "vocab.md", "| 词条 | 改用 | 场景 | 匹配模式 |\n|---|---|---|---|\n")
    terms = write(tmp_path / "terms.md", "| 状态 | 中文术语 | 推荐英文 | 匹配模式 | 来源 | 用户审阅 |\n|---|---|---|---|---|---|\n")
    candidates = write(
        tmp_path / "candidates.md",
        "| 状态 | 原始表达 | 推荐表达 | 匹配模式 | 场景 | 拒绝理由 |\n|---|---|---|---|---|---|\n| 已拒绝 | spurious signal | noise floor | `(?i)\\bspurious signal\\b` | 论文 | |\n",
    )
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "results", "--vocab-table", str(vocab), "--term-bank", str(terms), "--candidate-ledger", str(candidates)]
    )
    result = audit.audit(args)
    assert any(item["type"] == "rejected_candidate_missing_reason" for item in result["schema_errors"])
    assert result["pass"] is False


def test_confirmed_candidate_requires_verified_active_migration(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "The method is stated plainly.")
    vocab = write(tmp_path / "vocab.md", "| 词条 | 改用 | 场景 | 匹配模式 |\n|---|---|---|---|\n")
    terms = write(tmp_path / "terms.md", "| 状态 | 中文术语 | 推荐英文 | 匹配模式 | 来源 | 用户审阅 |\n|---|---|---|---|---|---|\n")
    candidates = write(
        tmp_path / "candidates.md",
        "| 状态 | 原始表达 | 推荐表达 | 匹配模式 | 场景 | 用户确认 | 迁入位置 |\n|---|---|---|---|---|---|---|\n| 已确认 | signal-layer | signal definition | `(?i)\\bsignal-layer\\b` | 论文 | 是 | vocab-full.md |\n",
    )
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "methods", "--vocab-table", str(vocab), "--term-bank", str(terms), "--candidate-ledger", str(candidates)]
    )
    result = audit.audit(args)
    assert any(item["type"] == "confirmed_candidate_not_migrated" for item in result["schema_errors"])
    assert result["pass"] is False


def test_missing_required_rule_file_fails_closed(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "The method is stable.")
    terms = write(tmp_path / "terms.md", "| 状态 | 中文术语 | 推荐英文 | 匹配模式 | 来源 | 用户审阅 |\n|---|---|---|---|---|---|\n")
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "methods", "--vocab-table", str(tmp_path / "missing-vocab.md"), "--term-bank", str(terms)]
    )
    try:
        audit.audit(args)
    except ValueError as exc:
        assert "vocab_table" in str(exc)
    else:
        raise AssertionError("missing required rule file must not pass")


def test_parser_exposes_no_report_file_output_option() -> None:
    parser = audit.build_parser()
    assert "--report" not in parser.format_help()


def test_markdown_table_parser_preserves_regex_backslashes_and_alternation() -> None:
    text = "| status | source_form | match_pattern |\n|---|---|---|\n| rejected | spurious signal | `(?i)\\bspurious (signal|component)s?\\b` |\n"
    headers, cells = next(audit.table_rows(text))
    rule = audit.rule_from_row(headers, cells, "candidate", 1)
    assert rule is not None
    assert rule.pattern == r"(?i)\bspurious (signal|component)s?\b"
    assert [item.group(0) for item in audit.match_rule(rule, "spurious component")] == ["spurious component"]


def test_markdown_table_parser_preserves_escaped_regex_pipe() -> None:
    text = "| source_form | match_pattern |\n|---|---|\n| experiment day | `(?i)(experiment[- ]day|day's \\w+ conditions)` |\n"
    headers, cells = next(audit.table_rows(text))
    rule = audit.rule_from_row(headers, cells, "style", 1)
    assert rule is not None
    assert rule.pattern == r"(?i)(experiment[- ]day|day's \w+ conditions)"
    assert [item.group(0) for item in audit.match_rule(rule, "the day's rain conditions")] == ["day's rain conditions"]


def test_confirmed_candidate_with_matching_active_rule_is_migrated(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "The method is stated plainly.")
    vocab = write(
        tmp_path / "vocab.md",
        "| source_form | preferred_form | scope | match_pattern |\n|---|---|---|---|\n| signal layer | signal definition | paper | `(?i)\\bsignal[ -]layer\\b` |\n",
    )
    terms = write(tmp_path / "terms.md", "| status | source_form | preferred_form | match_pattern | source | user_reviewed |\n|---|---|---|---|---|---|\n")
    candidates = write(
        tmp_path / "candidates.md",
        "| status | candidate_type | source_form | preferred_form | match_pattern | scope | source | user_reviewed | migrated_to |\n|---|---|---|---|---|---|---|---|---|\n| confirmed | style | signal layer | signal definition | `(?i)\\bsignal[ -]layer\\b` | paper | user-confirmed | yes | vocab-full.md |\n",
    )
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "methods", "--vocab-table", str(vocab), "--term-bank", str(terms), "--candidate-ledger", str(candidates)]
    )
    result = audit.audit(args)
    assert not result["schema_errors"]
    assert result["pass"] is True


def test_confirmed_candidate_cannot_claim_the_wrong_active_bank(tmp_path: Path) -> None:
    source = write(tmp_path / "paper.md", "The method is stated plainly.")
    vocab = write(
        tmp_path / "vocab.md",
        "| source_form | preferred_form | scope | match_pattern |\n|---|---|---|---|\n| signal layer | signal definition | paper | `(?i)\\bsignal[ -]layer\\b` |\n",
    )
    terms = write(tmp_path / "terms.md", "| status | source_form | preferred_form | match_pattern | source | user_reviewed |\n|---|---|---|---|---|---|\n")
    candidates = write(
        tmp_path / "candidates.md",
        "| status | candidate_type | source_form | preferred_form | match_pattern | scope | source | user_reviewed | migrated_to |\n|---|---|---|---|---|---|---|---|---|\n| confirmed | term | signal layer | signal definition | `(?i)\\bsignal[ -]layer\\b` | paper | user-confirmed | yes | scientific-terminology-bank.md |\n",
    )
    args = audit.build_parser().parse_args(
        ["--file", str(source), "--domain", "THz communication", "--journal", "IEEE", "--section", "methods", "--vocab-table", str(vocab), "--term-bank", str(terms), "--candidate-ledger", str(candidates)]
    )
    result = audit.audit(args)
    assert any(item["type"] == "confirmed_candidate_not_migrated" for item in result["schema_errors"])
    assert result["pass"] is False


def test_masking_skips_latex_commands_and_references(tmp_path: Path) -> None:
    result = run_audit(
        tmp_path,
        r"""The method uses \texttt{leverage} only in code.

## References

leverage should not be audited in this bibliography section.
""",
    )
    assert result["counts"]["violations"] == 0


def test_report_has_input_and_rule_hashes(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The robust control loop is stable.")
    assert result["inputs"][0]["sha256"]
    assert all(item["sha256"] for item in result["rule_files"])
    json.dumps(result, ensure_ascii=False)
