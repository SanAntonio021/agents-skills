# LibreOffice Runner 调用契约

## 前提

- 仅支持 Windows。
- 使用本机可用的 Python 3.10+ 解释器，需要 `pywin32` 和 `PyPDF2`；路径由本机发现，不固定用户名或安装盘符。
- LibreOffice 默认寻找 `soffice.com`，也可用 `--soffice` 指定已存在的绝对路径。
- 输入必须是文件，输出路径不得存在，输入和输出不能相同。

以上是程序调用条件。授权、输出重名和用户窗口影响按 [技能入口](../SKILL.md#先读) 处理，
不增加接口外的确认环节；集成测试的无用户进程前提仅适用于该测试套件。

## CLI

```text
python scripts/libreoffice_run.py pdf <source> <output>
python scripts/libreoffice_run.py recalc <source.xlsx> <output.xlsx>
python scripts/libreoffice_run.py convert <source> <output> --convert-to <filter>
python scripts/libreoffice_run.py accept-changes <source.docx> <output.docx>
python scripts/libreoffice_run.py cleanup [--older-than <seconds>] [--work-root <directory>]
```

`pdf` 支持 DOC/DOCX/ODT、XLS/XLSX/XLSM/XLTX 和 PPT/PPTX/ODP。`recalc` 只支持
XLSX/XLTX 到 XLSX。`accept-changes` 只支持 DOCX 到 DOCX。

## Python API

```python
from pathlib import Path
from libreoffice_runner import RunRequest, convert, run

report = run(RunRequest("pdf", Path("input.docx"), Path("output.pdf")))
result = convert("recalc", Path("input.xlsx"), Path("output.xlsx"), timeout=120)
report = run(RunRequest("pdf", Path("input.pptx"), Path("output.pdf"),
                        work_root=Path("过程文件/汇报/runner-work"),
                        diagnostics_root=Path("过程文件/汇报/runner-diagnostics")))
```

`convert()` 是本地 `xlsx` skill 的兼容接口。它成功时返回 JSON 字典；失败时继续抛出
`FileNotFoundError`、`FileExistsError`、`ValueError` 或 `RuntimeError`，不允许退回到裸
`subprocess.run(soffice...)`。

所有转换 CLI 接受可选 `--work-root` 和 `--diagnostics-root`；`RunRequest` 提供对应的可选 Path
字段，`convert()` 提供同名 keyword-only 参数。未指定时保持原默认目录。Python 清理接口仍为
`cleanup_abandoned(temp_root=...)`，CLI 的 `--work-root` 映射到这个已有参数。

## 隔离和并发

槽位目录固定为：

```text
%LOCALAPPDATA%\SanAn\libreoffice-runner\slots\slot-0.lock
%LOCALAPPDATA%\SanAn\libreoffice-runner\slots\slot-1.lock
```

两个 `LockFileEx` 槽位限制实际 LibreOffice 进程树最多为两个。`queue.lock` 保护票号队列，
崩溃进程的票号和锁会根据 PID 创建时间自动失效。容量覆盖第二次输出检查、转换、验证、发布
和任务目录收尾。

每个任务使用：

```text
%TEMP%\sanan-lo-<uuid>\
  owner.json
  active.lock
  profile\
  input\
  output\
  diagnostics\
```

启动参数固定包含 `--headless --nologo --nodefault --nofirststartwizard` 和独立
`-env:UserInstallation=file:///...`。不使用默认 profile、`SAL_USE_VCLPLUGIN` 或
`--nolockcheck`。

指定 `--work-root` 后，上述 `sanan-lo-<uuid>` 目录创建在工作根中，并把子进程 TEMP/TMP/TMPDIR
设到任务的 `temp` 子目录。共享槽位仍在统一 LOCALAPPDATA 状态目录，不受工作根影响。
共享锁访问被拒绝时返回 `capacity_acquire_failed`，不启动进程；不能通过切换项目锁绕过。
工作根绝对路径不得超过 63 个 UTF-16 单元：任务 UUID 目录之外还为 LibreOffice 缓存预留 150
单元，避免已实测出现的 MAX_PATH 崩溃。超出返回 `work_root_too_long`，应显式配置更浅的项目
过程目录（默认 TEMP 太深时同样适用）；不自动迁移到配置外目录。这是兼容性预检，不能替代实际渲染。

## 进程和输出安全

根进程必须按 `CREATE_SUSPENDED`、`AssignProcessToJobObject`、`IsProcessInJob`、
`ResumeThread` 顺序启动。Job Object 有 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`；超时只结束该
Job Object，绝不按名称扫描或结束用户 LibreOffice。

PDF 由 `PyPDF2` 解析并要求至少一页。XLSX/DOCX/PPTX 做 ZIP/OOXML 验证；XLSX 额外检查
公式缓存和错误，PPTX 转 PDF 要求页数等于可见幻灯片数。最终输出先复制到同目录
`.name.tmp-<uuid>`，flush/fsync 后用不覆盖已有目标的 `MoveFileEx` 发布。

## 错误代码

```text
queue_timeout
run_timeout
nonzero_exit
no_output
corrupt_output
validation_unavailable
output_exists
input_not_found
unsupported_format
capacity_acquire_failed
job_setup_failed
work_root_too_long
publish_failed
cleanup_failed
```

失败 JSON 还会给出命令、退出码、stdout、stderr、根 PID、已归属 PID 和诊断位置。默认只保留
最小诊断 JSON；只有 `--keep-diagnostics-on-error` 保留完整任务目录。
最小报告默认位于统一状态目录的 `diagnostics`；指定 `--diagnostics-root` 时改存指定目录，
包含尚未创建任务目录的早期失败。保留完整任务时在任务内写 report.json；若同时指定诊断根，
也写独立报告。`diagnostics_error` 或 `cleanup_error` 记录附加保存/收尾失败，不覆盖主要 error。

重试与交付按 [失败处理](../SKILL.md#失败处理) 及“完成与交接”执行；错误码和 API 语义不变。
