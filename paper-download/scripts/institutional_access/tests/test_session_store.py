from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from institutional_access.session_store import (
    FileSessionStore,
    SessionError,
    session_lock,
    validate_session_id,
)


class SessionStoreTests(unittest.TestCase):
    def test_file_backend_round_trip_and_delete(self):
        with tempfile.TemporaryDirectory() as root:
            store = FileSessionStore(Path(root))
            value = {"taskId": "task_demo", "taskToken": "not-exported"}
            store.write("demo_session", value)
            self.assertEqual(store.read("demo_session"), value)
            store.delete("demo_session")
            self.assertIsNone(store.read("demo_session"))

    def test_session_id_rejects_paths_and_long_values(self):
        for value in ("", "../demo", "a/b", "x" * 65):
            with self.subTest(value=value):
                with self.assertRaises(SessionError):
                    validate_session_id(value)

    def test_test_backend_requires_explicit_test_mode(self):
        from institutional_access import session_store

        old_state = os.environ.get("PAPER_DOWNLOAD_TEST_STATE_DIR")
        old_mode = os.environ.get("PAPER_DOWNLOAD_TEST_MODE")
        try:
            os.environ["PAPER_DOWNLOAD_TEST_STATE_DIR"] = tempfile.gettempdir()
            os.environ.pop("PAPER_DOWNLOAD_TEST_MODE", None)
            with self.assertRaises(SessionError):
                session_store.get_session_store()
        finally:
            if old_state is None:
                os.environ.pop("PAPER_DOWNLOAD_TEST_STATE_DIR", None)
            else:
                os.environ["PAPER_DOWNLOAD_TEST_STATE_DIR"] = old_state
            if old_mode is None:
                os.environ.pop("PAPER_DOWNLOAD_TEST_MODE", None)
            else:
                os.environ["PAPER_DOWNLOAD_TEST_MODE"] = old_mode

    def test_same_session_cannot_run_concurrently(self):
        with tempfile.TemporaryDirectory() as root:
            old = os.environ.get("PAPER_DOWNLOAD_TEST_STATE_DIR")
            try:
                os.environ["PAPER_DOWNLOAD_TEST_STATE_DIR"] = root
                with session_lock("demo_lock"):
                    with self.assertRaises(SessionError):
                        with session_lock("demo_lock"):
                            pass
            finally:
                if old is None:
                    os.environ.pop("PAPER_DOWNLOAD_TEST_STATE_DIR", None)
                else:
                    os.environ["PAPER_DOWNLOAD_TEST_STATE_DIR"] = old


if __name__ == "__main__":
    unittest.main()
