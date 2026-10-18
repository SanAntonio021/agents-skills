"""Run a bounded fresh read-only CLI session against installed skills."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("client", choices=["codex", "claude"])
parser.add_argument("--clarify-fixture", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parent / (args.client + ("-clarified" if args.clarify_fixture else ""))
root.mkdir(parents=True, exist_ok=True)
host_home = os.environ["USERPROFILE"]
prompt = (
    f"这是一次合成材料的正常写作请求。启动环境 USERPROFILE 已解析为 {host_home}。"
    "请按实际加载的全局规则和本平台已安装技能处理，不读取技能源码工作树或旧评测材料。"
    "材料：比较室温与加热后两种状态的温度；有一只传感器和记录电脑；采样间隔1秒，测试时长待定。"
    "请整理成技术方案，主稿预定为本目录 draft.md，给出本次写作的第一条回复。"
    "不要联网、操作设备或读取私有样稿、词表；本次只读验证，不修改任何文档或配置。"
    "TRACE_WRITING_CONTEXT=1"
)
if args.clarify_fixture:
    prompt = prompt.replace("这是一次合成材料的正常写作请求。", "这是虚构测试用例，不对应真实实验；以下事实用于检验写作协作流程。")
(root / "prompt.txt").write_text(prompt, encoding="utf-8")
if args.client == "codex":
    command = [
        r"D:\Program Files\nodejs\node.exe",
        r"C:\Users\SanAn\AppData\Roaming\npm\node_modules\@openai\codex\bin\codex.js",
        "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
        "--json", "--color", "never", "-C", str(root),
        "--output-last-message", str(root / "final.txt"), "-"
    ]
else:
    command = [
        r"C:\Users\SanAn\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
        "--print", "--verbose", "--output-format", "stream-json",
        "--no-session-persistence", "--permission-mode", "dontAsk",
        "--tools", "Read,Glob,Grep,Skill", "--allowedTools", "Read,Glob,Grep,Skill",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}'
    ]
environment = os.environ.copy()
environment["PYTHONDONTWRITEBYTECODE"] = "1"
start = time.monotonic()
process = subprocess.Popen(
    command, cwd=root, env=environment, stdin=subprocess.PIPE,
    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding="utf-8", errors="replace",
    creationflags=subprocess.CREATE_NO_WINDOW
)
timed_out = False
try:
    stdout, stderr = process.communicate(prompt, timeout=240)
except subprocess.TimeoutExpired:
    timed_out = True
    if process.poll() is None:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    stdout, stderr = process.communicate(timeout=20)

def redact(text):
    return re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED]", text)

stdout, stderr = redact(stdout), redact(stderr)
(root / "events.jsonl").write_text(stdout, encoding="utf-8")
(root / "stderr.txt").write_text(stderr, encoding="utf-8")
events = []
for line in stdout.splitlines():
    try:
        events.append(json.loads(line))
    except json.JSONDecodeError:
        continue
final_events = [event for event in events if event.get("type") == "result"]
if args.client == "claude" and final_events:
    (root / "final.txt").write_text(final_events[-1].get("result", ""), encoding="utf-8")
result = {
    "client": args.client, "pid": process.pid, "exit_code": process.returncode,
    "timed_out": timed_out, "duration_seconds": round(time.monotonic() - start, 2),
    "event_count": len(events), "event_types": sorted({e.get("type", "") for e in events}),
    "final_file": str(root / "final.txt"),
    "draft_created": (root / "draft.md").exists(),
    "cli_result_error": final_events[-1].get("is_error") if final_events else None
}
(root / "execution.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(1 if timed_out else process.returncode)
