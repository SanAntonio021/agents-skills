from __future__ import annotations

import json
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


class StaticArtifactTests(unittest.TestCase):
    def test_skill_metadata_and_references_exist(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: product-research-workbook", skill)
        self.assertLessEqual(len(skill.splitlines()), 500)
        self.assertIn("不引用具体旧值", skill)
        self.assertIn("按工程形态和专用指标把不同组件类型拆成各自子表", skill)
        self.assertIn("整机参数表时，在`字段设计`把它的`工作表顺序`设为 `1`", skill)
        self.assertNotIn("才在只读审计中引用具体旧值", skill)
        self.assertTrue((SKILL_ROOT / "agents" / "openai.yaml").is_file())
        self.assertTrue((SKILL_ROOT / "references" / "workbook-contract.md").is_file())
        self.assertTrue((SKILL_ROOT / "references" / "acceptance-and-release.md").is_file())
        contract = (SKILL_ROOT / "references" / "workbook-contract.md").read_text(encoding="utf-8")
        self.assertIn("不在新输出中复述或引用具体旧值", contract)
        self.assertNotIn("只有用户明确要求定位原始单元格时才引用它", contract)
        self.assertIn("不迁入过程账本或正式工作簿", contract)
        self.assertIn("不建立旧号到新号的内部映射", contract)
        self.assertIn("不写入`样本依据`或复核备注", contract)
        self.assertIn("不生成 CSV/JSON 映射键", contract)
        self.assertIn("交付前全文扫描", contract)
        self.assertIn("严格匹配 `CAND-0001` 形式", contract)
        self.assertIn("立即丢弃的定位控制列", contract)
        self.assertIn("先跳过该编号列的值", contract)
        self.assertIn("不要用会逐格打印整张表的提取命令", contract)
        self.assertIn("不可引用的敏感值", contract)
        self.assertIn("整机参数表设为 `1`", contract)
        self.assertIn("不同组件类型按工程形态和专用指标分别成表", contract)
        self.assertIn("整机存在时位于第一个参数子表", contract)
        self.assertTrue((SKILL_ROOT / "scripts" / "scan_legacy_identifiers.py").is_file())
        self.assertTrue((SKILL_ROOT / "scripts" / "inspect_product_samples.py").is_file())

    def test_evals_cover_three_real_tasks_and_balanced_trigger_boundaries(self) -> None:
        evals = json.loads((SKILL_ROOT / "evals" / "evals.json").read_text(encoding="utf-8"))
        self.assertEqual(evals["skill_name"], "product-research-workbook")
        self.assertEqual(len(evals["evals"]), 3)
        self.assertTrue(all(item["expectations"] for item in evals["evals"]))
        trigger_evals = json.loads(
            (SKILL_ROOT / "evals" / "trigger-evals.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(trigger_evals), 20)
        self.assertEqual(sum(item["should_trigger"] for item in trigger_evals), 10)
        self.assertEqual(sum(not item["should_trigger"] for item in trigger_evals), 10)


if __name__ == "__main__":
    unittest.main()
