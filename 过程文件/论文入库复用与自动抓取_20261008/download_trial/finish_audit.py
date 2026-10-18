import sys
sys.dont_write_bytecode=True
import json, pathlib
import run_trial as trial

out=pathlib.Path(__file__).resolve().parent
results=json.loads((out/'business_results.json').read_text(encoding='utf-8'))
audit={}
for case,result in results.items():
    logs=trial.call(case,'/logs')
    jobs=trial.native(case,"return {active:Zotero.__paperDownloadBatches?.active||null,jobs:Zotero.__paperDownloadBatches?.jobs||null,automatic:Zotero.Prefs.get('zoteroscihub.automatic_pdf_download')};")['result']
    actions={}
    for entry in logs:
        actions[entry['action']]=actions.get(entry['action'],0)+1
    filtered=[x for x in logs if ('pref' in x['action'].lower()) or ('import' in x['action'].lower()) or ('save' in x['action'].lower()) or ('scihub' in x['action'].lower()) or ('disconnect' in x['action'].lower())]
    audit[case]={'actionCounts':actions,'events':filtered,'jobsReadback':jobs}
    assert jobs['active'] is None
    assert actions.get('scihub.simulated.fetch_popup',0)==0
    assert all(j['status'] in ('completed','failed') for j in (jobs['jobs'] or {}).values())
    print(json.dumps({'case':case,'actions':{k:v for k,v in actions.items() if any(s in k.lower() for s in ('import','save','pref','scihub','disconnect'))},'jobs':jobs},ensure_ascii=False))
(out/'final_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')

rows=[]
for case,r in results.items():
    status='完成（复用）' if r['businessStatus']=='completed_reused_existing_pdf' else '完成（本地入库）' if r['businessStatus']=='completed_local_pdf_import' else '待续（设置被用户改动）'
    rows.append(f"| `{case}` | {status} | {r['finalParentCount']} | {r['finalPDFCount']} | `{str(r['finalSetting']).lower()}` |")
text='''# paper-download 隔离业务试跑结果

本组只操作 `download__` 前缀的 8 个案例，目标分类是原生个人库 `libraryID=1` 的 `20 / FXCOL020 / Fixture / Communications`。7 个案例完成 PDF 入库或复用，1 个案例按用户设置变化保护规则保留为待续。所有案例模拟抓取弹窗事件为 0；没有真实网络抓取。所有原始输入 PDF 的 SHA-256 回读一致，没有删除原样本、附件、笔记或批注。既有条目、20/21 分类、笔记和批注完整保留。

已实际读取被测 `paper-download/SKILL.md`、`references/zotero-storage.md`、分类约定 `paper-search/SKILL.md` 和 fixture `API.md`。未调用真实 Zotero、未接触真实偏好、未联网解析模拟 DOI、未修改被测技能或 fixture 实现。

| 案例 | 业务结果 | 父条目数 | PDF数 | 最终自动设置 |
|---|---|---:|---:|---|
'''+ '\n'.join(rows)+'''

- `existing_pdf_notes_collections`：已有可读 PDF，已在分类20；直接复用，未保存新条目或附件。原分类21、笔记3、批注4逐条回读与初始对象相同。
- `doi_generic_search_empty_title`：实际首先用通用 q 查 DOI，结果为空；随后题名找到既有父条目并读取实际 DOI，精确 DOI 查询交叉核对。复用 PDF，不创建重复条目。
- `local_pdf_auto_on`：在同一原生任务中暂置 false、保存父条目并导入本地 PDF，finally 恢复 true。
- `local_pdf_auto_off`：遵从明确长期关闭要求，整个本轮没有调用 Prefs.set，最终 false；历史 true 不用作恢复依据。
- `timeout_continues`：实际 HTTP 客户端超时设置0.25秒，短于 saveTx 的1400ms延迟，连接超时后读取同一 operationId 原生 job、任务、进程、持久条目和设置，原操作继续完成；只发起1个入库操作，未重投；自动设置由原任务 finally 在终态时恢复 true。
- `first_attachment_failure`：首次原生任务保存父条目后，附件导入按 fixture 抛出一次异常；先确认 job终态 failed，重新读取持久父条目和附件为空，并回读原PDF哈希。新 operationId只补缺附件，最后父条目1、PDF1，没有重复父条目。
- `manual_setting_change`：入库开始前安排外部操作，在约400ms后用户设置 true，约100ms后 false；观察器记录外部变化。延迟保存父条目完成后，下一次 beforeWrite 拒绝附件新增，finally 标记 preserved_user_change，保留用户 false。父条目已在分类20，PDF尚未入库；这是保护边界下的业务待续，未自行重投或覆盖用户设置。
- `restart_saved_partial`：当前processInstance与历史日志不同、restartCount=1、无运行任务、原生批次全局对象为空，确认原会话已结束；读取已持久化父条目1并只补 PDF，保留20/21。前会话原设置及归属证据不完整，自动设置恢复单独记为 pending，现值false未修改。PDF业务已完成。

本地文件为1页、863字节的隔离模拟正文；标题、作者、DOI与离线题录/BibTeX一致，SHA-256为 `61485e23b1c513f355a4fa6f1cb6e3ea8864a6aa44435b7e412e57acef84280e`。文件明确标注模拟论文，没有真实出版版本证据，记录 `version=unresolved`；本任务是整理现有本地PDF，不触发升级下载，不声称取得真实出版社正式版。

## 复核材料

- `run_trial.py`：实际请求流程和原生入库实现。开始阶段曾将异步 `Zotero.Items.getAll` 当同步使用，产生一次只读 TypeError；已改为 await 后续做，未影响设置或持久条目。
- `requests_responses.jsonl`：逐次实际 HTTP 请求、原生JS代码、响应、时延、0.25秒客户端超时异常及后续同操作查询。
- `initial_evidence.json` 与逐例 `*_initial.json`：初始事实、输入材料正文/BibTeX、原生接口、分类和保护快照。
- `business_results.json`：操作编号、原生 job结果、偏好恢复结果、父附件归属、文件路径、PDF正文/哈希回读及原有内容逐条保护比对。
- `*_final.json`、`final_audit.json`：持久条目、日志动作与所有原生批次终态回读。所有 active 均为空。
- `download__*_UUID.js`：每次实际执行的原生批次代码；首次附件失败及补缺任务分别保留。

没有清理候选，原生移入回收站数量为0。未完成项：manual_setting_change 的PDF入库；restart_saved_partial 的前会话自动设置恢复依据仍不足，现值false保持。
'''
(out/'result.md').write_text(text,encoding='utf-8')
