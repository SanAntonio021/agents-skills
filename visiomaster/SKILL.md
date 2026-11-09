---
name: visiomaster
description: 在 Windows 上将已确认的文字讨论或参考图片绘制为可编辑 Visio 流程图、系统架构图和端口连接图，并打开已有 .vsdx 按页面和 Shape ID 局部修改原生模块、文字、分组及连线，保留其他对象。用户要求画 Visio、生成 .vsdx、修改旧 Visio 图或多轮修订时使用。场景起图以 .scene.json 迭代，旧图以当前 .vsdx 迭代；普通栅格科研配图交 research-schematic-imagegen，论文投稿图审查交 paper-figure-review。
---

# Visio 制图与多轮修改

**新建图从确认内容建立场景，已有图直接编辑当前 Visio 对象。** 两条路线都另存版本、导出 PNG 并实际看图。新建图保留 Visiomaster v0.3.2，旧图读取与基础写回复用 vsdx 0.6.1，来源及许可证见 [上游来源](references/upstream-source.md)。不需要安装或调用 ppt-master。

## 选择输入和正式源

先读取用户讨论、当前项目 README/AGENTS 和确认图，区分已确认关系、候选方案和待确认内容。文字起图直接据此建立节点、端口、连接方向及线型，不要求先生成截图。只询问会改变技术含义的缺口；未决内容写入 `metadata.pending_questions`，草图相应位置标“待确认”，不补造器件、参数或信号关系。

已有图需要保留对象时，先读取当前 `.vsdx`，走下方旧图入口；用户手改过 Visio 也适用。只有选择场景重建且场景仍与当前图一致时，才继续修改 `.scene.json`。场景重建会创建新文档，不能自动吸收 Visio 手改。整张嵌入图片内部没有可独立编辑的模块；说明具体受限对象并讨论重建，不自动替换整图。

模板只用于布局和格式，不能替代技术内容。选择 [系统架构](templates/system-architecture.scene.json) 或 [端口连接](templates/port-connections.scene.json)，替换合成示例。坐标和组件继续使用上游 [场景格式](vendor/upstream/references/scene-schema.md)，可用组件见 [组件表](vendor/upstream/references/visio-component-map.md)。流程图可使用上游 `vendor/upstream/templates/examples/basic_flow.scene.json`。

## 起图与中文排版

先列出已确认的节点、端口、方向和虚实线，再安排布局。物理端口名称和信号功能分别表达，不能凭习惯把 IF、LO、RF 重新归类。每个可见模块、标签、连接都用稳定 ID；分支、回路和交叉必须明确是否相连。用 `node:side@ratio` 锚点和明确转折点保持连线触边。

专利附图默认白底、黑线、宋体常规字形，图内主体字号统一；首次按图面密度选字号，用户指定时遵从指定值。模板以 18 pt 起步；调整框宽、留白、换行和局部走线解决拥挤，不靠缩小整张图应付。显式设置 `font_family: "SimSun"`、`font_role: "cjk_serif"`、`font_size_pt` 和 `text_fit: "none"`，中文与英文数字同一字体；单行标签声明 `single_line: true`。图号和总标题放文档图注，图面不另加总标题。

使用当前环境的 Python 和本地 Microsoft Visio。缺依赖时才安装 `requirements.txt`；不修改系统 PATH，不从可变上游镜像运行。先检查，随后在项目过程目录渲染候选，默认后台独立 Visio 实例，不接管用户窗口：

```powershell
python <skill-dir>/scripts/visio_workflow.py check <figure_v01.scene.json>
python <skill-dir>/scripts/visio_workflow.py render <figure_v01.scene.json> --output-dir <project-process-dir> --report <project-process-dir>/figure_v01.render.json
```

场景名去掉 `.scene.json` 即输出名，默认同时导出 `.vsdx`、PNG、SVG。已有输出拒绝覆盖，换下一个版本名。`metadata.pending_questions` 非空时只允许带 `--draft` 渲染，并在交付说明中明确未决项。细节、故障和图像复刻路线见 [操作说明](references/local-workflow.md)。

## 每轮修改和验收

### 已有 Visio 图

先检查并定位页面和对象，再生成与输入摘要绑定的顺序修改清单。文字搜索只辅助定位；重名、错误 ID 或输入变化时停止，不凭近似文字或距离猜对象及技术关系。默认保留旧图字体、字号和版式，仅调整本轮指定属性。操作格式、坐标、关联线和合成样例见 [旧图编辑](references/existing-visio.md)。

```powershell
python <skill-dir>/scripts/visio_edit.py inspect <figure_v01.vsdx> --output <process-dir>/figure_v01.inspect.json
python <skill-dir>/scripts/visio_edit.py apply <figure_v01.vsdx> --plan <process-dir>/round_v02.plan.json --output <process-dir>/figure_v02.vsdx
```

可改文字、字体字号、位置尺寸，可复制、新增和删除基本形状，调整连线端点、箭头、虚实线及普通折线路径。单一格式整段改字可选 `vsdx` 后端，其余由独立隐藏 Visio 实例处理。原生粘连连接由 Visio 联动并回读；普通线段必须明确列出线 ID、端点和标签，并在清单中执行相应调整。删除模块前明确处理关联线；不留下悬空关系。复杂分组或曲线未通过保真检查时报告具体对象，不自动重建。

每轮另存 `.vsdx`、每页 PNG 和含前后对象快照的 `.edit.json`，下一轮读取上一轮实际输出。输入 VSDX 不覆盖，后台实例不接管用户窗口。有匹配场景时绑定其摘要；完整映射可同步新版场景，不能完整回写时以 VSDX 为后续源并阻止旧场景直接重建。没有场景的旧图不强行转换。报告 `edited_pending_visual_review` 后继续实际看图，不能直接报验收完成。

### 场景重建

先把反馈映射到对象 ID，明确需要联动的框体、标签和走线，只修改这些对象。字号放大可能需要同步调整框体和路径，列入本轮对象集合；不顺带改变技术关系。另存下一版场景后重新渲染。再检查实际场景差异和像素变化：

```powershell
python <skill-dir>/scripts/visio_workflow.py compare --before-scene <figure_v01.scene.json> --after-scene <figure_v02.scene.json> --before-png <figure_v01.png> --after-png <figure_v02.png> --allow-id <changed-node> --allow-id <linked-edge> --report <process-dir>/round_v02.json
```

`--allow-id` 可重复，页面确需调整时加 `--allow-page`。仅改 metadata、无有效渲染变化、像素无变化或改到范围外时检查失败，不能报告修改成功。

**程序通过后仍要看图。** 打开实际 PNG，按需放大局部，核对中文和数字、压框压线、箭头方向、端口、虚实线、交叉和分支；与确认内容逐项对照。结构校验和文本高度检查不能证明连线、语义和美观已通过。直接读取或后台打开导出的 `.vsdx` 核对原生对象、字体和连接，不以文件存在代替验收。

## 交付与职责

确认后将同版本 `.vsdx`、PNG 及适用的 `.scene.json` 保存到项目正式位置；SVG 按用户需要交付。候选、检查记录和预览留在 `过程文件/任务主题/`。只在图件正式获确认、且本轮获授权更新文档时，通过现有文档制作链更新 Markdown/Word 图及图源引用；核对嵌入图片和引用版本一致，不把候选稿自动升级为正文插图。

专利内容、真实图件、私有讨论、项目绝对路径和检查日志留在本机项目。公开技能只包含通用流程和合成例子。说明本轮实际改了哪些对象、看图结果及未解决事项；脚本的 `rendered_pending_visual_review` 只表示导出成功。
