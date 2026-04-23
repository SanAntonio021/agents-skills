---
name: market-skill-updater
description: 检查、修复并更新通过 `npx skills` 安装到当前工作区的市场或社区 skill。Use when the user wants to audit installed market skills, run a safe pre-update check, repair residual global directories, or upgrade workspace-managed skills without mixing them with local `custom/vendor` skills; prefer this over `find-skills-local` when the goal is维护已安装 skill rather than发现新 skill.
---

# 市场 Skill 维护器

## 作用

这个 skill 只处理通过 `npx skills` 管理的外部 skill。

它不处理 `<agents-root>\skills\custom` 下的自建 skill，也不直接改写同步目录中的 `vendor` skill。

## 流程

1. 先用脚本盘点当前工作区的已安装 skill：

```powershell
powershell -ExecutionPolicy Bypass -File "<agents-root>\market-skill-updater\scripts\manage_market_skills.ps1" -Mode check -Scope workspace -Json
```

2. 先看盘点结果，再判断下一步：
   - 已安装 skill 是否为空
   - `npx skills check` 是否可用
   - 用户要的是“升级已安装 skill”还是“寻找新 skill”
3. 只有在工作区里确实装了 market skill，且用户明确要升级时，才执行：

```powershell
powershell -ExecutionPolicy Bypass -File "<agents-root>\market-skill-updater\scripts\manage_market_skills.ps1" -Mode update -Scope workspace -Json
```

4. 升级后汇报：
   - 升级前清单
   - 升级结果
   - 升级后清单

## 全局范围规则

全局范围只允许：

- 只读盘点
- 只读更新检查
- 显式残留修复

全局检查命令：

```powershell
powershell -ExecutionPolicy Bypass -File "<agents-root>\market-skill-updater\scripts\manage_market_skills.ps1" -Mode check -Scope global -Json
```

全局修复命令：

```powershell
powershell -ExecutionPolicy Bypass -File "<agents-root>\market-skill-updater\scripts\manage_market_skills.ps1" -Mode repair -Scope global -Json
```

修复时只清理“未列出且为空”的残留目录，不自动删非空目录。

## 什么时候不要用

- 用户真正要找新 skill，改用 [../find-skills-local/SKILL.md](../find-skills-local/SKILL.md)
- 用户真正要改自己写的 skill，改用 [../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)
- 用户要做生态周检，改用 `codex-skill-ecosystem-audit`

## 边界

- 不把 `custom/` 或 `vendor/` 当成 `npx skills` 的可升级包。
- 不因为用户提到“更新 skill”就去改 `SKILL.md` 正文。
- 不在未盘点已安装清单前直接跑 `npx skills update`。
- 不把全局检查偷偷扩大成全局更新。
- 不把“找新 skill”“安装 skill”“升级已安装 skill”混成一个入口。

## 相关文件

- 主脚本：[scripts/manage_market_skills.ps1](scripts/manage_market_skills.ps1)

## 相关技能

- 市场发现与复核：[../find-skills-local/SKILL.md](../find-skills-local/SKILL.md)
- 本地自建 skill 维护：[../skill-creator-local/SKILL.md](../skill-creator-local/SKILL.md)
- 自建 skill 运行复盘：[../jineng-fupan/SKILL.md](../jineng-fupan/SKILL.md)
- 系统安装基线：[`skill-installer`](%USERPROFILE%/.codex/skills/.system/skill-installer/SKILL.md)

## 维护

- `skills` CLI 的 `check`、`update`、`list` 语义变化时，优先复查这里。
- 解析逻辑出问题时，先修脚本，不把解析细节堆回主文件。
- 如果以后要做定时检查，优先在外层接 automation，不把调度规则写死在 skill 正文里。
