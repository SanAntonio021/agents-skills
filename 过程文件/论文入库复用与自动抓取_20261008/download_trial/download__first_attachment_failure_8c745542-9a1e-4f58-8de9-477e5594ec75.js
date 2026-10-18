
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

const metadata={"itemType": "journalArticle", "title": "Zotero Fixture Study: Spectral Windows in a Simulated Link", "DOI": "10.0000/zotero-fixture.target-001", "date": "2026", "publicationTitle": "Fixture Journal (Simulated)", "volume": "1", "issue": "1", "pages": "1-2", "url": "https://example.invalid/zotero-fixture/target-001", "creators": [{"creatorType": "author", "firstName": "Mira", "lastName": "Fixture"}], "localPDF": "D:\\BaiduSyncdisk\\.agents\\skills\\\u8fc7\u7a0b\u6587\u4ef6\\\u8bba\u6587\u5165\u5e93\u590d\u7528\u4e0e\u81ea\u52a8\u6293\u53d6_20261008\\fixture\\inputs\\simulated_target.pdf", "localBibTeX": "D:\\BaiduSyncdisk\\.agents\\skills\\\u8fc7\u7a0b\u6587\u4ef6\\\u8bba\u6587\u5165\u5e93\u590d\u7528\u4e0e\u81ea\u52a8\u6293\u53d6_20261008\\fixture\\inputs\\simulated_target.bib", "sha256": "61485e23b1c513f355a4fa6f1cb6e3ea8864a6aa44435b7e412e57acef84280e"};
const validatedAttachmentKeys=[];
return await runPaperImport("8c745542-9a1e-4f58-8de9-477e5594ec75","{\"contextID\": \"1fb0994b-67c8-4903-b765-d00d5cd4eca5\", \"pid\": 52084, \"processInstance\": \"3a0013b9-449c-49ec-a731-1f344900e4f9\", \"startedAt\": \"2026-10-08T13:47:18.596Z\"}",["zoteroscihub.automatic_pdf_download"],async ({beforeWrite,rememberItem})=>{
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
    