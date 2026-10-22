"""Task-scoped client for the web-access CDP proxy."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BrowserError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ProxyInfo:
    proxy_url: str
    browser: str
    protocol_version: int


def discover_web_access_checker() -> Path:
    candidates: list[Path] = []
    override = os.environ.get("PAPER_DOWNLOAD_WEB_ACCESS_CHECKER")
    if override:
        candidates.append(Path(override))
    package_root = Path(__file__).resolve().parents[3]
    candidates.append(package_root / "web-access" / "scripts" / "check-deps.mjs")
    home = Path.home()
    for variable, default in (
        ("CODEX_HOME", home / ".codex"),
        ("CLAUDE_CONFIG_DIR", home / ".claude"),
    ):
        root = Path(os.environ.get(variable) or default)
        candidates.append(root / "skills" / "web-access" / "scripts" / "check-deps.mjs")
    candidates.append(
        home / ".agents" / "skills" / "web-access" / "scripts" / "check-deps.mjs"
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BrowserError(
        "web_access_missing",
        "web-access is required but check-deps.mjs was not found; install "
        "paper-download and web-access from the same public skill repository",
    )


def check_web_access(browser: str | None = None) -> ProxyInfo:
    node = os.environ.get("PAPER_DOWNLOAD_NODE") or shutil.which("node")
    if not node:
        raise BrowserError("node_missing", "Node.js is required for browser access")
    try:
        version = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BrowserError(
            "node_unavailable",
            "Node.js could not be started",
        ) from error
    match = re.fullmatch(r"v(\d+)\.\d+\.\d+\s*", version.stdout or "")
    if version.returncode != 0 or not match or int(match.group(1)) < 22:
        raise BrowserError(
            "node_version",
            "Node.js 22 or newer is required for browser access",
        )
    checker = discover_web_access_checker()
    command = [node, str(checker), "--json"]
    selected = (browser or os.environ.get("PAPER_DOWNLOAD_BROWSER") or "auto").lower()
    if selected not in {"auto", "edge", "chrome"}:
        raise BrowserError("invalid_browser", "browser must be auto, edge, or chrome")
    if selected != "auto":
        command.extend(["--browser", selected])
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            creationflags=flags,
        )
    except subprocess.TimeoutExpired as error:
        raise BrowserError(
            "browser_preflight_timeout",
            "web-access preflight timed out",
        ) from error
    except OSError as error:
        raise BrowserError(
            "browser_preflight_failed",
            "web-access preflight could not start",
        ) from error
    parsed: dict[str, Any] | None = None
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed = value
            break
    if parsed is None:
        raise BrowserError(
            "browser_preflight_invalid",
            "web-access returned no usable JSON status",
        )
    if (
        result.returncode != 0
        or parsed.get("ready") is not True
        or parsed.get("protocolVersion") != 2
    ):
        raise BrowserError(
            str(parsed.get("status") or "browser_preflight_failed"),
            "web-access browser service is not ready",
        )
    ready = [
        item
        for item in parsed.get("results", [])
        if item.get("ready") is True
        and (item.get("proxy") or {}).get("protocolVersion") == 2
    ]
    if not ready:
        raise BrowserError(
            "browser_preflight_invalid",
            "web-access returned no ready browser",
        )
    selected_result = ready[0]
    return ProxyInfo(
        proxy_url=selected_result["proxy"]["url"].rstrip("/"),
        browser=selected_result["browser"]["id"],
        protocol_version=2,
    )


class BrowserClient:
    def __init__(
        self,
        proxy_url: str,
        *,
        task_id: str | None = None,
        task_token: str | None = None,
    ):
        self.proxy_url = proxy_url.rstrip("/")
        self.task_id = task_id
        self.task_token = task_token
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        authenticated: bool = True,
        timeout: int = 45,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if authenticated:
            if not self.task_token:
                raise BrowserError("task_token_missing", "browser task token is missing")
            headers["Authorization"] = "Bearer " + self.task_token
        data = None
        if body is not None:
            data = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if method in {"POST", "DELETE"}:
            headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
        request = urllib.request.Request(
            self.proxy_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                payload = response.read()
                if not payload:
                    return None
                try:
                    return json.loads(payload.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError) as error:
                    raise BrowserError(
                        "browser_api_invalid",
                        "browser API returned invalid JSON",
                    ) from error
        except urllib.error.HTTPError as error:
            code = "browser_api_error"
            try:
                body_data = json.loads(error.read(8192).decode("utf-8"))
                code = str(
                    ((body_data.get("error") or {}).get("code"))
                    or body_data.get("code")
                    or code
                )
            except Exception:
                pass
            raise BrowserError(code, f"browser API HTTP {error.code}", status=error.code)
        except (urllib.error.URLError, TimeoutError) as error:
            raise BrowserError(
                "browser_transport_failed",
                "browser API transport failed",
            ) from error

    def create_task(self, label: str) -> dict[str, Any]:
        task = self._request(
            "POST",
            "/v2/tasks",
            {"label": label},
            authenticated=False,
        )
        if not isinstance(task, dict) or not task.get("taskId") or not task.get("taskToken"):
            raise BrowserError("task_create_invalid", "browser task response is invalid")
        self.task_id = task["taskId"]
        self.task_token = task["taskToken"]
        return task

    def task(self) -> dict[str, Any]:
        return self._request("GET", f"/v2/tasks/{self.task_id}")

    def create_tab(self, url: str, *, background: bool = True) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v2/tabs",
            {"url": url, "background": background},
        )

    def tabs(self) -> list[dict[str, Any]]:
        value = self._request("GET", "/v2/tabs")
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for key in ("tabs", "items", "targets"):
                if isinstance(value.get(key), list):
                    return value[key]
        return []

    def tab(self, target_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/tabs/{target_id}")

    def wait_load(self, target_id: str, timeout_ms: int = 15000) -> None:
        try:
            self._request(
                "POST",
                f"/v2/tabs/{target_id}/wait",
                {"state": "load", "timeoutMs": timeout_ms},
                timeout=max(15, timeout_ms // 1000 + 5),
            )
        except BrowserError as error:
            if error.code not in {"WAIT_TIMEOUT", "WAIT_CANCELLED"}:
                raise

    def eval(
        self,
        target_id: str,
        expression: str,
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        value = self._request(
            "POST",
            f"/v2/tabs/{target_id}/eval",
            {"expression": expression},
            idempotency_key=idempotency_key,
        )
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        return value

    def snapshot(self, target_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v2/tabs/{target_id}/snapshot?mode=interactive&maxNodes=500&refresh=true",
        )

    def action(
        self,
        target_id: str,
        body: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        return self._request(
            "POST",
            f"/v2/tabs/{target_id}/action",
            body,
            idempotency_key=idempotency_key,
        )

    def navigate(self, target_id: str, url: str) -> Any:
        return self._request(
            "POST",
            f"/v2/tabs/{target_id}/navigate",
            {"url": url},
        )

    def handoff(self, target_id: str) -> Any:
        return self._request(
            "POST",
            f"/v2/tasks/{self.task_id}/handoff",
            {"targetId": target_id},
        )

    def resume(self) -> Any:
        return self._request("POST", f"/v2/tasks/{self.task_id}/resume", {})

    def complete(self) -> Any:
        return self._request(
            "POST",
            f"/v2/tasks/{self.task_id}/complete",
            {"keep": False},
        )
