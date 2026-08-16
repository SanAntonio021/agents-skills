#!/usr/bin/env python3
"""Read-only convention audit for English SCI/IEEE manuscripts.

The linter is intentionally conservative. It identifies deterministic repair
candidates but never edits the manuscript. Ambiguous wording, image semantics,
scientific qualifiers, and semantic repetition remain review items.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SCHEMA_VERSION = "1.0"
FORMAT_BY_SUFFIX = {".md": "markdown", ".markdown": "markdown", ".tex": "latex"}
CATEGORY_NAMES = (
    "safe_findings",
    "review_candidates",
    "protected_qualifiers",
    "unresolved",
)

TOKEN_RE = re.compile(r"\b[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*\b")
PAREN_ACRONYM_RE = re.compile(r"\((?P<acronym>[A-Za-z0-9][A-Za-z0-9-]{1,24})\)")
SENTENCE_RE = re.compile(r"[^.!?\n][^.!?]*[.!?](?=\s|$)")
NEGATION_SENTENCE_RE = re.compile(
    r'''[^.!?]+[.!?]+(?:["'\u201d\u2019)\]}*_]+)?(?=\s|$)''',
    re.S,
)
NO_NUMBER_RE = re.compile(
    r"\b(?i:No)(?P<period>\.)(?=\s*(?:"
    r"\d+[A-Za-z0-9-]*|"
    r"(?=[A-Za-z0-9-]*[A-Za-z])(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]+|"
    r"[IVXLCDM]+"
    r")\b)"
)
FIXED_INDIRECT_PATTERNS = (
    re.compile(r"\bby\s+no\s+means\b", re.I),
    re.compile(r"\bnot\s+without\b", re.I),
    re.compile(
        r"\bnot\s+(?:uncommon|infrequent|infrequently|insignificant|"
        r"negligible|impossible|unreasonable|unlikely|atypical)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:cannot|can['\u2019]t)\s+be\s+"
        r"(?:excluded|ruled\s+out|ignored|discounted|overlooked)\b",
        re.I,
    ),
)
NEGATIVE_AUXILIARY_PATTERNS = (
    re.compile(
        r"\b(?:am|is|are|was|were|be|been|being|do|does|did|has|have|had|"
        r"can|could|may|might|must|shall|should|will|would|need|dare)\s+not\b",
        re.I,
    ),
    re.compile(
        r"\b(?:cannot|can['\u2019]t|couldn['\u2019]t|don['\u2019]t|doesn['\u2019]t|"
        r"didn['\u2019]t|isn['\u2019]t|aren['\u2019]t|wasn['\u2019]t|weren['\u2019]t|"
        r"hasn['\u2019]t|haven['\u2019]t|hadn['\u2019]t|won['\u2019]t|wouldn['\u2019]t|"
        r"shouldn['\u2019]t|mustn['\u2019]t|mightn['\u2019]t|needn['\u2019]t|"
        r"shan['\u2019]t)\b",
        re.I,
    ),
)
ATOMIC_NEGATIVE_PATTERNS = (
    re.compile(r"\bunable\s+to\b", re.I),
    re.compile(r"\black(?:s|ed|ing)?\b", re.I),
    re.compile(r"\babsence\s+of\b", re.I),
    re.compile(r"\binsufficient\s+evidence\b", re.I),
    re.compile(r"\b(?:not|no|never|without|neither|nor)\b", re.I),
)
FAIL_TO_PATTERN = re.compile(
    r"\b(?P<fail>fail(?:s|ed|ing)?)\b.*?\b(?P<to>to)\b",
    re.I | re.S,
)

COMMON_EXEMPT_ACRONYMS = {
    "ASCII",
    "DOI",
    "HTML",
    "IEEE",
    "JSON",
    "ORCID",
    "PDF",
    "SCI",
    "URL",
    "UTF",
    "XML",
    "HZ",
    "KHZ",
    "MHZ",
    "GHZ",
    "THZ",
    "BAUD",
    "KBAUD",
    "MBAUD",
    "GBAUD",
    "DB",
    "DBM",
    "DBI",
}

DEFENSIVE_PATTERNS = (
    re.compile(r"\bit (?:should|must) be (?:noted|emphasized) that\b", re.I),
    re.compile(r"\bit is (?:important|interesting|worthwhile|worth) (?:to note|noting) that\b", re.I),
    re.compile(r"\bit can be seen that\b", re.I),
    re.compile(r"\bthe following (?:discussion|section|analysis) (?:focuses on|presents|describes)\b", re.I),
    re.compile(r"\bfor the sake of completeness\b", re.I),
    re.compile(r"\bwe do not claim that\b", re.I),
    re.compile(r"\bthe contribution of (?:this|the present) (?:paper|work) (?:lies|is)\b", re.I),
    re.compile(
        r"\b(?:fig(?:ure)?\.?|table)\s+[A-Z0-9]+\s+"
        r"(?:shows?|presents?|illustrates?|summarizes?)\s+(?:the\s+)?"
        r"(?:results?|comparison|setup|procedure)\s*[.,;:]",
        re.I,
    ),
)

PROTECTED_PATTERNS = (
    re.compile(r"\bunder (?:the )?(?:tested|measured|considered|assumed|experimental) conditions?\b", re.I),
    re.compile(r"\b(?:assuming|subject to|limited to|within the tested range)\b", re.I),
    re.compile(r"\b(?:comparison benchmark|for comparison|relative to the benchmark)\b", re.I),
    re.compile(r"\b(?:confidence|credible|uncertainty) intervals?\b", re.I),
    re.compile(r"\b(?:standard deviation|standard error|error bars?|interquartile range|IQR)\b", re.I),
    re.compile(r"\b(?:a limitation|limitations? of (?:this|the) (?:study|experiment|setup))\b", re.I),
)

VERBATIM_ENVIRONMENTS = {"verbatim", "Verbatim", "lstlisting", "minted"}
LATEX_MATH_ENVIRONMENTS = {
    "math",
    "displaymath",
    "equation",
    "equation*",
    "align",
    "align*",
    "alignat",
    "alignat*",
    "gather",
    "gather*",
    "multline",
    "multline*",
}
LATEX_NON_BODY_ENVIRONMENTS = {
    "thebibliography",
    "acknowledgment",
    "acknowledgments",
    "acknowledgement",
    "acknowledgements",
    "keywords",
    "IEEEkeywords",
}
LATEX_OPAQUE_ENVIRONMENTS = (
    VERBATIM_ENVIRONMENTS | LATEX_MATH_ENVIRONMENTS | LATEX_NON_BODY_ENVIRONMENTS
)
LATEX_CAPTION_CONFIG_COMMANDS = {
    "captionsetup",
    "captionstyle",
    "captionlabelfont",
    "captiontextfont",
}


@dataclass(frozen=True)
class Scope:
    scope_id: str
    kind: str
    text: str
    start_offset: int


@dataclass(frozen=True)
class Definition:
    acronym: str
    key: str
    full_form: str
    source_form: str
    source_form_safe: bool
    normalized_full_form: str
    scope_id: str
    full_start: int
    acronym_start: int
    paren_start: int
    paren_end: int


@dataclass(frozen=True)
class Sentence:
    scope_id: str
    paragraph: int
    start: int
    end: int
    text: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class SentenceUnit:
    scope_id: str
    start: int
    end: int
    source_text: str
    visible_text: str


@dataclass(frozen=True)
class MarkdownHeading:
    start: int
    content_start: int
    end: int
    level: int
    title: str


@dataclass(frozen=True)
class NegativeHit:
    start: int
    end: int
    text: str
    category: str


@dataclass(frozen=True)
class AcronymOccurrence:
    token: str
    start: int
    end: int


class SourceMap:
    def __init__(self, text: str) -> None:
        self.text = text
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer(r"\n", text))

    def point(self, offset: int) -> tuple[int, int]:
        bounded = max(0, min(offset, len(self.text)))
        index = bisect.bisect_right(self.line_starts, bounded) - 1
        return index + 1, bounded - self.line_starts[index] + 1

    def span(self, start: int, end: int) -> dict[str, int]:
        start_line, start_column = self.point(start)
        end_line, end_column = self.point(end)
        return {
            "start_line": start_line,
            "start_column": start_column,
            "end_line": end_line,
            "end_column": end_column,
        }


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def replace_range(buffer: list[str], start: int, end: int) -> None:
    for index in range(max(0, start), min(end, len(buffer))):
        if buffer[index] not in "\r\n":
            buffer[index] = " "


def mask_matches(text: str, patterns: Sequence[re.Pattern[str]]) -> str:
    buffer = list(text)
    for pattern in patterns:
        for match in pattern.finditer(text):
            replace_range(buffer, match.start(), match.end())
    return "".join(buffer)


def mask_markdown_code_spans(text: str) -> str:
    """Mask Markdown code spans while preserving offsets and line breaks."""

    buffer = list(text)
    runs = list(re.finditer(r"`+", text))
    index = 0
    while index < len(runs):
        opening = runs[index]
        delimiter_length = opening.end() - opening.start()
        closing_index = index + 1
        while closing_index < len(runs):
            closing = runs[closing_index]
            if closing.end() - closing.start() == delimiter_length:
                replace_range(buffer, opening.start(), closing.end())
                index = closing_index + 1
                break
            closing_index += 1
        else:
            index += 1
    return "".join(buffer)


def mask_inline_markup(text: str, *, markdown: bool) -> str:
    if markdown:
        text = mask_markdown_code_spans(text)
    patterns = (
        re.compile(r"\[@[^\]\n]+\]"),
        re.compile(r"\$\$.*?\$\$", re.S),
        re.compile(r"\$[^$\n]+\$"),
        re.compile(r"\\\[.*?\\\]", re.S),
        re.compile(r"\\\(.*?\\\)", re.S),
        re.compile(r"https?://\S+"),
        re.compile(r"\\(?:cite|citep|citet|ref|eqref|label|url|href|includegraphics|bibliography|bibliographystyle)\*?(?:\[[^\]]*\])?\{[^{}]*\}"),
        re.compile(r"\\[A-Za-z@]+\*?"),
    )
    if markdown:
        patterns += (re.compile(r"\]\((?:[^()\n]|\([^()\n]*\))*\)"),)
    return mask_matches(text, patterns)


def is_escaped(text: str, position: int) -> bool:
    count = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        count += 1
        position -= 1
    return count % 2 == 1


def mask_markdown_fences(text: str) -> tuple[str, int | None]:
    buffer = list(text)
    offset = 0
    fenced = False
    fence_character = ""
    fence_length = 0
    fence_start: int | None = None
    for line in text.splitlines(keepends=True):
        if fenced:
            closing = re.match(
                rf"^ {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*(?:\r?\n)?$",
                line,
            )
            if closing:
                fenced = False
                fence_character = ""
                fence_length = 0
                fence_start = None
            replace_range(buffer, offset, offset + len(line))
        else:
            opening = re.match(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>[^\r\n]*)", line)
            if opening:
                fence = opening.group("fence")
                info = opening.group("info")
                if fence[0] == "`" and "`" in info:
                    offset += len(line)
                    continue
                fenced = True
                fence_character = fence[0]
                fence_length = len(fence)
                fence_start = offset + len(opening.group("indent"))
                replace_range(buffer, offset, offset + len(line))
        offset += len(line)
    return "".join(buffer), fence_start


def mask_markdown_html_comments(text: str) -> tuple[str, int | None]:
    buffer = list(text)
    cursor = 0
    while True:
        start = text.find("<!--", cursor)
        if start == -1:
            return "".join(buffer), None
        close = text.find("-->", start + 4)
        if close == -1:
            replace_range(buffer, start, len(text))
            return "".join(buffer), start
        replace_range(buffer, start, close + 3)
        cursor = close + 3


def mask_markdown_raw_html(text: str) -> tuple[str, list[tuple[str, int]]]:
    """Mask raw HTML tables, code blocks, and headings while preserving offsets."""

    buffer = list(text)
    stack: list[tuple[str, int]] = []
    token = re.compile(
        r"<\s*(?P<close>/)?\s*(?P<tag>table|pre|code|h[1-6])\b[^>]*>",
        re.I,
    )
    for match in token.finditer(text):
        tag = match.group("tag").lower()
        if not match.group("close"):
            if match.group(0).rstrip().endswith("/>"):
                replace_range(buffer, match.start(), match.end())
            else:
                stack.append((tag, match.start()))
            continue
        matching_index = next(
            (
                index
                for index in range(len(stack) - 1, -1, -1)
                if stack[index][0] == tag
            ),
            None,
        )
        if matching_index is None:
            continue
        start = stack[matching_index][1]
        replace_range(buffer, start, match.end())
        del stack[matching_index:]
    for _, start in stack:
        replace_range(buffer, start, len(buffer))
    return "".join(buffer), stack


def mask_markdown_indented_code(text: str) -> str:
    buffer = list(text)
    offset = 0
    for line in text.splitlines(keepends=True):
        if re.match(r"^(?: {4}|\t)", line):
            replace_range(buffer, offset, offset + len(line))
        offset += len(line)
    return "".join(buffer)


def parse_markdown_headings(text: str) -> list[MarkdownHeading]:
    lines: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        lines.append((offset, offset + len(line), line))
        offset += len(line)

    headings: list[MarkdownHeading] = []
    atx_lines: set[int] = set()
    for index, (start, end, line) in enumerate(lines):
        raw = line.rstrip("\r\n")
        match = re.match(
            r"^ {0,3}(?P<marks>#{1,6})(?:[ \t]+|$)(?P<title>.*)$",
            raw,
        )
        if not match:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group("title")).strip()
        headings.append(
            MarkdownHeading(start, end, end, len(match.group("marks")), title)
        )
        atx_lines.add(index)

    for index in range(1, len(lines)):
        start, end, line = lines[index]
        underline = re.match(
            r"^ {0,3}(?P<marks>=+|-+)[ \t]*$", line.rstrip("\r\n")
        )
        if not underline or index - 1 in atx_lines:
            continue
        title_start, _, title_line = lines[index - 1]
        title = title_line.rstrip("\r\n").strip()
        if not title or re.match(r"^ {0,3}(?:[-+*]|\d+[.)])\s+", title_line):
            continue
        level = 1 if underline.group("marks").startswith("=") else 2
        headings.append(MarkdownHeading(title_start, end, end, level, title))

    return sorted(headings, key=lambda item: (item.start, item.end, item.level))


def mask_markdown_headings(
    text: str, headings: Sequence[MarkdownHeading] | None = None
) -> str:
    buffer = list(text)
    for heading in headings or parse_markdown_headings(text):
        replace_range(buffer, heading.start, heading.end)
    return "".join(buffer)


def markdown_named_section_ranges(
    text: str, headings: Sequence[MarkdownHeading] | None = None
) -> list[tuple[int, int]]:
    parsed = list(headings or parse_markdown_headings(text))
    excluded = re.compile(r"^(?:references|bibliography|acknowledg(?:e)?ments?)$", re.I)
    ranges: list[tuple[int, int]] = []
    for index, heading in enumerate(parsed):
        title = heading.title.strip(" *_`")
        if not excluded.fullmatch(title):
            continue
        end = len(text)
        for later in parsed[index + 1 :]:
            if later.level <= heading.level:
                end = later.start
                break
        ranges.append((heading.start, end))
    return ranges


def find_line_end(text: str, offset: int) -> int:
    newline = text.find("\n", offset)
    return len(text) if newline == -1 else newline


def find_paragraph_end(text: str, offset: int) -> int:
    match = re.search(r"\n\s*\n|\n\s*#{1,6}\s+", text[offset:])
    return len(text) if not match else offset + match.start()


def parse_markdown(
    text: str, source_map: SourceMap, path: str
) -> tuple[list[Scope], list[dict[str, object]]]:
    fence_visible, unclosed_fence = mask_markdown_fences(text)
    comment_visible, unclosed_comment = mask_markdown_html_comments(fence_visible)
    html_visible, unclosed_html = mask_markdown_raw_html(comment_visible)
    prose_visible = mask_markdown_indented_code(html_visible)
    headings = parse_markdown_headings(prose_visible)
    content_buffer = list(mask_markdown_headings(prose_visible, headings))
    scopes: list[Scope] = []
    unresolved: list[dict[str, object]] = []

    if unclosed_fence is not None:
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                unclosed_fence,
                "MARKDOWN_UNCLOSED_FENCE",
                "A fenced code block is not closed; the fenced remainder was not audited.",
                text[unclosed_fence : find_line_end(text, unclosed_fence)],
            )
        )

    if unclosed_comment is not None:
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                unclosed_comment,
                "MARKDOWN_UNCLOSED_HTML_COMMENT",
                "An HTML comment is not closed; the commented remainder was not audited.",
                text[unclosed_comment : find_line_end(text, unclosed_comment)],
            )
        )

    for tag, offset in unclosed_html:
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                offset,
                "MARKDOWN_UNCLOSED_RAW_HTML",
                "A raw HTML block is not closed; the remaining block was not audited.",
                text[offset : find_line_end(text, offset)],
            )
        )

    for start, end in markdown_named_section_ranges(prose_visible, headings):
        replace_range(content_buffer, start, end)
    reference_definition = re.compile(r"(?m)^ {0,3}\[[^\]\n]+\]:[^\n]*(?:\n|$)")
    for match in reference_definition.finditer(prose_visible):
        replace_range(content_buffer, match.start(), match.end())
    masked = "".join(content_buffer)
    body_buffer = list(masked)

    abstract_range: tuple[int, int] | None = None
    heading = next(
        (
            item
            for item in headings
            if item.title.strip(" *_`").lower() == "abstract"
        ),
        None,
    )
    if heading:
        replace_range(body_buffer, 0, heading.start)
        start = heading.content_start
        next_heading = next(
            (item for item in headings if item.start >= start),
            None,
        )
        end = len(text) if not next_heading else next_heading.start
        abstract_range = (start, end)
    else:
        inline = re.search(
            r"(?im)^\s*(?:\*\*)?abstract(?:\*\*)?\s*[\-:\u2014]\s*",
            prose_visible,
        )
        if inline:
            replace_range(body_buffer, 0, inline.start())
            start = inline.end()
            abstract_range = (start, find_paragraph_end(text, start))

    if abstract_range:
        start, end = abstract_range
        scopes.append(Scope("abstract", "abstract", masked[start:end], start))
        replace_range(body_buffer, start, end)

    caption_ranges: list[tuple[int, int]] = []
    image_pattern = re.compile(
        r"!\[(?P<caption>[^\]\n]*)\](?:\([^\n)]*\)|\[[^\]\n]*\])?"
    )
    for index, match in enumerate(image_pattern.finditer(masked), start=1):
        start, end = match.span("caption")
        scopes.append(Scope(f"figure_caption:{index}", "caption", text[start:end], start))
        caption_ranges.append(match.span())

    raw_caption = re.compile(
        r"(?im)^\s*(?:\*\*|\*|_)?(?P<caption>(?:(?:fig(?:ure)?\.?\s*"
        r"[A-Z0-9]+(?:\s*\([A-Za-z0-9]+\))*)|"
        r"(?:table\s+[A-Z0-9]+(?:\s*\([A-Za-z0-9]+\))*))\s*[.:]\s*.+?)"
        r"(?:\*\*|\*|_)?\s*$"
    )
    raw_index = len(caption_ranges)
    for match in raw_caption.finditer(masked):
        if any(start <= match.start() < end for start, end in caption_ranges):
            continue
        raw_index += 1
        start, end = match.span("caption")
        kind = "table_caption" if text[start:end].lstrip().lower().startswith("table") else "caption"
        scopes.append(Scope(f"{kind}:{raw_index}", kind, text[start:end], start))
        caption_ranges.append(match.span())

    for start, end in caption_ranges:
        replace_range(body_buffer, start, end)

    scopes.append(Scope("body", "body", "".join(body_buffer), 0))
    scopes.sort(key=lambda item: (item.start_offset, item.scope_id))
    return scopes, unresolved


def mask_latex_opaque(text: str) -> tuple[str, list[tuple[str, int]]]:
    buffer = list(text)
    unclosed: list[tuple[str, int]] = []
    active_env: str | None = None
    active_start = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        if active_env:
            comment_at = None
            for index, char in enumerate(line):
                if char == "%" and not is_escaped(line, index):
                    comment_at = index
                    break
            visible_end = len(line) if comment_at is None else comment_at
            if comment_at is not None:
                replace_range(buffer, offset + comment_at, offset + len(line))
            visible = line[:visible_end]
            closing = re.search(rf"\\end\{{{re.escape(active_env)}\}}", visible)
            if closing:
                replace_range(buffer, offset, offset + closing.end())
                active_env = None
            else:
                replace_range(buffer, offset, offset + len(line))
            offset += len(line)
            continue

        comment_at = None
        for index, char in enumerate(line):
            if char == "%" and not is_escaped(line, index):
                comment_at = index
                break
        visible_end = len(line) if comment_at is None else comment_at
        if comment_at is not None:
            replace_range(buffer, offset + comment_at, offset + len(line))
        visible = line[:visible_end]
        opaque_names = "|".join(
            re.escape(name) for name in sorted(LATEX_OPAQUE_ENVIRONMENTS, key=len, reverse=True)
        )
        begin = re.search(rf"\\begin\{{(?P<env>{opaque_names})\}}", visible)
        if begin:
            env = begin.group("env")
            closing = re.search(rf"\\end\{{{re.escape(env)}\}}", visible[begin.end() :])
            if closing:
                close_end = begin.end() + closing.end()
                replace_range(buffer, offset + begin.start(), offset + close_end)
            else:
                replace_range(buffer, offset + begin.start(), offset + len(line))
                active_env = env
                active_start = offset + begin.start()
        offset += len(line)
    if active_env:
        unclosed.append((active_env, active_start))
    return "".join(buffer), unclosed


def mask_latex_inline_verbatim(text: str) -> tuple[str, list[tuple[str, int]]]:
    buffer = list(text)
    unclosed: list[tuple[str, int]] = []
    command = re.compile(
        r"\\(?P<name>verb\*?|lstinline\*?|mintinline\*?)(?![A-Za-z@])"
    )
    for match in command.finditer(text):
        name = match.group("name").rstrip("*")
        cursor = match.end()
        if name != "verb":
            while cursor < len(text) and text[cursor] in " \t":
                cursor += 1
            if cursor < len(text) and text[cursor] == "[":
                options_end = scan_balanced(text, cursor, "[", "]")
                if options_end is None:
                    line_end = find_line_end(text, cursor)
                    replace_range(buffer, match.start(), line_end)
                    unclosed.append((name, match.start()))
                    continue
                cursor = options_end + 1
                while cursor < len(text) and text[cursor] in " \t":
                    cursor += 1
        if name == "mintinline":
            if cursor >= len(text) or text[cursor] != "{":
                line_end = find_line_end(text, cursor)
                replace_range(buffer, match.start(), line_end)
                unclosed.append((name, match.start()))
                continue
            language_end = scan_balanced(text, cursor, "{", "}")
            if language_end is None:
                line_end = find_line_end(text, cursor)
                replace_range(buffer, match.start(), line_end)
                unclosed.append((name, match.start()))
                continue
            cursor = language_end + 1
            while cursor < len(text) and text[cursor] in " \t":
                cursor += 1

        line_end = find_line_end(text, match.end())
        if cursor >= line_end or text[cursor].isspace() or text[cursor].isalnum():
            replace_range(buffer, match.start(), line_end)
            unclosed.append((name, match.start()))
            continue
        if text[cursor] == "{":
            close = scan_balanced(text, cursor, "{", "}")
            if close is None or close > line_end:
                replace_range(buffer, match.start(), line_end)
                unclosed.append((name, match.start()))
                continue
            replace_range(buffer, match.start(), close + 1)
            continue
        delimiter = text[cursor]
        close = text.find(delimiter, cursor + 1)
        if close == -1 or close > line_end:
            replace_range(buffer, match.start(), line_end)
            unclosed.append((name, match.start()))
            continue
        replace_range(buffer, match.start(), close + 1)
    return "".join(buffer), unclosed


def scan_balanced(text: str, start: int, opening: str, closing: str) -> int | None:
    if start >= len(text) or text[start] != opening:
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if is_escaped(text, index):
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def mask_custom_caption_definitions(
    text: str,
    path: str,
    source_map: SourceMap,
) -> tuple[str, list[dict[str, object]], set[str]]:
    """Mask command definitions that wrap ``\\caption`` and report them.

    Phase 1 cannot determine the scope or rendering semantics of user-defined
    caption commands. Masking their definitions also prevents a nested
    ``\\caption{#1}`` template from being mistaken for a manuscript caption.
    """

    buffer = list(text)
    unresolved: list[dict[str, object]] = []
    custom_names: set[str] = set()
    command = re.compile(
        r"\\(?:newcommand|renewcommand|providecommand|DeclareRobustCommand)\*?\s*"
        r"(?:\{\\(?P<braced>[A-Za-z@]+)\}|\\(?P<plain>[A-Za-z@]+))"
    )
    for match in command.finditer(text):
        cursor = match.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        while cursor < len(text) and text[cursor] == "[":
            optional_end = scan_balanced(text, cursor, "[", "]")
            if optional_end is None:
                break
            cursor = optional_end + 1
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            continue
        definition_end = scan_balanced(text, cursor, "{", "}")
        if definition_end is None:
            continue
        definition = text[cursor + 1 : definition_end]
        if not re.search(r"\\caption(?![A-Za-z@])", definition):
            continue
        name = match.group("braced") or match.group("plain") or "unknown"
        custom_names.add(name)
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                match.start(),
                "LATEX_CUSTOM_CAPTION",
                "A user-defined caption command is outside the deterministic Phase 1 parser.",
                rf"\{name}",
            )
        )
        replace_range(buffer, match.start(), definition_end + 1)
    return "".join(buffer), unresolved, custom_names


def latex_command_call_end(text: str, start: int, name_end: int) -> int:
    cursor = name_end
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    while cursor < len(text) and text[cursor] == "[":
        optional_end = scan_balanced(text, cursor, "[", "]")
        if optional_end is None:
            return find_line_end(text, cursor)
        cursor = optional_end + 1
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
    consumed_argument = False
    while cursor < len(text) and text[cursor] == "{":
        argument_end = scan_balanced(text, cursor, "{", "}")
        if argument_end is None:
            return len(text)
        consumed_argument = True
        cursor = argument_end + 1
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
    return cursor if consumed_argument else max(name_end, find_line_end(text, start))


def latex_excluded_tail_start(text: str) -> int | None:
    excluded = re.compile(r"^(?:references|bibliography|acknowledg(?:e)?ments?)$", re.I)
    section = re.compile(r"\\section\*?(?![A-Za-z@])")
    starts: list[int] = []
    for match in section.finditer(text):
        cursor = match.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            continue
        end = scan_balanced(text, cursor, "{", "}")
        if end is None:
            continue
        raw_title = text[cursor + 1 : end]
        title = re.sub(r"\\[A-Za-z@]+\*?", "", raw_title)
        title = re.sub(r"[{}]", "", title).strip()
        if excluded.fullmatch(title):
            starts.append(match.start())
    return min(starts) if starts else None


def unresolved_finding(
    path: str,
    source_map: SourceMap,
    offset: int,
    rule_id: str,
    message: str,
    evidence: str,
    scope: str = "document",
) -> dict[str, object]:
    line, _ = source_map.point(offset)
    return {
        "rule_id": rule_id,
        "check": "parser",
        "path": path,
        "line": line,
        "scope": scope,
        "message": message,
        "evidence": evidence,
    }


def audit_latex_environment_balance(
    text: str,
    path: str,
    source_map: SourceMap,
) -> list[dict[str, object]]:
    """Report malformed standard environments that Phase 1 cannot audit safely."""

    findings: list[dict[str, object]] = []
    stack: list[tuple[str, int]] = []
    environment = re.compile(
        r"\\(?P<kind>begin|end)\s*\{(?P<name>[A-Za-z@]+\*?)\}"
    )
    for match in environment.finditer(text):
        name = match.group("name")
        if name.lower() == "abstract":
            continue
        if match.group("kind") == "begin":
            stack.append((name, match.start()))
            continue
        if stack and stack[-1][0] == name:
            stack.pop()
            continue

        matching_index = next(
            (index for index in range(len(stack) - 1, -1, -1) if stack[index][0] == name),
            None,
        )
        if matching_index is None:
            findings.append(
                unresolved_finding(
                    path,
                    source_map,
                    match.start(),
                    "LATEX_UNMATCHED_ENVIRONMENT_END",
                    "An environment ends without a matching visible begin command.",
                    match.group(0),
                )
            )
            continue

        expected = stack[-1][0]
        findings.append(
            unresolved_finding(
                path,
                source_map,
                match.start(),
                "LATEX_MISMATCHED_ENVIRONMENT",
                "LaTeX environments close out of order; the affected structure was not audited reliably.",
                rf"expected \end{{{expected}}}, found {match.group(0)}",
            )
        )
        for dangling_name, dangling_offset in stack[matching_index + 1 :]:
            findings.append(
                unresolved_finding(
                    path,
                    source_map,
                    dangling_offset,
                    "LATEX_UNCLOSED_ENVIRONMENT",
                    "A LaTeX environment is not closed.",
                    rf"\begin{{{dangling_name}}}",
                )
            )
        del stack[matching_index:]

    for name, offset in stack:
        findings.append(
            unresolved_finding(
                path,
                source_map,
                offset,
                "LATEX_UNCLOSED_ENVIRONMENT",
                "A LaTeX environment is not closed.",
                rf"\begin{{{name}}}",
            )
        )
    return findings


def parse_latex(
    text: str, source_map: SourceMap, path: str
) -> tuple[list[Scope], list[dict[str, object]]]:
    masked, unclosed_envs = mask_latex_opaque(text)
    scopes: list[Scope] = []
    unresolved: list[dict[str, object]] = []

    for env, offset in unclosed_envs:
        rule_id = (
            "LATEX_UNCLOSED_VERBATIM"
            if env in VERBATIM_ENVIRONMENTS
            else "LATEX_UNCLOSED_OPAQUE_ENVIRONMENT"
        )
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                offset,
                rule_id,
                "An opaque LaTeX environment is not closed; later content was not audited.",
                env,
            )
        )

    masked, unclosed_verbs = mask_latex_inline_verbatim(masked)
    for command_name, offset in unclosed_verbs:
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                offset,
                "LATEX_UNCLOSED_INLINE_VERBATIM",
                "An inline verbatim command has no closing delimiter; the rest of the line was not audited.",
                rf"\{command_name}",
            )
        )

    masked, custom_definitions, custom_names = mask_custom_caption_definitions(
        masked, path, source_map
    )
    unresolved.extend(custom_definitions)
    unresolved.extend(audit_latex_environment_balance(masked, path, source_map))

    document_end = re.search(r"\\end\s*\{document\}", masked, re.I)
    if document_end:
        document_buffer = list(masked)
        replace_range(document_buffer, document_end.start(), len(document_buffer))
        masked = "".join(document_buffer)
    body_buffer = list(masked)

    excluded_tail = latex_excluded_tail_start(masked)
    if excluded_tail is not None:
        replace_range(body_buffer, excluded_tail, len(body_buffer))

    document_begin = re.search(r"\\begin\s*\{document\}", masked, re.I)
    abstract_begin = re.search(r"\\begin\s*\{abstract\}", masked, re.I)
    if abstract_begin:
        replace_range(body_buffer, 0, abstract_begin.start())
    elif document_begin:
        replace_range(body_buffer, 0, document_begin.end())

    for match in re.finditer(
        r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?(?![A-Za-z@])",
        masked,
    ):
        replace_range(
            body_buffer,
            match.start(),
            latex_command_call_end(masked, match.start(), match.end()),
        )

    external_file = re.compile(
        r"\\(?:input|include)(?![A-Za-z@])(?:\s*\{[^{}]*\}|[ \t]+[^\s%{}]+)"
    )
    for match in external_file.finditer(masked):
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                match.start(),
                "LATEX_EXTERNAL_FILE",
                "External LaTeX files are outside the single-file Phase 1 scope.",
                match.group(0),
            )
        )
        replace_range(body_buffer, match.start(), match.end())

    for match in re.finditer(r"\\(?:captionof|subcaption|subcaptionbox)\b", masked):
        unresolved.append(
            unresolved_finding(
                path,
                source_map,
                match.start(),
                "LATEX_CUSTOM_CAPTION",
                "This caption form is not parsed deterministically in Phase 1.",
                match.group(0),
            )
        )
        replace_range(
            body_buffer,
            match.start(),
            latex_command_call_end(masked, match.start(), match.end()),
        )

    custom_caption_command = re.compile(r"\\(?P<name>[A-Za-z@]+)\b")
    for match in custom_caption_command.finditer(masked):
        command_name = match.group("name").lower()
        defined_custom = match.group("name") in custom_names
        caption_like = "caption" in command_name and command_name not in {
            "caption",
            "captionof",
            "subcaption",
            "subcaptionbox",
        }
        if command_name in LATEX_CAPTION_CONFIG_COMMANDS:
            continue
        if not defined_custom and not caption_like:
            continue
        if not defined_custom:
            unresolved.append(
                unresolved_finding(
                    path,
                    source_map,
                    match.start(),
                    "LATEX_CUSTOM_CAPTION",
                    "This caption-like command is outside the deterministic Phase 1 parser.",
                    match.group(0),
                )
            )
        replace_range(
            body_buffer,
            match.start(),
            latex_command_call_end(masked, match.start(), match.end()),
        )

    if abstract_begin:
        abstract_end = re.search(r"\\end\s*\{abstract\}", masked[abstract_begin.end() :], re.I)
        if abstract_end:
            start = abstract_begin.end()
            end = abstract_begin.end() + abstract_end.start()
            full_end = abstract_begin.end() + abstract_end.end()
            scopes.append(Scope("abstract", "abstract", masked[start:end], start))
            replace_range(body_buffer, abstract_begin.start(), full_end)
        else:
            unresolved.append(
                unresolved_finding(
                    path,
                    source_map,
                    abstract_begin.start(),
                    "LATEX_UNCLOSED_ABSTRACT",
                    "The abstract environment is not closed.",
                    r"\begin{abstract}",
                )
            )
            replace_range(body_buffer, abstract_begin.start(), len(body_buffer))

    caption_index = 0
    search_at = 0
    caption_command = re.compile(r"\\caption(?![A-Za-z@])")
    while True:
        match = caption_command.search(masked, search_at)
        if not match:
            break
        cursor = match.end()
        while cursor < len(masked) and masked[cursor].isspace():
            cursor += 1
        if cursor < len(masked) and masked[cursor] == "[":
            short_end = scan_balanced(masked, cursor, "[", "]")
            if short_end is None:
                unresolved.append(
                    unresolved_finding(
                        path,
                        source_map,
                        match.start(),
                        "LATEX_UNBALANCED_CAPTION",
                        "The optional caption argument is not balanced.",
                        r"\caption[...",
                    )
                )
                replace_range(
                    body_buffer,
                    match.start(),
                    find_line_end(masked, match.start()),
                )
                search_at = match.end()
                continue
            cursor = short_end + 1
            while cursor < len(masked) and masked[cursor].isspace():
                cursor += 1
        if cursor >= len(masked) or masked[cursor] != "{":
            unresolved.append(
                unresolved_finding(
                    path,
                    source_map,
                    match.start(),
                    "LATEX_UNSUPPORTED_CAPTION",
                    "The caption command has no standard braced argument.",
                    r"\caption",
                )
            )
            replace_range(
                body_buffer,
                match.start(),
                find_line_end(masked, match.start()),
            )
            search_at = match.end()
            continue
        close = scan_balanced(masked, cursor, "{", "}")
        if close is None:
            unresolved.append(
                unresolved_finding(
                    path,
                    source_map,
                    match.start(),
                    "LATEX_UNBALANCED_CAPTION",
                    "The caption braces are not balanced.",
                    r"\caption{...",
                )
            )
            replace_range(body_buffer, match.start(), len(body_buffer))
            search_at = match.end()
            continue
        caption_index += 1
        scopes.append(
            Scope(
                f"caption:{caption_index}",
                "caption",
                masked[cursor + 1 : close],
                cursor + 1,
            )
        )
        replace_range(body_buffer, match.start(), close + 1)
        search_at = close + 1

    scopes.append(Scope("body", "body", "".join(body_buffer), 0))
    scopes.sort(key=lambda item: (item.start_offset, item.scope_id))
    return scopes, unresolved


def acronym_key(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", token).upper()


def is_acronym(token: str) -> bool:
    parts = re.split(r"[-/]", token)
    if len(parts) > 1:
        nonnumeric = [part for part in parts if part and not part.isdigit()]
        if nonnumeric and all(part.istitle() for part in nonnumeric):
            return False
        if parts[0].isdigit() and acronym_key(parts[-1]) in COMMON_EXEMPT_ACRONYMS:
            return False
        acronym_parts = [part for part in nonnumeric if is_acronym(part)]
        if len(acronym_parts) == 1 and len(nonnumeric) > 1:
            return False
    letters = [char for char in token if char.isalpha()]
    if len(letters) < 2 or sum(char.isupper() for char in letters) < 2:
        return False
    if any(char.islower() for char in letters) and not re.search(r"[A-Z]{2}", token):
        return False
    key = acronym_key(token)
    if key in COMMON_EXEMPT_ACRONYMS or re.fullmatch(r"\d+G", key):
        return False
    if re.fullmatch(r"(?:[A-Z]|S)\d{1,2}", key):
        return False
    if re.fullmatch(r"[A-Z]{2,}\d{2,}[A-Z0-9]*", key):
        return False
    if re.fullmatch(r"[A-Z]\d{3,}[A-Z0-9]*", key):
        return False
    if re.fullmatch(r"\d{4,}[A-Z]{1,3}", key):
        return False
    return True


def iter_acronym_occurrences(text: str) -> Iterable[AcronymOccurrence]:
    for match in TOKEN_RE.finditer(text):
        token = match.group(0)
        if is_acronym(token):
            yield AcronymOccurrence(token, match.start(), match.end())
            continue
        if "-" not in token and "/" not in token:
            continue
        for part in re.finditer(r"[A-Za-z0-9]+", token):
            if is_acronym(part.group(0)):
                yield AcronymOccurrence(
                    part.group(0),
                    match.start() + part.start(),
                    match.start() + part.end(),
                )


def phrase_signature(phrase: str) -> str:
    signature: list[str] = []
    for token_match in TOKEN_RE.finditer(phrase):
        token = token_match.group(0)
        parts = re.split(r"[-/]", token)
        if parts and parts[0].isdigit():
            signature.append(parts[0])
            parts = parts[1:]
            if parts and parts[0].lower() == "ary":
                parts = parts[1:]
        for part in parts:
            if part:
                signature.append(part[0])
    return "".join(signature).upper()


def is_subsequence(needle: str, haystack: str) -> bool:
    cursor = iter(haystack)
    return all(any(char == candidate for candidate in cursor) for char in needle)


def signature_matches(acronym: str, signature: str) -> bool:
    key = acronym_key(acronym)
    if key == signature:
        return True
    return len(signature) - len(key) <= 2 and is_subsequence(key, signature)


def embedded_acronym(phrase: str) -> bool:
    return any(iter_acronym_occurrences(phrase))


def expansion_before(
    text: str, paren_start: int, acronym: str
) -> tuple[str, int, int] | None:
    lower_bound = max(0, paren_start - 180)
    lookback = text[lower_bound:paren_start]
    separator = max((lookback.rfind(mark) for mark in ".;:!?()\n"), default=-1)
    segment_start = lower_bound + separator + 1
    segment = text[segment_start:paren_start]
    tokens = list(TOKEN_RE.finditer(segment))
    for size in range(1, min(8, len(tokens)) + 1):
        first = tokens[-size]
        last = tokens[-1]
        phrase = segment[first.start() : last.end()].strip()
        if not phrase or embedded_acronym(phrase):
            continue
        signature = phrase_signature(phrase)
        if signature_matches(acronym, signature):
            absolute_start = segment_start + first.start()
            absolute_end = segment_start + last.end()
            return phrase, absolute_start, absolute_end
    return None


def extend_inline_wrapper(text: str, start: int, end: int) -> tuple[int, int]:
    changed = True
    while changed:
        changed = False
        for marker in ("**", "__", "*", "_"):
            marker_start = start - len(marker)
            if marker_start < 0 or text[marker_start:start] != marker:
                continue
            closing = text.find(marker, start)
            if closing == -1 or closing > end:
                continue
            if closing == end:
                end += len(marker)
            start = marker_start
            changed = True
            break
        if changed:
            continue
        prefix_start = max(0, start - 80)
        prefix = text[prefix_start:start]
        command = re.search(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?\{$", prefix)
        if command:
            command_start = prefix_start + command.start()
            opening = start - 1
            closing = scan_balanced(text, opening, "{", "}")
            if closing is not None and closing < end:
                start = command_start
                changed = True
            elif closing is not None and closing == end:
                start = command_start
                end = closing + 1
                changed = True
    return start, end


def plain_full_form(visible_phrase: str) -> str:
    return " ".join(match.group(0) for match in TOKEN_RE.finditer(visible_phrase))


def source_form_is_balanced(source_form: str) -> bool:
    depth = 0
    for index, char in enumerate(source_form):
        if is_escaped(source_form, index):
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    if depth != 0:
        return False
    source_form = re.sub(r"\\[*_]", "", source_form)
    for marker in ("**", "__"):
        if source_form.count(marker) % 2:
            return False
        source_form = source_form.replace(marker, "")
    return source_form.count("*") % 2 == 0 and source_form.count("_") % 2 == 0


def partial_expansion_before(text: str, paren_start: int, acronym: str) -> tuple[str, int] | None:
    lower_bound = max(0, paren_start - 160)
    lookback = text[lower_bound:paren_start]
    tokens = list(TOKEN_RE.finditer(lookback))
    key = acronym_key(acronym)
    for size in range(1, min(6, len(tokens)) + 1):
        first = tokens[-size]
        last = tokens[-1]
        phrase = lookback[first.start() : last.end()].strip()
        signature = phrase_signature(phrase)
        if signature and len(signature) < len(key) and key.endswith(signature):
            return phrase, lower_bound + first.start()
    return None


def clip_evidence(text: str, limit: int | None = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if limit is None:
        return compact
    return compact if len(compact) <= limit else compact[: limit - 3] + "..."


def make_finding(
    rule_id: str,
    check: str,
    path: str,
    source_map: SourceMap,
    offset: int,
    scope: str,
    message: str,
    evidence: str,
    *,
    span: dict[str, int] | None = None,
    replacement: str | None = None,
    evidence_limit: int | None = 180,
) -> dict[str, object]:
    line, _ = source_map.point(offset)
    result: dict[str, object] = {
        "rule_id": rule_id,
        "check": check,
        "path": path,
        "line": line,
        "scope": scope,
        "message": message,
        "evidence": clip_evidence(evidence, evidence_limit),
    }
    if span is not None:
        result["span"] = span
    if replacement is not None:
        result["replacement"] = replacement
    return result


def extract_definitions(
    scopes: Sequence[Scope],
    path: str,
    source_map: SourceMap,
) -> tuple[list[Definition], list[dict[str, object]], list[tuple[int, int]]]:
    definitions: list[Definition] = []
    partials: list[dict[str, object]] = []
    partial_ranges: list[tuple[int, int]] = []
    markdown = FORMAT_BY_SUFFIX.get(Path(path).suffix.lower()) == "markdown"
    for scope in scopes:
        masked = mask_inline_markup(scope.text, markdown=markdown)
        for match in PAREN_ACRONYM_RE.finditer(masked):
            acronym = match.group("acronym")
            if not is_acronym(acronym):
                continue
            expansion = expansion_before(masked, match.start(), acronym)
            acronym_start = scope.start_offset + match.start("acronym")
            paren_start = scope.start_offset + match.start()
            paren_end = scope.start_offset + match.end()
            if expansion:
                visible_form, local_start, local_end = expansion
                source_start, source_end = extend_inline_wrapper(
                    scope.text, local_start, local_end
                )
                full_form = plain_full_form(visible_form)
                definitions.append(
                    Definition(
                        acronym=acronym,
                        key=acronym_key(acronym),
                        full_form=full_form,
                        source_form=scope.text[source_start:source_end],
                        source_form_safe=source_form_is_balanced(
                            scope.text[source_start:source_end]
                        ),
                        normalized_full_form=re.sub(r"\s+", " ", full_form).strip().lower(),
                        scope_id=scope.scope_id,
                        full_start=scope.start_offset + source_start,
                        acronym_start=acronym_start,
                        paren_start=paren_start,
                        paren_end=paren_end,
                    )
                )
                continue
            partial = partial_expansion_before(masked, match.start(), acronym)
            if partial:
                phrase, _ = partial
                partials.append(
                    make_finding(
                        "ACR_PARTIAL_EXPANSION",
                        "acronym",
                        path,
                        source_map,
                        acronym_start,
                        scope.scope_id,
                        "The parenthetical acronym is only partially expanded.",
                        f"{phrase} ({acronym})",
                    )
                )
                partial_ranges.append((paren_start, paren_end))
    return definitions, partials, partial_ranges


def occurrence_inside(offset: int, ranges: Iterable[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in ranges)


def find_unbound_full_form(text: str, before: int, acronym: str) -> tuple[str, int] | None:
    start = max(0, before - 600)
    segment = text[start:before]
    tokens = list(TOKEN_RE.finditer(segment))
    target = acronym_key(acronym)
    best: tuple[str, int] | None = None
    for end_index in range(len(tokens)):
        for size in range(2, min(7, end_index + 2)):
            first = tokens[end_index - size + 1]
            last = tokens[end_index]
            phrase = segment[first.start() : last.end()]
            if embedded_acronym(phrase):
                continue
            if phrase_signature(phrase) == target:
                best = (phrase, start + first.start())
    return best


def audit_acronyms(
    text: str,
    scopes: Sequence[Scope],
    path: str,
    source_map: SourceMap,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    definitions, partials, partial_ranges = extract_definitions(scopes, path, source_map)
    safe: list[dict[str, object]] = []
    review = list(partials)
    unresolved: list[dict[str, object]] = []
    markdown = FORMAT_BY_SUFFIX.get(Path(path).suffix.lower()) == "markdown"

    forms_by_key: dict[str, dict[str, Definition]] = {}
    for definition in definitions:
        forms_by_key.setdefault(definition.key, {})[definition.normalized_full_form] = definition

    conflicting = {key for key, forms in forms_by_key.items() if len(forms) > 1}
    for key in sorted(conflicting):
        first = min(forms_by_key[key].values(), key=lambda item: item.acronym_start)
        forms = sorted(item.full_form for item in forms_by_key[key].values())
        unresolved.append(
            make_finding(
                "ACR_CONFLICTING_MAPPING",
                "acronym",
                path,
                source_map,
                first.acronym_start,
                first.scope_id,
                "The manuscript contains conflicting explicit expansions for one acronym.",
                f"{first.acronym}: " + " | ".join(forms),
            )
        )

    valid_ranges_by_scope: dict[str, list[tuple[int, int, str]]] = {}
    for definition in definitions:
        valid_ranges_by_scope.setdefault(definition.scope_id, []).append(
            (definition.paren_start, definition.paren_end, definition.key)
        )

    for scope in scopes:
        masked = mask_inline_markup(scope.text, markdown=markdown)
        occurrences: dict[str, list[tuple[AcronymOccurrence, int]]] = {}
        for occurrence in iter_acronym_occurrences(masked):
            absolute = scope.start_offset + occurrence.start
            occurrences.setdefault(acronym_key(occurrence.token), []).append(
                (occurrence, absolute)
            )

        for key, entries in sorted(occurrences.items()):
            occurrence, absolute = entries[0]
            token = occurrence.token
            valid_here = any(
                start <= absolute < end and definition_key == key
                for start, end, definition_key in valid_ranges_by_scope.get(scope.scope_id, [])
            )
            if valid_here:
                if scope.kind == "abstract" and len(entries) == 1 and key not in conflicting:
                    definition = next(
                        item
                        for item in definitions
                        if item.scope_id == scope.scope_id and item.key == key and item.paren_start <= absolute < item.paren_end
                    )
                    finding = make_finding(
                        "ACR_ABSTRACT_SINGLE_USE",
                        "acronym",
                        path,
                        source_map,
                        definition.full_start,
                        scope.scope_id,
                        "An acronym used once in the abstract can remain written in full.",
                        text[definition.full_start : definition.paren_end],
                    )
                    if definition.source_form_safe:
                        finding["span"] = source_map.span(
                            definition.full_start, definition.paren_end
                        )
                        finding["replacement"] = definition.source_form
                        safe.append(finding)
                    else:
                        finding["rule_id"] = "ACR_FORMATTED_DEFINITION_REVIEW"
                        finding["message"] = (
                            "The single-use abstract definition has nontrivial formatting; "
                            "remove the acronym only after checking the markup."
                        )
                        review.append(finding)
                continue
            if occurrence_inside(absolute, partial_ranges):
                continue
            if key in conflicting:
                continue

            forms = forms_by_key.get(key, {})
            if len(forms) == 1:
                definition = next(iter(forms.values()))
                safe.append(
                    make_finding(
                        "ACR_SCOPE_REDEFINITION",
                        "acronym",
                        path,
                        source_map,
                        absolute,
                        scope.scope_id,
                        "This independent scope uses the acronym before defining it.",
                        token,
                        span=source_map.span(absolute, absolute + len(token)),
                        replacement=f"{definition.full_form} ({token})",
                    )
                )
                continue

            unbound = find_unbound_full_form(masked, occurrence.start, token)
            if unbound:
                phrase, phrase_offset = unbound
                review.append(
                    make_finding(
                        "ACR_FULL_FORM_UNBOUND",
                        "acronym",
                        path,
                        source_map,
                        scope.start_offset + phrase_offset,
                        scope.scope_id,
                        "A likely full form appears without binding the later acronym; confirm the intended mapping.",
                        f"{phrase} ... {token}",
                    )
                )
            else:
                review.append(
                    make_finding(
                        "ACR_UNDEFINED",
                        "acronym",
                        path,
                        source_map,
                        absolute,
                        scope.scope_id,
                        "No unique explicit expansion was found for this scope.",
                        token,
                    )
                )
    return safe, review, unresolved


def audit_captions(
    scopes: Sequence[Scope], path: str, source_map: SourceMap
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for scope in scopes:
        if scope.kind not in {"caption", "table_caption"}:
            continue
        plain = re.sub(r"\\[A-Za-z@]+\*?", "", scope.text)
        words = re.findall(r"[A-Za-z0-9]+", plain)
        if len(words) < 8:
            findings.append(
                make_finding(
                    "CAPTION_TOO_SHORT",
                    "caption",
                    path,
                    source_map,
                    scope.start_offset,
                    scope.scope_id,
                    "The caption is too short to establish a self-contained reading.",
                    scope.text,
                )
            )
        panels = list(re.finditer(r"\([a-z]\)", plain, re.I))
        if len(panels) >= 2 and len(words) < 18:
            findings.append(
                make_finding(
                    "CAPTION_PANEL_UNEXPLAINED",
                    "caption",
                    path,
                    source_map,
                    scope.start_offset + panels[0].start(),
                    scope.scope_id,
                    "Multiple panel labels appear without enough text to explain each panel.",
                    scope.text,
                )
            )
        statistical = re.search(r"\b(?:whiskers?|error bars?|shaded (?:area|region)|boxes?)\b", plain, re.I)
        definition_cue = re.search(
            r"\b(?:denote|denotes|indicate|indicates|represent|represents|correspond|percentile|median|minimum|maximum|standard deviation|confidence|interquartile|IQR)\b",
            plain,
            re.I,
        )
        if statistical and not definition_cue:
            findings.append(
                make_finding(
                    "CAPTION_STATISTIC_UNDEFINED",
                    "caption",
                    path,
                    source_map,
                    scope.start_offset + statistical.start(),
                    scope.scope_id,
                    "A statistical encoding is named without defining what it represents.",
                    statistical.group(0),
                )
            )
    return findings


def audit_language_boundaries(
    scopes: Sequence[Scope], path: str, source_map: SourceMap
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    review: list[dict[str, object]] = []
    protected: list[dict[str, object]] = []
    markdown = FORMAT_BY_SUFFIX.get(Path(path).suffix.lower()) == "markdown"
    for scope in scopes:
        if scope.kind not in {"abstract", "body", "caption", "table_caption"}:
            continue
        masked = mask_inline_markup(scope.text, markdown=markdown)
        if scope.kind in {"abstract", "body"}:
            for pattern in DEFENSIVE_PATTERNS:
                for match in pattern.finditer(masked):
                    review.append(
                        make_finding(
                            "LANG_DEFENSIVE_OR_META",
                            "defensive_language",
                            path,
                            source_map,
                            scope.start_offset + match.start(),
                            scope.scope_id,
                            "Rewrite this defensive or meta-discourse phrase as a direct factual statement.",
                            match.group(0),
                        )
                    )
        for pattern in PROTECTED_PATTERNS:
            for match in pattern.finditer(masked):
                protected.append(
                    make_finding(
                        "LANG_SCIENTIFIC_QUALIFIER",
                        "defensive_language",
                        path,
                        source_map,
                        scope.start_offset + match.start(),
                        scope.scope_id,
                        "Preserve this scientific boundary unless the underlying evidence changes.",
                        match.group(0),
                    )
                )
    return review, protected


def mask_markdown_tables(text: str) -> str:
    """Mask pipe tables without changing offsets or line structure."""

    buffer = list(text)
    lines: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        lines.append((offset, offset + len(line), line))
        offset += len(line)

    delimiter = re.compile(
        r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
    )
    masked_lines: set[int] = set()
    for index, (_, _, line) in enumerate(lines):
        content = line.rstrip("\r\n")
        if not delimiter.fullmatch(content):
            continue
        masked_lines.add(index)
        if index > 0 and "|" in lines[index - 1][2]:
            masked_lines.add(index - 1)
        following = index + 1
        while following < len(lines):
            row = lines[following][2].rstrip("\r\n")
            if not row.strip() or "|" not in row:
                break
            masked_lines.add(following)
            following += 1

    for index, (_, _, line) in enumerate(lines):
        if re.match(r"^\s*\|.*\|\s*(?:\r?\n)?$", line):
            masked_lines.add(index)

    for index in masked_lines:
        start, end, _ = lines[index]
        replace_range(buffer, start, end)
    return "".join(buffer)


def mask_latex_table_environments(text: str) -> str:
    """Mask table bodies while leaving separately parsed captions available."""

    table_environments = {
        "array",
        "longtable",
        "longtblr",
        "table",
        "table*",
        "sidewaystable",
        "sidewaystable*",
        "supertabular",
        "tabu",
        "tabular",
        "tabular*",
        "tabularx",
        "tblr",
    }

    def is_table_environment(name: str) -> bool:
        normalized = name.lower()
        return (
            normalized in table_environments
            or "table" in normalized
            or "tabular" in normalized
        )

    buffer = list(text)
    stack: list[tuple[str, int]] = []
    command = re.compile(r"\\(?P<kind>begin|end)\s*\{(?P<name>[A-Za-z@]+\*?)\}")
    for match in command.finditer(text):
        name = match.group("name").lower()
        if not is_table_environment(name):
            continue
        if match.group("kind") == "begin":
            stack.append((name, match.start()))
            continue
        matching_index = next(
            (index for index in range(len(stack) - 1, -1, -1) if stack[index][0] == name),
            None,
        )
        if matching_index is None:
            continue
        start = stack[matching_index][1]
        replace_range(buffer, start, match.end())
        del stack[matching_index:]
    for _, start in stack:
        replace_range(buffer, start, len(buffer))
    return "".join(buffer)


def mask_latex_structure_commands(text: str) -> str:
    return mask_matches(
        text,
        (re.compile(r"\\(?:begin|end)\s*\{[^{}]*\}"),),
    )


def markdown_list_item_ranges(text: str) -> list[tuple[int, int, int]]:
    lines: list[tuple[int, int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        lines.append((offset, offset + len(line), line))
        offset += len(line)
    marker = re.compile(r"^ {0,3}(?:[-+*]|\d+[.)])\s+")
    ranges: list[tuple[int, int, int]] = []
    for index, (start, end, line) in enumerate(lines):
        match = marker.match(line)
        if not match:
            continue
        item_end = end
        following = index + 1
        while following < len(lines):
            _, continuation_end, continuation = lines[following]
            if not continuation.strip() or marker.match(continuation):
                break
            if re.match(
                r"^ {0,3}(?:#{1,6}\s+|>|```|~~~|<\s*/?(?:table|pre|code|h[1-6])\b)",
                continuation,
                re.I,
            ):
                break
            item_end = continuation_end
            following += 1
        ranges.append((start, item_end, start + match.end()))
    return ranges


def latex_list_item_ranges(text: str) -> list[tuple[int, int, int]]:
    markers = list(
        re.finditer(r"\\item(?![A-Za-z@])(?:\s*\[[^\]\n]*\])?\s*", text)
    )
    environment_end = re.compile(r"\\end\s*\{(?:itemize|enumerate|description)\}")
    ranges: list[tuple[int, int, int]] = []
    for index, marker in enumerate(markers):
        candidates = [len(text)]
        if index + 1 < len(markers):
            candidates.append(markers[index + 1].start())
        closing = environment_end.search(text, marker.end())
        if closing:
            candidates.append(closing.start())
        ranges.append((marker.start(), min(candidates), marker.end()))
    return ranges


def protect_sentence_periods(text: str, *, caption: bool) -> str:
    buffer = list(text)
    for match in NO_NUMBER_RE.finditer(text):
        buffer[match.start("period")] = " "
    for match in re.finditer(r"(?<=\d)\.(?=\d)", text):
        buffer[match.start()] = " "
    if caption:
        prefix = re.match(
            r"\s*(?:(?:fig(?:ure)?\.?|table)\s+"
            r"[A-Z0-9]+(?:\s*\([A-Za-z0-9]+\))*\s*[.:])",
            text,
            re.I,
        )
        if prefix:
            for index in range(prefix.start(), prefix.end()):
                if buffer[index] in ".?!":
                    buffer[index] = " "
    return "".join(buffer)


def append_sentence_units(
    units: list[SentenceUnit],
    scope: Scope,
    source_text: str,
    visible: str,
    start: int,
    end: int,
    *,
    allow_unterminated: bool,
) -> None:
    if end <= start:
        return
    segment = visible[start:end]
    segmentation = protect_sentence_periods(
        segment,
        caption=scope.kind in {"caption", "table_caption"},
    )

    def add(local_start: int, local_end: int) -> None:
        candidate = visible[start + local_start : start + local_end]
        first = re.search(r"\S", candidate)
        if not first:
            return
        trailing = re.search(r"\S(?=\s*$)", candidate)
        if not trailing:
            return
        unit_start = start + local_start + first.start()
        unit_end = start + local_start + trailing.end()
        unit_visible = visible[unit_start:unit_end]
        if not re.search(r"[A-Za-z]", unit_visible):
            return
        absolute_start = scope.start_offset + unit_start
        absolute_end = scope.start_offset + unit_end
        units.append(
            SentenceUnit(
                scope.scope_id,
                absolute_start,
                absolute_end,
                source_text[absolute_start:absolute_end],
                unit_visible,
            )
        )

    matches = list(NEGATION_SENTENCE_RE.finditer(segmentation))
    for match in matches:
        add(match.start(), match.end())
    if allow_unterminated:
        trailing_start = matches[-1].end() if matches else 0
        if re.search(r"[A-Za-z]", segmentation[trailing_start:]):
            add(trailing_start, len(segment))


def extract_negation_sentence_units(
    scopes: Sequence[Scope], source_text: str, *, markdown: bool
) -> list[SentenceUnit]:
    units: list[SentenceUnit] = []
    for scope in scopes:
        if scope.kind not in {"abstract", "body", "caption", "table_caption"}:
            continue
        if markdown:
            visible = mask_markdown_tables(
                mask_markdown_raw_html(
                    mask_inline_markup(scope.text, markdown=True)
                )[0]
            )
        else:
            visible = mask_latex_table_environments(scope.text)
            visible = mask_latex_structure_commands(visible)
            visible = mask_inline_markup(visible, markdown=False)

        if scope.kind in {"caption", "table_caption"}:
            append_sentence_units(
                units,
                scope,
                source_text,
                visible,
                0,
                len(visible),
                allow_unterminated=True,
            )
            continue

        item_ranges = (
            markdown_list_item_ranges(visible)
            if markdown
            else latex_list_item_ranges(scope.text)
        )
        prose_buffer = list(visible)
        for item_start, item_end, content_start in item_ranges:
            append_sentence_units(
                units,
                scope,
                source_text,
                visible,
                content_start,
                item_end,
                allow_unterminated=True,
            )
            replace_range(prose_buffer, item_start, item_end)

        prose = "".join(prose_buffer)
        for paragraph in re.finditer(
            r"(?:^|\n\s*\n)(?P<body>.*?)(?=\n\s*\n|$)", prose, re.S
        ):
            body = paragraph.group("body")
            if not body.strip():
                continue
            start = paragraph.start("body")
            append_sentence_units(
                units,
                scope,
                source_text,
                prose,
                start,
                start + len(body),
                allow_unterminated=False,
            )
    return sorted(units, key=lambda item: (item.start, item.end, item.scope_id))


def range_is_occupied(occupied: Sequence[bool], start: int, end: int) -> bool:
    return any(occupied[start:end])


def occupy_range(occupied: list[bool], start: int, end: int) -> None:
    for index in range(max(0, start), min(end, len(occupied))):
        occupied[index] = True


def find_negative_hits(text: str) -> list[NegativeHit]:
    occupied = [False] * len(text)
    hits: list[NegativeHit] = []

    for match in NO_NUMBER_RE.finditer(text):
        occupy_range(occupied, match.start(), match.end())

    paired_not = re.compile(r"\bnot\b(?=\s+only\b)", re.I)
    for match in paired_not.finditer(text):
        if re.search(
            r"\bbut\b.*?\balso\b",
            text[match.end() :],
            re.I | re.S,
        ):
            occupy_range(occupied, match.start(), match.end())

    pending_neither: list[re.Match[str]] = []
    for token in re.finditer(r"\b(?:neither|nor)\b", text, re.I):
        if token.group(0).lower() == "neither":
            pending_neither.append(token)
            continue
        if not pending_neither:
            continue
        pending_neither_match = pending_neither.pop()
        if not range_is_occupied(
            occupied, pending_neither_match.start(), pending_neither_match.end()
        ) and not range_is_occupied(occupied, token.start(), token.end()):
            occupy_range(
                occupied,
                pending_neither_match.start(),
                pending_neither_match.end(),
            )
            occupy_range(occupied, token.start(), token.end())
            hits.append(
                NegativeHit(
                    pending_neither_match.start(),
                    token.end(),
                    f"{pending_neither_match.group(0)} ... {token.group(0)}",
                    "coordination",
                )
            )

    def collect(patterns: Sequence[re.Pattern[str]], category: str) -> None:
        for pattern in patterns:
            for match in pattern.finditer(text):
                if range_is_occupied(occupied, match.start(), match.end()):
                    continue
                occupy_range(occupied, match.start(), match.end())
                hits.append(
                    NegativeHit(
                        match.start(),
                        match.end(),
                        clip_evidence(match.group(0), None),
                        category,
                    )
                )

    collect(FIXED_INDIRECT_PATTERNS, "fixed_indirect")
    collect(NEGATIVE_AUXILIARY_PATTERNS, "atomic")

    for match in FAIL_TO_PATTERN.finditer(text):
        fail_start, fail_end = match.span("fail")
        to_start, to_end = match.span("to")
        if range_is_occupied(occupied, fail_start, fail_end) or range_is_occupied(
            occupied, to_start, to_end
        ):
            continue
        occupy_range(occupied, fail_start, fail_end)
        occupy_range(occupied, to_start, to_end)
        hits.append(
            NegativeHit(
                fail_start,
                to_end,
                f"{match.group('fail')} ... {match.group('to')}",
                "atomic",
            )
        )

    collect(ATOMIC_NEGATIVE_PATTERNS, "atomic")
    return sorted(hits, key=lambda item: (item.start, item.end, item.category))


def audit_negation_chains(
    scopes: Sequence[Scope], text: str, path: str, source_map: SourceMap
) -> list[dict[str, object]]:
    markdown = FORMAT_BY_SUFFIX.get(Path(path).suffix.lower()) == "markdown"
    units = extract_negation_sentence_units(scopes, text, markdown=markdown)
    findings: list[dict[str, object]] = []
    for unit in units:
        hits = find_negative_hits(unit.visible_text)
        if not hits:
            continue
        fixed_indirect = any(hit.category == "fixed_indirect" for hit in hits)
        if not fixed_indirect and len(hits) < 2:
            continue
        normalized_sentence = clip_evidence(unit.source_text, None)
        hit_evidence = "; ".join(
            f'"{clip_evidence(hit.text, None)}" [{hit.category}]' for hit in hits
        )
        findings.append(
            make_finding(
                "LANG_NEGATION_CHAIN",
                "negative_construction",
                path,
                source_map,
                unit.start + hits[0].start,
                unit.scope_id,
                "Review this indirect or repeated negative construction; do not rewrite it automatically.",
                f"Sentence: {normalized_sentence} | Hits: {hit_evidence}",
                evidence_limit=None,
            )
        )
    return findings


def sentence_words(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Za-z0-9]+", text.lower()))


def extract_sentences(
    scopes: Sequence[Scope], source_text: str, *, markdown: bool
) -> list[Sentence]:
    sentences: list[Sentence] = []
    paragraph_id = 0
    for scope in scopes:
        if scope.kind not in {"abstract", "body"}:
            continue
        masked = mask_inline_markup(scope.text, markdown=markdown)
        for paragraph in re.finditer(r"(?:^|\n\s*\n)(?P<body>.*?)(?=\n\s*\n|$)", masked, re.S):
            body = paragraph.group("body")
            body_start = paragraph.start("body")
            if not body.strip() or re.match(r"\s*(?:[-*+] |\|)", body):
                paragraph_id += 1
                continue
            for match in SENTENCE_RE.finditer(body):
                start = scope.start_offset + body_start + match.start()
                end = scope.start_offset + body_start + match.end()
                original = source_text[start:end].strip()
                words = sentence_words(original)
                if len(words) < 6:
                    continue
                sentences.append(Sentence(scope.scope_id, paragraph_id, start, end, original, words))
            paragraph_id += 1
    return sorted(sentences, key=lambda item: (item.start, item.end, item.scope_id))


def jaccard(left: Sequence[str], right: Sequence[str]) -> float:
    left_set, right_set = set(left), set(right)
    union = left_set | right_set
    return 0.0 if not union else len(left_set & right_set) / len(union)


def audit_repetition(
    scopes: Sequence[Scope], text: str, path: str, source_map: SourceMap
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    safe: list[dict[str, object]] = []
    review: list[dict[str, object]] = []
    markdown = FORMAT_BY_SUFFIX.get(Path(path).suffix.lower()) == "markdown"
    sentences = extract_sentences(scopes, text, markdown=markdown)
    safe_pairs: set[tuple[int, int]] = set()
    safe_duplicate_starts: set[int] = set()

    for left, right in zip(sentences, sentences[1:]):
        if (
            left.scope_id != "body"
            or right.scope_id != "body"
            or left.paragraph != right.paragraph
            or left.text != right.text
        ):
            continue
        safe_pairs.add((left.start, right.start))
        safe_duplicate_starts.add(right.start)
        safe.append(
            make_finding(
                "REPETITION_ADJACENT_EXACT",
                "repetition",
                path,
                source_map,
                right.start,
                right.scope_id,
                "This sentence exactly duplicates the immediately preceding sentence.",
                right.text,
                span=source_map.span(left.end, right.end),
                replacement="",
            )
        )

    candidate_count = 0
    for right_index, right in enumerate(sentences):
        if candidate_count >= 50:
            break
        if right.start in safe_duplicate_starts:
            continue
        for left in sentences[:right_index]:
            if left.start in safe_duplicate_starts:
                continue
            if (left.start, right.start) in safe_pairs:
                continue
            if len(set(left.words) | set(right.words)) < 8:
                continue
            score = jaccard(left.words, right.words)
            if score < 0.85:
                continue
            review.append(
                make_finding(
                    "REPETITION_POTENTIAL_CLUSTER",
                    "repetition",
                    path,
                    source_map,
                    right.start,
                    right.scope_id,
                    "These non-adjacent sentences may repeat the same function; review before compressing.",
                    f"line {source_map.point(left.start)[0]}: {left.text} || line {source_map.point(right.start)[0]}: {right.text}",
                )
            )
            candidate_count += 1
            break
    return safe, review


def stable_sort(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        findings,
        key=lambda item: (
            str(item.get("path", "")).lower(),
            int(item.get("line", 0)),
            str(item.get("rule_id", "")),
            str(item.get("scope", "")),
        ),
    )


def audit_supported_language(
    scopes: Sequence[Scope], path: str, source_map: SourceMap
) -> list[dict[str, object]]:
    for scope in scopes:
        match = re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", scope.text)
        if match:
            return [
                unresolved_finding(
                    path,
                    source_map,
                    scope.start_offset + match.start(),
                    "INPUT_NON_ENGLISH_TEXT",
                    "Convention audit v1 supports English manuscripts only; non-English visible text requires manual review.",
                    match.group(0),
                    scope.scope_id,
                )
            ]
    return []


def empty_categories() -> dict[str, list[dict[str, object]]]:
    return {name: [] for name in CATEGORY_NAMES}


def parse_error_report(path: Path, code: str, message: str, line: int | None = None) -> dict[str, object]:
    categories = empty_categories()
    error: dict[str, object] = {"code": code, "message": message}
    if line is not None:
        error["line"] = line
    suffix = path.suffix.lower()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "parse_error",
        "input": {"path": str(path.resolve()), "sha256": None, "format": FORMAT_BY_SUFFIX.get(suffix)},
        "scopes": [],
        **categories,
        "counts": {**{name: 0 for name in CATEGORY_NAMES}, "total": 0},
        "error": error,
    }


def audit_path(path: Path) -> dict[str, object]:
    suffix = path.suffix.lower()
    if suffix not in FORMAT_BY_SUFFIX:
        return parse_error_report(path, "unsupported_format", "Only Markdown and LaTeX inputs are supported.")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return parse_error_report(path, "input_unreadable", str(exc))
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        line = payload[: exc.start].count(b"\n") + 1
        return parse_error_report(path, "invalid_utf8", str(exc), line)
    if not text.strip():
        return parse_error_report(path, "empty_input", "The manuscript is empty.")

    resolved_path = str(path.resolve())
    source_map = SourceMap(text)
    format_name = FORMAT_BY_SUFFIX[suffix]
    try:
        if format_name == "markdown":
            scopes, parser_unresolved = parse_markdown(text, source_map, resolved_path)
        else:
            scopes, parser_unresolved = parse_latex(text, source_map, resolved_path)
    except (IndexError, ValueError) as exc:
        return parse_error_report(path, "structure_parse_failed", str(exc))
    parser_unresolved.extend(audit_supported_language(scopes, resolved_path, source_map))

    safe_acronyms, review_acronyms, unresolved_acronyms = audit_acronyms(
        text, scopes, resolved_path, source_map
    )
    caption_findings = audit_captions(scopes, resolved_path, source_map)
    defensive_findings, protected = audit_language_boundaries(scopes, resolved_path, source_map)
    negation_findings = audit_negation_chains(scopes, text, resolved_path, source_map)
    safe_repetition, review_repetition = audit_repetition(scopes, text, resolved_path, source_map)

    categories = {
        "safe_findings": stable_sort(safe_acronyms + safe_repetition),
        "review_candidates": stable_sort(
            review_acronyms
            + caption_findings
            + defensive_findings
            + negation_findings
            + review_repetition
        ),
        "protected_qualifiers": stable_sort(protected),
        "unresolved": stable_sort(parser_unresolved + unresolved_acronyms),
    }
    counts = {name: len(categories[name]) for name in CATEGORY_NAMES}
    counts["total"] = sum(counts.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "clean" if counts["total"] == 0 else "has_findings",
        "input": {"path": resolved_path, "sha256": sha256_bytes(payload), "format": format_name},
        "scopes": [
            {
                "id": scope.scope_id,
                "kind": scope.kind,
                "start_line": source_map.point(scope.start_offset)[0],
            }
            for scope in scopes
        ],
        **categories,
        "counts": counts,
        "error": None,
    }


def markdown_report(report: dict[str, object]) -> str:
    input_info = report["input"]
    lines = [
        "# Manuscript Convention Audit",
        "",
        f"- Schema version: `{report['schema_version']}`",
        f"- Status: `{report['status']}`",
        f"- Input: `{input_info['path']}`",
        f"- SHA-256: `{input_info['sha256'] or 'unavailable'}`",
    ]
    if report["status"] == "parse_error":
        error = report["error"]
        lines.extend(
            [
                "",
                "## Error",
                "",
                f"- [{input_info['path']}:{error.get('line', 0)}] `{error['code']}` {error['message']}",
            ]
        )
        return "\n".join(lines) + "\n"

    headings = (
        ("Safe Findings", "safe_findings"),
        ("Review Candidates", "review_candidates"),
        ("Protected Qualifiers", "protected_qualifiers"),
        ("Unresolved", "unresolved"),
    )
    for title, key in headings:
        lines.extend(["", f"## {title}", ""])
        entries = report[key]
        if not entries:
            lines.append("- None.")
            continue
        for item in entries:
            lines.append(
                f"- [{item['path']}:{item['line']}] `{item['rule_id']}` ({item['scope']}) "
                f"{item['message']} Evidence: {item['evidence']}"
            )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 Markdown or single-file LaTeX manuscript")
    parser.add_argument("--format", dest="output_format", choices=("json", "markdown"), default="json")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit_path(args.input)
    if args.output_format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(markdown_report(report), end="")
    return {"clean": 0, "has_findings": 1, "parse_error": 2}[str(report["status"])]


if __name__ == "__main__":
    raise SystemExit(main())
