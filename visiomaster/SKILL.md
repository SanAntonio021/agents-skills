---
name: visiomaster
description: 在 Windows 上把已确认的文字讨论、流程和模块连接关系绘制为可编辑 Visio 流程图、系统架构图或端口连接图，也支持按参考图片重建。用户要求画 Visio、生成 .vsdx，或反复修改本技能生成图中的模块、端口、文字和连线时使用；以 .scene.json 为持续编辑源。普通栅格科研配图交 research-schematic-imagegen，论文投稿图审查交 paper-figure-review；不承诺旧 .vsdx 原位编辑。
---

# Visio 制图与多轮修改

**默认链路是已确认内容 → `.scene.json` → Visio → PNG → 看图修订。** 每轮保留可继续编辑的场景文件、原生 Visio 图形及预览。固定上游 v0.3.2，许可和本地边界见 [上游来源](references/upstream-source.md)。不需要安装或调用 ppt-master。

## 选择输入和正式源

先读取用户讨论、当前项目 README/AGENTS 和确认图，区分已确认关系、候选方案和待确认内容。文字起图直接据此建立节点、端口、连接方向及线型，不要求先生成截图。只询问会改变技术含义的缺口；未决内容写入 `metadata.pending_questions`，草图相应位置标“待确认”，不补造器件、参数或信号关系。

已有本技能的 `.scene.json` 时，以它为本轮编辑源，保留对象 ID。用户手改过 `.vsdx` 时先读当前文件和修改意见：场景重生成不会自动吸收这些手改，须把所需变化回写场景再继续。任意旧 `.vsdx`、旧图片可作为参考重新建立场景；需要保留旧对象原位编辑的请求说明当前边界，不假称已支持。

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

先把反馈映射到对象 ID，明确需要联动的框体、标签和走线，只修改这些对象。字号放大可能需要同步调整框体和路径，列入本轮对象集合；不顺带改变技术关系。另存下一版场景后重新渲染。再检查实际场景差异和像素变化：

```powershell
python <skill-dir>/scripts/visio_workflow.py compare --before-scene <figure_v01.scene.json> --after-scene <figure_v02.scene.json> --before-png <figure_v01.png> --after-png <figure_v02.png> --allow-id <changed-node> --allow-id <linked-edge> --report <process-dir>/round_v02.json
```

`--allow-id` 可重复，页面确需调整时加 `--allow-page`。仅改 metadata、无有效渲染变化、像素无变化或改到范围外时检查失败，不能报告修改成功。

**程序通过后仍要看图。** 打开实际 PNG，按需放大局部，核对中文和数字、压框压线、箭头方向、端口、虚实线、交叉和分支；与确认内容逐项对照。结构校验和文本高度检查不能证明连线、语义和美观已通过。直接读取或后台打开导出的 `.vsdx` 核对原生对象、字体和连接，不以文件存在代替验收。

## 交付与职责

确认后将同名同版本 `.scene.json`、`.vsdx`、PNG 保存到项目正式位置；SVG 按用户需要交付。候选、检查记录和预览留在 `过程文件/任务主题/`。只在图件正式获确认、且本轮获授权更新文档时，通过现有文档制作链更新 Markdown/Word 图及图源引用；核对嵌入图片和引用版本一致，不把候选稿自动升级为正文插图。

专利内容、真实图件、私有讨论、项目绝对路径和检查日志留在本机项目。公开技能只包含通用流程和合成例子。说明本轮实际改了哪些对象、看图结果及未解决事项；脚本的 `rendered_pending_visual_review` 只表示导出成功。
