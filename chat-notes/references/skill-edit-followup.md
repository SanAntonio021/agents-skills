# 技能修改后的发布

本次 Skill 修改已获准且未限定只改本地时，检查完成后继续发布，不再逐步询问。

1. 确认实际源码仓库及本次改动范围，只提交和推送本次内容。
2. 按 `agent-rules` 的[发布流程](../../agent-rules/references/skill-upstream-maintenance.md)和本机[同步程序说明](D:/BaiduSyncdisk/.agents/automation/ccswitch-skill-sync/README.md)执行。使用已核实的现役入口；相关执行文件来源不明或正在变化时，先处理该问题。
3. 将准确发布提交传给 `ExpectedRemoteCommit`，将该提交实际修改且仍存在的完整 Skill 集合传给 `Skills`，调用现有后台程序定向同步。可恢复的命令错误交给程序内部重试，不把命令重试实现为外层重跑整个同步程序。随后用相同提交、集合和其他范围参数运行 `-VerifyOnly`。
4. 同步和复查均返回退出码 `0`、`runtime_active`，登记有效，且提交源码与 CC Switch、Claude、Codex 的全部文件集合和 SHA-256 一致，才报告运行时文件已同步。删除的附件也必须消失；文件同步不等于当前会话已重载。

Git 混合改动、并发或命令异常按 `command-memory` 的现有方法处理；分发和运行时异常交给 `skill-check`。保留发布提交、目标集合及必要错误证据，按现有流程恢复，不复制整套故障处理规则。

只报告实际完成的部分；发布或同步失败不改用手写数据库、手工覆盖运行时或前台点击。
