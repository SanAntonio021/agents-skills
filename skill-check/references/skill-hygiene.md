# Skill Hygiene

## Purpose

维护本地 skill 环境的一致性，避免把“源文件目录”“cc-switch 同步出来的目录”“Codex 实际读取的技能目录”混成一层，最后查不清到底哪里出了问题。

## 要分清的目录

在这台机器上，排查 skill 问题时默认先分四层：

- `C:\Users\SanAn\.codex\skills`
  Codex 实际读取的技能目录。这里面有什么，才算当前真的加载了什么。
- `C:\Users\SanAn\.cc-switch\skills`
  cc-switch 同步出来的目录。这里更新了，不代表 Codex 已经会用。
- `C:\Users\SanAn\.cc-switch\cc-switch.db`
  cc-switch 的记录层。面板显示名和目录名要一起看。
- `D:\BaiduSyncdisk\.agents\agents-skills-src`
  真正应该修改的源文件目录。以后该改哪份，看这里；但不要把它当成当前已加载列表。

## 什么算当前已加载

- 只有 Codex 实际读取的技能目录里的 skill，才算当前已加载。
- 源文件目录和 cc-switch 同步出来的目录都只是背景信息，不能直接拿来报“当前冲突”。
- cc-switch 面板里显示的名字，不等于磁盘目录名。
- 同步下来了但没启用时，`C:\Users\SanAn\.codex\skills` 里可能根本没有对应入口。

## 主要问题类型

- `真冲突`
  两个或多个当前会用到的技能里，`SKILL.md` 的 `name:` 一样或归一化后一样。
- `名字不一致`
  目录名、数据库里的 `directory`、数据库里的显示名，和 `SKILL.md` 里的 `name:` 对不上。
- `链接或路径失效`
  文本里的本地路径或相对引用已经失效。
- `目录结构问题`
  skill 放在不该放的位置，或工作区快照、文档目录混进活跃树。
- `空技能或坏技能`
  缺 `SKILL.md`、文件开头配置为空、正文为空。

## 检查顺序

默认按这个顺序查：

1. 先看 `C:\Users\SanAn\.codex\skills`
2. 再看 `C:\Users\SanAn\.cc-switch\skills`
3. 再看 `C:\Users\SanAn\.cc-switch\cc-switch.db`
4. 最后再看 `D:\BaiduSyncdisk\.agents\agents-skills-src` 和 GitHub 远端

如果用户问的是“为什么现在没生效”，不要一上来就看 GitHub。

## 常见错误

- 把源文件目录当成当前已加载 skill 列表
- 把 cc-switch 面板显示名当成磁盘目录名
- 看到 cc-switch 同步出来的目录更新了，就以为 Codex 已经会用
- 把“名字不一致”直接说成“运行时冲突”
- 没先看 Codex 实际读取的技能目录，就开始猜 GitHub 没更新

## 汇报顺序

汇报时优先按这个顺序说：

- 当前实际会用到的技能
- 真冲突
- 名字不一致
- 链接或路径失效
- 空技能或坏技能
- 建议动作

## 维护

- 本文件只定义“怎么排查 skill 层级和同步链路”，不定义单个 skill 的业务规则。
- 如果路径、同步方式或启用链路变了，先更新这份文件和脚本，再改 `SKILL.md`。
