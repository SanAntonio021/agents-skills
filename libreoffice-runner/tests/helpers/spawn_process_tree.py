from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _write_event(directory: Path, name: str, payload: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{os.getpid()}-{name}.json"
    target.write_text(json.dumps(payload), encoding="utf-8")


def slot_worker(args: argparse.Namespace) -> int:
    sys.path.insert(0, args.scripts)
    from libreoffice_runner.win32_sync import CapacitySlots

    event_dir = Path(args.event_dir)
    lease = CapacitySlots(Path(args.state_root)).acquire(args.queue_timeout)
    if lease is None:
        _write_event(event_dir, "timeout", {"pid": os.getpid(), "at": time.monotonic()})
        return 2
    _write_event(event_dir, "start", {"pid": os.getpid(), "at": time.monotonic()})
    if args.crash_after_acquire:
        os._exit(23)
    try:
        time.sleep(args.hold)
    finally:
        _write_event(event_dir, "end", {"pid": os.getpid(), "at": time.monotonic()})
        lease.release()
    return 0


def tree_child(args: argparse.Namespace) -> int:
    time.sleep(args.hold)
    return 0


def tree_parent(args: argparse.Namespace) -> int:
    children = [
        subprocess.Popen([sys.executable, __file__, "tree-child", "--hold", str(args.hold)])
        for _ in range(2)
    ]
    Path(args.pid_file).write_text(
        json.dumps({"parent": os.getpid(), "children": [child.pid for child in children]}),
        encoding="utf-8",
    )
    time.sleep(args.hold)
    return 0


def publish_worker(args: argparse.Namespace) -> int:
    sys.path.insert(0, args.scripts)
    from libreoffice_runner.publish import OutputExistsError, publish_exclusive

    source = Path(args.source)
    output = Path(args.output)
    try:
        publish_exclusive(source, output, lambda candidate: None)
    except OutputExistsError as exc:
        Path(args.result).write_text(json.dumps({"ok": False, "error": "output_exists", "message": str(exc)}), encoding="utf-8")
        return 3
    Path(args.result).write_text(json.dumps({"ok": True}), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    slot = subparsers.add_parser("slot-worker")
    slot.add_argument("--scripts", required=True)
    slot.add_argument("--state-root", required=True)
    slot.add_argument("--event-dir", required=True)
    slot.add_argument("--hold", type=float, default=0.25)
    slot.add_argument("--queue-timeout", type=float, default=5.0)
    slot.add_argument("--crash-after-acquire", action="store_true")
    child = subparsers.add_parser("tree-child")
    child.add_argument("--hold", type=float, default=30.0)
    parent = subparsers.add_parser("tree-parent")
    parent.add_argument("--pid-file", required=True)
    parent.add_argument("--hold", type=float, default=30.0)
    publish = subparsers.add_parser("publish-worker")
    publish.add_argument("--scripts", required=True)
    publish.add_argument("--source", required=True)
    publish.add_argument("--output", required=True)
    publish.add_argument("--result", required=True)
    args = parser.parse_args()
    return {
        "slot-worker": slot_worker,
        "tree-child": tree_child,
        "tree-parent": tree_parent,
        "publish-worker": publish_worker,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
