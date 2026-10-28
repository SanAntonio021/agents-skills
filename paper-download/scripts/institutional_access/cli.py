"""CLI for public, manual-login institutional PDF acquisition."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .browser import BrowserClient, BrowserError, check_web_access
from .pdf_tools import MAX_PDF_BYTES, validate_pdf_bytes, write_new_file
from .providers import (
    Provider,
    candidate_pdf_urls,
    get_provider,
    metadata_doi,
    normalize_doi,
    page_state_expression,
    pdf_button_node,
    public_page_identity,
    safe_url,
)
from .session_store import (
    SessionError,
    get_session_store,
    session_lock,
    validate_session_id,
)


class OperationError(RuntimeError):
    def __init__(self, stage: str, reason: str):
        super().__init__(reason)
        self.stage = stage
        self.reason = reason


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_summary(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session": session.get("sessionId"),
        "stage": session.get("stage"),
        "provider": session.get("provider"),
        "article": safe_url(session.get("requestedArticle") or ""),
        "doi": session.get("doi"),
        "browser": session.get("browser"),
        "updated_at": session.get("updatedAt"),
        "user_action_required": bool(session.get("userHandoffRequired", session.get("stage") == "user_login_required")),
        "failure_code": session.get("failure_code"),
        "browser_interaction_required": bool(session.get("browserInteraction")),
    }


def save_stage(
    store: Any,
    session: dict[str, Any],
    stage: str,
    **extra: Any,
) -> dict[str, Any]:
    session.update(extra)
    session["stage"] = stage
    session["updatedAt"] = utc_now()
    store.write(session["sessionId"], session)
    result = session_summary(session)
    result.update(
        {
            key: value
            for key, value in extra.items()
            if key
            not in {
                "taskToken",
                "taskId",
                "targetId",
                "proxyUrl",
                "requestedArticle",
            }
        }
    )
    return result


def load_session(store: Any, session_id: str) -> dict[str, Any]:
    validate_session_id(session_id)
    value = store.read(session_id)
    if not isinstance(value, dict):
        raise OperationError("no_session", "session does not exist")
    required = {"taskId", "taskToken", "targetId", "requestedArticle", "doi", "provider"}
    if not required.issubset(value):
        raise OperationError("session_invalid", "session record is incomplete")
    return value


def browser_for_session(session: dict[str, Any]) -> BrowserClient:
    return BrowserClient(
        session["proxyUrl"],
        task_id=session["taskId"],
        task_token=session["taskToken"],
    )


def reconcile_created_tab(
    client: BrowserClient,
    requested_url: str,
    *,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    """Recover a tab whose create-target result timed out.

    The Proxy may have created the target even when the mutation returns
    UNKNOWN_RESULT. Only empty tabs owned by this task are eligible.
    """
    deadline = time.monotonic() + timeout_seconds
    blank_since: float | None = None
    navigate_at: float | None = None
    while time.monotonic() < deadline:
        tabs = client.tabs()
        if len(tabs) > 1:
            raise BrowserError(
                "tab_create_ambiguous",
                "timed-out tab creation produced multiple task tabs",
            )
        if tabs:
            item = tabs[0]
            target_id = item.get("targetId") or item.get("id")
            if target_id:
                detail = client.tab(target_id)
                url = str(detail.get("url") or item.get("url") or "")
                if url and url not in {"about:blank", "edge://newtab/"}:
                    return {**item, **detail, "targetId": target_id}
                if blank_since is None:
                    blank_since = time.monotonic()
                if navigate_at is None and time.monotonic() - blank_since >= 3:
                    try:
                        client.navigate(target_id, requested_url)
                        navigate_at = time.monotonic()
                    except BrowserError as error:
                        if error.code == "TARGET_BUSY":
                            pass
                        elif error.code == "UNKNOWN_RESULT":
                            navigate_at = time.monotonic()
                        else:
                            raise
        time.sleep(0.5)
    raise BrowserError(
        "tab_create_unknown",
        "timed-out tab creation did not produce a usable task tab",
    )


def create_session(
    store: Any,
    *,
    session_id: str,
    provider: Provider,
    article_url: str,
    doi: str,
    browser: str,
) -> tuple[dict[str, Any], BrowserClient]:
    proxy = check_web_access(browser)
    client = BrowserClient(proxy.proxy_url)
    task = client.create_task("paper-download institutional access")
    session = {
        "schemaVersion": 1,
        "sessionId": session_id,
        "provider": provider.id,
        "requestedArticle": article_url,
        "doi": doi,
        "browser": proxy.browser,
        "proxyUrl": proxy.proxy_url,
        "taskId": task["taskId"],
        "taskToken": task["taskToken"],
        "targetId": "",
        "stage": "starting",
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    store.write(session_id, session)
    try:
        try:
            tab = client.create_tab(article_url, background=True)
        except BrowserError as error:
            if error.code != "UNKNOWN_RESULT":
                raise
            tab = reconcile_created_tab(client, article_url)
        target_id = tab.get("targetId") or tab.get("id")
        if not target_id:
            raise BrowserError("tab_create_invalid", "browser tab response is invalid")
        session["targetId"] = target_id
        store.write(session_id, session)
        client.wait_load(target_id, timeout_ms=15000)
    except Exception:
        try:
            client.complete()
        except Exception:
            pass
        store.delete(session_id)
        raise
    return session, client


def task_state(client: BrowserClient) -> str:
    task = client.task()
    return str(task.get("state") or "unknown")


def set_handoff(
    store: Any,
    session: dict[str, Any],
    client: BrowserClient,
    *,
    stage: str,
    reason: str,
    instruction: str,
) -> dict[str, Any]:
    state = task_state(client)
    if state == "active":
        try:
            client.handoff(session["targetId"])
        except BrowserError as error:
            if error.code != "UNKNOWN_RESULT":
                raise
            if task_state(client) != "handoff":
                raise
    elif state == "handoff":
        pass
    elif state in {"completed", "expired"}:
        store.delete(session["sessionId"])
        raise OperationError("session_ended", f"browser task is {state}")
    return save_stage(
        store,
        session,
        stage,
        reason=reason,
        instruction=instruction,
    )


def page_state(client: BrowserClient, target_id: str) -> dict[str, Any]:
    for attempt in range(3):
        try:
            value = client.eval(target_id, page_state_expression())
            if isinstance(value, dict):
                return value
        except BrowserError as error:
            if error.code not in {"EVAL_FAILED", "TARGET_BUSY"} or attempt == 2:
                raise
        time.sleep(1)
    raise BrowserError("page_state_invalid", "browser page state is unavailable")


def wait_for_page_signal(
    client: BrowserClient,
    target_id: str,
    provider: Provider,
) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    login_signal_since: float | None = None
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = page_state(client, target_id)
        if (
            metadata_doi(latest)
            or candidate_pdf_urls(provider, latest)
            or any(latest.get("accessSignals") or [])
            or any(latest.get("openAccessSignals") or [])
            or latest.get("challenge")
        ):
            return latest
        if any(latest.get("loginSignals") or []) or any(latest.get("denialSignals") or []):
            if login_signal_since is None:
                login_signal_since = time.monotonic()
            elif time.monotonic() - login_signal_since >= 3:
                return latest
        if latest.get("readyState") in {"interactive", "complete"}:
            time.sleep(0.5)
        else:
            time.sleep(0.25)
    return latest


def continue_browser_access(store: Any, session: dict[str, Any], client: BrowserClient,
                            *, allow_autofill: bool) -> dict[str, Any] | None:
    """Delegate authentication and challenge decisions to web-access."""
    access = client.access(session["targetId"], allow_autofill=allow_autofill)
    if access.get("state") == "ready":
        return None
    session["browserInteraction"] = not bool(access.get("handoffRequired"))
    session["userHandoffRequired"] = bool(access.get("handoffRequired"))
    session["failure_code"] = access.get("failureCode")
    if access.get("handoffRequired"):
        return set_handoff(store, session, client, stage="user_login_required",
                           reason=str(access.get("reason") or "strong authentication required"),
                           instruction="请完成当前页面的短信、动态口令、刷脸或系统身份验证，随后继续原任务。")
    return save_stage(store, session,
                      "publisher_verification" if access.get("state") in {"verification_required", "challenge"} else "user_login_required",
                      reason=str(access.get("reason") or access.get("state") or "browser interaction required"),
                      failure_code=access.get("failureCode") or "auth_required",
                      browser_interaction=access)


def click_pdf_control(client: BrowserClient, target_id: str, provider: Provider) -> bool:
    snapshot = client.snapshot(target_id)
    node = pdf_button_node(snapshot, provider)
    if not node:
        return False
    try:
        client.action(
            target_id,
            {"action": "click", "ref": node["ref"]},
            idempotency_key=str(uuid.uuid4()),
        )
    except BrowserError as error:
        if error.code != "UNKNOWN_RESULT":
            raise
    time.sleep(2)
    return True


def inspect_tabs_for_pdf(
    client: BrowserClient,
    provider: Provider,
) -> list[str]:
    candidates: list[str] = []
    for item in client.tabs():
        target_id = item.get("targetId") or item.get("id")
        if not target_id:
            continue
        try:
            detail = client.tab(target_id)
            href = detail.get("url") or ""
            if href.startswith("https://") and urlsplit(href).hostname == provider.host:
                lowered = href.lower()
                if (
                    detail.get("contentType") == "application/pdf"
                    or "stamppdf" in lowered
                    or "getpdf" in lowered
                    or "directpdfaccess" in lowered
                ):
                    candidates.append(href)
            try:
                value = client.eval(
                    target_id,
                    "({href:location.href,contentType:document.contentType,"
                    "embeds:[...document.querySelectorAll('iframe[src],embed[src],"
                    "object[data]')].map(e=>{try{return new URL(e.src||e.data,"
                    "location.href).href}catch(_){return ''}}).filter(Boolean)})",
                )
            except BrowserError:
                continue
            if isinstance(value, dict):
                if (
                    value.get("contentType") == "application/pdf"
                    and str(value.get("href") or "").startswith("https://")
                ):
                    candidates.append(value["href"])
                candidates.extend(
                    item
                    for item in value.get("embeds", [])
                    if isinstance(item, str) and item.startswith("https://")
                )
        except BrowserError:
            continue
    unique: list[str] = []
    for value in candidates:
        parsed = urlsplit(value)
        if parsed.hostname != provider.host:
            continue
        if value not in unique:
            unique.append(value)
    return unique


def looks_like_pdf_viewer(provider: Provider, value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.hostname != provider.host:
        return False
    lowered = parsed.path.lower()
    return (
        lowered.endswith(".pdf")
        or "directpdfaccess" in lowered
        or "stamppdf" in lowered
        or "getpdf" in lowered
    )


def restore_pdf_fetch_context(
    client: BrowserClient,
    session: dict[str, Any],
    provider: Provider,
    state: dict[str, Any],
) -> dict[str, Any]:
    is_pdf = state.get("contentType") == "application/pdf"
    if not is_pdf:
        try:
            is_pdf = looks_like_pdf_viewer(
                provider,
                str(client.tab(session["targetId"]).get("url") or ""),
            )
        except BrowserError:
            return state
    if not is_pdf:
        return state
    client.navigate(session["targetId"], session["requestedArticle"])
    client.wait_load(session["targetId"], timeout_ms=15000)
    return wait_for_page_signal(client, session["targetId"], provider)


def try_download(
    store: Any,
    session: dict[str, Any],
    client: BrowserClient,
    provider: Provider,
    state: dict[str, Any],
    output: Path,
) -> dict[str, Any] | None:
    candidates = candidate_pdf_urls(provider, state)
    if candidates:
        state = restore_pdf_fetch_context(client, session, provider, state)
    if not candidates:
        if click_pdf_control(client, session["targetId"], provider):
            candidates = inspect_tabs_for_pdf(client, provider)
            state = restore_pdf_fetch_context(client, session, provider, state)
            if not candidates:
                try:
                    refreshed = page_state(client, session["targetId"])
                except BrowserError:
                    refreshed = state
                candidates = candidate_pdf_urls(provider, refreshed)
    if not candidates:
        return None
    identity = public_page_identity(state, session["doi"], provider)
    candidates = candidates[:5]
    overall_deadline = time.monotonic() + 120
    last_failure: str | None = None
    for candidate in candidates:
        candidate_parts = urlsplit(candidate)
        if candidate_parts.scheme != "https" or candidate_parts.hostname != provider.host:
            continue
        remaining = int(overall_deadline - time.monotonic())
        if remaining < 5:
            break
        try:
            raw, _download_metadata = client.download(
                session["targetId"],
                candidate,
                allowed_hosts=[provider.host],
                timeout_ms=min(60_000, remaining * 1000),
                max_bytes=MAX_PDF_BYTES,
                idempotency_key=str(uuid.uuid4()),
            )
            validation = validate_pdf_bytes(
                raw,
                doi=session["doi"],
                title=str(state.get("title") or session.get("pageTitle") or ""),
                provider_identity_match=(
                    identity.get("doi_match") is not False
                    or session.get("pageDoi") == session["doi"]
                ),
            )
            write_new_file(output, raw)
            if not validation["identity_verified"]:
                return save_stage(
                    store,
                    session,
                    "downloaded_identity_requires_review",
                    source=safe_url(session["requestedArticle"]),
                    path=str(output),
                    validation=validation,
                    access=session.get("accessEvidence", "unknown"),
                )
            return save_stage(
                store,
                session,
                "downloaded_identity_verified",
                source=safe_url(session["requestedArticle"]),
                path=str(output),
                validation=validation,
                access=session.get("accessEvidence", "unknown"),
                version="official",
            )
        except BrowserError as error:
            last_failure = error.code
            continue
        except (OperationError, ValueError):
            last_failure = "pdf_validation_failed"
            continue
    return save_stage(
        store,
        session,
        "pdf_download_failed",
        source=safe_url(session["requestedArticle"]),
        reason=last_failure or "authorized PDF response was not usable",
        failure_code=last_failure or "not_pdf",
    )


def observe_and_continue(
    store: Any,
    session: dict[str, Any],
    client: BrowserClient,
    provider: Provider,
    output: Path,
    *,
    after_user_login: bool,
    allow_autofill: bool = True,
) -> dict[str, Any]:
    state = task_state(client)
    if state == "handoff":
        result = session_summary(session)
        result["reason"] = "same browser task is waiting for the user"
        return result
    if state != "active":
        store.delete(session["sessionId"])
        raise OperationError("session_ended", f"browser task is {state}")
    tab = client.tab(session["targetId"])
    tab_url = str(tab.get("url") or "")
    parsed = urlsplit(tab_url)
    if parsed.scheme == "about":
        client.navigate(session["targetId"], session["requestedArticle"])
        client.wait_load(session["targetId"], timeout_ms=15000)
        tab = client.tab(session["targetId"])
        tab_url = str(tab.get("url") or "")
        parsed = urlsplit(tab_url)
    if parsed.hostname != provider.host:
        result = continue_browser_access(store, session, client, allow_autofill=allow_autofill)
        if result is not None:
            return result
        return save_stage(store, session, "user_login_required",
                          reason="web-access must continue the institutional redirect", failure_code="auth_required")
    client.wait_load(session["targetId"], timeout_ms=15000)
    state_data = wait_for_page_signal(client, session["targetId"], provider)
    if any(state_data.get("accessSignals") or []):
        session["accessEvidence"] = "institutional"
    elif any(state_data.get("openAccessSignals") or []):
        session["accessEvidence"] = "open"
    if session.get("accessEvidence"):
        store.write(session["sessionId"], session)
    page_doi = metadata_doi(state_data)
    if page_doi and page_doi != session["doi"]:
        raise OperationError(
            "identity_mismatch",
            "publisher page DOI differs from the requested DOI",
        )
    if page_doi == session["doi"]:
        session["pageDoi"] = page_doi
        session["pageTitle"] = str(state_data.get("title") or "")
        store.write(session["sessionId"], session)
    downloaded = try_download(store, session, client, provider, state_data, output)
    if downloaded is not None:
        return downloaded
    if state_data.get("challenge"):
        return continue_browser_access(store, session, client, allow_autofill=allow_autofill) or save_stage(
            store, session, "publisher_verification", reason="site challenge requires web-access page interaction", failure_code="challenge")
    access = any(state_data.get("accessSignals") or [])
    if access:
        return save_stage(
            store,
            session,
            "institutional_access",
            reason="institution appears active but no usable PDF source was found",
            page=public_page_identity(state_data, session["doi"], provider),
        )
    if any(state_data.get("openAccessSignals") or []):
        return save_stage(
            store,
            session,
            "pdf_source_not_found",
            reason="open-access page was found but no usable PDF source was visible",
            page=public_page_identity(state_data, session["doi"], provider),
        )
    if any(state_data.get("loginSignals") or []):
        return continue_browser_access(store, session, client, allow_autofill=allow_autofill) or save_stage(
            store, session, "user_login_required", reason="institutional sign-in requires web-access", failure_code="auth_required")
    if after_user_login:
        return save_stage(
            store,
            session,
            "access_unavailable",
            reason="publisher page is reachable but institutional PDF access is absent",
            page=public_page_identity(state_data, session["doi"], provider),
        )
    return continue_browser_access(store, session, client, allow_autofill=allow_autofill) or save_stage(
        store, session, "user_login_required", reason="publisher does not expose an authorized PDF", failure_code="auth_required")


def acquire(args: argparse.Namespace) -> dict[str, Any]:
    provider = get_provider(args.url)
    article_url = provider.normalize_article_url(args.url)
    doi = normalize_doi(args.doi)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise OperationError("output_exists", "output PDF already exists")
    store = get_session_store()
    session = store.read(args.session)
    if session is not None:
        if (
            session.get("provider") != provider.id
            or session.get("doi") != doi
            or session.get("requestedArticle") != article_url
        ):
            raise OperationError(
                "session_conflict",
                "session belongs to a different article or DOI",
            )
        client = browser_for_session(session)
    else:
        session, client = create_session(
            store,
            session_id=args.session,
            provider=provider,
            article_url=article_url,
            doi=doi,
            browser=args.browser,
        )
    return observe_and_continue(
        store,
        session,
        client,
        provider,
        output,
        after_user_login=False,
    )


def resume(args: argparse.Namespace) -> dict[str, Any]:
    store = get_session_store()
    session = load_session(store, args.session)
    doi = normalize_doi(args.doi)
    if doi != session["doi"]:
        raise OperationError("session_conflict", "session DOI differs")
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise OperationError("output_exists", "output PDF already exists")
    provider = get_provider(session["requestedArticle"])
    client = browser_for_session(session)
    state = task_state(client)
    if state == "handoff":
        try:
            client.resume()
        except BrowserError as error:
            if error.code != "UNKNOWN_RESULT" or task_state(client) != "active":
                raise
    elif state != "active":
        store.delete(args.session)
        raise OperationError("session_ended", f"browser task is {state}")
    return observe_and_continue(
        store,
        session,
        client,
        provider,
        output,
        after_user_login=True,
    )


def status(args: argparse.Namespace) -> dict[str, Any]:
    store = get_session_store()
    session = load_session(store, args.session)
    client = browser_for_session(session)
    try:
        state = task_state(client)
    except BrowserError as error:
        raise OperationError("session_unavailable", error.code) from error
    if state in {"completed", "expired"}:
        result = session_summary(session)
        result["task_state"] = state
        store.delete(args.session)
        return result
    result = session_summary(session)
    result["task_state"] = state
    return result


def complete(args: argparse.Namespace) -> dict[str, Any]:
    store = get_session_store()
    session = load_session(store, args.session)
    client = browser_for_session(session)
    state = task_state(client)
    if state == "handoff":
        return {
            "stage": "task_in_handoff",
            "reason": "resume the browser task after user verification before completing",
        }
    if state == "active":
        try:
            client.complete()
        except BrowserError as error:
            if error.code != "UNKNOWN_RESULT":
                raise
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                state = task_state(client)
            except BrowserError:
                state = "unknown"
            if state != "active":
                break
            time.sleep(0.5)
        if state == "active":
            return {
                "stage": "completion_requires_inspection",
                "task_state": state,
            }
    if state in {"completed", "expired"}:
        store.delete(args.session)
        return {"stage": "completed", "task_state": state}
    return {"stage": "completion_requires_inspection", "task_state": state}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Public manual-login institutional PDF downloader"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("--session", required=True)
    acquire_parser.add_argument("--url", required=True)
    acquire_parser.add_argument("--doi", required=True)
    acquire_parser.add_argument("--output", required=True)
    acquire_parser.add_argument(
        "--browser", choices=("auto", "edge"), default="auto"
    )
    acquire_parser.set_defaults(handler=acquire)
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--session", required=True)
    resume_parser.add_argument("--doi", required=True)
    resume_parser.add_argument("--output", required=True)
    resume_parser.set_defaults(handler=resume)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--session", required=True)
    status_parser.set_defaults(handler=status)
    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--session", required=True)
    complete_parser.set_defaults(handler=complete)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        with session_lock(args.session):
            result = args.handler(args)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except OperationError as error:
        print(
            json.dumps(
                {"stage": error.stage, "reason": error.reason},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1
    except BrowserError as error:
        print(
            json.dumps(
                {
                    "stage": "browser_error",
                    "reason": error.code,
                    "http_status": error.status,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1
    except SessionError as error:
        print(
            json.dumps(
                {"stage": "session_error", "reason": str(error)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1
    except (ValueError, OSError):
        print(
            json.dumps(
                {"stage": "operation_failed", "reason": "local operation failed"},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1
