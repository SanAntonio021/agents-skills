"""CLI for public, manual-login institutional PDF acquisition."""

from __future__ import annotations

import argparse
import base64
import hashlib
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
        "user_action_required": session.get("stage")
        in {"user_login_required", "publisher_verification"},
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
        tab = client.create_tab(article_url, background=True)
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
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = page_state(client, target_id)
        if (
            metadata_doi(latest)
            or candidate_pdf_urls(provider, latest)
            or any(latest.get("accessSignals") or [])
            or any(latest.get("openAccessSignals") or [])
            or any(latest.get("loginSignals") or [])
            or any(latest.get("denialSignals") or [])
            or latest.get("challenge")
        ):
            return latest
        if latest.get("readyState") in {"interactive", "complete"}:
            time.sleep(0.5)
        else:
            time.sleep(0.25)
    return latest


def login_autofill_expression(*, submit: bool) -> str:
    expression = r"""(() => {
      const submitRequested = __SUBMIT__;
      const visible = e => !!e && e.getClientRects().length > 0;
      const matches = (element, selector) => {
        try { return element.matches(selector); } catch (_) { return false; }
      };
      const autofilled = element =>
        matches(element, ':-webkit-autofill') || matches(element, ':autofill');
      if (location.protocol !== 'https:') return {status: 'not_https'};
      const pageText = (
        (document.title || '') + '\n' +
        ((document.body && document.body.innerText) || '').slice(0, 12000)
      );
      if (!/(?:sign in|log in|login|single sign-on|\bsso\b|登录|统一身份认证)/i.test(pageText))
        return {status: 'not_login_page'};

      const passwords = [...document.querySelectorAll('input[type="password"]')]
        .filter(visible);
      if (!passwords.length) return {status: 'no_password_form'};
      const forms = [...new Set(passwords.map(input => input.form).filter(Boolean))];
      if (
        forms.length !== 1 ||
        passwords.filter(input => input.form === forms[0]).length !== 1
      )
        return {status: 'ambiguous_form'};

      const form = forms[0];
      let action;
      try {
        action = new URL(form.getAttribute('action') || location.href, location.href);
      } catch (_) {
        return {status: 'insecure_form'};
      }
      if (
        action.protocol !== 'https:' ||
        action.origin !== location.origin ||
        (form.method || 'get').toLowerCase() !== 'post' ||
        !['', '_self'].includes((form.target || '').toLowerCase())
      )
        return {status: 'insecure_form'};

      const identityFields = [...form.querySelectorAll('input')]
        .filter(input => {
          if (!visible(input)) return false;
          const type = (input.type || 'text').toLowerCase();
          if (!['text', 'email', 'tel'].includes(type)) return false;
          const hint = [
            input.type,
            input.name,
            input.id,
            input.getAttribute('autocomplete')
          ].filter(Boolean).join(' ');
          return type === 'email' ||
            /user(?:name)?|e-?mail|login|account|uid|学号|工号/i.test(hint);
        });
      if (identityFields.length !== 1) return {status: 'ambiguous_identity'};
      if (!autofilled(identityFields[0]))
        return {status: 'identity_not_filled'};
      if (!autofilled(passwords[0]))
        return {status: 'password_not_filled'};

      const requiredChoices = [
        ...form.querySelectorAll(
          'input[type="checkbox"][required],input[type="radio"][required]'
        )
      ].filter(visible);
      if (requiredChoices.some(input => !input.checked))
        return {status: 'consent_required'};

      const submitControls = [
        ...form.querySelectorAll('button,input[type="submit"],input[type="image"]')
      ].filter(control => {
        if (!visible(control) || control.disabled) return false;
        if ((control.tagName || '').toLowerCase() === 'button') {
          return ['', 'submit'].includes(
            (control.getAttribute('type') || '').toLowerCase()
          );
        }
        return true;
      });
      if (submitControls.length !== 1) return {status: 'ambiguous_submit'};

      if (submitRequested) {
        try {
          form.requestSubmit(submitControls[0]);
        } catch (_) {
          return {status: 'submit_failed'};
        }
        return {status: 'submitted', host: location.hostname, path: location.pathname};
      }
      return {status: 'ready', host: location.hostname, path: location.pathname};
    })()"""
    return expression.replace("__SUBMIT__", "true" if submit else "false")


_AUTOFILL_NON_SUBMIT_STATUSES = {
    "not_https",
    "not_login_page",
    "no_password_form",
    "ambiguous_form",
    "insecure_form",
    "ambiguous_identity",
    "identity_not_filled",
    "password_not_filled",
    "consent_required",
    "ambiguous_submit",
    "submit_failed",
}


def try_submit_autofilled_login(
    store: Any,
    session: dict[str, Any],
    client: BrowserClient,
) -> str:
    """Submit one uniquely identified, already-filled login form.

    The page script only returns booleans and page identity. It never returns
    account, password, cookie, or arbitrary form values.
    """
    if session.get("loginSubmitAttempted"):
        return "already_attempted"
    detected = client.eval(
        session["targetId"],
        login_autofill_expression(submit=False),
    )
    status = str(detected.get("status") or "") if isinstance(detected, dict) else ""
    if status != "ready":
        return status or "autofill_unavailable"

    session["loginSubmitAttempted"] = True
    session["loginSubmitAt"] = utc_now()
    session["loginSubmitHost"] = str(detected.get("host") or "")[:255]
    store.write(session["sessionId"], session)
    key = str(uuid.uuid4())
    try:
        submitted = client.eval(
            session["targetId"],
            login_autofill_expression(submit=True),
            idempotency_key=key,
        )
    except BrowserError as error:
        if error.code == "UNKNOWN_RESULT":
            session["loginSubmitResult"] = "unknown"
            store.write(session["sessionId"], session)
            return "submit_unknown"
        session["loginSubmitResult"] = "failed"
        store.write(session["sessionId"], session)
        return "submit_failed"

    submitted_status = (
        str(submitted.get("status") or "") if isinstance(submitted, dict) else ""
    )
    if submitted_status == "submitted":
        session["loginSubmitResult"] = "submitted"
        store.write(session["sessionId"], session)
        return "submitted"
    if submitted_status in _AUTOFILL_NON_SUBMIT_STATUSES:
        session["loginSubmitAttempted"] = False
        session.pop("loginSubmitAt", None)
        session.pop("loginSubmitHost", None)
        session["loginSubmitResult"] = submitted_status
        store.write(session["sessionId"], session)
        return submitted_status
    session["loginSubmitResult"] = "unknown"
    store.write(session["sessionId"], session)
    return "submit_unknown"


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


def fetch_pdf_bytes(
    client: BrowserClient,
    target_id: str,
    candidate: str,
    provider: Provider,
    *,
    timeout_seconds: int = 60,
) -> bytes:
    key = "__paperDownload_" + uuid.uuid4().hex
    script = r"""(() => {
      const key = __KEY__;
      const startUrl = __URL__;
      const expectedHost = __HOST__;
      const maxBytes = __MAX__;
      const expectedOrigin = new URL(startUrl).origin;
      window[key] = {state: 'pending'};
      (async () => {
        try {
          const visit = async (url, depth = 0) => {
            if (depth > 2) throw new Error('too_many_wrappers');
            const expected = new URL(url);
            if (
              expected.protocol !== 'https:' ||
              expected.hostname !== expectedHost ||
              expected.origin !== expectedOrigin ||
              expected.username ||
              expected.password
            )
              throw new Error('unexpected_pdf_origin');
            const response = await fetch(url, {
              credentials: 'same-origin',
              signal: AbortSignal.timeout(__TIMEOUT_MS__)
            });
            if (!response.ok) throw new Error('pdf_http_error');
            const finalUrl = new URL(response.url);
            if (
              finalUrl.protocol !== 'https:' ||
              finalUrl.hostname !== expectedHost ||
              finalUrl.origin !== expectedOrigin ||
              finalUrl.username ||
              finalUrl.password
            )
              throw new Error('unexpected_final_pdf_origin');
            const mime = (response.headers.get('content-type') || '').toLowerCase();
            if (mime.includes('text/html')) {
              const html = await response.text();
              const doc = new DOMParser().parseFromString(html, 'text/html');
              const nodes = [...doc.querySelectorAll('iframe[src],embed[src],object[data]')];
              for (const node of nodes) {
                const next = new URL(node.getAttribute('src') || node.getAttribute('data'), url).href;
                if (new URL(next).hostname === expectedHost) return visit(next, depth + 1);
              }
              throw new Error('pdf_source_not_found');
            }
            if (!(mime.includes('pdf') || mime.includes('octet-stream')))
              throw new Error('unexpected_pdf_content_type');
            const declared = Number(response.headers.get('content-length') || 0);
            if (declared > maxBytes) throw new Error('pdf_too_large');
            const reader = response.body.getReader();
            const chunks = [];
            let total = 0;
            while (true) {
              const part = await reader.read();
              if (part.done) break;
              total += part.value.byteLength;
              if (total > maxBytes) {
                await reader.cancel();
                throw new Error('pdf_too_large');
              }
              chunks.push(part.value);
            }
            const bytes = new Uint8Array(total);
            let offset = 0;
            for (const chunk of chunks) {
              bytes.set(chunk, offset);
              offset += chunk.byteLength;
            }
            if (bytes.length < 5 || String.fromCharCode(...bytes.slice(0, 5)) !== '%PDF-')
              throw new Error('invalid_pdf_signature');
            const sha256 = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
              .map(value => value.toString(16).padStart(2, '0')).join('');
            const blob = new Blob([bytes], {type: 'application/pdf'});
            const dataUrl = await new Promise((resolve, reject) => {
              const fileReader = new FileReader();
              fileReader.onload = () => resolve(fileReader.result);
              fileReader.onerror = () => reject(fileReader.error || new Error('file_reader_failed'));
              fileReader.readAsDataURL(blob);
            });
            const data = String(dataUrl).slice(String(dataUrl).indexOf(',') + 1);
            window[key] = {
              state: 'done', data, chars: data.length, bytes: bytes.length,
              sha256, mime: mime, source: finalUrl.origin + finalUrl.pathname
            };
          };
          await visit(startUrl);
        } catch (_) {
          window[key] = {state: 'error'};
        }
      })();
      return true;
    })()"""
    script = (
        script.replace("__KEY__", json.dumps(key))
        .replace("__URL__", json.dumps(candidate))
        .replace("__HOST__", json.dumps(provider.host))
        .replace("__MAX__", str(MAX_PDF_BYTES))
        .replace("__TIMEOUT_MS__", str(timeout_seconds * 1000))
    )
    try:
        client.eval(
            target_id,
            script,
            idempotency_key=str(uuid.uuid4()),
        )
    except BrowserError as error:
        if error.code != "UNKNOWN_RESULT":
            raise
    deadline = time.monotonic() + timeout_seconds + 10
    metadata: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        value = client.eval(
            target_id,
            "(()=>{const x=window["
            + json.dumps(key)
            + "];if(!x||x.state==='pending')return null;"
            "const {data,...rest}=x;return rest;})()",
        )
        if isinstance(value, dict):
            if value.get("state") != "done":
                client.eval(target_id, "delete window[" + json.dumps(key) + "]")
                raise OperationError(
                    "pdf_download_failed",
                    "browser PDF response was not usable",
                )
            metadata = value
            break
        time.sleep(0.25)
    if metadata is None:
        raise OperationError("pdf_download_timeout", "browser PDF fetch timed out")
    chars = metadata.get("chars")
    size = metadata.get("bytes")
    expected_sha = metadata.get("sha256")
    if (
        not isinstance(chars, int)
        or not isinstance(size, int)
        or not 5 <= size <= MAX_PDF_BYTES
        or not isinstance(expected_sha, str)
    ):
        raise OperationError("pdf_download_invalid", "browser PDF metadata is invalid")
    chunks: list[str] = []
    for offset in range(0, chars, 262144):
        expression = (
            "window["
            + json.dumps(key)
            + "].data.slice("
            + str(offset)
            + ","
            + str(offset + 262144)
            + ")"
        )
        read_key = str(uuid.uuid4())
        try:
            chunk = client.eval(
                target_id,
                expression,
                idempotency_key=read_key,
            )
        except BrowserError as error:
            if error.code != "UNKNOWN_RESULT":
                raise
            chunk = client.eval(
                target_id,
                expression,
                idempotency_key=read_key,
            )
        if not isinstance(chunk, str):
            raise OperationError("pdf_download_invalid", "browser PDF chunk is invalid")
        chunks.append(chunk)
    client.eval(target_id, "delete window[" + json.dumps(key) + "]")
    raw = base64.b64decode("".join(chunks), validate=True)
    if (
        len(raw) != size
        or hashlib.sha256(raw).hexdigest() != expected_sha
        or not raw.startswith(b"%PDF-")
    ):
        raise OperationError("pdf_download_invalid", "browser PDF integrity check failed")
    return raw


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
    for candidate in candidates:
        if urlsplit(candidate).hostname != provider.host:
            continue
        remaining = int(overall_deadline - time.monotonic())
        if remaining < 5:
            break
        try:
            raw = fetch_pdf_bytes(
                client,
                session["targetId"],
                candidate,
                provider,
                timeout_seconds=min(60, remaining),
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
        except (BrowserError, OperationError, ValueError):
            continue
    return save_stage(
        store,
        session,
        "pdf_download_failed",
        source=safe_url(session["requestedArticle"]),
        reason="authorized PDF response was not usable",
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
        autofill = (
            try_submit_autofilled_login(store, session, client)
            if allow_autofill
            else "already_attempted"
        )
        if autofill == "submitted":
            time.sleep(2)
            return observe_and_continue(
                store,
                session,
                client,
                provider,
                output,
                after_user_login=after_user_login,
                allow_autofill=False,
            )
        reason = "browser is at the school or institution login flow"
        if autofill == "consent_required":
            reason = "login form requires the user to confirm a required choice"
        elif autofill in {"submit_unknown", "submit_failed"}:
            reason = "automatic login submission requires user verification"
        elif autofill == "already_attempted":
            reason = "the login form was already submitted and still requires user action"
        return set_handoff(
            store,
            session,
            client,
            stage="user_login_required",
            reason=reason,
            instruction=(
                "请在已打开的浏览器页面完成学校/CARSI/OpenAthens 登录。"
                "完成后回复“已登录”，再继续原下载任务。"
            ),
        )
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
        return set_handoff(
            store,
            session,
            client,
            stage="publisher_verification",
            reason="publisher security verification is required",
            instruction="请在已打开的出版社页面完成验证，然后回复“已完成”。",
        )
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
        return set_handoff(
            store,
            session,
            client,
            stage="user_login_required",
            reason="publisher page still requires institutional sign-in",
            instruction=(
                "请在已打开的出版社页面完成学校/CARSI/OpenAthens 登录。"
                "完成后回复“已登录”，再继续原下载任务。"
            ),
        )
    if after_user_login:
        return save_stage(
            store,
            session,
            "access_unavailable",
            reason="publisher page is reachable but institutional PDF access is absent",
            page=public_page_identity(state_data, session["doi"], provider),
        )
    autofill = (
        try_submit_autofilled_login(store, session, client)
        if allow_autofill
        else "already_attempted"
    )
    if autofill == "submitted":
        time.sleep(2)
        return observe_and_continue(
            store,
            session,
            client,
            provider,
            output,
            after_user_login=False,
            allow_autofill=False,
        )
    reason = "publisher page does not expose an institutional PDF"
    if autofill == "consent_required":
        reason = "publisher login form requires the user to confirm a required choice"
    elif autofill in {"submit_unknown", "submit_failed"}:
        reason = "automatic login submission requires user verification"
    return set_handoff(
        store,
        session,
        client,
        stage="user_login_required",
        reason=reason,
        instruction=(
            "请在已打开的出版社页面选择 Institutional Sign In 或学校/CARSI 登录。"
            "登录完成后回复“已登录”，再继续原下载任务。"
        ),
    )


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
        "--browser", choices=("auto", "edge", "chrome"), default="auto"
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
