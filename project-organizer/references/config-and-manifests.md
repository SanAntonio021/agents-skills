# 配置与清单

## 配置

配置文件使用 UTF-8 JSON，`schema_version` 固定为 `1.0`。

| 字段 | 要求 |
| --- | --- |
| `mode` | `merge` 或 `group` |
| `search_roots` | 用户批准的绝对搜索根目录；只用于候选发现 |
| `candidate_hints` | 可选的名称关键词；只作为证据，不自动选来源 |
| `max_discovery_depth` | 默认 4 |
| `sources` | 已确认来源，字段为 `id`、`path`、`role`；归组模式还需 `target_name` |
| `target_root` | 唯一目标或共同父目录 |
| `audit_root` | 运行清单根目录，不得与来源或目标重叠 |
| `canonical_source_id` | 合并模式必填；新仓库可使用空值并令 `active_repo_policy` 为 `new` |
| `mapping_rules` | `merge` 中按顺序应用的 `source_id`、`from_prefix`、`to_prefix`；只表达已批准目录设计，默认空；`group` 禁止使用 |
| `layout_decisions` | `merge` 必填的目录设计、版本策略、例外和目录树批准记录 |
| `active_repo_policy` | `source:<id>`、`target_existing`、`new` 或归组模式的 `preserve_each` |
| `sync_roots` | 不允许存放活动 `.git` 数据库的同步目录 |
| `external_git_root` | 同步目录外的 Git 元数据和临时裸仓库根目录 |
| `protected_paths` | 任何阶段都不得修改的绝对路径 |
| `exclude_rules` | 显式目录名、扩展名和相对路径前缀 |

来源 ID 和 `target_name` 只允许 ASCII 字母、数字、点、下划线和连字符。来源不得互相嵌套，目标不得位于来源内，审计目录不得与来源或目标重叠。

### `layout_decisions`

| 字段 | 含义 |
| --- | --- |
| `restructure_in_scope` | 本次是否获准重构目录；为 `false` 时禁止非空 `mapping_rules` |
| `root_files` | 用户批准放在目标根目录的文件名 |
| `category_language` | 一级分类语言：`en`、`zh` 或 `preserve` |
| `max_general_depth` | 普通资料在目标根目录下允许的父目录层数；资料型项目通常为 1 |
| `deep_structure_prefixes` | 允许必要内部层级的前缀，如代码、论文、实验、数据、结果和审计记录 |
| `independent_subprojects` | 必须保持独立的子项目路径 |
| `version_policy` | `preserve_all` 或 `approved_selection`；后者只选择日常版本，其他唯一文件仍须进入获批归档路径或保持 `hold` |
| `keep_empty_directories` | 用户明确批准保留的空目录 |
| `forbidden_target_paths` | 不应出现在目标中的旧套壳目录或其他路径 |
| `exceptions` | 带 `path` 和具体 `reason` 的逐项例外 |
| `approved_tree_sha256` | 用户批准的 `target-tree.csv` SHA256；初次盘点留空 |

真实任务先使用 `ask-first`，一次确认一个会改变结构的事项。确认顺序重点覆盖根目录文件、分类名称与语言、普通资料最大层级、独立子项目、版本策略和目录重构范围。配置字段不能代替这次对话确认。

## 候选发现

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
- `hold_conflict`
- `hold_unsupported`

计划还输出 `space.json`、`review.md`、`errors.csv`、`plan-files.sha256` 和 `plan.sha256`。`merge` 只有在 `approved_tree_sha256` 与当前目录树一致且 `layout-violations.csv` 为空时才能生成正式计划。`plan.sha256` 绑定配置、目录树、映射、例外、盘点、动作和空间文件；任何变化都使批准失效。

执行输出为 `execution.jsonl`、`execution-state.json`、`execution-summary.json` 和 `acceptance.md`。日志只追加，状态文件使用同目录临时文件后原子替换。验收逐项比较实际目录树与批准目录树；额外路径、缺失路径、旧套壳目录和未批准空目录均失败。

## 退役计划

退役动作固定为：

- `already_moved`
- `recycle_verified_copy_source`
- `recycle_exact_duplicate`
- `recycle_cache`
- `recycle_git_metadata`
- `remove_empty_directory`
- `hold_changed`
- `hold_unplanned`

输出 `retirement.csv`、`errors.csv`、`review.md`、`retirement-files.sha256` 和 `retirement.sha256`。执行后输出追加日志和最终验收；不提供清空整个回收站的命令。
