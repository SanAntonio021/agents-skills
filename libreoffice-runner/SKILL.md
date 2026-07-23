---
name: libreoffice-runner
description: >
  在 Windows 上执行 LibreOffice 无界面转换、XLSX 重算、DOCX 接受修订或 Office 转 PDF 时使用。
  只要任务需要启动 `soffice`、`soffice.com`、`soffice.exe`、LibreOffice UNO，或现有 helper
  因 profile/AF_UNIX/并发转换失败，就必须使用本 skill 的统一 runner；不要直接运行 soffice。
compatibility: Requires Windows, LibreOffice, C:\Python313\python.exe with pywin32 and PyPDF2.
---

# LibreOffice Runner

这个 skill 是 Windows 上唯一允许启动 LibreOffice 无界面进程的入口。它允许两个任务并行，
但每次都创建独立 `UserInstallation`，并用 Job Object 只管理本次进程树。

## 先读

1. 读取上级规则，确认用户允许本次转换和输出路径不存在。
2. 读取 [调用契约](references/call-contract.md)。需要判断现有脚本能否迁移时读取
   [调用盘点](references/call-inventory.md)。
3. 任务涉及用户当前打开的 LibreOffice 或不确定会否影响编辑中的文件时，先停下询问。

## 调用

从 skill 根目录运行：

```powershell
& 'C:\Python313\python.exe' .\scripts\libreoffice_run.py pdf <source> <output>
& 'C:\Python313\python.exe' .\scripts\libreoffice_run.py recalc <source.xlsx> <output.xlsx>
& 'C:\Python313\python.exe' .\scripts\libreoffice_run.py convert <source> <output> --convert-to <filter>
& 'C:\Python313\python.exe' .\scripts\libreoffice_run.py accept-changes <source.docx> <output.docx>
```

常用参数：

```text
--queue-timeout 600
--run-timeout 120
--soffice <absolute path>
--json-out <report.json>
--keep-diagnostics-on-error
```

输出路径已存在时 runner 会失败，不会覆盖。CLI 的 stdout 始终是 JSON；成功退出码为 `0`。

## 运行规则

- 不直接运行 `soffice`，不复用默认 LibreOffice profile，不添加 `--nolockcheck`。
- 不按进程名结束 LibreOffice。超时由本次 Job Object 结束全部已归属 PID。
- 输入先复制到任务临时目录，LibreOffice 只写临时输出目录；格式验证成功后才原子发布。
- 同一最终输出被竞争时，只有一个任务可发布，另一个返回 `output_exists`。
- 容量固定为 `2`，调用方不能用参数提高它。入场票号保证等待者不会被后来任务反复抢占。
- `accept-changes` 使用安装的 LibreOffice Python/UNO 公共接口，不使用第三方宏或脚本。

## 失败处理

读取 JSON 的 `error`、`message`、`stdout`、`stderr`、`owned_pids` 与 `diagnostics`。失败默认保存
最小诊断 JSON，不保留输入副本；`--keep-diagnostics-on-error` 才保留整个隔离任务目录。

不要根据任何报错替换 `bootstrap.ini`。先确认是否共享 profile、队列超时、输出已存在或格式验证失败。

## 维护和测试

源码只在 `D:\BaiduSyncdisk\.agents\skills\libreoffice-runner` 修改。常规 fake-process 测试不启动
LibreOffice：

```powershell
& 'C:\Python313\python.exe' -m unittest discover -s .\tests -p 'test_*.py' -v
```

真实集成测试必须显式开启，并且测试开始时没有用户 LibreOffice 进程：

```powershell
$env:RUN_LIBREOFFICE_INTEGRATION='1'
& 'C:\Python313\python.exe' -m unittest discover -s .\tests -p 'test_integration.py' -v
```

不要修改 `.cc-switch`、`.claude`、`.codex` 或 bundled cache 中的第三方实现。更新源码后提交
`agents-skills` 仓库、推送，再通过 cc-switch 同步运行时。
