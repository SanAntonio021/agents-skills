---
name: skill-creator-local
description: 为本地同步 skill 提供创建、更新与整理规则，并控制目录膨胀。Use when creating or updating a local synced skill here, or tightening local routing rules; prefer this over `skill-creator` for targets managed via cc-switch under the user's `agents-skills` repo; defer to `duihua-jingyan-tiqu` when still deciding whether a skill should exist.
---

# 本地 Skill 创建器（过渡壳）

## 委托

创建与更新 skill 的通用做法全部走官方 `skill-creator`。

## 本地补充

1. 新 skill 的源文件写在 `SanAntonio021/agents-skills` 仓库的 `skills/<name>/` 下，不再写进 `D:\BaiduSyncdisk\.agents\skills\custom\`。
2. 若需要修改官方 skill，采用 fork-and-rename：在 `agents-skills/skills/<name>-x/` 下复制并改 `name:` 字段，避免与官方同名冲突。
3. 命名优先选短词；中文拼音 skill 名保留小写短横线。
4. 提交前走一次 `skill-hygiene-audit`。
