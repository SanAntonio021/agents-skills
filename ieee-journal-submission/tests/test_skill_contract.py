import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT.parent
GENERIC_REFERENCES = SKILLS_ROOT / "journal-submission" / "references"
VALID_STAGES = {
    "preparation", "initial_submission", "editorial_check", "under_review",
    "decision_received", "revision", "resubmission", "accepted", "final_files",
    "copyright_fees", "proof", "published", "rejected", "withdrawn", "transferred",
}


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.trigger_cases = json.loads(
            (ROOT / "references" / "trigger-evals.json").read_text(encoding="utf-8")
        )

    def test_frontmatter_name_matches_directory(self):
        match = re.search(r"^name:\s*(\S+)$", self.skill_text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), ROOT.name)

    def test_shared_core_dependency_is_explicit(self):
        shared = SKILLS_ROOT / "journal-submission"
        self.assertTrue((shared / "SKILL.md").is_file())
        self.assertIn("../journal-submission/SKILL.md", self.skill_text)
        self.assertIn("明确的依赖错误", self.skill_text)
        self.assertIn("../journal-submission/references/data-contracts.md", self.skill_text)
        self.assertIn("../journal-submission/references/lifecycle.md", self.skill_text)

    def test_validator_is_a_shared_core_shim(self):
        validator = (ROOT / "scripts" / "validate_submission_records.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("CANONICAL_SCRIPT", validator)
        self.assertIn('"journal-submission"', validator)
        self.assertIn("requires the sibling journal-submission skill", validator)
        self.assertNotIn("def validate_state(", validator)

    def test_validator_reports_missing_shared_core(self):
        path = ROOT / "scripts" / "validate_submission_records.py"
        spec = importlib.util.spec_from_file_location("ieee_validator_shim_test", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module.CANONICAL_SCRIPT = ROOT / "journal-submission-missing" / "validator.py"
        with self.assertRaisesRegex(ImportError, "requires the sibling journal-submission skill"):
            module._load_canonical()

    def test_all_lifecycle_states_are_documented(self):
        for stage in sorted(VALID_STAGES):
            self.assertIn(f"`{stage}`", self.skill_text)

    def test_relative_markdown_links_resolve(self):
        failures = []
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for markdown in ROOT.rglob("*.md"):
            for target in pattern.findall(markdown.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                clean_target = target.split("#", 1)[0]
                if clean_target and not (markdown.parent / clean_target).resolve().exists():
                    failures.append(f"{markdown.relative_to(ROOT)} -> {target}")
        self.assertEqual(failures, [])

    def test_platform_sources_and_tenant_boundaries(self):
        scholarone = (ROOT / "references" / "scholarone.md").read_text(encoding="utf-8")
        editorial_manager = (ROOT / "references" / "editorial-manager.md").read_text(
            encoding="utf-8"
        )
        rex = (ROOT / "references" / "research-exchange.md").read_text(encoding="utf-8")
        self.assertIn("Silverchair", scholarone)
        self.assertIn("Aries Systems", editorial_manager)
        self.assertIn("尚未经过本机真实投稿页面验证", editorial_manager)
        self.assertIn("Wiley", rex)
        self.assertIn("IEEE", rex)
        self.assertIn("不跨租户", rex)

    def test_all_confirmation_gates_are_documented(self):
        safety = (GENERIC_REFERENCES / "evidence-and-safety.md").read_text(encoding="utf-8")
        required_phrases = [
            "作者增删、顺序和通信作者",
            "伦理、利益冲突、数据、代码和重复投稿声明",
            "推荐或回避审稿人",
            "最终提交或返修提交",
            "OA、APC、版面费",
            "版权许可",
            "撤稿、转投或稿件转移",
        ]
        for phrase in required_phrases:
            self.assertIn(phrase, safety)

    def test_existing_skills_route_submission_operations_here(self):
        old_skills = [
            "writing-router/SKILL.md",
            "journal-selection/SKILL.md",
            "latex-paper/SKILL.md",
            "paper-review/SKILL.md",
            "ieee-manuscript-edit/SKILL.md",
        ]
        for relative in old_skills:
            with self.subTest(skill=relative):
                text = (SKILLS_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("ieee-journal-submission", text)

    def test_trigger_examples_cover_lifecycle_and_near_misses(self):
        positives = "\n".join(self.trigger_cases["positive"])
        for phrase in ("投稿流程", "major revision", "final files", "copyright", "校样", "Xplore"):
            self.assertIn(phrase, positives)

        routes = {case["route"] for case in self.trigger_cases["negative"]}
        self.assertEqual(
            routes,
            {
                "journal-selection",
                "ieee-manuscript-edit",
                "paper-review",
                "latex-paper",
                "paper-figure-review",
            },
        )

    def test_practice_rules_from_tmtt_submission_are_documented(self):
        contracts = (GENERIC_REFERENCES / "data-contracts.md").read_text(encoding="utf-8")
        materials = (GENERIC_REFERENCES / "material-templates.md").read_text(encoding="utf-8")
        rex = (ROOT / "references" / "research-exchange.md").read_text(encoding="utf-8")
        tmtt = (ROOT / "references" / "tmtt-profile.md").read_text(encoding="utf-8")

        self.assertIn("`salutation` 是投稿页面显示的称谓", contracts)
        self.assertIn("不能仅为了表示尊重", contracts)
        self.assertIn("上限是最大值，不是应达到的目标", materials)
        self.assertIn("记录为 `not_present`", rex)
        self.assertIn("3-5 篇相关 T-MTT 论文", rex)
        self.assertIn("公开 `Information for Authors` 页面未见该字段", tmtt)
        self.assertIn("`main document LaTeX source`", tmtt)
        self.assertIn("不是已确认的强制项", tmtt)

    def test_submission_artifact_freshness_gate_is_documented(self):
        safety = (GENERIC_REFERENCES / "evidence-and-safety.md").read_text(encoding="utf-8")
        lifecycle = (GENERIC_REFERENCES / "lifecycle.md").read_text(encoding="utf-8")
        contracts = (GENERIC_REFERENCES / "data-contracts.md").read_text(encoding="utf-8")
        rex = (ROOT / "references" / "research-exchange.md").read_text(encoding="utf-8")

        self.assertIn("提交文件新鲜度检查", self.skill_text)
        self.assertIn("输入在上传文件生成后发生变化", safety)
        self.assertIn("不可变基线", safety)
        self.assertIn("不静默替换", safety)
        self.assertIn("只能记录为 `unknown`", safety)
        self.assertIn("`provenance`", contracts)
        self.assertIn("提交确认后的原子更新", lifecycle)
        self.assertIn("明确显示 `Under Review`", lifecycle)
        self.assertIn("最后一次文件上传重新生成或复核", rex)

    def test_review_gate_and_conditional_source_are_documented(self):
        contracts = (GENERIC_REFERENCES / "data-contracts.md").read_text(encoding="utf-8")
        safety = (GENERIC_REFERENCES / "evidence-and-safety.md").read_text(encoding="utf-8")
        template = (GENERIC_REFERENCES / "material-templates.md").read_text(encoding="utf-8")
        self.assertIn("pre_submission_review", self.skill_text)
        self.assertIn("可兼容读取、不原地强制升级", self.skill_text)
        self.assertIn("checked_at", contracts)
        self.assertIn("非空 `evidence`", contracts)
        self.assertIn("任何情况下都不代点", self.skill_text)
        self.assertIn("始终由用户本人亲自操作", safety)
        self.assertNotIn("是否确认执行本页最终 Submit？", template)
        self.assertIn("只有当前页面或目标期刊指南要求 source", self.skill_text)
        self.assertTrue((ROOT / "references" / "tmtt-profile.md").is_file())
        self.assertTrue((ROOT / "scripts" / "validate_submission_records.py").is_file())

    def test_cover_letter_declarations_are_conditional(self):
        template = (GENERIC_REFERENCES / "material-templates.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("only after separate user confirmation", template)
        self.assertNotIn(
            "This manuscript is original, is not under consideration elsewhere",
            template,
        )


if __name__ == "__main__":
    unittest.main()
