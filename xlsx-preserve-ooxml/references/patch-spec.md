# OOXML 定点补丁规范

`patch_ooxml.py` 接受 UTF-8 JSON。顶层 `sheets` 以工作表名称为键。

## 完整示例

```json
{
  "sheets": {
    "成信大": {
      "cells": {
        "B6": {"kind": "number", "value": 13},
        "W8": {"kind": "string", "value": "1. 终端2台；\n2. 配套软件。"},
        "AD6": {"kind": "blank"},
        "AE6": {
          "kind": "formula",
          "formula": "AC6*AD6",
          "cached": 140,
          "result_type": "number"
        }
      },
      "row_heights": {
        "17": 420,
        "18": 420
      },
      "data_validation": {
        "require_count": 1,
        "index": 0,
        "sqref": "AH6:AH18"
      },
      "page_setup": {
        "orientation": "landscape",
        "paperSize": "8",
        "fitToWidth": "1",
        "fitToHeight": "0",
        "fitToPage": true
      },
      "row_breaks": [7, 9, 11, 13, 15, 17],
      "print_area": "$A$1:$AI$18",
      "print_titles": "$3:$3"
    }
  }
}
```

未出现的属性保持不变。

## 单元格类型

- `string`：写入 `inlineStr`，保留原单元格样式。
- `number`：写入数值；`value` 必须是 JSON 数字。
- `boolean`：写入布尔值。
- `blank`：删除公式和值，保留单元格及样式。
- `formula`：写入公式和可选缓存。公式不含开头 `=`。

公式 `result_type` 可为：

- `number`：默认；
- `string`；
- `boolean`；
- `error`。

公式变更后优先不提供 `cached`，再走 LibreOffice 隔离重算和缓存合并。示例中的缓存只适用于结果已经独立确认的情况。

## 保护规则

- 脚本拒绝源路径与输出路径相同。
- 输出已存在时拒绝写入。
- 默认只修改已存在单元格。需要创建新单元格时加 `--allow-new-cells`。
- 共享公式单元格默认拒绝直接改写，避免破坏共享公式组。
- `data_validation.require_count` 用于锁定验证条目数；不匹配时停止。
- `print_area` 和 `print_titles` 写入工作簿定义名称，只更新目标工作表对应项。
- `row_breaks` 会替换目标表的手动横向分页点；空数组表示清除手动横向分页。

## 补丁后检查

补丁命令只证明 XML 可写，不证明业务正确。至少执行：

```powershell
python <skill-root>\scripts\verify_xlsx.py output.xlsx --baseline input.xlsx --policy policy.json
```

如改过公式，再完成隔离重算、缓存合并和零错误检查。
