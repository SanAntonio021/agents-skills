# Pattern Library Maintenance

## Purpose

定义 `command-memory` 模式库的写入方式，避免它膨胀成日志堆。

## Entry Template

```md
### Pattern: <short-id>
- scenario: <high-level command family>
- use_when: <when this pattern should be preferred>
- shell: <PowerShell / other>
- validated_shape: <command skeleton with placeholders>
- substitute_only: <which placeholders may be replaced at runtime>
- preflight: <checks to run before execution>
- env: <environment variables that must be set first, or `none`>
- avoid: <shapes that should not be reused>
- success_signal: <what counted as "validated">
- capture_rule: <when to update this entry instead of adding a new one>
```

## Write Rules

- 只写可复用命令骨架，不写真实用户路径、用户名、私有文件名。
- 同类场景优先更新已有条目，而不是重复增加近似条目。
- 失败命令不得直接入库，只有修正后并验证成功的形态才允许入库。
- 用 `<TOOL>`、`<INPUT_PATH>`、`<OUTPUT_PATH>` 这类占位符，不存一次性上下文。
- 如果同一任务里先失败后成功，默认把“成功的修正形态”视为候选入库对象；失败本身只用于帮助判断该成功形态是否值得沉淀。

## High-Value Capture

只有满足任一条件时才更新模式库：

- 同类命令之前失败过
- 这次模式属于高风险类型：
  - 编码
  - 引号
  - 路径
  - 外部 CLI
- 这次模式明显可跨任务复用

不要收录：

- 一次性项目私有命令
- 仅因当前工作目录或当前文件名偶然成功的写法
- 与本次上下文强绑定的具体路径或个人信息
- 尚未稳定验证的试错命令

## Recovery Capture

当同一线程内出现“第一次命令失败，第二次或后续命令在调整形态后成功”时，按下面方式处理：

1. 不记录失败命令全文。
2. 抽取成功命令中的可复用骨架，保留占位符。
3. 在 `avoid` 中概括此前失败的形态类别，例如：
   - bare `Get-Content` 读取中文 Markdown
   - 未加引号的中文路径
   - PowerShell 下未设 UTF-8 环境变量的 `python -c`
4. 优先更新最接近的现有条目；只有确实没有承载位置时，才新增窄场景文件。
5. 如果该问题已经在多个任务中重复出现，本次成功后应立即更新模式库，不再等待“以后再说”。
