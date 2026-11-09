# 上游来源与本地维护

本技能基于 [Rss3208/Visiomaster](https://github.com/Rss3208/Visiomaster)，固定标签 `v0.3.2`，提交 `0d8ccf2c015dc99935a71d2618fe0399e00a0d10`。GitHub 发布日期为 2026-09-14。MIT 许可及 Ren Shuai 原始版权声明保留在根目录和上游副本的 LICENSE。

**上游代码原样保留。** `vendor/upstream/` 包含该提交的受跟踪文件，字节校验清单为 `vendor/upstream-manifest.json`。本地新增中文入口、两个合成模板、后台实例管理和版本差异检查；不修改上游渲染器或场景规范，因此目前无需单独 fork。以后确需改变上游渲染或格式时，先建立维护 fork，再记录接受提交和差异；升级时比较固定基线，不直接覆盖本地入口。

**专利文字起图与连续修订。** 默认从已确认的讨论建立 `.scene.json`，以稳定节点和连线 ID 记录模块、物理端口、方向及线型；待确认事实保留在场景元数据中并阻止正式态导出。每轮单独保存场景、`.vsdx`、SVG、PNG，比较允许修改的对象，并要求 PNG 有可见变化。旧 `.vsdx` 可供参考，但不承诺保留原有对象进行原位编辑。

**上游测试存在已知边界。** `tests/test_gates_v04.py` 是独立脚本，直接运行可完成 22 项检查；把它当作 pytest 文件运行会因 `tmp` fixture 不存在产生四个错误。`test_public_release_smoke.py` 中 `visual_grammar_primitives` 示例缺少两处区域检查字段，严格校验失败。保持原样并记录，不通过删测试或声称全绿掩盖。新建图走本地模板和本地验收，不把该示例视作已经合格。

**本地入口补齐运行保护。** 上游 `scene_to_visio.py` 默认复用 `EnsureDispatch` 实例，导出失败也可能返回 0；本地入口直接调用其绘制函数，使用独立 `DispatchEx`、显式关闭文档和 stencil、核对导出文件及中文文字框。Visio 字符区中 `AsianFont` 使用单元格索引 51；本地回归测试确保不把字体公式误写到双下划线单元格。上游 no-op 分类器未匹配嵌套路径 `style.font_size_pt`，仅该字段单独变更且 PNG 尺寸不变、像素差异非空时使用本地窄范围回退；其他未知场景字段仍按上游门禁失败处理。新增逻辑均在 `scripts/visio_workflow.py`，上游脚本仍可单独使用，但日常制图使用本地入口。
