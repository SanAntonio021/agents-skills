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
    savedKeys: [], preferenceRecovery: [], error: null, output: null
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
    job.output = await work({ beforeWrite, rememberItem: item => {
      if (item.key) job.savedKeys.push({ libraryID: item.libraryID, key: item.key });
    }});
    terminal = "completed";
  } catch (error) {
    job.error = stopReason || "native_write_failed";
    job.errorDetail = String(error);
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

const request = {"operationId": "0ce0343c-8655-47f1-8f17-3217819171d3", "processIdentity": "{\"contextID\": \"13cc0425-4cea-43a9-9e08-9e4f08a9e483\", \"pid\": 52084, \"processInstance\": \"3a0013b9-449c-49ec-a731-1f344900e4f9\", \"startedAt\": \"2026-10-08T13:47:18.596Z\"}", "automaticSettingKey": "zoteroscihub.automatic_pdf_download", "libraryID": 1, "collectionID": 20, "collectionKey": "FXCOL020", "metadata": {"itemType": "journalArticle", "DOI": "10.0000/zotero-fixture.target-001", "title": "Zotero Fixture Study: Spectral Windows in a Simulated Link", "fields": {"title": "Zotero Fixture Study: Spectral Windows in a Simulated Link", "DOI": "10.0000/zotero-fixture.target-001", "date": "2026", "publicationTitle": "Fixture Journal (Simulated)", "volume": "1", "issue": "1", "pages": "1-2", "url": "https://example.invalid/zotero-fixture/target-001"}, "creators": [{"creatorType": "author", "firstName": "Mira", "lastName": "Fixture"}]}, "withPDF": false, "localPDF": null};
return await runPaperImport(request.operationId, request.processIdentity,
  [request.automaticSettingKey], async ({beforeWrite, rememberItem}) => {
    const libraryID = Zotero.Libraries.userLibraryID;
    if (libraryID !== request.libraryID) throw new Error("library_identity_changed");
    const collection = await Zotero.Collections.getAsync(request.collectionID);
    if (!collection || collection.key !== request.collectionKey || collection.libraryID !== libraryID)
      throw new Error("collection_identity_changed");
    async function candidates() {
      const doiSearch = new Zotero.Search();
      doiSearch.libraryID = libraryID;
      doiSearch.addCondition("DOI", "is", request.metadata.DOI);
      const titleSearch = new Zotero.Search();
      titleSearch.libraryID = libraryID;
      titleSearch.addCondition("title", "is", request.metadata.title);
      const ids = [...new Set([...(await doiSearch.search()), ...(await titleSearch.search())])];
      const all = await Zotero.Items.getAsync(ids);
      const regular = all.filter(item => item.isRegularItem());
      const matches = regular.filter(item => item.getField("DOI") === request.metadata.DOI && item.getField("title") === request.metadata.title);
      if (regular.length !== matches.length) throw new Error("identity_conflict");
      if (matches.length > 1) throw new Error("duplicate_parent_conflict");
      return matches;
    }
    let found = await candidates();
    let parent = found[0];
    let parentAction = "reused";
    if (!parent) {
      beforeWrite();
      found = await candidates();
      parent = found[0];
      if (!parent) {
        parent = new Zotero.Item(request.metadata.itemType);
        parent.libraryID = libraryID;
        for (const [field, value] of Object.entries(request.metadata.fields)) parent.setField(field, value);
        parent.setCreators(request.metadata.creators);
        parent.addToCollection(request.collectionID);
        beforeWrite();
        await parent.saveTx();
        rememberItem(parent);
        parentAction = "created";
      }
    }
    const originalCollections = parent.getCollections();
    if (!originalCollections.includes(request.collectionID)) {
      beforeWrite();
      parent.addToCollection(request.collectionID);
      await parent.saveTx();
      rememberItem(parent);
    }
    parent = await Zotero.Items.getByLibraryAndKeyAsync(libraryID, parent.key);
    if (parent.getField("DOI") !== request.metadata.DOI || parent.getField("title") !== request.metadata.title)
      throw new Error("parent_readback_identity_mismatch");
    let attachment = null;
    let attachmentAction = "not_requested";
    if (request.withPDF) {
      const attachments = await Zotero.Items.getAsync(parent.getAttachments());
      const pdfs = attachments.filter(item => item.attachmentContentType === "application/pdf");
      if (pdfs.length > 1) throw new Error("multiple_existing_pdfs_need_verification");
      attachment = pdfs[0];
      attachmentAction = attachment ? "reused_pending_file_readback" : "imported";
      if (!attachment) {
        beforeWrite();
        const freshParent = await Zotero.Items.getByLibraryAndKeyAsync(libraryID, parent.key);
        const freshAttachments = await Zotero.Items.getAsync(freshParent.getAttachments());
        if (freshAttachments.some(item => item.attachmentContentType === "application/pdf"))
          throw new Error("attachment_state_changed");
        attachment = await Zotero.Attachments.importFromFile({
          file: request.localPDF, parentItemID: freshParent.id, libraryID,
          title: "Supplied simulated local PDF (version unresolved)", contentType: "application/pdf"
        });
        rememberItem(attachment);
      }
    }
    return {parentAction, attachmentAction, parent: parent.toJSON(),
      attachment: attachment ? attachment.toJSON() : null,
      attachmentPath: attachment ? await attachment.getFilePathAsync() : null,
      originalCollections, collections: parent.getCollections(),
      handoff: request.withPDF ? "paper-search local-material handoff completed by paper-download local reuse" : "paper-search metadata-only import; no PDF request"};
  });
