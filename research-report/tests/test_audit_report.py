from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "audit_report.py"
MIXED_FIXTURE = SKILL_ROOT / "evals" / "fixtures" / "mixed-report.md"
SEMANTIC_BOUNDARY_FIXTURE = SKILL_ROOT / "evals" / "fixtures" / "semantic-boundary.md"


def load_module():
    spec = importlib.util.spec_from_file_location("audit_report", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load audit_report.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit_report = load_module()


class AuditReportTests(unittest.TestCase):
    def test_mixed_fixture_flags_core_content_problems(self):
        result = audit_report.audit_text(
            MIXED_FIXTURE.read_text(encoding="utf-8"), source=str(MIXED_FIXTURE)
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("SUMMARY_DEFINITION_DENSITY", codes)
        self.assertIn("MIXED_STATEMENT_TYPES", codes)
        self.assertIn("UNCITED_FACTUAL_PARAGRAPH", codes)
        self.assertIn("GENERIC_HEADING", codes)
        self.assertIn("CONSULTING_JARGON", codes)
        self.assertIn("DUPLICATE_SENTENCE", codes)

    def test_semantic_boundary_fixture_flags_nonmechanical_language_problems(self):
        result = audit_report.audit_text(
            SEMANTIC_BOUNDARY_FIXTURE.read_text(encoding="utf-8"),
            source=str(SEMANTIC_BOUNDARY_FIXTURE),
        )
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("MIXED_STATEMENT_TYPES", codes)
        self.assertIn("DOUBLE_NEGATION", codes)
        self.assertIn("WEAK_QUALIFIER", codes)

    def test_clean_formal_report_avoids_separation_and_action_warnings(self):
        clean = """# 山区应急通信调研

## 摘要

甲省山区已完成两个固定站点的卫星应急通信演练，厂商甲公开的终端参数对应工程样机。[1][2] 这些已核验事实表明，报告所述对象处于工程验证应用场景。

## 范围与术语

本报告所称固定站址，是设备在一个任务周期内不移动的使用方式。

## 已公开的试验进展

甲省在 2026 年完成两个山区站点的应急通信演练。[^1]

厂商甲工程样机重量为 12 kg，峰值功耗为 140 W。[^2]

## 综合判断

已核验的现场演练和工程样机参数共同支持工程验证应用场景的判断。

## 资料来源

[^1]: 甲省应急通信演练公告，2026-06-18。
[^2]: 厂商甲工程样机规格页，2026-05-29。
"""
        result = audit_report.audit_text(clean)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("SUMMARY_DEFINITION_DENSITY", codes)
        self.assertNotIn("SUMMARY_LABEL_CHAIN", codes)
        self.assertNotIn("GENERIC_HEADING", codes)
        self.assertNotIn("INTERNAL_SOURCE_CITATION", codes)
        self.assertNotIn("SUMMARY_NEGATION_CHAIN", codes)
        self.assertNotIn("QUESTION_STYLE_HEADING", codes)
        self.assertNotIn("ACTION_DIRECTIVE_HEADING", codes)
        self.assertNotIn("ACTION_DIRECTIVE", codes)
        self.assertNotIn("DEFENSIVE_LIMITATION", codes)
        self.assertNotIn("FORMAL_UNFINISHED_STATUS", codes)
        self.assertNotIn("UNRESOLVED_NUMERIC_CITATION", codes)
        uncited = [
            item
            for item in result["findings"]
            if item["code"] == "UNCITED_FACTUAL_PARAGRAPH"
        ]
        self.assertEqual([], uncited)

    def test_summary_label_chain_is_flagged(self):
        mechanical = """# 调研报告

## 摘要

**研究对象。** 本报告整理山区固定站址卫星终端资料。

**主要发现。** 现有资料只能证明一次试点已经开展。[S-01]

**证据限制。** 资料没有公开用户数量和套餐价格。

**当前含义。** 这些资料不能支持量产决策。
"""
        result = audit_report.audit_text(mechanical)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("SUMMARY_LABEL_CHAIN", codes)

    def test_internal_classification_labels_are_flagged(self):
        labelled = """# 调研报告

## F-01 已公布的试点

U-01：公开资料没有给出用户数量。[S-01]

### J-01 当前不能支持量产

R-01：建议先补充认证条件。
"""
        result = audit_report.audit_text(labelled)
        labels = [
            item
            for item in result["findings"]
            if item["code"] == "INTERNAL_CLASSIFICATION_LABEL"
        ]
        self.assertGreaterEqual(len(labels), 4)

    def test_formulaic_summary_meta_leads_are_flagged(self):
        mechanical = """# 调研报告

## 摘要

本报告讨论山区固定卫星接入。

现有资料记录了一次行业试点。[S-01]

据此，当前不能冻结量产参数。
"""
        result = audit_report.audit_text(mechanical)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("SUMMARY_FORMULAIC_LEADS", codes)

    def test_sentence_label_chain_is_flagged(self):
        mechanical = """# 调研报告

## 摘要

研究对象：山区固定卫星接入。主要发现：试点已经开展。证据限制：用户数量未公开。当前含义：不能冻结量产参数。
"""
        result = audit_report.audit_text(mechanical)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("SUMMARY_SENTENCE_LABEL_CHAIN", codes)

    def test_internal_classification_in_body_is_flagged(self):
        labelled = """# 调研报告

## 综合判断

依据 F-02 和 J-01，当前不能冻结量产参数。
"""
        result = audit_report.audit_text(labelled)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("INTERNAL_CLASSIFICATION_BODY", codes)

    def test_internal_source_citations_are_flagged_in_formal_copy(self):
        report = """# 调研报告

## 公开进展

某项试点已经公布。[S-01]

## 参考资料

- [S-01] 某试点公告。
"""
        result = audit_report.audit_text(report)
        findings = [
            item
            for item in result["findings"]
            if item["code"] == "INTERNAL_SOURCE_CITATION"
        ]
        self.assertEqual(2, len(findings))

    def test_bare_internal_source_markers_are_flagged_in_formal_copy(self):
        report = """# 调研报告

## 公开进展

某项试点已经公布。S01

## 参考资料

- S02 某测试说明。
"""
        result = audit_report.audit_text(report)
        findings = [
            item
            for item in result["findings"]
            if item["code"] == "INTERNAL_SOURCE_CITATION"
        ]
        self.assertEqual(2, len(findings))

    def test_standard_numeric_and_footnote_citations_are_not_internal(self):
        report = """# 调研报告

## 公开进展

某项试点已经公布。[1] 另一项测试仍在进行。[^2]

## 参考资料

[1] 某试点公告。
[^2]: 某测试说明。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("INTERNAL_SOURCE_CITATION", codes)

    def test_standard_numeric_citation_ranges_count_as_evidence(self):
        report = """# 调研报告

## 公开进展

甲省在 2026 年公布了两项试点。[1-3, 5]
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("UNCITED_FACTUAL_PARAGRAPH", codes)
        self.assertNotIn("INTERNAL_SOURCE_CITATION", codes)

    def test_summary_negation_chain_is_flagged(self):
        report = """# 调研报告

## 摘要

资料没有给出公众套餐，也没有提供用户数量，因此不能估算市场规模，无法冻结量产参数。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("SUMMARY_NEGATION_CHAIN", codes)

    def test_double_negation_is_flagged(self):
        report = """# 调研报告

## 综合判断

已核验的现场演练表明，该方案并非没有工程应用价值。[1]

## 参考资料

[1] 甲省应急通信演练公告，2026-06-18。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("DOUBLE_NEGATION", codes)

    def test_weak_qualifier_is_flagged(self):
        report = """# 调研报告

## 综合判断

两次现场演练在一定程度上说明该样机适合工程验证。[1]

## 参考资料

[1] 甲省应急通信演练公告，2026-06-18。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("WEAK_QUALIFIER", codes)

    def test_direct_statement_does_not_trigger_new_language_checks(self):
        report = """# 调研报告

## 综合判断

两次现场演练支持该样机用于工程验证。[1]

## 参考资料

[1] 甲省应急通信演练公告，2026-06-18。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("DOUBLE_NEGATION", codes)
        self.assertNotIn("WEAK_QUALIFIER", codes)

    def test_material_role_meta_statement_is_flagged(self):
        report = """# 调研报告

## 综合判断

这些材料共同构成国内固定卫星宽带的公开业务与产业信息基础。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("MATERIAL_ROLE_META", codes)

    def test_direct_source_fact_does_not_trigger_material_role_meta(self):
        report = """# 调研报告

## 公开业务

中国卫通公开宽带卫星基础运营平台和网络系统集成服务。[1]

## 参考资料

[1] 中国卫通公开页面。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("MATERIAL_ROLE_META", codes)

    def test_definition_and_finding_mixed_in_body_is_flagged(self):
        report = """# 调研报告

## 公开试验进展

固定站址是设备在一个任务周期内不移动的使用方式。甲省在 2026 年完成两个山区站点的应急通信演练。[1]

## 参考资料

[1] 甲省应急通信演练公告，2026-06-18。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("MIXED_STATEMENT_TYPES", codes)

    def test_thin_body_sections_are_reviewed_in_dense_report(self):
        report = """# 调研报告

## 摘要

本文整理已公开的试验、终端和准入信息。

## 研究对象与术语

本报告所称固定站址终端，在同一安装位置运行。

## 公开业务

甲单位公开卫星接入服务。[1]

## 低轨进展

乙单位在 2026 年完成组网发射。[2]

## 国内终端

丙厂商公开固定终端参数。[3]

## 国际终端

丁厂商公开电子扫描终端。[4]

## 频段与准入

法规列出相关设备管理事项。[5]

## 参数对照

产品参数采用同一单位整理。

| 产品 | 功耗 |
| --- | --- |
| A | 80 W |
| B | 100 W |
| C | 120 W |

## 综合判断

公开资料可用于比较产品形态。

## 参考资料

[1] 甲单位公开页面。
[2] 乙单位公告。
[3] 丙厂商规格页。
[4] 丁厂商规格页。
[5] 主管部门法规。
"""
        result = audit_report.audit_text(report)
        findings = [
            item
            for item in result["findings"]
            if item["code"] == "THIN_BODY_SECTION"
        ]
        sections = {item["section"] for item in findings}
        self.assertIn("公开业务", sections)
        self.assertIn("低轨进展", sections)
        self.assertNotIn("参数对照", sections)
        self.assertTrue(all(item["severity"] == "info" for item in findings))

    def test_thin_body_sections_are_not_flagged_in_short_report(self):
        report = """# 调研报告

## 公开业务

甲单位公开卫星接入服务。[1]

## 终端产品

乙厂商公开固定终端参数。[2]

## 频段与准入

法规列出相关设备管理事项。[3]

## 参考资料

[1] 甲单位公开页面。
[2] 乙厂商规格页。
[3] 主管部门法规。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("THIN_BODY_SECTION", codes)

    def test_scope_cutoff_date_is_not_treated_as_uncited_fact(self):
        report = """# 调研报告

## 研究对象与术语

本报告研究中国境内固定卫星宽带的公开业务和用户终端，资料整理截止于 2026 年 8 月 15 日。
"""
        result = audit_report.audit_text(report)
        uncited = [
            item
            for item in result["findings"]
            if item["code"] == "UNCITED_FACTUAL_PARAGRAPH"
        ]
        self.assertEqual([], uncited)

    def test_summary_unfinished_research_status_is_flagged(self):
        report = """# 调研报告

## 摘要

公开资料记录了行业试点和工程样机状态。公众业务条件和需求规模不在现有材料的覆盖范围内，量产配置的判断还缺少相应资料。[1]
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("FORMAL_UNFINISHED_STATUS", codes)

    def test_question_style_headings_are_flagged(self):
        report = """# 调研报告

## 这份报告要帮助项目团队判断什么

正文。

## 当前应如何推进

正文。
"""
        result = audit_report.audit_text(report)
        findings = [
            item
            for item in result["findings"]
            if item["code"] == "QUESTION_STYLE_HEADING"
        ]
        self.assertEqual(2, len(findings))

    def test_professional_headings_and_common_questions_pass(self):
        report = """# 调研报告

## 研究目的与决策问题

正文。

## 量产判断的证据条件

正文。

## 常见问题

正文。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("QUESTION_STYLE_HEADING", codes)

    def test_colloquial_purpose_statement_is_flagged(self):
        report = """# 调研报告

## 研究目的

本报告整理试点和产品资料，供项目团队判断当前能确认哪些进展。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("COLLOQUIAL_PURPOSE_STATEMENT", codes)

    def test_professional_purpose_statement_passes(self):
        report = """# 调研报告

## 研究目的

本报告用于评估业务开放状态，并核定终端参数冻结所需的证据条件。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("COLLOQUIAL_PURPOSE_STATEMENT", codes)

    def test_vague_pending_disclosure_is_flagged_even_with_citation(self):
        report = """# 调研报告

## 业务条件

主管部门尚未公布公众套餐及申请方式。[1]

## 参考资料

[1] 甲省行业应用试点公告. 2026-04-12.
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("VAGUE_PENDING_DISCLOSURE", codes)

    def test_source_specific_missing_fields_pass(self):
        report = """# 调研报告

## 业务条件

甲省行业应用试点公告未列明公众套餐及申请方式。[1]

星河运营公司接入测试说明未提供终端采购价格。[2]

## 参考资料

[1] 甲省行业应用试点公告. 2026-04-12.

[2] 星河运营公司接入测试说明. 2026-05-08.
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("VAGUE_PENDING_DISCLOSURE", codes)
        self.assertNotIn("FORMAL_UNFINISHED_STATUS", codes)

    def test_colloquial_source_gap_is_flagged(self):
        report = """# 调研报告

## 业务条件

试点公告没有公布公众套餐及申请方式。[1]

## 参考资料

[1] 甲省行业应用试点公告. 2026-04-12.
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("VAGUE_PENDING_DISCLOSURE", codes)

    def test_explicit_future_disclosure_schedule_without_shangwei_passes(self):
        report = """# 调研报告

## 业务条件

公告说明，申请办法将于 2026 年 9 月另行公布。[1]

## 参考资料

[1] 甲省行业应用试点公告. 2026-04-12.
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("VAGUE_PENDING_DISCLOSURE", codes)

    def test_cited_shangwei_disclosure_is_still_flagged(self):
        report = """# 调研报告

## 业务条件

截至资料截止日，申请办法尚未公布；公告明确说明，该办法将于 2026 年 9 月另行公布。[1]

## 参考资料

[1] 甲省行业应用试点公告. 2026-04-12.
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("VAGUE_PENDING_DISCLOSURE", codes)

    def test_action_directive_heading_and_sentence_are_flagged(self):
        report = """# 调研报告

## 下一阶段建议

建议先冻结量产配置，并推进供应链建设。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("ACTION_DIRECTIVE_HEADING", codes)
        self.assertIn("ACTION_DIRECTIVE", codes)

    def test_natural_position_action_directives_are_flagged(self):
        report = """# 调研报告

## 综合判断

该项目不宜冻结量产指标。项目组应当补齐认证资料，后续需推进认证。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("ACTION_DIRECTIVE", codes)

    def test_implicit_validation_arrangement_is_flagged(self):
        report = """# 调研报告

## 量产配置与验证安排

频段、发射功率和接口以可调整配置进入后续验证，待接入规范、试验频段和终端认证条件形成正式资料后再冻结。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("ACTION_DIRECTIVE_HEADING", codes)
        self.assertIn("ACTION_DIRECTIVE", codes)

    def test_defensive_limitation_is_flagged(self):
        report = """# 调研报告

## 综合判断

现有资料尚不能说明公众业务是否具备量产条件。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("DEFENSIVE_LIMITATION", codes)

    def test_evidence_condition_belongs_in_internal_ledger(self):
        report = """# 调研报告

## 综合判断

原稿资料覆盖行业应用试点、接入规范测试和工程样机参数。量产配置的判断还需要接入条件、认证要求、需求规模与成本资料共同支撑。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("ACTION_DIRECTIVE", codes)
        self.assertIn("FORMAL_UNFINISHED_STATUS", codes)

    def test_formal_unfinished_heading_and_body_are_flagged(self):
        report = """# 调研报告

## 证据范围与待核实事项

试验频段仍待补充，市场规模尚未覆盖。
"""
        result = audit_report.audit_text(report)
        findings = [
            item
            for item in result["findings"]
            if item["code"] == "FORMAL_UNFINISHED_STATUS"
        ]
        self.assertGreaterEqual(len(findings), 2)

    def test_internal_ledger_mode_permits_work_status_and_internal_keys(self):
        ledger = """# 内部调研台账

## 待核实事项

U-01：试验频段待补充，关联来源 S01。下一步核对运营商技术文件。
"""
        result = audit_report.audit_text(ledger, document_role="internal-ledger")
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("FORMAL_UNFINISHED_STATUS", codes)
        self.assertNotIn("INTERNAL_CLASSIFICATION_LABEL", codes)
        self.assertNotIn("INTERNAL_SOURCE_CITATION", codes)
        self.assertNotIn("ACTION_DIRECTIVE", codes)
        self.assertNotIn("UNCITED_FACTUAL_PARAGRAPH", codes)

    def test_numeric_citation_requires_matching_reference_entry(self):
        report = """# 调研报告

## 公开进展

甲省在 2026 年完成应急通信演练。[1]

## 资料来源

[2] 甲省应急通信演练公告，2026-06-18。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("UNRESOLVED_NUMERIC_CITATION", codes)

    def test_numeric_citation_with_matching_reference_entries_passes(self):
        report = """# 调研报告

## 公开进展

甲省在 2026 年完成应急通信演练，厂商甲公布工程样机参数。[1-2]

## 资料来源

[1] 甲省应急通信演练公告，2026-06-18。
[2] 厂商甲工程样机规格页，2026-05-29。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("UNRESOLVED_NUMERIC_CITATION", codes)

    def test_bulleted_and_bare_numbered_reference_entries_resolve_citations(self):
        report = """# 调研报告

## 公开进展

甲省在 2026 年完成应急通信演练，厂商甲公布工程样机参数。[1-2]

## 资料来源

- [1] 甲省应急通信演练公告，2026-06-18。
2. 厂商甲工程样机规格页，2026-05-29。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertNotIn("UNRESOLVED_NUMERIC_CITATION", codes)

    def test_pending_reference_metadata_is_flagged_in_formal_copy(self):
        report = """# 调研报告

## 公开进展

甲省在 2026 年完成应急通信演练。[1]

## 资料来源

[1] 甲省应急通信演练公告，2026-06-18。发布主体、文号、URL：待补。
"""
        result = audit_report.audit_text(report)
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("FORMAL_UNFINISHED_STATUS", codes)

    def test_cli_emits_valid_json(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(MIXED_FIXTURE), "--json"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(2, payload["schema_version"])
        self.assertEqual("formal", payload["document_role"])
        self.assertGreater(payload["summary"]["findings"], 0)
        self.assertIn("启发式", payload["disclaimer"])

    def test_fail_on_warning_sets_nonzero_exit(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                str(MIXED_FIXTURE),
                "--fail-on",
                "warning",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(1, completed.returncode)

    def test_unreadable_input_returns_usage_error(self):
        missing = Path(tempfile.gettempdir()) / "research-report-missing.md"
        if missing.exists():
            missing.unlink()
        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(missing)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("cannot read", completed.stderr)


if __name__ == "__main__":
    unittest.main()
