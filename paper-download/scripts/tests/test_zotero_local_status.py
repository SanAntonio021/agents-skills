from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import zotero_local_status as status


@contextlib.contextmanager
def fixture(mode="ok"):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, value, headers=None):
            body = (value if isinstance(value, str) else json.dumps(value)).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            requests.append(("GET", self.path, dict(self.headers), None))
            if mode == "unrelated":
                return self.respond(200, "Other local service")
            if mode == "redirect":
                return self.respond(302, "", {"Location": "/should-not-be-followed"})
            if self.path == "/api/":
                headers = {"X-Zotero-Version": "10.0.6", "Zotero-API-Version": "3"}
                return self.respond(200, "Nothing to see here", headers)
            if self.path == "/api/schema":
                value = "not-json" if mode == "invalid-schema" else {"version": 44, "itemTypes": []}
                if mode == "wrong-schema":
                    value = {"version": 44, "itemTypes": "not-a-list"}
                return self.respond(200, value)
            if self.path == "/connector/ping":
                if mode == "no-connector":
                    return self.respond(404, "Missing connector")
                return self.respond(200, "<html>Zotero is running</html>")
            return self.respond(404, "Unrecognized route")

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
            requests.append(("POST", self.path, dict(self.headers), body))
            if self.path != "/debug-bridge/execute":
                return self.respond(405, "Writes forbidden")
            if mode in {"no-bridge", "bad-auth", "bridge-error"}:
                code = {"no-bridge": 404, "bad-auth": 401, "bridge-error": 500}[mode]
                return self.respond(code, self.headers.get("Authorization", ""))
            value = {"version": "10.0.6", "libraryID": 1, "importFromFileAvailable": True}
            if mode == "version-mismatch":
                value["version"] = "9.0.6"
            if mode == "no-import":
                value["importFromFileAvailable"] = False
            if mode == "wrapped-bridge":
                value = {"result": json.dumps(value)}
            return self.respond(201, value)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class ZoteroStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.process = mock.patch.object(status, "process_status", return_value={
            "state": "unknown", "pids": [], "executable_paths": []})
        self.process_mock = self.process.start()
        self.addCleanup(self.process.stop)

    def profile(self, name="default", token="fixture-secret", enabled=True, port=None):
        profile = self.root / name
        profile.mkdir(exist_ok=True)
        values = {status.API_PREF: enabled}
        if token is not None:
            values[status.TOKEN_PREF] = token
        if port is not None:
            values[status.PORT_PREF] = port
        text = "\n".join(f'user_pref({json.dumps(key)}, {json.dumps(value)});'
                         for key, value in values.items())
        (profile / "prefs.js").write_text(text, encoding="utf-8")
        return profile

    def ini(self, sections):
        text = "\n".join(f"[{name}]\n" + "\n".join(f"{k}={v}" for k, v in values.items())
                         for name, values in sections.items())
        (self.root / "profiles.ini").write_text(text, encoding="utf-8")

    def probe(self, mode="ok", **options):
        profile = self.profile(**options)
        with fixture(mode) as (base, requests):
            result = status.status_payload(str(profile), base, timeout=1)
        return result, requests

    def test_default_is_only_a_candidate(self):
        self.assertEqual(status.select_base_url(None, {}),
                         ("http://127.0.0.1:23119", "default_candidate"))

    def test_custom_port_and_override_precedence(self):
        preferences = {status.PORT_PREF: 12345}
        self.assertEqual(status.select_base_url(None, preferences),
                         ("http://127.0.0.1:12345", "profile_port"))
        os.environ["ZOTERO_LOCAL_BASE_URL"] = "http://127.0.0.1:23456"
        self.assertEqual(status.select_base_url(None, preferences)[1], "environment")
        self.assertEqual(status.select_base_url("http://127.0.0.1:34567", preferences),
                         ("http://127.0.0.1:34567", "argument"))

    def test_invalid_explicit_configuration_does_not_fall_back(self):
        for port in (0, True, "23119", 65536, None):
            with self.subTest(port=port), self.assertRaises(status.CheckError):
                status.select_base_url(None, {status.PORT_PREF: port})
        os.environ["ZOTERO_LOCAL_BASE_URL"] = ""
        with self.assertRaises(status.CheckError):
            status.select_base_url(None, {})

    def test_windows_standard_profile_roots(self):
        os.environ["APPDATA"] = str(self.root)
        with mock.patch.object(status.platform, "system", return_value="Windows"):
            self.assertEqual(status.profile_roots(),
                             [self.root / "Zotero/Zotero", self.root / "Zotero"])

    def test_single_and_default_profile_selection(self):
        first = self.profile("first")
        second = self.profile("second")
        self.ini({"Profile0": {"Path": "first", "Default": "1"},
                  "Profile1": {"Path": "second"}})
        with mock.patch.object(status, "profile_roots", return_value=[self.root]):
            self.assertEqual(status.resolve_profile(None)[0], first)
            self.assertEqual(status.resolve_profile(str(second))[0], second)

    def test_ambiguous_profile_blocks_network(self):
        self.profile("first")
        self.profile("second")
        self.ini({"Profile0": {"Path": "first"}, "Profile1": {"Path": "second"}})
        with mock.patch.object(status, "profile_roots", return_value=[self.root]), \
                mock.patch.object(status, "request") as request:
            result = status.status_payload()
        self.assertEqual(result["profile_error"], "profile_ambiguous")
        request.assert_not_called()

    def test_conflicting_install_defaults_are_ambiguous(self):
        self.profile("first")
        self.profile("second")
        self.ini({"Profile0": {"Path": "first"}, "Profile1": {"Path": "second"},
                  "InstallA": {"Default": "first"}, "InstallB": {"Default": "second"}})
        with mock.patch.object(status, "profile_roots", return_value=[self.root]):
            with self.assertRaisesRegex(status.CheckError, "profile_ambiguous"):
                status.resolve_profile(None)

    def test_missing_profile_can_still_confirm_reads_without_bridge(self):
        with mock.patch.object(status, "profile_roots", return_value=[]), \
                fixture() as (base, requests):
            result = status.status_payload(base_url=base, timeout=1)
        self.assertTrue(result["read_only_ready"])
        self.assertEqual(result["profile_error"], "profile_not_found")
        self.assertEqual(result["debug_bridge_error"], "bridge_credential_missing")
        self.assertEqual(len(requests), 3)

    def test_invalid_explicit_profile_does_not_use_default(self):
        with mock.patch.object(status, "request") as request:
            result = status.status_payload(str(self.root / "missing"))
        self.assertEqual(result["error"], "explicit_profile_unreadable")
        request.assert_not_called()

    def test_complete_probe_is_fixed_and_read_only(self):
        result, requests = self.probe()
        self.assertTrue(result["entry_verified"])
        self.assertTrue(result["debug_bridge_available"])
        self.assertEqual(result["native_library_id"], 1)
        self.assertTrue(result["import_from_file_available"])
        self.assertEqual([(r[0], r[1]) for r in requests], [
            ("GET", "/api/"), ("GET", "/api/schema"), ("GET", "/connector/ping"),
            ("POST", "/debug-bridge/execute")])
        self.assertEqual(requests[-1][2]["Content-Type"], "text/plain")
        self.assertEqual(requests[-1][3], status.BRIDGE_QUERY)
        self.assertNotIn("fixture-secret", json.dumps(result))

    def test_custom_profile_port_is_used_without_override(self):
        with fixture() as (base, requests):
            profile = self.profile(port=int(base.rsplit(":", 1)[1]))
            result = status.status_payload(str(profile), timeout=1)
        self.assertEqual(result["base_url"], base)
        self.assertEqual(result["base_url_source"], "profile_port")
        self.assertTrue(result["entry_verified"])

    def test_other_service_http_200_is_not_zotero(self):
        result, requests = self.probe("unrelated")
        self.assertTrue(result["api_running"])
        self.assertFalse(result["api_verified"])
        self.assertFalse(result["read_only_ready"])
        self.assertEqual(len(requests), 3)

    def test_invalid_schema_blocks_credentials(self):
        for mode in ("invalid-schema", "wrong-schema"):
            with self.subTest(mode=mode):
                result, requests = self.probe(mode)
                self.assertTrue(result["api_verified"])
                self.assertFalse(result["schema_verified"])
                self.assertEqual(len(requests), 3)

    def test_connector_failure_preserves_read_only_and_bridge(self):
        result, requests = self.probe("no-connector")
        self.assertTrue(result["read_only_ready"])
        self.assertFalse(result["entry_verified"])
        self.assertFalse(result["connector_verified"])
        self.assertTrue(result["debug_bridge_available"])

    def test_missing_or_unauthorized_bridge_preserves_reads(self):
        for mode, error in (("no-bridge", "bridge_not_available"),
                            ("bad-auth", "bridge_authentication_failed"),
                            ("bridge-error", "http_error")):
            with self.subTest(mode=mode):
                result, _ = self.probe(mode)
                self.assertTrue(result["read_only_ready"])
                self.assertFalse(result["debug_bridge_available"])
                self.assertEqual(result["debug_bridge_error"], error)
                self.assertNotIn("fixture-secret", json.dumps(result))

    def test_absent_or_malformed_credential_not_sent(self):
        for token in (None, "", "bad\nheader", "non-ascii-\u00e9"):
            with self.subTest(token=token):
                result, requests = self.probe(token=token)
                self.assertTrue(result["read_only_ready"])
                self.assertFalse(result["debug_bridge_available"])
                self.assertEqual(len(requests), 3)

    def test_disabled_api_pref_does_not_change_or_send_credentials(self):
        profile = self.profile(enabled=False)
        before = (profile / "prefs.js").read_bytes()
        with fixture() as (base, requests):
            result = status.status_payload(str(profile), base, timeout=1)
        self.assertEqual(result["error"], "local_api_disabled")
        self.assertFalse(result["read_only_ready"])
        self.assertEqual(len(requests), 3)
        self.assertEqual((profile / "prefs.js").read_bytes(), before)

    def test_wrapped_bridge_and_missing_import_function(self):
        result, _ = self.probe("wrapped-bridge")
        self.assertTrue(result["debug_bridge_available"])
        result, _ = self.probe("no-import")
        self.assertTrue(result["debug_bridge_available"])
        self.assertFalse(result["import_from_file_available"])

    def test_mismatched_bridge_version_is_rejected(self):
        result, _ = self.probe("version-mismatch")
        self.assertFalse(result["debug_bridge_available"])
        self.assertEqual(result["debug_bridge_error"], "bridge_version_mismatch")

    def test_proxy_environment_is_ignored(self):
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1",
                                         "http_proxy": "http://127.0.0.1:1",
                                         "ALL_PROXY": "http://127.0.0.1:1"}):
            result, _ = self.probe()
        self.assertTrue(result["entry_verified"])

    def test_redirects_are_not_followed(self):
        result, requests = self.probe("redirect")
        self.assertFalse(result["read_only_ready"])
        self.assertEqual(result["api_error"], "redirect_blocked")
        self.assertEqual(len(requests), 3)
        self.assertNotIn("/should-not-be-followed", [r[1] for r in requests])

    def test_non_loopback_and_credential_urls_rejected(self):
        for value in ("https://127.0.0.1:23119", "http://example.com", "http://192.168.0.1",
                      "http://user:secret@127.0.0.1", "http://localhost/path",
                      "http://127.0.0.1?secret=1", "http://127.0.0.1#fragment",
                      "http://127.0.0.1:99999"):
            with self.subTest(value=value), self.assertRaises(status.CheckError):
                status.validate_base_url(value)
        self.assertEqual(status.validate_base_url("http://[::1]:23119/"), "http://[::1]:23119")

    def test_failure_uses_only_selected_origin_without_retry(self):
        profile = self.profile(port=54321)
        with mock.patch.object(status, "request", return_value={
                "status": None, "error": "connection_failed"}) as request:
            result = status.status_payload(str(profile), "http://127.0.0.1:12345")
        self.assertEqual(request.call_count, 3)
        self.assertEqual({call.args[1] for call in request.call_args_list}, {"http://127.0.0.1:12345"})
        self.assertFalse(result["read_only_ready"])

    def test_json_cli_redacts_http_error_and_returns_read_capability(self):
        profile = self.profile()
        output = io.StringIO()
        with fixture("bad-auth") as (base, _), contextlib.redirect_stdout(output):
            code = status.main(["status", "--json", "--profile", str(profile), "--base-url", base])
        self.assertEqual(code, 0)
        self.assertNotIn("fixture-secret", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["debug_bridge_status"], 401)

    def test_process_inspection_is_read_only_and_hidden(self):
        self.process.stop()
        for stdout, expected in (("", "not_running"),
                                 ('[{"ProcessId": 123, "ExecutablePath": "C:/Zotero/zotero.exe"}]',
                                  "running")):
            with self.subTest(state=expected), \
                    mock.patch.object(status.platform, "system", return_value="Windows"), \
                    mock.patch.object(status.subprocess, "run", return_value=mock.Mock(
                        stdout=stdout)) as run:
                result = status.process_status()
                self.assertEqual(result["state"], expected)
                arguments = run.call_args.args[0]
                self.assertIn("Get-CimInstance", arguments[-1])
                self.assertNotIn("Stop-Process", arguments[-1])
                self.assertNotIn("Start-Process", arguments[-1])
                self.assertTrue(run.call_args.kwargs["creationflags"])

    def test_unresponsive_api_keeps_actual_process_state(self):
        profile = self.profile()
        for state in ("running", "not_running", "unknown"):
            self.process_mock.return_value = {"state": state, "pids": [], "executable_paths": []}
            with self.subTest(state=state), mock.patch.object(status, "request", return_value={
                    "status": None, "error": "connection_failed"}):
                result = status.status_payload(str(profile))
                self.assertFalse(result["read_only_ready"])
                self.assertEqual(result["process"]["state"], state)

    def test_unexpected_exception_cannot_print_secrets(self):
        output = io.StringIO()
        with mock.patch.object(status, "status_payload", side_effect=RuntimeError("fixture-secret")), \
                contextlib.redirect_stdout(output):
            code = status.main(["status", "--json"])
        self.assertEqual(code, 1)
        self.assertNotIn("fixture-secret", output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["error"], "status_check_failed")


if __name__ == "__main__":
    unittest.main()
