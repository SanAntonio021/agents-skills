这次在做：整理经验

结论：整理成新 skill

建议新建：`windows-voice-input`

拟议源码目录：`D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\`

这次只给审查稿。不改 skill 源码，不清场，不提交。

理由：
- 这轮经验不是普通录音转写，也不是会议纪要整理，而是 Windows 上怎么选、配置和排查 AI 语音输入。
- 可复用的部分已经比较稳定：闪电说作为桌面输入入口，豆包/火山 ASR 作为识别能力，用户词典和专业词维护，麦克风与系统权限检查，以及外部 skill 值不值得装的指标核对。
- 本地没有现成 skill 覆盖这件事。把这些规则塞进 `meeting-notes`、`web-access` 或 `find-skills` 都会跑偏。

准备写进去的内容：
- `name`：`windows-voice-input`
- `description`：在 Windows 上为用户选择、配置和排查 AI 语音输入方案，重点处理闪电说、豆包/火山 ASR、用户词典、专业词识别和麦克风问题。
- 触发场景：用户提到“语音输入”“闪电说”“豆包 ASR”“火山引擎 ASR”“用户词典”“专业词识别”“麦克风”“听写”“把语音输入到任意软件”。
- 预期输出：一页可执行配置清单、词典/热词维护建议、麦克风排查清单、外部工具或 skill 对比表。
- 主流程：
  1. 先分清目标是实时输入、录音转写，还是会议纪要。
  2. 优先走现成 Windows 桌面入口，不先写脚本。
  3. 核对 ASR 来源、账号/API、热词或用户词典能力。
  4. 检查麦克风设备、权限、输入音量、降噪和独占模式。
  5. 对专业词给出可维护的词表，而不是只做一次性纠错。
  6. 查外部 skill 时必须列来源、链接、GitHub stars、周下载量或安装量；查不到就写“未查到”或“未提供”。
- 建议放的资料：
  - `references/windows-mic-checklist.md`：Windows 麦克风和权限排查。
  - `references/asr-dictionary-template.md`：太赫兹、通信硬件、实验仪器等专业词模板。
  - `references/external-skill-metrics.md`：外部 skill 指标记录格式和示例。

本地有没有类似 skill：
- `meeting-notes`：只适合把语音转文字后的内容整理成会议纪要。它不处理 Windows 输入法、麦克风、ASR 服务选择和用户词典。
- `find-skills`：适合找外部 skill，并要求看安装量、来源和 stars。它可以提供外部对比方法，但不是语音输入配置 skill。
- `web-access`：只是联网和网页操作方法，不承担语音输入方案判断。
- `chat-notes`：负责判断经验该写到哪里。它不应该吸收这套 Windows 语音输入配置规则。
- 检索 `C:\Users\SanAn\.cc-switch\skills\` 和 `D:\BaiduSyncdisk\.agents\agents-skills-src\` 后，没有发现 `voice-input`、`dictation`、`asr-setup` 这类本地专门 skill。

外面有没有类似 skill：

已实际尝试的外部检索：
- `npx skills find "voice input"`
- `npx skills find "speech recognition"`
- `npx skills find "windows dictation"`
- `npx skills find "volcengine asr"`
- `npx skills find "doubao speech"`
- `npx skills find "闪电说"`
- `npx skills find "asr user dictionary"`
- 另用 Skills.sh 页面、GitHub API 和火山引擎官方文档核对来源和指标。

| skill | 来源 | 链接 | GitHub stars | 下载/安装指标 | 匹配度 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| `openai/skills@transcribe` | Skills.sh | [transcribe](https://skills.sh/openai/skills/transcribe) | 17.9K | 周安装量：1.0K | 中 | 只可参考。它处理音频文件转写，不处理 Windows 实时输入和用户词典。 |
| `github/gh-aw@Dictation Instructions` | Skills.sh / Skills CLI | [Dictation Instructions](https://skills.sh/github/gh-aw/dictation-instructions) | 4.4K | 周安装量：未提供；总安装量：32（Skills CLI） | 中 | 可参考。它的“项目术语表 + 常见误识别修正”很适合借鉴。 |
| `aradotso/trending-skills@type4me-macos-voice-input` | Skills.sh | [type4me-macos-voice-input](https://skills.sh/aradotso/trending-skills/type4me-macos-voice-input) | 40 | 周安装量：603 | 中 | 只可参考。它覆盖热键录音、ASR、LLM 后处理和文本注入，但目标系统是 macOS，不适合直接照搬到 Windows。 |
| `skills.volces.com@las-asr-pro` | Skills CLI / 火山引擎官方文档 | [火山 LAS 官方 skills 文档](https://www.volcengine.com/docs/6492/2278528) | 未提供 | 总安装量：16（Skills CLI） | 中 | 只可参考。它和火山 ASR 相关，但更像音视频文件转写流程，不是桌面语音输入配置。 |
| `marswaveai/skills@asr` | Skills.sh | [asr](https://skills.sh/marswaveai/skills/asr) | 49 | 周安装量：788 | 低 | 只可参考。它是本地离线音频转写，不覆盖闪电说、豆包/火山接口和 Windows 麦克风排查。 |

外部结论：
- 没查到直接覆盖“Windows + 闪电说 + 豆包/火山 ASR + 用户词典 + 专业词 + 麦克风”的现成 skill。
- 可以借鉴两类外部做法：一类是 ASR 转写流程，一类是听写纠错词表。
- 不能直接安装某个外部 skill 当作本地答案。

外部指标这条经验怎么处理：
- “外部搜索结果必须写清来源、GitHub stars、周下载量或安装量”不需要单独建 skill。
- 这条应该作为 `find-skills` 和 `chat-notes` 这类元流程的硬规则保留。
- 当前新版 `chat-notes` 源文件已经要求外部候选列来源、链接、stars、下载/安装指标和匹配度，所以这次不建议再改 `chat-notes`。

不改哪些文件：
- 不改 `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\SKILL.md`。
- 不改 `C:\Users\SanAn\.cc-switch\skills\chat-notes\SKILL.md`。
- 不改任何现有 skill 源文件。
- 不创建 `windows-voice-input`，除非用户之后明确说“同意，写进去”。

归档清理：
- 没有清场。当前只是审查稿，不移动文件。

未处理：
- 没有正式创建新 skill。
- 没有补 `evals/evals.json`。
- 没有提交或推送。

Git 状态：
- 当前审查稿阶段不处理 Git。
