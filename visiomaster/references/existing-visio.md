# 已有 Visio 图的局部编辑

## 定位与输入

`inspect` 默认用固定 vsdx 库读取文件结构，再用独立隐藏 Visio 实例读取有效属性，输出 SHA-256、页面、Shape ID、父分组、文字、位置尺寸、字符格式和原生连接清单。`--offline` 只读包内结构，不含继承后的有效属性和完整连接检查。`--search-text` 要求唯一匹配，最终仍用页面及 Shape ID 定位。

新建图的场景坐标以左上角为原点；旧图 COM 坐标使用英寸、左下角原点，位置是 PinX/PinY。分组子对象坐标相对于父分组，不可直接套用页面坐标。先看快照再写修改清单。

```powershell
python <skill-dir>/scripts/visio_edit.py inspect <input.vsdx> --output <process-dir>/input.inspect.json
python <skill-dir>/scripts/visio_edit.py apply <input.vsdx> --plan <process-dir>/edit.plan.json --output <process-dir>/figure_v02.vsdx
```

修改清单 `version: 1`，`input_sha256` 取本轮实际输入摘要，`operations` 按顺序执行。下一轮重新读取上一轮输出，不能沿用旧摘要。使用 [合成修改清单](../templates/existing-edit.plan.json) 时，替换摘要和检查得到的对象 ID，不能把示例数字用于真实图件。

## 操作字段

每项操作包含 `op`、`page_id`；已有对象必须有 `shape_id`。`expect_text` 可校验操作前当前文字，`search_text` 可辅助检查唯一定位。新增对象以 `as` 命名，后续用 `$别名` 引用，仅能用于同页。

| op | 参数与含义 |
|---|---|
| `text` | `text` 替换整段；富文本用 `start/end` 指定半开区间，保留范围外格式 |
| `font` | `font`、`size_pt`；可配 `start/end`，默认整段，中文与西文字体槽同时设置 |
| `move` | 每轴用绝对 `x/y` 或相对 `dx/dy`，附 `ordinary_links` |
| `resize` | 正数 `width/height`，附 `ordinary_links`；分组子对象仅在比例缩放可核实的情况下放行 |
| `copy` | `as`、可选 `dx/dy/text`；复制分组时包含子对象 |
| `add` | `as`、`kind`；rectangle/ellipse 用 `box: [左,下,右,上]`，line/polyline 用 `points`，可选 `text` |
| `delete` | 删除对象及分组子对象，附 `ordinary_links`；关联原生连接必须在后续清单中删除或重接 |
| `line` | `begin/end: [x,y]`，或 `begin_glue/end_glue`，或完整 `points`；可改 `start_arrow/end_arrow/line_pattern` |

`line` 箭头和线型使用 Visio 的数值代码，例如 `end_arrow: 4`、`line_pattern: 2`；实际图面核对样式，不能凭代码推定观感。完整 `points` 与端点操作分开执行；同一端点不可同时指定坐标和粘连。粘连写法如 `end_glue: {"shape_id": 2, "position": [0, 0.5]}`，position 为目标框的归一化位置，也可指定 `cell`，默认 PinX。保存前回读实际目标，保存后再次核对连接。

富文本范围使用 Visio Characters 的偏移。首版仅支持 BMP 字符的局部文字或格式修改，包括常用中文；包含 emoji 等非 BMP 字符的范围编辑明确拒绝，不能把 Python 字符下标直接当作 Visio 偏移。局部字号当前要求整数点。含文本字段的文字替换、复杂曲线路径或无法核实的分组缩放会报告具体对象。

## 原生连接和普通线段

原生连接有 Connect 记录，移动或缩放模块时由 Visio 联动，程序检查其有效属性及关系。重新粘连可能给目标模块新增连接点，这属于该操作的明确联动范围。

普通线没有可依赖的归属信息。移动、缩放或删除模块时必须显式声明 `ordinary_links`，没有关联普通线时填空数组。每个关联项指定 `shape_id`、`endpoints: ["begin"]` 或 `["end"]`，可附 `label_ids`；清单还必须包含这些线端点及标签的实际操作。不能按距离自动猜技术关系，检查脚本也不能证明人工声明完整。删除模块时逐一查看并处理所有关联线。

`backend` 默认 `com`。选 `vsdx` 时仅允许单一格式整段文字替换，其他类型拒绝；同一对象多次修改也按当前文字顺序检查。无论选哪个后端，都必须用本机 Visio 重新打开、导出并验收。

## 版本、场景与验收

输入 VSDX 永不覆盖，输出使用新版本名；已有同版本 VSDX、PNG、场景或记录时拒绝写入。每页导出 `<版本>.page-<页面ID>.png`，`.edit.json` 保留计划、输入摘要、前后快照、变动属性、文件摘要及后续编辑源。失败记录保留为 `failed`，已产生文件留作排查，换新版本重试。

同名 `.scene.json` 自动发现，或用 `--scene` 提供；计划同时绑定 `scene_sha256`。仅当单页、无连接无素材、全部基本节点一一映射且源场景文字坐标一致时同步新版场景，其他情况明确以 VSDX 继续。成功后旧场景新增 `metadata.native_edit_state.superseded` 及旁车记录，本地 `check/render` 阻止旧场景直接重建；原场景内容仍保留，标记也随场景复制。不能完整同步时不虚构新版场景。外部直接调用上游渲染器会绕过此保护，日常统一使用本地入口。

自动验收比较对象内容、核心属性、字符格式、几何和连接，不以压缩包字节变化判断误改；保存后重新读取应与操作结果一致。它不能证明全部 Visio 公式、插件对象、主题或外部链接的完整语义保真。遇到复杂对象的差异时保留失败材料，报告具体对象与属性，不自动整图重建。

程序状态 `edited_pending_visual_review` 表示属性和导出检查已通过，仍需实际查看 PNG 的整页及拥挤局部，核对中文字体、压框压线、端口、走线、箭头和技术关系。视觉验收结论与所看版本写入项目 README 或项目已有记录，原始 `.edit.json` 保留程序状态。真实专利图、快照和验收材料仅存本机项目，公开仓库只收通用代码及合成样例。
