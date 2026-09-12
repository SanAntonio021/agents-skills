"""Shared UTF-8 I/O and read-only, project-scoped runtime configuration."""
import json
import os
from pathlib import Path
import sys
import tempfile

ENVIRONMENT = {
    "lo_runner": "LAB_REPORT_LO_RUNNER", "soffice": "LAB_REPORT_SOFFICE",
    "pdftoppm": "LAB_REPORT_PDFTOPPM", "work_root": "LAB_REPORT_WORK_ROOT",
    "diagnostics_root": "LAB_REPORT_DIAGNOSTICS_ROOT",
}


class ConfigError(ValueError):
    pass


def emit_json(payload, stream=None):
    """Write UTF-8 even when a Windows pipe is configured as GBK."""
    stream = sys.stdout if stream is None else stream
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if hasattr(stream, "buffer"):
        stream.flush()
        stream.buffer.write(text.encode("utf-8"))
        stream.buffer.flush()
    else:
        stream.write(text)
        stream.flush()


def atomic_write_json(path, payload):
    """Publish a complete JSON file, leaving an existing file intact on failure."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        except OSError:
            # A cleanup failure must not mask the publication error.
            pass


def user_environment(name):
    """Report registry persistence separately from the inherited process value."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            try:
                value, _ = winreg.QueryValueEx(key, name)
                return {"user": value, "user_status": "present"}
            except FileNotFoundError:
                return {"user": None, "user_status": "absent"}
    except FileNotFoundError:
        return {"user": None, "user_status": "absent"}
    except (ImportError, OSError) as exc:
        return {"user": None, "user_status": "unavailable", "user_error": str(exc)}


def load_config(config_path=None, discovery_dir=None):
    """Resolve env > one project file; callers discover absent executables.

    No parent search, environment writes, or directory creation is performed.
    File paths must exist; configured output roots may be created by execution.
    """
    path = Path(config_path).expanduser().resolve() if config_path else (
        Path(discovery_dir or Path.cwd()).resolve() / "lab-report.local.json")
    data = {}
    if config_path or path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ConfigError("Cannot read project config {}: {}".format(path, exc)) from exc
        if not isinstance(data, dict) or any(k not in ENVIRONMENT for k in data):
            raise ConfigError("Project config must be an object containing only: " + ", ".join(ENVIRONMENT))
        for key, value in data.items():
            if not isinstance(value, str) or not value.strip():
                raise ConfigError("Invalid project path for " + key)
    else:
        path = None
    result = {"path": str(path) if path else None, "values": {}, "sources": {}, "persistence": {}}
    for key, variable in ENVIRONMENT.items():
        project = None
        if key in data:
            project_path = Path(data[key]).expanduser()
            project = str((path.parent / project_path).resolve() if not project_path.is_absolute() else project_path.resolve())
        session = os.environ.get(variable)
        result["persistence"][key] = {"session": session, "project": project, **user_environment(variable)}
        value = session or project
        if value:
            candidate = Path(value).expanduser()
            if key in ("work_root", "diagnostics_root"):
                if candidate.exists() and not candidate.is_dir():
                    raise ConfigError("{} is not a directory: {}".format(variable if session else key, candidate))
            elif not candidate.is_file():
                raise ConfigError("{} is not a file: {}".format(variable if session else key, candidate))
            result["values"][key] = str(candidate)
            result["sources"][key] = variable if session else "project config"
        result["persistence"][key]["effective"] = result["values"].get(key)
        result["persistence"][key]["source"] = result["sources"].get(key, "not configured")
    return result
