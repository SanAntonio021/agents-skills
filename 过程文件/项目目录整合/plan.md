# 项目目录整合技能修改方案

## 目标与边界
只修改 project-organizer 的说明、参考、配置示例、现有 PowerShell 程序及评测。不整理真实业务目录，不改变科学算法，不新增技能或审批系统。核心完成标准：一个项目的全部有效内容进入统一目录，Markdown 与实际引用适配新位置，经核验后按授权退役原目录；不默认建立历史版本副本。group 模式保留，独立项目仍保持各自结构和仓库，不自动触发单仓库分支整理。

## 目录与协作
统一原则、按项目设计目录；只创建需要的分类，普通资料浅层，代码、论文及实验数据保留必要内部关系。使用已确认的实验输出规范与 Zotero 文献管理分工，既有实验内容只按本次明确映射迁移，不自动改历史格式或操作 Zotero。默认过程材料放目标项目的“过程文件/整理主题”，不额外建审计顶层；Git 元数据沿用现有外置保护。
展示来源、目标目录树和整合/退役范围，一次准确授权覆盖必要步骤。保留用户明确要求的单独目录树审查或只读边界；删除自动 ask-first、分三次批准、让用户复制哈希的说明及冲突评测。工具哈希仍绑定实际内容，哈希变化需要重新核实与封定计划，但只有范围/重要取舍变化才重问用户。
读取每份现行说明与记录，合并仍有用内容，更新路径与使用说明，历史记录保持事实。可判断的文件冲突由智能体结合差异和检查解决，不按修改时间选胜者；无法判断的实质冲突保留相关来源，仅暂停依赖动作。

## 执行方式与接口
优先在迁移前准备最终整合内容和引用改动副本，再把副本纳入既有迁移计划；不在旧计划执行后直接改文件却沿用旧哈希验收，也不新增通用自动改写引擎。智能体负责内容判断，程序负责确定性部署、关联与完整性验证。

### 最小必要接口清单（已对照真实代码，标注修改点）
以下每项都是当前程序硬拒或缺失、不改则本方案无法实现的点；除此之外不扩大接口。

1. `ProjectOrganizer.psm1:591` 现为 `if ([string]$config.schema_version -ne '1.0') { throw }`，改为白名单 `@('1.0','1.1')`，并仅在 1.1 下读 `integration_manifest`。
2. `ProjectOrganizer.psm1:655` 现为 `version_policy -notin @('preserve_all','approved_selection') { throw }`，增加 `integrate`；同步 `references/config-and-manifests.md:37` 表格、`SKILL.md:88` 与 `Build-ProjectInventory.ps1:349` 的审阅文本。
3. `ProjectOrganizer.psm1:609-610` 现在双向报错 `audit_root overlaps target_root.`，改为单向：允许 audit_root 严格在 target_root 之内，仍禁止相等、audit_root 为 target_root 祖先、以及落入任一来源。
4. 新增 `-OutputDir` 必须归属 `audit_root` 的断言（现在完全没有校验，三个 Build-*/Test-* 入口均可任意写出）。
5. 过程子树排除必须落在三处真实扫描点：`Build-ProjectInventory.ps1:126`（`$targetScan`）、`Build-ProjectInventory.ps1:157`（`$targetAfter` 并发快照）、`Test-OrganizationAcceptance.ps1:100`（`$actualScan`，否则过程文件会被当成 `unapproved_extra_path`）；同时覆盖空祖先目录的 `empty_directory_not_approved` 记账与空间统计。
6. 已有目标安装目前从原语层就不可能：`Copy-POFileAtomicVerified`（`:384`）、`Move-POFileVerified`（`:415`）、`Copy-PODirectoryVerified`（`:441`）均 `throw "Target already exists"`。需一个“先保护再替换”原语（目标盘临时文件→校验→原目标存证入过程目录→原子替换）加一个新动作 `install_integrated_output`，并在 `Invoke-OrganizationPlan.ps1` 的 `default { throw "Unsupported action" }` 分支前注册、写入 `$priority` 排序表。
7. `Build-OrganizationPlan.ps1:153-156` 的 `$boundPaths` 现在只含配置/清单/树/违规/动作/空间/错误/review；必须补入 `integration.json`、准备好的输出文件、被改已有目标的原件副本、检查材料，否则这些文件不在 `plan.sha256` 保护范围内。
8. 新增目标侧并发复检：`Invoke-OrganizationPlan.ps1` 的 `Assert-SourceStateFresh` / `Assert-SourceInventorySet` 只重掃来源，需对应的 `Assert-TargetStateFresh`（对照 `target-state.json`）才能兑现“执行前检查输入与原目标未变”。
9. `Test-RetirementAcceptance.ps1` 的 `target_file` 循环现在拿 `Get-POStableSha256 -Path $action.target_path` 比 `$action.sha256`，而那是 actions.csv 里的**旧源哈希**；整合输出必须改比最终输出哈希，否则正确的整合会被判为失败。
10. `Build-RetirementPlan.ps1` 的内层 `switch` 对新动作会落到 `default { hold_unplanned }`（安全但永不可退役），需显式整合分支：仅当该输入已被 integration.json 完整覆盖、最终输出哈希就位、所需检查通过时才给可退役动作。
11. 去重必须从“全局按 SHA256”改为“同一目标路径内”：实测确认（临时项目）`Build-ProjectInventory.ps1:243-247` 对非选中成员直接 `continue`，`Build-OrganizationPlan.ps1:86-90` 把它改写为 `skip_exact_duplicate` 并把 `target_path` 指向另一个路径，`Build-RetirementPlan.ps1` 再映射为 `recycle_exact_duplicate`；当两份相同字节处于不同引用角色（如 `docs/logo.png` 与 `site/logo.png`）且目录内还有其他文件时，结果是 `layout: 0`、无 hold、无错误，`site/logo.png` 静默消失而旧位置被回收。字节仍存于选中输出，不是不可恢复的字节丢失，但是真实的引用完整性丢失，必须修。
12. 引用更新目前在 `scripts/` 里**没有任何实现**（已全目录检索确认）。本方案不新增自动改写引擎，因此引用改动一律作为智能体准备好的输出副本进入 integration.json，程序只负责部署与哈希校验。

配置新版本为 1.1，兼容 1.0 原样读取；新增可选 integration_manifest，指向本轮过程目录中的 integration.json。merge 新增 version_policy=integrate；旧 preserve_all/approved_selection 的含义和旧记录不迁移。没有整合清单仍沿用原有迁移路径。
integration.json 的每组记录包括：稳定 id；所有输入（来源 id、相对路径、原哈希；已有目标作为输入时标识 target）；一个或多个最终输出（目标相对路径、准备好的文件路径及哈希、目标预期原哈希或明确不存在）；内容去向/差异检查的材料路径及哈希；所需引用/使用检查及检查结果。每个需整合输入必须有明确去向，无记录或仅字符串“已合并”不能放行。检查材料必须覆盖每个独有改动如何保留或为什么已被替代；程序验证关联和文件，内容是否充分由智能体实际逐项检查，不宣称哈希能证明语义完整。
已存在目标需要修改时也作为输入盘点并保护，其无关内容不能被覆盖。所有被改写原件在部署前通过已有 Git 恢复能力或本轮过程目录中的原件副本核验可恢复，不备份整套项目来替代有效内容整合。数据/未知二进制默认原样保存；真正需要内容编辑时使用对应工具并检查，不自动文本替换。
扩展现有动作与验收：整合输出按目标唯一安装，多个输入引用同一组，不重复写目标；普通文件仍按原样哈希核验。准备内容、输入、已有目标及检查材料全部加入计划绑定；冲突仅在整合记录完整覆盖相应输入且通过检查后解除，不把 hold 全局忽略。同一目标多写者、漏输入、越界输出拒绝执行。
目标树按最终输出生成，而不是强求与输入一一相同。执行前检查输入与原目标未变；经过目标盘临时文件、校验及替换/恢复步骤部署，安装前保护现有目标，不以无条件覆盖实现。中断后复用既有状态日志，只在实际输出等于记录结果时承认该动作已完成；失败保留可恢复原件，不把部分整合报告为完成。原样移动/跨盘复制行为仍保留。
迁移后在新目录检查引用并做适用的打开/无硬件试运行/编译。所需检查未完成则对应内容不能退役，报告具体未验证项。若必须修改已封定输出，在实际当前文件上准备新结果并重新绑定受影响计划，保留旧记录；不向用户重复索要原范围授权。清理计划和执行前均重新核实输入、最终输出、恢复材料及必要检查对应的文件版本；最终验收同样使用最终输出哈希，而不是旧源哈希。退役通过现有回收接口，原目录不存在且目标可用才算完成；不要求用户清空回收站或最终签字。

## 引用与过程目录
扫描迁移范围内实际使用的 Markdown 链接/图片、代码和配置文件中的路径、论文或其他工程资源引用；根据明确的源到目标映射修改，优先可用相对路径。不全盘替换字符串，不更改外部 URL、Zotero 标识或历史叙述。动态生成路径和复杂工程依赖通过现有工具、静态分析与适用运行检查核实；未知不冒充已验证。已知项目外引用若必须修改但不在授权范围，指出具体依赖，只暂停相应旧入口清理。
允许 audit_root 为目标内专用过程子目录，禁止等于目标、成为目标祖先或进入任一来源；OutputDir 必须归属该根。所有盘点、目录比较和空间统计在进入前排除精确本轮过程子树（包括空祖先目录的记账），不笼统跳过整个过程文件目录。该子树及祖先必须核对真实路径、链接/占位状态；不能与业务输入/输出、现有业务文件混用。已有其他任务过程材料仍按普通目标内容保护。记录/日志正常增长不改变业务目录验收，但已绑定的清单、准备结果与恢复文件逐项验证；显式外部 audit_root 保持兼容。

## 验证与发布

### 两类验收分开可检验
两类写入同一份 `actions.csv`，但验收依据不同，不得混用：

- **原样迁移**（`move_file_verify` / `copy_file_verify` / `create_directory` / `skip_*`）：验收依据仍是盘点时的**源哈希**，与现有 `Test-OrganizationAcceptance.ps1` / `Test-RetirementAcceptance.ps1` 行为一致，不修改。要求：目标字节等于源字节，且无 `unapproved_extra_path`。
- **内容整合**（`install_integrated_output`）：验收依据是 integration.json 里的**最终输出哈希**，并额外要求每个输入都有已通过检查的去向记录。源哈希只用于证明“输入自盘点后未变”，不用于证明输出正确。

两类共同的硬条件：已有目标在执行前重验未被并发修改；中断后只有实际输出等于记录结果才算完成。

### 新增测试（写入 `Test-ProjectOrganizer.ps1`，当前基线已实测 46/46 通过）
新增用例只能在临时项目与模拟回收接口上跑，不降低现有 46 项：

- `integration_schema_11_accepted` / `integration_schema_10_still_accepted`（旧格式兼容）
- `integration_version_policy_integrate_accepted`
- `integration_audit_root_inside_target_accepted` 与 `integration_audit_root_equal_or_ancestor_rejected`
- `integration_process_subtree_excluded_from_inventory_and_acceptance`（同时断言无 `unapproved_extra_path` 且空祖先不报 `empty_directory_not_approved`）
- `integration_outputdir_outside_audit_root_rejected`
- `integration_install_over_existing_target_preserves_original_copy`
- `integration_missing_input_disposition_rejected`（仅字符串“已合并”也必须拒绝）
- `integration_prepared_output_tampered_rejected` / `integration_check_material_tampered_rejected`
- `integration_target_changed_before_execute_rejected`（验 `Assert-TargetStateFresh`）
- `integration_retirement_uses_final_output_hash`（现行代码下必须先红）
- `dedup_same_bytes_distinct_reference_roles_preserved`（回归用例：现行代码下 `site/logo.png` 静默消失且 `layout: 0`，修后必须两个引用角色都在）
- `integration_interrupt_resume_no_partial_success`（用现有 `-StopAfterActions` 钩子）
- `group_mode_unaffected_by_integration`

### 无法确认事项（如实标注，不当已验证）
- `Read-POConfig -RequireSources` 现在要求**至少 2 个**来源，“单来源 + 已有目标”的整合轮次会被直接拒绝。本轮未确定到底是放宽该开关、还是要求这类轮次不传 `-RequireSources`，实现时需先定。
- 云端占位文件（Offline/RecallOnOpen/RecallOnDataAccess）、真实仪器输出与用户 Office 窗口行为均因约束无法实测，只能按现有 `windows-safety.md` 规则推演。
- 本轮结论中“实测”仅指临时项目上的 `Build-ProjectInventory.ps1` 真实运行与 46/46 基线；其余为逐行读码推演。

使用临时项目与模拟回收接口，覆盖两处项目归拢、已有目标、Markdown 多合一和路径更新、代码独有改动合并、相同文件去重、相同内容不同引用角色、无法判断冲突拒绝清理、已有目标被并发修改、准备结果/检查材料/恢复原件篡改、未计划新增文件、同盘跨盘、失败中断恢复、旧 1.0 兼容、group 保持独立、嵌套过程目录和链接/路径越界。必要使用检查均禁止连接真实仪器或干扰用户 Office 窗口。
实际做一套含 Markdown 图片链接、相对与绝对代码路径和小数据文件的整合样例，验证新入口能用、独有内容保留、旧入口被模拟退役；让不合格样例确实失败，而非只改预期标签。运行受影响现有 PowerShell 测试和格式/引用检查。保留 Git 恢复与文件保护现有测试。
只提交本技能必要变更，保留无关工作；推送后用现有后台定向同步，核对源码、CC Switch、Claude、Codex 一致。交付简短修改和验证结果，区分规则推演与临时项目实测。
