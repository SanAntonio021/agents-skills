#!/usr/bin/env python3
"""Bind existing JSON document-check results to the files actually checked."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname


VERSION_KEY = "document_versions"
SCRIPT_ROOT = Path(__file__).resolve().parent


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path: str | Path, role: str) -> dict[str, Any]:
    path = Path(path).resolve()
    if not path.is_file():
        return {"path": str(path), "role": role, "sha256": None}
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "role": role, "sha256": digest.hexdigest()}


def require_file(path: str | Path, role: str) -> dict[str, Any]:
    item = fingerprint(path, role)
    if item["sha256"] is None:
        raise ValueError(f"Missing {role} file: {item['path']}")
    return item


class ImageSources(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []
        self.untracked = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "img" and values.get("src"):
            self.sources.append(values["src"] or "")
        if tag in {"img", "source"} and values.get("srcset"):
            self.untracked = True


def image_sources(node: Any) -> tuple[list[str], bool]:
    sources: list[str] = []
    untracked = False
    if isinstance(node, dict):
        if node.get("t") == "Image":
            sources.append(node["c"][-1][0])
        elif node.get("t") in {"RawInline", "RawBlock"} and node["c"][0] == "html":
            parser = ImageSources()
            parser.feed(node["c"][1])
            sources.extend(parser.sources)
            untracked = parser.untracked or bool(parser.sources)
        for value in node.values():
            found, incomplete = image_sources(value)
            sources.extend(found)
            untracked = untracked or incomplete
    elif isinstance(node, list):
        for value in node:
            found, incomplete = image_sources(value)
            sources.extend(found)
            untracked = untracked or incomplete
    return sources, untracked


def template_files(template: Path | None, preset: str | None) -> list[Path]:
    if template is not None and template.suffix.lower() != ".docx":
        return [template.resolve()]
    if template is None and preset is None:
        return []
    # Use the formatter's own preset/profile selection, including absent optional files.
    sys.path.insert(0, str(SCRIPT_ROOT / "template"))
    import word_template_formatter as formatter

    if template is not None:
        template = template.resolve()
        return [template, formatter.default_profile_path(template)]
    name = formatter.canonical_preset_name(preset)
    if name not in formatter.PRESET_PATHS:
        raise ValueError(f"Unknown preset: {preset}")
    paths = formatter.PRESET_PATHS[name]
    if not paths["template"].is_file() and not paths["profile"].is_file():
        raise ValueError(f"No template or profile for preset: {name}")
    return [paths["template"], paths["profile"]]


def capture_inputs(
    sources: list[Path], *, template: Path | None = None, preset: str | None = None,
    images: list[Path] | None = None, pandoc: str = "pandoc",
) -> dict[str, Any]:
    if template is not None and preset is not None:
        raise ValueError("Choose a template or a preset, not both")
    files: dict[tuple[str, str], dict[str, Any]] = {}
    untracked: list[str] = []

    def add(item: dict[str, Any]) -> None:
        files[(item["role"], item["path"])] = item

    for source in sources:
        source = source.resolve()
        add(require_file(source, "source"))
        if source.suffix.lower() in {".md", ".markdown"}:
            completed = subprocess.run(
                [pandoc, str(source), "--from=markdown", "--to=json"],
                cwd=source.parent, capture_output=True, text=True, encoding="utf-8",
                check=True, timeout=60,
            )
            urls, incomplete = image_sources(json.loads(completed.stdout))
            if incomplete:
                untracked.append("raw_html_image")
            for url in urls:
                parsed = urlsplit(url)
                if parsed.scheme == "data":
                    continue  # Inline image bytes are covered by the Markdown hash.
                if parsed.scheme == "file":
                    local = ("//" + parsed.netloc if parsed.netloc else "") + parsed.path
                    add(require_file(Path(url2pathname(local)), "image"))
                    continue
                if parsed.netloc:
                    untracked.append("external_image")
                    continue
                local_url = unquote(parsed._replace(query="", fragment="").geturl())
                if Path(local_url).is_absolute():
                    add(require_file(Path(local_url), "image"))
                    continue
                if parsed.scheme:
                    untracked.append("external_image")
                    continue
                image_path = source.parent / unquote(parsed.path)
                add(require_file(image_path, "image"))
    if template is not None:
        require_file(template, "template")
    for path in template_files(template, preset):
        add(fingerprint(path, "template"))
    for path in images or []:
        add(require_file(path, "image"))
    return {"files": sorted(files.values(), key=lambda item: (item["role"], item["path"])),
            "untracked": sorted(set(untracked))}


def changed_files(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changed = []
    for item in items:
        try:
            current = fingerprint(item["path"], item["role"])
            if current["sha256"] != item["sha256"]:
                changed.append({"path": item["path"], "role": item["role"]})
        except OSError:
            changed.append({"path": item["path"], "role": item["role"]})
    return changed


def read_record(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        return {}


def valid_fingerprint(item: Any, roles: set[str], *, optional: bool = False) -> bool:
    if not isinstance(item, dict) or not isinstance(item.get("role"), str) or item["role"] not in roles:
        return False
    if not isinstance(item.get("path"), str) or not Path(item["path"]).is_absolute():
        return False
    digest = item.get("sha256")
    return (optional and digest is None) or (
        isinstance(digest, str) and len(digest) == 64
        and all(char in "0123456789abcdef" for char in digest)
    )


def validate_versions(record: dict[str, Any], document: Path) -> dict[str, Any] | None:
    versions = record.get(VERSION_KEY)
    if not isinstance(versions, dict) or versions.get("schema_version") != 1:
        return None
    inputs = versions.get("inputs")
    if not isinstance(inputs, dict) or not isinstance(inputs.get("files"), list) or not isinstance(inputs.get("untracked"), list):
        return None
    if not all(valid_fingerprint(item, {"source", "template", "image"}, optional=True) for item in inputs["files"]):
        return None
    for key in ("generated_document", "checked_document"):
        if versions.get(key) is not None:
            if not valid_fingerprint(versions[key], {"document"}) or Path(versions[key]["path"]).resolve() != document.resolve():
                return None
    owner = versions.get("generated_document") or versions.get("checked_document")
    if owner is None or owner.get("sha256") is None or Path(owner["path"]).resolve() != document.resolve():
        return None
    return versions


def protect_record_path(path: Path, document: Path, inputs: dict[str, Any]) -> None:
    if path.suffix.lower() != ".json":
        raise ValueError("The check record must be a JSON file")
    protected = [document] + [Path(item["path"]) for item in inputs["files"]]
    for source in protected:
        if path.resolve() == source.resolve() or (path.exists() and source.exists() and os.path.samefile(path, source)):
            raise ValueError("The check record must not replace a document or input file")


def protect_output_path(document: Path, inputs: dict[str, Any]) -> None:
    for item in inputs["files"]:
        source = Path(item["path"])
        if document.resolve() == source.resolve() or (document.exists() and source.exists() and os.path.samefile(document, source)):
            raise ValueError("The output must not replace a source, template, or image")


def save_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        for attempt in range(4):
            try:
                replace_record(temporary, path)
                break
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep((0.1, 0.25, 0.5)[attempt])
    finally:
        Path(temporary).unlink(missing_ok=True)


def replace_record(temporary: str | Path, path: Path) -> None:
    if os.name != "nt" or not path.exists():
        os.replace(temporary, path)
        return
    # ReplaceFile preserves the existing record's ACL and attributes on Windows.
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    replace = kernel.ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL
    if not replace(str(path.resolve()), str(Path(temporary).resolve()), None, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def record_generation(document: Path, record_path: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    protect_record_path(record_path, document, inputs)
    if changed_files(inputs["files"]):
        raise ValueError("Inputs changed during document generation; the output needs checking")
    result = {"ok": False, "status": "UNCHECKED", VERSION_KEY: {
        "schema_version": 1, "inputs": inputs,
        "generated_document": require_file(document, "document"), "generated_at": now(),
    }}
    save_record(record_path, result)
    return result


def command_identity(command: list[str], kind: str) -> dict[str, Any]:
    executable = shutil.which(command[0]) or command[0]
    normalized = [str(Path(executable).resolve()), *command[1:]]
    tools = []
    for token in normalized:
        path = Path(token)
        if path.suffix.lower() in {".exe", ".py", ".ps1", ".js", ".mjs"} and path.is_file():
            tools.append(fingerprint(path, "checker"))
    digest = hashlib.sha256(json.dumps(normalized, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"kind": kind, "argv_sha256": digest, "tools": tools, "cwd": str(Path.cwd().resolve())}


def checker_passed(result: dict[str, Any]) -> bool:
    status = result.get("status")
    return result.get("ok") is True and (status is None or status == "PASS") and not result.get("error")


def assess(record: dict[str, Any], document: Path, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    versions = validate_versions(record, document)
    if versions is None:
        return {"reusable": False, "status": "NO_VERSION_RECORD", "changed": []}
    inputs_changed = changed_files(versions["inputs"]["files"])
    generated = versions.get("generated_document")
    hand_edited = bool(generated and changed_files([generated]))
    if inputs_changed:
        return {"reusable": False, "status": "INPUTS_CHANGED", "changed": inputs_changed,
                "word_changed_since_generation": hand_edited, "preserve_document": True}
    checked = versions.get("checked_document")
    if not checker_passed(record) or checked is None:
        return {"reusable": False, "status": "CHECK_REQUIRED", "changed": []}
    changed = changed_files([checked])
    if changed:
        return {"reusable": False, "status": "WORD_CHANGED", "changed": changed, "preserve_document": True}
    previous_identity = versions.get("check_identity")
    if not isinstance(previous_identity, dict) or (identity is not None and identity != previous_identity):
        return {"reusable": False, "status": "CHECK_METHOD_CHANGED", "changed": []}
    tools = previous_identity.get("tools")
    outputs = versions.get("check_outputs", [])
    if (not isinstance(tools, list) or not isinstance(outputs, list)
            or not all(valid_fingerprint(item, {"checker"}) for item in tools)
            or not all(valid_fingerprint(item, {"check_output"}) for item in outputs)):
        return {"reusable": False, "status": "NO_VERSION_RECORD", "changed": []}
    if changed_files(tools):
        return {"reusable": False, "status": "CHECK_METHOD_CHANGED", "changed": []}
    if changed_files(outputs):
        return {"reusable": False, "status": "CHECK_OUTPUT_CHANGED", "changed": []}
    if versions["inputs"].get("untracked"):
        return {"reusable": False, "status": "UNTRACKED_INPUTS", "changed": []}
    return {"reusable": True, "status": "CURRENT", "changed": [],
            "check_kind": previous_identity.get("kind"), "checked_at": versions.get("checked_at")}


def run_check(
    document: Path, record_path: Path, command: list[str], *, kind: str,
    inputs: dict[str, Any] | None = None, timeout: float | None = None, refresh: bool = False,
) -> dict[str, Any]:
    office_entrypoints = {"office_native_gate.py", "word_template_formatter.py", "libreoffice_run.py", "reference_word.py"}
    office_command = any(Path(token).name.lower() in office_entrypoints for token in command)
    if timeout is not None and (kind in {"word-native", "libreoffice-render"} or office_command):
        raise ValueError("Office checks manage their own timeout and cleanup; pass timeout options to the existing checker")
    document = document.resolve()
    before_document = require_file(document, "document")
    previous = read_record(record_path)
    versions = validate_versions(previous, document)
    identity = command_identity(command, kind)
    state = assess(previous, document, identity)
    if versions is not None and inputs is not None and inputs != versions["inputs"]:
        state = {"reusable": False, "status": "INPUTS_CHANGED", "changed": [], "preserve_document": True}
    if state["status"] == "INPUTS_CHANGED":
        return {"ok": False, "status": "INPUTS_CHANGED", "version_check": state,
                "message": "Update the output from the current inputs; preserve hand edits and resolve any content conflict first."}
    if state["reusable"] and not refresh:
        return {**previous, "reused": True, "version_check": state}
    inputs = inputs or (versions["inputs"] if versions is not None else {"files": [], "untracked": []})
    protect_record_path(record_path, document, inputs)
    before_inputs = [fingerprint(item["path"], item["role"]) for item in inputs["files"]]
    if before_inputs != inputs["files"]:
        return {"ok": False, "status": "INPUTS_CHANGED", "preserve_document": True}
    started = now()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        exit_code = completed.returncode
        try:
            result = json.loads(completed.stdout.lstrip("\ufeff"))
            if not isinstance(result, dict):
                raise ValueError("The checker must return a JSON object")
        except ValueError:
            result = {"ok": False, "status": "INVALID_CHECK_RESULT", "message": "The checker did not return one JSON object."}
    except (OSError, subprocess.SubprocessError) as exc:
        exit_code = None
        result = {"ok": False, "status": "CHECK_UNAVAILABLE", "message": type(exc).__name__}
    result["ok"] = exit_code == 0 and checker_passed(result)
    if not result["ok"] and (result.get("status") is None or result.get("status") == "PASS"):
        result["status"] = "CHECK_FAILED"
    # Native Office and LibreOffice already identify the checked source; keep that binding honest.
    if result["ok"]:
        for key in ("file", "source"):
            if result.get(key) and (not isinstance(result[key], str) or Path(result[key]).resolve() != document):
                result.update(ok=False, status="CHECK_SOURCE_MISMATCH")
        for key in ("source_sha256", "source_sha256_before", "source_sha256_after"):
            if key in result and (not isinstance(result[key], str) or result[key].lower() != before_document["sha256"]):
                result.update(ok=False, status="CHECK_SOURCE_MISMATCH")
    changed = changed_files(before_inputs + [before_document])
    if changed:
        result.update(ok=False, status="FILES_CHANGED_DURING_CHECK", changed=changed)
    result.update(reused=False, check_exit_code=exit_code)
    outputs = []
    if result["ok"] and result.get("output"):
        output = fingerprint(result["output"], "check_output") if isinstance(result["output"], str) else None
        if output is None or output["sha256"] is None:
            result.update(ok=False, status="CHECK_OUTPUT_MISSING")
        else:
            outputs.append(output)
    result[VERSION_KEY] = {
        "schema_version": 1, "inputs": inputs,
        "generated_document": versions.get("generated_document") if versions else None,
        "checked_document": before_document, "checked_at": started, "check_identity": identity,
        "check_outputs": outputs,
    }
    version_status = "CHECK_REQUIRED"
    if result["ok"]:
        version_status = "UNTRACKED_INPUTS" if inputs.get("untracked") else "CURRENT"
    result["version_check"] = {"reusable": result["ok"] and not inputs.get("untracked"),
                               "status": version_status, "changed": changed}
    save_record(record_path, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    capture = sub.add_parser("capture-inputs", help="capture inputs before producing the Word file")
    generation = sub.add_parser("record-generation", help="read the pre-generation input snapshot from stdin")
    verify = sub.add_parser("verify", help="check whether the saved result still applies; never writes files")
    run = sub.add_parser("run-check", help="reuse or run an explicit JSON checker; never executes commands from a record")
    for child in (capture, run):
        child.add_argument("--source", type=Path, action="append", default=[])
        child.add_argument("--template", type=Path)
        child.add_argument("--preset")
        child.add_argument("--image", type=Path, action="append", default=[])
        child.add_argument("--pandoc", default="pandoc")
    for child in (generation, verify, run):
        child.add_argument("document", type=Path)
        child.add_argument("--record", type=Path, required=True)
    capture.add_argument("--output", type=Path)
    capture.add_argument("--record", type=Path)
    run.add_argument("--kind", required=True, help="name of the actual check, e.g. word-native or libreoffice-render")
    run.add_argument("--timeout", type=float, help="optional deadline for non-Office checks only")
    run.add_argument("--refresh", action="store_true", help="run the requested check again even when its previous result is current")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if "--" in argv:
        index = argv.index("--")
        argv, command = argv[:index], argv[index + 1:]
    args = build_parser().parse_args(argv)
    try:
        if args.operation == "capture-inputs":
            result = capture_inputs(args.source, template=args.template, preset=args.preset, images=args.image, pandoc=args.pandoc)
            if args.output is not None:
                protect_output_path(args.output, result)
                if args.record is not None:
                    protect_record_path(args.record, args.output, result)
            exit_code = 0
        elif args.operation == "record-generation":
            result = record_generation(args.document, args.record, json.loads(sys.stdin.read().lstrip("\ufeff")))
            exit_code = 0
        elif args.operation == "verify":
            result = assess(read_record(args.record), args.document)
            exit_code = 0 if result["reusable"] else 2
        else:
            if not command:
                raise ValueError("run-check requires an explicit checker command after --")
            inputs = None
            if args.source or args.template or args.preset or args.image:
                inputs = capture_inputs(args.source, template=args.template, preset=args.preset, images=args.image, pandoc=args.pandoc)
            result = run_check(args.document, args.record, command, kind=args.kind, inputs=inputs, timeout=args.timeout, refresh=args.refresh)
            exit_code = 0 if result.get("ok") else 2
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "status": "UNVERIFIED", "message": str(exc)}
        exit_code = 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
