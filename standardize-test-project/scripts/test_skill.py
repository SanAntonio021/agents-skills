#!/usr/bin/env python3
"""Hardware-free integration test for the skill scaffold and Python helpers."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


sys.dont_write_bytecode = True


SCRIPT_DIR = Path(__file__).resolve().parent
SCAFFOLD = SCRIPT_DIR / "scaffold_test_project.py"
VALIDATOR = SCRIPT_DIR / "validate_test_project.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_measurement_run(
    results,
    plots,
    project: Path,
    run_kind: str,
    name_parts: list[str],
    x: np.ndarray,
    values: np.ndarray,
    timestamp: str,
    *,
    failed_index: int | None = None,
):
    run = results.create_run(
        project,
        run_kind,
        name_parts,
        project_name="skill_self_test",
        test_name="通用结果契约自检",
        purpose="debug",
        entry_point="run_test.py",
        primary_variable={
            "name": "控制变量",
            "symbol": "X",
            "unit": "-",
            "start": float(x.min()),
            "stop": float(x.max()),
            "step": float(x[1] - x[0]) if x.size > 1 else None,
        },
        parameters={"self_test_fixture": True},
        planned_count=x.size,
        timestamp=timestamp,
    )
    headers = ["控制变量", "实验指标", *(
        "状态",
        "repeat",
        "attempt",
        "采集时间",
        "原始数据文件",
        "单次图片文件",
        "错误代码",
        "错误信息",
    )]
    units = ["-", "-", "-", "-", "-", "-", "-", "-", "-", "-"]
    results.initialize_summary(run, headers, units)
    success = np.ones(x.size, dtype=bool)
    for index, (control, metric) in enumerate(zip(x, values), start=1):
        failed = failed_index == index - 1
        success[index - 1] = not failed
        point = f"X{results.format_value(float(control), 1)}"
        raw_name = results.point_filename(point, index, 1, "csv", failed=failed)
        raw_path = run.run_dir / raw_name
        raw_path.write_text(
            "control_value,metric\n" f"{control:.1f},{metric:.6f}\n",
            encoding="utf-8",
        )
        figure_name = f"{raw_path.stem}_spectrum.png"
        frequency = np.linspace(0.0, 1.0, 101)
        spectrum = -70.0 + 25.0 * np.exp(-0.5 * ((frequency - 0.5) / 0.08) ** 2)
        plots.plot_spectrum(
            run.run_dir / figure_name,
            frequency,
            spectrum,
            title="合成频谱格式自检",
            x_name="归一化频率",
            x_unit="-",
            y_name="归一化功率",
            y_unit="dB",
        )
        results.log(
            run,
            "ERROR" if failed else "INFO",
            "acquisition",
            f"repeat{index:02d} attempt01 {'失败' if failed else '成功'}；仅合成自检，未访问仪器",
        )
        results.append_summary(
            run,
            [
                f"{control:.1f}",
                "" if failed else float(metric),
                "失败" if failed else "成功",
                index,
                1,
                results.now_iso(),
                raw_name,
                figure_name,
                "SYNTHETIC_FAILURE" if failed else "",
                "合成失败记录" if failed else "",
            ],
        )
    plots.plot_scan_summary(
        run.run_dir / "overview.png",
        x,
        [{"name": "实验指标", "unit": "-", "values": values}],
        success_mask=success,
        planned_count=x.size,
        title="控制变量扫描格式自检",
        x_name="控制变量",
        x_unit="-",
    )
    counts = {
        "planned": int(x.size),
        "executed": int(x.size),
        "succeeded": int(np.count_nonzero(success)),
        "failed": int(np.count_nonzero(~success)),
        "invalid": 0,
    }
    results.update_run_info(
        run,
        {
            "counts": counts,
            "safety": {
                "preflight": "not_applicable_self_test",
                "shutdown": "not_applicable_self_test",
            },
        },
    )
    status = "completed_with_failures" if failed_index is not None else "completed"
    results.finalize_run(run, status, "normal_completion", counts=counts)
    return run


def write_dry_run(results, plots, project: Path):
    points = np.array([1.0, 2.0, 3.0])
    run = results.create_run(
        project,
        "dry_run",
        ["Point1-3", "step1"],
        project_name="skill_self_test",
        test_name="计划检查自检",
        purpose="debug",
        execution_mode="dry_run",
        planned_run_kind="scan",
        entry_point="run_test.py",
        primary_variable={
            "name": "计划点序号",
            "symbol": "point_index",
            "unit": "-",
            "start": 1,
            "stop": 3,
            "step": 1,
        },
        planned_count=3,
        timestamp="20260715_120200",
    )
    results.initialize_summary(
        run,
        [
            "计划点序号",
            "状态",
            "repeat",
            "attempt",
            "采集时间",
            "原始数据文件",
            "单次图片文件",
            "错误代码",
            "错误信息",
        ],
        ["-", "-", "-", "-", "-", "-", "-", "-", "-"],
    )
    plots.plot_plan_overview(
        run.run_dir / "overview.png",
        points,
        title="dry-run 计划检查",
        x_name="计划点序号",
        x_unit="-",
        planned_observations=3,
    )
    counts = {"planned": 3, "executed": 0, "succeeded": 0, "failed": 0, "invalid": 0}
    results.finalize_run(
        run,
        "completed",
        "normal_completion",
        counts=counts,
        safety={"preflight": "not_applicable", "shutdown": "not_applicable"},
    )
    return run


def write_analysis(results, plots, project: Path, sources):
    run = results.create_run(
        project,
        "analysis",
        ["ControlComparison", "A-B"],
        project_name="skill_self_test",
        test_name="跨运行分析自检",
        purpose="debug",
        execution_mode="offline_analysis",
        entry_point="run_test.py",
        primary_variable={"name": "来源序号", "symbol": "source", "unit": "-", "values": [1, 2]},
        planned_count=1,
        timestamp="20260715_120400",
    )
    results.write_sources(run, [source.run_dir for source in sources])
    results.initialize_summary(
        run,
        [
            "来源差值",
            "状态",
            "repeat",
            "attempt",
            "采集时间",
            "原始数据文件",
            "单次图片文件",
            "错误代码",
            "错误信息",
        ],
        ["-", "-", "-", "-", "-", "-", "-", "-", "-"],
    )
    results.append_summary(run, [0.1, "成功", 1, 1, results.now_iso(), "", "", "", ""])
    plots.plot_scan_summary(
        run.run_dir / "overview.png",
        np.array([1.0]),
        [{"name": "来源差值", "unit": "-", "values": np.array([0.1])}],
        success_mask=np.array([True]),
        planned_count=1,
        title="跨运行分析格式自检",
        x_name="比较序号",
        x_unit="-",
    )
    counts = {"planned": 1, "executed": 1, "succeeded": 1, "failed": 0, "invalid": 0}
    results.finalize_run(run, "completed", "normal_completion", counts=counts)
    return run


def test_plot_and_naming_contracts(results, plots, project: Path, temporary: Path) -> None:
    plot_root = temporary / "plot_contracts"
    plot_root.mkdir()
    scan_stats = plots.plot_scan_summary(
        plot_root / "ber_zero.png",
        np.array([1.0, 1.0, 2.0]),
        [
            {
                "name": "BER",
                "unit": "-",
                "values": np.array([0.0, 0.0, 1e-3]),
                "y_scale": "log",
                "bit_counts": np.array([1e6, 1e6, 1e6]),
            }
        ],
        success_mask=np.array([True, True, True]),
        planned_count=3,
        title="BER 零值格式自检",
        x_name="控制变量",
        x_unit="-",
    )
    metric = scan_stats["metrics"][0]
    if metric["mean"][0] != 0 or metric["zero_count"] != 2:
        raise AssertionError("BER=0 was not preserved in statistics")
    if not np.isnan(metric["sample_std"][1]):
        raise AssertionError("single-sample standard deviation must be NaN")

    ideal = np.array([-1 - 1j, -1 + 1j, 1 - 1j, 1 + 1j]) / np.sqrt(2)
    received = np.concatenate((np.tile(ideal, 20), np.array([3 + 3j])))
    constellation = plots.plot_constellation(
        plot_root / "constellation.png",
        [received],
        ideal,
        metrics=[{"BER": 0, "EVMPercent": 5.0, "MERdB": 26.0}],
    )
    if constellation["outside_count"][0] != 1:
        raise AssertionError("constellation out-of-range count is incorrect")

    spectrum_path = plot_root / "neutral_spectrum.png"
    frequency = np.linspace(0, 1, 11)
    plots.plot_spectrum(spectrum_path, frequency, np.linspace(-1, 1, 11))
    try:
        plots.plot_spectrum(spectrum_path, frequency, np.linspace(-1, 1, 11))
    except FileExistsError:
        pass
    else:
        raise AssertionError("plot helper overwrote an existing PNG")

    if results.format_parameter("scan", 1, 0, "") != "scan1":
        raise AssertionError("parameter symbols may use category words")
    if results.point_filename("analysis", 1, 1, "csv") != "analysis_repeat01_attempt01.csv":
        raise AssertionError("point filenames may use category words")
    try:
        results.create_run(
            project,
            "scan",
            ["analysis"],
            project_name="skill_self_test",
            test_name="reserved run name",
            timestamp="20260715_115959",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("run NameParts accepted a reserved result category")
    if (project / "results" / "scan" / "analysis_20260715_115959").exists():
        raise AssertionError("invalid run configuration left a directory behind")


def run_test() -> None:
    with tempfile.TemporaryDirectory(prefix="standardize_test_project_") as temporary:
        project = Path(temporary) / "project"
        subprocess.run(
            [
                sys.executable,
                str(SCAFFOLD),
                str(project),
                "--name",
                "Skill 隔离自检项目",
                "--language",
                "both",
            ],
            check=True,
        )
        if "{{PROJECT_NAME}}" in (project / "README.md").read_text(encoding="utf-8"):
            raise AssertionError("project name placeholder was not rendered")
        if not (project / "Run_Test.m").is_file() or not (project / "run_test.py").is_file():
            raise AssertionError("human entry scripts were not scaffolded")

        results = load_module(
            "test_project_results",
            project / "code" / "result_management" / "test_project_results.py",
        )
        plots = load_module(
            "test_project_plots",
            project / "code" / "plotting" / "test_project_plots.py",
        )
        test_plot_and_naming_contracts(results, plots, project, Path(temporary))
        single = write_measurement_run(
            results,
            plots,
            project,
            "single_point",
            ["Control1.0", "fixed2.0"],
            np.array([1.0, 1.0, 1.0]),
            np.array([2.0, 2.1, 1.9]),
            "20260715_120000",
        )
        scan = write_measurement_run(
            results,
            plots,
            project,
            "scan",
            ["Control1.0-1.2", "step0.1"],
            np.array([1.0, 1.1, 1.2]),
            np.array([2.0, 2.2, 2.4]),
            "20260715_120100",
            failed_index=1,
        )
        dry = write_dry_run(results, plots, project)
        simulation = write_measurement_run(
            results,
            plots,
            project,
            "simulation",
            ["ModelValue0.0-2.0", "step1.0"],
            np.array([0.0, 1.0, 2.0]),
            np.array([0.5, 0.7, 0.9]),
            "20260715_120300",
        )
        analysis = write_analysis(results, plots, project, [single, scan])

        replay = results.reserve_derived_path(
            single,
            "replay",
            "summary",
            "csv",
            timestamp="20260715_130000",
        )
        replay.write_text("metric\n1.0\n", encoding="utf-8")
        results.register_artifact(single, replay.name, "replay_summary")
        if results.check_flat(single):
            raise AssertionError("single-run replay created a subdirectory")
        if len((analysis.run_dir / "sources.txt").read_text(encoding="utf-8").splitlines()) != 2:
            raise AssertionError("analysis source linkage is incomplete")

        try:
            results.create_run(
                project,
                "dry_run",
                ["Point1-3", "step1"],
                project_name="skill_self_test",
                test_name="collision test",
                planned_run_kind="scan",
                timestamp="20260715_120200",
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing run directory was overwritten")

        validation = subprocess.run(
            [sys.executable, str(VALIDATOR), str(project)],
            check=False,
            capture_output=True,
            text=True,
        )
        if validation.returncode:
            raise AssertionError(validation.stdout + validation.stderr)
        print(validation.stdout.strip())
        print(
            "Self-test passed: scaffold, five result kinds, flat runs, replay linkage, "
            "analysis sources, CSV/JSON/log/PNG contracts, and no-overwrite guard."
        )
        _ = (dry, simulation)


if __name__ == "__main__":
    run_test()
