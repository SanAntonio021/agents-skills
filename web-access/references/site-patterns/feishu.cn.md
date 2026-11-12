---
domain: feishu.cn
aliases: [飞书, Feishu, Lark, larksuite.com, BaseApp, 多维表格应用]
updated: 2026-11-12
---

## 平台特征

飞书多维表格的应用模式（BaseApp）页面编辑器基于 `react-grid-layout`。组件外层是 `.react-grid-item`，组件本身的类名含 `widget-container-<组件ID>`，标签组件为 `widget-TABS`，当前标签内容区带 `tabs-widget-tab-pane-active`。组件 ID 与 `lark-cli base +app-block-list` 返回的 `widget_id` 一致，可以用它在页面和 CLI 之间对照。以下均为 2026-11 在 Windows Edge 后台标签中验证。

## 有效模式

### 进入页面编辑器

- 打开 `https://<租户>.feishu.cn/app/<app_token>?pageId=<页面ID>`，再点左上角应用名旁的编辑图标（`.edit_icon`，悬停提示“编辑应用”）。进入后 URL 带 `mode=edit`，右上角出现“预览”“完成编辑”，页面底部出现“+ 添加组件”。
- `/base/<base_token>?appPageId=...` 打开的是普通多维表格视图编辑器，不是页面编辑器。
- 浏览器窗口太窄时提示“当前窗口过小，无法编辑”，要换成足够宽的窗口。

### 查找坐标

- “+ 添加组件”等浮动按钮的位置随页面滚动变化，每次都按文字现查 `getBoundingClientRect()`，不要沿用旧坐标。
- 组件菜单有搜索框，可以用 `document.execCommand('insertText', false, '表格')` 输入中文。

### 拖动和缩放组件

- 用合成鼠标事件拖动时，每个 `mousedown`、`mousemove`、`mouseup` 都单独发一次 `/eval`，让页面在事件之间完成渲染。
- 拖动组件的抓手是 `.widget-container-header-drag-handle`。要先在组件内部找一个不压在按钮或选项上的空白点单击选中组件，抓手才能点中。
- 目标位置在页面顶部时：先移动几步，再把滚动容器 `[class*=page-view-scroll-container]` 的 `scrollTop` 设为 0，然后继续移动并松开。放下前读 `.react-grid-placeholder` 的位置；移动顶层组件时，确认它没有误落进标签组件里。
- 缩放时，用 `elementFromPoint` 命中的元素可能是 `resizeHandle-clickarea-<方向>`，它也是有效的缩放抓手。

### 往标签里放组件

- 菜单里的组件不能拖进标签，合成拖拽不会出现 `.react-grid-placeholder`。
- 可靠做法分两步：先切到目标标签，用 `/click-at` 点菜单项方块上部的图标（`.app-page-add-button-popover-item` 顶边往下约 25px，先确认 `elementFromPoint` 命中该项），组件会加到页面底部；再按上节方法拖它的抓手，松开前确认占位框落在 `tabs-widget-tab-pane-active` 所属的标签组件内。松开后读组件的父容器，确认已进入该标签（2026-11-12，两个页面共 5 次成功）。
- 原生表格组件不能直接引用表里已有的视图。筛选、分组、排序和可见字段要在组件配置面板里逐项设置。

### 配置面板

- 下拉选项是虚拟列表，不在可视范围内的选项不在 DOM 里。选中下拉框后按方向键 ArrowDown 滚动，直到目标选项出现。
- 字段显示设置里，每个字段的显隐状态看行内 SVG 的 `data-icon`：`VisibleOutlined` 表示显示，`InvisibleOutlined` 表示隐藏。
- 面板内控件超出视口时，先找到面板实际的滚动容器，设置它的 `scrollTop`，再去点。
- 筛选条件里的数字值要用 `/action` 的 `press` 逐键输入；`execCommand('insertText')` 只改输入框显示，条件不生效。人员字段按“访问者本人”筛选时，分三次调用完成：添加条件选字段、把运算符改为“包含”、再选“访问者本人”。

## 已知陷阱

- **整段操作塞进一次 eval 会超时**：在一次 `/eval` 里用 async 循环加 sleep 做整段拖拽，Broker 返回 504（`UNKNOWN_RESULT` 或 `CDP_TIMEOUT`），之后当前标签页失效，需要重新 `start` 和 `open`，并重新进入编辑模式（2026-11-12）。
- **点菜单项文字未插入组件**：点菜单项的文字标题或搜索结果，菜单关闭，但组件没有加上；要点图标，见“往标签里放组件”（2026-11-12）。
- **后台标签页画面不刷新**：标签页在后台时，截图会停在旧画面，菜单和弹层的位置也可能读到屏幕外的坐标（如 -9999）。每次点击后先截一帧，再读坐标或截图（2026-11-12）。
- **单次调用太长会被挂起**：一次命令串联十几步点击，可能超时，或一直占着目标标签页，后续调用报 `TARGET_BUSY`。按步骤拆成短调用；遇到 `TARGET_BUSY` 时等十几秒再重试（2026-11-12）。
- **`/app/<token>/edit` 不是编辑入口**：这个路径打开了一个“未命名应用”，不是目标应用；用后要核实有没有误建应用（2026-11-12）。
- **URL 参数 `mode=base-editor` 无效**：加在 `/app/` 链接上，页面仍是查看模式（2026-11-12）。
