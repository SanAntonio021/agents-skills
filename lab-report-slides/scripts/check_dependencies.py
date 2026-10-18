#!/usr/bin/env python3
"""Read-only dependency preflight; does not run Office or inspect sessions."""

import importlib
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime_config import ConfigError, emit_json, load_config


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


def check_dependencies(config_path=None):
    try:
        config = load_config(config_path, Path.cwd(), include_render_tools=False)
    except ConfigError as exc:
        return {"ok": False, "required": {}, "missing": ["configuration"],
                "error": str(exc), "interpreter": sys.executable}
    version = sys.version_info[:3]
    required = {
        "python": {"present": version >= (3, 10, 0),
                   "detail": ".".join(map(str, version)), "minimum": "3.10"},
        "windows": {"present": platform.system() == "Windows",
                    "detail": platform.system()},
    }
    for name in ("pptx", "PIL"):
        required[name] = module_status(name)
    required["timezone"] = timezone_status()
    missing = [name for name, status in required.items() if not status["present"]]
    optional = {"powerpoint_com": module_status("win32com.client")}
    try:
        render_config = load_config(config_path, Path.cwd(), include_render_tools=True)
    except ConfigError as exc:
        render_config = None
        for name in ("libreoffice_runner", "pdftoppm", "libreoffice"):
            optional[name] = {"present": False, "detail": str(exc), "source": "render configuration"}
    if render_config is not None:
        runner = render_config["values"].get("lo_runner")
        if runner:
            optional["libreoffice_runner"] = file_status(runner, render_config["sources"]["lo_runner"])
        else:
            path = Path(__file__).resolve().parents[2] / "libreoffice-runner" / "scripts" / "libreoffice_run.py"
            optional["libreoffice_runner"] = file_status(path, "adjacent skill")
        optional["pdftoppm"] = (file_status(render_config["values"]["pdftoppm"], render_config["sources"]["pdftoppm"])
                                  if "pdftoppm" in render_config["values"] else executable_status("LAB_REPORT_PDFTOPPM", ("pdftoppm",)))
        defaults = []
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(variable)
            if root:
                defaults.append(Path(root) / "LibreOffice" / "program" / "soffice.com")
                defaults.append(Path(root) / "LibreOffice" / "program" / "soffice.exe")
        optional["libreoffice"] = (file_status(render_config["values"]["soffice"], render_config["sources"]["soffice"])
                                    if "soffice" in render_config["values"] else executable_status(
                                        "LAB_REPORT_SOFFICE", ("soffice.com", "soffice.exe", "soffice"), defaults))
        for field, name in (("lo_runner", "libreoffice_runner"), ("soffice", "libreoffice"), ("pdftoppm", "pdftoppm")):
            status = optional[name]
            render_config["persistence"][field]["effective"] = status.get("path")
            render_config["persistence"][field]["source"] = status.get("source", "not found")
        config["optional_rendering"] = render_config
    return {
        "ok": not missing,
        "interpreter": sys.executable,
        "configuration": config,
        "required": required,
        "optional": optional,
        "missing": missing,
        "notes": [
            "Dependency preflight only; not end-to-end acceptance. No Office process was started and no sessions were read.",
            "LibreOffice/Poppler are not needed for daily reports; group reports use them for the existing compatibility render path.",
            "SVG assets optionally require Node.js and sharp; not checked here.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Explicit lab-report.local.json path")
    args = parser.parse_args(argv)
    result = check_dependencies(args.config)
    emit_json(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
