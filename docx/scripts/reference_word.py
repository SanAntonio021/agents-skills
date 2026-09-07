"""Evaluate reference fields in an owned Word instance, never in the source.

COM result strings are convergence evidence only. The caller must read the
published package's OOXML for transplantation and validate the delivered file
separately. Injection arguments are the native gate's fake-COM test hooks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import tempfile
from typing import Any
from zipfile import ZipFile

from lxml import etree as ET

import office_native_gate as gate


KINDS = ("STYLEREF", "SEQ", "REF", "PAGEREF")
WORD_OPTIONS = (
    "UpdateFieldsAtPrint", "UpdateLinksAtOpen",
    "WarnBeforeSavingPrintingSendingMarkup",
)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class EvaluationFailure(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def _registered_word_server(progid: str) -> Path:
    """Read the effective COM registration without modifying registry or apps."""
    if progid != "Word.Application":
        raise EvaluationFailure("APP_UNAVAILABLE", "only Word.Application registration is supported")
    try:
        import winreg
    except ImportError as exc:
        raise EvaluationFailure("APP_UNAVAILABLE", "Windows registry access is unavailable") from exc

    def read_value(key: Any, name: str, location: str) -> str:
        value, kind = winreg.QueryValueEx(key, name)
        if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not isinstance(value, str) or not value.strip():
            raise EvaluationFailure("APP_UNAVAILABLE", f"{location} is not a nonempty registry string")
        return value.strip()

    location = r"HKCR Word.Application\CLSID"
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID", 0, winreg.KEY_READ) as key:
            clsid = read_value(key, "", location)
        if not re.fullmatch(r"\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}", clsid):
            raise EvaluationFailure("APP_UNAVAILABLE", f"{location} is not a valid CLSID")
        location = "HKCR Word.Application CLSID/LocalServer32"
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32", 0, winreg.KEY_READ) as key:
            try:
                executable = read_value(key, "ServerExecutable", location + " ServerExecutable")
            except FileNotFoundError:
                command = read_value(key, "", location + " default")
                if any(char in command for char in ("\r", "\n", "\x00")):
                    raise EvaluationFailure("APP_UNAVAILABLE", f"{location} command contains control characters")
                match = re.match(r'^(?:"([^"\r\n]+\.exe)"|([^"\r\n]+?\.exe))(?=\s|$)', command, re.I)
                if match is None:
                    raise EvaluationFailure("APP_UNAVAILABLE", f"{location} default has no unambiguous executable")
                executable = match.group(1) or match.group(2)
            else:
                if executable.startswith('"') and executable.endswith('"'):
                    executable = executable[1:-1]
    except OSError as exc:
        raise EvaluationFailure("APP_UNAVAILABLE", f"{location} is missing or unreadable ({type(exc).__name__})") from exc

    if (any(char in executable for char in ('"', "\r", "\n", "\x00"))
            or not executable.lower().endswith(".exe")):
        raise EvaluationFailure("APP_UNAVAILABLE", f"{location} executable is malformed")
    registered = PureWindowsPath(executable)
    if not registered.is_absolute():
        raise EvaluationFailure("APP_UNAVAILABLE", f"{location} executable is not an absolute Windows path")
    if registered.name.upper() != "WINWORD.EXE":
        identity = "WPS (wps.exe)" if registered.name.lower() == "wps.exe" else "a different executable"
        raise EvaluationFailure("APP_UNAVAILABLE", f"{location} registers {identity}, not Microsoft WINWORD.EXE; activation refused")
    path = Path(executable)
    try:
        exists = path.is_file()
    except OSError as exc:
        raise EvaluationFailure("APP_UNAVAILABLE", "registered WINWORD.EXE cannot be inspected") from exc
    if not exists:
        raise EvaluationFailure("APP_UNAVAILABLE", "registered WINWORD.EXE does not exist as a file")
    return path


def native_dispatch(progid: str) -> Any:
    """Create a new late-bound instance without repairing generated COM caches."""
    _registered_word_server(progid)
    from win32com.client import DispatchEx, dynamic
    from pythoncom import IID_IDispatch

    wrapper = DispatchEx(progid, resultCLSID=IID_IDispatch)
    return dynamic.Dispatch(wrapper._oleobj_)


def _normalize(value: str) -> str:
    if not isinstance(value, str):
        raise EvaluationFailure("FIELD_MAP_MISMATCH", "field instruction is not text")
    # Keep identical to reference_fields.normal: quoted spaces are meaningful.
    return " ".join(re.findall(r'"[^"\r\n]*"|[^\s]+', value))


def _items(collection: Any) -> list[Any]:
    return [collection.Item(i) for i in range(1, int(collection.Count) + 1)]


def _required_set(obj: Any, name: str, value: Any) -> None:
    try:
        setattr(obj, name, value)
        if getattr(obj, name) != value:
            raise ValueError(f"did not retain {value!r}")
    except Exception as exc:
        raise EvaluationFailure("SECURITY_OPTIONS_FAILED", f"{name}: {exc}") from exc


def _prepare_copy(source: Path, isolated: Path) -> None:
    # updateFields=true can trigger work during Open, before COM enumeration.
    # Only the disposable evaluation package is normalized here.
    with ZipFile(source) as incoming, ZipFile(isolated, "x") as outgoing:
        names = incoming.namelist()
        if len(names) != len(set(names)):
            raise EvaluationFailure("INVALID_INPUT", "duplicate ZIP members")
        for info in incoming.infolist():
            content = incoming.read(info)
            if info.filename == "word/settings.xml":
                root = ET.fromstring(content, ET.XMLParser(resolve_entities=False, no_network=True))
                if root.getroottree().docinfo.doctype:
                    raise EvaluationFailure("INVALID_INPUT", "DTD declarations are unsupported")
                for flag in root.iter(W + "updateFields"):
                    flag.set(W + "val", "false")
                content = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            outgoing.writestr(info, content)


def _open(application: Any, isolated: Path, *, read_only: bool) -> Any:
    return application.Documents.Open(
        FileName=str(isolated), ConfirmConversions=False, ReadOnly=read_only,
        AddToRecentFiles=False, PasswordDocument="", PasswordTemplate="",
        Revert=False, WritePasswordDocument="", WritePasswordTemplate="",
        Visible=False, OpenAndRepair=False, NoEncodingDialog=True,
    )


def _shape_range(parent: Any, name: str) -> Any:
    matches: list[Any] = []

    def visit(shapes: Any, depth: int = 0) -> None:
        if depth > 32:
            raise EvaluationFailure("UNSUPPORTED_STORY", "shape group nesting exceeds 32")
        for shape in _items(shapes):
            if shape.Name == name:
                matches.append(shape)
            if int(shape.Type) == 6:  # msoGroup
                visit(shape.GroupItems, depth + 1)

    visit(parent.ShapeRange)
    if len(matches) != 1:
        raise EvaluationFailure("UNSUPPORTED_STORY", f"textbox name is not unique: {name!r}")
    frame = matches[0].TextFrame
    if frame.Next is not None or frame.Previous is not None:
        raise EvaluationFailure("UNSUPPORTED_STORY", f"linked textbox is unsupported: {name!r}")
    return frame.TextRange


def _locate(document: Any, stories: list[dict]) -> tuple[dict, dict]:
    descriptors: dict[str, dict] = {}
    for descriptor in stories:
        story_id = descriptor["id"]
        if story_id in descriptors and descriptors[story_id] != descriptor:
            raise EvaluationFailure("UNSUPPORTED_STORY", f"conflicting story locator: {story_id}")
        descriptors[story_id] = descriptor
    ranges: dict[str, Any] = {}
    aliases: dict[str, str] = {}
    identities: dict[tuple, str] = {}
    visiting: set[str] = set()

    def locate(story_id: str) -> Any:
        if story_id in ranges:
            return ranges[story_id]
        if story_id in visiting or story_id not in descriptors:
            raise EvaluationFailure("UNSUPPORTED_STORY", f"cyclic/missing story parent: {story_id}")
        visiting.add(story_id)
        descriptor = descriptors[story_id]
        kind = descriptor["kind"]
        if kind == "main":
            value, identity = document.Content, ("main",)
        elif kind in {"footnotes", "endnotes"}:
            value = document.StoryRanges.Item(2 if kind == "footnotes" else 3)
            identity = (kind,)
        elif kind in {"header", "footer"}:
            section, variant = descriptor["section"], descriptor["type"]
            if type(section) is not int or section < 1 or type(variant) is not int or variant not in (1, 2, 3):
                raise EvaluationFailure("UNSUPPORTED_STORY", f"invalid header/footer locator: {story_id}")
            collection = "Headers" if kind == "header" else "Footers"
            item = getattr(document.Sections.Item(section), collection).Item(variant)
            value = item.Range
            while section > 1 and bool(item.LinkToPrevious):
                section -= 1
                item = getattr(document.Sections.Item(section), collection).Item(variant)
            identity = (kind, section, variant)
        elif kind == "textbox":
            parent_id = descriptor["parent"]
            parent = locate(parent_id)
            value = _shape_range(parent, descriptor["name"])
            identity = (kind, aliases[parent_id], descriptor["name"])
        else:
            raise EvaluationFailure("UNSUPPORTED_STORY", f"unsupported story kind: {kind}")
        aliases[story_id] = identities.setdefault(identity, story_id)
        ranges[story_id] = value
        visiting.remove(story_id)
        return value

    for story_id in descriptors:
        locate(story_id)
    return {key: value for key, value in ranges.items() if aliases[key] == key}, aliases


def _expected_map(expected: list[dict], aliases: dict[str, str]) -> dict:
    groups: dict[str, dict] = {}
    for descriptor in expected:
        story = descriptor["story"]
        ordinal = descriptor["ordinal"]
        instruction = _normalize(descriptor["instruction"])
        kind, locked = descriptor["kind"], descriptor["locked"]
        if (story not in aliases or type(ordinal) is not int or ordinal < 0
                or type(locked) is not bool or not instruction
                or instruction.split()[0].upper() != kind):
            raise EvaluationFailure("FIELD_MAP_MISMATCH", f"invalid expected descriptor: {descriptor!r}")
        group = groups.setdefault(story, {})
        if ordinal in group:
            raise EvaluationFailure("FIELD_MAP_MISMATCH", f"duplicate expected ordinal: {story}/{ordinal}")
        group[ordinal] = (instruction, kind, locked)
    canonical: dict[str, dict] = {}
    for story, group in groups.items():
        if sorted(group) != list(range(len(group))):
            raise EvaluationFailure("FIELD_MAP_MISMATCH", f"non-contiguous expected ordinals: {story}")
        key = aliases[story]
        if key in canonical and canonical[key] != group:
            raise EvaluationFailure("FIELD_MAP_MISMATCH", f"inconsistent alias inventory: {story}")
        canonical[key] = group
    return {
        (story, ordinal, instruction): (kind, locked)
        for story, group in canonical.items()
        for ordinal, (instruction, kind, locked) in group.items()
    }


def _bind(document: Any, expected: list[dict], stories: list[dict]) -> dict:
    ranges, aliases = _locate(document, stories)
    wanted = _expected_map(expected, aliases)
    actual: dict[tuple, Any] = {}
    for story, story_range in ranges.items():
        fields = _items(story_range.Fields)  # Include unrelated fields in ordinals.
        ordered: list[tuple[int, Any, str]] = []
        for field in fields:
            code, result = field.Code, field.Result
            text = code.Text
            if (int(code.Fields.Count) or int(result.Fields.Count)
                    or any(marker in text for marker in ("\x13", "\x14", "\x15"))):
                raise EvaluationFailure("UNSUPPORTED_NESTED_FIELD", f"nested field in {story}")
            ordered.append((int(code.Start), field, _normalize(text)))
        ordered.sort(key=lambda item: item[0])
        if len({start for start, _, _ in ordered}) != len(ordered):
            raise EvaluationFailure("FIELD_MAP_MISMATCH", f"ambiguous field positions in {story}")
        for ordinal, (_, field, instruction) in enumerate(ordered):
            actual[(story, ordinal, instruction)] = field
    if actual.keys() != wanted.keys():
        missing, extra = sorted(wanted.keys() - actual.keys()), sorted(actual.keys() - wanted.keys())
        raise EvaluationFailure("FIELD_MAP_MISMATCH", f"field bijection failed; missing={missing!r}; extra={extra!r}")
    for key, field in actual.items():
        kind, locked = wanted[key]
        if kind in KINDS and (locked or bool(field.Locked)):
            raise EvaluationFailure("LOCKED_FIELD", f"locked field: {key!r}")
    return actual


def _snapshot(fields: dict) -> dict:
    values = {}
    for key, field in fields.items():
        value = field.Result.Text
        if not isinstance(value, str):
            raise EvaluationFailure("INVALID_RESULT", f"non-text COM result: {key!r}")
        values[key] = value
    return values


def _evidence(values: dict) -> list[dict]:
    # Hashes deliberately cannot be mistaken for transplantable field text.
    return [
        {"story": story, "ordinal": ordinal, "instruction": instruction,
         "result_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}
        for (story, ordinal, instruction), value in values.items()
    ]


def _evaluate(application: Any, isolated: Path, expected: list[dict], stories: list[dict], report: dict) -> None:
    previous_options: list[tuple[str, Any]] = []
    document = None
    cleanup_errors: list[str] = []
    try:
        report["phase"] = "security"
        for name, value in (("AutomationSecurity", 3), ("Visible", False),
                            ("DisplayAlerts", 0), ("ScreenUpdating", False)):
            _required_set(application, name, value)
        options = application.Options
        for name in WORD_OPTIONS:
            try:
                previous_options.append((name, getattr(options, name)))
            except Exception as exc:
                raise EvaluationFailure("SECURITY_OPTIONS_FAILED", f"Options.{name} read: {exc}") from exc
            _required_set(options, name, False)
        report["phase"] = "open"
        document = _open(application, isolated, read_only=False)
        if bool(document.ReadOnly):
            raise EvaluationFailure("FAIL_OPEN", "temporary evaluation document opened read-only")
        report["phase"] = "bind"
        fields = _bind(document, expected, stories)
        before = _snapshot(fields)
        unrelated = {key: value for key, value in before.items() if key[2].split()[0].upper() not in KINDS}
        report["phase"] = "evaluate"
        for number in range(1, 6):
            report["passes"] = number
            for kind in KINDS:
                if kind == "PAGEREF" and any(key[2].split()[0].upper() == kind for key in fields):
                    document.Repaginate()
                for key, field in fields.items():
                    if key[2].split()[0].upper() == kind:
                        if not field.Update():
                            raise EvaluationFailure("FIELD_UPDATE_FAILED", f"Field.Update failed: {key!r}")
            fields = _bind(document, expected, stories)
            after = _snapshot(fields)
            if any(after[key] != value for key, value in unrelated.items()):
                raise EvaluationFailure("UNRELATED_FIELD_CHANGED", "unrelated field result changed during evaluation")
            if after == before:
                break
            before = after
        else:
            raise EvaluationFailure("NON_CONVERGENT", "field results did not stabilize within five passes")
        report["phase"] = "save"
        document.Save()
        if not bool(document.Saved):
            raise EvaluationFailure("PERSISTENCE_FAILED", "Word did not confirm saving the evaluation copy")
        saved_fields = _snapshot(_bind(document, expected, stories))
        if saved_fields != after:
            raise EvaluationFailure("PERSISTENCE_FAILED", "field results changed on save")
        document.Close(False)
        document = None
        saved_hash = gate.sha256(isolated)
        report["phase"] = "reopen"
        document = _open(application, isolated, read_only=True)
        if not bool(document.ReadOnly):
            raise EvaluationFailure("PERSISTENCE_FAILED", "verification reopen was not read-only")
        reopened = _snapshot(_bind(document, expected, stories))
        if reopened != saved_fields:
            raise EvaluationFailure("PERSISTENCE_FAILED", "saved/reopened field keys or results are not stable")
        document.Close(False)
        document = None
        if gate.sha256(isolated) != saved_hash:
            raise EvaluationFailure("PERSISTENCE_FAILED", "read-only verification changed the saved package")
        report["persisted"] = {
            "ok": True, "save_reopen_verified": True, "field_count": len(reopened),
            "evaluation_sha256": saved_hash, "fields": _evidence(reopened),
            "scope": "evaluation_copy_only",
        }
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception as exc:
                cleanup_errors.append(f"document.Close: {exc}")
        for name, previous in reversed(previous_options):
            try:
                _required_set(application.Options, name, previous)
            except Exception as exc:
                cleanup_errors.append(f"Options.{name} restore: {exc}")
        report["options_restored"] = not any("Options." in item for item in cleanup_errors)
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            raise EvaluationFailure("CLEANUP_FAILED", "; ".join(cleanup_errors))


def evaluate_copy(
    source: Path, output: Path, expected: list[dict], stories: list[dict], *,
    allow_office_com: bool = False, dispatch_ex=None, com_runtime=None,
    process_ids=None,
    pid_observation_timeout_seconds: float = gate.PID_OBSERVATION_TIMEOUT_SECONDS,
    process_exit_timeout_seconds: float = gate.PROCESS_EXIT_TIMEOUT_SECONDS,
) -> dict:
    """Publish a new evaluation copy only after save/reopen and owned cleanup.

    All expected fields, including unrelated ones, must have independently
    enumerated story/ordinal/instruction keys. Relevant locks and nested fields
    fail closed. No COM launch occurs without explicit per-operation consent.
    """
    report = {
        "ok": False, "status": "UNVERIFIED", "passes": 0, "engine": "word",
        "phase": "preflight", "ownership": {}, "evaluation_output": None,
        "persisted": {"ok": False},
    }
    workspace = None
    before = None
    try:
        source, output = Path(source).resolve(), Path(output).absolute()
        report["source"] = str(source)
        if source == output.resolve() or os.path.lexists(output):
            raise EvaluationFailure("OUTPUT_EXISTS", "source overwrite or existing output is forbidden")
        if source.suffix.lower() != ".docx" or output.suffix.lower() != ".docx":
            raise EvaluationFailure("INVALID_INPUT", "evaluation requires .docx input and output")
        before = gate.sha256(source)
        report["source_sha256_before"] = before
        if not allow_office_com:
            raise EvaluationFailure("UNVERIFIED", "native refresh requires allow_office_com for this operation")
        if any(item.get("kind") in KINDS and item.get("locked") for item in expected):
            raise EvaluationFailure("LOCKED_FIELD", "expected inventory contains locked reference fields")
        if not any(item.get("kind") in KINDS for item in expected):
            raise EvaluationFailure("NOT_APPLICABLE", "no relevant internal reference fields; no Office launch")
        workspace = Path(tempfile.mkdtemp(prefix="codex-reference-word_"))
        isolated = workspace / "evaluation.docx"
        _prepare_copy(source, isolated)
        if gate.sha256(source) != before:
            raise EvaluationFailure("SOURCE_CHANGED", "source changed while creating the temporary copy")
        report["phase"] = "ownership"
        with gate.owned_application(
            gate.FORMAT_SPECS["docx"],
            dispatch_ex=native_dispatch if dispatch_ex is None else dispatch_ex,
            com_runtime=com_runtime, process_ids=process_ids,
            pid_observation_timeout_seconds=pid_observation_timeout_seconds,
            process_exit_timeout_seconds=process_exit_timeout_seconds,
            ownership_metadata=report["ownership"],
        ) as (application, owner):
            # The shared gate accepts a PID set. Evaluation requires exactly
            # one newly observed PID; no image-wide termination is permitted.
            if len(owner.metadata.get("owned_pids", [])) != 1:
                owner.exclusive_at_start = False
                raise gate.OwnershipFailure("exactly one owned Word PID is required")
            _evaluate(application, isolated, expected, stories, report)
        if report["ownership"].get("cleanup", {}).get("status") != "CLEAN":
            raise EvaluationFailure("CLEANUP_FAILED", "owned Word process cleanup was not proven")
        if gate.sha256(source) != before:
            raise EvaluationFailure("SOURCE_CHANGED", "source changed during evaluation")
        if gate.sha256(isolated) != report["persisted"]["evaluation_sha256"]:
            raise EvaluationFailure("PERSISTENCE_FAILED", "saved evaluation changed during cleanup")
        report["phase"] = "publish"
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, staging_name = tempfile.mkstemp(prefix=".reference-word-", suffix=".docx", dir=output.parent)
        staging = Path(staging_name)
        try:
            with os.fdopen(descriptor, "wb") as outgoing, isolated.open("rb") as incoming:
                shutil.copyfileobj(incoming, outgoing)
            if gate.sha256(staging) != report["persisted"]["evaluation_sha256"]:
                raise EvaluationFailure("PERSISTENCE_FAILED", "evaluation staging hash mismatch")
            os.link(staging, output)  # Atomic new-path publication, never replacement.
        finally:
            staging.unlink()
        report["evaluation_output"] = str(output.resolve())
        if gate.sha256(output) != report["persisted"]["evaluation_sha256"]:
            raise EvaluationFailure("PERSISTENCE_FAILED", "published evaluation hash mismatch")
        report.update(ok=True, status="PASS", phase="complete")
    except EvaluationFailure as exc:
        report.update(status=exc.status, error=str(exc))
    except gate.OwnershipFailure as exc:
        report.update(status="UNSAFE_PROCESS", error=str(exc))
    except (gate.ActivationFailure, ModuleNotFoundError) as exc:
        report.update(status="APP_UNAVAILABLE", error=str(exc))
    except Exception as exc:
        report.update(error=f"{type(exc).__name__}: {exc}")
    finally:
        if before is not None:
            try:
                report["source_sha256_after"] = gate.sha256(source)
                if report["source_sha256_after"] != before:
                    raise EvaluationFailure("SOURCE_CHANGED", "source hash changed during evaluation")
            except Exception as exc:
                report.update(ok=False, status="SOURCE_CHANGED", error=str(exc))
        ownership = report["ownership"]
        unsafe_cleanup = ownership.get("activation_succeeded") and (
            ownership.get("cleanup", {}).get("status") != "CLEAN"
            or ownership.get("com_uninitialize", {}).get("status") == "FAILED"
        )
        if unsafe_cleanup:
            report.update(ok=False, status="CLEANUP_FAILED", phase="cleanup")
            report.setdefault("error", "owned Word cleanup is unverified")
        if workspace is not None:
            if unsafe_cleanup:
                report["retained_workspace"] = str(workspace)
            else:
                try:
                    shutil.rmtree(workspace)
                except OSError as exc:
                    report.update(ok=False, status="CLEANUP_FAILED", phase="cleanup", error=str(exc))
                    report["retained_workspace"] = str(workspace)
    return report


def main(argv: list[str] | None = None) -> int:
    """Read-only native acceptance with the same late-bound dispatch factory."""
    parser = argparse.ArgumentParser(description="Read-only native Word reference-output check")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("output", type=Path)
    check.add_argument("--allow-office-com", action="store_true")
    check.add_argument("--json", action="store_true", help="accepted for compatibility; JSON is always emitted")
    args = parser.parse_args(argv)
    registration_failure = None

    def dispatch_registered(progid: str) -> Any:
        nonlocal registration_failure
        try:
            return native_dispatch(progid)
        except EvaluationFailure as exc:
            registration_failure = exc
            raise

    result = gate.check_file(
        args.output, "docx", allow_office_com=args.allow_office_com,
        dispatch_ex=dispatch_registered, require_render=False,
    )
    # The unchanged gate wraps factory exceptions as activation failures.
    # Retain this module's precise pre-activation refusal classification.
    if registration_failure is not None:
        result.update(ok=False, status=registration_failure.status,
                      phase="registered_server", error=str(registration_failure))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") and result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
