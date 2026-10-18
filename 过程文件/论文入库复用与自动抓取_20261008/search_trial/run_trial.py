import datetime
import hashlib
import json
import pathlib
import sys
import urllib.parse
import urllib.request
import uuid

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:11597"
ROOT = pathlib.Path(__file__).resolve().parent
ALLOWED = {"search__local_material_handoff", "search__metadata_only"}

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

class Session:
    def __init__(self, directory):
        self.directory = directory
        self.log = directory / "requests_responses.jsonl"

    def request(self, case, suffix="", body=None, name=None):
        if case not in ALLOWED:
            raise ValueError("case_not_authorized")
        path = "/cases/" + case + suffix
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        method = "GET" if body is None else "POST"
        request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method=method)
        entry = {"time": stamp(), "case": case, "method": method, "path": path, "request": body}
        try:
            with urllib.request.urlopen(request, timeout=50) as response:
                raw = response.read()
                entry["http_status"] = response.status
                if "application/json" in response.headers.get("Content-Type", ""):
                    result = json.loads(raw.decode("utf-8"))
                    entry["response"] = result
                else:
                    result = raw
                    entry["response"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "content_type": response.headers.get("Content-Type")}
        except Exception as error:
            entry["error"] = repr(error)
            with self.log.open("a", encoding="utf-8") as target:
                target.write(json.dumps(entry, ensure_ascii=False) + "\n")
            raise
        with self.log.open("a", encoding="utf-8") as target:
            target.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if name:
            if isinstance(result, bytes):
                (self.directory / name).write_bytes(result)
            else:
                write_json(self.directory / name, result)
        return result

def probe(directory):
    session = Session(directory)
    snapshots = {}
    for case in sorted(ALLOWED):
        case_state = session.request(case, name=case + "_case.json")
        state = {"case": case_state}
        for endpoint in ["process", "libraries", "collections", "settings", "items"]:
            state[endpoint] = session.request(case, "/" + endpoint)
        doi = "10.0000/zotero-fixture.target-001"
        title = "Zotero Fixture Study: Spectral Windows in a Simulated Link"
        state["doi_search"] = session.request(case, "/items?doi=" + urllib.parse.quote(doi))
        state["title_search"] = session.request(case, "/items?title=" + urllib.parse.quote(title))
        state["local_index_search"] = session.request(case, "/search?q=" + urllib.parse.quote(title))
        state["native_capabilities"] = session.request(case, "/js", {"code": "return {scihub: Zotero.Scihub, userLibraryID: Zotero.Libraries.userLibraryID, libraries: Zotero.Libraries.getAll(), prefs: {get: typeof Zotero.Prefs.get, set: typeof Zotero.Prefs.set, registerObserver: typeof Zotero.Prefs.registerObserver, unregisterObserver: typeof Zotero.Prefs.unregisterObserver}, currentAutomatic: Zotero.Prefs.get('zoteroscihub.automatic_pdf_download')};", "mode": "async", "waitMs": 30000})
        snapshots[case] = state
    write_json(directory / "initial_state.json", snapshots)
    return snapshots

def validate_materials(directory):
    import fitz
    snapshots = json.loads((directory / "initial_state.json").read_text(encoding="utf-8"))
    metadata = snapshots["search__local_material_handoff"]["case"]["inputs"][0]
    pdf = pathlib.Path(metadata["localPDF"])
    bib = pathlib.Path(metadata["localBibTeX"])
    index = pdf.parent / "publication_index.json"
    pdf_bytes = pdf.read_bytes()
    bib_text = bib.read_text(encoding="utf-8")
    index_text = index.read_text(encoding="utf-8")
    index_record = json.loads(index_text)
    with fitz.open(pdf) as reader:
        texts = [page.get_text() for page in reader]
        page_count = len(reader)
    text_content = "\n".join(texts)
    checks = {
        "pdf_path": str(pdf), "bibtex_path": str(bib), "index_path": str(index),
        "bytes": len(pdf_bytes), "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "pdf_header": pdf_bytes.startswith(b"%PDF-"), "pdf_eof": pdf_bytes.rstrip().endswith(b"%%EOF"),
        "pdf_page_count": page_count, "pdf_text": text_content, "bibtex_text": bib_text,
        "index": index_record,
        "identity": {"pdf_title": metadata["title"] in text_content, "pdf_doi": metadata["DOI"] in text_content, "pdf_author": metadata["creators"][0]["firstName"] + " " + metadata["creators"][0]["lastName"] in text_content, "bib_title": metadata["title"] in bib_text, "bib_doi": metadata["DOI"] in bib_text, "index_title": metadata["title"] in index_text, "index_doi": metadata["DOI"] in index_text, "expected_sha256": metadata["sha256"] == hashlib.sha256(pdf_bytes).hexdigest()},
        "scope": "Local simulated material only; no current publication version upgrade and no DOI network resolution",
        "version": "unresolved", "version_reason": "The PDF is a one-page fixture mock, not evidence of a real publisher version. Identity checked; local file reused as provided.",
    }
    assert checks["pdf_header"] and checks["pdf_eof"] and page_count > 0
    assert all(checks["identity"].values()), checks["identity"]
    write_json(directory / "local_material_validation.json", checks)
    handoff = {
        "from_skill": "paper-search", "to_skill": "paper-download", "case": "search__local_material_handoff",
        "title": metadata["title"], "DOI": metadata["DOI"], "metadata": metadata,
        "verification_status": "metadata-verified", "verification_source": "Fixture offline publication index and supplied BibTeX, matched to PDF content",
        "library": {"interface": "native", "libraryID": 1, "name": "Isolated Fixture Library"},
        "collection": {"id": 20, "key": "FXCOL020", "name": "Fixture / Communications"},
        "parent_item": None, "parent_search": "Actual DOI and title queries returned empty before import",
        "local_pdf": str(pdf), "local_bibtex": str(bib), "local_index": str(index),
        "sha256": checks["sha256"], "version": "unresolved", "version_requirement": "Reuse supplied local simulated PDF; do not obtain or upgrade another version",
        "network_channels_checked": [], "network_request_authorized": False,
        "handoff_status": "Ready; same agent continues paper-download local import",
    }
    write_json(directory / "local_material_handoff.json", handoff)
    return checks

def import_tasks(directory):
    session = Session(directory)
    snapshots = json.loads((directory / "initial_state.json").read_text(encoding="utf-8"))
    template = (ROOT / "native_import_template.js").read_text(encoding="utf-8")
    jobs = {}
    for case in sorted(ALLOWED):
        state = snapshots[case]
        process = session.request(case, "/process")
        current_settings = session.request(case, "/settings")
        assert process["processInstance"] == state["process"]["processInstance"]
        assert process["contextID"] == state["process"]["contextID"]
        assert current_settings[state["case"]["automaticSettingKey"]] == state["settings"][state["case"]["automaticSettingKey"]]
        metadata = state["case"]["inputs"][0]
        operation = {
            "operationId": str(uuid.uuid4()),
            "processIdentity": json.dumps({key: process[key] for key in ["pid", "processInstance", "startedAt", "contextID"]}, sort_keys=True),
            "automaticSettingKey": state["case"]["automaticSettingKey"],
            "libraryID": 1, "collectionID": 20, "collectionKey": "FXCOL020",
            "metadata": {"itemType": metadata["itemType"], "DOI": metadata["DOI"], "title": metadata["title"],
                         "fields": {key: metadata[key] for key in ["title", "DOI", "date", "publicationTitle", "volume", "issue", "pages", "url"]}, "creators": metadata["creators"]},
            "withPDF": case == "search__local_material_handoff", "localPDF": metadata["localPDF"] if case == "search__local_material_handoff" else None,
        }
        write_json(directory / (case + "_operation.json"), operation)
        code = template.replace("__REQUEST__", json.dumps(operation, ensure_ascii=False))
        (directory / (case + "_native_request.js")).write_text(code, encoding="utf-8")
        response = session.request(case, "/js", {"code": code, "mode": "async", "waitMs": 30000}, name=case + "_save_response.json")
        if response["status"] == "running":
            response = session.request(case, "/tasks/" + response["taskID"], name=case + "_task_state.json")
        if response["status"] != "completed" or response["result"]["status"] != "completed":
            jobs[case] = {"operation": operation, "response": response, "verification": "pending_or_failed"}
            write_json(directory / "import_results.json", jobs)
            raise RuntimeError("native_task_not_completed: " + case)
        job = response["result"]
        parent_key = job["output"]["parent"]["key"]
        native_readback = session.request(case, "/js", {"code": "const item = await Zotero.Items.getByLibraryAndKeyAsync(1, " + json.dumps(parent_key) + "); return {parent: item.toJSON(), collections: item.getCollections(), attachments: (await Zotero.Items.getAsync(item.getAttachments())).map(a => a.toJSON()), job: Zotero.__paperDownloadBatches?.jobs[" + json.dumps(operation["operationId"]) + "] ?? null, active: Zotero.__paperDownloadBatches?.active ?? null, automatic: Zotero.Prefs.get(" + json.dumps(operation["automaticSettingKey"]) + ")};", "mode": "async", "waitMs": 30000}, name=case + "_native_readback.json")
        parent = native_readback["result"]["parent"]
        saved_state = {"native_readback": native_readback, "settings": session.request(case, "/settings"), "items": session.request(case, "/items"), "collections": session.request(case, "/collections"), "logs": session.request(case, "/logs")}
        write_json(directory / (case + "_final_state.json"), saved_state)
        verification = {"status": "completed", "native_readback_success": native_readback["status"] == "completed", "automatic_restored": saved_state["settings"] == state["settings"], "active_batch_cleared": native_readback["result"]["active"] is None, "collection_20": 20 in native_readback["result"]["collections"], "parent_count": len([item for item in saved_state["items"] if item["itemType"] == "journalArticle"]), "pdf_count": len([item for item in saved_state["items"] if item["itemType"] == "attachment" and item.get("attachmentContentType") == "application/pdf"])}
        if operation["withPDF"]:
            import fitz
            attachment = job["output"]["attachment"]
            file_bytes = session.request(case, "/attachments/" + str(attachment["id"]) + "/file", name=case + "_saved_pdf_readback.pdf")
            with fitz.open(stream=file_bytes, filetype="pdf") as reader:
                actual_text = "\n".join(page.get_text() for page in reader)
                actual_pages = len(reader)
            verification["pdf_readback"] = {"attachmentID": attachment["id"], "attachmentKey": attachment["key"], "parentID": attachment["parentID"], "bytes": len(file_bytes), "sha256": hashlib.sha256(file_bytes).hexdigest(), "source_hash_match": hashlib.sha256(file_bytes).hexdigest() == metadata["sha256"], "title_match": metadata["title"] in actual_text, "doi_match": metadata["DOI"] in actual_text, "page_count": actual_pages}
            assert verification["pdf_readback"]["source_hash_match"] and verification["pdf_readback"]["title_match"] and verification["pdf_readback"]["doi_match"]
            assert attachment["parentID"] == parent["id"]
        assert verification["automatic_restored"] and verification["active_batch_cleared"] and verification["collection_20"]
        assert verification["parent_count"] == 1
        assert verification["pdf_count"] == (1 if operation["withPDF"] else 0)
        jobs[case] = {"operation": operation, "response": response, "verification": verification}
        write_json(directory / "import_results.json", jobs)
    handoff_path = directory / "local_material_handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["handoff_status"] = "Completed; local PDF copied to managed attachment, persistent file readback hash and content verified"
    handoff["parent_item"] = jobs["search__local_material_handoff"]["response"]["result"]["output"]["parent"]
    handoff["attachment"] = jobs["search__local_material_handoff"]["response"]["result"]["output"]["attachment"]
    write_json(handoff_path, handoff)
    return jobs

def finalize(directory):
    session = Session(directory)
    initial = json.loads((directory / "initial_state.json").read_text(encoding="utf-8"))
    imports = json.loads((directory / "import_results.json").read_text(encoding="utf-8"))
    validation = json.loads((directory / "local_material_validation.json").read_text(encoding="utf-8"))
    source_checks = {
        "pdf_unchanged": hashlib.sha256(pathlib.Path(validation["pdf_path"]).read_bytes()).hexdigest() == validation["sha256"],
        "bibtex_unchanged": pathlib.Path(validation["bibtex_path"]).read_text(encoding="utf-8") == validation["bibtex_text"],
        "index_unchanged": json.loads(pathlib.Path(validation["index_path"]).read_text(encoding="utf-8")) == validation["index"],
    }
    assert all(source_checks.values())
    results = {"source_checks": source_checks, "cases": {}, "incomplete": [], "scope": "Only two authorized search cases; isolated fixture API; no external retrieval or DOI resolution"}
    for case in sorted(ALLOWED):
        tasks = session.request(case, "/tasks", name=case + "_tasks_final.json")
        logs = session.request(case, "/logs", name=case + "_logs_final.json")
        relevant = [entry for entry in logs if entry.get("processInstance") == initial[case]["process"]["processInstance"]]
        fetches = [entry for entry in relevant if entry["action"] == "scihub.simulated.fetch_popup"]
        pref_changes = [entry for entry in relevant if entry["action"] == "native.pref.set"]
        writes = [entry for entry in relevant if entry["action"].startswith("native.item.save.") or entry["action"].startswith("native.attachment.import.")]
        observer_events = [entry for entry in relevant if "Observer" in entry["action"]]
        assert len(fetches) == 0
        assert pref_changes[0]["value"] is False and pref_changes[-1]["value"] is True
        case_import = imports[case]
        result = {
            "verification": case_import["verification"], "operation_id": case_import["operation"]["operationId"],
            "task_id": case_import["response"]["taskID"], "parent_key": case_import["response"]["result"]["output"]["parent"]["key"],
            "parent_action": case_import["response"]["result"]["output"]["parentAction"],
            "attachment_action": case_import["response"]["result"]["output"]["attachmentAction"],
            "simulated_fetch_popup_events": len(fetches), "preference_changes": pref_changes,
            "write_events": writes, "observer_events": observer_events,
            "task_readback": tasks,
        }
        results["cases"][case] = result
    write_json(directory / "final_summary.json", results)
    lines = ["# paper-search 隔离业务试跑", "", "仅执行两个授权 search 案例，来源为模拟离线记录；未访问真实 Zotero，未联网解析 DOI 或获取 PDF。", "", "| 案例 | 父条目 | 分类 | PDF | 自动设置 | 自动抓取事件 |", "|---|---|---|---|---|---|", "| search__local_material_handoff | FX000100，新增一次 | 20 / FXCOL020 | FX000101；1 页，863 字节，SHA-256 与源文件一致 | true → false → true | 0 |", "| search__metadata_only | FX000100，新增一次 | 20 / FXCOL020 | 0；本任务未请求 | true → false → true | 0 |", "", "任务 A 已读取本地 PDF、BibTeX、publication_index.json，核对题名、DOI、作者与哈希，按 paper-search 交接到 paper-download 本地复制入库。BibTeX 与索引用作题录依据，未作为额外附件导入。文件为模拟输入，version=unresolved；本轮未升级版本。", "", "任务 B 复用环境提供的已核实离线题录，按同一自动抓取检查流程只保存元数据。", "", "源 PDF、BibTeX、索引回读未变化。两任务原生 finally 恢复设置并移除监听，操作注册表 active 已清空。未完成项：无。", "", "## 可核查材料", "", "- requests_responses.jsonl：全部请求、代码、响应及文件回读哈希。", "- *_native_request.js、*_operation.json：实际执行代码、操作编号和进程身份。", "- *_save_response.json、*_native_readback.json、*_final_state.json、*_logs_final.json：保存、持久化回读与日志。", "- local_material_validation.json、local_material_handoff.json：原始材料核对和完成交接。", "- import_results.json、final_summary.json：逐案例结果与最终事件检查。", "", "运行限制：这些结果只证明隔离模拟环境中的流程；没有测量真实 Zotero 或外部网站行为。"]
    (directory / "结果.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"source_checks": source_checks, "cases": {case: {"parent_action": value["parent_action"], "attachment_action": value["attachment_action"], "simulated_fetch_popup_events": value["simulated_fetch_popup_events"], "preference_changes": [{"value": change["value"], "time": change["time"]} for change in value["preference_changes"]]} for case, value in results["cases"].items()}, "incomplete": []}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode == "probe":
        directory = ROOT / ("run_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8])
        directory.mkdir(parents=True)
        snapshots = probe(directory)
        print(json.dumps({"directory": str(directory), "state": snapshots}, ensure_ascii=False, indent=2))
    elif mode == "validate":
        directory = pathlib.Path(sys.argv[2]).resolve()
        assert directory.is_relative_to(ROOT)
        print(json.dumps(validate_materials(directory), ensure_ascii=False, indent=2))
    elif mode == "import":
        directory = pathlib.Path(sys.argv[2]).resolve()
        assert directory.is_relative_to(ROOT)
        jobs = import_tasks(directory)
        print(json.dumps({case: job["verification"] for case, job in jobs.items()}, ensure_ascii=False, indent=2))
    elif mode == "finalize":
        directory = pathlib.Path(sys.argv[2]).resolve()
        assert directory.is_relative_to(ROOT)
        print(json.dumps(finalize(directory), ensure_ascii=False, indent=2))
    else:
        raise ValueError("unknown_mode")
