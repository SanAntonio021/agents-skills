from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


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

    def Quit(self) -> None:
        self.quit_calls += 1


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

    def run_docx_gate(
        self,
        pid_responses: list[object],
        *,
        application: FakeWordApplication | None = None,
        require_render: bool = False,
        rasterizer=None,
    ) -> tuple[dict[str, object], FakeWordApplication, FakeComRuntime, ProcessTimeline]:
        word = application or FakeWordApplication()
        runtime = FakeComRuntime()
        timeline = ProcessTimeline(pid_responses)
        result = native_gate.check_file(
            self.source,
            "docx",
            allow_office_com=True,
            require_render=require_render,
            process_ids=timeline,
            dispatch_ex=lambda progid: word,
            com_runtime=runtime,
            rasterizer=rasterizer,
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


if __name__ == "__main__":
    unittest.main()
