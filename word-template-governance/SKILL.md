---
name: word-template-governance
description: 维护 `word-muban-geshihua` 背后的预设体系和默认模板规则。Use when 任务是重建或校验 `tongyong-moren`、评估样例是否应升级为预设、调整当前默认预设，或安装和刷新 Word 全局 `Normal.dotm`；defer 普通文档格式统一到 `word-muban-geshihua`。
---

# Word 模板治理

## 作用

这份 skill 不负责“把某份文档排好版”，而是负责维护排版体系本身。

它主要处理四类低频但高影响的任务：

- 重建或校验 `tongyong-moren`
- 决定当前默认预设是谁
- 判断某个样例 `.docx` 能不能升级成可复用预设
- 把当前默认模板安装到 Word 的 `Normal.dotm`

普通交付场景一律回到 [../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md)。

## 流程

1. 先判断这次是“治理任务”还是“交付任务”。
   如果用户只是想把一份文档排版成某种格式，不进入这里。
2. 治理任务开始前，先读：
   [../word-muban-geshihua/references/template-governance.md](../word-muban-geshihua/references/template-governance.md)
   和
   [../word-muban-geshihua/references/template-presets.md](../word-muban-geshihua/references/template-presets.md)。
3. 如果目标是校验当前默认预设，先跑验证脚本，看 `tmp/` 里的证据文件是否符合预期。
4. 如果目标是重建 `tongyong-moren`，先重建，再立刻重新验证，不要只重建不校验。
5. 如果目标是安装 `Normal.dotm`，先确认 Microsoft Word 已关闭，再执行安装脚本。
6. 如果目标是评估候选样例，先看它是不是稳定、通用、可复用，再决定是否升级；不要把一次性填表样例或手工痕迹很重的文档直接升为预设。
7. 最终结论要明确写清：
   `不调整`、`仅重建`、`通过校验`、`安装到 Normal.dotm`、`候选样例通过`、`候选样例拒绝`。
8. 如果默认预设真的变了，要同步影响到 [../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md) 的说明和脚本默认参数，而不是只在治理说明里记一笔。

## 常用命令

### 重建 `tongyong-moren`

```powershell
python ..\word-muban-geshihua\scripts\build_master_template.py
```

### 校验当前默认预设

```powershell
python ..\word-muban-geshihua\scripts\validate_master_default.py
```

### 安装到 Word 的 `Normal.dotm`

先关闭 Microsoft Word，再执行：

```powershell
python ..\word-muban-geshihua\scripts\install_normal_template.py
```

常用参数：

- `--template <path>`：用指定模板替代当前默认预设
- `--normal-template <path>`：显式指定目标 `Normal.dotm`

## 规则

- 这里是治理入口，不是普通格式化入口。
- 升级为预设的样例，必须可复用、稳定、不过度依赖手工局部修改。
- 没有足够稳定的候选样例时，宁可回到重建 `tongyong-moren`，也不要硬推一个质量一般的样例成为默认值。
- 重建或切换默认值之后，必须立即验证。
- 文档和规则中统一使用拼音预设名；旧英文名只保留兼容意义，不作为主名称。
- 所有脚本、预设文件和参考资料都继续以 `word-muban-geshihua` 为单一来源，不在这里复制一套。

## 边界

- 不负责具体文档的日常格式统一。
- 不负责普通 Markdown 转 Word 成稿。
- 这些交付任务交给 [../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md)。

## 相关文件

- 交付入口：[../word-muban-geshihua/SKILL.md](../word-muban-geshihua/SKILL.md)
- 治理说明：[../word-muban-geshihua/references/template-governance.md](../word-muban-geshihua/references/template-governance.md)
- 预设说明：[../word-muban-geshihua/references/template-presets.md](../word-muban-geshihua/references/template-presets.md)
- 重建脚本：[../word-muban-geshihua/scripts/build_master_template.py](../word-muban-geshihua/scripts/build_master_template.py)
- 校验脚本：[../word-muban-geshihua/scripts/validate_master_default.py](../word-muban-geshihua/scripts/validate_master_default.py)
- 安装脚本：[../word-muban-geshihua/scripts/install_normal_template.py](../word-muban-geshihua/scripts/install_normal_template.py)

## 维护

- 默认预设一旦调整，要同步文档、脚本默认值和用户可见说明。
- 如果以后出现新的稳定模板族，优先在治理规则里补准入标准，不要先堆命令示例。
