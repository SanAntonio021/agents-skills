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
        tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(
            imported,
            {"__future__", "argparse", "json", "re", "sys", "collections", "pathlib", "typing", "urllib"},
        )


if __name__ == "__main__":
    unittest.main()
