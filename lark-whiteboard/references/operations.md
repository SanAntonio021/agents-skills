# 调用方法

所有命令路径以实际安装的技能目录为准。请求、raw 快照、结果留在当前任务过程目录；不要存入公开技能源码。
需要 Python 3、已认证的 `lark-cli`，浏览器编辑还需要 `web-access` 前检返回的 protocol v2 Proxy。

## 读取与创建

先运行 `lark-cli whiteboard +export --help` 和 `lark-cli whiteboard +update --help` 核对当前 CLI。
CLI 文件路径相对于 cwd；例：

```text
lark-cli whiteboard +export --whiteboard-token <board> --output-type raw --output before.json --as user
lark-cli whiteboard +export --whiteboard-token <board> --output-type preview --output preview.jpg --as user
```

新画板由 `lark-doc` 插入 `<whiteboard type="blank"></whiteboard>`，从返回值取得文档链接和画板标识。
矩形、圆角矩形及连线使用 `native_nodes.py`，具体命令以 `--help` 为准。输入结构：

```json
{
  "shapes": [
    {"id":"o74001:1","text":"信号源","shape":"round_rect","x":80,"y":100,"width":180,"height":80,"font_size":20},
    {"id":"o74001:2","text":"处理模块","shape":"rect","x":400,"y":100,"width":180,"height":80,"font_size":20}
  ],
  "connectors": [{"id":"c74001:1","start_id":"o74001:1","end_id":"o74001:2"}]
}
```

为每次新图选择未使用的 ID，不能照抄示例 ID 到已有画板。原生 raw 在形状节点的**顶层 `text` 字段**放文字，
不是 `composite_shape.text`。追加用 runner 的 `--append-raw`；它不提供 overwrite 开关。
创建参数（均可省略，旧输入仍可使用）：

| 对象 | 字段 | 取值 |
|---|---|---|
| 形状 | border_color / fill_color / text_color | `#RRGGBB` |
| 连线 | border_color | `#RRGGBB` |
| 连线 | border_style | solid / dash / dot |
| 连线 | shape | straight / right_angled_polyline（服务端自动布线，不指定任意拐点） |
| 连线 | start_anchor / end_anchor | `{ "side":"top", "offset":0.5 }`；side 为 left/right/top/bottom，offset 为沿边的 0～1 比例 |
| 连线 | label | 首个线标签文本 |

默认起点在右侧中点、终点在左侧中点。指定锚点后允许向上、向下和向左连接，包围框尺寸保持非负。
例如驱动从模块下方接入，可用 `start_anchor:{"side":"top"}`、`end_anchor:{"side":"bottom"}`。
颜色、虚线、锚点与线标签仍须用线上 raw 和预览验收；下表后台编辑接口与本创建接口分开，不表示已有节点自动支持所有创建参数。
CLI 创建接口不支持连线引用本批次以外的旧形状。给已有图增加模块时，先仅追加新形状；
已有形状之间新增连线用 `connect`。有模板时复用其样式；无模板时只追加一条坐标线，再在重新加载的原生编辑器中绑定两端，不能把旧形状复制进追加批次。

```text
python <skill>/scripts/native_nodes.py --input diagram.json --output native.json
python <skill>/scripts/whiteboard.py --request target.json --append-raw native.json --output-dir <new-evidence-directory> --proxy-url <proxyUrl>
```

追加请求的 `operations` 为空。先验收追加并取得服务端实际 ID，再用新会话编辑，不沿用可能已过期的页面缓存。

## 后台编辑请求

```json
{
  "document_url":"https://<tenant>.feishu.cn/docx/<document>",
  "whiteboard_token":"<board>",
  "operations":[
    {"kind":"text","id":"<shape-id>","text":"本振信号源\n10 GHz"},
    {"kind":"font","id":"<shape-id>","font_size":24},
    {"kind":"move","ids":["<shape-id>"],"dx":0,"dy":80}
  ]
}
```

```text
python <skill>/scripts/whiteboard.py --request request.json --output-dir <new-evidence-directory> --proxy-url <proxyUrl>
```

`operations: []` 用于只读检查。每次运行创建独立后台标签，任务凭据只在内存中，正常完成后关闭自有标签。
请求明确指定文档和画板，不支持模糊搜索目标或自动迁移独立文本框。

| kind | 参数 |
|---|---|
| text | id, text（形状自身文字或独立文本框） |
| font | id, font_size |
| resize | id, width, height |
| move | ids, dx, dy |
| arrow | id, start/end；取值见下方箭头列表 |
| caption | id, text；无标签时新增，单标签时改写；空字符串清空并移除标签。支持多行，改写保留位置与格式 |
| caption_position | id；position 为 0～1 沿线比例；placement 为 on_line / above_line / below_line；至少提供一个，另一个保持原值 |
| caption_format | id；font_size 为 4～999；width 为不小于 10 的文字框宽度，自动换行；auto_width:true 恢复自动宽度。至少指定一项，width 与 auto_width 互斥，未指定的格式保持 |
| line_type | id, shape 为 straight / polyline / curve / right_angled_polyline |
| path | id, points；画布绝对坐标的中间点数组。折线为拐点，曲线须两端已绑定且恰好两个控制点；直线无拐点，正交线各段须水平或垂直 |
| curve_point | id, point 为画布 `{x,y}`；mode 可选 segment / turning，index 为从 0 开始的手柄下标。segment 拖动曲线段中点新增经过点，turning 移动已有经过点；默认有经过点则移动，否则新增，index 默认为 0 |
| style | id, style；border_color / fill_color / text_color 为 #RRGGBB，border_style 为 solid / dash / dot，border_width 为 extra_narrow / narrow / medium / bold；只更改提供的字段 |
| anchors | id 为已有连接线；start/end 可分别指定 `{snap_to:"bottom",position:{x:0.5,y:1}}`，仅改变锚点，保持两端绑定 ID |
| reconnect | id 为连线，start_id / end_id 可单独或同时指定；已有绑定保留原端锚点，首次绑定采用起点右侧中点、终点左侧中点 |
| connect | start_id/end_id 为两端形状；template_id 可选。省略时使用默认实线箭头，新 ID 由保存回读取得 |
| group | ids；返回新增 group ID，再据其发起后续操作 |
| ungroup | id 为 group |
| align_top | ids，至少两个形状 |
| distribute_horizontal | ids，至少三个形状 |
| delete | ids 为选择对象；delete_ids 为预期消失的全部 ID，包含子对象及关联线 |
| undo | 仅放在同一次请求中的 delete 后一步；撤销该删除 |

独立旋转模块的排列使用原生 `getBounds()` 外框，顶对齐核对可见顶部，水平等距按整个选择范围、各外框宽度与原生实际选择顺序核对。坐标可以不相同，外框必须满足排列要求。`arrangement_bounds` 是内部读数，不替换组合的 `object_bounds`；步骤中的 `arrangement_evidence` 和 `arrangement_reopened_bounds` 保存前后与重开核验依据。缺少边界或边界在提交前改变时拒绝写入。

组合 ID 由编辑器分配，禁止预猜。需要组合后移动时，先完成组合调用并读取新 ID，再发下一次请求。
新建组合明确选择的连线，其所有已绑定端点也必须在同一步选择集合内；单端绑定检查其已绑定一端，双游离线仍可组合。原生Group会排除跨选择边界的线，写前检查据实拦截，不能以服务端创建了部分成员组合当作原请求完成。
独立文字保留文本框身份，可以改字、字号、字色、移动和尺寸；不自动迁入形状。连线不支持填充色；没有标签时须先添加标签才能改标签字色。
已有一层组合的成员可以沿用 text / font / style / caption / caption_format / caption_position / arrow / line_type / path / curve_point / move / resize，直接提供成员 ID。未改成员的世界位置、属性及成员关系保持；父组只有经过成员几何核验的包围框变化可放行。同一步不能把组合及成员同时加入 ids，不能在组内增加或删除成员；旋转组或含旋转成员的组、复杂嵌套先拒绝写入。锚点刷新仍限两端均绑定的线，并在任何事务前核对实际需要临时移动的端点和关联锁定对象。
独立文字改字或字号时，原生编辑器可能按内容调整高度；验收仅对此放行目标文本框高度，仍保护原点、宽度、其他格式和无关对象。尺寸操作使用固定尺寸并核对指定宽高。

箭头取值：`none`、`line_arrow`、`triangle_arrow`、`empty_triangle_arrow`、`circle_arrow`、`empty_circle_arrow`、`diamond_arrow`、`empty_diamond_arrow`、`single_arrow`、`multi_arrow`、`exact_single_arrow`、`zero_or_single_arrow`、`single_or_multi_arrow`、`zero_or_multi_arrow`、`x_arrow`。

箭头文字属于连线。读出目标连线当前标签后，用 `caption` 改写，不能另加独立文本框盖住旧字。
需要避让时先按沿线比例移动，如 `{"kind":"caption_position","id":"<line-id>","position":0.75}`；改字与移位分别验收。
需上下避让时加 `"placement":"above_line"` 或 `"placement":"below_line"`。这对应原生线上、上方、下方三种模式；人工拖动将鼠标落点投到线上，再按距离与方向选模式，不把文字固定在鼠标的任意线外坐标。绝对标签坐标入口因此拒绝。
文字和位置编辑限单标签，一个标签内可写多行或多个段落。多标签指多个独立文字块：raw 可导入这种数据，但当前原生加载器只暴露首项；遇这种画板只读 raw，拒绝写入，避免隐含文字被删除。
清空会按原生编辑器语义移除标签；之后重新添加采用编辑器默认样式和中间位置，不承诺保留被删标签的格式。

需要调整长标签时，例如 `{"kind":"caption_format","id":"<line-id>","font_size":20,"width":180}`。固定宽度自动换行，显式换行仍保留；恢复自动宽度用 `"auto_width":true`。自动宽度也受原生测量上限影响，不保证长文字全部放在一行。字号和宽度操作保持标签内容、位置、连线和端点；改字及移位保留现有格式。

查看画面时，在请求顶层加 `"capture_preview":true`，可与编辑一起使用，或搭配 `"operations":[]` 只读观察。`inspect-000.json` 保存完整初始检查；编辑结果及 `visual-feedback.json` 的 `label_geometry` 按连线ID给出原生标签占位及屏幕位置，坐标以该次实际视口为准。runner 在自有页面等待两帧一致并排除画板全白的过渡画面，成功写入 `preview.png`，结果 `visual_status` 为 `needs_review`。执行智能体必须实际查看这张图，才能判断文字可见、换行和遮挡；几何数据及截图稳定不等于排版合格。
若 `visual_status:unavailable`，保存回读结果仍单独记录，使用新的只读观察重取画面，不重放修改。需要挪标签时，先据当前占位和图像选沿线比例或上下模式，改完再取截图。删除与紧接撤销仍在同一请求、同一编辑器中完成，截图在恢复后获取，不打断撤销栈。
观察入口会以已验原生回调刷新自有画布尺寸，前后必须保持内容、保存序号及撤销栈；建立截图基线和每次取图前后均须确认原生发送队列已清空、保存完成，applied_version 与基线严格相同。版本推进或转为未保存立即停止，只允许视口变化在原20秒上限内重新采样。被改标签在画面外或被裁切时不给可审截图状态。小数字号可用，CLI raw会将其截成整数，结果记录这一已观察差异；完整字号仍由原生保存和新页面严格核对。
默认先读取当前原生画布PNG，避免慢浏览器截图在超时后仍占用页面；原生图像明确不可用时再尝试浏览器合成截图，不重画图、不重放修改。`preview_source` 明示 browser_screenshot 或 native_canvas；后者不包含浏览器工具栏，几何屏幕坐标须扣除 `viewport.rect` 原点后对应到图像。两种图像都核对目标文字区域确有像素、两帧稳定，再交执行智能体查看。
整板仍至少需要24个白底可见深色像素，标签小区域只需1个；这仅判断截图非空，不证明文字可读或没有遮挡。透明或全白像素不算可见文字，最终仍须实际查看原图。
浏览器三次可见截图仍不稳定时也执行同一回退，`preview_fallback_reason` 记录原因；转换图像来源不延长原有总超时。
浏览器单张传输最多等待5秒且不超过本轮剩余预算，给原生回退留出时间；失败结果也保留 `preview_attempts`、回退原因及浏览器错误类型。
原生画布PNG保留透明背景；查看器显示黑底时应在白底查看器中打开原图，不能把显示背景误判为画板颜色或重新生成图像。

路径操作保持两端绑定和锚点，改变中间走线；自动直角线可先转换线型再读取生成的拐点。所有样式和路径编辑均须保存、服务端回读，不能仅凭页面显示验收。
`#RRGGBB` 按不透明主题色编码，独立 Opacity 属性不变。每步还核对原生渲染 alpha；颜色和新增线必须重开核对，并检查实际图像。RGB 字符串相同但对象透明不算完成。
曲线形状微调用 `curve_point`，既可处理绑定曲线，也可处理游离曲线。只读 inspect 的 `curve_handles` 按连线 ID 返回 `segment` 和 `turning` 的实际画布坐标；先据此选择手柄，再指定目标经过点，例如 `{"kind":"curve_point","id":"<curve-id>","point":{"x":410,"y":110}}`。再次调用默认移动已有的第一个经过点；需新增第二个点时明确指定 segment 和对应 index，不能把两个 Bezier 控制点当成经过点。
CLI raw 导出曲线经过点但省略 Bezier 控制向量；曲线控制点变化先由独立新页见证完整点列及首末点，确认保存后再关闭原写入页并执行普通重开验收。直接给游离四点曲线改两个控制向量会丢失 edited 状态，而人工拖动会写入可保存的经过点。`path` 保留原有两端绑定限制，游离曲线用 `curve_point`；一层组合内仍按成员 ID 调用并保护父组和其他成员。
长文档的目标画板未加载时，请求可提供 `section_id`（已有目录标题块 ID）和 `block_id`（画板文档块 ID）；
runner 点击页面真实存在的该目录链接，再滚动到准确画板块。二者不代替 `whiteboard_token`，进入后仍核对画板和文档身份。
目录链接或目标块不存在时停止，不跳到相似章节、不改整板覆盖。

## 失败后

先看结果中的全部步骤和最后 raw 快照。每步在提交前建立，不因后续失败而消失；CLI/API 错误与页面未保存分开报告。
`save_status` 为 not_written / unknown / confirmed，`verification_status` 为 pending / passed / failed，`failure_phase` 指出失败环节。提交前拒绝是 not_written + failed；响应丢失或保存回读超时是 unknown + failed；保存已确认而保护或重开失败是 confirmed + failed；必要数据验收全部完成才是 confirmed + passed。删除等待紧接撤销重开验收期间暂为 pending。
`visual_status` 仍独立记录图像是否可审。`pages` 和 `cleanup_receipts` 记录每次自有页面与换页/关闭回执，凭据不落盘；关闭超时按未知关闭状态报告，不能把 task 终态当成页面必已关闭。
`save_evidence` 记录内容调用前的 `save_fence` 及保存时的 `native_save` 回执：本次有可见变化时原生 `applied_version` 须推进，所有本地及有序待发队列须清空，processing/offline 为 false，保存状态完成。多事务先后入队时也不能仅凭旧 seq/savedSeq 相等判定保存；无变化操作仍须等待已入队事务完成。
raw 缺省或截断的字段变化由 `native_persistence` 记录独立新页见证；此时原写入页继续保留，保存状态先为 unknown，新页读到完整新值后才为 confirmed。新页仍是旧值时 `failure_phase:native_persistence`，不重放修改、不以组框缓存解释差异。只读见证页的关闭回执单列，关闭失败不能撤销已经取得的保存事实。
步骤也覆盖该步开始前的读取失败；删除已确认而紧接撤销读取失败时，删除保留 confirmed，延后验收改为 failed，撤销另有 not_written 失败记录。独立见证页的 `cleanup_errors` 和 `witness_cleanup_errors` 单列收尾及本地结果文件错误；保存事实保留。结果文件写入失败以 `report_write_status:failed` 报告，调用方标准输出含完整 `report`，不能因文件丢失掩盖已执行步骤。
初始化失败同样在调用输出的 `report` 中给出本次原因和 not_written；未生成本次结果文件时 `result:null`，不覆盖既有目录或引用旧报告。报告无法写入仍返回原失败，退出码为1。
保存稳定时间在未保存或服务端暂未就绪时重新计算，但总超时不延长。读取、分块传输和提交后轮询按本阶段剩余预算执行，返回后再次检查截止；新页见证沿用原保存截止。预览核对同一内容、保存序号、视口和实际像素比例；视口变化重新采样，内容变化停止观察。同RGB透明度修正也把目标标签纳入可见范围检查；PNG半透明像素按白底实际可见颜色判断，原图不加工。
一层组的 `group_cache_normalizations` 记录服务端父包围框与原生完整成员推导框的差异；不表示旧缓存已经更新。成员 ID、成员关系和其他组字段继续严格保护。`raw_exceptions` 仅列已取得真实证据的具体序列化差异。
重开时服务端可能才更新这四个缓存字段；只有完整成员和其他组属性严格不变、最新值与原生完整成员范围相符时，才在 `server_group_cache_catchup` 记录延迟更新。其他变化仍视为冲突。
追加入口将新节点的相对层序映射到现有根对象的最高层之后，结果给出 `append_layer_assignment`，保存回读再核对实际层号；原对象层号仍须完全保持。
`--append-raw` 写前检查当前构造的字段名称、类型、有限几何与角度、文字格式、形状与线型、单标签及边缘绑定。不支持未知字段、组成员构造、重复的绑定与绝对位置表示、自连接或新对象透明色；独立 `text_shape` 可不带 style。新增对象按真实ID映射比较所有请求raw字段，服务端补标签缺省不能改变显式格式；`appended_raw_exceptions` 仅记录已实证RGB大小写和合法标签缺省，`reopen_raw` 及其保护记录对应重开后的完整导出。画面入口失败单独给 visual unavailable，不改变已通过的数据验收。
新增形状必须取得 border/fill 透明度，有文字时另需 text；独立文字需 text；连线需 border，有非空标签时另需 text。要求分量完整且为1，其他返回分量仍须不透明；空标签不强求 text。缺失证据判验收失败，不重复追加，也不改已确认保存的事实。
未知写入结果不自动重试；重新读取确认真实状态后，只补尚未执行的修改。
无模板建线分两阶段。`connect-receipt-*.json` 保存幂等标识及 prepared / not_started / result_unknown 状态，区分本地准备或CLI未启动、已启动和未知结果；`connect-appended-*.json` 保存已回读的新线ID。若后续绑定失败，只对该ID补绑定，不能重建同一条线。已确认追加后的绑定写前拒绝仍保留该线的 confirmed 保存事实。
原始快照提供恢复依据，但恢复也应以最新状态逐对象处理，不能自动把旧快照整板覆盖回去。
若页面被保留以等待保存，不另开重复写入；保留标签不等于保存已成功。
