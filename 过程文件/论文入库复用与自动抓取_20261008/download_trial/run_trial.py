import sys
sys.dont_write_bytecode = True
import json, urllib.request, urllib.parse, urllib.error, hashlib, pathlib, time, uuid, threading
import fitz

BASE = "http://127.0.0.1:11597"
OUT = pathlib.Path(__file__).resolve().parent
CASES = ["download__" + x for x in [
    "existing_pdf_notes_collections", "local_pdf_auto_on", "local_pdf_auto_off",
    "doi_generic_search_empty_title", "timeout_continues", "first_attachment_failure",
    "manual_setting_change", "restart_saved_partial"]]
LOG = OUT / "requests_responses.jsonl"
lock = threading.Lock()

def record(value):
    value["recordedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    with lock:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(value, ensure_ascii=False) + "\n")

def call(case, endpoint="", body=None, timeout=5):
    assert case in CASES
    path = "/cases/" + case + endpoint
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    started = time.monotonic()
    entry = {"case": case, "path": path, "method": req.method, "request": body, "clientTimeoutSeconds": timeout}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if endpoint.startswith("/attachments/") and endpoint.endswith("/file"):
                result = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "pdfHeader": raw.startswith(b"%PDF-")}
                with fitz.open(stream=raw, filetype="pdf") as doc:
                    result["pages"] = len(doc)
                    result["text"] = "\n".join(p.get_text() for p in doc)
                    result["embeddedAnnotations"] = [a.info for p in doc for a in (p.annots() or [])]
            else:
                result = json.loads(raw)
            entry.update({"httpStatus": r.status, "response": result, "elapsedSeconds": time.monotonic() - started})
            record(entry)
            return result
    except Exception as e:
        entry.update({"error": type(e).__name__ + ": " + str(e), "elapsedSeconds": time.monotonic() - started})
        record(entry)
        raise

def native(case, code, timeout=5, wait_ms=30000):
    return call(case, "/js", {"code": code, "mode": "async", "waitMs": wait_ms}, timeout)

def pdfcheck(path, expected):
    p = pathlib.Path(path)
    raw = p.read_bytes()
    with fitz.open(path) as doc:
        text = "\n".join(page.get_text() for page in doc)
        anns = [a.info for page in doc for a in (page.annots() or [])]
        result = {"path": str(p), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "pdfHeader": raw.startswith(b"%PDF-"), "pages": len(doc), "text": text, "embeddedAnnotations": anns}
    result["matchesIndexSHA256"] = result["sha256"] == expected["sha256"]
    result["titlePresent"] = expected["title"] in text
    result["doiPresent"] = expected["DOI"] in text
    result["authorPresent"] = all(c["lastName"] in text for c in expected["creators"])
    result["version"] = "official" if "Official simulated publication" in text else "unresolved"
    return result

def snapshot(case, phase):
    endpoints = ["", "/process", "/libraries", "/collections", "/items", "/settings", "/tasks", "/logs"]
    data = {e or "/case": call(case, e) for e in endpoints}
    (OUT / (case + "_" + phase + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def prepare():
    all_initial = {}
    for case in CASES:
        initial = snapshot(case, "initial")
        metadata = initial["/case"]["inputs"][0]
        validation = pdfcheck(metadata["localPDF"], metadata)
        bib = pathlib.Path(metadata["localBibTeX"]).read_text(encoding="utf-8")
        validation["bibTeX"] = bib
        native_probe = native(case, "return {libraryID:Zotero.Libraries.userLibraryID,libraries:Zotero.Libraries.getAll(),scihub:Zotero.Scihub,prefKey:" + json.dumps(initial["/case"]["automaticSettingKey"]) + ",automatic:Zotero.Prefs.get(" + json.dumps(initial["/case"]["automaticSettingKey"]) + "),observerAvailable:typeof Zotero.Prefs.registerObserver==='function',unregisterAvailable:typeof Zotero.Prefs.unregisterObserver==='function',collections:Zotero.Collections.getByLibrary(Zotero.Libraries.userLibraryID)};")
        all_initial[case] = {"initial": initial, "localValidation": validation, "nativeProbe": native_probe}
    (OUT / "initial_evidence.json").write_text(json.dumps(all_initial, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({case:{"controls":v["initial"]["/case"]["controls"], "setting":v["initial"]["/settings"], "items":v["initial"]["/items"], "validation":v["localValidation"]} for case,v in all_initial.items()}, ensure_ascii=False, indent=2))

RUN_BATCH = r"""
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
    job.errorDetail = String(error?.message || error);
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
"""

def locate(case, metadata):
    if case.endswith("doi_generic_search_empty_title"):
        generic = call(case, "/items?q=" + urllib.parse.quote(metadata["DOI"]))
        assert generic == [], "The required empty DOI generic query did not occur"
        titles = call(case, "/items?title=" + urllib.parse.quote(metadata["title"]))
        for candidate in titles:
            item = call(case, "/items/" + str(candidate["id"]))
            assert item["fields"]["DOI"] == metadata["DOI"]
    exact = call(case, "/items?doi=" + urllib.parse.quote(metadata["DOI"]))
    titles = call(case, "/items?title=" + urllib.parse.quote(metadata["title"]))
    regular = [x for x in exact if x["itemType"] == metadata["itemType"] and not x["deleted"]]
    assert len(regular) <= 1
    assert not [x for x in titles if x["id"] not in [p["id"] for p in regular]], "Unresolved title collision"
    checked = []
    for parent in regular:
        assert parent["fields"]["title"] == metadata["title"]
        assert parent["creators"] == metadata["creators"]
        call(case, "/items/" + str(parent["id"]))
        attachments = call(case, "/items/" + str(parent["id"]) + "/attachments")
        call(case, "/items/" + str(parent["id"]) + "/notes")
        for attachment in attachments:
            call(case, "/items/" + str(attachment["id"]) + "/notes")
            call(case, "/items/" + str(attachment["id"]) + "/annotations")
            file = call(case, "/attachments/" + str(attachment["id"]) + "/file")
            assert file["sha256"] == metadata["sha256"]
            assert metadata["title"] in file["text"] and metadata["DOI"] in file["text"]
            checked.append(attachment["key"])
    return regular, checked

def import_code(op_id, process, prefkey, metadata, validated_keys):
    identity = json.dumps({k:process[k] for k in ["pid", "processInstance", "startedAt", "contextID"]}, sort_keys=True)
    code = RUN_BATCH + "\nconst metadata=" + json.dumps(metadata) + ";\n"
    code += "const validatedAttachmentKeys=" + json.dumps(validated_keys) + ";\n"
    code += "return await runPaperImport(" + json.dumps(op_id) + "," + json.dumps(identity) + ",[" + json.dumps(prefkey) + r"""],async ({beforeWrite,rememberItem})=>{
      const libraryID=Zotero.Libraries.userLibraryID;
      const targetCollection=await Zotero.Collections.getAsync(20);
      if (!targetCollection || targetCollection.libraryID!==libraryID || targetCollection.key!=="FXCOL020") throw new Error("target_collection_mismatch");
      const s=new Zotero.Search(); s.libraryID=libraryID; s.addCondition("DOI","is",metadata.DOI);
      const matches=(await Zotero.Items.getAsync(await s.search())).filter(i=>i.isRegularItem() && !i.deleted);
      if(matches.length>1) throw new Error("duplicate_parent_ambiguity");
      let item=matches[0];
      if(item && (item.getField("title")!==metadata.title || JSON.stringify(item.getCreators())!==JSON.stringify(metadata.creators))) throw new Error("parent_identity_mismatch");
      if(!item){
        const ts=new Zotero.Search(); ts.libraryID=libraryID; ts.addCondition("title","is",metadata.title);
        if((await ts.search()).length) throw new Error("unresolved_title_candidate");
        beforeWrite();
        item=new Zotero.Item(metadata.itemType); item.libraryID=libraryID;
        for(const field of ["title","DOI","date","publicationTitle","volume","issue","pages","url"]) item.setField(field,metadata[field]);
        item.setCreators(metadata.creators); item.addToCollection(20);
        await item.saveTx(); rememberItem(item);
      } else if(!item.getCollections().includes(20)){
        beforeWrite(); item.addToCollection(20); await item.saveTx(); rememberItem(item);
      }
      beforeWrite();
      const attachments=(await Zotero.Items.getAsync(item.getAttachments())).filter(i=>!i.deleted && i.attachmentContentType==="application/pdf");
      if(attachments.length){
        if(attachments.some(i=>!validatedAttachmentKeys.includes(i.key))) throw new Error("unvalidated_attachment_found");
        return;
      }
      beforeWrite();
      const attachment=await Zotero.Attachments.importFromFile({file:metadata.localPDF,parentItemID:item.id,libraryID,title:metadata.title+" (simulated local PDF)",contentType:"application/pdf"});
      rememberItem(attachment);
    });
    """
    return code

def jobread(case, op_id):
    code = "const job=Zotero.__paperDownloadBatches?.jobs[" + json.dumps(op_id) + "]; return job?JSON.parse(JSON.stringify(job)):null;"
    return native(case, code)["result"]

def wait_original(case, op_id):
    begin=time.monotonic()
    while time.monotonic()-begin < 45:
        tasks=call(case,"/tasks")
        job=jobread(case,op_id)
        call(case,"/process")
        call(case,"/items")
        call(case,"/settings")
        if job and job["status"] in ("completed","failed"):
            return job
        time.sleep(.25)
    return job

def import_one(case, data, checked, client_timeout=5, manual=False):
    metadata=data["initial"]["/case"]["inputs"][0]
    process=call(case,"/process")
    assert process["liveTaskCount"]==0
    op_id=str(uuid.uuid4())
    code=import_code(op_id,process,data["initial"]["/case"]["automaticSettingKey"],metadata,checked)
    (OUT/(case+"_"+op_id+".js")).write_text(code,encoding="utf-8")
    record({"case":case,"operationId":op_id,"processIdentity":process,"initialSetting":call(case,"/settings"),"event":"operation_recorded_before_write"})
    manual_errors=[]
    if manual:
        def user_change():
            try:
                time.sleep(.4)
                call(case,"/inject/manual-setting",{"key":data["initial"]["/case"]["automaticSettingKey"],"value":True})
                time.sleep(.1)
                call(case,"/inject/manual-setting",{"key":data["initial"]["/case"]["automaticSettingKey"],"value":False})
            except Exception as e:
                manual_errors.append(str(e))
        thread=threading.Thread(target=user_change)
        thread.start()
    response=None
    try:
        response=native(case,code,timeout=client_timeout)
    except TimeoutError:
        pass
    if manual:
        thread.join()
        assert not manual_errors, manual_errors
    if response and response["status"]=="completed":
        job=response["result"]
    else:
        job=wait_original(case,op_id)
    return {"operationId":op_id,"httpResponse":response,"job":job}

def execute():
    evidence=json.loads((OUT/"initial_evidence.json").read_text(encoding="utf-8"))
    result_path=OUT/"business_results.json"
    results=json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    for case in CASES:
        if case in results:
            continue
        data=evidence[case]
        metadata=data["initial"]["/case"]["inputs"][0]
        validation=data["localValidation"]
        assert all(validation[k] for k in ["pdfHeader","matchesIndexSHA256","titlePresent","doiPresent","authorPresent"])
        parents,checked=locate(case,metadata)
        result={"inputVersion":validation["version"],"operations":[]}
        if case.endswith("restart_saved_partial"):
            process=call(case,"/process")
            old_log=[x for x in data["initial"]["/logs"] if x["action"]=="fixture.seed.previousSession"]
            assert process["restartCount"]==1 and process["liveTaskCount"]==0 and old_log
            assert old_log[0]["processInstance"]!=process["processInstance"]
            original= native(case,"return {store:Zotero.__paperDownloadBatches||null,items:(await Zotero.Items.getAll(Zotero.Libraries.userLibraryID)).map(i=>i.toJSON()),automatic:Zotero.Prefs.get('zoteroscihub.automatic_pdf_download')};")["result"]
            assert original["store"] is None and original["automatic"] is False
            result["previousSessionSettingRecovery"]="pending: prior original value and ownership evidence incomplete; current false preserved"
            result["oldProcessEndedEvidence"]={"oldProcessInstance":old_log[0]["processInstance"],"currentProcess":process,"previousStoreRead":original}
        if checked and all(20 in p["collections"] for p in parents):
            result["businessStatus"]="completed_reused_existing_pdf"
            result["reason"]="Existing verified PDF and target collection already present; no writes needed"
        else:
            op=import_one(case,data,checked,client_timeout=.25 if case.endswith("timeout_continues") else 5,manual=case.endswith("manual_setting_change"))
            result["operations"].append(op)
            if case.endswith("first_attachment_failure"):
                assert op["job"]["status"]=="failed" and op["job"]["error"]=="native_write_failed"
                # A confirmed terminal failure permits a fresh lookup and only the missing attachment.
                parents,checked=locate(case,metadata)
                assert len(parents)==1 and checked==[]
                assert pdfcheck(metadata["localPDF"],metadata)["matchesIndexSHA256"]
                op=import_one(case,data,checked)
                result["operations"].append(op)
            result["businessStatus"]="completed_local_pdf_import" if op["job"]["status"]=="completed" else "pending"
            if case.endswith("manual_setting_change"):
                assert op["job"]["error"]=="automatic_preference_changed"
                result["reason"]="External true then false was observed during delayed parent save; stopped before attachment import; saved parent retained and current user false preserved"
        final=snapshot(case,"final")
        result["finalParentCount"]=len([x for x in final["/items"] if x["itemType"]==metadata["itemType"] and not x["deleted"]])
        result["finalPDFCount"]=len([x for x in final["/items"] if x["itemType"]=="attachment" and x.get("attachmentContentType")=="application/pdf" and not x["deleted"]])
        result["finalSetting"]=final["/settings"][data["initial"]["/case"]["automaticSettingKey"]]
        result["simulatedFetchPopupCount"]=sum(x["action"]=="scihub.simulated.fetch_popup" for x in final["/logs"])
        result["protectionChecks"]={}
        for old in data["initial"]["/items"]:
            now=call(case,"/items/"+str(old["id"]))
            # Reuse does not alter existing records; adding an attachment leaves parent data intact.
            result["protectionChecks"][str(old["id"])]= {"identical":old==now,"original":old,"readback":now}
        result["attachmentReadback"]=[]
        for parent in [x for x in final["/items"] if x["itemType"]==metadata["itemType"] and not x["deleted"]]:
            assert 20 in parent["collections"]
            for a in call(case,"/items/"+str(parent["id"])+"/attachments"):
                file=call(case,"/attachments/"+str(a["id"])+"/file")
                native_file=native(case,"const a=await Zotero.Items.getAsync("+str(a["id"])+"); return {key:a.key,parentID:a.parentID,contentType:a.attachmentContentType,path:await a.getFilePathAsync(),item:a.toJSON()};")["result"]
                local=pdfcheck(native_file["path"],metadata)
                assert file["sha256"]==local["sha256"]==metadata["sha256"]
                assert native_file["parentID"]==parent["id"] and native_file["contentType"]=="application/pdf"
                result["attachmentReadback"].append({"attachment":a,"native":native_file,"file":file,"localValidation":local})
        result["sourcePreserved"]=pdfcheck(metadata["localPDF"],metadata)["matchesIndexSHA256"]
        result["notesAnnotationsCollectionsPreserved"]=all(x["identical"] for x in result["protectionChecks"].values())
        result["dedupTrashedCount"]=0
        assert result["simulatedFetchPopupCount"]==0
        assert result["finalParentCount"]==1
        assert result["sourcePreserved"] and result["notesAnnotationsCollectionsPreserved"]
        if result["businessStatus"].startswith("completed"):
            assert result["finalPDFCount"]==1
        else:
            assert case.endswith("manual_setting_change") and result["finalPDFCount"]==0 and result["finalSetting"] is False
        if case.endswith(("local_pdf_auto_off","restart_saved_partial")):
            assert result["finalSetting"] is False
        results[case]=result
        (OUT/"business_results.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"case":case,"status":result["businessStatus"],"parents":result["finalParentCount"],"pdfs":result["finalPDFCount"],"setting":result["finalSetting"],"operations":len(result["operations"])},ensure_ascii=False))

if __name__ == "__main__":
    if "--execute" in sys.argv:
        execute()
    else:
        prepare()
