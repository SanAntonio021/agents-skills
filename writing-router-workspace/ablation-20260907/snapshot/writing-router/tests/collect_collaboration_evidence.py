"""Extract scoped tool-read evidence from the exact eval-agent rollout files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def collect(path: Path, agent_id: str) -> dict:
    calls = {}
    reads = []
    token_usage = None
    child_spawned = False
    session_id = None
    partial_lines = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            partial_lines += 1
            continue
        payload = event.get("payload", {})
        if event.get("type") == "session_meta":
            session_id = payload.get("id")
        if event.get("type") == "event_msg" and payload.get("type") == "token_count":
            token_usage = (payload.get("info") or {}).get("total_token_usage") or token_usage
        if event.get("type") != "response_item":
            continue
        kind = payload.get("type")
        if kind in {"function_call", "custom_tool_call"}:
            invocation = payload.get("input") or payload.get("arguments") or ""
            calls[payload.get("call_id")] = {"line": line_number, "input": invocation}
            child_spawned |= "spawn_agent(" in invocation or payload.get("name") == "spawn_agent"
        elif kind in {"function_call_output", "custom_tool_call_output"}:
            output = "\n".join(strings(payload.get("output")))
            call = calls.get(payload.get("call_id"), {})
            if "collaborative-writing.md" in call.get("input", "") and "# 文稿协作" in output:
                reads.append({"call_id": payload.get("call_id"),
                              "call_line": call["line"], "output_line": line_number})
    if session_id != agent_id:
        raise ValueError(f"Rollout identity mismatch: {path}")
    return {"agent_id": agent_id, "rollout": str(path),
            "workflow_read_observed": bool(reads), "workflow_read_receipts": reads,
            "child_agent_spawn_observed": child_spawned, "tool_calls": len(calls),
            "token_usage": token_usage, "unparsed_lines": partial_lines}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = []
    for run in manifest["runs"]:
        evidence = collect(Path(run["rollout"]), run["agent_id"])
        output = Path(run["run_root"]) / "tool-evidence.json"
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"case": run["case"], "version": run["version"], **evidence})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
