"""Task-scoped client for the web-access CDP proxy."""

from __future__ import annotations

import hashlib
import http.client
import socket
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from urllib.parse import unquote
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
    mode: str = "existing"
    broker_version: str | None = None
    instance_id: str | None = None
    cdp_port: int | None = None


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
    selected = (browser or os.environ.get("PAPER_DOWNLOAD_BROWSER") or "auto").lower()
    if selected not in {"auto", "edge"}:
        raise BrowserError(
            "unsupported_browser",
            "paper-download institutional access supports Microsoft Edge only",
        )
    # Browser control lives in web-access. Default to the running daily Edge
    # (existing mode) so the task reuses the user's real login state; managed
    # stays available only when explicitly requested.
    mode = (os.environ.get("PAPER_DOWNLOAD_BROWSER_MODE") or "existing").lower()
    if mode not in {"existing", "managed"}:
        raise BrowserError(
            "invalid_browser_mode",
            "PAPER_DOWNLOAD_BROWSER_MODE must be existing or managed",
        )
    command = [
        node,
        str(checker),
        "--browser",
        "edge",
        "--mode",
        mode,
        "--json",
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
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
        or parsed.get("browserMode") != mode
    ):
        raise BrowserError(
            str(parsed.get("status") or "browser_preflight_failed"),
            "web-access browser service is not ready",
        )
    results = parsed.get("results")
    if not isinstance(results, list):
        raise BrowserError(
            "browser_preflight_invalid",
            "web-access returned no browser result list",
        )
    ready = [
        item
        for item in results
        if isinstance(item, dict)
        and isinstance(item.get("browser"), dict)
        and isinstance(item.get("proxy"), dict)
        if item.get("ready") is True
        and (item.get("browser") or {}).get("id") == "edge"
        and (item.get("proxy") or {}).get("protocolVersion") == 2
        and (item.get("controlProbe") or {}).get("passed") is True
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
        mode=str(parsed.get("browserMode") or mode),
        broker_version=parsed.get("brokerVersion"),
        instance_id=selected_result.get("instanceId"),
        cdp_port=(selected_result.get("browser") or {}).get("cdpPort"),
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
                error_value = body_data.get("error") if isinstance(body_data, dict) else None
                if isinstance(error_value, dict):
                    code = str(error_value.get("code") or code)
                elif isinstance(error_value, str) and error_value:
                    code = error_value
                if isinstance(body_data, dict) and body_data.get("code"):
                    code = str(body_data["code"])
            except Exception:
                pass
            raise BrowserError(code, f"browser API HTTP {error.code}", status=error.code)
        except http.client.IncompleteRead as error:
            raise BrowserError("incomplete", "browser download transport was interrupted") from error
        except (TimeoutError, socket.timeout) as error:
            raise BrowserError("download_timeout", "browser download timed out") from error
        except (urllib.error.URLError, ConnectionError, http.client.HTTPException) as error:
            raise BrowserError("browser_transport_failed", "browser API transport failed") from error

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

    def access(self, target_id: str, *, allow_autofill: bool = True) -> dict[str, Any]:
        return self._request("POST", f"/v2/tabs/{target_id}/access", {"allowAutofill": allow_autofill})

    def download(
        self,
        target_id: str,
        url: str,
        *,
        allowed_hosts: list[str] | None = None,
        timeout_ms: int = 120_000,
        max_bytes: int | None = None,
        idempotency_key: str | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        """Fetch bytes through the web-access broker download endpoint.

        The broker validates the host, unwraps HTML wrappers, enforces the size
        cap, verifies the PDF signature and returns a SHA-256. It never writes a
        partial file, so a non-2xx response always means no usable bytes.
        """
        body: dict[str, Any] = {"url": url, "timeoutMs": int(timeout_ms)}
        if allowed_hosts:
            body["allowedHosts"] = list(allowed_hosts)
        if max_bytes is not None:
            body["maxBytes"] = int(max_bytes)
        raw, headers, status = self._request_raw(
            "POST",
            f"/v2/tabs/{target_id}/download",
            body,
            idempotency_key=idempotency_key,
            timeout=max(30.0, timeout_ms / 1000 + 30.0),
            max_bytes=max_bytes if max_bytes is not None else 50_000_000,
        )
        if status < 200 or status >= 300:
            raise BrowserError("download_failed", f"browser download HTTP {status}")
        if not raw.startswith(b"%PDF-") or headers.get("x-download-is-pdf") != "true":
            raise BrowserError("not_pdf", "browser download did not return a PDF")
        try:
            expected_bytes = int(headers.get("x-download-bytes", ""))
        except ValueError as error:
            raise BrowserError("incomplete", "browser download length metadata is invalid") from error
        expected_sha = headers.get("x-download-sha256", "")
        if expected_bytes != len(raw) or expected_bytes < 5:
            raise BrowserError("incomplete", "browser download length does not match")
        if len(raw) > (max_bytes if max_bytes is not None else 50_000_000):
            raise BrowserError("too_large", "browser download exceeded the size limit")
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha) or hashlib.sha256(raw).hexdigest() != expected_sha:
            raise BrowserError("incomplete", "browser download SHA-256 does not match")
        meta = {
            "sha256": expected_sha,
            "bytes": expected_bytes,
            "is_pdf": True,
            "final_url": unquote(headers.get("x-download-final-url", "")),
        }
        return raw, meta

    def _request_raw(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        timeout: float = 180.0,
        max_bytes: int = 50_000_000,
    ) -> tuple[bytes, dict[str, str], int]:
        if not self.task_token:
            raise BrowserError("task_token_missing", "browser task token is missing")
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.task_token}",
            "Accept": "*/*",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if method in {"POST", "DELETE"}:
            headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
        request = urllib.request.Request(
            self.proxy_url + path,
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                chunks: list[bytes] = []
                received = 0
                while True:
                    chunk = response.read(min(262_144, max_bytes - received + 1))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > max_bytes:
                        raise BrowserError("too_large", "browser download exceeded the size limit")
                    chunks.append(chunk)
                return (
                    b"".join(chunks),
                    {key.lower(): value for key, value in response.headers.items()},
                    response.status,
                )
        except urllib.error.HTTPError as error:
            code = "browser_api_error"
            try:
                body_data = json.loads(error.read(8192).decode("utf-8"))
                error_value = body_data.get("error") if isinstance(body_data, dict) else None
                if isinstance(error_value, dict):
                    code = str(error_value.get("code") or code)
                elif isinstance(error_value, str) and error_value:
                    code = error_value
                if isinstance(body_data, dict) and body_data.get("code"):
                    code = str(body_data["code"])
            except Exception:
                pass
            raise BrowserError(code, f"browser API HTTP {error.code}", status=error.code)
        except http.client.IncompleteRead as error:
            raise BrowserError("incomplete", "browser download transport was interrupted") from error
        except (TimeoutError, socket.timeout) as error:
            raise BrowserError("download_timeout", "browser download timed out") from error
        except (urllib.error.URLError, ConnectionError, http.client.HTTPException) as error:
            raise BrowserError("browser_transport_failed", "browser API transport failed") from error
