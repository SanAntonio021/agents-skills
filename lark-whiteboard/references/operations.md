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
初始连接器目前要求目标在源框右侧且不高于源框；其他布局先创建后通过编辑器移动。
CLI 创建接口不支持连线引用本批次以外的旧形状。给已有图增加模块时，先仅追加新形状；
已有形状之间新增连线由编辑器 `connect` 复用一条现有连线的样式创建，不能把旧形状复制进追加批次。

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
| text | id, text（形状自身文字） |
| font | id, font_size |
| resize | id, width, height |
| move | ids, dx, dy |
| arrow | id, start/end 均为 none 或 line_arrow |
| caption | id, text；仅添加首个线标签 |
| line_type | id, shape 为 straight 或 polyline |
| reconnect | id 为连线，end_id 为新目标形状；沿用原终点锚定位置 |
| connect | template_id 为现有连线，start_id/end_id 为两端形状；复制线样式后重新绑定，新 ID 由结果回读取得 |
| group | ids；返回新增 group ID，再据其发起后续操作 |
| ungroup | id 为 group |
| align_top | ids，至少两个形状 |
| distribute_horizontal | ids，至少三个形状 |
| delete | ids 为选择对象；delete_ids 为预期消失的全部 ID，包含子对象及关联线 |
| undo | 仅放在同一次请求中的 delete 后一步；撤销该删除 |

组合 ID 由编辑器分配，禁止预猜。需要组合后移动时，先完成组合调用并读取新 ID，再发下一次请求。
改接只覆盖终点，更改起点尚未提供接口。任意曲线路径、已有标签替换、文字迁入形状不能借自由 JavaScript 偷换为“已支持”。

## 失败后

先看结果中已完成步骤和最后 raw 快照。CLI/API 错误与页面未保存分开报告。
未知写入结果不自动重试；重新读取确认真实状态后，只补尚未执行的修改。
原始快照提供恢复依据，但恢复也应以最新状态逐对象处理，不能自动把旧快照整板覆盖回去。
若页面被保留以等待保存，不另开重复写入；保留标签不等于保存已成功。
