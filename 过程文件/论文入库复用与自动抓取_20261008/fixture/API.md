# Zotero 隔离试跑接口

此目录是一次性模拟环境，与真实 Zotero 的用户目录、资料库、附件和设置没有连接。论文、DOI、期刊和 URL 均为模拟身份。服务没有任何 PDF 网络抓取逻辑；Sci-Hub 抓取与弹窗只记录为日志事件。

## 启动、查看和停止

Windows PowerShell：

```powershell
& 'D:/Program Files/nodejs/node.exe' 'D:/BaiduSyncdisk/.agents/skills/过程文件/论文入库复用与自动抓取_20261008/fixture/server.mjs'
```

默认绑定 `127.0.0.1`，端口为 `0`，由系统分配。首行 JSON 提供 `url`、`pid` 和 `processInstance`。也可附加 `--port 具体端口`。主 Agent 负责启动和停止；本文件不会启动服务。普通运行保留既有案例状态，第二次启动会重新创建 JS 上下文。

前台启动时用 Ctrl+C 停止。后台启动由主 Agent 按首行 PID 停止进程；创建后台进程须使用隐藏窗口。服务没有远程关闭接口。

以下两个命令立即退出，不监听端口：

```powershell
& 'D:/Program Files/nodejs/node.exe' 'D:/BaiduSyncdisk/.agents/skills/过程文件/论文入库复用与自动抓取_20261008/fixture/server.mjs' --init
& 'D:/Program Files/nodejs/node.exe' 'D:/BaiduSyncdisk/.agents/skills/过程文件/论文入库复用与自动抓取_20261008/fixture/server.mjs' --selfcheck
```

`--init` 仅补齐缺失的输入和案例，不覆盖已存在的状态。`--selfcheck` 检查输入身份、PDF 起止标记、案例结构、父子引用、附件 SHA-256 和日志 JSON；该检查不执行被测代码，不代表技能行为通过。

## 存储

- `inputs/simulated_target.pdf`：一页小型模拟论文 PDF。
- `inputs/simulated_target.bib`：同一模拟论文的 BibTeX。
- `inputs/publication_index.json`：模拟题录、DOI、文件路径和 PDF 哈希。
- `cases/<案例名>/state.json`：该案例的持久条目、分类、资料库、设置和控制值。
- `cases/<案例名>/operations.jsonl`：读取查询、原生 JS、设置、观察器、保存、导入、断开和重启日志。
- `cases/<案例名>/storage/<附件 ID>/`：真实复制的模拟附件；哈希和大小同时保存在 `state.json` 与导入日志中。

论文身份：`Zotero Fixture Study: Spectral Windows in a Simulated Link`，DOI `10.0000/zotero-fixture.target-001`，`Fixture Journal (Simulated)`，2026。此 DOI 只用于本地测试，不需要联网解析。

## 案例

download、search 各有以下 8 个独立案例。完整名称为 `download__后缀` 或 `search__后缀`，两个执行者的数据互不共享。

| 后缀 | 初始事实 |
|---|---|
| `existing_pdf_notes_collections` | 父条目 id=1；PDF id=2；笔记 id=3；PDF 批注 id=4；分类 20、21；自动设置 true。 |
| `local_pdf_auto_on` | 输入目录有 PDF；资料库无目标父条目或附件；自动设置 true。 |
| `local_pdf_auto_off` | 输入目录有 PDF；资料库无目标父条目或附件；自动设置 false。 |
| `doi_generic_search_empty_title` | 父条目 id=1 保留正确题名、DOI 和 PDF id=2；此案例的 DOI 通用搜索为空、题名可命中；DOI 精确查询正常。案例 ID 沿用历史名称。 |
| `timeout_continues` | 无目标父条目；saveTx 在提交前延迟 1400 ms；HTTP 客户端断开不会取消原生 JS。 |
| `first_attachment_failure` | 无目标父条目；下一次附件导入抛出一次模拟异常；该失败控制随发生消费。 |
| `manual_setting_change` | 无目标父条目；saveTx 提交前延迟 1400 ms；可同时使用用户设置注入接口。 |
| `restart_saved_partial` | 已保存父条目 id=1，无 PDF；自动设置 false；模拟前一会话中断并重启后，任务、观察器和 JS 全局变量均为空。 |

另有检索侧独立案例 `search__local_material_handoff` 和 `search__metadata_only`：均无目标条目，自动设置 true；前者描述本地材料路径，后者描述题录来源。各案例的完整事实可通过接口读取。

## HTTP 接口

`BASE` 是启动输出的回环 URL。所有 POST 使用 JSON。读取接口也写入相应案例的日志。

| 方法与路径 | 内容 |
|---|---|
| `GET /health` | 服务 PID、进程 UUID、启动时间、隔离目录与设置键。 |
| `GET /cases` | 全部案例名称、执行者和初始事实。 |
| `GET /cases/<案例>` | 案例事实、当前控制值、进程身份、模拟题录与本地材料路径。 |
| `GET /cases/<案例>/process` | 当前进程和该案例上下文 UUID、重启次数、运行任务数。 |
| `GET /cases/<案例>/libraries` | 资料库。 |
| `GET /cases/<案例>/collections` | 分类。 |
| `GET /cases/<案例>/items` | 全部条目，包括附件、笔记和批注。 |
| `GET /cases/<案例>/items?q=文本` | 通用包含查询；包含字段、作者、key 和笔记，默认索引 DOI；两个 `doi_generic_search_empty_title` 案例不索引 DOI。`search=` 是别名。 |
| `GET /cases/<案例>/items?doi=DOI` | DOI 精确查询。还支持 `title`、`itemType`、`libraryID`、`topLevel=true`。 |
| `GET /cases/<案例>/items/<ID>` | 一条完整条目。 |
| `GET /cases/<案例>/items/<ID>/attachments` | 该条目的附件。对应 `/notes`、`/annotations` 返回对应子条目。 |
| `GET /cases/<案例>/attachments/<ID>/file` | 返回该模拟附件的文件字节，日志记录实际 SHA-256。 |
| `GET /cases/<案例>/settings` | 当前设置。 |
| `GET /cases/<案例>/settings/<键>` | 指定键的值和是否存在。 |
| `GET /cases/<案例>/search?q=文本` | 查询本地模拟论文索引；返回题录和本地路径；不操作资料库。 |
| `GET /cases/<案例>/logs` | 完整操作日志。 |
| `POST /cases/<案例>/js` | 执行原生 JS，参数见下文。 |
| `GET /cases/<案例>/tasks` | 当前上下文已启动的任务状态。 |
| `GET /cases/<案例>/tasks/<任务 UUID>` | 任务状态和已完成结果。 |
| `POST /cases/<案例>/inject/manual-setting` | `{"key":"设置键","value":true}`；key 缺省为自动设置键；以用户操作来源写入，触发已注册观察器。 |
| `POST /cases/<案例>/inject/attachment-failure` | `{}`；使下一次附件导入失败一次。 |
| `POST /cases/<案例>/restart` | `{}`；重建此案例的 JS 上下文，保留条目、附件、分类、设置和日志。 |

默认自动设置键为 `zoteroscihub.automatic_pdf_download`。服务不查重、不改自动设置、不替调用者套保护流程，也不把不同 JS 请求排成队。`Zotero.Scihub = {installed: true}` 仅表示插件存在。

新建普通父条目在 `saveTx()` 提交时，若当时此设置严格为 `true`，会写一次 `scihub.simulated.fetch_popup` 日志。更新既有条目、保存笔记、导入附件不触发该事件。日志内的 `networkRequestMade` 为 `false`。

## 原生 JS

请求体：

```json
{"code":"return Zotero.Libraries.getAll();","mode":"async","waitMs":30000}
```

默认 `mode="async"` 把代码作为 async 函数体执行，可用 `await` 和 `return`。请求之间需要保留的变量放在 `globalThis` 或 `Zotero` 上；函数局部变量随调用结束。`mode="script"` 按脚本原样运行，顶层变量位于该案例持久上下文，异步代码可用 async IIFE。每案例独立上下文支持 `Zotero.__paperDownloadBatches` 等调用者自行设置的属性；fixture 不主动创建或管理它们。

`waitMs` 只控制 HTTP 响应等待时长，范围 0–60000 ms，默认 30000 ms。超时返回 HTTP 202 和 `status="running"`；请求代码继续执行。客户端自行超时或中止连接同样不取消 JS，可读取 `/tasks`、日志和保存后的条目。任务完成返回 HTTP 200，状态为 `completed` 或 `failed`；JS 异常放在 `error` 字段。

模拟重启丢失任务注册表、JS 全局变量和观察器，并终止旧上下文的延迟与计时器。旧任务 ID 在新上下文返回 404。日志仍保留已经发生的动作；保存后的条目和附件不回滚。重启只影响选定案例。

运行环境提供 `Zotero`、日志化 `console`、`setTimeout`、`clearTimeout` 和标准 JS 内建对象；没有暴露 `fetch`、`require`、`process` 或外部抓取接口。此 VM 是测试执行上下文，不是用于执行敌对代码的安全沙箱。

### 支持的 Zotero API

- `Zotero.Prefs.get(key)`、`set(key,value)`、`registerObserver(key,callback)`、`unregisterObserver(token)`。注册返回 token；值变化时函数回调收到新值，也支持带 `observe()` 的对象。
- `new Zotero.Item(itemType)`；`setField/getField`、`setCreators/getCreators`、`setNote/getNote`、`saveTx()`、`addToCollection()`、`getCollections()`、`getAttachments()`、`getNotes()`、`getAnnotations()`、`getFilePathAsync()`、`toJSON()`；`isRegularItem/isAttachment/isNote/isAnnotation`。
- Item 属性：`id`、`key`、`libraryID`、`itemType`、`parentID`、`parentItemID`、`parentKey`、`attachmentPath`、`attachmentContentType`、`attachmentLinkMode` 及已有批注字段。
- `Zotero.Items.getAsync(id或ids)`、`get(id或ids)`、`getAll(libraryID=1,onlyTopLevel=false,includeDeleted=false,asIDs=false)`、`getByLibraryAndKeyAsync(libraryID,key)`。
- `Zotero.Attachments.importFromFile({file,parentItemID,libraryID,title,contentType})`：实际复制输入文件并返回附件 Item；file 是隔离目录内的绝对路径或相对 fixture 根目录的路径；也接受 `{path:字符串}`；不允许读取隔离目录外文件。
- `Zotero.Promise.delay(ms)`。
- `Zotero.Libraries.userLibraryID/getAll/get`；`Zotero.Collections.get/getAsync/getByLibrary`。
- `new Zotero.Search()`，`libraryID`、`addCondition(field,operator,value)` 和 `search()`；支持 `is`、`isNot`、`contains`，字段包括 DOI、title、itemType、`quicksearch-everything`；返回 ID 数组。两个 `doi_generic_search_empty_title` 案例的 quicksearch 不索引 DOI，但 DOI 字段精确条件正常。当前模拟条件按 AND 执行，`joinMode` 只记录，不改变运算。
- `Zotero.debug()`、`Zotero.logError()`。

库 ID 是 1，分类 ID 是 20、21。模拟新增条目从 ID 100 起分配。未实现的 API 直接按 JS 缺失属性/函数表现，不转接真实 Zotero。

## 一次读取示例

只展示接口调用方法，不包含入库流程。将 `BASE` 替换成服务输出 URL：

```python
import json, urllib.request
BASE = "http://127.0.0.1:服务端口"
CASE = "download__local_pdf_auto_on"
url = f"{BASE}/cases/{CASE}/js"
data = json.dumps({"code": "return Zotero.Prefs.get('zoteroscihub.automatic_pdf_download');", "waitMs": 0}).encode()
request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(request, timeout=5) as response:
    print(response.status, response.read().decode())
```

请求返回的任务 UUID 可用于后续读取。无需登录或访问真实 Zotero。
