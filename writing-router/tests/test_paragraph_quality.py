"""Validate fixtures and static links, not model behavior or writing quality."""

import json
import re
import unittest
from collections import Counter
from pathlib import Path


SKILLS_ROOT = Path(__file__).resolve().parents[2]
ROUTER = SKILLS_ROOT / "writing-router"
SUITE_PATH = ROUTER / "evals" / "paragraph-quality.json"
COMMON = "writing-router/references/common-quality.md"
COLLABORATION = "writing-router/references/collaborative-writing.md"
CATALOG = "writing-router/references/ai-smell-catalog.md"
VOCAB = "style-vocab/SKILL.md"
GENRES = {
    "project": "project-writing",
    "technical": "technical-writing",
    "research_report": "research-report",
    "meeting_notes": "meeting-notes",
    "paper": "ieee-manuscript-edit",
    "general": "writing-router",
}
CASES = {
    "unnecessary-defense-project": ("project", "unnecessary_defense"),
    "necessary-negation-paper": ("paper", "necessary_negation"),
    "empty-common-sense-report": ("research_report", "empty_common_sense"),
    "necessary-explanation-technical": ("technical", "necessary_explanation"),
    "cross-turn-repetition-minutes": ("meeting_notes", "cross_turn_repetition"),
    "natural-prose-general": ("general", "natural_prose"),
}
FACT_KINDS = {
    "number", "formula", "definition", "term", "status", "condition",
    "limitation", "decision",
}


def read_text(path):
    return path.read_text(encoding="utf-8")


def linked_paths(path):
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", read_text(path))
    return {
        (path.parent / target).resolve()
        for target in targets
        if not re.match(r"[a-zA-Z]+://", target)
    }


class ParagraphQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = json.loads(read_text(SUITE_PATH))
        cls.cases = cls.suite["evals"]
        cls.by_id = {case["id"]: case for case in cls.cases}

    def test_suite_identity_and_synthetic_provenance(self):
        self.assertEqual("writing-router", self.suite["skill_name"])
        self.assertEqual("synthetic-only", self.suite["fixture_policy"])
        self.assertTrue(self.suite["provenance"].strip())
        self.assertEqual(6, len(self.cases))
        self.assertEqual(set(CASES), set(self.by_id))
        self.assertEqual(6, len(self.by_id))
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertIs(case["synthetic"], True)
                self.assertEqual(
                    CASES[case["id"]],
                    (case["document_type"], case["case_kind"]),
                )

    def test_all_six_genres_and_both_entry_routes_are_present(self):
        self.assertEqual(Counter(GENRES.keys()), Counter(
            case["document_type"] for case in self.cases
        ))
        self.assertEqual(
            {"writing-router", "technical-writing"},
            {case["entry_skill"] for case in self.cases},
        )
        direct = self.by_id["necessary-explanation-technical"]
        self.assertEqual("technical-writing", direct["entry_skill"])
        for case in self.cases:
            if case is not direct:
                self.assertEqual("writing-router", case["entry_skill"])

    def test_replay_contract_keeps_scoring_and_future_turns_private(self):
        policy = self.suite["run_policy"]
        self.assertEqual(["Codex", "Claude"], policy["models"])
        self.assertEqual(["old", "candidate"], policy["variants"])
        self.assertEqual("one-user-prompt-per-turn", policy["delivery"])
        self.assertEqual(["prompt"], policy["visible_turn_fields"])
        self.assertIs(policy["future_turns_visible"], False)
        self.assertIs(policy["expectations_visible"], False)
        self.assertEqual("same-case-same-model-same-variant-only", policy["history"])
        self.assertEqual(
            "synthetic-fixtures-and-isolated-public-skills-only",
            policy["material_access"],
        )
        self.assertEqual(
            "semantic-human-review-not-keyword-count", policy["style_judgment"]
        )

    def test_each_case_has_nonempty_multiturn_prompts_and_semantic_checks(self):
        for case in self.cases:
            self.assertGreaterEqual(len(case["turns"]), 3, case["id"])
            for index, turn in enumerate(case["turns"], 1):
                with self.subTest(case=case["id"], turn=index):
                    self.assertEqual(
                        {"prompt", "expectations", "protected_facts"}, set(turn)
                    )
                    self.assertIsInstance(turn["prompt"], str)
                    self.assertTrue(turn["prompt"].strip())
                    self.assertIsInstance(turn["expectations"], list)
                    self.assertGreaterEqual(len(turn["expectations"]), 2)
                    self.assertTrue(all(isinstance(value, str) and value.strip()
                                        for value in turn["expectations"]))
                    self.assertIsInstance(turn["protected_facts"], list)
                    self.assertTrue(turn["protected_facts"])

    def test_prompts_do_not_instruct_style_or_expose_grading(self):
        # This checks prompt contamination, never vocabulary in model outputs.
        control_markers = (
            "去AI味", "去 AI 味", "AI气味", "AI 气味", "禁用词", "禁词表",
            "TRACE_WRITING_CONTEXT", "expectations", "protected_facts",
            "case_kind", "expected_loaded_refs", "评分标准", "评分要求",
        )
        for case in self.cases:
            for index, turn in enumerate(case["turns"], 1):
                with self.subTest(case=case["id"], turn=index):
                    for marker in control_markers:
                        self.assertNotIn(marker, turn["prompt"])

    def test_facts_are_typed_and_traceable_to_visible_user_material(self):
        kinds = set()
        for case in self.cases:
            for index, turn in enumerate(case["turns"], 1):
                for fact in turn["protected_facts"]:
                    with self.subTest(case=case["id"], turn=index, fact=fact):
                        self.assertEqual({"kind", "text", "source_turn"}, set(fact))
                        self.assertIn(fact["kind"], FACT_KINDS)
                        kinds.add(fact["kind"])
                        self.assertIs(type(fact["source_turn"]), int)
                        self.assertGreaterEqual(fact["source_turn"], 1)
                        self.assertLessEqual(fact["source_turn"], index)
                        self.assertIsInstance(fact["text"], str)
                        self.assertTrue(fact["text"].strip())
                        source = case["turns"][fact["source_turn"] - 1]["prompt"]
                        self.assertIn(fact["text"], source)
        self.assertEqual(FACT_KINDS, kinds)

    def test_formulas_and_definitions_survive_the_revision_fixture(self):
        for case_id, formula in [
            ("necessary-negation-paper", "p_drop = N_drop / N_sent"),
            ("necessary-explanation-technical", "T = C / r"),
        ]:
            for turn in self.by_id[case_id]["turns"][:2]:
                facts = turn["protected_facts"]
                self.assertIn(formula, {fact["text"] for fact in facts})
                self.assertTrue(any(fact["kind"] == "definition" for fact in facts))
                self.assertTrue(any(fact["kind"] == "status" for fact in facts))
        self.assertEqual(160 / 80000, 0.002)
        self.assertEqual(9600 / 80, 120)

    def test_revision_and_cross_turn_controls_are_explicit(self):
        revision = self.by_id["unnecessary-defense-project"]["turns"][1]
        self.assertIn("修改稿", revision["prompt"])
        self.assertTrue(any("实际展示" in check for check in revision["expectations"]))
        continuation = self.by_id["cross-turn-repetition-minutes"]["turns"][1]
        self.assertIn("前一部分沿用", continuation["prompt"])
        checks = "\n".join(continuation["expectations"])
        self.assertIn("只推进到行动项", checks)
        self.assertIn("必要复述", checks)
        natural = self.by_id["natural-prose-general"]
        self.assertTrue(any("原样交付" in check
                            for check in natural["turns"][0]["expectations"]))
        self.assertTrue(any(fact["source_turn"] == 3
                            for fact in natural["turns"][2]["protected_facts"]))

    def test_fixtures_have_no_local_paths_or_private_material_references(self):
        for case in self.cases:
            material = json.dumps(case, ensure_ascii=False)
            self.assertIsNone(re.search(r"[A-Za-z]:[\\/]|\\\\[^\\]+\\", material))
            self.assertIsNone(re.search(r"https?://|file://", material))
            for private_marker in ["writing-samples/", "writing-profile/", "rollout_summaries/"]:
                self.assertNotIn(private_marker, material)

    def test_expected_references_stay_inside_skills_and_exist(self):
        for case in self.cases:
            references = case["expected_loaded_refs"]
            self.assertIn(COMMON, references)
            self.assertIn(COLLABORATION, references)
            self.assertIn(CATALOG, references)
            self.assertIn(VOCAB, references)
            self.assertEqual(len(references), len(set(references)))
            for relative in [f"{case['entry_skill']}/SKILL.md", *references]:
                path = (SKILLS_ROOT / relative).resolve()
                self.assertTrue(path.is_relative_to(SKILLS_ROOT.resolve()), relative)
                self.assertTrue(path.is_file(), relative)

    def test_entrypoints_link_to_shared_rules_and_genre_routes(self):
        router_path = ROUTER / "SKILL.md"
        router_links = linked_paths(router_path)
        for case in self.cases:
            genre = GENRES[case["document_type"]]
            path = SKILLS_ROOT / genre / "SKILL.md"
            links = linked_paths(path)
            for relative in [COMMON, COLLABORATION]:
                self.assertIn((SKILLS_ROOT / relative).resolve(), links, genre)
            if case["entry_skill"] == "writing-router" and genre != "writing-router":
                self.assertIn(path.resolve(), router_links)
                self.assertIn(f"{genre}/SKILL.md", case["expected_loaded_refs"])
            self.assertIn("loaded_refs", read_text(path))

    def test_all_entrypoints_load_rules_before_chinese_prose_work(self):
        for genre in GENRES.values():
            path = SKILLS_ROOT / genre / "SKILL.md"
            text = read_text(path)
            with self.subTest(entry=genre):
                line = next(line for line in text.splitlines()
                            if "中文正文首次起草、续写、局部修改或审查前" in line)
                self.assertIn("中文正文展示前检查", line)
                self.assertIn("读取", line)
                self.assertIn("英文仍", line)
                self.assertIn((SKILLS_ROOT / CATALOG).resolve(), linked_paths(path))
                self.assertLess(text.index(line), text.index("## 完成条件"))

    def test_common_section_owns_semantic_checks_and_early_vocab_loading(self):
        path = SKILLS_ROOT / COMMON
        text = read_text(path)
        heading = "### 中文正文展示前检查"
        self.assertEqual(1, text.count(heading))
        section = text.split(heading, 1)[1].split("\n## ", 1)[0]
        for fragment in [
            "首次起草、续写、局部修改或审查前", "每次展示正文前", "loaded_refs",
            "标题和图表说明", "不扩展到普通讨论回复", "上下文已缺失",
            "先核对数字、公式、术语、完成状态和成立条件", "没有损失就删除",
            "对照材料检查实际增删", "合理推断不能写成已确认安排",
            "润色和摘要只处理既有信息", "将建议与已有事实分开",
            "先定位具体问题，再只替换必要片段", "不从头另写一版",
            "摘要先选取回答当前问题的原有事实和结论", "保留事实不等于每段重述事实",
            "会就保留具体限制", "不为完整性附加核对过程或未完成事项",
            "不能隐去影响它的未验证状态", "不把摘要取舍当成删除正文事实的许可",
            "直接交付本轮正文后结束",
            "删去该推断即可，不补一段声明来替它收尾",
            "材料本身明确的风险、否定和适用范围仍须保留",
            "首次定义、变量含义和推理必需的前提", "实际回应的观点",
            "真实反例、比较、风险和适用条件不能按句式删除", "新的章节功能",
            "不顺手修改已确认的旧段", "术语重复不等于论点重复",
            "已经清楚自然的文字保持原样", "用户修改或要求重写后，再检查本批",
            "不要求新建临时文件、运行扫描脚本", "只报告问题",
        ]:
            self.assertIn(fragment, section)
        self.assertIn((SKILLS_ROOT / CATALOG).resolve(), linked_paths(path))
        self.assertIn((SKILLS_ROOT / VOCAB).resolve(), linked_paths(path))

    def test_collaboration_checks_revisions_before_showing_and_preserves_approval(self):
        path = SKILLS_ROOT / COLLABORATION
        text = read_text(path)
        section = text.split("## 正文循环", 1)[1].split("\n## ", 1)[0]
        self.assertIn((SKILLS_ROOT / COMMON).resolve(), linked_paths(path))
        self.assertIn("中文正文展示前检查", section)
        self.assertRegex(
            section,
            r"起草或修改\s*→\s*展示前检查\s*→\s*展示\s*→\s*用户确认\s*→\s*原样写入并回读",
        )
        for fragment in [
            "直接处理任务在交付或写入前检查，不增加确认轮次",
            "先检查修改后的中文正文，再在对话中给出",
            "不能用上批的检查代替本次检查", "原样写入已认可的正文",
            "不在写入时悄悄重写", "中文后续正文也须先检查",
            "只报告问题，不生成替换稿",
        ]:
            self.assertIn(fragment, section)

    def test_vocab_distinguishes_contextual_batch_checks_from_full_audit(self):
        path = SKILLS_ROOT / VOCAB
        text = read_text(path)
        section = text.split("## 自动交付检查", 1)[1].split("\n## ", 1)[0]
        for fragment in [
            "中文正文首次起草、续写、局部修改或审查前", "同任务文体和规则未变时沿用",
            "每批展示前", "结合句子语境和例外", "不机械替换命中词",
            "不要求每段运行扫描脚本", "普通问答不触发正文检查",
            "完整正式文稿", "完整稿的正式审计", "`clean` 只代表没有词表命中",
        ]:
            self.assertIn(fragment, section)
        self.assertIn((SKILLS_ROOT / COMMON).resolve(), linked_paths(path))
        router_text = read_text(ROUTER / "SKILL.md")
        self.assertIn("中文正文工作开始时按 `style-vocab` 读取适用词表", router_text)
        self.assertIn("完整正式文稿交付前继续运行正式词表审计", router_text)

    def test_readme_keeps_full_evaluation_and_scopes_new_claims(self):
        text = read_text(ROUTER / "evals" / "README.md")
        for fragment in [
            "writing-quality-v2.json", "共 20 例", "共 15 组", "新版至少赢 12 组",
            "至少 80%", "chat-style-v2.json", "每端至少五例",
            "必须完整展示本轮待比较的实际输出", "只有用户明确选择后",
            "paragraph-quality.json", "六组", "Codex", "Claude", "四组",
            "不代表旧 20 例全面通过", "静态测试不能证明",
        ]:
            self.assertIn(fragment, text)

    def test_report_mode_does_not_expand_a_local_edit(self):
        entry = read_text(SKILLS_ROOT / 'research-report/SKILL.md')
        modes = read_text(SKILLS_ROOT / 'research-report/references/modes.md')
        decision = read_text(SKILLS_ROOT / 'research-report/references/decision-report.md')
        contract = read_text(SKILLS_ROOT / 'research-report/references/report-contract.md')
        self.assertIn('不扩大本轮改动授权', entry)
        self.assertIn('`decision_report` 也不新增建议', modes)
        self.assertIn('以下写法用于用户要求起草或修改建议的部分', decision)
        self.assertIn('未验收、未测试或未批准属于来源事实', contract)
        self.assertIn('只在它实际限制的判断处保留', contract)
        self.assertIn('不作每段的固定收尾', contract)

    def test_summary_and_name_checks_return_to_user_material(self):
        common = read_text(SKILLS_ROOT / COMMON)
        meeting = read_text(SKILLS_ROOT / 'meeting-notes/SKILL.md')
        report = read_text(SKILLS_ROOT / 'research-report/SKILL.md')
        self.assertIn('从改稿反查用户材料', common)
        self.assertIn('逐字核对出现的人名、机构名、型号和编号', common)
        self.assertIn('用户明确更正的内容优先', common)
        self.assertIn('摘要可以压缩复述已有结论', common)
        self.assertIn('核对发言人与任务归属，不只沿用上一轮纪要', meeting)
        self.assertIn('只交付本轮所要的部分，不重发或改动已确认部分', meeting)
        router = read_text(ROUTER / 'SKILL.md')
        self.assertIn('先实际读取上表对应主技能的 `SKILL.md`', router)
        self.assertIn('只读共同质量规则不算完成正式文稿的加载', router)
        self.assertIn('先在原文中定位要概括的结论句', report)
        self.assertIn('不把单项满足改写成综合推荐', report)
        self.assertIn('用户只要摘要时只交付摘要', report)
        turn = self.by_id['cross-turn-repetition-minutes']['turns'][0]
        self.assertIn('陈岚', {fact['text'] for fact in turn['protected_facts']})
        self.assertTrue(any('不强制' in check for check in turn['expectations']))
        summary = self.by_id['empty-common-sense-report']['turns'][2]
        self.assertTrue(any('不新增建议采购' in check for check in summary['expectations']))

    def test_summary_relevance_does_not_weaken_full_text_fact_protection(self):
        report = self.by_id['empty-common-sense-report']['turns']
        self.assertNotIn('验收状态放在最后', report[1]['prompt'])
        self.assertTrue(any('不强制复述' in check for check in report[2]['expectations']))
        self.assertFalse(any(fact['kind'] == 'status' for fact in report[2]['protected_facts']))
        for turn in report[:2]:
            self.assertTrue(any('样机验收尚未进行' in fact['text'] for fact in turn['protected_facts']))
        paper = self.by_id['necessary-negation-paper']['turns']
        for turn in paper:
            self.assertTrue(any('多发送端测试尚未开展' in fact['text'] for fact in turn['protected_facts']))

    def test_output_and_audit_scope_do_not_request_process_narration(self):
        router = read_text(ROUTER / 'SKILL.md')
        paper = read_text(SKILLS_ROOT / 'ieee-manuscript-edit/SKILL.md')
        report = read_text(SKILLS_ROOT / 'research-report/SKILL.md')
        vocab = read_text(SKILLS_ROOT / VOCAB)
        self.assertIn('默认只交付本轮请求的正文，不附修改理由或检查记录', router)
        self.assertIn('完整正式稿才运行词表审计', paper)
        self.assertIn('局部文本：只给修改稿', paper)
        self.assertIn('不为这些操作启动完整报告审计', report)
        self.assertIn('不能把未验收自动接成该交期结论的转折', report)
        self.assertIn('不要求在交付正文时宣布结果', vocab)


if __name__ == "__main__":
    unittest.main()
