#!/usr/bin/env python3
"""Read-only dependency preflight; does not run Office or inspect sessions."""

import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys


def module_status(name):
    try:
        importlib.import_module(name)
        return {"present": True, "detail": "import succeeded"}
    except Exception as exc:
        return {"present": False, "detail": str(exc)}


def timezone_status():
    try:
        zoneinfo = importlib.import_module("zoneinfo")
        zoneinfo.ZoneInfo("Asia/Shanghai")
        return {"present": True, "detail": "Asia/Shanghai available"}
    except Exception as exc:
        return {"present": False, "detail": str(exc),
                "hint": "Install tzdata if the system has no timezone database."}


def file_status(path, source):
    candidate = Path(path).expanduser()
    present = candidate.is_file()
    return {"present": present, "path": str(candidate), "source": source}


def executable_status(override, commands, defaults=()):
    # An explicit override is authoritative: report a bad path, do not hide it.
    if os.environ.get(override):
        return file_status(os.environ[override], override)
    for command in commands:
        found = shutil.which(command)
        if found and Path(found).is_file():
            return file_status(found, "PATH")
    for candidate in defaults:
        if Path(candidate).is_file():
            return file_status(candidate, "default installation")
    return {"present": False, "detail": "Executable not found",
            "hint": "Set {} to its full file path.".format(override)}


def check_dependencies():
    version = sys.version_info[:3]
    required = {
        "python": {"present": version >= (3, 10, 0),
                   "detail": ".".join(map(str, version)), "minimum": "3.10"},
        "windows": {"present": platform.system() == "Windows",
                    "detail": platform.system()},
    }
    for name in ("pptx", "PIL", "win32api", "PyPDF2"):
        required[name] = module_status(name)
    required["timezone"] = timezone_status()
    runner = os.environ.get("LAB_REPORT_LO_RUNNER")
    if runner:
        required["libreoffice_runner"] = file_status(runner, "LAB_REPORT_LO_RUNNER")
    else:
        path = Path(__file__).resolve().parents[2] / "libreoffice-runner" / "scripts" / "libreoffice_run.py"
        required["libreoffice_runner"] = file_status(path, "adjacent skill")
    required["pdftoppm"] = executable_status("LAB_REPORT_PDFTOPPM", ("pdftoppm",))
    defaults = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(variable)
        if root:
            defaults.append(Path(root) / "LibreOffice" / "program" / "soffice.com")
            defaults.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
    required["libreoffice"] = executable_status(
        "LAB_REPORT_SOFFICE", ("soffice.com", "soffice.exe", "soffice"), defaults)
    missing = [name for name, status in required.items() if not status["present"]]
    return {
        "ok": not missing,
        "required": required,
        "missing": missing,
        "notes": [
            "Dependency preflight only; not end-to-end acceptance. No Office process was started and no sessions were read.",
            "SVG assets optionally require Node.js and sharp; not checked here.",
        ],
    }


def main():
    result = check_dependencies()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
