---
name: ieee-manuscript-edit
description: 精修已有 SCI/IEEE 工程论文草稿：英文改写、润色、中文改英文、图注/引用/术语/单位核查、去 AI 写作痕迹、投稿前文字精修、Cover Letter 和 Response Letter 正文精修、合作者文件整理。用户要求“终稿规范化”“最后一轮规范检查”“缩写首次定义/全称重写”“图注自解释”“减少防御性用语”“压缩论文重复内容”“检查否定链/双重否定/反复说不”时必须使用本技能，即使没有明确说“润色”。其他触发场景包括“改英文”“精修”“投稿前文字检查”“审稿回复”“改图注”“改摘要/引言/方法/结果”“术语校准”“发给合作者”“核验修改建议”，或要求审查另一批审查员/合作者/模型给出的修改建议清单，或说论文稿“AI 味重”“像 AI 写的”“去 AI 腔”，或要求把中文技术内容改成 SCI/IEEE 英文论文。正式投稿前审查门由 `paper-review` 负责；LaTeX 模板、工程转换和编译由 `latex-paper` 负责；未指定或非 IEEE 投稿事务由 `journal-submission` 负责，明确 IEEE 投稿事务由 `ieee-journal-submission` 负责；纯英文句子质量审查的触发词还包括“检查英文句子”“删废话”“改被动语态”“精简表达”“太啰嗦”“check English sentences”“remove filler”“fix passive voice”“tighten expression”“too verbose”“check my English writing”“improve clarity”“tighten the writing”（纯句子质量审查；`sentence-polish` 已并入本技能）。
metadata:
  version: "1.0.0"
---

# SCI/IEEE 论文精修

## 目标

用于已经有草稿的 SCI/IEEE 工程论文。输入可以是中文、英文、中英混合段落，也可以是工作区里的论文草稿文件。

先确保实验事实、图文对应、引用和单位完整准确，再把文字改成更准确、更克制的英文论文风格。

## 默认回答

- 如果用户给的是文件，优先直接改文件；回复只说改了哪个文件、主要改了什么、还剩哪些待确认问题。
- 如果用户给的是局部文本，输出 `修改稿`、`主要改动`、`待确认问题`。主要改动最多 3 条，待确认问题最多 5 条。
- 全文任务默认直接改文件并给摘要；用户明确要求时，再在聊天里贴整篇修改稿。
- 用户要求"只给建议不修改""先告诉我怎么改""列出修改前后"或审查合作者/模型润色后的稿件时，默认用表格给出建议，列为 `位置`、`修改前`、`修改后`、`理由/风险`；除非用户明确要求极简回复，不要只给散点建议。
- 修改理由、待确认问题和文件取舍建议默认用中文；论文正文、英文标题、图注和投稿材料保持英文。
- 目标期刊/会议待定且任务是终稿精修或投稿前检查时，先提醒可做一次选刊判断；用户选择先精修时，结果标注为"通用 SCI/IEEE 精修"。
- 用户要求"把当前中文版本翻回英文"时，先锁定中文源文件路径，再从当前中文生成英文候选；除非用户明确要求同步，不把此前审查建议或旧英文稿自动混入。
- 涉及术语校准时，只给用户看"新增 / 冲突 / 待判定"的短术语表；已确认旧术语默认内部沿用，除非本次目标期刊或高相关论文证据明显冲突。
- 任何从本轮修改差异或外部论文提炼新表达的动作都先询问用户；未获同意不启动学习会话。

## 核心规则

1. 保留实验事实和定量信息，包括单位、频率、功率、带宽、误码率、EVM、SNR、相位噪声和动态范围。
2. 文献、DOI、citation key、实验条件和性能对比必须有可核验证据。
3. 结论强度必须跟数据一致。有限实验写成在已测试条件下成立；普遍结论需要充分证据支撑。
4. 引用紧跟所支撑的论点；修改时保持引用和对应句子的关系。技术参数或方法需要引用依据时，查该领域是否有多篇先例；声称"广泛采用"/"统一参考"/"consistently"时，必须有 3 篇及以上文献支撑；优先溯源到综述论文或标准文档，比只引实验论文更有说服力。
5. 图注说明实验对象、状态定义、关键参数和主要现象，少用纯 `(a)`、`(b)` 标签堆砌。
6. 中文改英文时，先保留技术主线，再按英文论文的信息顺序重写。
7. 同一任务内术语要稳定，例如系统、链路、工作点、频谱分量、代表性谱线、测量链路和性能指标保持固定叫法。
8. 专业术语先校准再润色。技术名词优先使用本领域正式表达。
9. 语言质量复查只改表达方式，科学内容、数据、技术结论和引用含义保持原边界。
10. 审查合作者或 Claude 润色后的稿件前，先锁定准确文件路径、语言版本和实际修改章节；用户只要求局部审查时，只审指定章节，不混用旧稿或另一语种候选稿。
11. "IEEE 风格"只表示语言、结构、引用、图注和常见工程论文写法；"IEEE 模板符合性"必须有目标期刊/会议官方模板、作者指南或投稿系统要求作为依据。
12. 缩写按独立作用域处理：摘要、正文、每个图注和每个表注分别计数。摘要用过的缩写，正文首次出现仍须重新定义；一个图注或表注不能借用正文或另一图表注的定义。摘要内只出现一次的缩写不引入缩写、直接写全称，复用的才在摘要定义。审计时对每个缩写分别检索 `(缩写)` 的显式定义与裸用处，并在各作用域核对首现（2026-07-11 IQ-MIMO 论文实战定型：正文 4 个缩写通篇裸用、全靠摘要定义，属违规）。
13. 否定链审计只给人工复核候选。固定间接否定或同句多个否定单元不等于错误；不得自动删除、反转或改成正面句式，尤其要保护科学限定和证据边界。

## 本地文稿版本保护

实际写入本地 `.md` 或 `.tex` 前，读取并执行 [../writing-router/references/document-version-protection.md](../writing-router/references/document-version-protection.md)。后续出现明确里程碑确认或旧版本查找、比较、恢复请求时也读取。一轮精修完成并验证通过后只创建本地 commit；不配置远程、不 push。纯审查、聊天内改句和只读核验不触发。

## 工作流程

1. 先判断用户要做哪类工作：英文精修、中文改英文、分节重写、图注/引用检查、投稿前文字精修、Cover Letter/Response Letter 正文精修、终稿精修、终稿规范化、否定链/间接否定审计，或发给合作者前整理文件。用户要整体投稿前审查或最终 Submit 门时转 `paper-review`。
2. 目标期刊或会议待定，且用户正在做终稿精修或投稿前文字精修时，先提示可做一次选刊判断。选刊判断要联网核验期刊官网、scope 和近期文章；用户选择先精修时，按通用 SCI/IEEE 版本处理。
3. 目标期刊或会议已知时，先找用户提供的模板、作者指南或官方页面；依据缺失时，做通用 SCI/IEEE 精修，并把"目标期刊模板待核对"列为待确认问题。
4. 目标期刊或会议待定，但用户明确只要语言精修时，默认按 IEEE journal article 的克制工程写法处理，版式保持通用。
5. 涉及专业术语时，先按"术语校准与全局术语库"执行：读术语库、识别新增/冲突/待判定术语、必要时联网核验，再进入句子润色。
6. 写作或精修论文正文时，读取 `D:\BaiduSyncdisk\.agents\vocab\vocab-full.md`、`scientific-terminology-bank.md`、`academic-expression-bank.md` 和结构化例外表；只加载状态为 `已确认` 且领域/目标期刊/章节功能匹配的记录。用户硬禁用优先于普通术语建议，未经显式例外确认不得覆盖。
7. 先检查实验事实、章节安排和关键结论依据。有疑点时先列待确认问题；终稿英文等事实明确后再生成。
8. 再做五项语言质量复查：删掉空话和重复句，改顺主语和动词，拆开过长的句子，固定术语，核对数字、单位和引用。需要独立完整句子审查（full-review / section-review / targeted / interactive 模式）时，读取 [references/sainani-sentence-review.md](references/sainani-sentence-review.md)。
9. 再修改正文：压缩冗余，统一术语，理顺句子，控制结论强度。
10. 最后检查缩写首次定义（按核心规则 12 的独立作用域审计）、引用位置、图表标题、单位符号和中英文版本的一致性。终稿规范化任务先按下节运行 convention audit；所有写入完成后再运行 `scripts/audit_writing_memory.py` 做独立复扫。复扫不通过时停止交付。

## 术语校准与全局术语库

术语校准的目标是保护专业词，同时控制用户审阅负担。默认使用活数据术语库 `D:\BaiduSyncdisk\.agents\vocab\scientific-terminology-bank.md`；技能内 [references/sci-terminology-bank.md](references/sci-terminology-bank.md) 只作兼容说明。表达模式、候选、结构化例外和状态机见 [references/writing-memory-schema.md](references/writing-memory-schema.md)。

执行顺序：

1. 先读取活数据术语库，找出与当前稿件领域、目标期刊、章节功能和关键词相匹配的 `已确认` 术语；`候选`、`待审`、`待迁移`、`已拒绝` 不得自动影响润色。
2. 用户明确硬禁用优先于普通术语建议。只有术语记录或结构化例外明确标记 `例外覆盖用户禁用=是` 且用户审阅为 `是` 时才能覆盖；任何其他重叠都标为"冲突待审"。
3. 从当前稿件中提取高频中文术语、英文术语、缩写、图注关键词和领域特有表达。
4. 对新增、冲突、待判定、跨领域复用风险高的术语做联网核验；已审且上下文一致的术语直接沿用。联网或从本轮差异学习前，必须先取得用户同意。
5. 联网核验优先级：目标期刊近期正式论文和高相关正式论文 > 目标期刊作者指南或官方页面 > 用户已审术语库和当前稿件定义 > ScienceDirect Topics、权威教材或综述定义。ScienceDirect Topics 可作为入口和辅助定义，最终依据优先取正式论文或官方来源。
6. 工具路由：普通网页检索、目标期刊页面、ScienceDirect Topics、LetPub 或动态页面用 `web-access`；已经有题名、DOI、出版社页或需要正式论文 PDF 时，用 `paper-download` 获取正式版本和原文证据；已有本地 PDF 且需要总结或术语摘录时，用 `paper-summary`。
7. 如果需要从论文原文中确认术语，优先读取正式发表论文的标题、摘要、关键词、图注、方法段和结论附近表述；只提炼术语、标准搭配或不超过 4 个连续实词的抽象模式，不保存完整句子、图注或方法描述。来源必须写入 DOI、正式链接或官方页面。
8. 润色前只向用户展示短表，列出需要审阅的术语：

| 状态 | 中文术语 | 推荐英文 | 适用领域 | 依据 | 需要用户确认 |
|---|---|---|---|---|---|
| 新增待审 | 术语 | term | THz communication | 目标论文 / DOI / URL | 是 |
| 冲突待审 | 术语 | term A / term B | photonics | 已审术语 vs 本次论文证据 | 是 |
| 待判定 | 术语 | candidate term | device / system | 证据待补 | 是 |

9. 用户确认后，统一调用 `style-vocab` 收录模式完成写入；展示完整 15 列记录后经用户明确确认才写入活数据术语库，并在候选台账填写迁入位置；拒绝候选写入 `已拒绝` 及理由，不能删除或绕过。
10. 术语库保存可复用表达；临时句子、整段翻译和待核验说法留在当前稿件里处理。每轮最多展示 3 条候选。

## 终稿精修

当用户已经有一版可交付初稿，当前步骤明确是提交前精修、导出前整理或审稿前整理时，按 [references/draft-finalization-rules.md](references/draft-finalization-rules.md) 执行。

核心原则：先确保引用和数据完整，再统一术语和压缩冗余。详细规则见参考文件。

## 终稿规范化

当任务涉及缩写作用域、图注自解释、防御性元话语、否定链/间接否定或重复内容中的任一项，先读取 [references/draft-finalization-rules.md](references/draft-finalization-rules.md)，再按以下顺序执行：

1. v1 只接受英文 Markdown 和单文件 LaTeX。Word/PDF、多文件 LaTeX 和中文论文转入相应既有流程；不要把不完整解析结果写成全文已通过。
2. 修改前记录输入文件 SHA-256，并运行只读审计：

   ```text
   python -X utf8 scripts/audit_manuscript_conventions.py --input <path> --format json
   ```

   退出码 `1` 表示发现问题，不是脚本故障；退出码 `2` 才表示输入或解析错误。
3. 只自动采用 `safe_findings` 中带精确 `span` 和 `replacement` 的项目。缩写补全只使用同一稿件中唯一且一致的显式 `full form (ACRONYM)` 映射；不从常识、领域词表或外部资料猜全称。
4. `review_candidates` 和 `unresolved` 只报告或经人工判断后修改。否定链固定使用 `LANG_NEGATION_CHAIN` / `negative_construction`，按“编号/配对 → fixed_indirect → atomic”顺序合并命中，不带自动替换；`fail...to`、`neither...nor` 和 `not only...but also` 的配对不能吞掉同句其他否定。完整分类、屏蔽范围和优先级见终稿规则。`protected_qualifiers` 是需要保留的证据边界，不是删除清单。
5. 对每个图注和表注逐项核对对象、条件、面板、图例、单位、统计元素和主要读法。本地图片存在时必须查看图片后判断；脚本不做图像语义识别。
6. 修改完成后对最终文件重新运行同一审计。交付的 SHA-256、行号和计数必须来自重跑结果，不能沿用修改前报告。

该模式是文字与约定层的终稿整理。整体投稿审查门仍由 `paper-review` 负责；LaTeX 模板、工程转换和编译仍由 `latex-paper` 负责；词级偏好仍由 `style-vocab` 负责。

## 审查建议的双镜头对抗核验（2026-07-11 由 IQ-MIMO 英文稿全文审查定型）

批量产生的修改建议（多审查员并行初审、合作者或另一模型给的润色清单）在呈给用户前，先过两个独立核验视角，各自以"尽力否决"为立场：

- **术语与事实镜头**：声称的术语问题是否真实存在？原文是否其实是 IEEE 正式论文的标准用法（拿不准就联网查正式论文实例）？建议的改法本身是否领域标准？违反项目口径直接否决。
- **母语地道性镜头**：原文真的不地道，还是审查员的个人偏好（churn）？改法是否比原文更地道、是否引入语法错误或改变技术含义？纯风格偏好、改了没实质提升的，否决。

裁决规则：两方一致否决才删；单方否决标"存疑"留用户裁决；有一方修订改法则采用修订版。实战效果：130 条初审过滤到 89 条，拦下的假阳性包括 "serve a role"（标准搭配被误报）、"are additive noise"（数学写作标准用法被误报）这类看似有理的建议。核验方要求逐条给中文理由，便于用户复核。

## 去 AI 味（学术模式边界）

论文稿需要清理 AI 写作痕迹（用户说"AI 味重""像 AI 写的"，或引用 Humanizer-zh 这类通用去 AI 味方法）时，通用方法要加学术边界后才能用（2026-07-07 由 IQ-MIMO 论文实战定型）：

- **不适用的通用规则**：注入个性、第一人称、幽默、表达不确定感——期刊论文保持客观工程口吻，去 AI 味不等于加人味。
- **红线**：所有数值、单位、术语、LaTeX 命令原样保留；结论的方向和力度不得削弱；写作禁忌类规则（如项目大纲中的 overclaim 禁令）优先级高于文风调整。
- **重点清理的学术 AI 腔**：`是……而非……`/`不是……而是……`句式（改正面陈述"由 A 变为 B"，或拆成事实句）；"换言之/需要说明的是/据此"引出的金句式总结句（多数可整句删除，让事实自己说话）；防御性表述（"本文不主张……""为保证公平性……""贡献定位于……"——改写成中性事实陈述，把结论留给读者，不删论证本身）；行话直译（"口径"要说清是什么统计方式）。用户自维护的词级替换对由 `style-vocab` 和 `vocab-full.md` 处理，不在本节继续扩清单。
- **统计量必须带含义**：中位数、百分位数、CDF 出现时，用一句话说清读者该读出什么（如"中位数 4.6 dB，即一半频点低于该值"），不要只报数。
- 交给子智能体重写时，把上述边界连同数值/术语红线清单写进任务书，逐项列明待保留数字。

## 目标期刊/会议

- 通用 SCI/IEEE 精修保证语言、结构和常见格式更接近工程论文；具体期刊符合性以官方模板和作者指南为准。
- 选刊结合论文主题、创新点、实验完整度、目标读者、期刊 scope 和近期发文来判断。
- 需要最新模板、作者指南或引用规则时，先联网核验官方来源，优先使用期刊官网、IEEE Author Center 或会议官网。
- IEEE 官方 Word/LaTeX 模板先查技能内 `assets/ieee-official-templates/`；资源里没有目标期刊、年份或格式时，再从 IEEE 官方 Template Selector 下载，下载后同步回技能资源。
- 目标期刊缺失时，回复中明确当前版本为通用版本。

## 发给合作者前

当目录里已经有多份 Markdown、Word 或中间文件时，先降低用户的检查负担：

1. 根目录只保留合作者会看的文件，以及一份简短的待确认问题说明。
2. 源文件、历史版本和中间文件优先移到 `_archive_日期` 这类归档目录；移动或删除前先说明对象并取得用户确认。
3. 待确认说明只保留仍需处理的问题。
4. 如果已有版式正确的 Word 母版，优先复制母版再回填新内容。
5. 标黄和批注只用于关键修改、争议点和需要合作者确认的位置。
6. 中英文版本的事实表述要同步一致。英文标题、结论强度、单位和术语改过后，中文稿也要检查是否需要同步。

## 参考文件

按任务只读取需要的参考：

- 语言精修：读 [references/manuscript-refinement-checklist.md](references/manuscript-refinement-checklist.md)。
- 独立完整 Sainani 五轮句子审查：读 [references/sainani-sentence-review.md](references/sainani-sentence-review.md)。
- 中文改英文或分节重写：读 [references/manuscript-refinement-checklist.md](references/manuscript-refinement-checklist.md) 和 [references/section-by-section-review.md](references/section-by-section-review.md)。
- 术语校准和长期复用：读 `D:\BaiduSyncdisk\.agents\vocab\scientific-terminology-bank.md` 和 [references/writing-memory-schema.md](references/writing-memory-schema.md)；技能内旧术语库只作兼容说明，只把用户审过或带明确来源的术语通过 `style-vocab` 收录模式写入活数据表。
- 术语需要联网证据：用 `web-access` 查网页、目标期刊页面和 ScienceDirect Topics；需要定位或下载正式论文 PDF 时，调用 `paper-download`；已有本地 PDF 需要总结或术语摘录时，调用 `paper-summary`。
- IEEE 风格、引用、图表和模板：读 [references/ieee-structure-and-style.md](references/ieee-structure-and-style.md)。
- IEEE 官方模板资源：读 [references/ieee-official-template-cache.md](references/ieee-official-template-cache.md)，优先复用技能内 `assets/ieee-official-templates/` 的 Word/LaTeX 模板。
- 终稿精修或实验段落终稿化：读 [references/draft-finalization-rules.md](references/draft-finalization-rules.md)；按需读 [references/writing-samples.md](references/writing-samples.md)。
- 用户自维护词级偏好和交付前扫用词：用 [../style-vocab/SKILL.md](../style-vocab/SKILL.md)，词表数据在 `D:\BaiduSyncdisk\.agents\vocab\`。
- 判断外部技能来源和边界：读 [references/upstream-skill-notes.md](references/upstream-skill-notes.md)。
- 涉及 Word 版式、批注、标黄或母版回填时，交给 `docx`；本技能只判断论文内容和文件角色。Markdown 内容冻结后，按 [Markdown 到 DOCX 交接契约](../writing-router/references/markdown-docx-contract.md) 交接，不在未确认时直接生成正式 DOCX。

## 验收

- 事实新增项均有证据。
- 数值、单位和实验条件保持原边界。
- 术语、缩写、符号和变量保持一致。
- 新增、冲突或待判定术语已经形成短审阅表；用户确认后才写成"已确认"。
- 术语来源能追溯到目标期刊/高相关正式论文、官方页面、用户审过的术语库或明确标注的辅助来源。
- 复扫报告记录稿件、词表、术语库和脚本版本/哈希；`violations`、`unresolved` 或 `schema_errors` 非空时，交付状态必须是“复扫未通过”。
- 引用仍然紧跟对应论点。
- 图注和正文能互相对应。
- 占位符、截断标记和重复套话已清理。
- 冗余套话、不必要的被动句和过度名词化已清理。
- 关键术语保持固定叫法。
- 如果声称符合某个具体期刊/会议，必须能指出所依据的官方模板或作者指南。
- 回复保持短，优先给用户下一步真正需要看的内容。

## 边界

- 如果实验事实、章节安排或关键结论依据还需确认，先指出缺什么，当前只做问题清单。
- 正式内容批准后，再启动终稿精修流程。
- 用户只要求简单润色，但任务类型、结构或证据依据待定，先判断该走哪个写作流程。
- 结构重写、补章节、补实验依据和补申报论证走对应前置流程。
- 缺失证据标出后退给前置步骤处理。
- 引用位置正确优先于句子流畅。
- ScienceDirect Topics、机器生成摘要和二手网页只作为辅助入口。
- 用户已审术语保持稳定；如本次正式论文证据冲突，先列为冲突待审。
- 如果用户要求严格套用某个 IEEE 模板，以用户提供的模板或 IEEE 官方页面为准。
- 如果需要最新模板、目标期刊作者指南或引用规则，先核验官方来源。
- 如果任务主要是 Word、PDF 文件操作，按对应文件技能处理；md 转 LaTeX、套模板、BibTeX、编译和按期刊/页面要求的 source 打包转给 `latex-paper`。本技能只负责论文内容、风格和文件取舍判断。
- Cover Letter 和 Response Letter 正文仍由本技能处理。未指定或非 IEEE 投稿系统、作者与声明、决定、返修上传、录用后、版权费用或校样事务转给 [../journal-submission/SKILL.md](../journal-submission/SKILL.md)；明确 IEEE 时转给 [../ieee-journal-submission/SKILL.md](../ieee-journal-submission/SKILL.md)。任何最终 Submit 请求先转 [../paper-review/SKILL.md](../paper-review/SKILL.md) 完成审查门。
- 纯英文句子质量审查现由本技能直接处理；需要独立句子审查模式时，读取 [references/sainani-sentence-review.md](references/sainani-sentence-review.md)。
- 如果用户只想维护词表、收录"别用 X，用 Y"或交付前扫词，转给 [../style-vocab/SKILL.md](../style-vocab/SKILL.md)。如果用户想处理整体 AI 写作痕迹、句式和结构，转给 `humanizer-zh`；SCI/IEEE 论文正文里的 AI 腔先按本技能的学术边界处理。
