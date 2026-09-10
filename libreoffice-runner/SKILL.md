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

1. 读取当前任务和文件，复用已经明确的转换、重算或接受修订授权；只读检查不启动转换。
   普通交付按项目命名选择尚不存在的新版本路径；用户明确指定固定路径时保留该要求，冲突处理见下文。
2. 读取 [调用契约](references/call-contract.md)。需要判断现有脚本能否迁移时读取
   [调用盘点](references/call-inventory.md)。
3. 按实际操作判断影响：处理已保存文件的副本，且独立 profile、Job Object 和新输出路径能隔离
   本轮操作时，自主执行。需要未保存的编辑内容时先说明所需版本；确需操作用户窗口或隔离归属
   无法查明时才询问，只暂停相关步骤。现有集成测试的“无用户进程”前提不扩大为日常转换限制。

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

输出路径已存在时 runner 会失败，不会覆盖。CLI 的 stdout 始终是一行 UTF-8 JSON（含行末换行，
不受 Windows 控制台代码页影响）；`--json-out` 也写入 UTF-8 JSON。成功退出码为 `0`。
普通交付遇到重名时，由调用方选择新的版本名后继续；runner 的不覆盖行为保持不变。
固定输出路径发生冲突时先读取当前文件并核对已有授权，不能擅自换路径或删除旧文件来绕过保护。
需要替换时沿用对应文档技能的原稿保护流程，runner 仍写入新路径；无法确定取舍时才询问。

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

先按错误原因处理：队列繁忙时等待后重试；运行超时先查诊断，确有耗时依据时调整本轮时限；
普通输出重名改用新版本名；输入或格式问题交给对应文档技能修正已授权内容。复用当前授权完成
必要重试，检查修正后的结果；相同失败且没有新线索时报告具体缺口，继续不依赖该转换的工作。
进程归属建立失败时保留失败结果。排障沿用隔离机制，不替换 `bootstrap.ini`、绕过 runner
或结束用户进程。

## 完成与交接

转换成功并通过 runner 文件校验后，把实际输出和检查结果交回 `docx`、`xlsx`、`pptx` 等调用方，
由其完成任务所需的内容、版面或计算检查。文件可解析不等于排版正确，LibreOffice 转换不代替
明确要求的 Word、Excel 或 PowerPoint 原生验证。完成适用检查即可交付；未完成的明确检查如实说明。

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

源码修改和定向发布复用 [agent-rules](../agent-rules/SKILL.md) 的后台流程，核对源码与运行副本；
不手工修改分发目录或第三方实现。
