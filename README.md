# agents-skills

这是我个人维护的 Claude Code 和 Codex CLI 技能库，通过 [cc-switch](https://github.com/farion1231/cc-switch) 分发到本地环境。

## 这是什么

这个仓库按“一个顶层目录对应一个技能”的方式组织。每个技能目录里都有 `SKILL.md`，也可能包含 `references/`、`scripts/`、`assets/` 或 `agents/` 等辅助材料。

当前目录结构采用 `cc-switch` 需要的扁平根目录形式。

## 适用范围

这个仓库主要用于我自己的多设备技能同步。

仓库公开，是因为当前 `cc-switch` 可以直接消费公开 GitHub 技能仓库；同一流程下私有仓库鉴权还不够方便。

其他人可以浏览或 fork，但这里的技能首先按我的个人工作流维护，不承诺通用兼容性或支持。

`paper-download` 内置的 IEEE/Optica 机构访问模块按 MIT 许可证公开发布，许可证见该技能目录。它采用尽力维护模式：Windows 第一版提供安装、诊断、登录交接和失败回退，使用时需同时安装 `web-access`，并准备 Python 3.10+ 与 Node.js 22+；但不承诺所有学校、出版社或浏览器版本长期兼容。

## 使用方式

1. 安装 `cc-switch`。
2. 在仓库管理里添加 `SanAntonio021/agents-skills`，分支选择 `main`。
3. 由 `cc-switch` 将技能安装到 `%USERPROFILE%\.claude\skills\` 和/或 `%USERPROFILE%\.codex\skills\`。

## 维护约定

- 公开文档里使用 `%USERPROFILE%`、`<agents-root>`、`<projects-root>` 这类占位符，不写死本机私有路径。
- 技能之间的引用使用技能名或仓库内相对链接，不再引用旧的私有目录结构。
- 部分 Word 格式化技能只保留样式配置文件，原始示例 `.docx` 文件不会放进公开仓库。
- 本地已结束的测试工作区归入 `过程文件/`；正式技能仍保留在仓库根目录。原始报告保持不变，历史路径可查工作区清理映射。
- `lark-doc` 与 `lark-whiteboard` 采用分工维护：`lark-doc` 本地接管 2026-10-18 官方完整包，只负责文档位置、空白画板块、文档/画板 token 与 block ID；`lark-whiteboard` 是单个画板内图示能力的唯一 owner，负责图型判断、图内容清单、原生对象创建与局部编辑、回读和看图。系统架构、信号链、接线和模块拓扑使用可编辑原生对象；Mermaid、PlantUML、SVG 仅在用户确认后作为非原生路径使用。官方 `lark-doc` 更新先比较整体差异再合并，不直接覆盖本地版本。
- 技能发布由 [agent-rules](agent-rules/SKILL.md) 统一执行；运行时生效、管理界面显示与云端分发分别核验，具体流程集中维护在[发布章节](agent-rules/references/skill-upstream-maintenance.md#技能定向发布)。
