---
name: repo-mirror-maintainer
description: 检查或同步用户自己登记的上游仓库镜像。Use when 用户要检查 `Superpowers` 这类 tracked upstream 是否有更新、初始化或同步某个登记镜像，或查看本地补充层与 git 上游之间的漂移；prefer this over `market-skill-updater` when 来源是仓库镜像而不是市场安装 skill.
---

# 仓库镜像维护

## 作用

这份 skill 为用户本地自管的整仓级上游镜像提供统一维护入口。

它只处理用户自己维护的镜像登记表里的仓库，例如 `<agents-root>\upstreams\repo-mirrors.toml`。它不处理当前 cc-switch 同步仓，也不处理 `npx skills` 安装的市场 skill。

## 流程

1. 先确认镜像登记表路径。默认示例：
   `<agents-root>\upstreams\repo-mirrors.toml`
2. 默认先跑只读检查：

```powershell
python <agents-root>\repo-mirror-maintainer\scripts\manage_repo_mirrors.py check --registry <agents-root>\upstreams\repo-mirrors.toml --json
```

3. 检查结果至少要看：
   - 本地镜像目录是否存在
   - 本地 HEAD 与远端 HEAD 是否一致
   - 当前是否需要初始化或可同步更新
   - 远端检查是否失败，以及失败原因
4. 只有用户明确要求同步时，才执行：

```powershell
python <agents-root>\repo-mirror-maintainer\scripts\manage_repo_mirrors.py sync --registry <agents-root>\upstreams\repo-mirrors.toml --id superpowers --json
```

5. `sync` 后只汇报本次登记项里哪些 tracked upstream skills 发生了变化，不对整仓做无差别播报。

## 本地规则

- `check` 必须保持只读，不把周检偷偷写成 `git pull`。
- `upstreams/` 下的仓库不是活跃 skill 源；即使里面有 `SKILL.md`，也不直接加入普通发现路径。
- 如果本地镜像目录缺失，先报告“需要初始化镜像”，不要误判成 skill 目录异常。
- 如果远端查询失败，要明确写成“本轮未完成上游检查”，不要把它混进本地 `skills` 卫生问题。

## 边界

- 不把仓库镜像直接当作当前同步 skill 仓的一部分。
- 用户未明确要求时，不执行 `sync`。
- 不改写上游镜像里的 `SKILL.md`。
- 不替代 [../market-skill-updater/SKILL.md](../market-skill-updater/SKILL.md) 的市场 skill 维护职责。

## 相关文件

- 镜像登记表：用户自备 TOML，例如 `<agents-root>\upstreams\repo-mirrors.toml`
- 主脚本：[scripts/manage_repo_mirrors.py](scripts/manage_repo_mirrors.py)

## 相关技能

- 本地 skill 维护：`skill-creator`
- 市场 skill 更新：[../market-skill-updater/SKILL.md](../market-skill-updater/SKILL.md)
- 维护规则总览：[../agent-maintenance-handbook/SKILL.md](../agent-maintenance-handbook/SKILL.md)

## 维护

- 新增同类上游仓库时，优先扩用户自己的镜像登记表，不要为每个仓库重写一套逻辑。
- 如果 git 检查或同步策略变化，优先更新脚本，不把解析细节堆回正文。
