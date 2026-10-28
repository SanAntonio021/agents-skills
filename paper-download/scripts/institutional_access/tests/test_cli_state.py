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
    continue_browser_access,
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

    def access(self, _target_id, *, allow_autofill=True):
        self.page_reads += 1
        if self._state.get("challenge"):
            return {"state": "challenge", "failureCode": "challenge", "handoffRequired": False, "interactionRequired": True}
        if self._state.get("strong_auth"):
            return {"state": "user_handoff_required", "failureCode": "user_handoff_required", "handoffRequired": True}
        return {"state": "auth_required", "failureCode": "auth_required", "handoffRequired": False, "interactionRequired": True}

    def snapshot(self, _target_id):
        return {"nodes": []}


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

    def test_school_page_delegates_to_web_access(self):
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
            self.assertEqual(client.handoff_calls, [])
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

    def test_publisher_challenge_delegates_without_user_handoff(self):
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
            self.assertEqual(client.handoff_calls, [])

    def test_same_host_login_still_requires_access_readback(self):
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
            self.assertEqual(client.handoff_calls, [])

    def test_only_strong_authentication_enters_real_handoff(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            client = _FakeClient(url="https://idp.example.edu/login", state={"strong_auth": True})
            result = continue_browser_access(store, session, client, allow_autofill=True)
            self.assertTrue(result["user_action_required"])
            self.assertEqual(client.handoff_calls, ["target"])
            self.assertEqual(result["failure_code"], "user_handoff_required")

    def test_routine_login_stays_active_for_web_access(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            session = self.session()
            client = _FakeClient(url="https://idp.example.edu/login")
            result = continue_browser_access(store, session, client, allow_autofill=True)
            self.assertFalse(result["user_action_required"])
            self.assertTrue(result["browser_interaction_required"])
            self.assertEqual(client.handoff_calls, [])
            self.assertEqual(client._task, "active")

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
