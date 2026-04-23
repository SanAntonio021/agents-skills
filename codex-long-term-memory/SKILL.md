---
name: codex-long-term-memory
description: 为当前 Codex 本地环境启用、配置和维护跨会话长期记忆，并把运行时状态与同步 skill 文件隔离。Use when 用户希望助手跨会话记住偏好、背景、决定或重要事实，尤其是希望默认开启记忆时；prefer this over 直接套用 `vendor/long-term-memory`，因为这里已经处理了本地目录、初始化和运行边界。
---

# Codex 长期记忆

## 作用

这份 skill 承接 `long-term-memory`，但把可变运行态从同步技能目录里分离出来，避免把记忆数据写回 `skills/`。

默认运行目录：

- `CODEX_HOME\state\long-term-memory\`

如果 `CODEX_HOME` 没设置，就回退到：

- `%USERPROFILE%\.codex\state\long-term-memory\`

## 流程

1. 先读上游基线和本地运行布局说明：
   - `long-term-memory`
   - [references/runtime-layout.md](references/runtime-layout.md)
2. 首次启用、补齐运行态或上游更新后，先运行：
   [scripts/ensure_runtime.ps1](scripts/ensure_runtime.ps1)
3. 运行目录准备好后，再把该目录作为 `workdir` 去调用上游脚本。
4. 默认通过 [scripts/invoke_runtime_python.ps1](scripts/invoke_runtime_python.ps1) 统一调用上游 Python 脚本。
5. 如果用户只是在讨论“要不要记忆”，先解释现状和选项，不擅自初始化、配置或写入记忆。

## 默认记忆模式

- 如果用户明确表达“默认自动记忆”“以后直接记着”，就把当前线程视为已进入默认记忆模式。
- 一旦进入，长期有效的信息默认自动记录，不必每次重问。
- 用户说下面这些话时，视为本轮不要记：
  - `别记`
  - `这步别记`
  - `不用记`
  - `停止记忆`
  - `暂停记忆`

## 运行约定

- 上游静态文件继续留在 `vendor/long-term-memory/`。
- 本地这一层只负责路径、初始化和边界控制，不复制上游逻辑。
- 永远不要把下面这些可变内容写回 `skills/custom/` 或 `skills/vendor/`：
  - `.env`
  - `configured.txt`
  - `memories/`
  - `short-term/`
  - `vector_db/`

## 边界

- 不把这份 skill 误当成编程语言里的 memory safety 话题。
- 用户还没明确需要默认记忆前，不把所有个人信息都写成跨会话记忆。
- 不把 API Key 或用户记忆写进同步 skill 源目录。
- 不直接改 `vendor/long-term-memory` 来适配本地目录；本地差异只维护在这里。

## 相关文件

- 上游基线：`long-term-memory`
- 运行布局：[references/runtime-layout.md](references/runtime-layout.md)
- 运行态初始化：[scripts/ensure_runtime.ps1](scripts/ensure_runtime.ps1)
- 统一调用入口：[scripts/invoke_runtime_python.ps1](scripts/invoke_runtime_python.ps1)

## 相关技能

- Windows 命令复用：[../command-pattern-memory/SKILL.md](../command-pattern-memory/SKILL.md)
- Windows 命令护栏：[../zhongduan-zhixing-hulan/SKILL.md](../zhongduan-zhixing-hulan/SKILL.md)
- 本地 skill 维护：[../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)

## 维护

- 上游更新后，先同步 `vendor/long-term-memory/`，再刷新本地运行态静态文件。
- 如果以后要把“启用记忆”和“日常使用记忆”拆成两层，再在这里外面补独立 leaf skill，不复制上游脚本。
