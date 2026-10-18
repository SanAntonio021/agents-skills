# 原文保护发布与实际调用验收

更新：2026-09-08。本文件取代 preflight.md 中的暂停状态。

## 结论

已完成用户批准的两次发布。源码、CC Switch、Claude、Codex 文件一致；去 AI 味试验没有发布。
实际调用验收未全部通过：Codex 两例成功调用并内部校验；Claude 两例在技能可用时仍漏用。不能据此宣布原文保护已在所有实际任务中可靠执行，更不能宣布去 AI 味问题解决。

## 发布

| 内容 | 提交 | 完整同步 | 同参数复查 |
|---|---|---|---|
| 既有 Word 更新，docx 和 writing-router | da0c2758ad7577f76974c6bce58e4aa1f77c2a52 | sync-word-a8de6b24/sync.json | sync-word-a8de6b24/verify.json |
| 原文保护，只有 writing-router 的指定 5 文件 | c32d384a879b5870b07af35fd5248cacd15f7adc | sync-exact-8223044c/sync.json | sync-exact-2133e1b2/verify.json |

四份回执均为 ok=true、runtime_active；完整同步均证明非目标技能未改变。结束时再次逐文件读取并与提交内容比较：docx 的 142 文件、writing-router 的 25 文件在三个运行目录全部一致，详见 final-state.json。

Word 历史下载失败后，本轮只读探针完整取回 8,031,451 字节，HTTP 200，14.989 秒，再继续受支持的同步。首次包装器参数格式错误在发布预检前退出，源码原样恢复；修正数组传参后成功。原文保护完整同步成功后的第一次复查遇到 TLS EOF，只重试只读复查一次即成功，没有重复安装。

发布源是精确提交，不是脏工作树。Word 发布临时移开的 5 文件、原文保护发布及复查临时移开的 2 个试验文件均已按原路径和 SHA-256 恢复，各次目录有 preservation.json、source-before.json、source-after.json、restored.json。暂存区为空；其他未提交试验仍保留。未修改模型、上游、认证、持久代理或运行目录权限，未手工复制运行文件。

## 测试

本轮候选与范围检查：29 passed、1 skipped、50 subtests passed；修正测试加载设置后，3 项发布准备检查再次通过。Windows 不适用的 POSIX FIFO 项跳过。
前次全量候选检查为 60 passed、1 failed、2 skipped、50 subtests passed；唯一失败是在未改基线也复现的既有 Word 字符串断言 standing task authorization，不是原文保护新增缺陷。本轮没有为通过旧断言修改 Word。

所有材料均为新建合成文稿。仅测试前置标题、追加给定原句，原文为 UTF-8 BOM、CRLF、无末尾换行。未使用真实业务文稿。

| 有效测试 | 实际技能调用 | 原文保护结果 |
|---|---|---|
| Codex 标题 | 读取已安装入口和 exact-edit.md，成功执行 apply 与 verify | 两份工具回执哈希与独立预期哈希一致，源文件未变 |
| Codex 追加 | 同上，并回读结果正文 | 两份工具回执哈希与独立预期哈希一致，源文件未变 |
| Claude 标题 | 启动清单含 writing-router，但未调用 Skill、未读规则或工具 | 用文本重写输出，丢 BOM、CRLF 变 LF，增加空行和末尾换行 |
| Claude 追加 | 同上 | 用文本重写输出，丢 BOM、CRLF 变 LF、增加末尾换行 |

Claude 两例的文字、数字和公式本身未发现变化，失败是未按要求使用保护工具、未保留原文字节，不夸大成事实错误。全部输入文件未变。有效 Claude 测试的 assistant 消息报告 claude-opus-5；用量统计另列辅助模型，不据此推断上游真实模型身份。

Codex 两例的外部回读受 Windows 文件权限阻挡，不能声称父进程独立逐字节验收通过。标题例在回执保存前因此退出，原始事件与工具输出已保留，review.json 从记录重建检查；追加例保存了读取失败状态。没有更改 ACL 或扩大权限。两例仍有成功工具执行、内部回读及预期 SHA-256 的明确证据。Codex 使用的 .cc-switch/skills 受控副本与 .codex/skills 完全一致。

## 无效测试与补充诊断

native-runs/claude 的最初 2 例用了空 setting-sources，启动清单没有 writing-router，不能计入已安装技能验收。已保留原始失败记录，改为加载 user 后在 native-user-source 重测，没有更换模型或上游。[官方说明](https://code.claude.com/docs/en/agent-sdk/skills)确认用户技能发现受 setting sources 控制。

另在 native-slash-control 做了 1 个同模型标题对照，只在请求前加 /writing-router。记录仍只有读原文和直接写文件，未见 Skill 调用或规则读取。不能把它算成“完整规则已经加载仍执行失败”，也不能外推交互式斜杠命令的可靠性。

逐例证据见 native-review.json 及各例 review.json、events.jsonl、read-evidence.json、final.md。原始结果未修改，失败与有效测试没有混算。

## 未完成事项

- Claude 在已发现技能的情况下漏用，需要进一步区分调用方式、宿主行为与上游执行问题；本轮不凭少量样本归因或切换模型。
- Codex 测试输出的外部读取权限问题尚未处理，只接受已有内部验证证据。
- 自动触发可靠性、真实业务文稿验收与去 AI 味效果均未证明。此前去 AI 味对照及私有词表、样稿均未发布或修改。

本轮止于已批准发布及测试。若下一步要把原文保护变成不依赖模型选择的强制工作流步骤，应先明确实际写入入口和覆盖范围，再决定是否改宿主或文档工作流，不继续用追加禁词代替执行验证。
