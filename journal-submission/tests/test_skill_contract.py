import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT.parent
SCRIPT = ROOT / "scripts" / "validate_submission_records.py"
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic-cases.json"

SPEC = importlib.util.spec_from_file_location("validate_submission_records", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SkillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        cls.lifecycle_text = (ROOT / "references" / "lifecycle.md").read_text(encoding="utf-8")
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.trigger_cases = json.loads(
            (ROOT / "references" / "trigger-evals.json").read_text(encoding="utf-8")
        )

    def test_frontmatter_name_matches_directory(self):
        match = re.search(r"^name:\s*(\S+)$", self.skill_text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), ROOT.name)

    def test_lifecycle_state_set_is_identical_everywhere(self):
        expected = set(self.fixture["stages"])
        self.assertEqual(MODULE.VALID_STAGES, expected)
        for stage in sorted(expected):
            self.assertIn(f"`{stage}`", self.skill_text)
            self.assertIn(f"`{stage}`", self.lifecycle_text)

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

    def test_platform_names_and_tenant_boundaries(self):
        scholarone = (ROOT / "references" / "platforms" / "scholarone.md").read_text(
            encoding="utf-8"
        )
        rex = (ROOT / "references" / "platforms" / "research-exchange.md").read_text(
            encoding="utf-8"
        )
        editorial_manager = (
            ROOT / "references" / "platforms" / "editorial-manager.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Silverchair", scholarone)
        self.assertNotIn("schola-one", "\n".join(str(path) for path in ROOT.rglob("*")))
        self.assertIn("Wiley", rex)
        self.assertIn("IEEE", rex)
        self.assertIn("不跨租户", rex)
        self.assertIn("目标期刊当日官方作者指南控制", self.skill_text)
        self.assertIn("明确标注为跨租户差异", self.skill_text)
        self.assertIn("冲突双方的原文", self.skill_text)
        self.assertIn("Aries Systems", editorial_manager)
        self.assertIn("尚未经过本机真实投稿页面验证", editorial_manager)

    def test_scis_experience_is_not_platform_rule(self):
        scis = (ROOT / "references" / "journals" / "scis.md").read_text(encoding="utf-8")
        scholarone = (ROOT / "references" / "platforms" / "scholarone.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("一次 ScholarOne 投稿经验", scis)
        self.assertIn("不能作为 ScholarOne 通用规则", scholarone)
        general_rules, prohibited_examples = scholarone.split("## 禁止泛化", 1)
        self.assertNotIn("必须同时查看 HTML 和 PDF", general_rules)
        self.assertIn("必须同时查看 HTML 和 PDF", prohibited_examples)

    def test_source_package_is_conditional(self):
        contracts = (ROOT / "references" / "data-contracts.md").read_text(encoding="utf-8")
        self.assertIn("LaTeX source 包是条件性产物", self.skill_text)
        self.assertIn("没有输入快照时只能使用 `unknown`", contracts)

    def test_trigger_contract_has_required_coverage(self):
        self.assertIsInstance(self.trigger_cases, list)
        self.assertTrue(
            all("query" in item and "should_trigger" in item for item in self.trigger_cases)
        )
        self.assertGreaterEqual(len(self.trigger_cases), 20)
        categories = {item["category"] for item in self.trigger_cases}
        self.assertTrue(
            {
                "selection",
                "writing",
                "pre_review",
                "scis_initial",
                "revision",
                "unknown_platform",
                "post_acceptance",
                "final_submit",
            }.issubset(categories)
        )
        tmtt = next(item for item in self.trigger_cases if item["id"] == "tmtt-revision")
        self.assertEqual(tmtt["expected_route"], "ieee-journal-submission")
        self.assertFalse(tmtt["should_trigger"])

    def test_real_routes_replace_nonexistent_names(self):
        files = [
            SKILLS_ROOT / "writing-router" / "SKILL.md",
            SKILLS_ROOT / "writing-router" / "references" / "academic-workflow-map.md",
            SKILLS_ROOT / "journal-selection" / "SKILL.md",
            SKILLS_ROOT / "paper-review" / "SKILL.md",
            SKILLS_ROOT / "latex-paper" / "SKILL.md",
            SKILLS_ROOT / "ieee-manuscript-edit" / "SKILL.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
        for missing_name in ("brainstorming", "response-to-referees", "sciwrite", "sci-paper-edit"):
            self.assertNotIn(missing_name, combined)
        for route in (
            "ask-first",
            "journal-submission",
            "ieee-journal-submission",
            "paper-review",
            "ieee-manuscript-edit",
            "latex-paper",
        ):
            self.assertIn(route, combined)

    def test_generic_and_ieee_routes_are_both_documented(self):
        for relative in (
            "writing-router/SKILL.md",
            "journal-selection/SKILL.md",
            "paper-review/SKILL.md",
            "latex-paper/SKILL.md",
            "ieee-manuscript-edit/SKILL.md",
        ):
            with self.subTest(skill=relative):
                text = (SKILLS_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("journal-submission", text)
                self.assertIn("ieee-journal-submission", text)

    def test_review_gate_and_manual_actions_are_explicit(self):
        safety = (ROOT / "references" / "evidence-and-safety.md").read_text(encoding="utf-8")
        contracts = (ROOT / "references" / "data-contracts.md").read_text(encoding="utf-8")
        template = (ROOT / "references" / "material-templates.md").read_text(encoding="utf-8")
        self.assertIn("pre_submission_review", self.skill_text)
        self.assertIn("checked_at", contracts)
        self.assertIn("evidence", contracts)
        self.assertIn("可定位的 `evidence`", self.skill_text)
        self.assertIn("任何情况下都不代点", self.skill_text)
        self.assertIn("不要只把这两项留在内部清单", self.skill_text)
        self.assertIn("## 输出前自检", self.skill_text)
        self.assertIn("最终动作始终由用户亲自完成", template)
        for phrase in ("最终 Submit", "作者增删", "OA、APC", "版权许可"):
            self.assertIn(phrase, safety)

    def test_cover_letter_declarations_are_conditional(self):
        template = (ROOT / "references" / "material-templates.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("only after separate user confirmation", template)
        self.assertNotIn(
            "This manuscript is original, is not under consideration elsewhere",
            template,
        )

    def test_author_library_path_is_preserved(self):
        self.assertIn("local-assets/ieee-journal-submission/authors.json", self.skill_text)

    def test_ieee_specialized_entry_remains_independent(self):
        ieee_skill = (SKILLS_ROOT / "ieee-journal-submission" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("IEEE 期刊投稿全生命周期助手", ieee_skill)
        self.assertTrue((SKILLS_ROOT / "ieee-journal-submission" / "scripts").is_dir())
        self.assertTrue(
            (SKILLS_ROOT / "ieee-journal-submission" / "references" / "tmtt-profile.md").exists()
        )


if __name__ == "__main__":
    unittest.main()
