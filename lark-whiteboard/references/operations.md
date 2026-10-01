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
| line_type | id, shape 为 straight / polyline / curve / right_angled_polyline |
| path | id, points；画布绝对坐标的中间点数组。折线为拐点，曲线须两端已绑定且恰好两个控制点；直线无拐点，正交线各段须水平或垂直 |
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

组合 ID 由编辑器分配，禁止预猜。需要组合后移动时，先完成组合调用并读取新 ID，再发下一次请求。
独立文字保留文本框身份，可以改字、字号、字色、移动和尺寸；不自动迁入形状。连线不支持填充色；没有标签时须先添加标签才能改标签字色。
独立文字改字或字号时，原生编辑器可能按内容调整高度；验收仅对此放行目标文本框高度，仍保护原点、宽度、其他格式和无关对象。尺寸操作使用固定尺寸并核对指定宽高。

箭头取值：`none`、`line_arrow`、`triangle_arrow`、`empty_triangle_arrow`、`circle_arrow`、`empty_circle_arrow`、`diamond_arrow`、`empty_diamond_arrow`、`single_arrow`、`multi_arrow`、`exact_single_arrow`、`zero_or_single_arrow`、`single_or_multi_arrow`、`zero_or_multi_arrow`、`x_arrow`。

箭头文字属于连线。读出目标连线当前标签后，用 `caption` 改写，不能另加独立文本框盖住旧字。
需要避让时先按沿线比例移动，如 `{"kind":"caption_position","id":"<line-id>","position":0.75}`；改字与移位分别验收。
需上下避让时加 `"placement":"above_line"` 或 `"placement":"below_line"`。这对应原生线上、上方、下方三种模式；任意线外绝对坐标不会被当前渲染器使用，入口拒绝。
文字和位置编辑限单标签。raw 可导入多条文字，但当前原生加载器只暴露首项；遇这种画板只读 raw，拒绝写入，避免隐含文字被删除。
清空会按原生编辑器语义移除标签；之后重新添加采用编辑器默认样式和中间位置，不承诺保留被删标签的格式。

路径操作保持两端绑定和锚点，改变中间走线；自动直角线可先转换线型再读取生成的拐点。所有样式和路径编辑均须保存、服务端回读，不能仅凭页面显示验收。
`#RRGGBB` 按不透明主题色编码，独立 Opacity 属性不变。每步还核对原生渲染 alpha；颜色和新增线必须重开核对，并检查实际图像。RGB 字符串相同但对象透明不算完成。
CLI raw 不导出曲线控制点；曲线编辑还须关闭自有页面、重新加载后比较完整原生控制点。游离曲线的控制点会被当前加载器规范化为默认值，入口写前拒绝，不能宣称任意曲线都可编辑。
长文档的目标画板未加载时，请求可提供 `section_id`（已有目录标题块 ID）和 `block_id`（画板文档块 ID）；
runner 点击页面真实存在的该目录链接，再滚动到准确画板块。二者不代替 `whiteboard_token`，进入后仍核对画板和文档身份。
目录链接或目标块不存在时停止，不跳到相似章节、不改整板覆盖。

## 失败后

先看结果中已完成步骤和最后 raw 快照。CLI/API 错误与页面未保存分开报告。
未知写入结果不自动重试；重新读取确认真实状态后，只补尚未执行的修改。
无模板建线分两阶段。`connect-receipt-*.json` 保存一次提交的幂等标识，`connect-appended-*.json` 保存已回读的新线ID；若后续绑定失败，只对该ID补绑定，不能重建同一条线。
原始快照提供恢复依据，但恢复也应以最新状态逐对象处理，不能自动把旧快照整板覆盖回去。
若页面被保留以等待保存，不另开重复写入；保留标签不等于保存已成功。
