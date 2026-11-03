// Independently implemented Local API protocol. Runs inside the existing batch guard.
// The authorization object is ephemeral and never copied into a job or receipt.
async function archiveAPI(lib, parent, beforeWrite, baseline) {
    const base = q.apiBase + '/api/';
    const prefix = q.request.library.type === 'user' ? 'users/0' : 'groups/' + q.request.library.id;
    const auth = q.apiAuthorization;
    if (typeof fetch !== 'function') ChromeUtils.importGlobalProperties(['fetch']);
    let consumed = false;
    job.backend = 'local_api'; job.apiStages = [];
    async function http(method, path, body, headers={}, stage=null, binary=false) {
        needed(q.databaseId === Zotero.Server.LocalAPI.getServerID(), 'database_identity_changed');
        if (method !== 'GET') await beforeWrite();
        const uploadBytes = path.startsWith('local/uploads/');
        if (method !== 'GET' && !uploadBytes && !auth.remember && consumed) {
            // A one-time grant is consumed once. Obtain the NEXT grant before the next
            // write, never replay a rejected/unknown write or change the database binding.
            let response;
            try { response = await fetch(base + 'local/authorize', {method:'POST',redirect:'error',
                headers:{'Content-Type':'application/json','Zotero-Server-ID':q.databaseId,
                    'Zotero-Allowed-Request':'true'},
                body:JSON.stringify({appName:'Zotero Workspace Library'})}); }
            catch (e) { stop('local_api_authorization_result_unknown'); }
            needed(response.headers.get('Zotero-Server-ID') === q.databaseId, 'database_identity_changed');
            needed(response.status === 200, 'local_api_authorization_denied');
            const next = await response.json();
            needed(typeof next.key === 'string' && typeof next.remember === 'boolean', 'invalid_authorization_response');
            auth.key = next.key; auth.remember = next.remember; consumed = false;
        }
        if (method !== 'GET') await beforeWrite();
        const options = {headers: {'Zotero-API-Version':'3', 'Zotero-Server-ID':q.databaseId,
            'Zotero-Allowed-Request':'true', ...headers}, method,redirect:'error'};
        if (method !== 'GET') {
            if (!uploadBytes) options.headers['Zotero-API-Key'] = auth.key;
            if (!binary && typeof body !== 'string') {
                options.headers['Content-Type'] = 'application/json'; body = JSON.stringify(body);
            }
            options.body = body; if (!uploadBytes) consumed = true; job.contentWritesStarted = true;
        }
        if (stage) { job.apiStages.push({stage, state:'dispatched'}); job.apiStage = stage; }
        let response;
        try { response = await fetch(base + path, options); }
        catch (e) { job.apiOutcomeUnknown = true; stop('local_api_result_unknown'); }
        needed(response.headers.get('Zotero-Server-ID') === q.databaseId, 'database_identity_changed');
        const codes = {401:'local_api_authorization_required',403:'local_api_access_denied',
            412:'local_api_version_conflict',428:'local_api_precondition_required'};
        needed(response.status >= 200 && response.status < 300,
            codes[response.status] || 'local_api_write_failed');
        if (stage) job.apiStages[job.apiStages.length-1].state = 'acknowledged';
        let text;
        try { text = await response.text(); }
        catch (e) { job.apiOutcomeUnknown = true; stop('local_api_result_unknown'); }
        if (!text) return null;
        try { return JSON.parse(text); }
        catch (e) { stop('invalid_local_api_response'); }
    }
    async function create(kind, data, stage) {
        const result = await http('POST', prefix + '/' + kind, [data], {}, stage);
        if (result?.failed?.['0']?.code === 412) stop('local_api_version_conflict');
        needed(result && !Object.keys(result.failed || {}).length &&
            (result.success?.['0'] === data.key || result.unchanged?.['0'] === data.key ||
             result.successful?.['0']?.key === data.key), 'local_api_object_write_failed');
        job.savedKeys.push(data.key);
    }
    if (!parent) {
        const prior = await Zotero.Items.getByLibraryAndKeyAsync(lib.libraryID, q.apiKeys.parent);
        needed(!prior, 'planned_key_collision');
        const ident = q.request.identity;
        const data = {itemType: ident.doi ? 'journalArticle' : 'document', ...q.request.metadata,
            key:q.apiKeys.parent, version:0, title:ident.title};
        for (const [src,dst] of [['doi','DOI'],['url','url'],['date','date'],['creators','creators']])
            if (ident[src]) data[dst] = ident[src];
        await create('items', data, 'create_parent');
        parent = await itemAt(lib.libraryID, data.key);
    }
    job.parentKey = parent.key; job.libraryID = lib.libraryID;
    for (const wanted of q.request.collections) {
        let collection;
        if (wanted.key) {
            collection = Zotero.Collections.getByLibraryAndKey(lib.libraryID, wanted.key);
            needed(collection && !collection.deleted, 'collection_not_found');
        } else {
            let parentID = false, parentKey = false;
            for (let i=0;i<wanted.path.length;i++) {
                const name = wanted.path[i];
                const siblings = Zotero.Collections.getByLibrary(lib.libraryID,true)
                    .filter(c => (c.parentID || false) === parentID && c.name === name && !c.deleted);
                needed(siblings.length <= 1, 'ambiguous_collection_path'); collection = siblings[0];
                if (!collection) {
                    const planned = q.apiKeys.collections.find(c =>
                        JSON.stringify(c.path) === JSON.stringify(wanted.path.slice(0,i+1)));
                    needed(planned, 'planned_collection_missing');
                    needed(!Zotero.Collections.getByLibraryAndKey(lib.libraryID,planned.key), 'planned_key_collision');
                    await create('collections', {key:planned.key,version:0,name,parentCollection:parentKey}, 'create_collection');
                    collection = Zotero.Collections.getByLibraryAndKey(lib.libraryID, planned.key);
                    needed(collection, 'collection_readback_failed');
                }
                parentID = collection.id; parentKey = collection.key;
            }
        }
        if (!parent.getCollections().includes(collection.id)) {
            const fresh = await http('GET', prefix + '/items/' + parent.key);
            const members = [...new Set([...(fresh.data.collections || []),collection.key])];
            await http('PATCH', prefix + '/items/' + parent.key, {collections:members},
                {'If-Unmodified-Since-Version':String(fresh.version)}, 'link_collection');
        }
        needed(parent.getCollections().includes(collection.id), 'collection_readback_failed');
        job.collections.push(collection.key);
    }
    let selected = null;
    const pdf = q.request.pdf;
    if (q.request.reuse_pdf) {
        selected = await itemAt(lib.libraryID, q.request.reuse_pdf.key);
        const info = await fileInfo(selected);
        needed(!selected.deleted && selected.parentID === parent.id &&
            info.sha256 === q.request.reuse_pdf.sha256, 'reuse_pdf_mismatch');
    } else if (pdf) {
        needed(fileHash(pdf.path) === pdf.sha256, 'source_file_changed');
        for (const id of parent.getAttachments()) {
            const item = await Zotero.Items.getAsync(id); await item.loadAllData();
            if (item.attachmentContentType !== 'application/pdf' || item.deleted) continue;
            const file = await item.getFilePathAsync();
            // Only this operation's durable, predetermined placeholder may be incomplete.
            if (!file && item.key === q.apiKeys.attachment && q.resumeAPI) { selected = item; continue; }
            needed(file, 'existing_pdf_state_unknown');
            if (fileHash(file) === pdf.sha256) { selected = item; break; }
        }
        if (!selected) {
            needed(!await Zotero.Items.getByLibraryAndKeyAsync(lib.libraryID,q.apiKeys.attachment), 'planned_key_collision');
            await create('items', {key:q.apiKeys.attachment,version:0,itemType:'attachment',
                parentItem:parent.key,linkMode:'imported_file',contentType:'application/pdf',
                filename:'document.pdf',title:'PDF'}, 'create_attachment');
            selected = await itemAt(lib.libraryID, q.apiKeys.attachment);
        }
        if (!await selected.getFilePathAsync()) {
            const info = await IOUtils.stat(pdf.path);
            const md5 = await Zotero.Utilities.Internal.md5Async(pdf.path);
            const form = new URLSearchParams({md5,filename:'document.pdf',filesize:String(info.size),
                mtime:String(info.lastModified),contentType:'application/pdf'}).toString();
            const headers = {'Content-Type':'application/x-www-form-urlencoded','If-None-Match':'*'};
            const upload = await http('POST', prefix + '/items/' + selected.key + '/file', form, headers, 'authorize_upload');
            if (!upload.exists) {
                // Upload grants are capabilities. Never put upload URLs/keys in jobs/receipts.
                const url = new URL(upload.url);
                needed(url.origin === new URL(q.apiBase).origin &&
                    /^\/api\/local\/uploads\/[a-zA-Z0-9]+$/.test(url.pathname) && !url.search && !url.hash,
                    'invalid_local_upload_target');
                needed(fileHash(pdf.path) === pdf.sha256, 'source_file_changed');
                const bytes = await IOUtils.read(pdf.path);
                await http('POST', url.pathname.slice(5), bytes,
                    {'Content-Type':'application/octet-stream'}, 'upload_bytes', true);
                await http('POST', prefix + '/items/' + selected.key + '/file',
                    new URLSearchParams({upload:upload.uploadKey}).toString(), headers, 'register_upload');
            }
        }
    }
    if (selected) {
        const info = await fileInfo(selected);
        needed(!selected.deleted && selected.parentID === parent.id &&
            info.sha256 === (pdf || q.request.reuse_pdf).sha256, 'attachment_readback_failed');
        job.attachment = info;
    }
    await confirmProtected(parent, baseline); job.preserved = true;
    return parent;
}
