"""Bounded, offline research intake for the existing weekly review state.

This module schedules human/agent research; it never searches the network or
interprets file changes as proof of changed skill behaviour.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

TRIGGERS = {"user_feedback", "eval_gap", "source_unknown"}
TRIGGER_PRIORITY = {"user_feedback": 0, "eval_gap": 1, "source_unknown": 2}
OUTCOMES = {"candidates", "no_benefit", "blocked"}
SKILL_LIMIT = 3
CANDIDATE_LIMIT = 2


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def local_content_digest(root: Path) -> str:
    """Same byte-level signal as upstream maintenance's local_skill_digest."""
    value = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if any(part in {".git", "__pycache__", ".pytest_cache", ".mypy_cache"} for part in relative.parts):
            continue
        if relative.as_posix() == "references/upstream-sources.md" or path.suffix in {".pyc", ".pyo"}:
            continue
        value.update(relative.as_posix().encode("utf-8") + b"\0")
        value.update(hashlib.sha256(path.read_bytes()).digest())
    return value.hexdigest()


def week_key(value: str) -> str:
    day = date.fromisoformat(value)
    return (day - timedelta(days=(day.weekday() - 5) % 7)).isoformat()


def validate_extension(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("discovery state must be an object")
    for key in ("tasks", "weeks", "snapshots", "reviews"):
        if key in value and not isinstance(value[key], dict):
            raise ValueError(f"discovery.{key} must be an object")
        if any(not isinstance(row, dict) for row in value.get(key, {}).values()):
            raise ValueError(f"discovery.{key} entries must be objects")


def read_inventory(roots: dict[str, Path], summaries: dict[str, Any], hash_tree) -> tuple[dict, list]:
    inventory, errors = {}, []
    for scope, root in roots.items():
        summary = summaries.get(scope) or {}
        registered = {str(row.get("name")): row for row in summary.get("local_skills", [])}
        try:
            children = sorted(root.iterdir())
        except OSError as exc:
            errors.append(f"{scope} source inventory: {exc.__class__.__name__}")
            continue
        for child in children:
            # An explicit source root is the maintenance boundary. Never follow
            # links to installed packages or outside that root.
            if not child.is_dir() or child.is_symlink() or not (child / "SKILL.md").is_file():
                continue
            if not child.resolve().is_relative_to(root.resolve()):
                continue
            key = f"{scope}:{child.name}"
            row = registered.get(child.name, {})
            try:
                content_digest = hash_tree(child)
            except OSError as exc:
                errors.append(f"{key} content inventory: {exc.__class__.__name__}")
                continue
            inventory[key] = {
                "skill_key": key, "name": child.name, "source_scope": scope,
                "local_digest": content_digest, "status": row.get("status", "unregistered"),
                "adopted": copy.deepcopy(row.get("adopted", [])),
            }
    return inventory, errors


def task_key(skill_key: str, trigger: str, purpose: str) -> str:
    return "research-" + digest([skill_key, trigger, purpose])[:20]


def candidate_key(candidate: dict) -> str:
    # The URL/path pair is the candidate identity; evidence changes reopen review.
    return digest([candidate["repo_url"].rstrip("/").removesuffix(".git").lower(),
                   candidate["upstream_path"].strip("/")])[:20]


def require_text(row: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f"{field} must be nonempty text")


def update_discovery(state: dict, *, inventory: dict, date_value: str, intake: Any = None) -> dict:
    """Transactionally update optional state. A bad intake leaves this state intact."""
    extension = copy.deepcopy(state.get("discovery", {}))
    validate_extension(extension)
    for field in ("tasks", "weeks", "snapshots", "reviews"):
        extension.setdefault(field, {})
    tasks, reviews = extension["tasks"], extension["reviews"]
    payload = {} if intake is None else intake
    if not isinstance(payload, dict) or payload.get("schema_version", 1) != 1:
        raise ValueError("discovery input must be a schema_version=1 object")
    for field in ("triggers", "results"):
        if not isinstance(payload.get(field, []), list):
            raise ValueError(f"discovery input {field} must be a list")

    def add_trigger(row: dict) -> None:
        if not isinstance(row, dict):
            raise ValueError("trigger must be an object")
        require_text(row, ("skill_key", "trigger", "purpose", "evidence"))
        if row["skill_key"] not in inventory or row["trigger"] not in TRIGGERS:
            raise ValueError("trigger requires a maintained skill and an allowed reason")
        key = task_key(row["skill_key"], row["trigger"], row["purpose"])
        evidence_hash = digest(row["evidence"])
        previous = tasks.get(key)
        if previous and previous["evidence_fingerprint"] == evidence_hash:
            return
        history = copy.deepcopy(previous.get("history", [])) if previous else []
        if previous:
            history.append({"evidence_fingerprint": previous["evidence_fingerprint"],
                            "status": previous["status"], "result": previous.get("result")})
        tasks[key] = {"id": key, **{k: row[k] for k in ("skill_key", "trigger", "purpose", "evidence")},
                      "evidence_fingerprint": evidence_hash, "status": "pending",
                      "first_seen": previous["first_seen"] if previous else date_value,
                      "history": history}

    # Only explicitly unresolved provenance triggers research. A self-created
    # skill registered as none is a normal state, as is an absent registry entry.
    for key, row in inventory.items():
        if row["status"] in {"pending", "unknown", "needs_research"}:
            add_trigger({"skill_key": key, "trigger": "source_unknown",
                         "purpose": "resolve-provenance", "evidence": f"registry status: {row['status']}"})
        prior = extension["snapshots"].get(key)
        if row["status"] == "unregistered" and prior:
            row = {**row, "adopted": copy.deepcopy(prior.get("adopted", []))}
        if prior is None:
            accepted = {item.get("accepted_local_digest") for item in row["adopted"]
                        if isinstance(item, dict) and item.get("accepted_local_digest")}
            if len(accepted) == 1:
                prior = {"local_digest": next(iter(accepted)), "adopted": row["adopted"]}
        if prior and prior["local_digest"] != row["local_digest"] and (prior.get("adopted") or row["adopted"]):
            review_id = "local-" + digest(key)[:20]
            reviews[review_id] = {
                "id": review_id, "kind": "local_capability_review", "skill_key": key,
                "evidence": {"before": prior["local_digest"], "after": row["local_digest"],
                             "previous_adopted": prior.get("adopted", []), "adopted": row["adopted"]},
                "summary": "本地内容已变化，请人工核对登记的已吸收能力：有意删除则更新说明，疑似退化则评测；文件差异不能证明行为退化。",
            }
        # Retain adopted claims if a source scan failed; do not erase the last
        # successful provenance information with an empty fallback inventory.
        snapshot = copy.deepcopy(row)
        if row["status"] == "unregistered" and prior:
            snapshot["adopted"] = copy.deepcopy(prior.get("adopted", []))
        extension["snapshots"][key] = snapshot
    for row in payload.get("triggers", []):
        add_trigger(row)

    week = week_key(date_value)
    budget = extension["weeks"].setdefault(week, {"skills": [], "candidates": {}})
    # Persist admission before accepting results: a result cannot spend another
    # week's allowance or research an unselected skill.
    pending = sorted((t for t in tasks.values() if t["status"] == "pending" and t["skill_key"] in inventory),
                     key=lambda t: (TRIGGER_PRIORITY[t["trigger"]], t["first_seen"], t["id"]))
    for task in pending:
        key = task["skill_key"]
        if key not in budget["skills"] and len(budget["skills"]) < SKILL_LIMIT:
            budget["skills"].append(key)

    for result in payload.get("results", []):
        if not isinstance(result, dict):
            raise ValueError("research result must be an object")
        require_text(result, ("task_id", "outcome", "evidence", "expected_evidence_fingerprint"))
        task = tasks.get(result["task_id"])
        if task is None or task["skill_key"] not in budget["skills"]:
            raise ValueError("result does not belong to an admitted research task")
        if result["expected_evidence_fingerprint"] != task["evidence_fingerprint"]:
            raise ValueError("research task evidence changed")
        if result["outcome"] not in OUTCOMES:
            raise ValueError("unknown research outcome")
        candidates = result.get("candidates", [])
        if not isinstance(candidates, list) or (result["outcome"] == "candidates" and not candidates):
            raise ValueError("candidate outcome requires candidates")
        if result["outcome"] != "candidates" and candidates:
            raise ValueError("non-candidate result cannot contain candidates")
        seen = budget["candidates"].setdefault(task["skill_key"], [])
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("candidate must be an object")
            require_text(candidate, ("repo_url", "upstream_path", "revision", "license", "source_evidence", "upstream_improvement",
                                     "local_gap", "expected_benefit", "conflicts"))
            identity = candidate_key(candidate)
            if identity not in seen:
                if len(seen) >= CANDIDATE_LIMIT:
                    raise ValueError("weekly candidate limit exceeded for this skill")
                seen.append(identity)
            review_id = "candidate-" + digest([task["skill_key"], identity])[:20]
            reviews[review_id] = {
                "id": review_id, "kind": "discovery_candidate", "skill_key": task["skill_key"],
                "evidence": copy.deepcopy(candidate),
                "summary": "候选来源待审核：" + candidate["expected_benefit"],
            }
        task["status"] = result["outcome"]
        task["result"] = copy.deepcopy(result)
        task["last_researched"] = date_value
    state["discovery"] = extension
    selected = [copy.deepcopy(task) for task in pending
                if task["skill_key"] in budget["skills"] and task["status"] == "pending"]
    return {"week": week, "limits": {"skills": SKILL_LIMIT, "candidates_per_skill": CANDIDATE_LIMIT},
            "admitted_skills": budget["skills"], "research_tasks": selected,
            "deferred_task_ids": [t["id"] for t in pending if t["skill_key"] not in budget["skills"]],
            "inventory": list(inventory.values()), "reviews": list(reviews.values()),
            "outcomes": [{"task_id": t["id"], "skill_key": t["skill_key"], "status": t["status"]}
                         for t in tasks.values() if t["status"] != "pending"]}
