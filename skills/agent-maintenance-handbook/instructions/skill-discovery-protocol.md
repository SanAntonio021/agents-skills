# Skill Discovery Protocol

## Purpose

规范当前机器上的 skill 路由顺序，避免无谓深搜、错误优先级和重复加载。

## Default Source Order

当任务可能命中 skill 时，按以下顺序找：

1. `skills/custom/<skill>/SKILL.md`
2. `skills/vendor/<skill>/SKILL.md`
3. legacy 根目录 `<skill>/SKILL.md`
4. system skills under `C:\Users\SanAn\.codex\skills\.system`

默认不把这些位置当作活跃 skill 源：

- `skills/archive/`
- `skills/docs/`
- `skills/` 根目录散落 `.md`
- `D:\BaiduSyncdisk\.agents\upstreams\`

## Core Routing Rules

1. 先判断是否真的有 skill 适用。
2. 若用户点名 skill，先按名称在 synced root 中定位。
3. 若任务明显匹配某个 skill，即使用户没点名，也应读取该 `SKILL.md`。
4. 只读取最小必要 skill，不整树扫描。
5. 若一个 skill 需要 `references/` 或相邻 skill，再按需继续读取。

## Priority Rules

- `custom` > `vendor` > `system`
- `custom` 是本地收口和编排层
- `vendor` 保留上游内容，不默认改写
- `archive` 默认不参与路由
- `repo mirror` 不参与优先级竞争；它只作为 `custom` wrapper 的显式上游

## Wrapper Rule

如果出现“官方/下载 skill + 自建增强层”：

- 保留两层
- `vendor` 负责基础能力
- `custom` 负责本地策略、复核、路由或边界收口

不要默认把两者合并成一个 skill。

## Repo Mirrors

- `D:\BaiduSyncdisk\.agents\upstreams\` 用于零暴露上游整仓镜像。
- 即使镜像内部包含 `SKILL.md`，也不直接参与 discovery。
- 只允许 `custom` wrapper 或 [repo-mirror-maintainer](D:/BaiduSyncdisk/.agents/skills/custom/repo-mirror-maintainer/SKILL.md) 显式读取其中内容。
- repo mirror 的登记入口是 [upstreams/repo-mirrors.toml](D:/BaiduSyncdisk/.agents/upstreams/repo-mirrors.toml)，不要把它混进 `skills/vendor/`。

## When Not To Run Discovery

以下情况不要先跑 `find-skills-local` 或市场检索：

- 普通业务任务
- 已有明确命中的 `custom` skill
- 已有 `vendor` skill 足够覆盖任务
- 用户没有要求找新 skill、装新 skill、比较 skill

## When To Run Discovery

只有在以下情况才触发 skill 发现：

- 用户明确要求找 skill / 装 skill / 比较 skill
- 本地现有 synced skills 明显不够
- 需要核验某个候选 skill 是否权威或是否值得装

此时的顺序是：

1. 先看本地已同步的 `custom` / `vendor`
2. 不够时再用 [find-skills-local](D:/BaiduSyncdisk/.agents/skills/custom/find-skills-local/SKILL.md)
3. `find-skills-local` 内部再包装 [find-skills](D:/BaiduSyncdisk/.agents/skills/vendor/find-skills/SKILL.md)

## Explicit-Only Skills

这些 skill 默认不要自动接管普通任务：

- [agent-maintenance-handbook](D:/BaiduSyncdisk/.agents/skills/custom/agent-maintenance-handbook/SKILL.md)
- [zixun-pipan-zhibi](D:/BaiduSyncdisk/.agents/skills/custom/zixun-pipan-zhibi/SKILL.md)

只有用户点名或出现明确触发信号时才进入。

## Maintenance

- 如果目录结构、优先级或 wrapper 规则变化，优先更新本文件。
- 如果实际路由已稳定写入 [AGENTS.md](D:/BaiduSyncdisk/.agents/AGENTS.md) 或 [skills/CONVENTIONS.md](D:/BaiduSyncdisk/.agents/skills/CONVENTIONS.md)，本文件保持从属解释，不重复发明新规则。
