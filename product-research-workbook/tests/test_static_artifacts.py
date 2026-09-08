from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class StaticArtifactTests(unittest.TestCase):
    def test_skill_metadata_and_references_exist(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: product-research-workbook", skill)
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("按工程形态和专用指标把不同组件类型拆成各自子表", skill)
        self.assertIn("整机参数表时，在`字段设计`把它的`工作表顺序`设为 `1`", skill)
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue((SKILL_ROOT / "references" / "workbook-contract.md").is_file())
        self.assertTrue((SKILL_ROOT / "references" / "acceptance-and-release.md").is_file())
        contract = (SKILL_ROOT / "references" / "workbook-contract.md").read_text(encoding="utf-8")
        self.assertIn("严格匹配 `CAND-0001` 形式", contract)
        self.assertIn("整机参数表设为 `1`", contract)
        self.assertIn("不同组件类型按工程形态和专用指标分别成表", contract)
        self.assertIn("整机存在时位于第一个参数子表", contract)
        self.assertTrue((SKILL_ROOT / "scripts" / "scan_legacy_identifiers.py").is_file())
        self.assertTrue((SKILL_ROOT / "scripts" / "inspect_product_samples.py").is_file())

    def test_evals_are_well_formed_and_cover_routing_boundaries(self) -> None:
        evals = json.loads((SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(evals["skill_name"], "product-research-workbook")
        self.assertIn("临时", evals["execution_note"])
        cases = evals["evals"]
        self.assertEqual(len({item["id"] for item in cases}), len(cases))
        for item in cases:
            with self.subTest(eval_id=item["id"]):
                self.assertIsInstance(item["id"], int)
                for field in ("prompt", "expected_output"):
                    self.assertIsInstance(item[field], str)
                    self.assertTrue(item[field].strip())
                self.assertIsInstance(item["expectations"], list)
                self.assertTrue(item["expectations"])
                self.assertTrue(all(isinstance(text, str) and text.strip() for text in item["expectations"]))
        scenarios = {item["scenario"] for item in cases if "scenario" in item}
        self.assertTrue({
            "one_off_comparison", "one_off_procurement", "small_maintained_catalog",
            "readonly_catalog_audit", "format_only", "existing_catalog_update",
            "material_ambiguity",
        }.issubset(scenarios))
        # Explicit historical task instructions remain special cases, not defaults.
        original = {item["id"]: item for item in cases}
        self.assertIn("用户已说明历史人工前缀序号没有必要保留", original[2]["prompt"])
        self.assertIn("必须等待用户确认字段和证据标准", original[3]["prompt"])
        self.assertIn("Excel 原生兼容性检查", original[4]["prompt"])

    def test_trigger_evals_are_well_formed_with_both_decisions(self) -> None:
        trigger_evals = json.loads(
            (SKILL_ROOT / "evals" / "trigger-evals.json").read_text(encoding="utf-8")
        )
        self.assertTrue(trigger_evals)
        self.assertEqual(len({item["query"] for item in trigger_evals}), len(trigger_evals))
        for item in trigger_evals:
            self.assertIsInstance(item["query"], str)
            self.assertTrue(item["query"].strip())
            self.assertIs(type(item["should_trigger"]), bool)
        self.assertEqual({item["should_trigger"] for item in trigger_evals}, {True, False})

    def test_local_markdown_references_resolve(self) -> None:
        # Documentation changes must not leave broken skill-local links.
        for document in [SKILL_ROOT / "SKILL.md", *(SKILL_ROOT / "references").glob("*.md")]:
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                relative = target.split("#", 1)[0].strip("<>")
                if relative:
                    with self.subTest(document=document.name, target=target):
                        self.assertTrue((document.parent / relative).exists())


if __name__ == "__main__":
    unittest.main()
