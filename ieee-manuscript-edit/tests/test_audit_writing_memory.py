from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import audit_writing_memory as audit  # noqa: E402


STYLE_HEADER = "| 不建议 | 建议 | 例外 |\n|---|---|---|\n"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_vocab_root(tmp_path: Path) -> Path:
    root = tmp_path / "vocab"
    write(
        root / "中文" / "通用.md",
        "# 中文通用\n\n" + STYLE_HEADER + "| 赋能 | 用于 | 引用原文 |\n",
    )
    write(
        root / "中文" / "申报书.md",
        "# 中文申报书\n\n"
        + STYLE_HEADER
        + "| 赋能 | 支撑 | 政策标题原文 |\n"
        + "| 不作为……前提/条件 | 直接陈述任务和限制 | 真实限制或合规要求 |\n",
    )
    for name in ("调研报告.md", "论文.md", "审稿回复.md"):
        write(root / "中文" / name, f"# {name}\n\n" + STYLE_HEADER)
    write(
        root / "英文" / "通用.md",
        "# English general\n\n"
        + STYLE_HEADER
        + "| leverage | use; apply | finance or mechanics contexts |\n",
    )
    write(
        root / "英文" / "论文.md",
        "# English paper\n\n"
        + STYLE_HEADER
        + "| robust | stable; reliable | robust control or robust statistics |\n",
    )
    write(root / "英文" / "审稿回复.md", "# English response\n\n" + STYLE_HEADER)
    write(root / "术语.md", "# 术语\n\n| 中文 | 英文 |\n|---|---|\n| 杂散分量 | spurious component |\n")
    write(
        root / "维护.md",
        r"""# 维护

## 待确认

当前无记录。

## 不采用

当前无记录。

## 检查补充

| 条目 | 匹配 |
|---|---|
| 不作为……前提/条件 | `(不作为.{0,20}(前提\|条件))` |
| leverage | `(?i)\bleverag[a-z]*\b` |
| robust | `(?i)\brobust[a-z]*\b` |

## 变更记录

- test fixture
""",
    )
    return root


def parse_args(root: Path, source: Path, language: str, kind: str, output_format: str = "json"):
    return audit.build_parser().parse_args(
        [
            "--file",
            str(source),
            "--vocab-root",
            str(root),
            "--language",
            language,
            "--document-kind",
            kind,
            "--output-format",
            output_format,
        ]
    )


def run_audit(tmp_path: Path, text: str, language: str = "en", kind: str = "paper"):
    root = make_vocab_root(tmp_path)
    source = write(tmp_path / "draft.md", text)
    return audit.audit(parse_args(root, source, language, kind))


def test_complete_language_and_document_kind_routing(tmp_path: Path) -> None:
    root = make_vocab_root(tmp_path)
    for kind in audit.DOCUMENT_KINDS:
        zh_paths = audit.selected_style_paths(root, "zh", kind)
        en_paths = audit.selected_style_paths(root, "en", kind)
        assert zh_paths[0].name == "通用.md"
        assert en_paths[0].name == "通用.md"
        assert len(zh_paths) == (2 if kind in {"proposal", "research-report", "paper", "review-response"} else 1)
        assert len(en_paths) == (2 if kind in {"paper", "review-response"} else 1)


def test_task_rule_overrides_general_rule(tmp_path: Path) -> None:
    root = make_vocab_root(tmp_path)
    source = write(tmp_path / "proposal.md", "本项目赋能产业发展。")
    proposal = audit.audit(parse_args(root, source, "zh", "proposal"))
    general = audit.audit(parse_args(root, source, "zh", "general"))
    assert proposal["matches"][0]["suggestion"] == "支撑"
    assert proposal["matches"][0]["rule_scope"] == "proposal"
    assert general["matches"][0]["suggestion"] == "用于"
    assert general["matches"][0]["rule_scope"] == "general"


def test_proposal_nonliteral_rule_is_routed_and_reported(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "该方向不作为阶段一的前提条件。", language="zh", kind="proposal")
    assert result["status"] == "review_required"
    assert result["matches"][0]["not_recommended"] == "不作为……前提/条件"
    assert result["matches"][0]["exception"] == "真实限制或合规要求"


def test_proposal_rule_is_not_loaded_for_general_chinese(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "该方向不作为阶段一的前提条件。", language="zh", kind="general")
    assert result["status"] == "clean"


def test_english_paper_loads_general_and_paper_morphology(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The leveraged method was robustly validated.")
    assert result["status"] == "review_required"
    assert [item["match"] for item in result["matches"]] == ["leveraged", "robustly"]
    assert {item["rule_scope"] for item in result["matches"]} == {"general", "paper"}


def test_other_english_kinds_load_only_general(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The method is robust but leveraged carefully.", kind="proposal")
    assert [item["not_recommended"] for item in result["matches"]] == ["leverage"]


def test_exception_text_is_always_in_match_report(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The robust controller is tested.")
    assert result["matches"][0]["exception"] == "robust control or robust statistics"


def test_masking_skips_code_urls_paths_latex_citations_quotes_and_references(tmp_path: Path) -> None:
    result = run_audit(
        tmp_path,
        r"""`leverage`

```text
leverage
```

https://example.com/leverage
D:\leverage\file.md
./leverage/file.md
\texttt{leverage}
[@leverage2024]
> leverage is quoted from the source.
“leverage”

## References

leverage in a title
""",
    )
    assert result["status"] == "clean"


def test_terms_are_not_style_rules(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The spurious component is measured.")
    assert result["status"] == "clean"


def test_report_contains_input_and_loaded_rule_hashes(tmp_path: Path) -> None:
    result = run_audit(tmp_path, "The method leverages prior work.")
    assert result["inputs"][0]["sha256"]
    assert len(result["rule_files"]) == 3
    assert all(item["sha256"] for item in result["rule_files"])
    json.dumps(result, ensure_ascii=False)


def test_cli_status_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_vocab_root(tmp_path)
    clean = write(tmp_path / "clean.md", "The method uses prior work.")
    review = write(tmp_path / "review.md", "The method leverages prior work.")

    clean_code = audit.main(["--file", str(clean), "--vocab-root", str(root), "--language", "en", "--document-kind", "paper"])
    clean_result = json.loads(capsys.readouterr().out)
    assert clean_code == 0
    assert clean_result["status"] == "clean"

    review_code = audit.main(["--file", str(review), "--vocab-root", str(root), "--language", "en", "--document-kind", "paper"])
    review_result = json.loads(capsys.readouterr().out)
    assert review_code == 1
    assert review_result["status"] == "review_required"

    error_code = audit.main(["--file", str(clean), "--vocab-root", str(tmp_path / "missing"), "--language", "en", "--document-kind", "paper"])
    error_result = json.loads(capsys.readouterr().out)
    assert error_code == 2
    assert error_result["status"] == "error"


def test_markdown_output_contains_suggestion_and_exception(tmp_path: Path) -> None:
    root = make_vocab_root(tmp_path)
    source = write(tmp_path / "draft.md", "The method leverages prior work.")
    result = audit.audit(parse_args(root, source, "en", "paper", "markdown"))
    report = audit.markdown_report(result)
    assert "use; apply" in report
    assert "finance or mechanics contexts" in report


def test_malformed_style_table_returns_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = make_vocab_root(tmp_path)
    write(root / "英文" / "通用.md", "| 不建议 | 建议 | 例外 | 备注 |\n|---|---|---|---|\n")
    source = write(tmp_path / "draft.md", "Plain text.")
    code = audit.main(["--file", str(source), "--vocab-root", str(root), "--language", "en", "--document-kind", "paper"])
    result = json.loads(capsys.readouterr().out)
    assert code == 2
    assert result["status"] == "error"
    assert "invalid table header" in result["errors"][0]["message"]


def test_escaped_regex_pipe_is_preserved() -> None:
    cells = audit.split_table_line(r"| item | `(?i)(first\|second)` |")
    assert cells == ["item", "(?i)(first|second)"]
    assert audit.compile_pattern(cells[1], cells[0]).search("second")


def test_full_vocab_validation_checks_schema_routes_and_mapping(tmp_path: Path) -> None:
    root = make_vocab_root(tmp_path)
    result = audit.validate_vocab_root(root)
    assert result == {
        "style_files": 8,
        "style_rules": 5,
        "term_rows": 1,
        "match_overrides": 3,
        "routes": 14,
    }


def test_full_vocab_validation_rejects_unmapped_match_rule(tmp_path: Path) -> None:
    root = make_vocab_root(tmp_path)
    maintenance = (root / "维护.md").read_text(encoding="utf-8")
    maintenance = maintenance.replace(
        "| robust | `(?i)\\brobust[a-z]*\\b` |",
        "| robust | `(?i)\\brobust[a-z]*\\b` |\n| missing active row | `missing` |",
    )
    write(root / "维护.md", maintenance)
    with pytest.raises(audit.AuditError, match="without active style rows"):
        audit.validate_vocab_root(root)
