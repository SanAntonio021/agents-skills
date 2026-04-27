# agents-skills

这是我个人维护的 Claude Code 和 Codex CLI 技能库，通过 [cc-switch](https://github.com/farion1231/cc-switch) 分发到本地环境。

## 这是什么

这个仓库按“一个顶层目录对应一个技能”的方式组织。每个技能目录里都有 `SKILL.md`，也可能包含 `references/`、`scripts/`、`assets/` 或 `agents/` 等辅助材料。

当前目录结构采用 `cc-switch` 需要的扁平根目录形式。

## 适用范围

这个仓库主要用于我自己的多设备技能同步。

仓库公开，是因为当前 `cc-switch` 可以直接消费公开 GitHub 技能仓库；同一流程下私有仓库鉴权还不够方便。

其他人可以浏览或 fork，但这里的技能首先按我的个人工作流维护，不承诺通用兼容性或支持。

## 使用方式

1. 安装 `cc-switch`。
2. 在仓库管理里添加 `SanAntonio021/agents-skills`，分支选择 `main`。
3. 由 `cc-switch` 将技能安装到 `%USERPROFILE%\.claude\skills\` 和/或 `%USERPROFILE%\.codex\skills\`。

## 维护约定

- 公开文档里使用 `%USERPROFILE%`、`<agents-root>`、`<projects-root>` 这类占位符，不写死本机私有路径。
- 技能之间的引用使用技能名或仓库内相对链接，不再引用旧的私有目录结构。
- 部分 Word 格式化技能只保留样式配置文件，原始示例 `.docx` 文件不会放进公开仓库。
