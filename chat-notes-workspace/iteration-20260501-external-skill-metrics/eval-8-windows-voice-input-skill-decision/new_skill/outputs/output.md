# chat-notes 审查稿

这次在做：整理经验

结论：整理成新 skill。

建议新建一个本地 skill，暂定名：`windows-voice-input`。

它要解决的不是“怎么调用一个 ASR API”，而是“在 Windows 上把语音输入真正配稳定”：选型、闪电说配置保存、火山引擎豆包 ASR 2.0、用户词典、日志排查、Token 防泄露、重启后复测。这套经验已经跑通，并且以后很可能还会复用。

## 理由

- 这轮不是一次性聊天记录。它形成了稳定流程：先比较 Typeless、CapsWriter-Offline、闪电说、智谱 AI 输入法，再落到闪电说 + 火山引擎豆包 ASR。
- 关键经验跨项目可用。比如：闪电说 API 要通过 UI 设置默认模型才稳定保存；API 重启后要验证配置是否还在；火山 2.0 资源 ID、用户词典路径、日志路径都要分开核对。
- Token 安全是硬边界。新 skill 应明确：不在聊天、日志、截图、文档里暴露 Token；只记录路径、字段名、验证方法，不记录密钥值。
- 它不适合写进当前项目 README。语音输入是这台 Windows 工作站的通用工作流，不属于某个论文或申报项目。
- 它也不适合塞进 `command-memory`。`command-memory` 管的是 PowerShell/Windows 命令写法，不管桌面输入法、ASR 供应商和词典配置。

## 本地有没有类似 skill

| 本地 skill | 位置 | 重合点 | 差异 | 结论 |
| --- | --- | --- | --- | --- |
| `command-memory` | `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\SKILL.md` | Windows 路径、命令护栏、编码和搜索写法 | 不处理语音输入软件、ASR 选型、用户词典、Token 配置保存 | 不改，只借鉴“路径精确、敏感信息不乱写”的做法 |
| `web-access` | `C:\Users\SanAn\.cc-switch\skills\web-access\SKILL.md` | 可用于查火山引擎官方文档、动态页面和登录后页面 | 不处理本机 GUI 配置，不记录闪电说路径和重启验证 | 不改，作为必要时查官方页面的辅助 |
| `find-skills` | `C:\Users\SanAn\.cc-switch\skills\find-skills\SKILL.md` | 用来查外部类似 skill | 只负责发现 skill，不负责 Windows 语音输入落地 | 不改 |
| `codex-memory` | `D:\BaiduSyncdisk\.agents\agents-skills-src\codex-memory\SKILL.md` | 有“不把 API Key 写进同步 skill 源目录”的安全边界 | 这是记忆维护规则，不是语音输入配置流程 | 不改，只复用安全边界 |

本地没有直接覆盖“Windows 闪电说 + 火山豆包 ASR + 用户词典 + Token 安全”的 skill。

## 外面有没有类似 skill

我实际查了 Skills/skills.sh、ClawHub、SkillsMP、GitHub，关键词包括 `ASR`、`speech recognition`、`voice input`、`Volcengine`、`Doubao`、`SKILL.md`。没有运行 `npx skills find`，因为它可能写 npm 缓存到用户目录；本轮只允许在指定 `outputs` 目录写文件。

| skill | 来源 | 链接 | GitHub stars | 下载/安装指标 | 匹配度 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| `vahnxu/doubao-asr` | ClawHub + GitHub | https://clawhub.ai/vahnxu/doubao-asr / https://github.com/vahnxu/doubao-asr | 6 | ClawHub：1.3k downloads；8 current installs；9 all-time installs | 中 | 只可参考。它直接覆盖豆包 ASR 2.0 和凭证设置，但偏“录音文件转写 + TOS 上传”，不是 Windows 闪电说实时输入配置 |
| `agentrix-ai/skills@doubao-asr` | SkillsMP + GitHub | https://skillsmp.com/skills/agentrix-ai-skills-doubao-asr-skill-md / https://github.com/agentrix-ai/skills | 1 | 未提供 | 中 | 只可参考。它写了 Volcengine Big-Model ASR 2.0、时间戳、说话人等 API 流程，但页面元数据里出现 TTS env 名，不能直接照搬 |
| `dionren/asr-claw` | ClawHub | https://clawhub.ai/dionren/asr-claw | 未查到 | ClawHub：312 downloads；0 current installs；0 all-time installs | 中 | 不适合直接用。它是 ASR CLI，支持本地和云端引擎，也提到 Doubao，但页面标注 OS 为 macOS/Linux，不适合这轮 Windows 闪电说场景 |
| `ada20204/qwen-voice@qwen-voice` | skills.sh | https://skills.sh/ada20204/qwen-voice/qwen-voice | 5 | Weekly installs：191 | 低 | 只可参考。它是 DashScope/Qwen 的云 ASR/TTS，不是火山豆包，也不处理 Windows 输入法 |
| `theplasmak/faster-whisper@faster-whisper` | skills.sh + GitHub | https://skills.sh/theplasmak/faster-whisper/faster-whisper / https://github.com/theplasmak/faster-whisper | 6 | Weekly installs：1.1K | 低 | 只可参考。它适合本地/离线转写和字幕，不解决闪电说 + 火山配置保存 |
| `inference-sh/agent-skills@speech-to-text` | skills.sh + GitHub | https://skills.sh/inference-sh/agent-skills/speech-to-text / https://github.com/inference-sh/skills | 363 | Weekly installs：35 | 低 | 不适合。它是 inference.sh CLI 的通用转写 skill，不处理本机输入法和火山控制台 |

外部最接近的是 `vahnxu/doubao-asr`。它可以作为豆包 ASR 2.0 凭证、TOS、最小权限和安全提示的参考，但不能替代本地新 skill。

## 建议新 skill 怎么写

建议源码目录：

`D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\`

建议文件：

- `SKILL.md`：主流程和边界。
- `references/lightning-say-volcengine-doubao.md`：闪电说 + 火山豆包 ASR 的具体配置步骤、路径核对、重启复测。
- `evals/evals.json`：放 2-3 个测试提示，覆盖“帮我配 Windows 语音输入”“闪电说重启后 API 丢了怎么办”“用户词典和 Token 怎么处理”。

`SKILL.md` 里建议固定这些规则：

- 先判断用户要的是系统级语音输入、录音文件转写，还是会议纪要。不要把三者混在一起。
- Windows 语音输入选型先按实际使用体验判断：低打扰、能进任意文本框、中文术语识别、可维护词典、Token 安全。
- 闪电说配置要通过 UI 设置默认模型，并在重启闪电说/API 后复测；不要只看配置文件存在就说稳定。
- 火山豆包 ASR 2.0 要明确资源 ID、模型版本、免费额度、控制台路径、日志定位方式。
- 用户词典只写术语和路径，不写敏感值。示例术语可以包括“太赫兹”“源端”“本振泄漏”等。
- Token 永远不进入输出文件、skill 源码、聊天记录、截图说明和日志摘要。需要用户填 Token 时，只告诉他在哪个 UI 字段填。

## 准备改哪些文件

如果用户同意，下一步只新建：

- `D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\SKILL.md`
- `D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\references\lightning-say-volcengine-doubao.md`
- `D:\BaiduSyncdisk\.agents\agents-skills-src\windows-voice-input\evals\evals.json`

## 不改哪些文件

- 不改 `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes\SKILL.md`
- 不改 `D:\BaiduSyncdisk\.agents\agents-skills-src\command-memory\SKILL.md`
- 不改 `C:\Users\SanAn\.cc-switch\skills\` 和 `C:\Users\SanAn\.codex\skills\` 下的同步产物
- 不改闪电说真实配置文件
- 不写入任何 Token、API Key、Access Key、Secret Key

## 归档清理

这次只是审查稿，不清场、不归档、不移动文件。

## 未处理

- 没有正式创建新 skill。
- 没有检查闪电说当前真实配置文件内容。
- 没有记录具体 Token，也不应该记录。

## Git 状态

本轮预期只新增评测输出文件：

- `D:\BaiduSyncdisk\.agents\agents-skills-src\chat-notes-workspace\iteration-20260501-external-skill-metrics\eval-8-windows-voice-input-skill-decision\new_skill\outputs\output.md`
