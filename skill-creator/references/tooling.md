# 触发优化与打包工具

## 自动触发与执行行为分开

指定加载技能后完成任务是行为测试，不证明普通请求会自动加载它。出现漏触发、误触发或用户要求优化描述时，再做触发测试。

现有 `scripts/run_eval.py` 和 `scripts/run_loop.py` 调用 `claude -p`，通过临时 `.claude/commands/` 条目观察加载。它们不是 Codex/Astra 测试器，也不完整复制每种宿主的真实技能发现机制。报告具体宿主与方法，不能由这项测试推断所有平台均通过。

## 准备与调用

先核对当前 Claude CLI、可用模型及运行环境；Windows 管道兼容性未验证时先做隔离小样本。脚本会从工作目录向上寻找最近的 `.claude`，仅切换到项目下的过程目录仍可能命中真实项目：在隔离测试根建立专用 `.claude`，先核对 `find_project_root()` 返回值位于允许写入的测试范围，再运行。工具不可用只阻塞该项测试，不虚构跨平台替代结果。

触发数据使用现有格式：
```json
[
  {"query": "用户实际可能提出的请求", "should_trigger": true},
  {"query": "职责相邻但应交给其他技能的请求", "should_trigger": false}
]
```

覆盖实际触发与容易混淆的近邻场景，避免只选明显无关的负例。不设固定条数；样本标签已有明确依据时自行准备，真实归属歧义才向用户确认。需要批量人工标注时可使用 `assets/eval_review.html`，保留既有占位符和 JSON 导出格式。

将 skill-creator 目录加入测试子进程的 Python 模块搜索路径，使 `scripts` 包可导入，并以隔离任务目录为工作目录。单次评测沿用：
```text
python -m scripts.run_eval --eval-set <queries.json> --skill-path <skill-dir> --model <Claude调用标识>
```

需要迭代优化才运行：
```text
python -m scripts.run_loop --eval-set <queries.json> --skill-path <skill-dir> --model <Claude调用标识> --report none --results-dir <task-process-dir>
```

按问题设置现有 `--num-workers`、`--timeout`、`--max-iterations`、`--runs-per-query`、`--holdout` 参数，不自动把脚本默认规模当成每次要求。后台默认 `--report none`，因为该脚本启用报告时会打开浏览器。

工具返回 `best_description` 后仍检查是否准确描述真实能力，按当前授权修改；保留训练与留出测试的区别。报告改善仅适用于本次样本和实际模型，不承诺稳定触发率。

## 格式检查与打包

`python <skill-root>/scripts/quick_validate.py <target-skill>` 检查基本结构，不能代替行为验收。Windows 读取中文前设 UTF-8，Python 使用 `PYTHONUTF8=1`。

用户需要可安装包时才调用：
```text
python <skill-root>/scripts/package_skill.py <target-skill> <task-process-dir>
```

沿用原名、许可及必要资源，核对包内容并按共享交付约定交付；已有源码仓库的定向发布由 `agent-rules` 完成，不要求用户再手动安装。
