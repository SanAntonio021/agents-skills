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
TOKEN_PREF = "extensions.zotero.debug-bridge.token"
BRIDGE_QUERY = (
    'return {version: Zotero.version, libraryID: Zotero.Libraries.userLibraryID, '
    'importFromFileAvailable: typeof Zotero.Attachments.importFromFile === "function"};'
)
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
                if match and match[1] in {API_PREF, PORT_PREF, TOKEN_PREF}:
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


def request(opener, base: str, path: str, timeout: float, token: str | None = None) -> dict:
    headers = {"Zotero-API-Version": "3"}
    data = None
    if path.startswith("/connector/"):
        headers["X-Zotero-Connector-API-Version"] = "3"
    if token is not None:
        headers.update({"Content-Type": "text/plain", "Authorization": "Bearer " + token})
        data = BRIDGE_QUERY.encode("utf-8")
    req = urllib.request.Request(base + path, data=data, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as response:
            body = response.read(4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024:
                return {"status": response.status, "error": "response_too_large"}
            return {"status": response.status, "headers": response.headers,
                    "body": body.decode("utf-8", errors="replace"), "error": None}
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        return {"status": code, "error": "redirect_blocked" if 300 <= code < 400 else "http_error"}
    except (OSError, urllib.error.URLError, ValueError):
        return {"status": None, "error": "connection_failed"}


def successful(response: dict) -> bool:
    return (response["status"] is not None and 200 <= response["status"] < 300
            and response.get("error") is None)


def version(value):
    return value if isinstance(value, str) and VERSION.fullmatch(value) else None


def status_payload(profile: str | None = None, base_url: str | None = None,
                   timeout: float = 3) -> dict:
    result = {
        "profile": None, "prefs_file": None, "profiles_ini": None, "profile_error": None,
        "local_api_enabled_pref": None, "base_url": None, "base_url_source": None,
        "api_running": False, "api_status": None, "api_error": None,
        "api_version": None, "zotero_version": None, "api_verified": False,
        "schema_running": False, "schema_status": None, "schema_error": None,
        "schema_version": None, "schema_verified": False,
        "connector_running": False, "connector_status": None, "connector_error": None,
        "connector_verified": False, "read_only_ready": False, "entry_verified": False,
        "debug_bridge_status": None, "debug_bridge_available": False,
        "debug_bridge_error": None, "bridge_credential_present": False,
        "native_library_id": None, "import_from_file_available": None,
        "process": {"state": "unknown", "pids": [], "executable_paths": []},
        "error": None,
    }
    try:
        selected, ini = resolve_profile(profile)
        result.update(profile=str(selected) if selected else None,
                      prefs_file=str(selected / "prefs.js") if selected else None,
                      profiles_ini=str(ini) if ini else None,
                      profile_error=None if selected else "profile_not_found")
        preferences = read_preferences(selected)
        pref = preferences.get(API_PREF)
        result["local_api_enabled_pref"] = pref if type(pref) is bool else None
        base, source = select_base_url(base_url, preferences)
    except CheckError as error:
        result["error"] = str(error)
        if str(error).startswith(("profile", "explicit_profile")):
            result["profile_error"] = str(error)
        return result
    result.update(base_url=base, base_url_source=source, process=process_status())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    root = request(opener, base, "/api/", timeout)
    headers = root.get("headers", {})
    api_version = version(headers.get("Zotero-API-Version"))
    zotero_version = version(headers.get("X-Zotero-Version"))
    root_ok = successful(root)
    identity = root_ok and bool(api_version or zotero_version)
    result.update(api_running=root_ok, api_status=root["status"],
                  api_error=root["error"] or (None if identity else "zotero_identity_missing"),
                  api_version=api_version, zotero_version=zotero_version, api_verified=identity)
    schema = request(opener, base, "/api/schema", timeout)
    schema_ok = False
    schema_version = None
    if successful(schema):
        try:
            value = json.loads(schema["body"])
            schema_version = value.get("version") if isinstance(value, dict) else None
            schema_ok = (isinstance(value, dict) and isinstance(value.get("itemTypes"), (list, dict))
                         and (type(schema_version) is int or version(schema_version) is not None))
        except ValueError:
            pass
    result.update(schema_running=successful(schema), schema_status=schema["status"],
                  schema_verified=schema_ok, schema_version=schema_version if schema_ok else None,
                  schema_error=schema["error"] or (None if schema_ok else "invalid_zotero_schema"))
    connector = request(opener, base, "/connector/ping", timeout)
    connector_ok = (successful(connector) and "zotero is running" in connector["body"].lower())
    result.update(connector_running=successful(connector), connector_status=connector["status"],
                  connector_verified=connector_ok,
                  connector_error=connector["error"] or (None if connector_ok else "connector_identity_missing"),
                  read_only_ready=bool(identity and schema_ok and pref is not False),
                  entry_verified=bool(identity and schema_ok and connector_ok))

    # Credentials are used only after Zotero identity/schema validation, never in output.
    token = preferences.get(TOKEN_PREF)
    credential = isinstance(token, str) and bool(token.strip())
    result["bridge_credential_present"] = credential
    if not result["read_only_ready"]:
        result["debug_bridge_error"] = "api_not_verified_or_disabled"
    elif not credential:
        result["debug_bridge_error"] = "bridge_credential_missing"
    elif not token.isascii() or any(ord(char) < 33 or ord(char) == 127 for char in token):
        result["debug_bridge_error"] = "bridge_credential_invalid"
    else:
        bridge = request(opener, base, "/debug-bridge/execute", timeout, token)
        result["debug_bridge_status"] = bridge["status"]
        code = {401: "bridge_authentication_failed", 403: "bridge_access_denied",
                404: "bridge_not_available"}.get(bridge["status"])
        result["debug_bridge_error"] = code or bridge["error"] or "invalid_bridge_response"
        if successful(bridge):
            try:
                native = json.loads(bridge["body"])
                if isinstance(native, dict) and "result" in native:
                    native = native["result"]
                if isinstance(native, str):
                    native = json.loads(native)
                native_version = version(native.get("version"))
                library = native.get("libraryID")
                available = native.get("importFromFileAvailable")
                if (native_version and type(library) is int and library > 0
                        and type(available) is bool):
                    if zotero_version and native_version != zotero_version:
                        result["debug_bridge_error"] = "bridge_version_mismatch"
                    else:
                        result.update(debug_bridge_available=True, debug_bridge_error=None,
                                      zotero_version=native_version, native_library_id=library,
                                      import_from_file_available=available)
            except (ValueError, AttributeError, TypeError):
                pass
    if not result["read_only_ready"]:
        result["error"] = "local_api_disabled" if pref is False else "local_api_unavailable_or_unverified"
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Check local endpoints without changing Zotero")
    status.add_argument("--json", action="store_true", help="Print machine-readable status")
    status.add_argument("--profile", help="Explicit Zotero profile directory containing prefs.js")
    status.add_argument("--base-url", help="Override the single loopback origin to verify")
    status.add_argument("--timeout", type=float, default=3, help="Per-request seconds (0 < value <= 10)")
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 10:
        parser.error("timeout must be greater than zero and no more than 10 seconds")
    try:
        result = status_payload(args.profile, args.base_url, args.timeout)
    except Exception:
        # Do not let raw exceptions expose credentials, prefs, or server error bodies.
        result = {"error": "status_check_failed", "read_only_ready": False}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        for key in ("base_url", "base_url_source", "read_only_ready", "connector_verified",
                    "debug_bridge_available", "profile_error", "error"):
            print(f"{key}: {result.get(key)}")
    return 0 if result["read_only_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
