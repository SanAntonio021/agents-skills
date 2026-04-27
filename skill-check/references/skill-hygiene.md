# Skill Hygiene

## Purpose

维护本地 skill 环境的一致性，避免把“源码目录”“同步目录”“运行时入口”混成一层，最后查不清到底哪里出了问题。

## Layers to separate

在这台机器上，排查 skill 问题时默认先分四层：

- `C:\Users\SanAn\.codex\skills`
  运行时入口。这里面有什么，才算当前真的加载了什么。
- `C:\Users\SanAn\.cc-switch\skills`
  同步目录。这里更新了，不代表运行时一定已经生效。
- `C:\Users\SanAn\.cc-switch\cc-switch.db`
  cc-switch 的记录层。面板显示名和目录名要一起看。
- `D:\BaiduSyncdisk\.agents\agents-skills-src`
  源码目录。以后该改哪份，看这里；但不要把它当成当前已加载列表。

## What counts as loaded

- 只有运行时入口里的 skill，才算当前已加载。
- 源码目录和同步目录都只是背景信息，不能直接拿来报“当前冲突”。
- cc-switch 面板里显示的名字，不等于磁盘目录名。
- 同步下来了但没启用时，`C:\Users\SanAn\.codex\skills` 里可能根本没有对应入口。

## Main finding types

- `真冲突`
  两个或多个当前活跃 skill 的 `SKILL.md` 里，`name:` 一样或归一化后一样。
- `名字漂移`
  目录名、数据库里的 `directory`、数据库里的显示名，和 `SKILL.md` 里的 `name:` 对不上。
- `路径漂移`
  文本里的本地路径或相对引用已经失效。
- `结构问题`
  skill 放在不该放的位置，或工作区快照、文档目录混进活跃树。
- `空壳/破损项`
  缺 `SKILL.md`、frontmatter 为空、正文为空。

## Check order

默认按这个顺序查：

1. 先看 `C:\Users\SanAn\.codex\skills`
2. 再看 `C:\Users\SanAn\.cc-switch\skills`
3. 再看 `C:\Users\SanAn\.cc-switch\cc-switch.db`
4. 最后再看 `D:\BaiduSyncdisk\.agents\agents-skills-src` 和 GitHub 远端

如果用户问的是“为什么现在没生效”，不要一上来就看 GitHub。

## Common mistakes

- 把源码目录当成当前已加载 skill 列表
- 把 cc-switch 面板显示名当成磁盘目录名
- 看到同步目录更新了，就以为运行时已经生效
- 把“名字不一致”直接说成“运行时冲突”
- 没先看运行时入口，就开始猜 GitHub 没更新

## Reporting

汇报时优先按这个顺序说：

- 当前活跃 skill
- 真冲突
- 名字漂移
- 路径漂移
- 空壳或破损项
- 建议动作

## Maintenance

- 本文件只定义“怎么排查 skill 层级和同步链路”，不定义单个 skill 的业务规则。
- 如果路径、同步方式或启用链路变了，先更新这份文件和脚本，再改 `SKILL.md`。
