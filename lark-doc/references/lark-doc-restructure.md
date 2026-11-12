# 重排已有内容（保留图片、附件、画板和已填表格）

把已有段落或列表改成表格、调整块顺序时，文档里往往已经有上传的图片、附件、画板和填过的表格。这些块一旦删除，只能重新上传或重画，所以重排全程不删除、不重建它们，只做四件事：插入新内容、给名称段落改名、移动位置、删除已被取代的文字块。读取和写入的通用规则仍按 [`+update`](lark-doc-update.md)，表格写法见 [`lark-doc-xml.md`](lark-doc-xml.md)。

## 做法

1. **改写前读全文并保存。** `docs +fetch --detail with-ids` 读取全文存成文件，留作最后比对，同时记下 revision，需要回退时见[历史版本](lark-doc-history.md)；再按节读取（`--scope section --start-block-id <标题id> --detail with-ids`），拿到本节各块的 ID。重排只回写名称段落的文字，`with-ids` 已够用。
2. **新内容用插入。** 新表格、新段落用 `block_insert_after` 插到目标位置的前一个块后面，一次可以连续插入多张表和段落。
3. **已有块只改名、只移动。** 图片或留白上方的名称段落用 `block_replace` 单块改名，保留原有加粗；位置不对时用 `block_move_after` 移动，名称段落连同它下面的图片或空白留位一起移。同一个名称段落既要移动又要改名时，先移动、后改名。
4. **只删除已被取代的文字块。** `block_delete` 只用于内容已经写进新表的列表项和说明段落；删除前确认该块里没有图片、附件、画板，也没有子块。
5. **含资源块的区间不整段替换、不整段删除。** 区间替换会删掉区间内的原块，再按 `--content` 新建；即使把原 token 写回去，得到的也是复制品，不是原块。区间里只要有图片、附件、画板或填过的表格，就改用上面的单块操作。
6. **每节做完重新读取。** 核对本节图片、附件、画板的 token 一个不多、一个不少，新增表格数与计划一致，再做下一节。

每次写入都检查返回的 `result` 为 `success` 且 `warnings` 为空；不满足就停下来读取现状，不接着执行后面的步骤。

```bash
# 改名：只替换名称段落本身
lark-cli docs +update --doc "xx" --command block_replace --block-id blkCaption --content '<p><b>步骤 2｜接线照片：</b></p>'

# 移动：名称段落和它下面的留位一起移到锚点后面
lark-cli docs +update --doc "xx" --command block_move_after --block-id blkAnchor --src-block-ids blkCaption,blkBlank1,blkBlank2

# 删除：一次传多个不相邻的块
lark-cli docs +update --doc "xx" --command block_delete --block-id blkItem1,blkItem2,blkPara
```

## 改写后比对

全部改完再读一次全文，与改写前保存的文件比较：

- 图片、附件、画板的 token 一个不多、一个不少，先后顺序除计划内的移动外不变；
- 没动的部分逐块一致；
- 没有 ID 相同而内容不同的块；
- 消失的块都在计划删除或改名的清单里。

有一项不符就先查清并修复，再报告完成。

## 块 ID 与批量操作

update 参考按“每次写入后 ID 都可能变化”处理。下面是 2026-11 在一篇文档上连续几十次写入的实测规律，重排一节时可以据此少读几次；接口更新后先在一节上验证，再沿用。

- 被 `block_replace` 的块换成新 ID；没动的块 ID 不变，被 `block_move_after` 移动的段落 ID 也不变。同一节内可以用同一次读取的 ID 连续执行多步；要再操作刚替换过的块，先重新读取。图片等资源块的移动没有实测，移动后以 token 核对为准。
- 锚点：`block_insert_after` 用过标题、段落、表格和列表项，`block_move_after` 用过表格。
- `<ol>`、`<ul>` 里的每个 `<li>` 是独立的块，可以单独删除，也可以作插入的锚点；列表项删除后，原先插在它后面的段落和表格是普通的顶层块。
- `block_delete --block-id` 可以用逗号传多个 ID，一次删除不相邻的块；CLI 帮助里也有这项说明。
