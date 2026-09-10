# 配置与清单

## 配置

配置文件使用 UTF-8 JSON，新配置为 `schema_version: "1.1"`，旧 `1.0` 配置和记录按原义读取，不迁移。`1.1` 允许单一来源与已有目标整合；旧 `1.0` 来源数量校验不变。

| 字段 | 要求 |
| --- | --- |
| `mode` | `merge` 或 `group` |
| `search_roots` | 用户批准的绝对搜索根目录；只用于候选发现 |
| `candidate_hints` | 可选的名称关键词；只作为证据，不自动选来源 |
| `max_discovery_depth` | 默认 4 |
| `sources` | 已确认来源，字段为 `id`、`path`、`role`；归组模式还需 `target_name` |
| `target_root` | 唯一目标或共同父目录 |
| `audit_root` | 本轮过程根目录；`1.1` 可为目标内的 `过程文件/整理主题/`，不得等于目标、成为目标祖先或进入来源。`1.0` 保持与目标不重叠 |
| `integration_manifest` | `1.1/merge` 可选，指向 `audit_root` 内的整合 JSON；未使用时为空或省略 |
| `canonical_source_id` | 合并模式必填；新仓库可使用空值并令 `active_repo_policy` 为 `new` |
| `mapping_rules` | `merge` 中按顺序应用的 `source_id`、`from_prefix`、`to_prefix`；只表达已批准目录设计，默认空；`group` 禁止使用 |
| `layout_decisions` | `merge` 必填的目录设计、版本策略、例外和目录树批准记录 |
| `active_repo_policy` | `source:<id>`、`target_existing`、`new` 或归组模式的 `preserve_each` |
| `sync_roots` | 不允许存放活动 `.git` 数据库的同步目录 |
| `external_git_root` | 同步目录外的 Git 元数据和临时裸仓库根目录 |
| `protected_paths` | 任何阶段都不得修改的绝对路径 |
| `exclude_rules` | 显式目录名、扩展名和相对路径前缀 |

来源 ID 和 `target_name` 只允许 ASCII 字母、数字、点、下划线和连字符。来源不得互相嵌套，来源与目标不得嵌套。`OutputDir` 位于本轮 `audit_root` 内。内部过程目录及祖先经过路径检查，只排除精确本轮子树，不排除整个 `过程文件/`。

### `layout_decisions`

| 字段 | 含义 |
| --- | --- |
| `restructure_in_scope` | 本次是否获准重构目录；为 `false` 时禁止非空 `mapping_rules` |
| `root_files` | 用户批准放在目标根目录的文件名 |
| `category_language` | 一级分类语言：`en`、`zh` 或 `preserve` |
| `max_general_depth` | 普通资料在目标根目录下允许的父目录层数；资料型项目通常为 1 |
| `deep_structure_prefixes` | 允许必要内部层级的前缀，如代码、论文、实验、数据、结果和审计记录 |
| `independent_subprojects` | 必须保持独立的子项目路径 |
| `version_policy` | `1.1` 新增 `integrate`：以整合清单承接有效内容，不默认历史副本。旧 `preserve_all`、`approved_selection` 保持原义；后者只选择日常版本，其他唯一文件仍按既定归档方案保留或保持 `hold` |
| `keep_empty_directories` | 用户明确批准保留的空目录 |
| `forbidden_target_paths` | 不应出现在目标中的旧套壳目录或其他路径 |
| `exceptions` | 带 `path` 和具体 `reason` 的逐项例外 |
| `approved_tree_sha256` | `target-tree.csv` SHA256，由智能体绑定已有准确授权。`1.1` 可留空，由完整计划锁定目录树；非空必须匹配。`1.0` 正式计划仍要求该值 |

按当前明确请求确定结构；只有显式调用时使用 `ask-first`，其余只问实际未决事项。确认顺序重点覆盖根目录文件、分类名称与语言、普通资料最大层级、独立子项目、版本策略和目录重构范围。配置字段记录本次准确授权，不要求重复对话确认。

## 整合清单与使用检查

`integration_manifest` 指向 JSON：`{"schema_version":"1.0","groups":[...]}`。组字段如下，数组均至少一项；路径以实际文件为准。

| 字段 | 内容 |
| --- | --- |
| `id` | 稳定组标识 |
| `inputs` | 每项含 `source_id`、`relative_path`、原 `sha256`、绝对 `recovery_path`；已有目标使用保留标识 `__target__` |
| `outputs` | 每项含目标 `relative_path`、绝对 `prepared_path`、最终 `sha256`、`expected_target_sha256`（原哈希或字面值 `absent`） |
| `coverage` | 非空实际检查报告的 `path`、`sha256`，以及 `inputs` 覆盖数组 |
| `required_checks` | 部署后必做检查的唯一名称，如 `links`、`run` |

`coverage.inputs` 每份输入恰好一项：`source_id`、`relative_path`、`destination_paths`（本组输出路径）、`reason`（具体保留或替代判断）。报告逐项说明独有内容如何保留或为何被替代，不能只写“已合并”。程序核验对应关系和文件，智能体实际检查内容充分性。

所有准备文件、恢复副本、覆盖报告均在本轮 `audit_root` 内。已有目标输入必须有同路径输出且预期原哈希一致。多个输入可对应同一输出；同一输入重复归组、多个组写同一目标、缺失输入、输出越界均不能执行。恢复副本须与各原件哈希相符，Git bundle 不能代替工作文件的整合恢复副本。

部署后实际检查新目录，将结果写入唯一的 `<OutputDir>/integration-checks.json`：

```json
{
  "schema_version": "1.0",
  "manifest_sha256": "<integration_manifest 的实际 SHA256>",
  "checks": [{
    "group_id": "docs",
    "id": "links",
    "status": "passed",
    "checked_at": "<实际 ISO8601 时间>",
    "outputs": [{"relative_path": "README.md", "sha256": "<最终实际 SHA256>"}],
    "report_path": "<本轮过程目录内的实际非空检查报告绝对路径>",
    "report_sha256": "<报告实际 SHA256>"
  }]
}
```

每项 `required_checks` 恰好有一份通过回执，并列全本组输出及精确哈希。报告记录新入口的实际链接、打开、编译或无硬件运行结果；未完成时保留缺失状态，不预填通过。生成退役计划时绑定这些回执和报告，执行清理前再次复核版本；改写后重新检查，旧结果不能沿用。

示例见 [project-organizer.example.json](../assets/project-organizer.example.json) 和 [integration.example.json](../assets/integration.example.json)。它们只示范接口，含不可直接执行的占位值；实际路径、输入覆盖及所有哈希必须由当前项目盘点生成。只做原样迁移时省略 `integration_manifest`，使用原有版本策略。

## 候选发现输出

输出：

- `candidates.csv`：路径、名称、深度、README、Git、项目标记、关键词命中和证据分数。
- `candidate_evidence.json`：搜索根、停止项和每个候选的证据。
- `errors.csv`：无法枚举、网络路径和重解析点问题。
- `review.md`：供用户选择来源。

## 文件盘点

`files.csv` 固定包含：

```text
source_id,source_root,relative_path,entry_type,size_bytes,last_write_utc,
attributes,reparse_tag,link_count,sha256,scan_status,reason,
proposed_relative_path,proposed_target_path,target_status
```

其他输出：

- `duplicates.csv`：相同 SHA256 的所有来源及规范目标。
- `conflicts.csv`：同一拟目标路径的不同 SHA256。
- `source_state.json`：扫描前后文件数、字节数和源根状态。
- `git_state.json`：仓库路径、分支、HEAD、引用、dirty/staged/untracked。
- `target-tree.md`：供用户审批的可读最终目录树。
- `target-tree.csv` 和 `target-tree.sha256`：稳定目录树及其批准标识。
- `target-state.csv`、`target-state.json`：计划前已有目标内容。
- `layout-violations.csv`：未批准根文件、普通资料层级超限、旧套壳目录、空目录和未解决项。
- `errors.csv`、`summary.md`、`inventory.sha256`。

核心 CSV 不写运行时间。路径使用 `/`，排序使用忽略大小写后的规范路径，再以原路径作稳定次序。

## 迁移计划

`actions.csv` 动作固定为：

- `create_directory`
- `move_file_verify`
- `copy_file_verify`
- `skip_exact_duplicate`
- `skip_target_duplicate`
- `exclude_cache`
- `preserve_git_metadata`
- `install_integrated_file`：每个最终输出只安装一次。
- `integrated_input`：每个来源输入一项，原件保留至退役，不重复安装输出；已有目标输入不作为来源退役。
- `hold_conflict`
- `hold_unsupported`

计划还输出 `space.json`、`review.md`、`errors.csv`、`plan-files.sha256` 和 `plan.sha256`。`merge` 的 `layout-violations.csv` 必须为空；目录树哈希按上述版本规则校验。`plan.sha256` 绑定配置、目录树、映射、例外、盘点、动作、空间及整合材料。任何变化均需核实并重新封定计划，只有授权范围或重要取舍改变才重新询问用户。

执行输出为 `execution.jsonl`、`execution-state.json`、`execution-summary.json` 和 `acceptance.md`。日志只追加，状态文件使用同目录临时文件后原子替换。验收逐项比较实际目录树与批准目录树；额外路径、缺失路径、旧套壳目录和未批准空目录均失败。

## 退役计划

退役动作固定为：

- `already_moved`
- `recycle_verified_copy_source`
- `recycle_exact_duplicate`
- `recycle_integrated_source`：按最终输出、恢复副本及实际使用检查核验整合输入后回收。
- `recycle_cache`
- `recycle_git_metadata`
- `remove_empty_directory`
- `hold_changed`
- `hold_unplanned`

输出 `retirement.csv`、`retirement-errors.csv`、`retirement-review.md`、`retirement-files.sha256` 和 `retirement.sha256`。清理前重新枚举全部来源，核对待处理文件、已退役路径及新增条目；未计划文件、已清理路径重新出现或不支持的路径状态均停止清理。

执行后输出追加日志和最终验收。`1.1` 最终验收重新比较完整业务目标树，包含已有目标保留内容的哈希、路径类型、缺失项和额外项；仅排除本轮专用过程子树，Git 元数据沿用独立检查。不提供清空整个回收站的命令。
