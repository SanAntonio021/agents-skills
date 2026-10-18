"""Bounded, fail-closed paragraph evaluation. Python standard library only.

Usage: python -B run_evaluation.py --host claude --version baseline --case ID
Codex exec currently fails closed: read-only is not a read allowlist, and an
ephemeral exec cannot be resumed. No replacement model or transcript replay.
Claude uses bare mode, no built-in tools, and one private stdio MCP reader.
This is model-tool isolation, NOT an OS sandbox against a compromised CLI.
CLI/provider internal writes and provider-side retention are outside this boundary.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid


ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = ROOT.parent.parent
VOCAB_ROOT = SKILLS_ROOT.parent / "vocab"
CASE_FILE = SKILLS_ROOT / "writing-router" / "evals" / "paragraph-quality.json"
MODELS = {"codex": "gpt-5.6-sol", "claude": "claude-opus-5"}
SKILLS = {"writing-router", "project-writing", "technical-writing",
          "research-report", "meeting-notes", "ieee-manuscript-edit", "style-vocab"}
TOOL = "mcp__snapshot__read_file"
SENSITIVE = re.compile(
    r"^(?:authorization|proxy.?authorization|.*api.?key.*|.*secret.*|password|"
    r"passwd|cookie|set.?cookie|credentials?|authentication|auth|auth.?token|"
    r"access.?token|refresh.?token|id.?token|client.?secret|token)$", re.I)


class Gap(RuntimeError):
    """A capability, evidence, or safety gate failed; not a model result."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if SENSITIVE.match(k) else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    for key, secret in os.environ.items():
        if len(secret) >= 8 and re.search(r"KEY|TOKEN|SECRET|PASSWORD|COOKIE|AUTH", key, re.I):
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", "[REDACTED]", value, flags=re.I)
    value = re.sub(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@", r"\1[REDACTED]@", value)
    value = re.sub(r"(?i)([?&](?:api[_-]?key|token|key|access_token)=)[^&\s\"']+",
                   r"\1[REDACTED]", value)
    value = re.sub(r"(?i)((?:api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|"
                   r"password|authorization|cookie)\s*[=:]\s*)[^\r\n]+",
                   r"\1[REDACTED]", value)
    return value


def write_json(path, value):
    path.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_json(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(redact(value), ensure_ascii=False) + "\n")


def regular_path(path, root):
    path, root = Path(path).absolute(), Path(root).absolute()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise Gap("Path outside approved root") from exc
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
            raise Gap("Symlink/junction not permitted: " + str(item))
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise Gap("Not an approved regular file: " + str(path))
    return path.resolve()


def load_case(path, case_id):
    raw = path.read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    cases = document if isinstance(document, list) else document.get("cases", document.get("evals"))
    if not isinstance(cases, list):
        raise Gap("Fixture must be a list or an object with cases/evals")
    matches = [case for case in cases if str(case.get("id")) == case_id]
    if len(matches) != 1:
        raise Gap("Case ID missing or duplicated")
    case = matches[0]
    if case.get("entry_skill") not in SKILLS:
        raise Gap("entry_skill is not one of the seven snapshot skills")
    turns = case.get("turns")
    if not isinstance(turns, list) or not turns:
        raise Gap("Case has no turns")
    # Only this projection can reach the child. No expectations or future turns.
    prompts = []
    for turn in turns:
        if not isinstance(turn, dict) or not isinstance(turn.get("prompt"), str) or not turn["prompt"].strip():
            raise Gap("Each turn must contain a nonempty prompt")
        prompts.append(turn["prompt"])
    return {"id": case_id, "entry_skill": case["entry_skill"], "prompts": prompts,
            "fixture_sha256": digest(raw)}


def inventory(snapshot, vocab):
    if {p.name for p in snapshot.iterdir() if p.is_dir()} != SKILLS:
        raise Gap("Snapshot must contain exactly the seven skill directories")
    entries = {}
    for skill in sorted(SKILLS):
        paths = [snapshot / skill / "SKILL.md"]
        refs = snapshot / skill / "references"
        if refs.exists():
            paths += sorted(refs.rglob("*.md"))
        for path in paths:
            path = regular_path(path, snapshot)
            key = "skills/" + path.relative_to(snapshot.resolve()).as_posix()
            data = path.read_bytes()
            data.decode("utf-8-sig")
            entries[key] = {"path": str(path), "root": str(snapshot.resolve()), "sha256": digest(data)}
    if not vocab.is_dir():
        raise Gap("Local vocabulary directory missing")
    for path in sorted(vocab.rglob("*.md")):
        # Maintenance/candidate material is not ordinary writing vocabulary.
        if path.name == "\u7ef4\u62a4.md":
            continue
        path = regular_path(path, vocab)
        key = "vocab/" + path.relative_to(vocab.resolve()).as_posix()
        data = path.read_bytes()
        data.decode("utf-8-sig")
        entries[key] = {"path": str(path), "root": str(vocab.resolve()), "sha256": digest(data)}
    if not any(key.startswith("vocab/") for key in entries):
        raise Gap("No vocabulary files available")
    return entries


def lock_vocab(entries, path):
    current = {key: value["sha256"] for key, value in entries.items() if key.startswith("vocab/")}
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(current, stream, ensure_ascii=False, sort_keys=True)
    except FileExistsError:
        if json.loads(path.read_text(encoding="utf-8")) != current:
            raise Gap("Vocabulary changed; baseline/candidate comparison is blocked")
    return digest(json.dumps(current, sort_keys=True, ensure_ascii=False).encode("utf-8"))


class FileBroker:
    def __init__(self, entries, ledger, turn_file):
        self.entries, self.ledger, self.turn_file = entries, ledger, turn_file

    def read(self, name, request_id=None):
        entry = self.entries.get(name)
        # Absolute snapshot references are accepted only by exact manifest match.
        if entry is None and isinstance(name, str):
            normalized = name.replace("\\", "/").casefold()
            found = [(key, item) for key, item in self.entries.items()
                     if item["path"].replace("\\", "/").casefold() == normalized]
            if len(found) == 1:
                name, entry = found[0]
        if entry is None:
            append_json(self.ledger, {"status": "denied", "requested": name, "request_id": request_id})
            raise Gap("File is not in the read allowlist")
        path = regular_path(entry["path"], entry["root"])
        data = path.read_bytes()
        if digest(data) != entry["sha256"]:
            append_json(self.ledger, {"status": "hash_changed", "name": name})
            raise Gap("Approved file changed after preflight")
        text = data.decode("utf-8-sig")
        turn = int(self.turn_file.read_text(encoding="utf-8"))
        append_json(self.ledger, {"status": "read", "name": name, "path": str(path),
                                 "sha256": digest(data), "bytes": len(data), "turn": turn,
                                 "request_id": request_id, "time": time.time()})
        return text


def serve_reader(run_dir):
    run_dir = run_dir.resolve()
    if not run_dir.is_relative_to(ROOT / "runs") and not run_dir.is_relative_to(ROOT / "selftests"):
        raise Gap("Reader run directory is outside evaluation workspace")
    entries = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    broker = FileBroker(entries, run_dir / "reads.jsonl", run_dir / "current-turn.txt")
    for line in sys.stdin:
        request = json.loads(line)
        request_id, method = request.get("id"), request.get("method")
        if request_id is None:
            continue
        result = {}
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "paragraph-snapshot-reader", "version": "1.0"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "read_file", "description": "Read one approved skill/reference/vocabulary file.",
                                 "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}},
                                                 "required": ["path"], "additionalProperties": False}}]}
        elif method == "tools/call":
            try:
                params = request.get("params", {})
                if params.get("name") != "read_file":
                    raise Gap("Unknown tool")
                result = {"content": [{"type": "text", "text": broker.read(params.get("arguments", {}).get("path"), request_id)}]}
            except (Gap, OSError, ValueError, TypeError) as exc:
                result = {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        elif method != "ping":
            print(json.dumps({"jsonrpc": "2.0", "id": request_id,
                              "error": {"code": -32601, "message": "Method not available"}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, ensure_ascii=False), flush=True)


class OwnedProcess:
    """On Windows, assign the suspended child to a kill-on-close Job first."""
    def __init__(self, command, cwd, env):
        self.job = None
        options = dict(cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
        if os.name == "nt":
            from ctypes import wintypes as w

            class Basic(ctypes.Structure):
                _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                            ("Flags", w.DWORD), ("MinWS", ctypes.c_size_t), ("MaxWS", ctypes.c_size_t),
                            ("ActiveLimit", w.DWORD), ("Affinity", ctypes.c_size_t),
                            ("Priority", w.DWORD), ("Scheduling", w.DWORD)]

            class Limits(ctypes.Structure):
                _fields_ = [("Basic", Basic), ("Io", ctypes.c_uint64 * 6),
                            ("ProcessMemory", ctypes.c_size_t), ("JobMemory", ctypes.c_size_t),
                            ("PeakProcess", ctypes.c_size_t), ("PeakJob", ctypes.c_size_t)]

            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
            self.kernel.CreateJobObjectW.restype = w.HANDLE
            self.kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
            self.kernel.SetInformationJobObject.restype = w.BOOL
            self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            self.kernel.AssignProcessToJobObject.restype = w.BOOL
            self.kernel.CloseHandle.argtypes = [w.HANDLE]
            self.kernel.CloseHandle.restype = w.BOOL
            self.job = self.kernel.CreateJobObjectW(None, None)
            if not self.job:
                raise Gap("Cannot create owned Windows Job")
            limits = Limits()
            limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            if not self.kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                self.kernel.CloseHandle(self.job)
                self.job = None
                raise Gap("Cannot configure owned Windows Job")
            try:
                self.process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW | 0x4, **options)
                if not self.kernel.AssignProcessToJobObject(self.job, int(self.process._handle)):
                    raise Gap("Cannot assign suspended child to owned Job")
                resume = ctypes.WinDLL("ntdll").NtResumeProcess
                resume.argtypes, resume.restype = [w.HANDLE], ctypes.c_long
                if resume(int(self.process._handle)) != 0:
                    raise Gap("Cannot resume owned child")
            except BaseException:
                if hasattr(self, "process"):
                    self.process.kill()
                    self.process.wait(timeout=10)
                self.kernel.CloseHandle(self.job)
                self.job = None
                raise
        else:
            self.process = subprocess.Popen(command, start_new_session=True, **options)

    def stop(self):
        if os.name == "nt":
            if self.job:
                self.kernel.CloseHandle(self.job)
                self.job = None
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.process.wait(timeout=10)


def resolve_cli(host):
    home = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules"
    if host == "claude":
        path = home / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if path.is_file():
            return [str(path)]
    else:
        path = home / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        if path.is_file() and node:
            return [node, str(path)]
    executable = shutil.which(host)
    if executable and Path(executable).suffix.lower() not in {".cmd", ".ps1", ".bat"}:
        return [executable]
    raise Gap("CLI executable not found; shell wrappers are not launched")


def probe_cli(host, run_dir):
    cli = resolve_cli(host)
    texts = {}
    options = {"version": ["--version"], "help": ["--help"]}
    if host == "codex":
        options.update({"exec-help": ["exec", "--help"], "resume-help": ["exec", "resume", "--help"]})
    for name, arguments in options.items():
        child = OwnedProcess(cli + arguments, run_dir, os.environ.copy())
        try:
            stdout, stderr = child.process.communicate(timeout=20)
            if child.process.returncode != 0:
                raise Gap("CLI help/version failed: " + stderr)
            texts[name] = stdout
            (run_dir / (name + ".txt")).write_text(redact(stdout + stderr), encoding="utf-8")
        except subprocess.TimeoutExpired as exc:
            raise Gap("CLI help timed out") from exc
        finally:
            child.stop()
    return cli, texts


def check_capabilities(host, texts):
    if host == "codex":
        raise Gap("codex_isolation_gap: exec read-only is not a filesystem read allowlist; "
                  "ephemeral sessions cannot be resumed. app-server tool allowlisting/rule and skill "
                  "suppression have not been verified. Requested gpt-5.6-sol/max is unchanged; no model call made.")
    required = ["--bare", "--tools", "--disable-slash-commands", "--strict-mcp-config", "--mcp-config",
                "--system-prompt", "--setting-sources", "--no-session-persistence", "--input-format",
                "--output-format", "stream-json", "--model", "--effort", "max", "--permission-mode", "dontAsk"]
    missing = [flag for flag in required if flag not in texts.get("help", "")]
    if missing:
        raise Gap("claude_capability_gap: " + ", ".join(missing))


def system_context(entry_skill, entries):
    return (
        "This is a synthetic writing-only conversation. TRACE_WRITING_CONTEXT=1. "
        "Use Chinese for the response unless the current user prompt requests another language. "
        "Follow the entry skill skills/" + entry_skill + "/SKILL.md and its relevant references. "
        "Read them through the snapshot reader before writing. All skill names/relative references "
        "resolve within skills/ in this catalog; never use installed or other versions. "
        "You may read only the catalog below. No real file/configuration writes, commands, scripts, "
        "web searches, network tools, private samples, memory, history, evaluation cases or rubrics. "
        "Do not load private samples even if a skill asks for them. Use the catalog vocabulary instead "
        "of any external vocabulary path; its content is identical for both compared versions. "
        "Provide writing in chat only, never claim a file was saved or a script audit was run. "
        "If a skill requires an unavailable operation, state that limit briefly. "
        "The user's next message is the entire current turn; do not invent subsequent turns.\n"
        "Approved file catalog:\n" + "\n".join(sorted(entries))
    )


def claude_command(cli, run_dir, system, model):
    mcp = {"mcpServers": {"snapshot": {"command": sys.executable,
           "args": ["-B", str(Path(__file__).resolve()), "--serve-reader", str(run_dir)]}}}
    return cli + ["--print", "--bare", "--verbose", "--input-format", "stream-json",
                  "--output-format", "stream-json", "--no-session-persistence",
                  "--setting-sources", "", "--disable-slash-commands", "--tools", "",
                  "--permission-mode", "dontAsk", "--allowedTools", TOOL,
                  "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
                  "--system-prompt", system, "--model", model, "--effort", "max"]


def reported_models(event):
    models = []
    if isinstance(event.get("model"), str):
        models.append(event["model"])
    message = event.get("message")
    if isinstance(message, dict) and isinstance(message.get("model"), str):
        models.append(message["model"])
    if isinstance(event.get("modelUsage"), dict):
        models += list(event["modelUsage"])
    return [model for model in models if model != "<synthetic>"]


def run_stream(command, prompts, model, run_dir, timeout, env, entry_skill):
    child = OwnedProcess(command, run_dir, env)
    process = child.process
    events = queue.Queue()
    session_id = None
    started = time.monotonic()
    report = {"status": "running", "pid": process.pid, "requested_model": model,
              "requested_effort": "max", "reported_models": [], "turns": [], "timed_out": False,
              "model_evidence_limit": "CLI reports only; upstream model identity/effort is not independently attested."}

    def pump(stream, kind):
        try:
            for line in stream:
                events.put((kind, line))
        finally:
            events.put((kind, None))

    threads = [threading.Thread(target=pump, args=(process.stdout, "stdout"), daemon=True),
               threading.Thread(target=pump, args=(process.stderr, "stderr"), daemon=True)]
    for thread in threads:
        thread.start()
    active = 0
    init_seen = False

    def record(kind, line):
        if kind == "stderr":
            with (run_dir / "stderr.txt").open("a", encoding="utf-8") as output:
                output.write(redact(line))
            return None
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("Event is not an object")
        except (json.JSONDecodeError, ValueError):
            with (run_dir / "stdout-unparsed.txt").open("a", encoding="utf-8") as output:
                output.write(redact(line))
            raise Gap("Malformed CLI event; cannot establish turn boundaries")
        append_json(run_dir / "events.jsonl", {"turn": active, "time": time.time(), "event": event})
        return event

    try:
        for index, prompt in enumerate(prompts, 1):
            active = index
            turn_dir = run_dir / ("turn-%02d" % index)
            turn_dir.mkdir()
            (run_dir / "current-turn.txt").write_text(str(index), encoding="utf-8")
            message = {"type": "user", "message": {"role": "user", "content": prompt}}
            write_json(turn_dir / "request.json", {"requested_model": model, "requested_effort": "max", "input": message})
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()
            deadline = time.monotonic() + timeout
            assistant_text = []
            turn_models = set()
            result = None
            while result is None:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("Turn %d exceeded %.1f seconds" % (index, timeout))
                try:
                    kind, line = events.get(timeout=left)
                except queue.Empty as exc:
                    raise TimeoutError("No turn completion before timeout") from exc
                if line is None:
                    if kind == "stdout":
                        raise Gap("CLI exited before a result event")
                    continue
                event = record(kind, line)
                if event is None:
                    continue
                event_session = event.get("session_id")
                if event_session:
                    if session_id and event_session != session_id:
                        raise Gap("CLI session changed within one case")
                    session_id = event_session
                for reported in reported_models(event):
                    turn_models.add(reported)
                    if reported not in report["reported_models"]:
                        report["reported_models"].append(reported)
                    if reported != model:
                        raise Gap("Reported model mismatch: " + reported)
                if event.get("type") == "system" and event.get("subtype") == "init":
                    init_seen = True
                    advertised = event.get("tools")
                    if advertised != [TOOL]:
                        raise Gap("Unexpected available tools or missing reader: " + str(advertised))
                    if event.get("skills") or event.get("plugins"):
                        raise Gap("Installed skills/plugins leaked into bare session")
                if event.get("type") == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use" and block.get("name") != TOOL:
                            raise Gap("Unexpected tool call: " + str(block.get("name")))
                        if block.get("type") == "text":
                            assistant_text.append(block.get("text", ""))
                    (turn_dir / "assistant-partial.txt").write_text(redact("\n".join(assistant_text)), encoding="utf-8")
                if event.get("type") == "result":
                    result = event
            if result.get("is_error") or result.get("subtype") not in {None, "success"}:
                raise Gap("CLI result error: " + str(result.get("errors", result.get("result", result.get("subtype")))))
            if not init_seen or not session_id:
                raise Gap("Missing initialization/session evidence")
            if not turn_models:
                raise Gap("No reported model evidence for this turn")
            body = result.get("result")
            if not isinstance(body, str) or not body.strip():
                body = "\n".join(assistant_text)
            if not body.strip():
                raise Gap("Empty response")
            (turn_dir / "body.txt").write_text(redact(body), encoding="utf-8")
            turn_report = {"turn": index, "status": "completed", "reported_models": sorted(turn_models),
                           "session_id": session_id, "result": result}
            write_json(turn_dir / "execution.json", turn_report)
            report["turns"].append({k: v for k, v in turn_report.items() if k != "result"})
        process.stdin.close()
        process.wait(timeout=15)
        if process.returncode != 0:
            raise Gap("CLI returned nonzero exit code: " + str(process.returncode))
        reads_path = run_dir / "reads.jsonl"
        reads = [json.loads(line) for line in reads_path.read_text(encoding="utf-8").splitlines()] if reads_path.exists() else []
        if not any(row.get("status") == "read" and row.get("name") == "skills/" + entry_skill + "/SKILL.md" for row in reads):
            raise Gap("No actual entry-skill file read evidence")
        if any(row.get("status") == "hash_changed" for row in reads):
            raise Gap("An approved source changed during the session")
        report["status"] = "completed"
    except (Gap, OSError, TimeoutError, subprocess.TimeoutExpired) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        report["failed_turn"] = active
        report["timed_out"] = isinstance(exc, (TimeoutError, subprocess.TimeoutExpired))
    finally:
        child.stop()
        for thread in threads:
            thread.join(timeout=5)
        # Preserve tail/error output even when processing stopped at the first failure.
        while not events.empty():
            kind, line = events.get_nowait()
            if line is not None:
                try:
                    record(kind, line)
                except Gap:
                    pass
        for stream in (process.stdin, process.stdout, process.stderr):
            if not stream.closed:
                stream.close()
        report["exit_code"] = process.returncode
        report["duration_seconds"] = round(time.monotonic() - started, 3)
        report["session_id"] = session_id
        write_json(run_dir / "execution.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=sorted(MODELS))
    parser.add_argument("--version", choices=["baseline", "candidate"])
    parser.add_argument("--case")
    parser.add_argument("--timeout", type=float, default=300, help="Per-turn deadline in seconds")
    parser.add_argument("--preflight-only", action="store_true", help="No model request")
    parser.add_argument("--serve-reader", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_reader:
        serve_reader(args.serve_reader)
        return 0
    if not args.host or not args.version or not args.case:
        parser.error("--host, --version and --case are required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", args.case) or args.timeout <= 0:
        parser.error("Unsafe case ID or nonpositive timeout")
    runs = ROOT / "runs"
    runs.mkdir(exist_ok=True)
    run_dir = runs / (args.host + "-" + args.version + "-" + args.case + "-" + uuid.uuid4().hex)
    run_dir.mkdir()
    metadata = {"host": args.host, "version": args.version, "case": args.case,
                "requested_model": MODELS[args.host], "requested_effort": "max",
                "private_samples": "disabled_for_both_versions", "trace_writing_context": "1",
                "status": "preflight", "run_dir": str(run_dir),
                "isolation": "model has no built-in tools; exact-manifest stdio reader only",
                "limitations": ["Not an OS sandbox against compromised CLI/provider",
                                "CLI/auth/provider internal I/O is outside model-tool isolation",
                                "Read ledger proves broker reads, not model comprehension",
                                "Scripts and maintenance vocabulary unavailable equally in both versions",
                                "CLI model report does not attest upstream identity or effective effort"]}
    try:
        cli, texts = probe_cli(args.host, run_dir)
        metadata["cli"] = cli
        metadata["cli_version"] = texts["version"].strip()
        check_capabilities(args.host, texts)
        case = load_case(CASE_FILE, args.case)
        metadata["fixture_sha256"] = case["fixture_sha256"]
        entries = inventory(ROOT / args.version, VOCAB_ROOT)
        metadata["vocab_manifest_sha256"] = lock_vocab(entries, runs / "vocab-lock.json")
        write_json(run_dir / "manifest.json", entries)
        system = system_context(case["entry_skill"], entries)
        (run_dir / "system.txt").write_text(system, encoding="utf-8")
        # Bare mode deliberately does not consult OAuth/keychain or invoke helpers.
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise Gap("claude_auth_gap: --bare documents ANTHROPIC_API_KEY authentication. "
                      "It is absent from this process. No credentials/configuration were copied or changed.")
        if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            raise Gap("claude_auth_gap: conflicting API key and auth token; precedence not verified")
        metadata["status"] = "preflight_passed"
        if not args.preflight_only:
            env = os.environ.copy()
            for key in list(env):
                if key.startswith(("CLAUDE", "CODEX")) or key.startswith("ANTHROPIC_DEFAULT_") or key == "ANTHROPIC_MODEL":
                    env.pop(key)
            env.update({"TRACE_WRITING_CONTEXT": "1", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
            command = claude_command(cli, run_dir, system, MODELS[args.host])
            result = run_stream(command, case["prompts"], MODELS[args.host], run_dir, args.timeout, env, case["entry_skill"])
            metadata["status"] = result["status"]
            metadata["execution"] = result
            for entry in entries.values():
                path = regular_path(entry["path"], entry["root"])
                if digest(path.read_bytes()) != entry["sha256"]:
                    raise Gap("Snapshot/vocabulary changed during the run; result invalid")
    except (Gap, OSError, ValueError) as exc:
        metadata["status"] = "blocked"
        metadata["error"] = str(exc)
    finally:
        write_json(run_dir / "run.json", metadata)
    print(json.dumps(redact(metadata), ensure_ascii=False))
    return 0 if metadata["status"] in {"completed", "preflight_passed"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
