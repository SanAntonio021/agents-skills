这次在做：整理经验

结论：整理成新 skill

理由：
- 这轮经验不是单次配置记录，而是一套可以复用的 Windows 语音输入配置流程：先选工具，再接云端 ASR，再处理术语词典、日志、配置保存和 Token 安全。
- 关键坑点有复用价值。比如闪电说 API 配置要通过 UI 设置默认模型才稳定保存；火山引擎豆包 ASR 需要确认 2.0 资源 ID；用户词典要放入“太赫兹、源端、本振泄漏”等专业术语；Token 不能出现在记录、日志截图或交付文档里。
- 这类内容不适合写进 `chat-notes`。`chat-notes` 只负责判断经验该放哪里，不应该承载 Windows 语音输入工具的具体配置方法。
- 也不建议只写在当前项目里。用户以后在论文、申报书、日常输入里都会遇到同类问题，放成独立 skill 更容易复用。

建议的新 skill：
- 名称：`windows-voice-input`
- 作用：帮助用户在 Windows 上选择和配置语音输入方案，重点覆盖闪电说、火山引擎豆包 ASR、专业术语词典、日志排查和密钥保护。
- 触发场景：用户提到 Windows 语音输入、闪电说、豆包 ASR、火山引擎、语音转文字、用户词典、ASR Token、语音输入不稳定、模型配置重启后丢失等。
- 预期输出：给出当前最该做的一步；必要时列出需要用户手动核对的位置；严禁输出或保存 Token 明文。

如果用户同意，准备改这些文件：
- `D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\SKILL.md`：新建主 skill，写清楚触发条件、操作流程、安全边界和排查顺序。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\references\shandianshuo-volcengine-doubao-asr.md`：记录闪电说 + 火山豆包 ASR 的配置经验，包括默认模型保存、资源 ID、用户词典、日志路径和 Token 脱敏要求。
- `D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\evals\evals.json`：补最小测试用例，比如“API 重启后配置会不会丢”“用户词典该写哪里”“Token 能不能贴给 agent”。

明确不改这些文件：
- 不改闪电说真实配置文件。
- 不改火山引擎 Token 或任何密钥文件。
- 不改用户词典原文件。
- 不改日志文件。
- 不改 `chat-notes` 源文件。
- 不改现有全局规则文件。

本地有没有类似 skill：
- 从当前会话可见的 skill 名称看，没有专门处理 Windows 语音输入、闪电说或火山豆包 ASR 的 skill。
- `chat-notes` 只适合做这次判断，不适合放具体配置步骤。
- `command-memory` 关注 Windows 命令写法，不覆盖语音输入工具配置。
- 这次受评测限制，没有继续打开本地 skill 源码目录核对，所以本地相似度结论只能作为初步判断。

外面有没有类似 skill：
- 这次没有做外部查询。
- 如果正式创建前要更稳妥，应该再查一次官方技能站和 GitHub 上是否已有 speech-to-text、voice input、Volcengine ASR、Doubao ASR 相关 skill。
- 目前即使外部有通用语音转文字 skill，本轮经验也偏向用户本机 Windows 工作流和中文科研术语输入，仍然更适合做成本地自用 skill。

未处理：
- 还没有正式新建 skill。
- 还没有把真实路径写入 skill，因为要先确认哪些路径可以公开记录，哪些只能写成“本机路径，使用时再查”。
- 没有记录任何 Token 明文。

Git 状态：
- 审查稿阶段不提交、不推送。
- 这一步按用户要求不改源 skill。
