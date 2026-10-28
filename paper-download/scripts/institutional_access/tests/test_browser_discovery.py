from __future__ import annotations

import json
import hashlib
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

    def test_preflight_defaults_to_existing_edge_and_requires_control_probe(self):
        checker = Path("C:/test/web-access/scripts/check-deps.mjs")
        ready_report = {
            "ok": True,
            "status": "ready",
            "ready": True,
            "browserMode": "existing",
            "protocolVersion": 2,
            "brokerVersion": "managed-edge.1",
            "results": [
                {
                    "ready": True,
                    "proxy": {"url": "http://127.0.0.1:3456", "protocolVersion": 2},
                    "browser": {"id": "edge", "cdpPort": 14151},
                    "controlProbe": {"passed": True},
                    "instanceId": "0123456789abcdef01234567",
                }
            ],
        }
        with patch.dict(os.environ, {"PAPER_DOWNLOAD_BROWSER_MODE": "existing"}), \
             patch("institutional_access.browser.shutil.which", return_value="node.exe"), \
             patch("institutional_access.browser.discover_web_access_checker", return_value=checker), \
             patch("institutional_access.browser.subprocess.run", side_effect=[
                 SimpleNamespace(returncode=0, stdout="v22.0.0\n", stderr=""),
                 SimpleNamespace(returncode=0, stdout=json.dumps(ready_report), stderr=""),
             ]) as run:
            info = check_web_access("edge")
        command = run.call_args_list[1].args[0]
        self.assertEqual(
            command[-5:],
            ["--browser", "edge", "--mode", "existing", "--json"],
        )
        self.assertEqual(info.mode, "existing")
        self.assertEqual(info.instance_id, "0123456789abcdef01234567")
        self.assertEqual(info.cdp_port, 14151)

    def test_preflight_rejects_missing_control_probe(self):
        checker = Path("C:/test/web-access/scripts/check-deps.mjs")
        report = {
            "ok": True,
            "status": "ready",
            "ready": True,
            "browserMode": "existing",
            "protocolVersion": 2,
            "results": [
                {
                    "ready": True,
                    "proxy": {"url": "http://127.0.0.1:3456", "protocolVersion": 2},
                    "browser": {"id": "edge"},
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

    def test_download_returns_bytes_and_verifies_broker_metadata(self):
        raw = b"%PDF-1.7\nfixture"
        digest = hashlib.sha256(raw).hexdigest()

        class Response(io.BytesIO):
            status = 200
            headers = {
                "X-Download-Sha256": digest,
                "X-Download-Bytes": str(len(raw)),
                "X-Download-Is-Pdf": "true",
                "X-Download-Final-Url": "https%3A%2F%2Fpublisher.test%2Fpaper.pdf",
            }

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        client = BrowserClient("http://127.0.0.1:3456", task_token="test-token")
        with patch.object(client.opener, "open", return_value=Response(raw)) as opened:
            body, metadata = client.download(
                "target-1",
                "https://publisher.test/paper.pdf",
                allowed_hosts=["publisher.test"],
                timeout_ms=5000,
                max_bytes=1024,
                idempotency_key="download-key",
            )
        self.assertEqual(body, raw)
        self.assertEqual(metadata["sha256"], digest)
        self.assertEqual(metadata["bytes"], len(raw))
        self.assertTrue(metadata["is_pdf"])
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Idempotency-key"), "download-key")
        self.assertEqual(
            json.loads(request.data),
            {
                "url": "https://publisher.test/paper.pdf",
                "timeoutMs": 5000,
                "allowedHosts": ["publisher.test"],
                "maxBytes": 1024,
            },
        )

    def test_download_rejects_non_pdf_and_incomplete_payloads(self):
        cases = [
            (b"<html>login</html>", {"X-Download-Is-Pdf": "false"}, "not_pdf"),
            (b"%PDF-1.7\nfixture", {"X-Download-Is-Pdf": "true", "X-Download-Bytes": "1"}, "incomplete"),
            (b"%PDF-1.7\nfixture", {"X-Download-Is-Pdf": "true", "X-Download-Bytes": "16", "X-Download-Sha256": "0" * 64}, "incomplete"),
        ]
        for raw, headers, expected in cases:
            with self.subTest(expected=expected, headers=headers):
                complete_headers = {
                    "X-Download-Is-Pdf": "true",
                    "X-Download-Bytes": str(len(raw)),
                    "X-Download-Sha256": hashlib.sha256(raw).hexdigest(),
                    **headers,
                }

                class Response(io.BytesIO):
                    status = 200

                    def __init__(self, data):
                        super().__init__(data)
                        self.headers = complete_headers

                    def __enter__(self):
                        return self

                    def __exit__(self, *_):
                        self.close()

                client = BrowserClient("http://127.0.0.1:3456", task_token="test-token")
                with patch.object(client.opener, "open", return_value=Response(raw)):
                    with self.assertRaises(BrowserError) as raised:
                        client.download("target-1", "https://publisher.test/paper.pdf")
                self.assertEqual(raised.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
