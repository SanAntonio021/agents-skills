from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest


SKILLS_ROOT = Path(__file__).resolve().parents[2]
ROUTER = SKILLS_ROOT / "writing-router"
COMMON = ROUTER / "references" / "collaborative-writing.md"
ENTRYPOINTS = ["writing-router", "project-writing", "technical-writing", "research-report",
               "ieee-manuscript-edit", "meeting-notes"]
SUITE = ROUTER / "evals" / "collaborative-writing.json"


@pytest.mark.parametrize("name", ENTRYPOINTS)
def test_entrypoint_resolves_and_loads_one_shared_workflow(name):
    entry = SKILLS_ROOT / name / "SKILL.md"
    text = entry.read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]]+\]\(([^)]+collaborative-writing\.md)\)", text)
    assert len(links) == 1
    assert (entry.parent / links[0]).resolve() == COMMON.resolve()
    assert COMMON.is_file()
    line = next(line for line in text.splitlines() if "collaborative-writing.md" in line)
    assert "loaded_refs" in line and "读取" in line
    assert text.index("collaborative-writing.md") < text.index("## 完成条件")
    if name != "writing-router":
        assert "直接调用本技能时同样执行" in line


@pytest.mark.parametrize("mode", ["draft", "structural", "bounded", "in_place", "audit_only"])
def test_existing_scope_modes_have_workflow_mapping(mode):
    assert f"| `{mode}` |" in COMMON.read_text(encoding="utf-8")


def test_router_loads_workflow_after_context_and_before_prose():
    text = (ROUTER / "SKILL.md").read_text(encoding="utf-8")
    loading = text.split("## 最小加载规则", 1)[1].split("\n## ", 1)[0]
    assert "建立写作上下文后、处理正文前" in loading
    assert "collaborative-writing.md" in loading
    assert "实际路径记入 `loaded_refs`" in loading
    assert text.index("## 最小加载规则") < text.index("## 通用流程")
    assert "不另建记录文件" in text
    assert "同样适用于直接调用文体技能" in loading
    assert "本轮实际读取过的规则和样稿路径" in text
    assert "TRACE_WRITING_CONTEXT=1" in text


def test_workflow_covers_authoring_and_confirmation_boundaries():
    text = COMMON.read_text(encoding="utf-8")
    for fragment in ["结构可以暂定", "实际正文", "未提及段落", "主动询问", "明确认可",
                     "回读当前主稿", "用户的新改动", "直接给出后续正文", "写入受阻",
                     "不要求用户再审一遍完整稿", "独立读者检查按用户要求或明显理解风险"]:
        assert fragment in text
    assert "固定口令" not in text


def test_exceptions_are_checked_before_scope_defaults():
    text = COMMON.read_text(encoding="utf-8")
    for name in ["会议转写整理", "执行期运行日志", "普通润色与纠错", "明确要求直接给出整篇"]:
        assert text.index(name) < text.index("| `draft` |")
    assert "已有模板或材料齐全，本身不改变协作方式" in text
    assert "保持只读" in text


def test_remote_main_and_word_handoff_do_not_force_a_local_main():
    text = COMMON.read_text(encoding="utf-8")
    assert "直接修改飞书无需额外维护本地主稿" in text
    handoff = (ROUTER / "references" / "markdown-docx-contract.md").read_text(encoding="utf-8")
    assert "collaborative-writing.md" in handoff
    assert "飞书主稿通过对应平台技能回读" in handoff
    assert "不作为另一份长期主稿" in handoff
    assert "直接处理任务使用本轮完成的正文" in handoff
    assert "格式阶段不自行改写正文" in handoff


def test_local_shared_rule_routes_instead_of_forcing_markdown():
    path = SKILLS_ROOT.parent / "global-rules" / "shared-rules.md"
    if not path.exists():
        pytest.skip("Host shared-rule file is not part of the standalone skills repository")
    text = path.read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if line.startswith("- 文稿流程："))
    assert "writing-router" in line and "用户选定的主稿" in line
    assert "先保存为 Markdown 文件" not in line


def test_eval_suite_is_synthetic_and_covers_multiturn_and_exceptions():
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    assert suite["fixture_policy"] == "synthetic-only"
    assert len({case["id"] for case in suite["evals"]}) == len(suite["evals"])
    assert {"remote-authoring", "direct-entry-and-exceptions"} == {case["id"] for case in suite["evals"]}
    for case in suite["evals"]:
        assert len(case["turns"]) >= 5
        assert all(turn["prompt"] and turn["expectations"] for turn in case["turns"])


@pytest.fixture
def store_module():
    path = Path(__file__).with_name("fake_document_store.py")
    spec = importlib.util.spec_from_file_location("fake_document_store", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_store_records_writes_without_enforcing_approval(tmp_path, store_module):
    result = store_module.operate(tmp_path, "append", "unapproved candidate")
    assert result["revision"] == 1
    state = json.loads((tmp_path / "document.json").read_text())
    assert state["events"][0]["action"] == "append"


def test_store_preserves_other_blocks_and_records_readback(tmp_path, store_module):
    first = store_module.operate(tmp_path, "append", "initial")["blocks"][0]["id"]
    store_module.operate(tmp_path, "append", "manual edit", actor="user")
    store_module.operate(tmp_path, "fetch")
    result = store_module.operate(tmp_path, "replace", "approved", first)
    assert [b["text"] for b in result["blocks"]] == ["approved", "manual edit"]
    state = json.loads((tmp_path / "document.json").read_text())
    assert state["events"][-2]["action"] == "fetch"


def test_failed_store_write_does_not_change_content(tmp_path, store_module):
    store_module.operate(tmp_path, "append", "preserved")
    store_module.operate(tmp_path, "unavailable", actor="user")
    result = store_module.operate(tmp_path, "append", "not saved")
    assert result == {"error": "store_unavailable", "retryable": False}
    final = store_module.operate(tmp_path, "fetch")
    assert final["revision"] == 1
    assert [b["text"] for b in final["blocks"]] == ["preserved"]


@pytest.fixture
def evidence_module():
    path = Path(__file__).with_name("collect_collaboration_evidence.py")
    spec = importlib.util.spec_from_file_location("collect_collaboration_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evidence_requires_a_matching_tool_output(tmp_path, evidence_module):
    path = tmp_path / "rollout.jsonl"
    events = [
        {"type": "session_meta", "payload": {"id": "synthetic-agent"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call", "name": "exec",
         "call_id": "read-1", "input": "Get-Content collaborative-writing.md"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output",
         "call_id": "read-1", "output": [{"type": "input_text", "text": "# 文稿协作"}]}},
    ]
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    result = evidence_module.collect(path, "synthetic-agent")
    assert result["workflow_read_observed"]
    assert result["workflow_read_receipts"][0]["output_line"] == 3


def test_declared_loaded_ref_alone_is_not_read_evidence(tmp_path, evidence_module):
    path = tmp_path / "rollout.jsonl"
    events = [
        {"type": "session_meta", "payload": {"id": "synthetic-agent"}},
        {"type": "response_item", "payload": {"type": "message", "content": [
            {"text": "loaded_refs: collaborative-writing.md; # 文稿协作"}]}},
    ]
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in events), encoding="utf-8")
    assert not evidence_module.collect(path, "synthetic-agent")["workflow_read_observed"]
    with pytest.raises(ValueError, match="identity mismatch"):
        evidence_module.collect(path, "another-agent")
