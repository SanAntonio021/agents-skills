---
name: find-skills-local
description: 为当前本地技能树提供 skill 查找、比较、安装与低置信度复核规则。Use when the user explicitly wants to find, compare, or install a skill, or when routing confidence is low and an existing skill may already cover the need; do not use this for obvious direct hits; prefer this over `find-skills` when the result must fit the user's local cc-switch-managed skill set rather than the global marketplace.
---

# 本地 Skill 查找与复核（过渡壳）

## 委托

本 skill 现在是最小委托壳。查找、比较、安装主流程全部走官方 `find-skills`。

## 本地补充

1. 查找前先列出 `%USERPROFILE%\.claude\skills\` 和 `%USERPROFILE%\.codex\skills\`，确认是否已通过 cc-switch 安装过同名或同类 skill，避免重复安装。
2. 新装的 skill 如果是自建需求，直接在 `SanAntonio021/agents-skills` 仓库新增目录；不要装到全局 market 源。
3. 低置信度场景（routing confidence 不够）优先先查现有 skill 再建议新装。
