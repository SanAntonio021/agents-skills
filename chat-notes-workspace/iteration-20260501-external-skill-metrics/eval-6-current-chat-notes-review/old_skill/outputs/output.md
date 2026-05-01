这次在做：整理经验

结论：整理成新 skill。另有一条规则建议补到现有 `find-skills`，不要塞进 `chat-notes`。

建议新建的 skill：`windows-voice-input-setup`

它要解决的问题不是“怎么写一段语音输入总结”，而是以后再遇到 Windows 语音输入、ASR、用户词典、专业词识别、麦克风选型时，有一套固定检查顺序，避免每次重新比较。

准备写进去的内容：
- 先问清使用场景：是给 AI 输入长文本、日常口述、会议转写，还是命令控制。
- 先定约束：Windows、中文为主、夹杂太赫兹/通信专业词、能否联网、是否能接受云端 ASR、预算和延迟要求。
- 再比较方案：输入法或桌面工具、ASR 后端、用户词典/热词、专业词识别、麦克风和降噪。
- 必须保留一组测试短句，里面包含用户常用专业词，比如太赫兹、F-band、链路预算、相位噪声、误码率、光电探测器。
- 输出要直接给推荐组合、备选组合、放弃原因和下一步配置动作。

建议补到现有 `find-skills` 的规则：
- 查外部 skill 或开源工具时，必须写清来源链接。
- GitHub 项目要写 GitHub stars。
- npm、PyPI、插件市场这类包或市场页，能查到就写周下载量、安装量或页面显示的安装指标。
- 查不到就写“未查到”或“未提供”，不要自己估数字。

理由：
- 这轮讨论里的语音输入配置流程以后还会复用，已经超过一次性聊天建议。
- 本地没有看到专门处理 Windows 语音输入、ASR 热词和麦克风配置的 skill。
- `chat-notes` 只负责判断经验写到哪里，不适合承载具体语音输入配置方法。
- 外部 skill 指标规则属于“怎么评价外部 skill 是否值得安装”，更适合放进 `find-skills`。

本地有没有类似 skill：
- `find-skills`：相近点是外部 skill 搜索；差别是它不负责 Windows 语音输入方案本身。
- `research-lookup`：相近点是联网查资料；差别是它偏科研和信息检索，不负责本机语音输入配置。
- `command-memory`：相近点是 Windows 环境和命令习惯；差别是它不处理 ASR、词典、麦克风。
- 当前本地目录没有看到 `voice-input`、`speech-to-text`、`asr`、`dictation` 这类专门 skill。

外面有没有类似 skill：
- SkillHub `speech-to-text`：来源 https://www.skillhub.club/skills/inferencesh-skills-speech-to-text ，源码 https://github.com/inference-sh/skills 。用途是用 inference.sh CLI 调 Whisper 模型转写音频。GitHub stars：390。周下载量/安装量：未提供。
- Cult of Claude `Super Voice Assistant`：来源 https://cultofclaude.com/skills/super-voice-assistant/ ，源码 https://github.com/ykdojo/super-voice-assistant 。用途是 Claude Code 语音助手，偏 macOS。GitHub stars：187。周下载量/安装量：未提供。
- Claude Plugins `voice-interface-builder`：来源 https://claude-plugins.dev/skills/%40daffy0208/ai-dev-standards/voice-interface-builder ，源码 https://github.com/daffy0208/ai-dev-standards 。用途是开发语音界面，不是配置 Windows 输入法。GitHub stars：27。周下载量/安装量：页面未明确提供。
- TypeWhisper for Windows：来源 https://github.com/TypeWhisper/typewhisper-win 。它不是 agent skill，但和 Windows 语音输入高度相关，包含全局听写、词典、工作流、本地和云端 ASR。GitHub stars：86。周下载量/安装量：未提供。
- `foges/whisper-dictation`：来源 https://github.com/foges/whisper-dictation 。它是 Whisper 听写应用，不是 agent skill。GitHub stars：215。周下载量/安装量：未提供。
- `openai/whisper`：来源 https://github.com/openai/whisper 。这是 ASR 引擎参考，不是语音输入 skill。GitHub stars：98698。周下载量/安装量：未提供。
- `ggml-org/whisper.cpp`：来源 https://github.com/ggml-org/whisper.cpp 。这是本地 Whisper 推理参考，不是语音输入 skill。GitHub stars：49225。周下载量/安装量：未提供。

准备改哪些文件：
- 新建 `D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input-setup\SKILL.md`。
- 如果用户同意，再核对 `find-skills` 的真实源码目录，把“外部 skill 指标必须写清来源和公开指标”补进去。

不改哪些文件：
- 不改 `C:\Users\SanAn\.cc-switch\skills\chat-notes\SKILL.md`，这是同步产物，不是源码修改目标。
- 不改旧版或新版 `chat-notes`，因为语音输入配置方法不属于它的职责。
- 不改全局 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md`，这次不是多代理规则变更。

归档清理：
- 这一步只是审查稿，不清场，不移动文件。

未处理：
- 还没有正式创建新 skill。
- 还没有修改 `find-skills`。
- 外部项目的安装量或周下载量多数页面未提供，不能补数字。

Git 状态：
- 这一步不提交，不推送。
