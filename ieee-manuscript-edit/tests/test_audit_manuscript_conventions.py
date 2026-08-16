from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "audit_manuscript_conventions.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))

import audit_manuscript_conventions as audit  # noqa: E402


REQUIRED_REPORT_KEYS = {
    "schema_version",
    "status",
    "input",
    "scopes",
    "safe_findings",
    "review_candidates",
    "protected_qualifiers",
    "unresolved",
    "counts",
    "error",
}
REQUIRED_FINDING_KEYS = {
    "rule_id",
    "check",
    "path",
    "line",
    "scope",
    "message",
    "evidence",
}


def write_text(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8", newline="")
    return path


def findings(report: dict[str, object], category: str, rule_id: str) -> list[dict[str, object]]:
    return [item for item in report[category] if item["rule_id"] == rule_id]


def run_cli(path: Path, output_format: str = "json") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(SCRIPT_PATH),
            "--input",
            str(path),
            "--format",
            output_format,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_markdown_uses_independent_abstract_body_and_caption_scopes(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.md",
        """# Abstract

A multiple-input multiple-output (MIMO) link was measured. MIMO carried two streams.

# Introduction

The MIMO link used equal bandwidth for both streams.

![MIMO performance under the measured 1 km link condition with received power in dBm.](figure.png)
""",
    )
    report = audit.audit_path(source)

    scopes = {(item["id"], item["kind"]) for item in report["scopes"]}
    assert ("abstract", "abstract") in scopes
    assert ("body", "body") in scopes
    assert ("figure_caption:1", "caption") in scopes
    repairs = findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")
    assert {item["scope"] for item in repairs} == {"body", "figure_caption:1"}
    assert all(item["replacement"] == "multiple-input multiple-output (MIMO)" for item in repairs)


def test_abstract_single_use_acronym_is_a_safe_removal(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.md",
        "# Abstract\n\nBit error rate (BER) was measured over the link.\n\n# Results\n\nThe link remained stable.\n",
    )
    report = audit.audit_path(source)

    item = findings(report, "safe_findings", "ACR_ABSTRACT_SINGLE_USE")[0]
    assert item["replacement"] == "Bit error rate"
    assert item["span"]["start_line"] == 3


def test_partial_expansion_conflict_and_exempt_allowlist_are_conservative(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.md",
        """# Abstract

An IQ multiple-input multiple-output (IQ-MIMO) link was tested.

# Introduction

Radio frequency (RF) hardware was used. A resonant frequency (RF) was also calculated.
IEEE PDF records for the 5G setup and S1 were retained.
""",
    )
    report = audit.audit_path(source)

    assert findings(report, "review_candidates", "ACR_PARTIAL_EXPANSION")
    assert findings(report, "unresolved", "ACR_CONFLICTING_MAPPING")
    evidence = " ".join(item["evidence"] for item in report["review_candidates"])
    assert "IEEE" not in evidence
    assert "PDF" not in evidence
    assert "S1" not in evidence


def test_unbound_full_form_is_review_only(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.md",
        "The arbitrary waveform generator supplied the signal. The AWG output was measured.\n",
    )
    report = audit.audit_path(source)

    assert findings(report, "review_candidates", "ACR_FULL_FORM_UNBOUND")
    assert not findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")


def test_caption_checks_distinguish_sparse_and_self_contained_examples(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.md",
        """Fig. 1. (a) Setup; (b) output.

Fig. 2. Measured bit error rate versus received power for the two 1 km link states. Circles and squares denote the two streams, respectively; whiskers denote the measured minimum and maximum, and the dashed line marks the threshold.
""",
    )
    report = audit.audit_path(source)

    short = findings(report, "review_candidates", "CAPTION_TOO_SHORT")
    panels = findings(report, "review_candidates", "CAPTION_PANEL_UNEXPLAINED")
    statistics = findings(report, "review_candidates", "CAPTION_STATISTIC_UNDEFINED")
    assert len(short) == 1 and short[0]["scope"] == "caption:1"
    assert len(panels) == 1 and panels[0]["scope"] == "caption:1"
    assert statistics == []


def test_defensive_meta_language_is_review_only_and_qualifiers_are_protected(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.md",
        """# Results

It should be noted that the following discussion focuses on the weaker stream. Fig. 2 shows the results. Under the tested conditions, the comparison benchmark retained the same occupied bandwidth. The error bars represent confidence intervals.
""",
    )
    report = audit.audit_path(source)

    assert len(findings(report, "review_candidates", "LANG_DEFENSIVE_OR_META")) == 3
    protected = findings(report, "protected_qualifiers", "LANG_SCIENTIFIC_QUALIFIER")
    assert {item["evidence"].lower() for item in protected} >= {
        "under the tested conditions",
        "comparison benchmark",
        "error bars",
        "confidence intervals",
    }
    assert all("replacement" not in item and "span" not in item for item in protected)


def test_fixed_indirect_negatives_report_but_standalone_without_does_not(
    tmp_path: Path,
) -> None:
    cases = {
        "by-no-means.md": ("By no means was the calibration complete.\n", True),
        "standalone-without.md": ("The receiver operated without calibration.\n", False),
        "not-without.md": ("The method is not without limitations.\n", True),
        "not-unlikely.md": ("The observed trend is not unlikely.\n", True),
        "ruled-out.md": ("The calibration error cannot be ruled out.\n", True),
    }
    for name, (content, expected) in cases.items():
        report = audit.audit_path(write_text(tmp_path, name, content))
        items = findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
        assert bool(items) is expected, name
        if not expected:
            continue
        assert len(items) == 1
        assert items[0]["check"] == "negative_construction"
        assert "[fixed_indirect]" in items[0]["evidence"]
        assert content.strip() in items[0]["evidence"]
        assert "span" not in items[0] and "replacement" not in items[0]


def test_not_only_pair_masks_only_the_pairing_not(tmp_path: Path) -> None:
    single = write_text(
        tmp_path,
        "not-only-single.md",
        "Not only did the method not improve BER, but it also increased EVM.\n",
    )
    assert not findings(
        audit.audit_path(single), "review_candidates", "LANG_NEGATION_CHAIN"
    )

    repeated = write_text(
        tmp_path,
        "not-only-repeated.md",
        "Not only did the method not improve BER, but it also did not reduce EVM.\n",
    )
    items = findings(
        audit.audit_path(repeated), "review_candidates", "LANG_NEGATION_CHAIN"
    )
    assert len(items) == 1
    evidence = items[0]["evidence"].lower()
    assert evidence.count("[atomic]") == 2
    assert '"not" [atomic]' in evidence
    assert '"did not" [atomic]' in evidence
    assert '"not only"' not in evidence

    long_pair = write_text(
        tmp_path,
        "not-only-long-pair.md",
        "Not only did the method not improve BER, but the newly proposed adaptive receiver also increased EVM.\n",
    )
    assert not findings(
        audit.audit_path(long_pair), "review_candidates", "LANG_NEGATION_CHAIN"
    )


def test_sentence_terminators_before_closing_quotes_do_not_merge_units(
    tmp_path: Path,
) -> None:
    quoted_chain = write_text(
        tmp_path,
        "quoted-chain.md",
        'The reviewer wrote, "The receiver did not operate without calibration."\n',
    )
    items = findings(
        audit.audit_path(quoted_chain), "review_candidates", "LANG_NEGATION_CHAIN"
    )
    assert len(items) == 1
    assert items[0]["evidence"].startswith(
        'Sentence: The reviewer wrote, "The receiver did not operate without calibration."'
    )

    separate_list_sentences = write_text(
        tmp_path,
        "quoted-list.md",
        '- "The receiver did not operate." "No link was lost."\n',
    )
    assert not findings(
        audit.audit_path(separate_list_sentences),
        "review_candidates",
        "LANG_NEGATION_CHAIN",
    )


def test_coordination_and_nonadjacent_not_without_are_counted_conservatively(
    tmp_path: Path,
) -> None:
    coordination_only = write_text(
        tmp_path,
        "coordination-only.md",
        "Neither the receiver nor the transmitter changed state.\n",
    )
    assert not findings(
        audit.audit_path(coordination_only),
        "review_candidates",
        "LANG_NEGATION_CHAIN",
    )

    coordination_plus_negative = write_text(
        tmp_path,
        "coordination-plus-negative.md",
        "Neither the receiver nor the transmitter did not change state.\n",
    )
    item = findings(
        audit.audit_path(coordination_plus_negative),
        "review_candidates",
        "LANG_NEGATION_CHAIN",
    )[0]
    assert '"Neither ... nor" [coordination]' in item["evidence"]
    assert '"did not" [atomic]' in item["evidence"]

    negative_inside_coordination = write_text(
        tmp_path,
        "coordination-inside-negative.md",
        "Neither did the receiver not change nor did the transmitter change state.\n",
    )
    item = findings(
        audit.audit_path(negative_inside_coordination),
        "review_candidates",
        "LANG_NEGATION_CHAIN",
    )[0]
    assert '"Neither ... nor" [coordination]' in item["evidence"]
    assert '"not" [atomic]' in item["evidence"]

    separated = write_text(
        tmp_path,
        "not-entirely-without.md",
        "The method is not entirely without limitations.\n",
    )
    item = findings(
        audit.audit_path(separated), "review_candidates", "LANG_NEGATION_CHAIN"
    )[0]
    assert item["evidence"].count("[atomic]") == 2
    assert "[fixed_indirect]" not in item["evidence"]


def test_number_abbreviations_and_single_scientific_negatives_do_not_report(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "single-negatives.md",
        """No.3 did not improve.
No. A1 was not selected.
No. III cannot confirm the trend.
No packet loss was observed.
The difference was not statistically significant.
The available data cannot confirm the mechanism.
The receiver operated without calibration.
""",
    )
    report = audit.audit_path(source)
    assert not findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
    for sentence in (
        "No.3 did not improve.",
        "No. A1 was not selected.",
        "No. III cannot confirm the trend.",
    ):
        hits = audit.find_negative_hits(sentence)
        assert len(hits) == 1
        assert all(hit.text.lower() != "no" for hit in hits)


def test_long_fail_to_decimal_and_nested_coordination_are_counted_once(
    tmp_path: Path,
) -> None:
    long_fail = audit.audit_path(
        write_text(
            tmp_path,
            "long-fail.md",
            "The receiver failed repeatedly under all tested conditions to reacquire the signal without calibration.\n",
        )
    )
    fail_items = findings(long_fail, "review_candidates", "LANG_NEGATION_CHAIN")
    assert len(fail_items) == 1
    assert '"failed ... to" [atomic]' in fail_items[0]["evidence"]
    assert '"without" [atomic]' in fail_items[0]["evidence"]

    decimal = audit.audit_path(
        write_text(
            tmp_path,
            "decimal.md",
            "The receiver did not reach 0.1 dB without calibration.\n",
        )
    )
    assert len(findings(decimal, "review_candidates", "LANG_NEGATION_CHAIN")) == 1

    nested_hits = audit.find_negative_hits(
        "Neither neither the receiver nor the transmitter nor the repeater changed state."
    )
    assert [(hit.text.lower(), hit.category) for hit in nested_hits] == [
        ("neither ... nor", "coordination"),
        ("neither ... nor", "coordination"),
    ]


def test_markdown_setext_headings_references_and_abstract_scope_are_supported(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "setext.md",
        """Abstract
========
Multiple-input multiple-output (MIMO) was measured. MIMO carried two streams.

Results
-------
The receiver did not operate without calibration.

References
----------
By no means should this title be audited.
""",
    )
    report = audit.audit_path(source)
    assert {item["kind"] for item in report["scopes"]} >= {"abstract", "body"}
    items = findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
    assert len(items) == 1
    assert items[0]["line"] == 7


def test_markdown_panel_caption_emphasis_and_lazy_list_continuation(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "markdown-boundaries.md",
        """Fig. 1(a). The method is not without limitations

_The receiver did not operate without calibration._
**The receiver did not operate without calibration.**

- The receiver did not operate
without calibration
""",
    )
    report = audit.audit_path(source)
    items = findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
    assert len(items) == 4
    assert {item["scope"] for item in items} == {"body", "caption:1"}
    assert sum(item["scope"] == "caption:1" for item in items) == 1


def test_markdown_raw_html_blocks_are_not_audited(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "raw-html.md",
        """<table>
<tr><td>By no means should not be audited.</td></tr>
</table>
<code>The method is not without limitations.</code>
<h1>Not without title</h1>
""",
    )
    report = audit.audit_path(source)
    assert not findings(report, "review_candidates", "LANG_NEGATION_CHAIN")


def test_latex_heading_table_inline_code_and_decimal_boundaries(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "latex-boundaries.tex",
        r"""\begin{document}
\paragraph{Not without limitations}
\subparagraph{By no means title}
\begin{sidewaystable}
By no means should not be audited.
\end{sidewaystable}
\lstinline|The method is not without limitations.| text.
\mintinline{python}|The method is not without limitations.| text.
The receiver did not reach 0.1 dB without calibration.
\caption{The receiver did not reach 0.1 dB without calibration.}
\end{document}
""",
    )
    report = audit.audit_path(source)
    items = findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
    assert {item["scope"] for item in items} == {"body", "caption:1"}
    assert len(items) == 2
    assert not findings(report, "unresolved", "LATEX_UNCLOSED_INLINE_VERBATIM")


def test_unclosed_latex_lstinline_masks_the_remainder_and_is_unresolved(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "unclosed-lstinline.tex",
        r"""\begin{document}
\lstinline|The method is not without limitations.
The receiver did not operate without calibration.
\end{document}
""",
    )
    report = audit.audit_path(source)
    assert findings(report, "unresolved", "LATEX_UNCLOSED_INLINE_VERBATIM")
    items = findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
    assert len(items) == 1
    assert "did not" in items[0]["evidence"]


def test_unterminated_markdown_captions_and_list_items_are_sentence_units(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "unterminated.md",
        """# Results

The receiver did not operate without calibration

- The receiver did not operate without calibration

Fig. 1. The method is not without limitations
""",
    )
    report = audit.audit_path(source)
    items = findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
    assert len(items) == 2
    assert {item["scope"] for item in items} == {"body", "caption:1"}
    assert {item["line"] for item in items} == {5, 7}


def test_unterminated_latex_caption_and_item_are_sentence_units(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "unterminated.tex",
        r"""\begin{document}
\begin{itemize}
\item The receiver did not operate without calibration
\end{itemize}
\begin{figure}
\caption{The method is not without limitations}
\end{figure}
\end{document}
""",
    )
    report = audit.audit_path(source)
    items = findings(report, "review_candidates", "LANG_NEGATION_CHAIN")
    assert len(items) == 2
    assert {item["scope"] for item in items} == {"body", "caption:1"}
    assert {item["line"] for item in items} == {3, 6}


def test_markdown_negation_audit_excludes_nonprose_regions(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "masked-regions.md",
        """# Not without a defensive title

The measured link remained stable.

| Condition | Statement |
| --- | --- |
| A | not without calibration |

`not without inline code` and $x \ne 0$ were recorded.

<!-- By no means should this comment be audited. -->

```text
The method is not without limitations.
```

# References

By no means should this title be audited.
""",
    )
    report = audit.audit_path(source)
    assert not findings(report, "review_candidates", "LANG_NEGATION_CHAIN")


def test_latex_negation_audit_excludes_nonprose_regions(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "masked-regions.tex",
        r"""\title{A Method That Is Not Without Limitations}
\begin{document}
\section{Not Without a Defensive Title}
The measured link remained stable.
\begin{table}
\begin{tabular}{cc}
A & not without calibration \\
\end{tabular}
\end{table}
\begin{equation}
not + without = 0
\end{equation}
% By no means should this comment be audited.
\begin{verbatim}
The method is not without limitations.
\end{verbatim}
\begin{thebibliography}{1}
By no means should this title be audited.
\end{thebibliography}
\end{document}
""",
    )
    report = audit.audit_path(source)
    assert not findings(report, "review_candidates", "LANG_NEGATION_CHAIN")


def test_negation_chain_merges_hits_and_preserves_complete_sentence_evidence(
    tmp_path: Path,
) -> None:
    sentence = (
        "The receiver did not complete the deliberately extended calibration sequence "
        "that was used to verify every branch of the measurement pipeline, and the "
        "recorded data never recovered without the final reference marker."
    )
    source = write_text(tmp_path, "complete-evidence.md", sentence + "\n")
    item = findings(
        audit.audit_path(source), "review_candidates", "LANG_NEGATION_CHAIN"
    )[0]
    assert len(findings(
        audit.audit_path(source), "review_candidates", "LANG_NEGATION_CHAIN"
    )) == 1
    assert sentence in item["evidence"]
    assert item["evidence"].endswith(
        '"did not" [atomic]; "never" [atomic]; "without" [atomic]'
    )
    assert "..." not in item["evidence"]


def test_only_adjacent_exact_body_duplicates_are_safe(tmp_path: Path) -> None:
    repeated = "The measured link retained the target bit error rate under all tested powers."
    source = write_text(
        tmp_path,
        "paper.md",
        f"""# Abstract

{repeated} {repeated}

# Results

{repeated} {repeated}

The intervening sentence reports a separate measurement condition.

{repeated}

Fig. 1. {repeated}
""",
    )
    report = audit.audit_path(source)

    safe = findings(report, "safe_findings", "REPETITION_ADJACENT_EXACT")
    review = findings(report, "review_candidates", "REPETITION_POTENTIAL_CLUSTER")
    assert len(safe) == 1
    assert safe[0]["scope"] == "body"
    assert safe[0]["replacement"] == ""
    assert review
    assert all(item["scope"] != "caption:1" for item in review)


def test_latex_masks_comments_and_verbatim_and_parses_nested_multiline_caption(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.tex",
        r"""% \input{ignored}
\begin{verbatim}
\include{ignored}
\caption{ignored}
\end{verbatim}
\input{section}
\include {appendix}
\caption[Short entry]{Measured {bit error rate} versus
received power for two streams; circles denote stream one and squares denote stream two.}
""",
    )
    report = audit.audit_path(source)

    captions = [item for item in report["scopes"] if item["kind"] == "caption"]
    external = findings(report, "unresolved", "LATEX_EXTERNAL_FILE")
    assert len(captions) == 1
    assert len(external) == 2
    assert all("ignored" not in item["evidence"] for item in external)


def test_latex_custom_caption_macro_is_unresolved_not_parsed_as_caption(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.tex",
        r"""\newcommand{\mycap}[1]{\caption{#1}}
\mycap{Custom result caption}
\mycaption{Another custom result caption}
""",
    )
    report = audit.audit_path(source)

    assert findings(report, "unresolved", "LATEX_CUSTOM_CAPTION")
    assert not [item for item in report["scopes"] if item["kind"] == "caption"]


def test_unbalanced_latex_caption_is_unresolved(tmp_path: Path) -> None:
    source = write_text(tmp_path, "paper.tex", "\\caption{Measured result with {nested text}.\n")
    report = audit.audit_path(source)

    assert report["status"] == "has_findings"
    assert findings(report, "unresolved", "LATEX_UNBALANCED_CAPTION")


def test_non_utf8_input_returns_fixed_parse_error_schema_and_exit_two(tmp_path: Path) -> None:
    source = tmp_path / "paper.md"
    source.write_bytes(b"valid prefix\n\xff\xfe")

    completed = run_cli(source)
    report = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert set(report) == REQUIRED_REPORT_KEYS
    assert report["status"] == "parse_error"
    assert report["error"]["code"] == "invalid_utf8"


def test_json_schema_sorting_and_cli_output_are_stable_and_read_only(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "paper.md",
        "# Results\n\nIt can be seen that RF remains undefined.\n\nFig. 1. RF result.\n",
    )
    before = source.read_bytes()
    first = run_cli(source)
    second = run_cli(source)
    report = json.loads(first.stdout)

    assert first.returncode == 1
    assert first.stdout == second.stdout
    assert source.read_bytes() == before
    assert set(report) == REQUIRED_REPORT_KEYS
    for category in ("safe_findings", "review_candidates", "protected_qualifiers", "unresolved"):
        for item in report[category]:
            assert REQUIRED_FINDING_KEYS <= set(item)
            if category != "safe_findings":
                assert "span" not in item and "replacement" not in item
        assert report[category] == sorted(
            report[category],
            key=lambda item: (item["path"].lower(), item["line"], item["rule_id"], item["scope"]),
        )


def test_clean_and_markdown_cli_contract(tmp_path: Path) -> None:
    clean_source = write_text(
        tmp_path,
        "clean.md",
        "The measured link remained stable throughout the experiment.\n",
    )
    clean = run_cli(clean_source)
    rendered = run_cli(clean_source, "markdown")

    assert clean.returncode == 0
    assert json.loads(clean.stdout)["status"] == "clean"
    assert rendered.returncode == 0
    for heading in ("## Safe Findings", "## Review Candidates", "## Protected Qualifiers", "## Unresolved"):
        assert heading in rendered.stdout
    assert f"- Input: `{clean_source.resolve()}`" in rendered.stdout


def test_formatted_explicit_mapping_produces_well_formed_replacements(tmp_path: Path) -> None:
    markdown_source = write_text(
        tmp_path,
        "formatted.md",
        "# Abstract\n\n*multiple-input multiple-output* (MIMO) was evaluated.\n",
    )
    markdown_report = audit.audit_path(markdown_source)
    abstract_repair = findings(
        markdown_report, "safe_findings", "ACR_ABSTRACT_SINGLE_USE"
    )[0]
    assert abstract_repair["replacement"] == "*multiple-input multiple-output*"

    partial_source = write_text(
        tmp_path,
        "partial-format.md",
        "# Abstract\n\n*multiple-input* multiple-output (MIMO) was evaluated.\n",
    )
    partial_report = audit.audit_path(partial_source)
    partial_repair = findings(
        partial_report, "safe_findings", "ACR_ABSTRACT_SINGLE_USE"
    )[0]
    assert partial_repair["replacement"] == "*multiple-input* multiple-output"

    trailing_format = write_text(
        tmp_path,
        "trailing-format.md",
        "# Abstract\n\nMultiple-input **multiple-output** (MIMO) was evaluated.\n",
    )
    trailing_report = audit.audit_path(trailing_format)
    assert not findings(trailing_report, "safe_findings", "ACR_ABSTRACT_SINGLE_USE")
    assert findings(trailing_report, "review_candidates", "ACR_FORMATTED_DEFINITION_REVIEW")

    latex_source = write_text(
        tmp_path,
        "formatted.tex",
        r"""\begin{document}
\begin{abstract}
\emph{multiple-input multiple-output} (MIMO) was evaluated. MIMO carried two streams.
\end{abstract}
\section{Results}
MIMO retained the target rate under the measured condition.
\end{document}
""",
    )
    latex_report = audit.audit_path(latex_source)
    body_repair = findings(latex_report, "safe_findings", "ACR_SCOPE_REDEFINITION")[0]
    assert body_repair["replacement"] == "multiple-input multiple-output (MIMO)"
    assert "{" not in body_repair["replacement"]


def test_markdown_fenced_fake_abstract_is_ignored_and_unclosed_fence_is_unresolved(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "fenced.md",
        """```markdown
# Abstract
multiple-input multiple-output (MIMO) appears only in this example.
""",
    )
    report = audit.audit_path(source)

    assert findings(report, "unresolved", "MARKDOWN_UNCLOSED_FENCE")
    assert not [item for item in report["scopes"] if item["kind"] == "abstract"]
    assert report["safe_findings"] == []

    closed = write_text(
        tmp_path,
        "closed.md",
        """```markdown
# Abstract
multiple-input multiple-output (MIMO) is example text.
```

# Results

MIMO is undefined in the actual manuscript body.
""",
    )
    closed_report = audit.audit_path(closed)
    assert not [item for item in closed_report["scopes"] if item["kind"] == "abstract"]
    assert findings(closed_report, "review_candidates", "ACR_UNDEFINED")

    longer = write_text(
        tmp_path,
        "longer-fence.md",
        """````text
FRT is code, not manuscript prose.
``` trailing text is not a closing fence
```
````

The measured link remained stable throughout the experiment.
""",
    )
    longer_report = audit.audit_path(longer)
    assert not findings(longer_report, "unresolved", "MARKDOWN_UNCLOSED_FENCE")
    assert not findings(longer_report, "review_candidates", "ACR_UNDEFINED")


def test_multibacktick_code_spans_and_indented_backmatter_are_not_audited(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "markup-boundaries.md",
        """# Abstract

Multiple-input multiple-output (MIMO) was evaluated. MIMO carried two streams.

# Results

``MIMO`` is example code, not manuscript prose.

    MIMO is an indented code-block example, not manuscript prose.

   # References

MIMO appears in a cited article title.
""",
    )
    report = audit.audit_path(source)

    assert not findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")
    assert not findings(report, "review_candidates", "ACR_UNDEFINED")


def test_markdown_html_comments_and_reference_destinations_are_not_audited(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "hidden-markup.md",
        """# Abstract

Multiple-input multiple-output (MIMO) was evaluated. MIMO carried two streams.

# Results

<!-- MIMO is a drafting note, not manuscript prose. -->
![Measured link response][fig1]

[fig1]: figures/MIMO-result.png
""",
    )
    report = audit.audit_path(source)

    assert not findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")
    assert not findings(report, "review_candidates", "ACR_UNDEFINED")


def test_reference_style_markdown_image_has_an_independent_caption_scope(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "reference-image.md",
        """# Abstract

Multiple-input multiple-output (MIMO) was evaluated. MIMO carried two streams.

# Results

![MIMO performance under the measured condition][fig1]

The MIMO link retained both streams.

[fig1]: figure.png
""",
    )
    report = audit.audit_path(source)

    repairs = findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")
    assert {item["scope"] for item in repairs} == {"body", "figure_caption:1"}


def test_empty_markdown_image_caption_is_a_review_candidate(tmp_path: Path) -> None:
    source = write_text(tmp_path, "empty-caption.md", "![](figure.png)\n")
    report = audit.audit_path(source)

    captions = [item for item in report["scopes"] if item["kind"] == "caption"]
    assert len(captions) == 1
    assert findings(report, "review_candidates", "CAPTION_TOO_SHORT")


def test_unresolved_latex_calls_do_not_contribute_safe_acronym_repairs(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "unresolved.tex",
        r"""\begin{document}
\begin{abstract}
Multiple-input multiple-output (MIMO) was evaluated. MIMO carried two streams.
\end{abstract}
\newcommand{\mycap}[1]{\caption{#1}}
\mycap{MIMO result}
\input{MIMO-results}
\caption{MIMO result with an unbalanced {detail}
""",
    )
    report = audit.audit_path(source)

    assert findings(report, "unresolved", "LATEX_CUSTOM_CAPTION")
    assert findings(report, "unresolved", "LATEX_EXTERNAL_FILE")
    assert findings(report, "unresolved", "LATEX_UNBALANCED_CAPTION")
    assert not findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")


def test_latex_document_without_abstract_or_sections_keeps_body_visible(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "sectionless.tex",
        r"""\title{Measured link response}
\begin{document}
It should be noted that FRT remained stable under the tested conditions.
\end{document}
""",
    )
    report = audit.audit_path(source)

    assert report["status"] == "has_findings"
    assert [
        item["evidence"]
        for item in findings(report, "review_candidates", "ACR_UNDEFINED")
    ] == ["FRT"]
    assert findings(report, "review_candidates", "LANG_DEFENSIVE_OR_META")
    assert findings(report, "protected_qualifiers", "LANG_SCIENTIFIC_QUALIFIER")


def test_unbraced_latex_input_is_unresolved_and_its_filename_is_not_audited(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "unbraced-input.tex",
        r"""\begin{document}
\input MIMO-results.tex
The measured link remained stable.
\end{document}
""",
    )
    report = audit.audit_path(source)

    external = findings(report, "unresolved", "LATEX_EXTERNAL_FILE")
    assert len(external) == 1
    assert external[0]["evidence"] == r"\input MIMO-results.tex"
    assert not findings(report, "review_candidates", "ACR_UNDEFINED")


def test_latex_comment_cannot_close_an_opaque_math_environment(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "commented-math-end.tex",
        r"""\begin{document}
\begin{abstract}
Frequency response transfer (FRT) was measured. FRT remained stable.
\end{abstract}
\begin{equation}
% \end{equation}
FRT = 1
\end{equation}
The measured link remained stable.
\end{document}
""",
    )
    report = audit.audit_path(source)

    assert not findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")
    assert not findings(report, "review_candidates", "ACR_UNDEFINED")


def test_latex_quotes_are_not_treated_as_markdown_code_spans(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "latex-quotes.tex",
        r"""\begin{document}
The ``first'' marker precedes FRT under the tested conditions and another ``second'' marker.
\end{document}
""",
    )
    report = audit.audit_path(source)

    assert [
        item["evidence"]
        for item in findings(report, "review_candidates", "ACR_UNDEFINED")
    ] == ["FRT"]
    assert findings(report, "protected_qualifiers", "LANG_SCIENTIFIC_QUALIFIER")


def test_same_line_opaque_math_preserves_trailing_latex_prose(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "same-line-math.tex",
        r"""\begin{document}
\begin{equation}x=1\end{equation} It should be noted that FRT remained stable under the tested conditions.
\end{document}
""",
    )
    report = audit.audit_path(source)

    assert [
        item["evidence"]
        for item in findings(report, "review_candidates", "ACR_UNDEFINED")
    ] == ["FRT"]
    assert findings(report, "review_candidates", "LANG_DEFENSIVE_OR_META")
    assert findings(report, "protected_qualifiers", "LANG_SCIENTIFIC_QUALIFIER")


def test_latex_inline_verbatim_is_not_audited(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "inline-verbatim.tex",
        r"""\begin{document}
\begin{abstract}
Multiple-input multiple-output (MIMO) was evaluated. MIMO carried two streams.
\end{abstract}
\verb|MIMO| is literal example text.
\end{document}
""",
    )
    report = audit.audit_path(source)

    assert not findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")
    assert not findings(report, "review_candidates", "ACR_UNDEFINED")


def test_unclosed_standard_latex_environments_are_unresolved(tmp_path: Path) -> None:
    cases = {
        "document.tex": r"\begin{document}The measured link remained stable.",
        "figure.tex": r"\begin{figure}The measured link remained stable.",
        "itemize.tex": r"\begin{itemize}\item Measured result.",
    }
    for name, content in cases.items():
        report = audit.audit_path(write_text(tmp_path, name, content))
        unclosed = findings(report, "unresolved", "LATEX_UNCLOSED_ENVIRONMENT")
        assert len(unclosed) == 1
        assert report["status"] == "has_findings"


def test_latex_content_after_end_document_is_not_audited(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "post-document.tex",
        r"""\begin{document}
\begin{abstract}
Multiple-input multiple-output (MIMO) was evaluated. MIMO carried two streams.
\end{abstract}
The measured link remained stable.
\end{document}
MIMO is a dormant editing note outside the document.
""",
    )
    report = audit.audit_path(source)

    assert not findings(report, "safe_findings", "ACR_SCOPE_REDEFINITION")
    assert not findings(report, "review_candidates", "ACR_UNDEFINED")


def test_visible_non_english_text_is_unresolved(tmp_path: Path) -> None:
    source = write_text(tmp_path, "chinese.md", "# Results\n\n系统保持稳定。\n")
    report = audit.audit_path(source)

    assert findings(report, "unresolved", "INPUT_NON_ENGLISH_TEXT")
    assert report["status"] == "has_findings"


def test_markdown_references_and_acknowledgments_are_not_body_scope(tmp_path: Path) -> None:
    source = write_text(
        tmp_path,
        "backmatter.md",
        """# Results

The measured link remained stable throughout the experiment.

# Acknowledgments

The MIMO test team assisted with the setup.

# References

TMTT, RF, and MIMO appear in article titles.
""",
    )
    report = audit.audit_path(source)

    assert not findings(report, "review_candidates", "ACR_UNDEFINED")


def test_latex_front_matter_math_and_references_do_not_define_or_pollute_body(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "sections.tex",
        r"""\title{Multiple-input multiple-output (MIMO) measurements}
\begin{document}
\maketitle
\section{Results}
MIMO was measured under the stated condition.
\captionsetup{font=small}
\begin{equation}
RF = MIMO + TMTT
\end{equation}
\section*{References}
MIMO and TMTT occur in bibliography titles.
\end{document}
""",
    )
    report = audit.audit_path(source)

    undefined = findings(report, "review_candidates", "ACR_UNDEFINED")
    assert [item["evidence"] for item in undefined] == ["MIMO"]
    assert not findings(report, "unresolved", "LATEX_CUSTOM_CAPTION")


def test_units_models_and_title_case_compounds_are_exempt_but_embedded_acronyms_are_checked(
    tmp_path: Path,
) -> None:
    source = write_text(
        tmp_path,
        "tokens.md",
        "The 115-GHz Front-End used a 5-GBaud M8195A source with an 83501QA head and a LeCroy SiGe test fixture. The OFDM-based waveform was measured.\n",
    )
    report = audit.audit_path(source)

    undefined = findings(report, "review_candidates", "ACR_UNDEFINED")
    assert [item["evidence"] for item in undefined] == ["OFDM"]


def test_invalid_utf8_reports_the_actual_line_not_the_byte_offset(tmp_path: Path) -> None:
    source = tmp_path / "broken.md"
    source.write_bytes(b"first line\nvalid prefix \xff")

    report = audit.audit_path(source)
    assert report["status"] == "parse_error"
    assert report["error"]["line"] == 2


def test_skill_entrypoint_has_no_utf8_bom() -> None:
    assert not (SKILL_DIR / "SKILL.md").read_bytes().startswith(b"\xef\xbb\xbf")
