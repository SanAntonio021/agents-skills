# LibreOffice Runner 调用契约

## 前提

- 仅支持 Windows。
- 运行解释器固定为 `C:\Python313\python.exe`，需要 `pywin32` 和 `PyPDF2`。
- LibreOffice 默认寻找 `soffice.com`，也可用 `--soffice` 指定已存在的绝对路径。
- 输入必须是文件，输出路径不得存在，输入和输出不能相同。

## CLI

```text
python scripts/libreoffice_run.py pdf <source> <output>
python scripts/libreoffice_run.py recalc <source.xlsx> <output.xlsx>
python scripts/libreoffice_run.py convert <source> <output> --convert-to <filter>
python scripts/libreoffice_run.py accept-changes <source.docx> <output.docx>
python scripts/libreoffice_run.py cleanup [--older-than <seconds>]
```

`pdf` 支持 DOC/DOCX/ODT、XLS/XLSX/XLSM/XLTX 和 PPT/PPTX/ODP。`recalc` 只支持
XLSX/XLTX 到 XLSX。`accept-changes` 只支持 DOCX 到 DOCX。

## Python API

```python
from pathlib import Path
from libreoffice_runner import RunRequest, convert, run

report = run(RunRequest("pdf", Path("input.docx"), Path("output.pdf")))
result = convert("recalc", Path("input.xlsx"), Path("output.xlsx"), timeout=120)
```

`convert()` 是本地 `xlsx` skill 的兼容接口。它成功时返回 JSON 字典；失败时继续抛出
`FileNotFoundError`、`FileExistsError`、`ValueError` 或 `RuntimeError`，不允许退回到裸
`subprocess.run(soffice...)`。

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
publish_failed
cleanup_failed
```

失败 JSON 还会给出命令、退出码、stdout、stderr、根 PID、已归属 PID 和诊断位置。默认只保留
最小诊断 JSON；只有 `--keep-diagnostics-on-error` 保留完整任务目录。
