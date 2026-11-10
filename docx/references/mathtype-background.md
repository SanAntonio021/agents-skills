# MathType 后台转换、格式与编号

用户要求 MathType 公式、统一已有 MathType 的字体，或按 MathType 模板调整编号时读取本参考。
Word 原生公式 OMML、MathType 可编辑 OLE 对象和公式图片是不同格式；先盘点输入，再按用户指定目标处理。
本方法验证于 Windows、经典 MathType 7.8 及其 64 位 SDK/OLE 服务。其他版本、网页加载项和未安装 SDK 的环境需先核实能力，不把 Word 功能区出现 MathType 当作 API 可用的证据。

## 输入、范围与后台能力

1. 从当前 Word 及指定模板盘点所有公式：正文、表格、页眉页脚、脚注尾注及文本框；区分 OMML、`Equation.DSMT4`、旧 Equation 对象和纯图片。避免重复统计 `AlternateContent` 的备用表示。不支持的故事位置或对象类型须列明，不能只处理正文后声称全部完成。
2. 记录输入和模板哈希、公式顺序及内联/独立位置、原编号、书签/引用、字体和尺寸。用户只确认公式格式时，保留正文、页面、段落间距及图题；使用新输出，不覆盖用户正在编辑的文件。
3. 定位实际 MathType 安装目录、注册的 `Equation.DSMT4` 服务和匹配 Python 位数的 `MT6.dll`。64 位 DLL 通常位于 `<mathtype-root>/System/64/MT6.dll`；不要硬编码某台电脑的安装盘或复制专有二进制到技能中。缺失依赖时说明缺项，不自行安装或改 COM 注册。
4. 优先使用 DLL 转换与独立 OLE 对象。无需启动 Word、运行加载项宏、调用 OLE `DoVerb` 或激活公式编辑窗口。用户限定后台时，这个限制同样适用于诊断和核验；隔离 Word 不可用时继续文件及对象检查，原生刷新保留为未核验。

Word 的隔离与身份检查沿用 [Office 安全边界](office-security-boundary.md)，不在本流程重写或放宽。只关闭本任务创建的独立公式对象并释放 SDK 连接，不连接、保存或结束用户的 Office/MathType 文档。

## 先验证一个代表性公式

选包含分式或上下标的公式，在任务过程目录完成“输入 → 原生对象保存 → 重新加载 → 数学内容回读 → 预览”后再扩展批次。根据任务还应覆盖内联公式、复杂独立公式及编号引用。API 非零状态、对象保存失败或结构改变时停止该公式的写入，保留其他已核实成果。

已有 OMML 可用已安装 Office 的 `OMML2MML.XSL` 转为结构化 MathML。保留 `mfrac`、上下标、矩阵、分段及定界符语义；不能把整条公式塞进一个普通文本节点。纯图片没有可恢复公式结构时单独报告，不把改扩展名或添加 ProgID 当作转换。

### 独立 OLE 导入与持久化

下列是已验证的调用要点，不是可直接批处理任意文档的完整脚本。按实际 SDK 核对签名并设置 `ctypes.argtypes/restype`；指针使用 `c_void_p`，Windows `long` 使用 `c_long`，不能因 Python 为 64 位而把 `long` 改成 64 位。

| 函数 | 已验证的参数类型与用途 |
|---|---|
| `MTAPIConnect(short, short)` / `MTAPIDisconnect()` | 建立/释放 SDK 连接；已验证的连接参数示例为 `(0, 15)`。 |
| `MTSetMTPrefs(short, char*, short)` | `(1, eqp_bytes, -1)`：把指定偏好用于下一个新公式，不保存为用户的全局默认。 |
| `MTSetEqnFromLangStr(void*, short, void*, long)` | 语言 `2` 导入 MathML：UTF-16LE 缓冲区，以 UTF-16 代码单元数传长度。 |
| `MTSetEqnFromLangBytes(void*, short, void*, long)` | 语言 `3` 导入 MTEF 原生二进制，长度为字节数。 |
| `MTGetLangStrFromEqn(void*, short, void*, long*)` | 语言 `2` 回读 MathML；先查询大小，再分配字节缓冲区。已验证回读为 UTF-8 XML，不照搬输入的 UTF-16 解码。 |
| `MTGetLangBytesFromEqn(void*, short, void*, long*)` | 语言 `3` 导出原生 MTEF，采用同样的两次缓冲区调用。 |
| `MTCloseOleObject(long, void*)` | `(0, owned_pointer)` 结束本任务的对象操作；在 `finally` 中处理。 |

返回值按对应函数检查；上述已验证操作以 `0` 表示成功。字符串长度不要用含非 BMP 字符时的 Python `len(text)` 代替 UTF-16 单元数：

```python
encoded = mathml.encode("utf-16-le")
buffer = ctypes.create_string_buffer(encoded + b"\0\0")
status = sdk.MTSetEqnFromLangStr(pointer, 2, buffer, len(encoded) // 2)
```

使用 `comtypes.client.CreateObject('Equation.DSMT4', interface=IDispatch)` 创建独立对象；取得其 `IDispatch` 指针，经 `pythoncom.ObjectFromAddress(pointer, pythoncom.IID_IDispatch)` 查询 `IID_IPersistStorage`。新建复合存储后依次执行：

```text
StgCreateDocfile(new_path, STGM_CREATE | STGM_READWRITE | STGM_SHARE_EXCLUSIVE, 0)
IPersistStorage.InitNew(storage)
MathType 导入 MathML 或 MTEF；回读并比较
IPersistStorage.Save(storage, True)
IPersistStorage.SaveCompleted(storage)
storage.Commit(0)
关闭本任务对象，释放 storage / persist / dispatch 引用
```

重新创建独立对象，以 `StgOpenStorage(path, None, STGM_SHARE_EXCLUSIVE)` 和 `IPersistStorage.Load(storage)` 加载保存的文件，再回读 MathML。导入时的内存回读不能代替保存后重载。确认复合文件确有 `Equation Native` 流，根 CLSID 与经典 MathType 对象相符（已验证值 `0002CE03-0000-0000-C000-000000000046`）。已验证文件的原生流有 28 字节头部；读取前检查头部、长度和 MTEF 版本，不对其他 Equation 格式直接截去 28 字节。

将真实复合存储嵌入 `word/embeddings/`，建立 OLE 关系与 `o:OLEObject ProgID="Equation.DSMT4"`，同时提供预览图及其关系。用唯一的关系/形状 ID，维护 `[Content_Types].xml`。公式对象与预览是两个部分，PNG 只用于显示，不能替代原生可编辑数据。

### 现有 MathType 的字体转换

从模板对象及其渲染/MathType 偏好中核实正文字体、希腊字母与符号字体、主字号、一级和二级上下标比例。修改 `.eqp` 中对应样式和尺寸，保留需要的 Symbol/MT Extra；不要把一个模板的 Cambria Math、16 pt、70%/50% 固定为所有文档的默认值。沿用安装目录中的偏好文件时只读原件，另存任务副本。

现有 MTEF 可经 `MTXFormReset()`、`MTXFormSetPrefs(3, eqp_bytes)` 和文件输出完成原生重排：

```text
MTXFormEqn(-3, 4, mtef_buffer, byte_length, -4, 6, NULL, 0, wmf_path_bytes, NULL)
MTGetLastDimension(1) / 32    # 宽度，pt
MTGetLastDimension(2) / 32    # 高度，pt
MTGetLastDimension(3) / 32    # 基线参数，pt
```

`wmf_path_bytes` 是 Windows 当前代码页可表示的绝对路径；不能表示时使用任务专属的兼容暂存路径，再将产物复制回任务目录，不改系统代码页。`MTGetLastDimension` 的签名为 `(short) -> long`；转换和偏好函数返回 `long`。尺寸应在下一次转换前立即读取。

重排后的原生 MTEF 可以从 MathType 生成的 WMF `AppsMFCC` 注释中取得，再经 `MTSetEqnFromLangBytes(..., 3, ...)` 保存为新对象。已验证 MathType 7.8 输出中，`META_ESCAPE` (`0x0626`) 注释以 `AppsMFCC` 开头，包含 `Design Science, Inc.\0` 标识；该标识后的数据为候选载荷，注释数据偏移 10 的 DWORD 给出载荷长度。逐记录检查边界、声明长度和 MTEF 版本；另一个同类注释可能是 MathML，不能把 XML 当 MTEF。带 placeable 头的样例从字节 40 开始遍历记录，其他 WMF 头必须另行解析，不固定套偏移。

在已验证环境中，将 MTEF 转 WMF 的纯 DLL 阶段与导入 `pythoncom/comtypes` 的 OLE 阶段分开进程执行更可靠。曾出现混用时首次转换返回 `mtMT_CANT_RUN`，以及直接请求原生内存输出时访问异常；遇到这些情况保留错误，改用已验证的文件输出，不循环重试同一崩溃调用。`MTXFormEqn` 的 TEXT 输入不能直接用来导入 MathML，可能将 XML 本身排成文字；MathML 导入走独立 OLE 的语言接口。

## 预览尺寸、基线与段落

预览必须来自最终保存的原生数据。核对宽高比、分式/求和边界及内联基线，并同步 OLE 的 VML 形状宽高、`dxaOrig/dyaOrig` 和相应预览。基线参数的方向须用代表性内联公式实际检查，不能仅凭正负号推定。

MathType WMF 在部分兼容渲染器或 PIL WMF 读取器中会出现字形变形或裁切。Windows 上可用 `System.Drawing.Imaging.Metafile` 和 GDI+，按原生点尺寸在明确分辨率（例如 600 dpi）画入 PNG，嵌入同一宽高比的预览；分别释放图形与位图对象。不要修整可见图片后让它与实际 OLE 公式不一致。Word 页面核验继续遵循技能现有渲染规范。

独立公式先复用模板的对齐方式。需要同时居中公式、靠右编号且垂直对齐时，可使用等宽左右侧栏的无边框三列表格；总宽度取当前页可用文字宽度，编号栏按实际编号宽度确定，公式位于中栏，单元格垂直居中。保留原公式段前段后和正文间距，不能把某次使用的栏宽推广为默认。表格等容器变化属于公式布局修改，应核对相邻段落与分页，不更换页面或正文样式。

异常空白或过高公式先检查 MathML/MTEF 和渲染。`U+200B` 等字符可能是导入占位，也可能有意保留；仅在具体节点已证明造成版式伪影、删除不改变数学结构时局部处理。按 [公式空白字符诊断](native-equations.md#diagnose-boxes-and-invisible-spacing-characters) 保留前后对照，不批量删除全部不可见字符。

## MathType 编号与引用

读取模板的实际字段和文档 MathType 属性，不仅看显示出的括号。简单连续编号的已验证结构是外层 `MACROBUTTON MTPlaceRef` 的指令部分中包含隐藏序列递增与当前序列值：

```text
{ MACROBUTTON MTPlaceRef { SEQ MTEqn \h }({ SEQ MTEqn \c \* ARABIC }) }
```

这表示复杂字段的嵌套关系，不能作为一段普通文字插入。构造合法的 `begin`、`instrText`、`separate`、`end`；括号属于外层指令的普通文本段，数字来自内部 `SEQ`。需要缓存外层结果时保存完整 `(n)`，同时保留内层数字缓存。正文用到的数字书签包住内层数字字段，保留原书签名称/ID 和 `REF` 目标，不能只包住可能被外层刷新重写的显示缓存。

仅对已经打算编号的独立公式建立此结构；内联和原本无编号公式保持无编号。保留原顺序、起点、章号、附录、重置和多段规则；上例不能代替复杂编号设计。半角/全角括号、编号字体、字号及位置依实际模板与授权范围决定。

如果模板使用文档属性保存编号格式，一并保留或更新对应 MathType 属性。例如已验证的简单连续编号使用自定义属性 `MTEquationNumber2 = (#E1)`；不能只改外观而让后续 MathType 更新又恢复旧格式，也不能把这个值覆盖到其他编号方案。

[通用编号工具](numbering-references.md)当前不支持这种 MathType 嵌套字段；应报告不支持的原生刷新，不能删除嵌套结构或改成手写数字以取得“通过”。后台 Word 可安全隔离且有相应专用核验时，另行检查实际编号刷新与保存重开；普通 SDK 对象转换不证明 Word 字段已刷新。不得为此放宽 Word 隔离检查或在后台限定下转向前台宏、键盘操作。

LibreOffice 可能把该宏字段显示为重复数字或空括号。可在纯诊断副本中用已核对的 `(n)` 缓存替代编号字段检查几何布局；保留正式候选中的真实字段。诊断副本、它的 PDF 与原文档分别记录路径/哈希，明确其用途仅为版式，不能作为正式 Word 编号刷新证据或交付成正式源文件。

## 保存后的核验与交付

内容、对象、版式和字段刷新分别判定，使用现有任务核验记录，不为每一步新增报告：

- 对每个目标公式重载保存的 MathType 对象并回读结构化 MathML。比较运算符、数值、变量、分式分子/分母、上下标位置、矩阵和定界符；只比较去空白后的文字不足以证明等价。处理 `mfenced` 时把 `open/close/separators` 计入比较，不把语义节点或所有空白一概忽略。
- 盘点对象数、所有故事位置、OLE 关系/嵌入文件及预览；PNG 可读与 ProgID 正确不足以证明可编辑。检查每个保存对象的原生流和重载结果。
- 用公式占位符比较原稿与候选的正文骨架，另核对明确批准的删段或布局变更。检查样式、页面、图题、页眉页脚、书签和引用，解释每个变化的包部件。运行包完整性与适用的 DOCX schema 检查。
- 核对每条编号的缓存、字段嵌套、序列/格式属性、书签与引用目标，并检查代表性首、中、末编号及复杂公式页面。结构检查与编号显示缓存正确不等于 Word 原生刷新通过。
- 预览字体、尺寸、上下标、符号、基线、裁切和对齐符合模板后，将正式文件复制到约定位置并核对哈希；原稿、模板和先前交付保留。只在 SDK 对象、兼容版式或用户确认范围内作相应结论，未完成的 Word 原生分页/字段刷新保持未核验。

API、WMF 载荷与复合存储的说明来自本地安装服务的实际调用验证；不附带专有 DLL、加载项源码或用户文档。跨版本使用时先重做代表性公式的保存重载和尺寸检查，再开展批量转换。
