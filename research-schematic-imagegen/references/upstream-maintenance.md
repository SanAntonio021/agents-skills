# 上游维护

## 来源和分层

- 上游仓库：`https://github.com/ConardLi/garden-skills`
- 上游技能：`skills/gpt-image-2`
- 初始吸收版本：`1.0.4`
- 零暴露镜像：`<agents-root>/upstream/ConardLi-garden-skills`
- 镜像登记：`<agents-root>/upstream/repo-mirrors.toml`
- 本地专属技能：`<agents-root>/skills/research-schematic-imagegen`

镜像不参与技能查找，也不直接同步到 cc-switch。它只保存上游原貌，供差异检查。

## 检查顺序

### 1. 只读检查远端

```powershell
python <agents-root>/skills/agent-rules/scripts/manage_repo_mirrors.py check --registry <agents-root>/upstream/repo-mirrors.toml --id conardli-garden-skills --json
```

`up_to_date` 表示镜像 HEAD 与远端一致；`update_available` 表示远端有新提交。

### 2. 用户同意后刷新镜像

```powershell
python <agents-root>/skills/agent-rules/scripts/manage_repo_mirrors.py sync --registry <agents-root>/upstream/repo-mirrors.toml --id conardli-garden-skills --json
```

同步只更新零暴露镜像，不改本地专属技能。

### 3. 比较与本地相关的上游文件

```powershell
python <skill-dir>/scripts/compare_upstream.py --mirror <agents-root>/upstream/ConardLi-garden-skills --baseline <skill-dir>/references/upstream-baseline.json
```

结果分三类：

- `up_to_date`：已跟踪的上游文件与基准一致。
- `review_required`：核心脚本或相关模板有新增、修改、删除，需要人工评估。
- `mirror_error`：镜像缺失或不可读，先修复镜像，不推断上游变化。

## 评估优先级

| 上游变化 | 优先级 | 本地处理 |
| --- | --- | --- |
| `scripts/shared.js`、`generate.js`、`edit.js`、`check-mode.js` | 高 | 检查接口参数、响应格式、安全和兼容性；必要时人工移植 |
| `references/academic-figures/` | 中 | 检查是否增加适合科研申报图的结构或约束 |
| `references/technical-diagrams/` | 中 | 只吸收适合白底科研图的结构，不照搬暗色工程风格 |
| 编辑、双语和提示词方法文件 | 中 | 检查是否改善中文标签或局部编辑稳定性 |
| README、案例链接、市场路径 | 低 | 通常不改本地专属技能 |
| 仅版本号变化 | 低 | 不因版本号自动修改本地代码 |

## 合并原则

- 不用上游目录覆盖本地技能。
- 先读上游 diff，再判断是否解决本地真实问题。
- 本地已经更严格的凭据、技术合同和最终目录规则继续保留。
- 接受变化后，先修改本地代码和测试，再更新 `upstream-baseline.json`。
- 更新基准必须显式运行基准记录脚本，并带 `--confirm-reviewed`；不能把“看到更新”直接当成“已完成审查”。

```powershell
python <skill-dir>/scripts/capture_upstream_baseline.py --mirror <agents-root>/upstream/ConardLi-garden-skills --output <skill-dir>/references/upstream-baseline.json --confirm-reviewed
```
