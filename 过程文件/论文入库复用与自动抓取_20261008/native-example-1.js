(async function(){
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
})
