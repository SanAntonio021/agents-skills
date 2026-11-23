---
domain: feishu.cn
aliases: [飞书, Feishu, Lark, larksuite.com, BaseApp, 多维表格应用]
updated: 2026-11-21
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
- 不拖动也能放进标签：组件右上角 `⋮`（`.widget-container-block-menu-config-button`）→“移入”→标签组件名→标签名。“移入”是悬停展开的子菜单，后台标签页里先按[后台弹层处理](../cdp-interaction.md#后台标签页的弹层与菜单)装补丁，再对子菜单项调用 React `onMouseEnter` 逐级展开，最末级的标签项直接 `.click()`。完成后用 `lark-cli base +app-block-list` 读回该组件的 `parent` 已变成目标标签面板的 ID（2026-11-18，1 次成功）。
- 用“添加组件→表格”加的组件，有时要重新加载编辑页才出现在 DOM 里；`+app-block-list` 能先读到它（2026-11-18）。

### 新增标签

- 选中标签组件，`⋮`→“配置”，右侧“标签页”面板的“标签”列表下有“添加标签”按钮，新标签默认名为“标签 N”。改名时用原生 `value` setter 写入该输入框，依次派发 `input`、`change` 后再 `blur`，然后回读标签栏文字（2026-11-18）。
- 新标签是空的，提示“拖拽组件至标签页”，放组件见上节。
- 调整标签顺序：在同一面板拖标签项左侧的 `.tabs-widget-edit-panel-item-handle`。对抓手派发 `pointerdown`+`mousedown`，再分几次 `/eval` 对 `elementFromPoint` 命中的元素和 `document` 派发 `pointermove`+`mousemove`，最后派发 `pointerup`+`mouseup`；标签内容随标签一起移动。项右侧的“更多”菜单只有“移入组件”“删除”，没有上移下移（2026-11-22，1 次成功）。

### 配置面板

- 下拉选项是虚拟列表，不在可视范围内的选项不在 DOM 里。选中下拉框后按方向键 ArrowDown 滚动，直到目标选项出现。
- 字段显示设置里，每个字段的显隐状态看行内 SVG 的 `data-icon`：`VisibleOutlined` 表示显示，`InvisibleOutlined` 表示隐藏。
- 面板内控件超出视口时，先找到面板实际的滚动容器，设置它的 `scrollTop`，再去点。
- 筛选条件里的数字值要用 `/action` 的 `press` 逐键输入；`execCommand('insertText')` 只改输入框显示，条件不生效。人员字段按“访问者本人”筛选时，分三次调用完成：添加条件选字段、把运算符改为“包含”、再选“访问者本人”。
- 表格工具栏的“筛选”是浏览者自己的临时筛选，不保存到组件；组件条件在 `⋮`→“配置”→“数据可见范围”的“可见记录”里。条件编辑器关闭（点配置面板空白处）后才保存，`+app-block-get` 读回可能晚几秒（2026-11-18）。
- 条件编辑器在后台标签页里：字段下拉项 `.bitable-dropdown-select__item` 用 `/click-at` 点不中（命中下层面板），对该项依次派发 pointer/mouse 事件序列后生效；运算符下拉项 `.ud__select__list__item` 调用其 React `onClick` 生效。每次选完先读回条件行文字再继续（2026-11-18）。
- “可见字段”面板只能拖动调整顺序，关闭再打开字段的显示开关不会改变位置；能用 CLI 时改用 CLI，见下节。必须在面板里拖时：
  - 对字段项的 `.drag-icon-container` 派发 `mousedown`，之后的 `mousemove`、`mouseup` 都发给 `document`，每个事件单独一次 `/eval`。只发给字段项本身不会开始拖动（2026-11-18 失败的原因）。
  - 列表只露出几行时，拖动中逐步设置 `.bitable-field-panel-list` 的 `scrollTop` 并派发 `scroll`，再把鼠标移到目标位置。
  - 主字段那一行锁定，不在排序区内。松手点落在主字段行上时拖动结束但顺序不变，要落在主字段下面第一项的上半部分。
  - 面板关闭后才保存，用 `+app-block-get` 读回 `visible_fields` 确认（2026-11-22，第二次成功）。
  - 放下后字段项的 DOM 顺序会滞后于屏幕顺序，读当前顺序要按各项 `getBoundingClientRect().top` 排序，不按节点先后；最终以接口读回为准。
  - 往下拖、以及只往上挪一格，经常放下后顺序不变。可靠做法是把下方字段往上拖到两格以上的位置，鼠标停在目标项上沿往下约 8px 再松手；需要“往下挪”时，改成把它下面的字段往上拖（2026-11-23，三张表共约 20 次拖动中归纳）。

### 与 lark-cli 配合

- 表格、看板、甘特等视图组件（`+app-block-list` 中 `type: view`）的名称、`visible_fields`、`filter`、`sort_by`、`group_by` 可以用 `+app-block-update --no-validate` 修改；不加该参数时本地校验不认这些字段。服务端会连同组件已有条件一起校验：已有条件含“访问者本人”（`{"$slot":"current_user"}`）时，即使本次不传 `filter`，整次更新也会被拒，这类组件只能在编辑器里改（2026-11-18）。
- 条件写法：复选框用 `{"operator":"is","value":false}`（或 `true`）；单选可直接写选项名，服务端会存成选项 ID。`isNot` 某选项时，该字段为空的记录也算满足条件（2026-11-22 读回条数核实）。
- CLI 不能新建视图组件（`--type` 不接受 `view`），也不能改变组件所在的标签；这两步要在编辑器里做，字段、筛选和排序再交给 CLI 设置。
- **接口更新会清空“父记录字段”**：表格组件的树状显示靠配置面板里的“父记录字段”，`+app-block-get` 读不到这项，`+app-block-update` 提交后它会被清空，表格退回平铺（2026-11-21 复现）。对树状表格用过接口后，必须进编辑器 `⋮`→“配置”把“父记录字段”设回原字段，再在浏览模式确认能展开。

## 已知陷阱

- **整段操作塞进一次 eval 会超时**：在一次 `/eval` 里用 async 循环加 sleep 做整段拖拽，Broker 返回 504（`UNKNOWN_RESULT` 或 `CDP_TIMEOUT`），之后当前标签页失效，需要重新 `start` 和 `open`，并重新进入编辑模式（2026-11-12）。
- **点菜单项文字未插入组件**：点菜单项的文字标题或搜索结果，菜单关闭，但组件没有加上；要点图标，见“往标签里放组件”（2026-11-12）。
- **后台标签页画面不刷新、弹层在屏幕外**：标签页在后台时，截图会停在旧画面，菜单和弹层的位置会读到屏幕外的坐标（如 -9999），子菜单悬停不展开。每次点击后先截一帧再读截图；弹层和菜单按[后台弹层处理](../cdp-interaction.md#后台标签页的弹层与菜单)装 `requestAnimationFrame` 补丁后重新打开（2026-11-12 发现，2026-11-18 用补丁解决）。
- **单次调用太长会被挂起**：一次命令串联十几步点击，可能超时，或一直占着目标标签页，后续调用报 `TARGET_BUSY`。按步骤拆成短调用；遇到 `TARGET_BUSY` 时等十几秒再重试（2026-11-12）。
- **`/app/<token>/edit` 不是编辑入口**：这个路径打开了一个“未命名应用”，不是目标应用；用后要核实有没有误建应用（2026-11-12）。
- **URL 参数 `mode=base-editor` 无效**：加在 `/app/` 链接上，页面仍是查看模式（2026-11-12）。
