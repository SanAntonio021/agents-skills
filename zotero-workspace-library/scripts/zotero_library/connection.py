#!/usr/bin/env python3
"""Read-only Zotero Desktop readiness check; Python 3.10+, standard library only."""

from __future__ import annotations

import argparse
import configparser
import ipaddress
import json
import os
import platform
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "http://127.0.0.1:23119"
API_PREF = "extensions.zotero.httpServer.localAPI.enabled"
PORT_PREF = "extensions.zotero.httpServer.port"
VERSION = re.compile(r"[0-9][0-9A-Za-z.+_-]{0,63}\Z")


class CheckError(Exception):
    """Carries only a fixed error code, never raw input or server messages."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def profile_roots() -> list[Path]:
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        return [Path(appdata) / "Zotero/Zotero", Path(appdata) / "Zotero"] if appdata else []
    home = Path.home()
    if platform.system() == "Darwin":
        return [home / "Library/Application Support/Zotero"]
    return [home / ".zotero/zotero", home / ".var/app/org.zotero.Zotero/data/zotero"]


def resolve_profile(explicit: str | None) -> tuple[Path | None, Path | None]:
    if explicit is None and "ZOTERO_PROFILE" in os.environ:
        explicit = os.environ["ZOTERO_PROFILE"]
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if not path.is_dir() or not (path / "prefs.js").is_file():
            raise CheckError("explicit_profile_unreadable")
        return path, None
    ini = next((root / "profiles.ini" for root in profile_roots()
                if (root / "profiles.ini").is_file()), None)
    if ini is None:
        return None, None
    parser = configparser.RawConfigParser()
    try:
        with ini.open(encoding="utf-8-sig") as stream:
            parser.read_file(stream)
        candidates, defaults, installs = set(), set(), set()
        for section in parser.sections():
            if section.lower().startswith("profile") and parser.has_option(section, "Path"):
                path = Path(parser.get(section, "Path"))
                if parser.get(section, "IsRelative", fallback="1") == "1":
                    path = ini.parent / path
                path = path.resolve()
                candidates.add(path)
                if parser.get(section, "Default", fallback="0") == "1":
                    defaults.add(path)
            elif section.lower().startswith("install") and parser.has_option(section, "Default"):
                installs.add((ini.parent / parser.get(section, "Default")).resolve())
    except (OSError, UnicodeError, configparser.Error, ValueError):
        raise CheckError("profiles_ini_unreadable") from None
    preferred = installs or defaults or candidates
    if len(preferred) != 1 or (installs and not installs.issubset(candidates)):
        raise CheckError("profile_ambiguous" if candidates else "profile_not_found")
    path = next(iter(preferred))
    if not (path / "prefs.js").is_file():
        raise CheckError("profile_prefs_unreadable")
    return path, ini


def read_preferences(profile: Path | None) -> dict:
    if profile is None:
        return {}
    values = {}
    pattern = re.compile(r'^\s*user_pref\("([^"\\]+)",\s*(.*?)\);\s*$')
    try:
        with (profile / "prefs.js").open(encoding="utf-8-sig") as stream:
            for line in stream:
                match = pattern.match(line)
                if match and match[1] in {API_PREF, PORT_PREF}:
                    try:
                        values[match[1]] = json.loads(match[2])
                    except ValueError:
                        values[match[1]] = None
    except (OSError, UnicodeError):
        raise CheckError("profile_prefs_unreadable") from None
    return values


def validate_base_url(raw: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(raw)
        host = parsed.hostname
        loopback = host == "localhost" or ipaddress.ip_address(host or "").is_loopback
        port = parsed.port
        if (parsed.scheme != "http" or not loopback or parsed.username is not None
                or parsed.password is not None or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment or "?" in raw or "#" in raw
                or any(char.isspace() or ord(char) < 32 for char in raw)
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError
        authority = f"[{host}]" if ":" in host else host
        return f"http://{authority}" + (f":{port}" if port is not None else "")
    except (ValueError, TypeError):
        raise CheckError("invalid_loopback_base_url") from None


def select_base_url(explicit: str | None, preferences: dict) -> tuple[str, str]:
    if explicit is not None:
        raw, source = explicit, "argument"
    elif "ZOTERO_LOCAL_BASE_URL" in os.environ:
        raw, source = os.environ["ZOTERO_LOCAL_BASE_URL"], "environment"
    elif PORT_PREF in preferences:
        port = preferences[PORT_PREF]
        if type(port) is not int or not 1 <= port <= 65535:
            raise CheckError("invalid_profile_port")
        raw, source = f"http://127.0.0.1:{port}", "profile_port"
    else:
        raw, source = DEFAULT_BASE_URL, "default_candidate"
    return validate_base_url(raw), source


def process_status() -> dict:
    result = {"state": "unknown", "pids": [], "executable_paths": []}
    if platform.system() != "Windows":
        return result
    command = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        "@(Get-CimInstance Win32_Process -Filter \"Name='zotero.exe'\" -ErrorAction Stop | "
        "Select-Object ProcessId,ExecutablePath) | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, encoding="utf-8-sig", timeout=5, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        rows = json.loads(completed.stdout) if completed.stdout.strip() else []
        if isinstance(rows, dict):
            rows = [rows]
        result = {"state": "running" if rows else "not_running",
                  "pids": [row["ProcessId"] for row in rows],
                  "executable_paths": sorted({row["ExecutablePath"] for row in rows
                                              if row.get("ExecutablePath")})}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        pass
    return result


def status_payload(profile=None, base_url=None, timeout=3):
    # Diagnostics use the same connection and transport as every business command.
    from .client import Client
    from .errors import LibraryError
    client = Client.__new__(Client)
    try:
        client.__init__(profile, base_url, timeout)
        return client.diagnostics()
    except (CheckError, LibraryError) as error:
        result = getattr(client, 'status', empty_status()).copy()
        code = str(error)
        result.update(error=code, read_only_ready=False, process=process_status())
        if 'profile' in code:
            result['profile_error'] = code
        elif not result['api_verified']:
            result['api_error'] = code
        else:
            result['schema_error'] = code
        return result


def empty_status():
    return {
        'profile': None, 'prefs_file': None, 'profiles_ini': None, 'profile_error': None,
        'local_api_enabled_pref': None, 'base_url': None, 'base_url_source': None,
        'api_running': False, 'api_status': None, 'api_error': None,
        'api_version': None, 'zotero_version': None, 'api_verified': False,
        'schema_running': False, 'schema_status': None, 'schema_error': None,
        'schema_version': None, 'schema_verified': False,
        'connector_running': None, 'connector_status': None, 'connector_error': None,
        'connector_verified': None, 'read_only_ready': False, 'entry_verified': False,
        'debug_bridge_status': None, 'debug_bridge_available': None,
        'debug_bridge_error': None, 'bridge_credential_present': None,
        'native_library_id': None, 'import_from_file_available': None,
        'automatic_fetch_protection_ready': None, 'write_capabilities': None,
        'debug_bridge_applicability': 'not_applicable',
        'local_api_write_supported': False, 'local_api_authorization_present': False,
        'process': {'state': 'unknown', 'pids': [], 'executable_paths': []}, 'error': None,
    }


def main(argv=None):
    from .cli import main as cli_main
    return cli_main(argv)


if __name__ == '__main__':
    sys.exit(main())
