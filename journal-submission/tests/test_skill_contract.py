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

    def test_optica_prism_route_is_documented(self):
        prism = (ROOT / "references" / "platforms" / "prism-optica.md").read_text(
            encoding="utf-8"
        )
        source_index = (ROOT / "references" / "official-source-index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("prism-optica.md", self.skill_text)
        self.assertIn("CountryCode", prism)
        self.assertIn("不得通过修改隐藏字段", prism)
        self.assertIn("prism.optica.org", source_index)
        self.assertIn("novelty and impact statement", source_index)

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
        self.assertEqual(tmtt["expected_route"], "journal-submission")
        self.assertTrue(tmtt["should_trigger"])
        for item in self.trigger_cases:
            if item["category"] == "selection":
                with self.subTest(selection=item["id"]):
                    self.assertTrue(item["should_trigger"])
                    self.assertEqual(item["expected_route"], "journal-submission")

    def test_selection_resources_and_license_are_available(self):
        selection = (ROOT / "references" / "journal-selection.md").read_text(encoding="utf-8")
        profiles = (ROOT / "references" / "journal-profiles.md").read_text(encoding="utf-8")
        provenance = (ROOT / "references" / "selection-upstream-source.md").read_text(encoding="utf-8")
        license_text = (ROOT / "references" / "licenses" / "awesome-journal-skills.txt").read_text(encoding="utf-8")
        self.assertIn("references/journal-selection.md", self.skill_text)
        for name in ("reach", "match", "safe", "JCR", "SCIE/ESCI", "scope rather than quality"):
            self.assertIn(name, selection)
        for name in ("TTST", "TMTT", "TWC", "TCOM", "Nature Communications", "SCIS", "JSAC"):
            self.assertIn(name, profiles)
        self.assertIn("初稿待校准", profiles)
        self.assertIn("d08b584", provenance)
        self.assertIn("Copyright (c) 2026 Bryce Wang", license_text)
        self.assertIn("Permission is hereby granted", license_text)

    def test_real_routes_replace_nonexistent_names(self):
        files = [
            SKILLS_ROOT / "writing-router" / "SKILL.md",
            SKILLS_ROOT / "writing-router" / "references" / "academic-workflow-map.md",
            ROOT / "references" / "journal-selection.md",
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
            "paper-review",
            "ieee-manuscript-edit",
            "latex-paper",
        ):
            self.assertIn(route, combined)

    def test_unified_submission_route_is_documented(self):
        for relative in (
            "writing-router/SKILL.md",
            "journal-submission/SKILL.md",
            "paper-review/SKILL.md",
            "latex-paper/SKILL.md",
            "ieee-manuscript-edit/SKILL.md",
        ):
            with self.subTest(skill=relative):
                text = (SKILLS_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("journal-submission", text)

    def test_optional_review_and_manual_actions_are_explicit(self):
        safety = (ROOT / "references" / "evidence-and-safety.md").read_text(encoding="utf-8")
        contracts = (ROOT / "references" / "data-contracts.md").read_text(encoding="utf-8")
        template = (ROOT / "references" / "material-templates.md").read_text(encoding="utf-8")
        self.assertIn("pre_submission_review", self.skill_text)
        self.assertIn("checked_at", contracts)
        self.assertIn("evidence", contracts)
        self.assertIn("可定位的 `evidence`", self.skill_text)
        self.assertIn("可选的内容审查记录", self.skill_text)
        self.assertIn("缺失或 `not_run` 不自动阻止", self.skill_text)
        self.assertIn("局部修改和检查，不宣称整稿已审查", self.skill_text)
        self.assertIn("已有准确提交授权可复用", self.skill_text)
        self.assertIn("## 输出前自检", self.skill_text)
        self.assertIn("本人签署事项", template)
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

    def test_ieee_extension_is_available_in_unified_entry(self):
        self.assertIn("IEEE", self.skill_text)
        for relative in ("references/publishers/ieee.md", "references/journals/tmtt.md", "references/platforms/research-exchange.md"):
            self.assertTrue((ROOT / relative).is_file())


if __name__ == "__main__":
    unittest.main()
