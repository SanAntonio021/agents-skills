from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import office_native_gate as native_gate  # noqa: E402


class FakeComRuntime:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.uninitialize_calls = 0

    def CoInitialize(self) -> None:
        self.initialize_calls += 1

    def CoUninitialize(self) -> None:
        self.uninitialize_calls += 1


class FakeDocument:
    def __init__(self, documents: "FakeDocuments", *, pages: int = 1) -> None:
        self.documents = documents
        self.pages = pages
        self.repaginate_calls = 0
        self.statistics_calls: list[int] = []
        self.close_calls: list[tuple[object, ...]] = []
        self.exports: list[tuple[Path, int]] = []

    def Repaginate(self) -> None:
        self.repaginate_calls += 1

    def ComputeStatistics(self, statistic: int) -> int:
        self.statistics_calls.append(statistic)
        return self.pages

    def ExportAsFixedFormat(self, output: str, format_id: int) -> None:
        path = Path(output)
        path.write_bytes(b"%PDF-1.7\n% fake Word export\n")
        self.exports.append((path, format_id))

    def Close(self, *args: object) -> None:
        self.close_calls.append(args)
        self.documents.Count = 0


class FakeDocuments:
    def __init__(self, *, pages: int = 1) -> None:
        self.Count = 0
        self.document = FakeDocument(self, pages=pages)
        self.open_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def Open(self, *args: object, **kwargs: object) -> FakeDocument:
        self.open_calls.append((args, kwargs))
        self.Count = 1
        return self.document


class FakeWordApplication:
    def __init__(self, *, pages: int = 1) -> None:
        self.Documents = FakeDocuments(pages=pages)
        self.quit_calls = 0
        self.Path = r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE"
        self.Version = "16.0"
        self.Caption = "Microsoft Word"

    def Quit(self) -> None:
        self.quit_calls += 1


class FakeEngineApplication(FakeWordApplication):
    def __init__(self, path: str, *, pages: int = 1) -> None:
        super().__init__(pages=pages)
        self.Path = path
        self.Version = "16.0"
        self.Caption = "Microsoft Word"


class ProcessTimeline:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.images: list[str] = []

    def __call__(self, image_name: str) -> list[int]:
        self.images.append(image_name)
        if not self.responses:
            raise AssertionError("unexpected Office PID probe")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return list(response)  # type: ignore[arg-type]


class OfficeNativeGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source.docx"
        self.source.write_bytes(b"fake DOCX input for injected COM tests")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @unittest.skipUnless(os.name == "nt", "Windows process path integration")
    def test_process_path_reads_the_actual_current_process(self) -> None:
        self.assertEqual(Path(native_gate._process_path(os.getpid())).resolve(), Path(sys.executable).resolve())
        self.assertIsNone(native_gate._process_path(-1))

    def test_safe_process_executable_path_returns_path_and_reports_missing(self) -> None:
        executable = self.root / "WINWORD.EXE"
        executable.write_bytes(b"word")
        with patch.object(native_gate, "_process_path", return_value=str(executable)):
            path, error = native_gate._safe_process_executable_path(4242)
        self.assertEqual(path, executable.resolve())
        self.assertIsNone(error)

        with patch.object(native_gate, "_process_path", return_value=None):
            path, error = native_gate._safe_process_executable_path(4242)
        self.assertIsNone(path)
        self.assertIn("could not read executable path", str(error))

    def run_docx_gate(
        self,
        pid_responses: list[object],
        *,
        application: FakeWordApplication | None = None,
        require_render: bool = False,
        rasterizer=None,
        dispatch_word_executable=None,
        prepare_owned_application=None,
    ) -> tuple[dict[str, object], FakeWordApplication, FakeComRuntime, ProcessTimeline]:
        word = application or FakeWordApplication()
        runtime = FakeComRuntime()
        timeline = ProcessTimeline(pid_responses)
        with patch.object(native_gate.tempfile, "gettempdir", return_value=str(self.root)), \
             patch.object(native_gate, "_verify_word_ownership", return_value={"status": "VERIFIED"}):
            result = native_gate.check_file(
                self.source,
                "docx",
                allow_office_com=True,
                require_render=require_render,
                process_ids=timeline,
                dispatch_ex=lambda progid: word,
                com_runtime=runtime,
                rasterizer=rasterizer,
                dispatch_word_executable=dispatch_word_executable,
                prepare_owned_application=prepare_owned_application,
                pid_observation_timeout_seconds=0,
                process_exit_timeout_seconds=0,
            )
        return result, word, runtime, timeline

    def test_word_uses_named_read_only_open_and_cleans_task_pid(self) -> None:
        result, word, runtime, timeline = self.run_docx_gate([[], [], [4242], []])

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(timeline.images, ["WINWORD.EXE"] * 4)
        self.assertEqual(runtime.initialize_calls, 1)
        self.assertEqual(runtime.uninitialize_calls, 1)
        self.assertEqual(word.quit_calls, 1)
        self.assertEqual(word.Documents.document.close_calls, [(False,)])
        args, kwargs = word.Documents.open_calls[0]
        self.assertEqual(args, ())
        self.assertEqual(Path(str(kwargs["FileName"])).name, self.source.name)
        self.assertNotEqual(Path(str(kwargs["FileName"])).resolve(), self.source.resolve())
        self.assertEqual(
            {key: value for key, value in kwargs.items() if key != "FileName"},
            {
                "ConfirmConversions": False,
                "ReadOnly": True,
                "AddToRecentFiles": False,
                "PasswordDocument": "",
                "PasswordTemplate": "",
                "Revert": False,
                "WritePasswordDocument": "",
                "WritePasswordTemplate": "",
                "Visible": False,
                "OpenAndRepair": False,
                "NoEncodingDialog": True,
            },
        )
        ownership = result["ownership"]
        self.assertEqual(ownership["owned_pids"], [4242])
        self.assertEqual(ownership["cleanup"]["status"], "CLEAN")

    def test_bootstrap_is_prepared_only_after_verified_ownership(self) -> None:
        word = FakeWordApplication()
        word.Documents.Count = 1
        prepared = []
        def prepare(app):
            prepared.append(app)
            app.Documents.Count = 0
        result, _, _, _ = self.run_docx_gate(
            [[], [], [4242], []], application=word, prepare_owned_application=prepare,
        )
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(prepared, [word])
        self.assertEqual(result['ownership']['instance_preparation']['status'], 'PASS')

        wps = FakeEngineApplication(r'D:\kingsoft\WPS Office\office6')
        result, _, _, _ = self.run_docx_gate(
            [[], [], []], application=wps, prepare_owned_application=prepare,
        )
        self.assertFalse(result['ok'])
        self.assertEqual(prepared, [word])
        self.assertEqual(wps.Documents.open_calls, [])

    def test_non_microsoft_provider_is_refused_without_fallback_or_quit(self) -> None:
        wps = FakeEngineApplication(r"D:\ProgramData\kingsoft\WPS Office\office6")
        def forbidden_fallback(_path):
            self.fail("executable fallback must not run")
        result, returned, _runtime, _timeline = self.run_docx_gate(
            [[], [], []], application=wps, dispatch_word_executable=forbidden_fallback,
        )
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["ownership"]["activation_identity"]["status"], "NON_MICROSOFT_PROVIDER")
        self.assertIs(returned, wps)
        self.assertEqual(wps.quit_calls, 0)
        self.assertEqual(wps.Documents.open_calls, [])
        self.assertEqual(result["ownership"]["cleanup"]["status"], "NOT_ATTEMPTED")

    def test_activation_failure_records_new_process_without_closing_it(self) -> None:
        runtime = FakeComRuntime()
        timeline = ProcessTimeline([[], [], [4242]])
        def failed_dispatch(_progid):
            raise RuntimeError("activation failed")
        with patch.object(native_gate.tempfile, "gettempdir", return_value=str(self.root)):
            result = native_gate.check_file(
                self.source, "docx", allow_office_com=True, process_ids=timeline,
                dispatch_ex=failed_dispatch, com_runtime=runtime,
            )
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["ownership"]["activation_failure_observation"]["new_pids"], [4242])
        self.assertEqual(result["ownership"]["cleanup"]["status"], "NOT_ATTEMPTED")
        self.assertEqual(runtime.initialize_calls, runtime.uninitialize_calls)

    def test_default_word_dispatch_uses_verified_interface(self) -> None:
        import reference_word
        word = FakeWordApplication()
        runtime = FakeComRuntime()
        timeline = ProcessTimeline([[], [], [4242], []])
        with patch.object(reference_word, "native_dispatch", return_value=word) as dispatch, \
             patch.object(native_gate, "_verify_word_ownership", return_value={"status": "VERIFIED"}), \
             patch.object(native_gate.tempfile, "gettempdir", return_value=str(self.root)):
            result = native_gate.check_file(
                self.source, "docx", allow_office_com=True, process_ids=timeline,
                com_runtime=runtime, pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0,
            )
        dispatch.assert_called_once_with("Word.Application")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(word.quit_calls, 1)

    def test_quit_failure_is_reported_and_never_passes(self) -> None:
        word = FakeWordApplication()
        def fail_quit():
            word.quit_calls += 1
            raise RuntimeError("quit failed")
        word.Quit = fail_quit
        result, _, _, _ = self.run_docx_gate([[], [], [4242], [4242]], application=word)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["phase"], "cleanup")
        self.assertEqual(result["ownership"]["cleanup"]["status"], "QUIT_FAILED")
        self.assertEqual(word.quit_calls, 1)

    def test_existing_word_pid_stops_before_dispatch(self) -> None:
        word = FakeWordApplication()
        result, returned_word, runtime, _timeline = self.run_docx_gate([[99]], application=word)

        self.assertEqual(result["status"], "UNSAFE_PROCESS")
        self.assertIs(returned_word, word)
        self.assertEqual(word.Documents.open_calls, [])
        self.assertEqual(word.quit_calls, 0)
        self.assertEqual(runtime.initialize_calls, 0)

    def test_unobservable_preflight_pid_probe_is_unverified(self) -> None:
        word = FakeWordApplication()
        result, returned_word, runtime, _timeline = self.run_docx_gate(
            [RuntimeError("tasklist failed")], application=word
        )

        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["ownership"]["preflight"]["status"], "UNOBSERVED")
        self.assertIs(returned_word, word)
        self.assertEqual(word.Documents.open_calls, [])
        self.assertEqual(word.quit_calls, 0)
        self.assertEqual(runtime.initialize_calls, 0)

    def test_activation_without_new_pid_is_unverified_without_quit(self) -> None:
        result, word, runtime, _timeline = self.run_docx_gate([[], [], []])

        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["phase"], "cleanup")
        self.assertEqual(result["ownership"]["pid_observation"]["status"], "NO_NEW_PID")
        self.assertEqual(result["ownership"]["cleanup"]["status"], "NOT_ATTEMPTED")
        self.assertEqual(word.Documents.open_calls, [])
        self.assertEqual(word.quit_calls, 0)
        self.assertEqual(runtime.initialize_calls, 1)
        self.assertEqual(runtime.uninitialize_calls, 1)

    def test_residual_owned_pid_downgrades_pass_and_keeps_prior_result(self) -> None:
        result, word, _runtime, _timeline = self.run_docx_gate([[], [], [17], [17]])

        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["phase"], "cleanup")
        self.assertEqual(word.quit_calls, 1)
        self.assertEqual(result["ownership"]["cleanup"]["status"], "RESIDUAL_PIDS")
        self.assertEqual(result["details"]["prior_result"]["status"], "PASS")
        self.assertEqual(result["details"]["cleanup_uncertainties"][0]["kind"], "office_process")

    def test_unconfirmed_office_exit_preserves_isolated_document(self) -> None:
        for after_quit in ([17], RuntimeError("PID observation failed")):
            with self.subTest(after_quit=after_quit):
                result, word, _runtime, _timeline = self.run_docx_gate([[], [], [17], after_quit])
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], "UNVERIFIED")
                retained = Path(result["details"]["retained_workspace"])
                self.assertTrue(retained.is_dir())
                self.assertEqual((retained / self.source.name).read_bytes(), self.source.read_bytes())
                self.assertEqual(word.quit_calls, 1)

    def test_confirmed_office_exit_removes_isolated_workspace(self) -> None:
        result, word, _runtime, _timeline = self.run_docx_gate([[], [], [17], []])
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn("retained_workspace", result["details"])
        isolated = Path(word.Documents.open_calls[0][1]["FileName"])
        self.assertFalse(isolated.parent.exists())

    def test_word_pdf_and_png_page_count_mismatch_fails_render(self) -> None:
        result, word, _runtime, _timeline = self.run_docx_gate(
            [[], [], [84], []],
            require_render=True,
            rasterizer=lambda _pdf, _directory, _expected: {"pdf_pages": 1, "png_pages": 2},
        )

        self.assertEqual(result["status"], "FAIL_RENDER")
        self.assertEqual(result["phase"], "page_count_evidence")
        self.assertEqual(result["details"]["page_counts"], {"word": 1, "pdf": 1, "png": 2})
        self.assertEqual(word.Documents.document.exports[0][1], 17)

    def test_missing_pdf_or_png_page_count_is_unverified(self) -> None:
        for raster_result in (
            {"pdf_pages": None, "png_pages": 1},
            {"pdf_pages": 1, "png_pages": None},
        ):
            with self.subTest(raster_result=raster_result):
                result, word, _runtime, _timeline = self.run_docx_gate(
                    [[], [], [101], []],
                    require_render=True,
                    rasterizer=lambda _pdf, _directory, _expected, value=raster_result: value,
                )

                self.assertEqual(result["status"], "UNVERIFIED")
                self.assertEqual(result["phase"], "page_count_evidence")
                self.assertEqual(word.quit_calls, 1)


class WordIdentityTests(OfficeNativeGateTests):
    def test_real_word_interface_uses_and_closes_bootstrap_window(self):
        executable = self.root / "Microsoft Office" / "Office16" / "WINWORD.EXE"
        word = FakeWordApplication()
        word.Path = str(executable.parent)
        word._codex_expected_provider_path = executable
        bootstrap = FakeDocument(word.Documents)
        bootstrap.Windows = type("Windows", (), {"Item": lambda self, index: type("Window", (), {"Hwnd": 10})()})()
        word.Documents.Add = lambda **kwargs: bootstrap
        with patch.object(native_gate, "_window_process_id", return_value=4242), \
             patch.object(native_gate, "_safe_process_executable_path", return_value=(executable, None)):
            result = native_gate._verify_word_ownership(word, {"path": word.Path}, {"owned_pids": [4242]})
        self.assertEqual(result["pid"], 4242)
        self.assertEqual(bootstrap.close_calls, [(False,)])

    def test_bootstrap_is_closed_when_window_pid_does_not_match(self):
        executable = self.root / "Microsoft Office" / "Office16" / "WINWORD.EXE"
        word = FakeWordApplication()
        word.Path = str(executable.parent)
        word._codex_expected_provider_path = executable
        bootstrap = FakeDocument(word.Documents)
        bootstrap.Windows = type("Windows", (), {"Item": lambda self, index: type("Window", (), {"Hwnd": 10})()})()
        word.Documents.Add = lambda **kwargs: bootstrap
        with patch.object(native_gate, "_window_process_id", return_value=999), \
             patch.object(native_gate, "_safe_process_executable_path", return_value=(executable, None)):
            with self.assertRaises(ValueError):
                native_gate._verify_word_ownership(word, {"path": word.Path}, {"owned_pids": [4242]})
        self.assertEqual(bootstrap.close_calls, [(False,)])
        self.assertEqual(word.quit_calls, 0)

    def test_bootstrap_refuses_nonempty_document_collection(self):
        executable = self.root / "Microsoft Office" / "Office16" / "WINWORD.EXE"
        word = FakeWordApplication()
        word.Path = str(executable.parent)
        word._codex_expected_provider_path = executable
        word.Documents.Count = 1
        with self.assertRaisesRegex(ValueError, "already contains documents"):
            native_gate._verify_word_ownership(word, {"path": word.Path}, {"owned_pids": [4242]})
        self.assertEqual(word.quit_calls, 0)

    def _case(self, *, observed=None, window_pid=4242, app_path=None, expected_path=None,
              process_path=None, path_error=None, hwnd=10):
        executable = self.root / "Microsoft Office" / "Office16" / "WINWORD.EXE"
        word = FakeWordApplication()
        word.Path = str(app_path if app_path is not None else executable.parent)
        word._codex_expected_provider_path = expected_path if expected_path is not None else executable
        word.Hwnd = hwnd
        observation = {"owned_pids": [4242] if observed is None else observed}
        with patch.object(native_gate, "_window_process_id", return_value=window_pid), \
             patch.object(native_gate, "_safe_process_executable_path", return_value=(process_path if process_path is not None else executable, path_error)):
            return native_gate._verify_word_ownership(word, {"path": word.Path}, observation)

    def test_identity_matches_directory_and_one_window_pid(self):
        result = self._case()
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["pid"], 4242)

    def test_identity_refuses_mismatch_or_missing_evidence(self):
        for changes in (
            {"observed": [4242, 4243]}, {"observed": []}, {"window_pid": 999},
            {"app_path": self.root / "other"}, {"process_path": self.root / "other" / "WINWORD.EXE"},
            {"expected_path": self.root / "other" / "WINWORD.EXE"}, {"path_error": "access denied"},
            {"expected_path": self.root / "wps.exe"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self._case(**changes)

    def test_unverified_identity_never_opens_or_quits(self):
        word = FakeWordApplication()
        runtime = FakeComRuntime()
        timeline = ProcessTimeline([[], [], [4242]])
        with patch.object(native_gate.tempfile, "gettempdir", return_value=str(self.root)), \
             patch.object(native_gate, "_verify_word_ownership", side_effect=ValueError("PID mismatch")):
            result = native_gate.check_file(self.source, "docx", allow_office_com=True,
                dispatch_ex=lambda _: word, com_runtime=runtime, process_ids=timeline,
                pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0)
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertEqual(result["ownership"]["word_identity_and_ownership"]["status"], "UNVERIFIED")
        self.assertEqual(result["ownership"]["candidate_pids"], [4242])
        self.assertEqual(result["ownership"]["owned_pids"], [])
        self.assertEqual(word.Documents.open_calls, [])
        self.assertEqual(word.quit_calls, 0)

    def test_gate_accepts_only_matching_window_and_paths(self):
        word = FakeWordApplication()
        executable = self.root / "Microsoft Office" / "Office16" / "WINWORD.EXE"
        word.Path = str(executable.parent)
        word._codex_expected_provider_path = executable
        word.Hwnd = 10
        timeline = ProcessTimeline([[], [], [4242], []])
        with patch.object(native_gate.tempfile, "gettempdir", return_value=str(self.root)), \
             patch.object(native_gate, "_window_process_id", return_value=4242), \
             patch.object(native_gate, "_safe_process_executable_path", return_value=(executable, None)):
            result = native_gate.check_file(self.source, "docx", allow_office_com=True,
                dispatch_ex=lambda _: word, com_runtime=FakeComRuntime(), process_ids=timeline,
                pid_observation_timeout_seconds=0, process_exit_timeout_seconds=0)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["ownership"]["owned_pids"], [4242])
        self.assertEqual(word.quit_calls, 1)

    def test_ignored_background_and_security_settings_block_open(self):
        class IgnoringWord(FakeWordApplication):
            def __setattr__(self, name, value):
                if name == self.__dict__.get("ignored"):
                    if self.__dict__.get("mode") == "ignore":
                        return
                    if self.__dict__.get("mode") == "write_error":
                        raise RuntimeError("setting failed")
                super().__setattr__(name, value)

            def __getattribute__(self, name):
                state = object.__getattribute__(self, "__dict__")
                if name == state.get("ignored") and state.get("mode") == "read_error":
                    raise RuntimeError("reading failed")
                return super().__getattribute__(name)

        for name, initial in (("Visible", True), ("DisplayAlerts", 1),
                              ("ScreenUpdating", True), ("AutomationSecurity", 1)):
            for mode in ("ignore", "write_error", "read_error"):
                with self.subTest(name=name, mode=mode):
                    word = IgnoringWord()
                    setattr(word, name, initial)
                    word.ignored = name
                    word.mode = mode
                    result, _, _, _ = self.run_docx_gate([[], [], [4242], []], application=word)
                    self.assertNotEqual(result["status"], "PASS")
                    self.assertEqual(word.Documents.open_calls, [])
                    self.assertEqual(word.quit_calls, 1)


if __name__ == "__main__":
    unittest.main()
