---
name: codex-skill-ecosystem-audit
description: 面向 Codex 本地环境做 skill 生态周检与市场更新审计。Use when 用户要运行 `.codex/automations/skill`、用 Codex 本地规则替代旧的 Claude 风格 `skills-updater` 语义，或要汇总 `npx skills` 安装、`D:\BaiduSyncdisk\.agents\skills` 同步目录、本地补充关系和本周变更；prefer this over `market-skill-updater` when 目标是整套周报，而不是单独检查某个市场 skill。
---

# Codex Skill 生态审计

## 作用

这份 skill 把旧的“检查已安装 skill 更新”思路，收成适合当前这台机器的 Codex 本地周检流程。

它不沿用 Claude 的插件语义，而是统一检查和汇总：

- `npx skills` 管理的全局 market skills
- `D:\BaiduSyncdisk\.agents\skills` 下的同步技能树
- `custom` 对 `vendor` 的本地补充关系和漂移线索
- 相比上一轮快照，本周新增、删除、迁移和重命名

## 流程

1. 先读当前自动化目录里的 `memory.md`，但只把它当历史语境，不让旧口径覆盖脚本结果。
2. 确认 `Asia/Shanghai` 当天日期，格式固定为 `YYYY-MM-DD`。
3. 运行统一汇总脚本：

```powershell
python "D:\BaiduSyncdisk\.agents\skills\custom\codex-skill-ecosystem-audit\scripts\run_codex_skill_ecosystem_audit.py" --date YYYY-MM-DD --skills-root "D:\BaiduSyncdisk\.agents\skills" --hygiene-reports-root "D:\BaiduSyncdisk\.agents\reports\skill-hygiene" --output-root "D:\BaiduSyncdisk\.agents\reports\codex-skill-ecosystem-audit"
```

4. 脚本会自动做三件事：
   - 调用 [../market-skill-updater/SKILL.md](../market-skill-updater/SKILL.md) 的主脚本做全局只读检查
   - 调用 [../skill-hygiene-audit/SKILL.md](../skill-hygiene-audit/SKILL.md) 的扫描脚本生成当日 `summary.json`
   - 结合上一轮快照，生成 Codex 专用汇总 JSON
5. 读结果时优先看：
   - `reports/codex-skill-ecosystem-audit/manifests/YYYY-MM-DD/summary.json`
   - `reports/skill-hygiene/weekly/YYYY-MM-DD.md`

## 汇报重点

中文 inbox 优先覆盖这些点：

- 同步 skill 总数，以及 `custom`、`vendor`、根目录遗留项、`archive` 各有多少
- market skills 的登记数、实存目录数和可更新候选数
- 本周新增、删除、迁移或重命名候选
- 本地补充关系线索：同名覆盖、显式 vendor 引用、失效 vendor 引用、缺少本地接入层的 vendor 候选
- 是否存在空目录、路径漂移和目录卫生问题

如果结构化结果和旧 `memory.md` 冲突，优先相信本轮脚本输出，并明确写出“旧记录与当前扫描不一致”。

## 边界

- 不使用 Claude 的 `~/.claude/plugins`、`installed_plugins.json` 或 `/install` 语义。
- 不把 `skills/custom` 下的自建 skill 伪装成 market skills。
- 默认只做读取、审计和汇总，不直接执行更新。
- 不因为某个 `vendor` 没有本地接入层就自动判成异常；这里只整理候选。
- 除非脚本本身失败，不靠手工数目录替代结构化脚本。

## 相关文件

- 市场 skill 检查入口：[../market-skill-updater/SKILL.md](../market-skill-updater/SKILL.md)
- 技能树卫生审计：[../skill-hygiene-audit/SKILL.md](../skill-hygiene-audit/SKILL.md)
- 汇总脚本：[scripts/run_codex_skill_ecosystem_audit.py](scripts/run_codex_skill_ecosystem_audit.py)

## 维护

- 如果 `market-skill-updater` 的 JSON 结构变化，优先更新汇总脚本，不把解析逻辑堆回正文。
- 如果 `skill-hygiene-audit` 的 `summary.json` 字段变化，同步更新差分和本地补充关系统计逻辑。
- 这份 skill 是 Codex 本地适配层；除非用户明确要求，不再把 Claude 专属语义搬回来。
