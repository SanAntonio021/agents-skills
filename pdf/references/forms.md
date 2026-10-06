# PDF 表单填写与检查

## 识别与保护

先检查 `PdfReader(...).get_fields()`、目录 `/AcroForm` 和各页 `/Annots` 中的 `/Widget`，同时查看页面。字段树为空不能单独证明没有表单：页面可能保留孤立 Widget。只有画出来的方框、扫描表格或已扁平化表格，交给 [精确编辑](precise-editing.md) 或 [OCR](ocr-workflow.md)。

- 读取完整字段名、`/FT`、`/Ff`、当前 `/V`、`/Opt`、`/Parent`、`/Kids`、`/DA` 与 `/AP`。字段属性可能继承自父节点；同名的多个 Widget 可以属于同一个字段。
- 复选框和单选按钮使用 `/AP/N` 的真实导出状态名，不假定都是 `/Yes`；取消勾选用 `/Off`。单选按钮组只选一个有效状态。下拉和列表按 `/Opt` 核对导出值与显示标签，多选要检查对应标志及索引。
- 缺少用户所指字段、同名但属于不同字段对象、只读字段或结构有歧义时，不盲写或把部分成果报告为完成。需要用户补充的信息一次说明；已确定的独立工作可以继续。
- `/XFA` 动态表单不是普通 AcroForm。没有受支持的填写方法时说明边界，不删除 XFA 后假称填写成功。
- 保留原 PDF、已有值和用户改动。检查 `/Sig`、`/ByteRange` 与签名限制；签名可能因改写失效。未明确授权改动已签文件时先说明这一具体后果并确认；不把图片签名当成数字签名，不替用户签署。

## 填写交互稿

从原稿克隆整个文档，保留页面、表单树和资源；不要仅复制页面再重建表单。以下使用现有 pypdf，无需新维护脚本：

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader(source)
writer = PdfWriter()
writer.clone_document_from_reader(reader)

# 先完成 Widget、父子关系与字段树检查，确认缺失字段后才修复。
# writer.reattach_fields() 只考虑用于已确认全部为独立孤立字段的结构；
# 混有合法按钮组时，它可能把组内 Widget 重复挂到根字段，不能全量调用。
# 对已确认的单个孤立字段，在同一 Writer 中定向补回其字段引用。
fields = writer.get_fields() or {}
unknown = set(values) - set(fields)
if unknown:
    raise ValueError(f"找不到字段: {sorted(unknown)}")
writer.update_page_form_field_values(None, values, auto_regenerate=False)
# 按下文检查/修正按钮状态，然后写到新路径。
writer.write(interactive_output)
```

只传本次指定值；未指定字段维持原值和外观。`auto_regenerate=False` 用于生成可显示的外观，不依赖查看器打开后重建。不能仅设置 `/NeedAppearances` 就交付。

### 按钮状态

检查按钮组的规范 `/V` 和每个 Widget 的 `/AS`：规范值为 PDF NameObject，所选状态必须存在于相应 Widget 的 `/AP/N`。其他 Widget 使用 `/Off`，已有正确外观流继续保留。

pypdf 6.10.0 的单选按钮更新可能在组父节点写字符串 `/V`，并在子 Widget 写各自 `/V`。写出前将组值规范为 `NameObject('/真实导出值')`，移除组子 Widget 的局部 `/V`，按各自 `/AP/N` 设置 `/AS`，防止局部值与组值冲突。完整字段名需沿父树计算，不用页面标签替代。对这种组结构可用：

```python
from pypdf.generic import NameObject

def normalize_radio(group, export_value):
    chosen = NameObject(export_value)  # 如 '/Safe'；先确认有效且属于此组
    group[NameObject('/V')] = chosen
    for ref in group.get('/Kids', []):
        widget = ref.get_object()
        if widget.get('/Subtype') != '/Widget':
            raise ValueError('需检查嵌套的按钮组，不能按直接子 Widget 处理')
        widget.pop(NameObject('/V'), None)
        appearance = widget.get('/AP', {}).get('/N')
        if appearance is None:
            raise ValueError('按钮缺少正常外观，需要先检查或重建')
        states = appearance.get_object()
        widget[NameObject('/AS')] = chosen if chosen in states else NameObject('/Off')
```

这个片段适用于已核实的直接子 Widget 结构。无父节点的复选框在自身保留规范 `/V` 和一致的 `/AS`；推送按钮不要当作复选框处理。

### 中文与字体

字段值正确不代表文字显示正确。先复用表单已有的、覆盖所填字符的字体资源；检查字段及父节点的 `/DA`、`/AcroForm/DR/Font` 和外观流 `/AP/N/Resources/Font`。Helvetica 等西文字体不能直接承担中文。

没有可用字体时，在副本给表单默认资源加入覆盖中文的 Type0 字体，并让相关文本字段 `/DA` 指向它，再生成外观。字体资源跨文档加入时用 `font_ref.clone(writer)`，不直接引用其他 Reader 的对象。只改需要中文的字段，不统一改写所有字段字体。

现有 ReportLab 可创建 `STSong-Light`、`/UniGB-UCS2-H` 字体资源作为本机可用的备用方法：注册 `UnicodeCIDFont('STSong-Light')`，在内存临时页使用该字体，将生成的 Type0 字体克隆至表单 `/DR/Font`（如 `/FChinese`），相关字段 `/DA` 设为 `/FChinese 13 Tf 0 g`，再运行 pypdf 更新。字号按原框尺寸调整，不固定用 13。这个字体未嵌入，需查看器支持或替代字体；不能声称跨查看器可移植。

若用户要求指定查看器或跨设备可靠显示，应使用允许嵌入且覆盖字符的字体并检查 `/FontDescriptor` 中的 `/FontFile2` 或 `/FontFile3`，在目标查看器验证。本机将 PyMuPDF 生成的 msyh.ttc、simsun.ttc 嵌入 Identity-H 字体克隆至 pypdf 6.10.0 后，重建外观均报编码错误；这个组合尚不可用，不以字体已嵌入代替填写成功。只有当前本机渲染证据时明确此边界，不把转成图片当作保留交互表单的解决办法。

核对换行、字号、裁切、滚动区域和新增汉字。至少检查首次填写和再次改值后的显示，确认仍可编辑；中文多行字段不能只验第一行。

## 用户要求静态版时

先生成并核验交互稿，再把 Widget 外观烘焙到页面。复用现有 PyMuPDF，先确认实际版本有 `Document.bake`：

```python
import pymupdf

with pymupdf.open(verified_interactive_output) as doc:
    doc.bake(annots=False, widgets=True)
    doc.save(flat_output, garbage=4, deflate=True)
```

`annots=False` 保留原非表单批注。此方法保留文字和矢量，不要求整页栅格化。转换后必须重新检查，不能仅凭 API 成功认定扁平化正确；若当前版本不支持，选择经验证的其他方法，不默默改变输出性质。

本机 pypdf 6.10.0 的 `update_page_form_field_values(..., flatten=True)` 加删除 Widget/AcroForm，曾因同名单选组的页面 XObject 重名丢失选中外观。不要未经外观对照直接使用这个捷径。保留所有未指定字段的已有内容；不能仅将本次 `values` 覆盖到页面后删除其他字段。

## 写后核验与交付

重开文件，并核对源文件哈希未变、页数及非目标内容：

1. **交互稿**：指定字段 `/V` 与预期一致，未指定字段不变；逐页 Widget 通过父树继承得到的有效 `/V` 与字段树一致。按钮 `/AS`、导出状态及 `/AP/N` 一致，文本外观存在且非空，原有字段树和可编辑 Widget 保留。`/AP/N` 是流还是状态字典要分别处理。
2. **静态稿**：字段树、`/AcroForm` 与所有页的 `/Widget` 均移除；非表单批注维持原状。核对填入值和原有值仍在页面显示。文本或矢量内容若本来可保留，不整页改成图片。
3. **页面外观**：用可用 Poppler 或 MuPDF 渲染受影响页面，对照填写位置的中文、勾选和单选、字号、裁切、底色、边框及多页内容。pypdf 重建文本外观可能丢掉原底色/边框；修正时保留必要的背景绘制，不能把旧文本一起叠回去。静态稿对照已核验交互稿，尤其检查选中标记。路径定位见 [Windows 工具](windows-tools.md)。

字段读回、页面渲染、再次编辑是不同证据。针对用户要求交付交互稿或静态稿；未完成的目标查看器验证、动态表单或签名限制如实说明，不以一句“校验通过”掩盖。

## 来源与验证边界

表单识别、文档克隆、默认保留交互、孤立字段修复条件及写后检查吸收自本机 OpenAI `pdf` 插件的 `skills/pdf/SKILL.md` 表单部分。插件快照版本 `26.921.10847`，作者 OpenAI，`.codex-plugin/plugin.json` 声明 MIT；源入口 SHA-256：`a13d2f878d6f79df9ebba91901c0b09bf799e83973b47ebba2104e385b6e4ede`。这是已安装快照来源，没有据此虚构 Git 仓库或接受提交。未引入 Anthropic 的 Proprietary 表单资料，也未继承官方的操作标记、固定输出目录或交付格式要求。

2026-10-06 隔离样本实测 pypdf 6.10.0、PyMuPDF 1.27.1 和本机 Poppler：中文多行、复选框、两 Widget 单选组、两页表单及二次填写；PyMuPDF `bake` 后按钮区域与交互稿像素一致，未指定值保留，字段移除且页面仍为文字/矢量。上述方法以本机兼容结果为依据，不能代替用户实际 PDF 或指定查看器的检查。
