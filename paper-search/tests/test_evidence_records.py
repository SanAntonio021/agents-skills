from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
SCRIPT_PATH = SKILL_ROOT / "scripts" / "evidence_records.py"
SPEC = importlib.util.spec_from_file_location("evidence_records", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample_payload() -> dict:
    return {
        "query": "mountain energy inspection",
        "records": [
            {
                "title": "A Verified Journal Study on Mountain Energy Inspection",
                "authors": ["Li Ming", "Ana Doe"],
                "publish_date": "2024-05-08",
                "journal": "Journal of Field Systems",
                "url": "https://publisher.example/paper?utm_source=test",
                "doi": "https://doi.org/10.1234/ABC.2024.7",
                "relevance": "Directly evaluates the requested inspection setting.",
                "relevance_score": 0.95,
                "verification_status": "primary-source-verified",
            },
            {
                "title": "A Verified Journal Study on Mountain Energy Inspection",
                "url": "https://publisher.example/paper?utm_campaign=duplicate",
                "notes": "PMID: 12345678, published in 2024.",
                "relevance": "Duplicate discovery record for the same work.",
                "verification_status": "discovery-only",
            },
            {
                "title": "Proceedings Paper for Remote Asset Monitoring",
                "year": "2022",
                "venue": "International Conference on Field Systems",
                "url": "https://conference.example/proceedings/item",
                "relevance": "Provides a related monitoring method.",
                "relevance_score": 0.5,
                "verification_status": "metadata-verified",
            },
        ],
    }


def citation_payload() -> dict:
    return {
        "query": "verified citation records",
        "records": [
            {
                "title": "A Complete Journal Citation for Deterministic Tests",
                "authors": [
                    "Alice Alpha",
                    "Bob Beta",
                    "Carol Gamma",
                    "David Delta",
                    "Eve Epsilon",
                    "Frank Zeta",
                    "Grace Eta",
                ],
                "source_type": "journal-article",
                "journal": "Journal of Citation Systems",
                "volume": "42",
                "issue": "7",
                "pages": "101-115",
                "publication_date": "2025-07",
                "doi": "HTTPS://doi.org/10.5555/ABC.Def",
                "url": "https://publisher.example/journal-paper",
                "relevance": "Exercises complete journal metadata.",
                "verification_status": "primary-source-verified",
                "field_sources": {"doi": "publisher", "pages": "publisher"},
                "original_citation": "Original journal reference text.",
            },
            {
                "title": "A Conference Paper with Six Verified Authors",
                "authors": [
                    "Hao One",
                    "Iris Two",
                    "Jun Three",
                    "Kai Four",
                    "Lin Five",
                    "Ming Six",
                ],
                "source_type": "conference-paper",
                "conference": "International Conference on Citation Tests",
                "pages": "22-29",
                "publication_date": "2024-09-12",
                "doi": "10.5555/conf.2024.2",
                "url": "https://conference.example/paper",
                "relevance": "Exercises conference and six-author rendering.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "An Early Access Article Identified by Article Number",
                "authors": ["Nora Solo"],
                "source_type": "early-access",
                "journal": "IEEE Test Journal",
                "article_number": "5500123",
                "publication_date": "2026-02-01",
                "doi": "10.5555/early.2026.3",
                "url": "https://publisher.example/early-access",
                "relevance": "Exercises Early Access without invented volume or pages.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "A Preprint Citation with an arXiv Identifier",
                "authors": ["Omar Preprint"],
                "source_type": "preprint",
                "arxiv_id": "2601.01234",
                "publication_date": "2026-01-03",
                "url": "https://arxiv.org/abs/2601.01234",
                "relevance": "Exercises preprint metadata.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Citation Testing as a Book",
                "authors": ["Paula Writer"],
                "source_type": "book",
                "publisher": "Test Press",
                "publication_date": "2023",
                "isbn": "978-1-23456-789-0",
                "url": "https://publisher.example/book",
                "relevance": "Exercises book metadata.",
                "verification_status": "metadata-verified",
            },
            {
                "title": "Citation Testing in an Edited Book",
                "authors": ["Quinn Chapter"],
                "source_type": "book-chapter",
                "book_title": "Handbook of Citation Tests",
                "publisher": "Test Press",
                "pages": "50-71",
                "publication_date": "2022",
                "isbn": "978-1-23456-700-5",
                "url": "https://publisher.example/chapter",
                "relevance": "Exercises book-chapter metadata.",
                "verification_status": "metadata-verified",
            },
            {
                "title": "Reference Data Exchange Test Standard",
                "authors": ["Test Standards Association"],
                "source_type": "standard",
                "publisher": "Test Standards Association",
                "publication_date": "2021",
                "url": "https://standards.example/standard",
                "relevance": "Exercises standard metadata.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Annual Citation Verification Report",
                "authors": ["Test Research Institute"],
                "source_type": "report",
                "publisher": "Test Research Institute",
                "publication_date": "2020-11",
                "url": "https://institute.example/report",
                "relevance": "Exercises report metadata.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Online Citation Verification Data",
                "authors": ["Test Data Office"],
                "source_type": "online-resource",
                "publisher": "Test Data Office",
                "publication_date": "2019-04-02",
                "accessed_date": "2026-09-01",
                "url": "https://data.example/citation",
                "relevance": "Exercises online metadata and access date.",
                "verification_status": "primary-source-verified",
            },
        ],
    }


def collect_issue_codes(value: object) -> list[str]:
    codes: list[str] = []
    if isinstance(value, dict):
        if isinstance(value.get("code"), str):
            codes.append(value["code"])
        for item in value.values():
            codes.extend(collect_issue_codes(item))
    elif isinstance(value, list):
        for item in value:
            codes.extend(collect_issue_codes(item))
    return codes


class EvidenceRecordTests(unittest.TestCase):
    def test_input_requires_array_or_record_container(self) -> None:
        with self.assertRaises(MODULE.EvidenceRecordError):
            MODULE.build_output("not-an-object")
        with self.assertRaises(MODULE.EvidenceRecordError):
            MODULE.build_output({"query": "missing records"})

    def test_record_requires_title_relevance_and_locator(self) -> None:
        base = {"title": "Valid title", "relevance": "Direct match", "doi": "10.1234/x"}
        for missing in ("title", "relevance", "doi"):
            record = dict(base)
            del record[missing]
            with self.subTest(missing=missing), self.assertRaises(MODULE.EvidenceRecordError):
                MODULE.build_output([record])

    def test_extracts_and_normalizes_identifiers_and_year(self) -> None:
        output = MODULE.build_output(sample_payload())
        first = output["records"][0]
        self.assertEqual(first["doi"], "10.1234/abc.2024.7")
        self.assertEqual(first["pmid"], "12345678")
        self.assertEqual(first["year"], "2024")
        self.assertEqual(first["url"], "https://publisher.example/paper")

    def test_classifies_deduplicates_and_sorts(self) -> None:
        output = MODULE.build_output(sample_payload())
        self.assertEqual(output["coverage"]["input_records"], 3)
        self.assertEqual(output["coverage"]["unique_records"], 2)
        self.assertEqual(output["coverage"]["duplicates_removed"], 1)
        self.assertEqual(output["records"][0]["source_type"], "journal-article")
        self.assertEqual(output["records"][0]["verification_status"], "primary-source-verified")
        self.assertEqual(output["records"][1]["source_type"], "conference-paper")
        self.assertEqual([item["record_id"] for item in output["records"]], ["E001", "E002"])

    def test_unknown_year_and_conservative_default_status(self) -> None:
        output = MODULE.build_output(
            [
                {
                    "title": "A discoverable but not yet verified source",
                    "url": "https://index.example/item",
                    "relevance": "Potentially related to the requested mechanism.",
                }
            ]
        )
        record = output["records"][0]
        self.assertEqual(record["year"], "")
        self.assertEqual(record["verification_status"], "discovery-only")
        self.assertEqual(output["coverage"]["missing_year"], 1)

    def test_rejects_unknown_status_and_invalid_score(self) -> None:
        record = {
            "title": "A valid evidence title",
            "doi": "10.1234/test",
            "relevance": "Direct match.",
        }
        with self.assertRaises(MODULE.EvidenceRecordError):
            MODULE.build_output([{**record, "verification_status": "certain"}])
        with self.assertRaises(MODULE.EvidenceRecordError):
            MODULE.build_output([{**record, "relevance_score": "high"}])

    def test_renders_all_formats_deterministically(self) -> None:
        output = MODULE.build_output(sample_payload())
        json_text = MODULE.render_output(output, "json")
        markdown = MODULE.render_output(output, "markdown")
        bibtex = MODULE.render_output(output, "bibtex")
        self.assertEqual(json.loads(json_text)["coverage"]["unique_records"], 2)
        self.assertIn("| ID | 题名 | 年份 | 类型 |", markdown)
        self.assertIn("DOI: `10.1234/abc.2024.7`", markdown)
        self.assertIn("@article{", bibtex)
        self.assertIn("doi = {10.1234/abc.2024.7}", bibtex)
        self.assertEqual(json_text, MODULE.render_output(output, "json"))

    def test_cli_stdout_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "records.json"
            output_path = root / "nested" / "records.md"
            input_path.write_text(json.dumps(sample_payload()), encoding="utf-8")
            stdout_run = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--input", str(input_path), "--format", "json"],
                text=True,
                capture_output=True,
                check=False,
                encoding="utf-8",
            )
            self.assertEqual(stdout_run.returncode, 0, stdout_run.stderr)
            self.assertEqual(json.loads(stdout_run.stdout)["query"], "mountain energy inspection")
            file_run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(input_path),
                    "--format",
                    "markdown",
                    "--output",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=False,
                encoding="utf-8",
            )
            self.assertEqual(file_run.returncode, 0, file_run.stderr)
            self.assertTrue(output_path.is_file())
            self.assertEqual(file_run.stdout, "")

    def test_script_uses_only_non_network_standard_library_imports(self) -> None:
        script_paths = sorted(SCRIPTS_ROOT.glob("*.py"))
        self.assertGreaterEqual(len(script_paths), 2)
        forbidden_imports = {
            "aiohttp",
            "crossrefapi",
            "httpx",
            "pybliometrics",
            "requests",
            "semanticscholar",
            "socket",
            "urllib3",
        }
        network_calls = ("urlopen(", "http.client", "urllib.request", "requests.", "httpx.")
        credential_markers = ("api_key", "api-key", "authorization:", "bearer ")
        for script_path in script_paths:
            source = script_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            with self.subTest(script=script_path.name):
                self.assertTrue(imported.isdisjoint(forbidden_imports))
                lowered = source.lower()
                for marker in network_calls + credential_markers:
                    self.assertNotIn(marker, lowered)

    def test_v1_input_remains_compatible_and_v2_fields_are_preserved(self) -> None:
        legacy = MODULE.build_output(sample_payload())
        self.assertEqual(legacy["schema_version"], 2)
        self.assertEqual(legacy["records"][0]["authors"], "Li Ming and Ana Doe")

        output = MODULE.build_output(citation_payload(), order="input")
        record = output["records"][0]
        self.assertEqual(record["author_list"][0], "Alice Alpha")
        self.assertEqual(record["journal"], "Journal of Citation Systems")
        self.assertEqual(record["volume"], "42")
        self.assertEqual(record["issue"], "7")
        self.assertEqual(record["pages"], "101-115")
        self.assertEqual(record["publication_date"], "2025-07")
        self.assertEqual(record["field_sources"]["doi"], [{"source": "publisher"}])
        self.assertEqual(record["original_citation"], "Original journal reference text.")

    def test_ieee_author_threshold_and_supported_source_types(self) -> None:
        output = MODULE.build_output(citation_payload(), order="input")
        ieee = MODULE.render_output(output, "ieee")
        lines = ieee.splitlines()
        self.assertEqual(len(lines), 9)
        self.assertTrue(all(line.startswith(f"[{index}] ") for index, line in enumerate(lines, 1)))
        self.assertIn("et al.", lines[0])
        self.assertNotIn("et al.", lines[1])
        self.assertNotIn("et al.", lines[2])
        for expected in (
            "Journal of Citation Systems",
            "International Conference on Citation Tests",
            "IEEE Test Journal",
            "arXiv",
            "Test Press",
            "Test Standards Association",
            "Test Research Institute",
            "https://data.example/citation",
        ):
            self.assertIn(expected, ieee)

    def test_duplicate_author_names_are_preserved_and_reported(self) -> None:
        authors = ["Alice Author", "Bob Writer", "Alice Author"]
        output = MODULE.build_output(
            [
                {
                    "title": "A Paper Whose Source Repeats an Author Name",
                    "authors": authors,
                    "journal": "Journal of Author Metadata",
                    "year": "2025",
                    "doi": "10.5555/authors.duplicate",
                    "relevance": "Tests conservative handling of repeated author metadata.",
                    "verification_status": "primary-source-verified",
                }
            ]
        )
        record = output["records"][0]
        self.assertEqual(record["author_list"], authors)
        duplicate_issues = [
            issue for issue in record["issues"] if issue["code"] == "author_sequence_duplicate"
        ]
        self.assertEqual(len(duplicate_issues), 1)
        self.assertIn("未自动删除", duplicate_issues[0]["message"])
        self.assertEqual(duplicate_issues[0]["values"], authors)

    def test_ieee_uses_pages_or_article_number_without_invention(self) -> None:
        output = MODULE.build_output(citation_payload(), order="input")
        lines = MODULE.render_output(output, "ieee").splitlines()
        self.assertIn("101–115", lines[0])
        self.assertIn("5500123", lines[2])
        self.assertNotIn("vol.", lines[2].lower())
        self.assertNotIn("pp.", lines[2].lower())

    def test_doi_forms_and_invalid_doi_are_handled_conservatively(self) -> None:
        payload = {
            "records": [
                {
                    "title": "Valid DOI URL Form for a Journal Article",
                    "relevance": "Tests DOI URL normalization.",
                    "url": "https://publisher.example/valid-doi",
                    "doi": "HTTPS://DOI.ORG/10.5555/AbC.XyZ",
                    "source_type": "journal-article",
                    "verification_status": "metadata-verified",
                },
                {
                    "title": "Invalid DOI Text Must Not Become an Identifier",
                    "relevance": "Tests conservative invalid DOI handling.",
                    "url": "https://publisher.example/invalid-doi",
                    "doi": "this-is-not-a-doi",
                    "source_type": "journal-article",
                    "verification_status": "metadata-verified",
                },
            ]
        }
        output = MODULE.build_output(payload, order="input")
        self.assertEqual(output["records"][0]["doi"], "10.5555/abc.xyz")
        self.assertEqual(output["records"][1]["doi"], "")

    def test_published_version_absorbs_preprint_without_losing_identifiers(self) -> None:
        title = "One Scientific Work with a Preprint and Published Version"
        output = MODULE.build_output(
            {
                "records": [
                    {
                        "title": title,
                        "authors": ["Alice Author"],
                        "source_type": "preprint",
                        "url": "https://arxiv.org/abs/2501.01234",
                        "arxiv_id": "2501.01234",
                        "publication_date": "2025-01",
                        "relevance": "Preprint version of the same work.",
                        "verification_status": "primary-source-verified",
                    },
                    {
                        "title": title,
                        "authors": ["Alice Author"],
                        "source_type": "journal-article",
                        "journal": "Journal of Published Versions",
                        "doi": "10.5555/published.2025.1",
                        "url": "https://publisher.example/published",
                        "publication_date": "2025-06",
                        "relevance": "Published version of the same work.",
                        "verification_status": "primary-source-verified",
                    },
                ]
            },
            order="input",
        )
        self.assertEqual(output["coverage"]["unique_records"], 1)
        record = output["records"][0]
        self.assertEqual(record["source_type"], "journal-article")
        self.assertFalse(record["preprint"])
        self.assertIn("2501.01234", [record["arxiv_id"], *record["alternate_arxiv_ids"]])
        self.assertIn("https://arxiv.org/abs/2501.01234", record["alternate_urls"])

    def test_bibtex_matches_doi_before_title_and_reports_all_problem_classes(self) -> None:
        payload = {
            "records": [
                {
                    "title": "Verified DOI-Matched Paper",
                    "authors": ["Alice Author"],
                    "journal": "Correct Journal",
                    "volume": "8",
                    "issue": "2",
                    "pages": "10-20",
                    "publication_date": "2024",
                    "doi": "10.5555/match.1",
                    "url": "https://publisher.example/match",
                    "relevance": "Tests DOI-first BibTeX matching.",
                    "verification_status": "primary-source-verified",
                },
                {
                    "title": "Title Fallback Match without a DOI",
                    "authors": ["Bob Author"],
                    "journal": "Fallback Journal",
                    "volume": "3",
                    "publication_date": "2023",
                    "url": "https://publisher.example/fallback",
                    "relevance": "Tests title fallback matching.",
                    "verification_status": "primary-source-verified",
                },
            ]
        }
        bibtex = r'''
@string{fallback = "Fallback Journal"}
@article{doiFirst,
  title = {A Different Title in the Existing Entry},
  author = {Alice Author},
  journal = {Wrong Journal},
  year = {2024},
  doi = {https://doi.org/10.5555/MATCH.1}
}
@article{titleFallback,
  title = {Title Fallback Match without a DOI},
  author = {Bob Author},
  journal = fallback,
  year = {2023}
}
@article{unmatched,
  title = {An Entry Not Present in the Verified Records},
  year = {2022},
  doi = {10.5555/unmatched.9}
}
'''
        output = MODULE.build_output(payload, order="input", bibtex_text=bibtex)
        codes = collect_issue_codes(output)
        self.assertIn("bibtex_field_mismatch", codes)
        self.assertIn("bibtex_field_missing", codes)
        self.assertIn("bibtex_entry_unmatched", codes)
        self.assertIn("bibtex_parse_unresolved", codes)
        first_issues = output["records"][0]["issues"]
        self.assertTrue(
            any(issue["code"] == "bibtex_field_mismatch" and issue["field"] == "title" for issue in first_issues)
        )
        self.assertFalse(any(issue["code"] == "bibtex_entry_unmatched" for issue in first_issues))

    def test_conflicting_field_sources_are_reported_without_guessing(self) -> None:
        output = MODULE.build_output(
            {
                "records": [
                    {
                        "title": "A Paper with Conflicting Publication Years",
                        "authors": ["Alice Author"],
                        "journal": "Journal of Source Conflicts",
                        "year": "2024",
                        "doi": "10.5555/conflict.1",
                        "url": "https://publisher.example/conflict",
                        "relevance": "Tests field-level source conflict reporting.",
                        "verification_status": "primary-source-verified",
                        "field_sources": {
                            "year": [
                                {"source": "publisher", "value": "2024"},
                                {"source": "crossref", "value": "2023"},
                            ]
                        },
                    }
                ]
            }
        )
        record = output["records"][0]
        self.assertEqual(record["year"], "2024")
        conflicts = [issue for issue in record["issues"] if issue["code"] == "source_conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["field"], "year")
        self.assertIn("2024", conflicts[0]["message"])
        self.assertIn("2023", conflicts[0]["message"])

    def test_missing_citation_metadata_keeps_every_record_and_lists_plain_issues(self) -> None:
        payload = {
            "records": [
                {
                    "title": "A Journal Paper Missing Most Citation Fields",
                    "url": "https://publisher.example/incomplete-one",
                    "relevance": "Tests incomplete citation delivery.",
                    "source_type": "journal-article",
                    "verification_status": "metadata-verified",
                },
                {
                    "title": "A Conference Paper with Only a Stable URL",
                    "url": "https://conference.example/incomplete-two",
                    "relevance": "Tests that a second incomplete item is retained.",
                    "source_type": "conference-paper",
                    "verification_status": "metadata-verified",
                },
            ]
        }
        output = MODULE.build_output(payload, order="input")
        self.assertEqual(output["coverage"]["input_records"], 2)
        self.assertEqual(output["coverage"]["unique_records"], 2)
        self.assertTrue(all(record["issues"] for record in output["records"]))
        messages = " ".join(
            issue["message"] for record in output["records"] for issue in record["issues"]
        )
        self.assertIn("未查到", messages)
        ieee = MODULE.render_output(output, "ieee")
        self.assertIn("A Journal Paper Missing Most Citation Fields", ieee)
        self.assertIn("A Conference Paper with Only a Stable URL", ieee)
        markdown = MODULE.render_output(output, "markdown")
        self.assertIn("## 引用问题", markdown)
        self.assertIn("citation_field_missing", markdown)
        self.assertIn("未查到", markdown)

    def test_input_order_is_optional_and_ranked_order_remains_default(self) -> None:
        payload = {
            "records": [
                {
                    "title": "First in the Existing Reference List",
                    "doi": "10.5555/order.first",
                    "relevance": "Original first item.",
                    "relevance_score": 0.1,
                    "verification_status": "metadata-verified",
                },
                {
                    "title": "Second but More Relevant Search Result",
                    "doi": "10.5555/order.second",
                    "relevance": "Original second item.",
                    "relevance_score": 0.9,
                    "verification_status": "primary-source-verified",
                },
            ]
        }
        ranked = MODULE.build_output(payload)
        preserved = MODULE.build_output(payload, order="input")
        self.assertEqual(ranked["records"][0]["title"], "Second but More Relevant Search Result")
        self.assertEqual(preserved["records"][0]["title"], "First in the Existing Reference List")

    def test_cli_supports_ieee_input_order_and_bibtex_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "records.json"
            bibtex_path = root / "existing.bib"
            output_path = root / "references.txt"
            input_path.write_text(json.dumps(citation_payload()), encoding="utf-8")
            bibtex_path.write_text(
                "@article{first, title={A Complete Journal Citation for Deterministic Tests}, doi={10.5555/abc.def}}\n",
                encoding="utf-8",
            )
            run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(input_path),
                    "--format",
                    "ieee",
                    "--order",
                    "input",
                    "--bibtex-input",
                    str(bibtex_path),
                    "--output",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=False,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            rendered = output_path.read_text(encoding="utf-8")
            self.assertTrue(rendered.startswith("[1] "))
            self.assertIn("A Complete Journal Citation for Deterministic Tests", rendered)

    def test_cli_bibtex_patch_preserves_order_keys_macros_and_unmatched_raw_entries(self) -> None:
        payload = {
            "records": [
                {
                    "title": "Macro Matched Paper",
                    "authors": ["Alice Smith"],
                    "journal": "Journal of Tests",
                    "journal_abbreviation": "J. Tests",
                    "year": "2024",
                    "doi": "10.5555/macro.1",
                    "url": "https://publisher.example/macro",
                    "relevance": "Matches the bare-macro entry by DOI.",
                    "verification_status": "primary-source-verified",
                },
                {
                    "title": "Simple Matched Paper",
                    "authors": ["Bob Writer"],
                    "journal": "Verified Journal",
                    "year": "2023",
                    "pages": "11-19",
                    "doi": "10.5555/simple.2",
                    "url": "https://publisher.example/simple",
                    "relevance": "Matches the simple entry by DOI.",
                    "verification_status": "primary-source-verified",
                },
            ]
        }
        bibtex = r'''@string{JTEST = "Journal of Tests"}

@article{macroKey,
  title = {Macro Matched Paper},
  author = {Alice Smith},
  journal = JTEST,
  year = {2024},
  doi = {10.5555/macro.1}
}

@article{unmatchedKey,
  title = {Unmatched Existing Entry},
  author = {Una Matched},
  year = {2022},
  doi = {10.5555/unmatched.9}
}

@article{simpleKey,
  title = {Simple Matched Paper},
  author = {Bob Writer},
  journal = {Old Journal},
  year = {2023},
  pages = {11--19},
  doi = {10.5555/simple.2}
}
'''
        macro_block = r'''@article{macroKey,
  title = {Macro Matched Paper},
  author = {Alice Smith},
  journal = JTEST,
  year = {2024},
  doi = {10.5555/macro.1}
}'''
        unmatched_block = r'''@article{unmatchedKey,
  title = {Unmatched Existing Entry},
  author = {Una Matched},
  year = {2022},
  doi = {10.5555/unmatched.9}
}'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "records.json"
            bibtex_path = root / "existing.bib"
            output_path = root / "patched.bib"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            bibtex_path.write_text(bibtex, encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--input",
                    str(input_path),
                    "--format",
                    "bibtex",
                    "--order",
                    "input",
                    "--bibtex-input",
                    str(bibtex_path),
                    "--output",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=False,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            rendered = output_path.read_text(encoding="utf-8")

        self.assertIn('@string{JTEST = "Journal of Tests"}', rendered)
        self.assertIn(macro_block, rendered)
        self.assertIn(unmatched_block, rendered)
        self.assertEqual(rendered.count("@article{macroKey,"), 1)
        self.assertEqual(rendered.count("@article{unmatchedKey,"), 1)
        self.assertEqual(rendered.count("@article{simpleKey,"), 1)
        self.assertLess(rendered.index("@string{JTEST"), rendered.index("@article{macroKey"))
        self.assertLess(rendered.index("@article{macroKey"), rendered.index("@article{unmatchedKey"))
        self.assertLess(rendered.index("@article{unmatchedKey"), rendered.index("@article{simpleKey"))
        self.assertIn("journal = {Verified Journal},", rendered)
        self.assertIn("pages = {11--19},", rendered)

    def test_bibtex_nested_braces_and_backslashes_are_preserved_exactly(self) -> None:
        payload = [
            {
                "title": "A {THz} Paper",
                "authors": ["Alice Smith"],
                "journal": "Journal of THz Tests",
                "year": "2025",
                "doi": "10.5555/thz.braces",
                "url": "https://publisher.example/thz-braces",
                "relevance": "Tests lossless handling of TeX syntax.",
                "verification_status": "primary-source-verified",
            }
        ]
        source = r'''@article{nestedKey,
  title = {A {THz} Paper},
  author = {Smith, Alice},
  journal = {Journal of THz Tests},
  year = {2025},
  note = {uses \alpha},
  doi = {10.5555/thz.braces}
}
'''
        output = MODULE.build_output(payload, order="input", bibtex_text=source)
        rendered = MODULE.render_output(output, "bibtex")
        self.assertEqual(rendered, source)
        self.assertEqual(rendered.count("@article{nestedKey,"), 1)
        self.assertIn("title = {A {THz} Paper}", rendered)
        self.assertIn(r"note = {uses \alpha}", rendered)

    def test_bibtex_equivalent_author_and_venue_are_not_rewritten(self) -> None:
        payload = [
            {
                "title": "Equivalent Author and Venue Forms",
                "authors": ["Alice Smith"],
                "journal": "Journal of Citation Tests",
                "journal_abbreviation": "J. Citation Tests",
                "volume": "9",
                "issue": "4",
                "pages": "101-115",
                "year": "2025",
                "doi": "10.5555/equivalent.1",
                "url": "https://publisher.example/equivalent",
                "relevance": "Tests semantic equality without cosmetic rewriting.",
                "verification_status": "primary-source-verified",
            }
        ]
        source = r'''@article{keepForms,
  title = {Equivalent Author and Venue Forms},
  author = {Smith, Alice},
  journal = {J. Citation Tests},
  volume = {9},
  number = {4},
  pages = {101--115},
  year = {2025},
  doi = {10.5555/equivalent.1}
}
'''
        output = MODULE.build_output(payload, order="input", bibtex_text=source)
        author_mismatches = [
            issue
            for issue in output["records"][0]["issues"]
            if issue["code"] == "bibtex_field_mismatch" and issue["field"] == "authors"
        ]
        venue_mismatches = [
            issue
            for issue in output["records"][0]["issues"]
            if issue["code"] == "bibtex_field_mismatch" and issue["field"] == "venue"
        ]
        self.assertEqual(author_mismatches, [])
        self.assertEqual(venue_mismatches, [])
        rendered = MODULE.render_output(output, "bibtex")
        self.assertIn("author = {Smith, Alice},", rendered)
        self.assertIn("journal = {J. Citation Tests},", rendered)
        self.assertIn("pages = {101--115},", rendered)
        self.assertEqual(rendered.count("@article{keepForms,"), 1)

    def test_ieee_exact_golden_references(self) -> None:
        records = [
            {
                "title": "A THz Link",
                "authors": ["Smith, Alice"],
                "source_type": "journal-article",
                "journal": "Journal Full Name",
                "journal_abbreviation": "J. Full",
                "volume": "9",
                "issue": "4",
                "pages": "101-115",
                "publication_date": "2025-07",
                "doi": "10.5555/j.1",
                "relevance": "Journal golden case.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "An EA Paper",
                "authors": ["Alice Smith"],
                "source_type": "early-access",
                "journal": "IEEE Journal Full Name",
                "journal_abbreviation": "IEEE J. Test",
                "article_number": "5500123",
                "publication_date": "2025-07-03",
                "doi": "10.5555/ea.1",
                "relevance": "Early Access golden case.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Data Portal",
                "authors": ["Data Office"],
                "source_type": "online-resource",
                "publisher": "Data Office",
                "publication_date": "2024-05-06",
                "accessed_date": "2026-09-01",
                "url": "https://example.org/data",
                "relevance": "Online resource golden case.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Test Standard",
                "authors": ["Standards Org"],
                "source_type": "standard",
                "standard_number": "IEEE Std 1234-2025",
                "publisher": "Standards Org",
                "publication_place": "New York, NY, USA",
                "publication_date": "2025",
                "url": "https://example.org/std",
                "relevance": "Standard golden case.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Annual THz Report",
                "authors": ["Test Institute"],
                "source_type": "report",
                "publisher": "Test Institute",
                "publication_place": "Chengdu, China",
                "report_number": "TR-9",
                "publication_date": "2024-10",
                "url": "https://example.org/report",
                "relevance": "Report golden case.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Citation Systems",
                "authors": ["Alice Writer"],
                "source_type": "book",
                "publisher": "Test Press",
                "publication_place": "New York, NY, USA",
                "edition": "2nd ed.",
                "publication_date": "2023",
                "isbn": "978-1",
                "url": "https://example.org/book",
                "relevance": "Book golden case.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "THz Chapter",
                "authors": ["Bob Chapter"],
                "source_type": "book-chapter",
                "book_title": "Handbook of THz",
                "editors": ["Editor, Eva"],
                "publisher": "Test Press",
                "publication_place": "London, U.K.",
                "edition": "3rd ed.",
                "publication_date": "2022",
                "chapter": "4",
                "pages": "50-71",
                "url": "https://example.org/chapter",
                "relevance": "Book chapter golden case.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": "Conference THz Paper",
                "authors": ["Alice Smith"],
                "source_type": "conference-paper",
                "conference": "International Conference Full Name",
                "conference_abbreviation": "Int. Conf. Test",
                "publication_place": "Chengdu, China",
                "publication_date": "2025-08-12",
                "pages": "1-9",
                "url": "https://example.org/conf",
                "relevance": "Conference golden case.",
                "verification_status": "primary-source-verified",
            },
        ]
        output = MODULE.build_output(records, order="input")
        self.assertEqual(
            MODULE.render_output(output, "ieee").splitlines(),
            [
                "[1] A. Smith, “A THz Link,” J. Full, vol. 9, no. 4, pp. 101–115, Jul. 2025, doi: 10.5555/j.1.",
                "[2] A. Smith, “An EA Paper,” IEEE J. Test, early access, Jul. 3, 2025, Art. no. 5500123, doi: 10.5555/ea.1.",
                "[3] Data Office. “Data Portal.” Data Office. May 6, 2024. Accessed: Sep. 1, 2026. [Online]. Available: https://example.org/data",
                "[4] Test Standard, IEEE Std 1234-2025, Standards Org, New York, NY, USA, 2025. [Online]. Available: https://example.org/std",
                "[5] Test Institute, “Annual THz Report,” Chengdu, China, Rep. TR-9, Oct. 2024. [Online]. Available: https://example.org/report",
                "[6] A. Writer, Citation Systems, 2nd ed., New York, NY, USA: Test Press, 2023, ISBN 978-1. [Online]. Available: https://example.org/book",
                "[7] B. Chapter, “THz Chapter,” in Handbook of THz, E. Editor, Ed., 3rd ed., London, U.K.: Test Press, 2022, ch. 4, pp. 50–71. [Online]. Available: https://example.org/chapter",
                "[8] A. Smith, “Conference THz Paper,” in Proc. Int. Conf. Test, Chengdu, China, Aug. 12, 2025, pp. 1–9. [Online]. Available: https://example.org/conf",
            ],
        )
        for line in MODULE.render_output(output, "ieee").splitlines()[2:]:
            self.assertFalse(line.endswith("."))

    def test_ieee_report_and_website_section_t_exact_golden(self) -> None:
        output = MODULE.build_output(
            [
                {
                    "title": "THz Measurement Report",
                    "authors": ["Alice Smith"],
                    "source_type": "report",
                    "publisher": "Example Research Company",
                    "publication_place": "Chengdu, China",
                    "report_number": "TR-2025-7",
                    "publication_date": "2025-07-03",
                    "accessed_date": "2026-09-01",
                    "url": "https://example.org/report-company",
                    "relevance": "Checks report company, city, number, date, and access order.",
                    "verification_status": "primary-source-verified",
                },
                {
                    "title": "Institute Annual Report",
                    "authors": ["Test Institute"],
                    "source_type": "report",
                    "publisher": "Test Institute",
                    "publication_place": "Beijing, China",
                    "report_number": "Rep-18",
                    "publication_date": "2024-10",
                    "accessed_date": "2026-08-31",
                    "url": "https://example.org/report-institute",
                    "relevance": "Checks that an institutional author is not repeated as publisher.",
                    "verification_status": "primary-source-verified",
                },
                {
                    "title": "Spectrum Data Portal",
                    "authors": ["Data Office"],
                    "source_type": "online-resource",
                    "publisher": "Data Office",
                    "publication_date": "2024-05-06",
                    "accessed_date": "2026-09-01",
                    "url": "https://example.org/spectrum-data",
                    "relevance": "Checks IEEE Section T website sentence structure.",
                    "verification_status": "primary-source-verified",
                },
            ],
            order="input",
        )
        lines = MODULE.render_output(output, "ieee").splitlines()
        self.assertEqual(
            lines,
            [
                "[1] A. Smith, “THz Measurement Report,” Example Research Company, Chengdu, China, Rep. TR-2025-7, Jul. 3, 2025. Accessed: Sep. 1, 2026. [Online]. Available: https://example.org/report-company",
                "[2] Test Institute, “Institute Annual Report,” Beijing, China, Rep. Rep-18, Oct. 2024. Accessed: Aug. 31, 2026. [Online]. Available: https://example.org/report-institute",
                "[3] Data Office. “Spectrum Data Portal.” Data Office. May 6, 2024. Accessed: Sep. 1, 2026. [Online]. Available: https://example.org/spectrum-data",
            ],
        )
        self.assertEqual(lines[1].count("Test Institute"), 1)
        self.assertEqual(lines[2].count("Data Office."), 2)
        self.assertTrue(all(not line.endswith(".") for line in lines))

    def test_ieee_journal_article_number_uses_exact_field_order(self) -> None:
        output = MODULE.build_output(
            [
                {
                    "title": "Article Number Ordering",
                    "authors": ["Alice Smith"],
                    "source_type": "journal-article",
                    "journal": "Journal Full Name",
                    "journal_abbreviation": "J. Test",
                    "volume": "9",
                    "issue": "4",
                    "article_number": "5500123",
                    "publication_date": "2025-07",
                    "doi": "10.5555/article.5500123",
                    "relevance": "Checks exact IEEE article-number ordering.",
                    "verification_status": "primary-source-verified",
                }
            ]
        )
        self.assertEqual(
            MODULE.render_output(output, "ieee"),
            "[1] A. Smith, “Article Number Ordering,” J. Test, vol. 9, no. 4, Jul. 2025, Art. no. 5500123, doi: 10.5555/article.5500123.\n",
        )

    def test_same_title_and_authors_with_different_dois_are_not_merged(self) -> None:
        title = "Same Long Scientific Title but Distinct Published Articles"
        records = [
            {
                "title": title,
                "authors": ["Alice Smith"],
                "source_type": "journal-article",
                "journal": "Journal One",
                "year": "2025",
                "doi": "10.5555/distinct.one",
                "relevance": "First distinct article.",
                "verification_status": "primary-source-verified",
            },
            {
                "title": title,
                "authors": ["Alice Smith"],
                "source_type": "journal-article",
                "journal": "Journal Two",
                "year": "2025",
                "doi": "10.5555/distinct.two",
                "relevance": "Second distinct article.",
                "verification_status": "primary-source-verified",
            },
        ]
        output = MODULE.build_output(records, order="input")
        self.assertEqual(output["coverage"]["unique_records"], 2)
        self.assertEqual(output["duplicate_groups"], [])
        self.assertEqual([record["doi"] for record in output["records"]], ["10.5555/distinct.one", "10.5555/distinct.two"])
        self.assertTrue(
            all(
                any(issue["code"] == "duplicate_identity_conflict" for issue in record["issues"])
                for record in output["records"]
            )
        )

    def test_correction_and_retraction_records_remain_separate(self) -> None:
        base = {
            "title": "A Published Work with Status-Specific Records",
            "authors": ["Alice Smith"],
            "source_type": "journal-article",
            "journal": "Journal of Record Status",
            "year": "2024",
            "doi": "10.5555/status.1",
            "relevance": "Tests status-aware identity handling.",
            "verification_status": "primary-source-verified",
        }
        output = MODULE.build_output(
            [base, {**base, "corrected": True}, {**base, "retracted": True}],
            order="input",
        )
        self.assertEqual(output["coverage"]["unique_records"], 3)
        self.assertEqual(output["duplicate_groups"], [])
        self.assertEqual([record["corrected"] for record in output["records"]], [False, True, False])
        self.assertEqual([record["retracted"] for record in output["records"]], [False, False, True])

    def test_preprint_merges_into_early_access_and_records_duplicate_mapping(self) -> None:
        title = "A Preprint Later Released as an Early Access Article"
        output = MODULE.build_output(
            [
                {
                    "title": title,
                    "authors": ["Alice Smith"],
                    "source_type": "preprint",
                    "arxiv_id": "2412.01234",
                    "url": "https://arxiv.org/abs/2412.01234",
                    "publication_date": "2024-12",
                    "relevance": "Preprint version.",
                    "verification_status": "primary-source-verified",
                },
                {
                    "title": title,
                    "authors": ["Alice Smith"],
                    "source_type": "early-access",
                    "journal": "IEEE Journal of Early Access Tests",
                    "article_number": "5500123",
                    "doi": "10.5555/ea.merge",
                    "url": "https://publisher.example/ea-merge",
                    "publication_date": "2025-01-03",
                    "relevance": "Early Access version.",
                    "verification_status": "primary-source-verified",
                },
            ],
            order="input",
        )
        self.assertEqual(output["coverage"]["unique_records"], 1)
        record = output["records"][0]
        self.assertEqual(record["source_type"], "early-access")
        self.assertFalse(record["preprint"])
        self.assertEqual(record["merged_input_indices"], [1, 2])
        self.assertEqual(
            output["duplicate_groups"],
            [{"record_id": "E001", "merged_input_indices": [1, 2]}],
        )
        self.assertEqual(record["doi"], "10.5555/ea.merge")
        self.assertIn("2412.01234", [record["arxiv_id"], *record["alternate_arxiv_ids"]])

    def test_duplicate_mapping_for_exact_identifier_merge(self) -> None:
        output = MODULE.build_output(sample_payload(), order="input")
        first = output["records"][0]
        self.assertEqual(first["merged_input_indices"], [1, 2])
        self.assertEqual(
            output["duplicate_groups"],
            [{"record_id": "E001", "merged_input_indices": [1, 2]}],
        )


if __name__ == "__main__":
    unittest.main()
