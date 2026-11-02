// Fixed internal program. Only validated JSON data is substituted by client.py.
const q = __ZOTERO_LIBRARY_INPUT__;
const copy = x => JSON.parse(JSON.stringify(x));
const stop = code => { const e = new Error(code); e.publicCode = code; throw e; };
const needed = (x, code = "capability_missing") => { if (!x) stop(code); };
const processIdentity = () => String(Services.appinfo.processID) + ":" +
    Services.startup.getStartupInfo().process.getTime();
const { AddonManager } = ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
async function inventory() {
    const addons = await AddonManager.getAddonsByTypes(["extension"]);
    return addons.filter(a => a.isActive).map(a => ({id: a.id, version: a.version}))
        .sort((a,b) => a.id.localeCompare(b.id));
}
async function capabilities() {
    return {processIdentity: processIdentity(), addons: await inventory(),
        nativeWrite: typeof Zotero.Item === "function" && typeof Zotero.Collection === "function"
            && typeof Zotero.Items.trash === "function" && typeof Zotero.DB.executeTransaction === "function",
        importFile: typeof Zotero.Attachments.importFromFile === "function",
        preferences: ["get", "set", "registerObserver", "unregisterObserver"].every(k =>
            typeof Zotero.Prefs[k] === "function"),
        fileHash: !!Components.classes["@mozilla.org/security/hash;1"],
        legacyActive: Zotero.__paperDownloadBatches?.active || null};
}
if (q.action === "capabilities") return await capabilities();
async function library() {
    let id = q.request.library.type === "user" ? Zotero.Libraries.userLibraryID
        : Zotero.Groups.getLibraryIDFromGroupID(q.request.library.id);
    const lib = Zotero.Libraries.get(id);
    needed(lib && lib.libraryID && !lib.isPublications, "library_not_found");
    return lib;
}
async function itemAt(id, key) {
    const item = await Zotero.Items.getByLibraryAndKeyAsync(id, key);
    needed(item && item.libraryID === id, "item_not_found");
    await item.loadAllData();
    return item;
}
function fileHash(path) {
    const file = Zotero.File.pathToFile(path);
    needed(file && file.exists() && file.isFile() && file.fileSize <= 209715200, "pdf_unreadable");
    const stream = Components.classes["@mozilla.org/network/file-input-stream;1"]
        .createInstance(Components.interfaces.nsIFileInputStream);
    try {
        stream.init(file, 0x01, 0, 0);
        const hash = Components.classes["@mozilla.org/security/hash;1"]
            .createInstance(Components.interfaces.nsICryptoHash);
        hash.init(hash.SHA256);
        hash.updateFromStream(stream, 0xffffffff);
        return Array.from(hash.finish(false), c => c.charCodeAt(0).toString(16).padStart(2,"0")).join("");
    } finally { stream.close(); }
}
async function fileInfo(item) {
    needed(item.isAttachment() && item.attachmentContentType === "application/pdf", "not_pdf_attachment");
    const path = await item.getFilePathAsync();
    needed(path, "pdf_unreadable");
    return {key: item.key, parentKey: item.parentKey, path, sha256: fileHash(path),
        contentType: item.attachmentContentType, deleted: !!item.deleted,
        annotations: item.getAnnotations(true).length, note: !!item.getNote()};
}
if (q.action === "inspect") {
    const lib = await library();
    const out = [];
    for (const key of q.keys) out.push(await fileInfo(await itemAt(lib.libraryID, key)));
    return {files: out};
}
if (q.action === "operation") {
    const store = Zotero.__zoteroLibraryBatches;
    const job = store?.jobs[q.attemptId];
    return {processIdentity: processIdentity(), job: job ? copy(job) : null,
        active: store?.active || null, legacyActive: Zotero.__paperDownloadBatches?.active || null};
}
needed(q.action === "start", "invalid_native_action");
needed(q.processIdentity === processIdentity(), "process_identity_changed");
const store = Zotero.__zoteroLibraryBatches ||= {active: null, jobs: Object.create(null)};
if (store.jobs[q.attemptId]) {
    needed(store.jobs[q.attemptId].requestHash === q.requestHash, "operation_request_conflict");
    return copy(store.jobs[q.attemptId]);
}
// Legacy scripts must not be run concurrently with this executor.
needed(!Zotero.__paperDownloadBatches?.active, "legacy_batch_active");
needed(!store.active, "another_batch_active");
const job = store.jobs[q.attemptId] = {operationId: q.operationId, attemptId: q.attemptId,
    requestHash: q.requestHash, processIdentity: q.processIdentity, status: "running",
    startedAt: Date.now(), savedKeys: [], collections: [], skipped: [], trashed: [],
    preferenceRecovery: [], error: null, verified: false, contentWritesStarted: false};
store.active = q.attemptId;

const norm = s => String(s || "").normalize("NFKC").replace(/\s+/g," ").trim().toLowerCase();
const doi = s => String(s || "").trim().replace(/^doi:\s*/i, "")
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "").trim().toLowerCase();
const year = s => String(s || "").match(/\b[12][0-9]{3}\b/)?.[0] || norm(s);
const people = rows => JSON.stringify((rows || []).map(p => [p.creatorType || "author",
    norm(p.name || ((p.firstName || "") + " " + (p.lastName || "")))]));
function matchIdentity(item) {
    if (!item.isRegularItem() || item.deleted) return false;
    const ident = q.request.identity;
    if (norm(item.getField("title")) !== norm(ident.title)) return false;
    const wanted = doi(ident.doi), stored = doi(item.getField("DOI"));
    if (wanted && stored && wanted !== stored) return false;
    if (ident.date && year(item.getField("date")) !== year(ident.date)) return false;
    if (ident.creators?.length && people(item.getCreatorsJSON()) !== people(ident.creators)) return false;
    if (wanted && stored) return true;
    return !!((ident.url && String(item.getField("url")).trim() === ident.url.trim()) ||
        (ident.date && ident.creators?.length && year(item.getField("date")) === year(ident.date)
            && people(item.getCreatorsJSON()) === people(ident.creators)));
}
async function findParent(lib) {
    if (q.request.parent_key) {
        const item = await itemAt(lib.libraryID, q.request.parent_key);
        needed(matchIdentity(item), "parent_identity_mismatch");
        return item;
    }
    const search = new Zotero.Search();
    search.libraryID = lib.libraryID;
    const word = norm(q.request.identity.title).match(/[\p{L}\p{N}_]+/gu)
        ?.sort((a,b) => b.length - a.length)[0] || q.request.identity.title;
    search.addCondition("title", "contains", word);
    const ids = await search.search();
    const candidates = [];
    for (const id of ids) {
        const item = await Zotero.Items.getAsync(id);
        await item.loadAllData();
        if (item.isRegularItem() && !item.deleted &&
            norm(item.getField("title")) === norm(q.request.identity.title)) candidates.push(item);
    }
    // Explicit DOI search also finds metadata title differences, which need business review.
    if (q.request.identity.doi) {
        const byDoi = new Zotero.Search(); byDoi.libraryID = lib.libraryID;
        byDoi.addCondition("DOI", "contains", q.request.identity.doi);
        for (const id of await byDoi.search()) {
            const item = await Zotero.Items.getAsync(id); await item.loadAllData();
            if (item.isRegularItem() && !item.deleted && !candidates.some(x => x.id === id)) candidates.push(item);
        }
    }
    for (const key of q.candidateKeys || []) {
        const item = await itemAt(lib.libraryID, key);
        if (item.isRegularItem() && !item.deleted && !candidates.some(x => x.id === item.id)) candidates.push(item);
    }
    const matches = candidates.filter(matchIdentity);
    needed(matches.length <= 1, "duplicate_parents_require_review");
    needed(!candidates.length || (matches.length === 1 && candidates.length === 1), "identity_candidates_require_review");
    return matches[0] || null;
}
function stable(item) {
    const data = copy(item.toJSON());
    delete data.version; delete data.dateModified; delete data.collections;
    return JSON.stringify(data);
}
async function protect(parent) {
    if (!parent) return null;
    const children = [];
    for (const id of [...parent.getAttachments(true), ...parent.getNotes(true)]) {
        const item = await Zotero.Items.getAsync(id); await item.loadAllData();
        const snap = {key: item.key, data: JSON.stringify(item.toJSON())};
        if (item.isAttachment()) {
            const path = await item.getFilePathAsync();
            needed(path || item.attachmentLinkMode === Zotero.Attachments.LINK_MODE_LINKED_URL,
                "existing_attachment_state_unknown");
            if (path) snap.hash = fileHash(path);
            if (item.isFileAttachment()) {
                const annotations = item.getAnnotations(true);
                for (const annotation of annotations) await annotation.loadAllData();
                snap.annotations = JSON.stringify(annotations.map(a => a.toJSON()));
            }
        }
        children.push(snap);
    }
    return {parent: stable(parent), collections: parent.getCollections(), children};
}
async function confirmProtected(parent, baseline, trashed=[]) {
    if (!baseline) return;
    await parent.loadAllData();
    needed(stable(parent) === baseline.parent, "protected_parent_changed");
    needed(baseline.collections.every(id => parent.getCollections().includes(id)), "original_collection_lost");
    for (const snap of baseline.children) {
        const item = await itemAt(parent.libraryID, snap.key);
        const data = copy(item.toJSON());
        if (trashed.includes(snap.key)) {
            needed(item.deleted, "trash_not_verified");
            delete data.version; delete data.dateModified; delete data.deleted;
            const old = JSON.parse(snap.data); delete old.version; delete old.dateModified; delete old.deleted;
            needed(JSON.stringify(data) === JSON.stringify(old), "protected_attachment_changed");
        } else needed(JSON.stringify(data) === snap.data, "protected_reading_content_changed");
        if (snap.hash) needed(fileHash(await item.getFilePathAsync()) === snap.hash, "protected_file_changed");
        if (snap.annotations !== undefined) needed(
            JSON.stringify(item.getAnnotations(true).map(a => a.toJSON())) === snap.annotations,
            "protected_annotations_changed");
    }
}

async function run() {
    const prefs = [];
    let parent = null, lib = null;
    let terminal = "failed";
    const beforeWrite = async () => {
        needed(JSON.stringify(await inventory()) === JSON.stringify(q.addons), "addon_inventory_changed");
        needed(store.active === q.attemptId && !Zotero.__paperDownloadBatches?.active, "batch_ownership_lost");
        for (const p of prefs) needed(!p.external && Zotero.Prefs.get(p.key, true) === false,
            "automatic_preference_changed");
        const current = await findParent(lib);
        needed((current?.key || null) === (parent?.key || null), "parent_state_changed");
        if (parent) needed(matchIdentity(parent), "parent_identity_mismatch");
    };
    try {
        lib = await library();
        needed(lib.editable && (!q.request.pdf || lib.filesEditable), "library_not_editable");
        parent = await findParent(lib);
        const baseline = await protect(parent);
        // Policy is resolved by the internal connection layer, with exact live versions.
        needed(JSON.stringify(await inventory()) === JSON.stringify(q.addons), "addon_inventory_changed");
        for (const key of q.preferenceKeys) {
            const original = Zotero.Prefs.get(key, true);
            needed(typeof original === "boolean", "automatic_preference_unknown");
            const p = {key, original, own: false, external: false, changed: false, observer: null};
            p.observer = Zotero.Prefs.registerObserver(key, () => { if (!p.own) p.external = true; }, true);
            prefs.push(p);
            needed(Zotero.Prefs.get(key, true) === original, "automatic_preference_changed");
            if (original) {
                p.changed = true; p.own = true;
                try { Zotero.Prefs.set(key, false, true); } finally { p.own = false; }
            }
        }
        await beforeWrite();
        if (q.kind === "archive") {
            if (!parent) {
                await beforeWrite();
                job.contentWritesStarted = true;
                const data = q.request.metadata || {};
                parent = new Zotero.Item(data.itemType || (q.request.identity.doi ? "journalArticle" : "document"));
                parent.libraryID = lib.libraryID;
                for (const [k,v] of Object.entries(data)) if (k !== "itemType") parent.setField(k,v);
                parent.setField("title", q.request.identity.title);
                if (q.request.identity.doi) parent.setField("DOI", q.request.identity.doi);
                if (q.request.identity.url) parent.setField("url", q.request.identity.url);
                if (q.request.identity.date) parent.setField("date", q.request.identity.date);
                if (q.request.identity.creators) parent.setCreators(q.request.identity.creators);
                await parent.saveTx(); job.savedKeys.push(parent.key);
            }
            job.parentKey = parent.key;
            job.libraryID = lib.libraryID;
            for (const wanted of q.request.collections) {
                let collection;
                if (wanted.key) {
                    collection = Zotero.Collections.getByLibraryAndKey(lib.libraryID, wanted.key);
                    needed(collection && !collection.deleted, "collection_not_found");
                } else {
                    let parentID = false;
                    for (const name of wanted.path) {
                        const siblings = Zotero.Collections.getByLibrary(lib.libraryID, true)
                            .filter(c => (c.parentID || false) === parentID && c.name === name && !c.deleted);
                        needed(siblings.length <= 1, "ambiguous_collection_path");
                        collection = siblings[0];
                        if (!collection) {
                            await beforeWrite(); job.contentWritesStarted = true; collection = new Zotero.Collection();
                            collection.libraryID = lib.libraryID; collection.name = name;
                            if (parentID) collection.parentID = parentID;
                            await collection.saveTx(); job.savedKeys.push(collection.key);
                        }
                        parentID = collection.id;
                    }
                }
                if (!parent.getCollections().includes(collection.id)) {
                    await beforeWrite(); job.contentWritesStarted = true; parent.addToCollection(collection.id); await parent.saveTx();
                }
                needed(parent.getCollections().includes(collection.id), "collection_readback_failed");
                job.collections.push(collection.key);
            }
            let pdf = q.request.pdf, selected = null;
            if (q.request.reuse_pdf) {
                selected = await itemAt(lib.libraryID, q.request.reuse_pdf.key);
                const file = await fileInfo(selected);
                needed(!selected.deleted && selected.parentID === parent.id
                    && file.sha256 === q.request.reuse_pdf.sha256, "reuse_pdf_mismatch");
            } else if (pdf) {
                needed(fileHash(pdf.path) === pdf.sha256, "source_file_changed");
                for (const id of parent.getAttachments()) {
                    const item = await Zotero.Items.getAsync(id); await item.loadAllData();
                    if (!item.deleted && item.attachmentContentType === "application/pdf") {
                        const path = await item.getFilePathAsync();
                        needed(path, "existing_pdf_state_unknown");
                        if (fileHash(path) === pdf.sha256) { selected = item; break; }
                    }
                }
                if (!selected) {
                    await beforeWrite(); needed(fileHash(pdf.path) === pdf.sha256, "source_file_changed");
                    job.contentWritesStarted = true;
                    selected = await Zotero.Attachments.importFromFile({file: pdf.path,
                        parentItemID: parent.id, contentType: "application/pdf", moveFile: false});
                    job.savedKeys.push(selected.key);
                }
            }
            if (selected) {
                const file = await fileInfo(selected);
                needed(selected.parentID === parent.id && !selected.deleted
                    && file.sha256 === (pdf || q.request.reuse_pdf).sha256, "attachment_readback_failed");
                job.attachment = file;
            }
            await confirmProtected(parent, baseline);
            job.preserved = true;
        } else {
            needed(parent, "parent_not_found"); job.parentKey = parent.key; job.libraryID = lib.libraryID;
            const keep = await itemAt(lib.libraryID, q.request.keep.key);
            const kept = await fileInfo(keep);
            needed(!keep.deleted && keep.parentID === parent.id && kept.sha256 === q.request.keep.sha256,
                "keep_attachment_mismatch");
            const trash = [];
            for (const candidate of q.request.candidates) {
                let item;
                try {
                    item = await itemAt(lib.libraryID, candidate.key);
                    const file = await fileInfo(item);
                    needed(item.parentID === parent.id && file.sha256 === candidate.sha256,
                        "candidate_attachment_mismatch");
                    if (item.deleted) { job.trashed.push(item.key); continue; }
                    needed(!file.annotations && !file.note && !parent.getNotes().length,
                        "candidate_has_reading_content");
                    const notes = new Zotero.Search(); notes.libraryID = lib.libraryID;
                    notes.addCondition("note", "contains", item.key);
                    needed(!(await notes.search()).length, "candidate_has_linked_notes");
                    needed(q.files[candidate.key]?.sha256 === file.sha256
                        && q.files[candidate.key].embedded_annotations === false, "candidate_pdf_inspection_unknown");
                    trash.push(item);
                } catch (e) { job.skipped.push({key: candidate.key, reason: e.publicCode || "candidate_state_unknown"}); }
            }
            await beforeWrite();
            // Recheck all target state inside the same native DB transaction, immediately before trash.
            await Zotero.DB.executeTransaction(async () => {
                await confirmProtected(parent, baseline);
                needed(fileHash(await keep.getFilePathAsync()) === kept.sha256, "keep_file_changed");
                for (const item of trash) {
                    const file = await fileInfo(item);
                    needed(!item.deleted && item.parentID === parent.id && !file.annotations && !file.note
                        && file.sha256 === q.files[item.key].sha256 && !parent.getNotes().length,
                        "candidate_state_changed");
                    const notes = new Zotero.Search(); notes.libraryID = lib.libraryID;
                    notes.addCondition("note", "contains", item.key);
                    needed(!(await notes.search()).length, "candidate_has_linked_notes");
                }
                await beforeWrite();
                if (trash.length) { job.contentWritesStarted = true; await Zotero.Items.trash(trash.map(i => i.id)); }
            });
            job.trashed.push(...trash.map(i => i.key));
            await confirmProtected(parent, baseline, job.trashed);
            needed(!keep.deleted && fileHash(await keep.getFilePathAsync()) === kept.sha256, "keep_readback_failed");
            job.preserved = true;
        }
        job.verified = true; terminal = "completed";
    } catch (e) { job.error = e.publicCode || "native_operation_failed"; }
    finally {
        for (const p of prefs.reverse()) {
            let recovery = "not_needed";
            try {
                if (p.external) recovery = "preserved_external_change";
                else if (p.changed) {
                    if (Zotero.Prefs.get(p.key, true) !== false) recovery = "pending";
                    else {
                        p.own = true;
                        try { Zotero.Prefs.set(p.key, p.original, true); } finally { p.own = false; }
                        recovery = Zotero.Prefs.get(p.key, true) === p.original ? "restored" : "pending";
                    }
                }
            } catch (e) { recovery = "pending"; }
            try { Zotero.Prefs.unregisterObserver(p.observer); } catch (e) { recovery = "pending"; }
            job.preferenceRecovery.push({key: p.key, recovery});
        }
        job.status = terminal; job.finishedAt = Date.now();
        if (store.active === q.attemptId) store.active = null;
    }
}
// Own the slot before the first await; client timeouts never terminate this task or restore settings.
run().catch(() => { job.status = "failed"; job.error = "native_task_failed"; });
return copy(job);
