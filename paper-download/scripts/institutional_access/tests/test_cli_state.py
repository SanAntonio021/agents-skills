from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from institutional_access.browser import BrowserError
from institutional_access.cli import (
    observe_and_continue,
    reconcile_created_tab,
    session_summary,
    try_submit_autofilled_login,
)
from institutional_access.providers import IEEE
from institutional_access.session_store import FileSessionStore


class _FakeClient:
    def __init__(self, *, task="active", url="", state=None):
        self._task = task
        self._url = url
        self._state = state or {}
        self.handoff_calls = []
        self.page_reads = 0

    def task(self):
        return {"state": self._task}

    def tab(self, _target_id):
        return {"url": self._url, "title": "Test"}

    def handoff(self, target_id):
        self.handoff_calls.append(target_id)
        self._task = "handoff"
        return {"state": "handoff"}

    def wait_load(self, _target_id, timeout_ms=15000):
        return None

    def eval(self, _target_id, _expression, **_kwargs):
        self.page_reads += 1
        return self._state

    def snapshot(self, _target_id):
        return {"nodes": []}


class _AutofillClient(_FakeClient):
    def eval(self, _target_id, expression, **_kwargs):
        self.page_reads += 1
        if "const submitRequested = false;" in expression:
            return {"status": "ready", "host": "idp.example.edu", "path": "/login"}
        if "const submitRequested = true;" in expression:
            return {
                "status": "submitted",
                "host": "idp.example.edu",
                "path": "/login",
            }
        return self._state


class _UnknownAutofillClient(_AutofillClient):
    def eval(self, target_id, expression, **kwargs):
        if "const submitRequested = true;" in expression:
            self.page_reads += 1
            raise BrowserError("UNKNOWN_RESULT", "unknown")
        return super().eval(target_id, expression, **kwargs)


class _UnknownCreateClient:
    def __init__(self):
        self.navigate_calls = 0
        self._url = ""

    def tabs(self):
        return [{"targetId": "target", "url": self._url}]

    def tab(self, _target_id):
        return {"targetId": "target", "url": self._url}

    def navigate(self, _target_id, url):
        self.navigate_calls += 1
        self._url = url
        return {"ok": True}


class CliStateTests(unittest.TestCase):
    def session(self):
        return {
            "schemaVersion": 1,
            "sessionId": "test",
            "provider": "ieee",
            "requestedArticle": "https://ieeexplore.ieee.org/document/123/",
            "doi": "10.1109/test.2026.1",
            "browser": "edge",
            "proxyUrl": "http://127.0.0.1:3456",
            "taskId": "task",
            "taskToken": "secret-not-output",
            "targetId": "target",
            "stage": "starting",
            "createdAt": "now",
            "updatedAt": "now",
        }

    def test_school_page_enters_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            store.write("test", session)
            client = _FakeClient(url="https://idp.example.edu/login")
            result = observe_and_continue(
                store,
                session,
                client,
                IEEE,
                Path(root) / "paper.pdf",
                after_user_login=False,
            )
            self.assertEqual(result["stage"], "user_login_required")
            self.assertEqual(client.handoff_calls, ["target"])
            self.assertEqual(store.read("test")["stage"], "user_login_required")

    def test_unknown_create_reconciles_one_owned_blank_tab(self):
        client = _UnknownCreateClient()
        requested = "https://ieeexplore.ieee.org/document/123/"
        result = reconcile_created_tab(client, requested, timeout_seconds=10)
        self.assertEqual(result["targetId"], "target")
        self.assertEqual(result["url"], requested)
        self.assertEqual(client.navigate_calls, 1)

    def test_handoff_never_reads_page(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            session["stage"] = "user_login_required"
            store.write("test", session)
            client = _FakeClient(task="handoff", url="https://idp.example.edu/login")
            result = observe_and_continue(
                store,
                session,
                client,
                IEEE,
                Path(root) / "paper.pdf",
                after_user_login=False,
            )
            self.assertEqual(result["stage"], "user_login_required")
            self.assertEqual(client.page_reads, 0)

    def test_user_return_without_access_is_not_success(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            store.write("test", session)
            state = {
                "readyState": "complete",
                "host": IEEE.host,
                "path": "/document/123/",
                "href": session["requestedArticle"],
                "title": "Article",
                "contentType": "text/html",
                "text": "",
                "meta": {"citation_doi": session["doi"]},
                "links": [],
                "embeds": [],
                "challenge": False,
                "accessSignals": [],
                "loginSignals": [],
                "denialSignals": ["You do not have access"],
                "openAccessSignals": [],
            }
            client = _FakeClient(url=session["requestedArticle"], state=state)
            result = observe_and_continue(
                store,
                session,
                client,
                IEEE,
                Path(root) / "paper.pdf",
                after_user_login=True,
            )
            self.assertEqual(result["stage"], "access_unavailable")
            self.assertFalse((Path(root) / "paper.pdf").exists())

    def test_publisher_challenge_enters_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            store.write("test", session)
            state = {
                "readyState": "complete",
                "host": IEEE.host,
                "path": "/document/123/",
                "href": session["requestedArticle"],
                "title": "Security check",
                "contentType": "text/html",
                "text": "",
                "meta": {"citation_doi": session["doi"]},
                "links": [],
                "embeds": [],
                "challenge": True,
                "accessSignals": [],
                "loginSignals": [],
                "denialSignals": [],
                "openAccessSignals": [],
            }
            client = _FakeClient(url=session["requestedArticle"], state=state)
            result = observe_and_continue(
                store,
                session,
                client,
                IEEE,
                Path(root) / "paper.pdf",
                after_user_login=False,
            )
            self.assertEqual(result["stage"], "publisher_verification")
            self.assertEqual(client.handoff_calls, ["target"])

    def test_same_host_login_after_user_claim_returns_to_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            store.write("test", session)
            state = {
                "readyState": "complete",
                "host": IEEE.host,
                "path": "/document/123/",
                "href": session["requestedArticle"],
                "title": "Article",
                "contentType": "text/html",
                "text": "",
                "meta": {"citation_doi": session["doi"]},
                "links": [],
                "embeds": [],
                "challenge": False,
                "accessSignals": [],
                "loginSignals": ["Institutional Sign In"],
                "denialSignals": ["Sign in to access"],
                "openAccessSignals": [],
            }
            client = _FakeClient(url=session["requestedArticle"], state=state)
            result = observe_and_continue(
                store,
                session,
                client,
                IEEE,
                Path(root) / "paper.pdf",
                after_user_login=True,
            )
            self.assertEqual(result["stage"], "user_login_required")
            self.assertEqual(client.handoff_calls, ["target"])

    def test_autofilled_login_submits_once_but_still_needs_access_readback(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            store.write("test", session)
            client = _AutofillClient(url="https://idp.example.edu/login")
            with patch("institutional_access.cli.time.sleep"):
                result = observe_and_continue(
                    store,
                    session,
                    client,
                    IEEE,
                    Path(root) / "paper.pdf",
                    after_user_login=False,
                )
            saved = store.read("test")
            self.assertEqual(result["stage"], "user_login_required")
            self.assertTrue(saved["loginSubmitAttempted"])
            self.assertEqual(saved["loginSubmitResult"], "submitted")
            self.assertEqual(client.handoff_calls, ["target"])

    def test_unknown_login_submit_is_never_replayed(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            store.write("test", session)
            client = _UnknownAutofillClient(url="https://idp.example.edu/login")
            result = try_submit_autofilled_login(store, session, client)
            self.assertEqual(result, "submit_unknown")
            self.assertTrue(store.read("test")["loginSubmitAttempted"])
            self.assertEqual(
                try_submit_autofilled_login(
                    store,
                    store.read("test"),
                    client,
                ),
                "already_attempted",
            )
            self.assertEqual(client.page_reads, 2)

    def test_status_summary_excludes_task_secrets_and_query_parameters(self):
        session = self.session()
        session["requestedArticle"] = (
            "https://ieeexplore.ieee.org/document/123/?token=secret-query"
        )
        result = session_summary(session)
        serialized = str(result)
        self.assertEqual(
            result["article"],
            "https://ieeexplore.ieee.org/document/123/",
        )
        for secret in ("secret-not-output", "task", "target", "3456", "secret-query"):
            self.assertNotIn(secret, serialized)


if __name__ == "__main__":
    unittest.main()
