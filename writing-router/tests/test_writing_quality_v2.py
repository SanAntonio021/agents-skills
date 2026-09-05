import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_ROOT = REPO_ROOT / "writing-router"
FORMAL_EVALS = ROUTER_ROOT / "evals" / "writing-quality-v2.json"
CHAT_EVALS = ROUTER_ROOT / "evals" / "chat-style-v2.json"


class WritingQualityV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formal = json.loads(FORMAL_EVALS.read_text(encoding="utf-8"))
        cls.chat = json.loads(CHAT_EVALS.read_text(encoding="utf-8"))

    def test_formal_suite_has_four_synthetic_cases_per_genre(self):
        cases = self.formal["evals"]
        self.assertEqual(20, len(cases))
        self.assertEqual("synthetic-only", self.formal["fixture_policy"])
        by_type = {}
        for case in cases:
            self.assertTrue(case["synthetic"])
            by_type.setdefault(case["document_type"], []).append(case)
        self.assertEqual(
            {
                "project",
                "technical",
                "research_report",
                "meeting_notes",
                "paper",
            },
            set(by_type),
        )
        for genre_cases in by_type.values():
            self.assertEqual(4, len(genre_cases))
            self.assertEqual(
                {
                    "normal_writing",
                    "insufficient_material",
                    "fact_formula_protection",
                    "repetition_smell_audit",
                },
                {case["case_kind"] for case in genre_cases},
            )

    def test_paper_cases_cover_chinese_and_english(self):
        languages = {
            case["language"]
            for case in self.formal["evals"]
            if case["document_type"] == "paper"
        }
        self.assertEqual({"zh", "en"}, languages)

    def test_eval_fixtures_do_not_contain_local_absolute_paths(self):
        serialized = json.dumps(self.formal, ensure_ascii=False)
        self.assertIsNone(re.search(r"[A-WYZ]:\\\\", serialized))

    def test_every_expected_reference_exists(self):
        for case in self.formal["evals"]:
            for relative in (
                case["expected_loaded_refs"] + case["expected_unloaded_refs"]
            ):
                self.assertTrue(
                    (REPO_ROOT / relative).is_file(),
                    f"missing eval reference {relative} for case {case['id']}",
                )

    def test_trace_and_loaded_refs_are_required(self):
        for case in self.formal["evals"]:
            self.assertIn("TRACE_WRITING_CONTEXT=1", case["prompt"])
            self.assertTrue(case["expected_loaded_refs"])
        for relative in [
            "writing-router/SKILL.md",
            "humanizer-zh/SKILL.md",
            "project-writing/SKILL.md",
            "technical-writing/SKILL.md",
            "research-report/SKILL.md",
            "meeting-notes/SKILL.md",
            "ieee-manuscript-edit/SKILL.md",
        ]:
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("loaded_refs", text, relative)

    def test_docx_delivery_consumes_the_reviewed_text_once(self):
        delivery = (
            REPO_ROOT / "markdown-docx-workflow" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("不自行改写正文", delivery)
        self.assertIn("不再次调用 `humanizer-zh`", delivery)
        self.assertIn("loaded_refs", delivery)

    def test_router_contains_complete_mode_matrix(self):
        router = (ROUTER_ROOT / "SKILL.md").read_text(encoding="utf-8")
        tokens = {
            "proposal",
            "expert_reply",
            "final_audit",
            "technical_scheme",
            "system_description",
            "test_result_analysis",
            "evidence_report",
            "decision_report",
            "discussion",
            "action",
            "mixed",
            "zh_paper",
            "en_paper",
            "general_edit",
            "audit_only",
        }
        for token in tokens:
            self.assertIn(token, router)

    def test_smell_catalog_has_conditions_exceptions_blocks_and_actions(self):
        catalog = (
            REPO_ROOT
            / "humanizer-zh"
            / "references"
            / "ai-smell-catalog.md"
        ).read_text(encoding="utf-8")
        for index in range(1, 11):
            section = re.search(
                rf"## S{index:02d} .*?(?=\n## S|\n## 复核顺序|\Z)",
                catalog,
                flags=re.S,
            )
            self.assertIsNotNone(section, f"missing S{index:02d}")
            body = section.group(0)
            for label in ["成立条件", "文体例外", "blocking_when", "处理"]:
                self.assertIn(label, body, f"S{index:02d} missing {label}")

    def test_blind_review_requires_complete_matched_outputs_and_user_choice(self):
        guidance = (ROUTER_ROOT / "evals" / "README.md").read_text(encoding="utf-8")
        self.assertIn("必须完整展示本轮待比较的实际输出", guidance)
        self.assertIn("不得摘要、删减或用空白替代其中一版", guidance)
        self.assertIn("两版使用同一种清晰排版", guidance)
        self.assertIn("先用一句具体的话说明本组要判断什么", guidance)
        self.assertIn("只有用户明确选择后，才写入人工复核结果", guidance)
        self.assertIn("另记为评测调整，不能记成用户选择", guidance)

    def test_public_personal_sample_files_are_removed(self):
        self.assertFalse(
            (REPO_ROOT / "project-writing" / "references" / "writing-samples.md").exists()
        )
        self.assertFalse(
            (
                REPO_ROOT
                / "ieee-manuscript-edit"
                / "references"
                / "writing-samples.md"
            ).exists()
        )

    def test_language_specific_paper_refs_do_not_cross_load(self):
        cases = {
            case["id"]: case
            for case in self.formal["evals"]
            if case["document_type"] == "paper"
        }
        for case in cases.values():
            loaded = set(case["expected_loaded_refs"])
            if case["language"] == "zh":
                self.assertNotIn(
                    "ieee-manuscript-edit/references/english-paper.md", loaded
                )
            if case["language"] == "en":
                self.assertNotIn(
                    "ieee-manuscript-edit/references/chinese-paper.md", loaded
                )

    def test_chat_suite_has_six_complete_synthetic_cases(self):
        self.assertEqual("synthetic-only", self.chat["fixture_policy"])
        self.assertEqual(6, len(self.chat["evals"]))
        for case in self.chat["evals"]:
            self.assertTrue(case["synthetic"])
            self.assertGreaterEqual(len(case["checks"]), 4)


if __name__ == "__main__":
    unittest.main()
