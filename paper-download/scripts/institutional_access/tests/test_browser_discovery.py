from __future__ import annotations

import json
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from institutional_access.browser import (
    BrowserClient,
    BrowserError,
    check_web_access,
    discover_web_access_checker,
)


class BrowserDiscoveryTests(unittest.TestCase):
    def test_environment_override(self):
        with tempfile.TemporaryDirectory() as root:
            checker = Path(root) / "check-deps.mjs"
            checker.write_text("// test", encoding="utf-8")
            old = os.environ.get("PAPER_DOWNLOAD_WEB_ACCESS_CHECKER")
            try:
                os.environ["PAPER_DOWNLOAD_WEB_ACCESS_CHECKER"] = str(checker)
                self.assertEqual(discover_web_access_checker(), checker)
            finally:
                if old is None:
                    os.environ.pop("PAPER_DOWNLOAD_WEB_ACCESS_CHECKER", None)
                else:
                    os.environ["PAPER_DOWNLOAD_WEB_ACCESS_CHECKER"] = old

    def test_preflight_forces_managed_edge_and_requires_control_probe(self):
        checker = Path("C:/test/web-access/scripts/check-deps.mjs")
        ready_report = {
            "ok": True,
            "status": "ready",
            "ready": True,
            "browserMode": "managed",
            "protocolVersion": 2,
            "brokerVersion": "managed-edge.1",
            "results": [
                {
                    "ready": True,
                    "proxy": {"url": "http://127.0.0.1:3456", "protocolVersion": 2},
                    "browser": {"id": "edge"},
                    "managedBrowser": {"ready": True},
                    "controlProbe": {"passed": True},
                    "instanceId": "0123456789abcdef01234567",
                }
            ],
        }
        with patch("institutional_access.browser.shutil.which", return_value="node.exe"), \
             patch("institutional_access.browser.discover_web_access_checker", return_value=checker), \
             patch("institutional_access.browser.subprocess.run", side_effect=[
                 SimpleNamespace(returncode=0, stdout="v22.0.0\n", stderr=""),
                 SimpleNamespace(returncode=0, stdout=json.dumps(ready_report), stderr=""),
             ]) as run:
            info = check_web_access("edge")
        command = run.call_args_list[1].args[0]
        self.assertEqual(
            command[-5:],
            ["--browser", "edge", "--mode", "managed", "--json"],
        )
        self.assertEqual(info.mode, "managed")
        self.assertEqual(info.instance_id, "0123456789abcdef01234567")

    def test_preflight_rejects_missing_control_probe(self):
        checker = Path("C:/test/web-access/scripts/check-deps.mjs")
        report = {
            "ok": True,
            "status": "ready",
            "ready": True,
            "browserMode": "managed",
            "protocolVersion": 2,
            "results": [
                {
                    "ready": True,
                    "proxy": {"url": "http://127.0.0.1:3456", "protocolVersion": 2},
                    "browser": {"id": "edge"},
                    "managedBrowser": {"ready": True},
                    "controlProbe": {"passed": False},
                }
            ],
        }
        with patch("institutional_access.browser.shutil.which", return_value="node.exe"), \
             patch("institutional_access.browser.discover_web_access_checker", return_value=checker), \
             patch("institutional_access.browser.subprocess.run", side_effect=[
                 SimpleNamespace(returncode=0, stdout="v22.0.0\n", stderr=""),
                 SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr=""),
             ]):
            with self.assertRaisesRegex(BrowserError, "no ready browser"):
                check_web_access("edge")

    def test_proxy_string_error_code_is_preserved(self):
        client = BrowserClient("http://127.0.0.1:3456", task_token="test-token")
        error = HTTPError(
            "http://127.0.0.1:3456/v2/tabs",
            504,
            "Gateway Timeout",
            {},
            io.BytesIO(
                json.dumps(
                    {
                        "error": "UNKNOWN_RESULT",
                        "code": "UNKNOWN_RESULT",
                    }
                ).encode("utf-8")
            ),
        )
        with patch.object(client.opener, "open", side_effect=error):
            with self.assertRaises(BrowserError) as raised:
                client.create_tab("https://example.com")
        self.assertEqual(raised.exception.code, "UNKNOWN_RESULT")


if __name__ == "__main__":
    unittest.main()
