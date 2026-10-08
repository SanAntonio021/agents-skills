# Zotero 入库与附件复用

先读取当前安装的 Zotero 插件说明，用其 `status --json` 核对可用接口和实际资料库。库内检索、条目和附件读取使用本地 API；写入使用现有 Connector 或已配置后台桥接调用 Zotero 原生 API，不直接修改数据库或 storage 文件。

资料库标识须注明接口类型：REST 响应的 `library.id` 或 `/users/<id>` 中的 ID 是 Web user ID，群组 REST 标识也不能直接当成本地原生 `libraryID`。原生个人库使用当前 `Zotero.Libraries.userLibraryID`，其他库通过实际原生条目／资料库对象确认。未查询原生标识时保持未知，写入前再核实；不把 REST 标识直接传入原生查询或导入。

## 本地资料复用

按资料库、DOI 及题名作者核对已有条目和附件，再读本任务已知的索引、BibTeX 和 PDF。已有可读目标文件时直接复用；本地 PDF 已存在但库内缺父条目时，用核实的本地元数据创建一次，再复制导入该文件，不重新下载。纯本地整理或归类如实记录实际版本，不自动补当前卷期版。身份、版本依据不明时保留缺口，不凭文件名、日期或一次空查询作判断。

## 自动抓取与原操作检查

所有新增条目入口，包括 Connector、BibTeX/RIS 和仅元数据导入，均在第一条保存之前检查实际插件和新增事件处理。保存元数据也可能触发 PDF 抓取；已取得文件不意味着插件会等附件保存完再运行。

- 通过现有受支持接口查实际插件、自动开关和调用能力。读取开关不调用可能初始化默认值的下载函数。用户明确要求长期关闭时保留关闭，不从历史备份恢复开启；普通入库不调用手动全文抓取。
- 入口有可靠的单次抑制功能时优先使用。否则仅在已核实的原生设置接口内临时暂停相应自动开关，回读确认后再新增；开关未知、无法抑制或设置变化无法归属时暂停新增，继续独立读取和复用。不要用卸载插件或改插件代码解决。
- 临时变更和条目写入属于同一原生任务。监听开关变化，区分本次设置与外部修改；任一外部修改停止后续新增，保留用户当前设置。任务实际结束后在原生 `finally` 中恢复仍归本次所有的临时改动，再解除本次监听；客户端超时不能提前恢复。恢复结果与入库结果分别回读和报告。
- 写入前记录本次操作编号和 Zotero 进程身份（PID、启动时间）。同一 Zotero 进程内本流程只允许一个写入批次；按篇串行查重、保存并记录已返回的条目标识。不能逐项核实或跟踪的整批导入入口，不用于本流程的未知结果重试。
- 超时先查询同一操作及持久化条目、附件、实际文件；每轮状态检查连同等待最多 45 秒。仍在运行或无法确认终态时报告待续，不重新投递、不更换入口重放。`running` 标记不会因等待到期变为失败；暂时查不到条目不证明原操作已结束。
- 确认终态后重新查重：完成的结果复用，失败批次已保存的部分保留，只有确认缺少的部分才能用新操作编号续做。进程标记是易失线索；重启或状态丢失时先确认原进程已结束，再查持久化结果。状态丢失但原进程仍在时，不擅自清活动标记或重试。设置恢复依据不足则保留现状并报告待恢复，不据旧快照覆盖当前值。

### 原生批次示例

下例是嵌入现有原生调用的框架，不是新桥接或独立脚本。`operationId` 是调用前生成并保留的本次 UUID；`processIdentity` 来自已核实的当前进程身份。`automaticPrefKeys` 只接受现场核实的自动开关；空数组仅用于确认没有自动抓取处理器的环境。本机已观察的 Sci-Hub 开关示例是 `zoteroscihub.automatic_pdf_download`，不作为所有插件的固定配置。

`work` 每次新增父条目或附件前调用 `beforeWrite()`，重新核对该论文和已有附件；保存成功后才调用 `rememberItem(item)`。源 PDF 默认复制导入。示例依赖同步偏好通知及已有 `Zotero.Prefs` 接口；接口或变化归属不可靠时不能套用。捕获的状态只是执行线索，最终成功仍须通过下方持久化回读验收。

```javascript
async function runPaperImport(operationId, processIdentity, automaticPrefKeys, work) {
  if (!operationId || !processIdentity || !Array.isArray(automaticPrefKeys)
      || typeof work !== "function") throw new Error("invalid_import_context");
  const store = Zotero.__paperDownloadBatches ||= {
    processIdentity, active: null, jobs: Object.create(null)
  };
  if (store.processIdentity !== processIdentity) throw new Error("process_identity_mismatch");
  const copy = value => JSON.parse(JSON.stringify(value));
  if (store.jobs[operationId]) return copy(store.jobs[operationId]);
  if (store.active) throw new Error("another_import_is_running");
  const job = store.jobs[operationId] = {
    operationId, processIdentity, status: "running", startedAt: Date.now(),
    savedKeys: [], preferenceRecovery: [], error: null
  };
  store.active = operationId;
  const prefs = [];
  let terminal = "failed", stopReason = null;
  const stop = reason => { stopReason = reason; throw new Error(reason); };
  const beforeWrite = () => {
    for (const pref of prefs) {
      if (pref.externalChange || Zotero.Prefs.get(pref.key) !== false)
        stop("automatic_preference_changed");
    }
  };
  try {
    for (const key of new Set(automaticPrefKeys)) {
      const original = Zotero.Prefs.get(key);
      if (typeof original !== "boolean") stop("automatic_preference_unknown");
      const pref = { key, original, ownChange: false, externalChange: false,
        changed: false, observer: null };
      pref.observer = Zotero.Prefs.registerObserver(key, () => {
        if (!pref.ownChange) pref.externalChange = true;
      });
      prefs.push(pref);
      if (Zotero.Prefs.get(key) !== original) stop("automatic_preference_changed");
      if (original) {
        pref.changed = true;
        pref.ownChange = true;
        try { Zotero.Prefs.set(key, false); }
        finally { pref.ownChange = false; }
        if (Zotero.Prefs.get(key) !== false) stop("automatic_pause_not_confirmed");
      }
    }
    beforeWrite();
    await work({ beforeWrite, rememberItem: item => {
      if (item.key) job.savedKeys.push({ libraryID: item.libraryID, key: item.key });
    }});
    terminal = "completed";
  } catch (error) {
    job.error = stopReason || "native_write_failed";
  } finally {
    for (const pref of prefs.reverse()) {
      let recovery = "not_needed";
      try {
        if (pref.changed) {
          if (pref.externalChange) recovery = "preserved_user_change";
          else if (Zotero.Prefs.get(pref.key) !== false) recovery = "pending";
          else {
            pref.ownChange = true;
            try { Zotero.Prefs.set(pref.key, pref.original); }
            finally { pref.ownChange = false; }
            recovery = Zotero.Prefs.get(pref.key) === pref.original ? "restored" : "pending";
          }
        }
      } catch (error) { recovery = "pending"; }
      finally {
        try { Zotero.Prefs.unregisterObserver(pref.observer); }
        catch (error) { recovery = "pending"; }
      }
      job.preferenceRecovery.push({ key: pref.key, recovery });
    }
    job.status = terminal;
    job.finishedAt = Date.now();
    if (store.active === operationId) store.active = null;
  }
  return copy(job);
}
```

将实际按篇查重、保存和附件调用放入 `work`，通过同一现有桥接执行 `runPaperImport(...)`。调用方保留操作编号、进程身份和暂停前设置，不记录凭据。查询原操作只执行读取，例如：

```javascript
const job = Zotero.__paperDownloadBatches?.jobs["<同一本次UUID>"];
return job ? JSON.parse(JSON.stringify(job)) : null;
```

查询为 `null` 不等于失败；先按上面的进程和持久化规则判断。重启后内存状态不可恢复，不用自动清标记、重启用户应用或增加服务来制造终态。

## 已有条目补 PDF

- 根据 libraryID 和 item key 重新读取父条目，核对 DOI、题名及请求的目标版本；写入前再次检查附件，避免重复任务同时补同一文件。已有可读目标版本时按技能正文优先复用，不因下载时间或哈希不同重复入库。目标为当前正式版时，作者稿不能终止补齐；用户准确指定非正式版本时按该目标验收，不强制取得正式版。新文件补到同一父条目并回读，不直接覆盖旧文件。
- 本次已下载或已有本地且核验通过的 PDF，可在上述检查后通过 `Zotero.Attachments.importFromFile({file, parentItemID, contentType: "application/pdf"})` 存为受 Zotero 管理的附件。导入前关闭本次文件流和 PDF 解析器，尤其在移动导入前释放源文件读取句柄。用户原文件默认复制导入；本次自有临时下载才可使用 `moveFile: true`。复制导入则在成功回读后清理自有暂存，不清理用户原文件。
- 不存在条目时，用核实的元数据创建一次，保存 libraryID 和 key 后再补附件；不把查询不到等同于已确认没有重复项。查询失败应先解决或报告。
- 写入后按 item key 回读附件，检查 parentID、MIME、实际文件、PDF 可读性及哈希，确认请求版本确实存在。仅元数据或 HTML 快照不算 PDF 入库完成；目标为正式版时，其他版本仍待补。批量回读按主技能区分目标已取得、其他版本已保存与目标待补。
- 导入失败或返回不明时，先确认原操作终态，再通过现有受支持接口重新查询父条目、持久化附件和实际文件，不把失败调用产生的标识或旧附件缓存当成功证据。已保存且核验通过则复用；已确认原操作结束及原生回滚、附件不存在且有效源文件完整时，刷新读取结果、弃用失败标识，再续做未完成部分。未知结果不盲目重试。文件占用先结束本次读取，不擅自关闭用户应用或改数据库、storage、第三方插件。确认成功后再去重和清理自有暂存。

认证按已配置工具处理，凭据不输出。具体 profile、端口和桥接配置从当前插件及本机配置发现，不把测试机器路径写成通用配置，不自动安装新桥接或改写第三方插件。

## 版本去重执行

只处理本次下载触及或用户指定的父条目，沿用技能正文的版本判断和批注保留规则。不用“所有非保留 PDF”作为删除条件：补充材料、更正文件、身份或版本不明的文件均不在清理集合。

1. **记录候选**：通过已配置接口回读父条目身份、分类、标签、独立笔记及所有有效附件。保存保留附件和候选附件的 libraryID、key、parentID、文件哈希、正文角色及版本依据。保留目标按主技能核实；目标为当前正式版时须有出版社记录与文件内容证据。同版本但字节不同的判断记录实际比较，不能仅凭去除空白后的文字相同忽略公式图表变化。
2. **检查阅读内容**：回读 Zotero PDF 批注和关联笔记，并检查附件自身笔记及 PDF 内嵌批注；用可用的 PDF 检查工具识别批注对象，无法辨别时保留。任何读取失败都标为未知。多个同版本附件各有阅读内容时暂留；不靠批注数量相同就认定内容重复。检查结果与暂留原因留在本次记录，不修改用户笔记。
3. **核验保留文件**：确认原生入库或复用成功，重新取得实际路径并检查 PDF 可读性、论文身份、目标版本及 SHA-256。新导入文件哈希应与已核验下载一致；复用不同字节的同版本文件时，保留其自身哈希及版本等价依据，不要求它匹配本次下载哈希。新版确有更新但旧版有批注时，报告新版的准确附件入口作为阅读目标，不擅自改旧附件标题或笔记。
4. **可恢复清理**：通过现有桥接在一次原生调用中重新核对父条目、保留和待清理附件的 key、归属、有效状态及阅读内容，再调用 `Zotero.Items.trashTx(ids)`；没有候选时不调用。文件哈希与嵌入批注也须在提交前复核；快照发生变化时重新判断。只移入回收站，不调用永久删除接口、不操作 storage 文件、不清空回收站。
5. **回读验收**：确认候选处于回收站、保留附件仍有效且可读、哈希未变，父条目身份、分类、标签和独立笔记及所有暂留/独立材料均未改变。以一份可读请求版本正文为目标，有例外时列出暂留附件及原因；明确只取历史或非正式版本时，不据此清理其他不同版本。分别报告目标取得状态、去重状态、移入回收站数量，不能互相替代。

调用返回不明时，先按原始标识读取附件当前状态及文件，已入库或已移入回收站的对象不重复操作。若目标版本未核验、文件不可读或导入失败，保留旧附件和有效暂存，不进入清理。此流程复用现有 Zotero 接口，不新增后台服务，也不改写第三方 Zotero 插件。

## 任务分类操作

以资料库和 collection key 定位已确认分类；新建前先查询，续做复用同一 key。使用 Zotero 原生分类接口创建必要分类，通过条目的 `addToCollection(collectionID)` 和 `saveTx()` 添加归类。回读 `getCollections()` 检查目标关系及原有归类仍在；不使用仅含新分类的 `setCollections()` 覆盖原关系。同一资料库内复用原条目和附件，不为不同任务复制 PDF；跨资料库不能直接套用此关系操作，需另行确定目标，不自动复制整套文献。

重复执行前先回读，分类已经存在或条目已在其中时复用。不自动重组历史分类。测试清理只针对本次新建且身份已核对的对象，移除测试分类不应删除用户文献。

## 隔离试跑与未验证项

2026-10-08 两个新上下文执行者实际完成 10 个隔离接口场景：既有和本地 PDF 复用、DOI 通用搜索未命中后的题名核对、仅元数据入库、自动开关开／关、客户端真实超时而模拟原生任务继续执行、部分保存后补缺项、外部设置变化及重启后续做。回读操作日志、文件哈希和任务状态，未出现重复对象或模拟抓取事件，既有笔记、批注和分类保持；设置变化场景按规则停止后续写入并待续，恢复依据不完整时保留当前值并报告待恢复。

这些是隔离接口的行为证据，不是实际 Sci-Hub 插件触发验收。真实环境只读核实了 Zotero API／Connector 可用及已保存的自动抓取关闭状态；真实新增条目的临时暂停、恢复和并发设置变化分支尚未触发验证。下方历史实测不替代本次新增流程的真实验收。

## 已验证范围

2026-09-10 在当前 Windows/Zotero 9.0.6 环境实测：通过已安装后台桥接调用原生接口，可给先前已保存的测试条目补 PDF，回读、内容一致性及临时文件移入通过；重复请求前查附件可复用已有文件，查重是调用流程的职责，不是导入函数自动提供的保证。

同日使用临时分类和带 PDF、阅读笔记的测试条目验证：原条目加入第二个分类后保留第一分类，重复加入不增加关系、条目或附件；移除第二分类后条目仍在。条目 key、附件 ID/路径和笔记内容均未变化，测试对象已清理。

公开网页流程使用 arXiv 的 `1706.03762`：在后台浏览器读取页面 PDF 链接，以公开请求取得 15 页、2,215,244 字节的 PDF，再添加到测试条目并回读验证。该文件按 arXiv 版本记录，未冒充出版社正式版。测试条目及附件已清理。

同日通过用户配置的 Windows 凭据库及本机助手完成后台学校登录，经用户同意 CARSI 信息发布后获得 IEEE 机构访问。论文 DOI `10.1109/JLT.2017.2776320` 的官方 PDF 返回 HTTP 200、`application/pdf`，共 7 页、2,636,722 字节，文件头、题名、DOI、哈希及首页检查通过。按题名找到已有 Zotero 条目并核对实际 DOI；新旧 PDF 去除下载授权页脚后逐页正文一致，复用原附件，保留原分类，清理本轮下载暂存，未新增该论文条目或附件。此次验证的是机构下载和已有附件复用，新附件入库由前述测试覆盖。

本次通用搜索 DOI 片段曾返回空结果，题名搜索却找到已有条目：检索接口的字段覆盖范围需核实，空结果不能直接当成查重完成。正文一致也不等于文件字节一致。

浏览器原生保存信息下拉框自动选择、Connector 扩展自动调用仍未验证；未持续监测前台焦点。当前可用路线是后台登录、网页取得 PDF 后原生入库或复用附件，不把本机一次实测推广成所有机构和机器均可用。

2026-09-15 独立代表性试跑：在已接通机构访问、正常宿主审批和具备 PDF 依赖的解释器下，取得 IEEE 论文当前卷期正式 PDF，实际检查首页与卷期页码后补到原 Zotero 父条目，哈希回读及原附件、分类保护通过。试跑得到现有机构会话和解释器定位帮助，未独立验证首次登录或自动触发；本机登录恢复另有 59 项隔离检查，不能代替所有机构的真实验收。批量下载完成情况与技能运行副本是否生效分别记录。
