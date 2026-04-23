---
name: skill-publisher-local
description: 为准备公开发布的 skill 提供去私有化检查、README 补齐、GitHub 元信息整理和发布前预检。Use when 用户要把本地同步 skill 准备成可公开发布状态，但不想重写上游 `skill-publisher` 的整套发布流程。
---

# 本地 Skill 发布准备（过渡壳）

## 委托

发布的主流程全部走官方 `skill-publisher`。

## 本地补充

1. 发布前检查 skill 是否引用了 `D:\BaiduSyncdisk` 等私有绝对路径；有则改为 HOME 相对或配置项。
2. 检查 frontmatter `description` 是否泄露内部项目名；发布版应替换为通用描述。
3. 当前 cc-switch 同步仓可以公开分发；如果只想单独发布某个 skill，也可以另建独立仓库，不必强制从整仓拆分。
