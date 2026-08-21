from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = SKILL_ROOT / "scripts" / "invoke_paper_figure_python.ps1"
RUNTIME_ROOT = Path(r"C:\Users\SanAn\.local\scientific-plotting-runtime")
RUNTIME_PYTHON = RUNTIME_ROOT / ".venv" / "Scripts" / "python.exe"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell is required for the runtime adapter tests")
    return executable


def _run_adapter(
    script_path: Path,
    *,
    script_arguments: list[str] | None = None,
    draft_variant: str = "unspecified",
    runtime_root: Path = RUNTIME_ROOT,
    test_mode: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [
        _powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ADAPTER),
        "-DraftVariant",
        draft_variant,
        "-RuntimeRoot",
        str(runtime_root),
        "-ScriptPath",
        str(script_path),
    ]
    if script_arguments:
        command.extend(["-ScriptArguments", *script_arguments])
    if test_mode:
        command.append("-TestMode")
    environment = os.environ.copy()
    if test_mode:
        environment["PAPER_FIGURE_REVIEW_TEST_MODE"] = "1"
    else:
        environment.pop("PAPER_FIGURE_REVIEW_TEST_MODE", None)
    return subprocess.run(command, capture_output=True, text=True, env=environment, check=False)


def test_adapter_runs_fixed_runtime_and_records_metadata(tmp_path: Path):
    if not RUNTIME_PYTHON.is_file():
        pytest.skip("fixed scientific plotting runtime is not installed")
    script = tmp_path / "make_runtime_figure.py"
    script.write_text(
        """
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import ieee_plot_style as style

output_dir = Path(sys.argv[1])
output_dir.mkdir(parents=True, exist_ok=True)
style.use_ieee_single_column_style()
figure, axis = plt.subplots(figsize=(3.5, 2.4))
axis.plot([0, 1, 2], [0.2, 0.8, 0.4], marker='o', label='series')
axis.set_xlabel('x')
axis.set_ylabel('y')
style.export_ieee_single_column(
    figure,
    'runtime',
    output_dir,
    mode='draft',
    grid_mode='major_xy',
)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = _run_adapter(script, script_arguments=[str(tmp_path / "figure-output")], draft_variant="B")
    assert result.returncode == 0, result.stderr + result.stdout
    manifest_path = tmp_path / "figure-output" / "drafts" / "runtime.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    runtime = manifest["runtime"]
    assert runtime["execution_source"] == "fixed_runtime_adapter"
    assert Path(runtime["runtime_root"]).resolve() == RUNTIME_ROOT.resolve()
    assert Path(runtime["python_executable"]).resolve() == RUNTIME_PYTHON.resolve()
    assert runtime["python_version"].startswith("3.12.")
    assert runtime["matplotlib_version"] == "3.11.1"
    assert runtime["scienceplots_version"] == "2.2.2"
    assert runtime["draft_variant"] == "B"
    assert manifest["formal_style_source"] == "ieee_plot_style.py"


def test_adapter_rejects_non_fixed_runtime_without_test_mode(tmp_path: Path):
    script = tmp_path / "noop.py"
    script.write_text("print('should not run')\n", encoding="utf-8")
    result = _run_adapter(script, runtime_root=tmp_path / "other-runtime")
    assert result.returncode != 0
    assert "RuntimeRoot is fixed" in result.stderr
    assert "should not run" not in result.stdout


def test_adapter_reports_missing_test_runtime_without_fallback(tmp_path: Path):
    script = tmp_path / "noop.py"
    script.write_text("print('should not run')\n", encoding="utf-8")
    result = _run_adapter(
        script,
        runtime_root=tmp_path / "missing-runtime",
        test_mode=True,
    )
    assert result.returncode != 0
    assert "runtime directory was not found" in result.stderr.lower()
    assert "should not run" not in result.stdout


def test_adapter_propagates_figure_script_failure(tmp_path: Path):
    if not RUNTIME_PYTHON.is_file():
        pytest.skip("fixed scientific plotting runtime is not installed")
    script = tmp_path / "fail.py"
    script.write_text("raise SystemExit(17)\n", encoding="utf-8")
    result = _run_adapter(script)
    assert result.returncode == 17
