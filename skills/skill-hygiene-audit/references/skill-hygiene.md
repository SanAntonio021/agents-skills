# Skill Hygiene

## Purpose

维护 synced skill 目录的整洁、单一真源和可路由性，避免重复副本、路径漂移和职责混乱。

## Current Layout

当前有效目录模型是：

- `D:\BaiduSyncdisk\.agents\skills\custom`
- `D:\BaiduSyncdisk\.agents\skills\vendor`
- `D:\BaiduSyncdisk\.agents\skills\archive`
- `D:\BaiduSyncdisk\.agents\skills\docs`

含义分别是：

- `custom`：用户自建、当前活跃
- `vendor`：下载或官方来源，保留上游
- `archive`：停用、备份、迁移保留
- `docs`：说明、审计、迁移记录，不参与 skill 路由

## Hygiene Rules

1. 活跃 skill 只放在 `custom/` 或 `vendor/`。
2. 根目录不再新增活跃 skill 文件夹。
3. `docs/` 只放文档，不放可路由 skill。
4. `archive/` 默认不参与路由，不把归档误当活跃来源。
5. `vendor` 只归类，不默认改内容；本地收口放在 `custom`。

## Duplicate Handling

发现重复 skill 时，按这个顺序处理：

1. 先判断是否真重复，还是“vendor 基座 + custom 包装层”。
2. 如果只是包装关系，保留两层，不合并。
3. 如果是同一 skill 的多份活跃副本，只保留一个真源。
4. 被淘汰的副本优先归档，不静默删除历史痕迹。

## Naming Rules

- 自建 skill 使用语义化 kebab-case
- 不用 `_name`、`final2`、日期堆叠名这类维护性差的名字
- `vendor` 名称尽量跟随上游
- skill 名称描述功能，不描述来源

## Routing Hygiene

- 默认优先级是 `custom > vendor > system`
- 普通任务不要先跑 skill 深搜
- 只有现有 synced skills 不够时，才进入 `find-skills-local`
- `agent-maintenance-handbook` 和 `zixun-pipan-zhibi` 默认只在显式触发时进入

## Root Hygiene

`D:\BaiduSyncdisk\.agents\skills` 根目录应尽量只保留：

- `README.md`
- `CONVENTIONS.md`
- `custom/`
- `vendor/`
- `archive/`
- `docs/`

其余散落文档优先下沉到 `docs/`。

## Maintenance Triggers

出现以下情况时，应做一次 hygiene 复核：

- 新增或下载了多份 skill
- 移动、重命名、归档了 skill
- 目录根部又出现散落文件或活跃 skill
- 某个 skill 的职责开始与相邻 skill 明显重叠
- 发现旧路径引用、空壳目录或遗留副本

## Maintenance

- 本文件只定义目录卫生和归类卫生，不定义单个 skill 的业务规则。
- 若目录模型变化，优先更新本文件和 `CONVENTIONS.md`，不要靠零碎补丁维持。
