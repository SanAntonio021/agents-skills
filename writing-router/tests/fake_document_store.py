"""Offline document API for behavior evals; records writes without approving them."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path


def operate(root: Path, action: str, text: str = "", block_id: str | None = None,
            actor: str = "assistant") -> dict:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "document.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "revision": 0, "next_id": 1, "blocks": [], "events": [], "available": True,
    }
    event = {"action": action, "actor": actor, "revision_before": state["revision"]}
    result = None
    if action == "unavailable":
        state["available"] = False
    elif action != "fetch" and not state["available"]:
        result = {"error": "store_unavailable", "retryable": False}
    elif action in {"append", "overwrite"}:
        block = {"id": f"block-{state['next_id']}", "text": text}
        state["next_id"] += 1
        state["blocks"] = state["blocks"] + [block] if action == "append" else [block]
        state["revision"] += 1
    elif action == "replace":
        blocks = [block for block in state["blocks"] if block["id"] == block_id]
        if len(blocks) != 1:
            result = {"error": "block_not_found", "retryable": False}
        else:
            blocks[0]["text"] = text
            state["revision"] += 1
    elif action != "fetch":
        raise ValueError(f"Unknown action: {action}")
    event.update(revision_after=state["revision"], blocks=deepcopy(state["blocks"]))
    if result:
        event["error"] = result["error"]
    state["events"].append(event)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result or {"revision": state["revision"], "blocks": state["blocks"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("action", choices=["fetch", "append", "replace", "overwrite", "unavailable"])
    parser.add_argument("--text", default="")
    parser.add_argument("--id", dest="block_id")
    parser.add_argument("--actor", default="assistant")
    args = parser.parse_args()
    result = operate(args.root, args.action, args.text, args.block_id, args.actor)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
