"""Real PPTX adapter integration tests guarded by RUN_LIBREOFFICE_INTEGRATION."""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


_SKILLS_ROOT = Path(__file__).resolve().parents[2]
_PPTX_SCRIPTS = _SKILLS_ROOT / "pptx" / "scripts"
_ADAPTER = _PPTX_SCRIPTS / "office" / "soffice.py"
_THUMBNAIL = _PPTX_SCRIPTS / "thumbnail.py"
_BOOTSTRAP = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LibreOffice" / "program" / "bootstrap.ini"
_DEFAULT_PROFILE = Path(os.environ["APPDATA"]) / "LibreOffice" / "4" / "user" / "registrymodifications.xcu"


def _check_integration_deps() -> list[str]:
    missing = []
    for package, import_name in (
        ("psutil", "psutil"),
        ("python-pptx", "pptx"),
        ("Pillow", "PIL"),
        ("PyPDF2", "PyPDF2"),
    ):
        try:
            __import__(import_name)
        except ImportError:
            missing.append(package)
    if shutil.which("pdftoppm") is None:
        missing.append("pdftoppm")
    return missing


def _lo_snapshots() -> list[dict]:
    import psutil

    snapshots = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (process.info["name"] or "").lower()
            if "soffice" in name:
                snapshots.append(
                    {
                        "pid": process.info["pid"],
                        "name": name,
                        "cmdline": process.info["cmdline"] or [],
                    }
                )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return snapshots


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_state(path: Path) -> tuple[bool, str | None]:
    return (path.is_file(), _sha256_file(path) if path.is_file() else None)


def _task_roots() -> set[str]:
    return {
        str(path.resolve())
        for path in Path(tempfile.gettempdir()).glob("sanan-lo-*")
        if path.is_dir()
    }


def _make_pptx_two_slides(path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    blank_layout = presentation.slide_layouts[6]
    for index in range(2):
        slide = presentation.slides.add_slide(blank_layout)
        text_box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        text_box.text_frame.text = f"Slide {index + 1}"
    presentation.save(str(path))


def _profile_args(snapshots: list[dict]) -> set[str]:
    profiles = set()
    for snapshot in snapshots:
        for argument in snapshot["cmdline"]:
            if argument.lower().startswith("-env:userinstallation="):
                profiles.add(argument.split("=", 1)[1])
    return profiles


@unittest.skipUnless(
    os.environ.get("RUN_LIBREOFFICE_INTEGRATION") == "1",
    "Set RUN_LIBREOFFICE_INTEGRATION=1 to run",
)
class TestPptxIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = _check_integration_deps()
        if missing:
            raise RuntimeError(f"Missing integration dependencies: {missing}")
        running = _lo_snapshots()
        if running:
            raise RuntimeError(
                "LibreOffice already running before PPTX integration tests: "
                + ", ".join(str(process["pid"]) for process in running)
            )
        cls.bootstrap_before = _file_state(_BOOTSTRAP)
        cls.default_profile_before = _file_state(_DEFAULT_PROFILE)
        cls.task_roots_before = _task_roots()

    @classmethod
    def tearDownClass(cls):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if not _lo_snapshots() and not (_task_roots() - cls.task_roots_before):
                break
            time.sleep(0.1)

        failures = []
        remaining = _lo_snapshots()
        if remaining:
            failures.append(
                "LibreOffice processes remain: "
                + ", ".join(str(process["pid"]) for process in remaining)
            )
        new_roots = _task_roots() - cls.task_roots_before
        if new_roots:
            failures.append(f"New sanan-lo task roots remain: {sorted(new_roots)}")
        if _file_state(_BOOTSTRAP) != cls.bootstrap_before:
            failures.append("bootstrap.ini changed during integration tests")
        if _file_state(_DEFAULT_PROFILE) != cls.default_profile_before:
            failures.append("Default LibreOffice profile changed during integration tests")
        if failures:
            raise AssertionError("; ".join(failures))

    def test_thumbnail_cli_creates_decodable_jpeg(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "deck.pptx"
            output_prefix = Path(temp_dir) / "deck-thumbnails"
            _make_pptx_two_slides(source)

            completed = subprocess.run(
                [sys.executable, str(_THUMBNAIL), str(source), str(output_prefix)],
                cwd=str(_SKILLS_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"thumbnail.py failed\nstdout={completed.stdout}\nstderr={completed.stderr}",
            )
            grids = sorted(Path(temp_dir).glob("deck-thumbnails*.jpg"))
            self.assertTrue(grids, "thumbnail.py created no JPEG grids")
            for grid in grids:
                with Image.open(grid) as image:
                    image.verify()
                with Image.open(grid) as image:
                    self.assertGreater(image.width, 0)
                    self.assertGreater(image.height, 0)

    def test_three_independent_adapter_processes_use_isolated_profiles(self):
        from PyPDF2 import PdfReader

        processes = []
        captures = []
        profiles = set()
        peak_soffice_bin = 0
        timed_out = False

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            jobs = []
            for index in range(3):
                source = temp_path / f"deck_{index}.pptx"
                output_dir = temp_path / f"out_{index}"
                output_dir.mkdir()
                _make_pptx_two_slides(source)
                jobs.append((source, output_dir))

            environment = os.environ.copy()
            environment["PYTHONUTF8"] = "1"
            environment["PYTHONIOENCODING"] = "utf-8"
            try:
                for source, output_dir in jobs:
                    processes.append(
                        subprocess.Popen(
                            [
                                sys.executable,
                                str(_ADAPTER),
                                "--headless",
                                "--convert-to",
                                "pdf:impress_pdf_Export",
                                "--outdir",
                                str(output_dir),
                                str(source),
                            ],
                            cwd=str(_SKILLS_ROOT),
                            env=environment,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                        )
                    )

                self.assertEqual(len({process.pid for process in processes}), 3)
                deadline = time.monotonic() + 300.0
                while any(process.poll() is None for process in processes):
                    snapshots = _lo_snapshots()
                    peak_soffice_bin = max(
                        peak_soffice_bin,
                        sum(item["name"] == "soffice.bin" for item in snapshots),
                    )
                    profiles.update(_profile_args(snapshots))
                    if time.monotonic() >= deadline:
                        timed_out = True
                        break
                    time.sleep(0.01)
            finally:
                for process in processes:
                    if process.poll() is None:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                for process in processes:
                    stdout, stderr = process.communicate(timeout=30)
                    captures.append((process.returncode, stdout, stderr))

            self.assertFalse(timed_out, "Parallel adapter processes exceeded 300 seconds")
            for returncode, stdout, stderr in captures:
                self.assertEqual(
                    returncode,
                    0,
                    f"Adapter process failed\nstdout={stdout}\nstderr={stderr}",
                )

            self.assertGreater(peak_soffice_bin, 0, "Process monitor saw no soffice.bin")
            self.assertLessEqual(peak_soffice_bin, 2)
            isolated_profiles = {
                profile
                for profile in profiles
                if "sanan-lo-" in profile.lower()
                and profile.replace("\\", "/").lower().endswith("/profile")
            }
            self.assertEqual(
                len(isolated_profiles),
                3,
                f"Expected 3 isolated UserInstallation profiles, got {sorted(profiles)}",
            )

            for source, output_dir in jobs:
                output = output_dir / f"{source.stem}.pdf"
                self.assertTrue(output.is_file(), f"Missing output: {output}")
                self.assertEqual(len(PdfReader(str(output)).pages), 2)


if __name__ == "__main__":
    unittest.main()
