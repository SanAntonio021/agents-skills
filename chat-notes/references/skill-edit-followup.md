# 技能发布操作

授权、触发和完成标准见 [SKILL.md 第 5 项](../SKILL.md#5-提交发布与运行时同步)；本文件维护具体操作与恢复方法。

1. 确认实际源码仓库及本次改动范围，只提交和推送本次内容。
2. 按 `agent-rules` 的[发布流程](../../agent-rules/references/skill-upstream-maintenance.md)定位维护目录中的 `automation/ccswitch-skill-sync/README.md`，读取后使用同目录 `Invoke-CcSwitchSkillSync.ps1`。相关执行文件来源不明或正在变化时，先核实现役版本。
3. 用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <现役脚本路径>` 调用后台程序，将准确发布提交传给 `ExpectedRemoteCommit`，将该提交实际修改且仍存在的完整 Skill 集合传给 `Skills`；需要时用 `SourceRoot` 指定实际源码 Git 根。其他范围参数按工具说明传入，并在后续复查中保持不变。
4. 同步成功后，用完全相同的提交、技能集合和其他参数追加 `-VerifyOnly`。检查回执中的文件集合差异、逐文件 SHA-256、来源登记和启用状态；删除的附件不能残留。

发布或复查失败时，先保留原参数和失败回执，按同参数执行只读核验，再依现役工具说明恢复。可恢复的命令错误交给程序内部重试，不把命令重试实现为外层重跑整个同步程序。Git 云盘干扰或并发写入可查 [Windows Git 局部排错](../../git-branch-consolidation/references/recovery-contract.md#windows-git-局部排错)，不因此启动全面收口；分发和运行时异常交给 `skill-check`。需要接续恢复时沿用已有维护记录，恢复后更新状态；普通发布成功在对话中报告，不向业务项目说明追加发布流水。
