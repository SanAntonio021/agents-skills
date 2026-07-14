import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT.parent
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

    def test_all_lifecycle_states_are_documented(self):
        for stage in sorted(VALID_STAGES):
            self.assertIn(f"`{stage}`", self.skill_text)

    def test_all_confirmation_gates_are_documented(self):
        safety = (ROOT / "references" / "evidence-and-safety.md").read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
