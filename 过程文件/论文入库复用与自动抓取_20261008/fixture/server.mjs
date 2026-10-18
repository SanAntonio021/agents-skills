import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const CASES_DIR = path.join(ROOT, 'cases');
const INPUTS_DIR = path.join(ROOT, 'inputs');
const AUTO_KEY = 'zoteroscihub.automatic_pdf_download';
const PROCESS_ID = crypto.randomUUID();
const STARTED_AT = new Date().toISOString();
const PUBLICATION = {
  itemType: 'journalArticle',
  title: 'Zotero Fixture Study: Spectral Windows in a Simulated Link',
  DOI: '10.0000/zotero-fixture.target-001',
  date: '2026',
  publicationTitle: 'Fixture Journal (Simulated)',
  volume: '1', issue: '1', pages: '1-2',
  url: 'https://example.invalid/zotero-fixture/target-001',
  creators: [{ creatorType: 'author', firstName: 'Mira', lastName: 'Fixture' }],
};

const DEFINITIONS = [
  { suffix: 'existing_pdf_notes_collections', automatic: true, seeded: 'complete',
    facts: '父条目已有 PDF；另有笔记、PDF 批注和两个分类。自动下载设置为 true。' },
  { suffix: 'local_pdf_auto_on', automatic: true,
    facts: 'inputs 中有本地 PDF；资料库没有此论文的父条目或附件。自动下载设置为 true。' },
  { suffix: 'local_pdf_auto_off', automatic: false,
    facts: 'inputs 中有本地 PDF；资料库没有此论文的父条目或附件。自动下载设置为 false。' },
  { suffix: 'doi_generic_search_empty_title', automatic: true, seeded: 'doi-not-indexed', excludeDOIFromGenericSearch: true,
    facts: '父条目保留正确题名、DOI 和 PDF；此案例的 DOI 通用搜索为空，题名可命中。DOI 精确查询仍正常。案例 ID 沿用历史名称。' },
  { suffix: 'timeout_continues', automatic: true, saveDelayMs: 1400,
    facts: '资料库无目标父条目。每次 saveTx 在提交前延迟 1400 ms；客户端断开不取消 JS。' },
  { suffix: 'first_attachment_failure', automatic: true, failNextImport: true,
    facts: '资料库无目标父条目；下一次 importFromFile 抛出一次模拟异常，随后导入可执行。' },
  { suffix: 'manual_setting_change', automatic: true, saveDelayMs: 1400,
    facts: '资料库无目标父条目；saveTx 在提交前延迟 1400 ms。用户设置注入接口可独立调用。' },
  { suffix: 'restart_saved_partial', automatic: false, seeded: 'partial', restartCount: 1,
    facts: '模拟前一会话已把自动设置改为 false 并保存父条目；尚无 PDF。上下文已重启，前一会话的 JS 全局变量、观察器和任务均不存在。' },
];
const CASE_SPECS = ['download', 'search'].flatMap(executor =>
  DEFINITIONS.map(definition => ({ name: `${executor}__${definition.suffix}`, ...definition }))).concat([
  { name: 'search__local_material_handoff', automatic: true,
    facts: '本地索引提供模拟论文的 PDF 和 BibTeX 路径。资料库没有目标条目；自动设置为 true。' },
  { name: 'search__metadata_only', automatic: true,
    facts: '本地索引提供模拟论文题录和 DOI。资料库没有目标条目；自动设置为 true。' },
]);
const CASE_NAMES = CASE_SPECS.map(specification => specification.name);
const runtimes = new Map();

function insideRoot(candidate) {
  const resolved = path.resolve(candidate);
  const relative = path.relative(ROOT, resolved);
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error('Fixture paths must remain inside the fixture directory');
  }
  return resolved;
}
function caseDirectory(name) {
  if (!CASE_NAMES.includes(name)) throw Object.assign(new Error('Unknown case'), { statusCode: 404 });
  return insideRoot(path.join(CASES_DIR, name));
}
function hashFile(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
function copy(value) { return value === undefined ? undefined : structuredClone(value); }
function jsonSafe(value) {
  if (value === undefined) return null;
  const seen = new WeakSet();
  return JSON.parse(JSON.stringify(value, (_key, current) => {
    if (typeof current === 'bigint') return current.toString();
    if (typeof current === 'function') return '[function]';
    if (typeof current === 'symbol') return String(current);
    if (current instanceof Error) return { name: current.name, message: current.message };
    if (current && typeof current === 'object') {
      if (seen.has(current)) return '[circular]';
      seen.add(current);
    }
    return current;
  }));
}
function writeJSON(file, data) {
  insideRoot(file);
  const temporary = `${file}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  fs.renameSync(temporary, file);
}
function appendLog(name, action, details = {}) {
  const entry = { time: new Date().toISOString(), processInstance: PROCESS_ID, case: name, action, ...jsonSafe(details) };
  fs.appendFileSync(path.join(caseDirectory(name), 'operations.jsonl'), `${JSON.stringify(entry)}\n`, 'utf8');
  return entry;
}
function parseLogs(name) {
  const file = path.join(caseDirectory(name), 'operations.jsonl');
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8').split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line)) : [];
}
function makePDF() {
  const lines = [
    'SIMULATED PAPER - NOT A REAL PUBLICATION',
    PUBLICATION.title,
    `DOI: ${PUBLICATION.DOI}`,
    'Author: Mira Fixture. Fixture Journal (Simulated), 2026.',
    'This one-page PDF is an isolated Zotero test input.',
  ];
  const escapePDF = text => text.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
  const stream = `BT /F1 11 Tf 48 760 Td 16 TL ${lines.map((line, index) => `${index ? 'T* ' : ''}(${escapePDF(line)}) Tj`).join('\n')} ET\n`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(stream, 'ascii')} >>\nstream\n${stream}endstream`,
  ];
  let body = '%PDF-1.4\n';
  const offsets = [0];
  for (let i = 0; i < objects.length; i++) {
    offsets.push(Buffer.byteLength(body, 'ascii'));
    body += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`;
  }
  const xref = Buffer.byteLength(body, 'ascii');
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  body += offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('');
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body, 'ascii');
}
function baseItem(id, type, fields = {}, extra = {}) {
  return { id, key: `FX${String(id).padStart(6, '0')}`, libraryID: 1, itemType: type,
    fields: copy(fields), creators: [], collections: [], parentID: null,
    deleted: false, dateAdded: STARTED_AT, dateModified: STARTED_AT, ...extra };
}
function baseline(name, definition) {
  const state = {
    schemaVersion: 1, name, executor: name.split('__')[0], facts: definition.facts,
    settings: { [AUTO_KEY]: definition.automatic },
    libraries: [{ libraryID: 1, id: 1, libraryType: 'user', name: 'Isolated Fixture Library', editable: true, filesEditable: true }],
    collections: [
      { id: 20, key: 'FXCOL020', libraryID: 1, name: 'Fixture / Communications', parentID: null },
      { id: 21, key: 'FXCOL021', libraryID: 1, name: 'Fixture / Read and Annotated', parentID: null },
    ],
    items: [], nextItemID: 100,
    controls: { saveDelayMs: definition.saveDelayMs || 0, failNextImport: Boolean(definition.failNextImport),
      ...(definition.excludeDOIFromGenericSearch ? { excludeDOIFromGenericSearch: true } : {}) },
    restartCount: definition.restartCount || 0,
  };
  if (definition.seeded) {
    const { creators, itemType, ...fields } = PUBLICATION;
    state.items.push(baseItem(1, itemType, fields, { creators: copy(creators), collections: [20, 21] }));
    if (definition.seeded === 'complete' || definition.seeded === 'doi-not-indexed') {
      const target = path.join(caseDirectory(name), 'storage', '2', 'simulated_target.pdf');
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.copyFileSync(path.join(INPUTS_DIR, 'simulated_target.pdf'), target);
      state.items.push(baseItem(2, 'attachment', { title: 'Simulated target PDF' }, {
        parentID: 1, attachmentPath: target, attachmentContentType: 'application/pdf',
        attachmentLinkMode: 0, sha256: hashFile(target), sizeBytes: fs.statSync(target).size,
      }));
    }
    if (definition.seeded === 'complete') {
      state.items.push(baseItem(3, 'note', { title: 'Existing fixture reading note' }, {
        parentID: 1, note: '<p>Existing fixture note: preserve the recorded observation.</p>',
      }));
      state.items.push(baseItem(4, 'annotation', {}, {
        parentID: 2, annotationType: 'highlight', annotationText: 'This one-page PDF is an isolated Zotero test input.',
        annotationComment: 'Existing fixture annotation', annotationColor: '#ffd400',
        annotationPageLabel: '1', annotationSortIndex: '00000|000001|00000',
        annotationPosition: JSON.stringify({ pageIndex: 0, rects: [[48, 680, 300, 695]] }),
      }));
    }
  }
  return state;
}
function initialize() {
  fs.mkdirSync(INPUTS_DIR, { recursive: true });
  fs.mkdirSync(CASES_DIR, { recursive: true });
  const pdf = path.join(INPUTS_DIR, 'simulated_target.pdf');
  if (!fs.existsSync(pdf)) fs.writeFileSync(pdf, makePDF());
  const bib = path.join(INPUTS_DIR, 'simulated_target.bib');
  if (!fs.existsSync(bib)) fs.writeFileSync(bib, `@article{fixture_target_001,\n  title = {${PUBLICATION.title}},\n  author = {Fixture, Mira},\n  journal = {${PUBLICATION.publicationTitle}},\n  year = {2026},\n  volume = {1},\n  number = {1},\n  pages = {1--2},\n  doi = {${PUBLICATION.DOI}},\n  url = {${PUBLICATION.url}}\n}\n`, 'utf8');
  const indexFile = path.join(INPUTS_DIR, 'publication_index.json');
  if (!fs.existsSync(indexFile)) writeJSON(indexFile, {
    simulated: true,
    warning: 'All publication identities and source URLs in this fixture are simulated. No remote requests are made.',
    publications: [{ ...copy(PUBLICATION), localPDF: pdf, localBibTeX: bib, sha256: hashFile(pdf) }],
  });
  for (const definition of CASE_SPECS) {
      const name = definition.name;
      const directory = caseDirectory(name);
      fs.mkdirSync(directory, { recursive: true });
      const stateFile = path.join(directory, 'state.json');
      if (!fs.existsSync(stateFile)) {
        writeJSON(stateFile, baseline(name, definition));
        appendLog(name, 'fixture.seed', { facts: definition.facts, initialAutomatic: definition.automatic, simulated: true });
        if (definition.seeded === 'partial') {
          appendLog(name, 'fixture.seed.previousSession', {
            facts: '已持久化 Pref=false、父条目 id=1；模拟重启后不保留前一会话的任务或 JS 全局状态。',
            savedParentItemID: 1, savedAutomatic: false, restartCount: 1,
          });
        }
      }
  }
}

class RestartedError extends Error {
  constructor() { super('The simulated Zotero context was restarted'); this.name = 'ContextRestartedError'; }
}
class Runtime {
  constructor(name) {
    this.name = name;
    this.directory = caseDirectory(name);
    this.state = JSON.parse(fs.readFileSync(path.join(this.directory, 'state.json'), 'utf8'));
    this.contextID = crypto.randomUUID();
    this.createdAt = new Date().toISOString();
    this.live = true;
    this.observers = new Map();
    this.pendingDelays = new Map();
    this.nativeTimers = new Set();
    this.tasks = new Map();
    this.makeContext();
  }
  check() { if (!this.live) throw new RestartedError(); }
  log(action, details = {}) { return appendLog(this.name, action, { contextID: this.contextID, ...details }); }
  persist() { this.check(); writeJSON(path.join(this.directory, 'state.json'), this.state); }
  identity() {
    return { pid: process.pid, processInstance: PROCESS_ID, startedAt: STARTED_AT,
      case: this.name, contextID: this.contextID, contextCreatedAt: this.createdAt,
      restartCount: this.state.restartCount, liveTaskCount: [...this.tasks.values()].filter(task => task.status === 'running').length };
  }
  delay(ms) {
    this.check();
    return new Promise((resolve, reject) => {
      const handle = setTimeout(() => {
        this.pendingDelays.delete(handle);
        if (this.live) resolve(); else reject(new RestartedError());
      }, Math.max(0, Number(ms) || 0));
      this.pendingDelays.set(handle, reject);
    });
  }
  stop(reason) {
    this.log('runtime.restart.discard', { reason, activeTaskIDs: [...this.tasks.values()].filter(task => task.status === 'running').map(task => task.id), observerCount: this.observers.size });
    this.live = false;
    for (const [handle, reject] of this.pendingDelays) { clearTimeout(handle); reject(new RestartedError()); }
    this.pendingDelays.clear();
    for (const handle of this.nativeTimers) clearTimeout(handle);
    this.nativeTimers.clear();
    this.observers.clear();
    for (const task of this.tasks.values()) {
      if (task.status === 'running') task.resolveWait({ taskID: task.id, status: 'lost_on_restart', contextID: this.contextID });
    }
    this.tasks.clear();
  }
  getPref(key) {
    this.check(); this.log('native.pref.get', { key, value: this.state.settings[key] });
    return copy(this.state.settings[key]);
  }
  setPref(key, value, source = 'native') {
    this.check();
    const oldValue = this.state.settings[key];
    this.state.settings[key] = copy(value);
    this.persist();
    this.log(source === 'manual' ? 'manual.pref.set' : 'native.pref.set', { key, oldValue, value });
    if (!Object.is(oldValue, value)) {
      for (const [token, observer] of [...this.observers]) {
        if (observer.key !== key) continue;
        this.log('native.pref.observer.notify', { token, key, value, source });
        try {
          const result = typeof observer.callback === 'function'
            ? observer.callback(copy(value))
            : observer.callback.observe(null, 'nsPref:changed', key);
          if (result && typeof result.then === 'function') result.catch(error => this.log('native.pref.observer.error', { token, error }));
        } catch (error) { this.log('native.pref.observer.error', { token, error }); }
      }
    }
  }
  wrap(data) { return data ? new this.Item(copy(data)) : false; }
  lookup(id) { return this.state.items.find(item => item.id === Number(id)); }
  searchItems(query, filters = {}) {
    this.check();
    const normalized = String(query || '').toLowerCase();
    const result = this.state.items.filter(item => {
      if (filters.libraryID && item.libraryID !== Number(filters.libraryID)) return false;
      if (filters.itemType && item.itemType !== filters.itemType) return false;
      if (filters.topLevel && item.parentID !== null) return false;
      if (filters.DOI && String(item.fields.DOI || '').toLowerCase() !== String(filters.DOI).toLowerCase()) return false;
      if (filters.title && String(item.fields.title || '').toLowerCase() !== String(filters.title).toLowerCase()) return false;
      if (!normalized) return true;
      const fields = Object.entries(item.fields).filter(([field]) => !(this.state.controls.excludeDOIFromGenericSearch && field === 'DOI')).map(([, value]) => value);
      const searchable = [item.key, ...fields, item.note || '', ...(item.creators || []).flatMap(c => [c.firstName, c.lastName, c.name])].join(' ').toLowerCase();
      return searchable.includes(normalized);
    });
    return result.map(copy);
  }
  makeContext() {
    const runtime = this;
    this.Item = class Item {
      constructor(typeOrData = 'journalArticle') {
        runtime.check();
        this.data = typeof typeOrData === 'string' ? baseItem(null, typeOrData, {}, { key: null }) : copy(typeOrData);
      }
      get id() { return this.data.id; }
      get key() { return this.data.key; }
      get libraryID() { return this.data.libraryID; }
      set libraryID(value) { this.data.libraryID = Number(value); }
      get itemType() { return this.data.itemType; }
      get itemTypeID() { return this.data.itemType; }
      get parentID() { return this.data.parentID; }
      set parentID(value) { this.data.parentID = value === null || value === undefined ? null : Number(value); }
      get parentItemID() { return this.data.parentID; }
      set parentItemID(value) { this.parentID = value; }
      get parentKey() { return runtime.lookup(this.data.parentID)?.key || false; }
      get attachmentPath() { return this.data.attachmentPath || ''; }
      get attachmentContentType() { return this.data.attachmentContentType || ''; }
      get attachmentLinkMode() { return this.data.attachmentLinkMode ?? null; }
      setField(field, value) {
        runtime.check(); this.data.fields[field] = value;
        runtime.log('native.item.setField', { itemID: this.id, itemType: this.itemType, field, value });
        return true;
      }
      getField(field) {
        runtime.check(); const value = this.data.fields[field] ?? '';
        runtime.log('native.item.getField', { itemID: this.id, field, value }); return value;
      }
      setCreators(creators) { runtime.check(); this.data.creators = copy(creators); runtime.log('native.item.setCreators', { itemID: this.id, creators }); }
      getCreators() { runtime.check(); runtime.log('native.item.getCreators', { itemID: this.id }); return copy(this.data.creators); }
      setNote(note) { runtime.check(); this.data.note = String(note); runtime.log('native.item.setNote', { itemID: this.id, note }); }
      getNote() { runtime.check(); runtime.log('native.item.getNote', { itemID: this.id }); return this.data.note || ''; }
      isAttachment() { return this.itemType === 'attachment'; }
      isNote() { return this.itemType === 'note'; }
      isAnnotation() { return this.itemType === 'annotation'; }
      isRegularItem() { return !['attachment', 'note', 'annotation'].includes(this.itemType); }
      addToCollection(collectionID) {
        runtime.check(); const id = Number(collectionID);
        if (!runtime.state.collections.some(collection => collection.id === id)) throw new Error('Unknown fixture collection');
        if (!this.data.collections.includes(id)) this.data.collections.push(id);
        runtime.log('native.item.addToCollection', { itemID: this.id, collectionID: id });
      }
      getCollections() { runtime.check(); runtime.log('native.item.getCollections', { itemID: this.id, collections: this.data.collections }); return [...this.data.collections]; }
      getAttachments() {
        runtime.check(); const ids = runtime.state.items.filter(item => item.itemType === 'attachment' && item.parentID === this.id).map(item => item.id);
        runtime.log('native.item.getAttachments', { itemID: this.id, attachmentIDs: ids }); return ids;
      }
      getNotes() {
        runtime.check(); const ids = runtime.state.items.filter(item => item.itemType === 'note' && item.parentID === this.id).map(item => item.id);
        runtime.log('native.item.getNotes', { itemID: this.id, noteIDs: ids }); return ids;
      }
      getAnnotations() {
        runtime.check(); const items = runtime.state.items.filter(item => item.itemType === 'annotation' && item.parentID === this.id);
        runtime.log('native.item.getAnnotations', { itemID: this.id, annotationIDs: items.map(item => item.id) }); return items.map(item => runtime.wrap(item));
      }
      async getFilePathAsync() { runtime.check(); runtime.log('native.attachment.getFilePathAsync', { itemID: this.id, file: this.attachmentPath }); return this.attachmentPath || false; }
      async saveTx(options = {}) {
        runtime.check(); runtime.log('native.item.save.start', { itemID: this.id, itemType: this.itemType, delayMs: runtime.state.controls.saveDelayMs, options });
        if (runtime.state.controls.saveDelayMs) await runtime.delay(runtime.state.controls.saveDelayMs);
        runtime.check();
        const isNew = this.data.id === null || this.data.id === undefined;
        if (isNew) {
          this.data.id = runtime.state.nextItemID++;
          this.data.key = `FX${String(this.data.id).padStart(6, '0')}`;
          this.data.dateAdded = new Date().toISOString();
        }
        if (!runtime.state.libraries.some(library => library.libraryID === this.data.libraryID)) throw new Error('Unknown fixture library');
        if (this.data.parentID !== null && !runtime.lookup(this.data.parentID)) throw new Error('Parent item must already exist in this case');
        this.data.dateModified = new Date().toISOString();
        const index = runtime.state.items.findIndex(item => item.id === this.id);
        if (index < 0) runtime.state.items.push(copy(this.data)); else runtime.state.items[index] = copy(this.data);
        runtime.persist();
        runtime.log('native.item.save.committed', { itemID: this.id, isNew, item: this.data });
        if (isNew && this.isRegularItem() && runtime.state.settings[AUTO_KEY] === true) {
          runtime.log('scihub.simulated.fetch_popup', { itemID: this.id, DOI: this.data.fields.DOI || '', automatic: true, simulatedFetch: true, simulatedPopup: true, networkRequestMade: false });
        }
        return this.id;
      }
      toJSON() { runtime.check(); runtime.log('native.item.toJSON', { itemID: this.id }); return copy(this.data); }
    };
    for (const field of ['annotationType', 'annotationText', 'annotationComment', 'annotationColor', 'annotationPageLabel', 'annotationSortIndex', 'annotationPosition']) {
      Object.defineProperty(this.Item.prototype, field, {
        get() { return this.data[field] || ''; }, set(value) { this.data[field] = value; },
      });
    }
    const Zotero = {
      Scihub: { installed: true },
      Prefs: {
        get: key => runtime.getPref(key),
        set: (key, value) => runtime.setPref(key, value),
        registerObserver: (key, callback) => {
          runtime.check();
          if (typeof callback !== 'function' && typeof callback?.observe !== 'function') throw new TypeError('Observer must be a function or an object with observe()');
          const token = `observer-${crypto.randomUUID()}`;
          runtime.observers.set(token, { key, callback });
          runtime.log('native.pref.registerObserver', { key, token }); return token;
        },
        unregisterObserver: token => { runtime.check(); const removed = runtime.observers.delete(token); runtime.log('native.pref.unregisterObserver', { token, removed }); },
      },
      Item: this.Item,
      Items: {
        getAsync: async ids => {
          runtime.check(); const values = Array.isArray(ids) ? ids : [ids];
          runtime.log('native.items.getAsync', { itemIDs: values });
          const items = values.map(id => runtime.wrap(runtime.lookup(id)));
          return Array.isArray(ids) ? items : items[0];
        },
        get: ids => {
          runtime.check(); const values = Array.isArray(ids) ? ids : [ids];
          runtime.log('native.items.get', { itemIDs: values });
          const items = values.map(id => runtime.wrap(runtime.lookup(id)));
          return Array.isArray(ids) ? items : items[0];
        },
        getAll: async (libraryID = 1, onlyTopLevel = false, includeDeleted = false, asIDs = false) => {
          runtime.check();
          const items = runtime.state.items.filter(item => item.libraryID === Number(libraryID) && (!onlyTopLevel || item.parentID === null) && (includeDeleted || !item.deleted));
          runtime.log('native.items.getAll', { libraryID, onlyTopLevel, includeDeleted, asIDs, itemIDs: items.map(item => item.id) });
          return asIDs ? items.map(item => item.id) : items.map(item => runtime.wrap(item));
        },
        getByLibraryAndKeyAsync: async (libraryID, key) => {
          runtime.check(); runtime.log('native.items.getByLibraryAndKeyAsync', { libraryID, key });
          return runtime.wrap(runtime.state.items.find(item => item.libraryID === Number(libraryID) && item.key === key));
        },
      },
      Attachments: {
        LINK_MODE_IMPORTED_FILE: 0,
        importFromFile: async options => {
          runtime.check();
          const sourceInput = typeof options?.file === 'string' ? options.file : options?.file?.path;
          if (!sourceInput) throw new Error('importFromFile requires a fixture file path');
          const source = insideRoot(path.isAbsolute(sourceInput) ? sourceInput : path.join(ROOT, sourceInput));
          runtime.log('native.attachment.import.start', { source, parentItemID: options.parentItemID ?? null });
          if (runtime.state.controls.failNextImport) {
            runtime.state.controls.failNextImport = false;
            runtime.persist();
            runtime.log('native.attachment.import.failure', { source, injected: true });
            const error = new Error('Injected one-time fixture attachment import failure'); error.name = 'FixtureAttachmentImportError'; throw error;
          }
          const parentID = options.parentItemID === null || options.parentItemID === undefined ? null : Number(options.parentItemID);
          if (parentID !== null && !runtime.lookup(parentID)) throw new Error('Parent item must already exist in this case');
          if (!fs.statSync(source).isFile()) throw new Error('Attachment source is not a file');
          const id = runtime.state.nextItemID++;
          const destination = insideRoot(path.join(runtime.directory, 'storage', String(id), path.basename(source)));
          fs.mkdirSync(path.dirname(destination), { recursive: true });
          fs.copyFileSync(source, destination);
          const item = baseItem(id, 'attachment', { title: options.title || path.basename(source) }, {
            libraryID: options.libraryID || runtime.lookup(parentID)?.libraryID || 1, parentID,
            attachmentPath: destination, attachmentContentType: options.contentType || 'application/pdf',
            attachmentLinkMode: 0, sha256: hashFile(destination), sizeBytes: fs.statSync(destination).size,
          });
          runtime.state.items.push(item);
          runtime.persist();
          runtime.log('native.attachment.import.committed', { attachmentID: id, parentItemID: parentID, source, destination, sha256: item.sha256, sizeBytes: item.sizeBytes });
          return runtime.wrap(item);
        },
      },
      Libraries: {
        userLibraryID: 1,
        getAll: () => { runtime.check(); runtime.log('native.libraries.getAll'); return copy(runtime.state.libraries); },
        get: id => { runtime.check(); runtime.log('native.libraries.get', { libraryID: id }); return copy(runtime.state.libraries.find(library => library.libraryID === Number(id))) || false; },
      },
      Collections: {
        get: id => { runtime.check(); runtime.log('native.collections.get', { collectionID: id }); return copy(runtime.state.collections.find(collection => collection.id === Number(id))) || false; },
        getAsync: async id => { runtime.check(); runtime.log('native.collections.getAsync', { collectionID: id }); return copy(runtime.state.collections.find(collection => collection.id === Number(id))) || false; },
        getByLibrary: libraryID => { runtime.check(); runtime.log('native.collections.getByLibrary', { libraryID }); return copy(runtime.state.collections.filter(collection => collection.libraryID === Number(libraryID))); },
      },
      Search: class Search {
        constructor() { this.libraryID = 1; this.conditions = []; }
        addCondition(field, operator, value) { runtime.check(); this.conditions.push({ field, operator, value }); runtime.log('native.search.addCondition', { field, operator, value }); }
        async search() {
          runtime.check();
          let items = runtime.state.items.filter(item => item.libraryID === Number(this.libraryID));
          for (const condition of this.conditions) {
            if (condition.field === 'joinMode') continue;
            const matches = item => {
              const fields = Object.entries(item.fields).filter(([field]) => !(runtime.state.controls.excludeDOIFromGenericSearch && field === 'DOI')).map(([, value]) => value);
              const actual = condition.field === 'quicksearch-everything'
                ? [item.key, ...fields, ...(item.creators || []).flatMap(c => [c.firstName, c.lastName, c.name])].join(' ')
                : condition.field === 'itemType' ? item.itemType : item.fields[condition.field] || '';
              const left = String(actual).toLowerCase(), right = String(condition.value).toLowerCase();
              if (condition.operator === 'contains') return left.includes(right);
              if (condition.operator === 'is') return left === right;
              if (condition.operator === 'isNot') return left !== right;
              throw new Error(`Unsupported fixture Search operator: ${condition.operator}`);
            };
            items = items.filter(matches);
          }
          const ids = items.map(item => item.id);
          runtime.log('native.search.search', { libraryID: this.libraryID, conditions: this.conditions, itemIDs: ids }); return ids;
        }
      },
      Promise: { delay: ms => { runtime.log('native.promise.delay', { ms }); return runtime.delay(ms); } },
      debug: message => runtime.log('native.debug', { message }),
      logError: error => runtime.log('native.logError', { error }),
    };
    const sandbox = {
      Zotero,
      console: Object.fromEntries(['log', 'warn', 'error', 'info', 'debug'].map(level => [level, (...args) => runtime.log(`js.console.${level}`, { args })])),
      setTimeout: (callback, ms, ...args) => {
        runtime.check();
        const handle = setTimeout(() => {
          runtime.nativeTimers.delete(handle);
          if (!runtime.live) return;
          try { callback(...args); } catch (error) { runtime.log('js.timer.error', { error }); }
        }, Math.max(0, Number(ms) || 0));
        runtime.nativeTimers.add(handle); return handle;
      },
      clearTimeout: handle => { clearTimeout(handle); runtime.nativeTimers.delete(handle); },
    };
    this.context = vm.createContext(sandbox, { name: `Fixture Zotero: ${this.name}` });
  }
  startTask(code, mode = 'async') {
    this.check();
    if (typeof code !== 'string' || !code.trim()) throw new Error('JS code is required');
    if (!['async', 'script'].includes(mode)) throw new Error('mode must be async or script');
    const id = crypto.randomUUID();
    let resolveWait;
    const completion = new Promise(resolve => { resolveWait = resolve; });
    const task = { id, status: 'running', mode, code, startedAt: new Date().toISOString(), contextID: this.contextID, completion, resolveWait };
    this.tasks.set(id, task);
    this.log('js.task.start', { taskID: id, mode, code });
    let running;
    try {
      const source = mode === 'async' ? `(async function fixtureTask(){\n${code}\n}).call(globalThis)` : code;
      running = new vm.Script(source, { filename: `${this.name}/${id}.js` }).runInContext(this.context);
    } catch (error) { running = Promise.reject(error); }
    Promise.resolve(running).then(result => {
      if (!this.live) return;
      task.status = 'completed'; task.result = jsonSafe(result); task.finishedAt = new Date().toISOString();
      this.log('js.task.complete', { taskID: id, result: task.result });
      resolveWait(this.taskSnapshot(task));
    }, error => {
      if (!this.live) return;
      task.status = 'failed'; task.error = { name: error.name || 'Error', message: error.message || String(error) }; task.finishedAt = new Date().toISOString();
      this.log('js.task.failed', { taskID: id, error: task.error });
      resolveWait(this.taskSnapshot(task));
    });
    return task;
  }
  taskSnapshot(task) {
    return { taskID: task.id, status: task.status, mode: task.mode, contextID: task.contextID,
      startedAt: task.startedAt, finishedAt: task.finishedAt || null,
      ...(task.status === 'completed' ? { result: task.result } : {}),
      ...(task.status === 'failed' ? { error: task.error } : {}) };
  }
}
function getRuntime(name) {
  caseDirectory(name);
  if (!runtimes.has(name)) runtimes.set(name, new Runtime(name));
  return runtimes.get(name);
}
async function readBody(request) {
  let body = '';
  for await (const chunk of request) {
    body += chunk.toString('utf8');
    if (Buffer.byteLength(body, 'utf8') > 2_000_000) throw new Error('Request body exceeds fixture limit');
  }
  return body ? JSON.parse(body) : {};
}
function sendJSON(response, status, data) {
  if (response.destroyed || response.writableEnded) return;
  response.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  response.end(`${JSON.stringify(jsonSafe(data))}\n`);
}
function publicationSearch(query) {
  const index = JSON.parse(fs.readFileSync(path.join(INPUTS_DIR, 'publication_index.json'), 'utf8'));
  const normalized = String(query || '').toLowerCase();
  return index.publications.filter(publication => !normalized || [publication.title, publication.DOI, publication.publicationTitle, ...publication.creators.flatMap(c => [c.firstName, c.lastName])].join(' ').toLowerCase().includes(normalized));
}
async function route(request, response) {
  const url = new URL(request.url, 'http://127.0.0.1');
  const segments = url.pathname.split('/').filter(Boolean).map(decodeURIComponent);
  const method = request.method;
  if (method === 'GET' && segments.join('/') === 'health') {
    return sendJSON(response, 200, { service: 'isolated-zotero-fixture', pid: process.pid, processInstance: PROCESS_ID, startedAt: STARTED_AT, root: ROOT, automaticSettingKey: AUTO_KEY, networkFetching: false });
  }
  if (method === 'GET' && segments.join('/') === 'cases') {
    return sendJSON(response, 200, CASE_NAMES.map(name => {
      const state = JSON.parse(fs.readFileSync(path.join(caseDirectory(name), 'state.json'), 'utf8'));
      appendLog(name, 'http.read.caseListing');
      return { name, executor: state.executor, facts: state.facts };
    }));
  }
  if (segments[0] !== 'cases' || !segments[1]) throw Object.assign(new Error('Unknown endpoint'), { statusCode: 404 });
  const name = segments[1], runtime = getRuntime(name), sub = segments.slice(2);
  runtime.log('http.request', { method, path: url.pathname, query: Object.fromEntries(url.searchParams) });
  if (method === 'GET' && sub.length === 0) return sendJSON(response, 200, {
    name, facts: runtime.state.facts, process: runtime.identity(), controls: runtime.state.controls,
    automaticSettingKey: AUTO_KEY, inputs: publicationSearch(''),
  });
  if (method === 'GET' && sub[0] === 'process' && sub.length === 1) return sendJSON(response, 200, runtime.identity());
  if (method === 'GET' && sub[0] === 'libraries') return sendJSON(response, 200, runtime.state.libraries);
  if (method === 'GET' && sub[0] === 'collections') return sendJSON(response, 200, runtime.state.collections);
  if (method === 'GET' && sub[0] === 'settings') {
    return sendJSON(response, 200, sub.length === 1 ? runtime.state.settings : { key: sub[1], value: runtime.state.settings[sub[1]] ?? null, exists: Object.hasOwn(runtime.state.settings, sub[1]) });
  }
  if (method === 'GET' && sub[0] === 'items' && sub.length === 1) {
    const query = url.searchParams.get('q') ?? url.searchParams.get('search') ?? '';
    const filters = {
      libraryID: url.searchParams.get('libraryID'), itemType: url.searchParams.get('itemType'),
      DOI: url.searchParams.get('doi'), title: url.searchParams.get('title'),
      topLevel: url.searchParams.get('topLevel') === 'true',
    };
    const items = runtime.searchItems(query, filters);
    runtime.log('http.read.items', { query, filters, itemIDs: items.map(item => item.id) });
    return sendJSON(response, 200, items);
  }
  if (method === 'GET' && sub[0] === 'items' && sub.length >= 2) {
    const item = runtime.lookup(sub[1]);
    if (!item) throw Object.assign(new Error('Item not found in this case'), { statusCode: 404 });
    if (sub.length === 2) return sendJSON(response, 200, item);
    const type = { attachments: 'attachment', notes: 'note', annotations: 'annotation' }[sub[2]];
    if (type) return sendJSON(response, 200, runtime.state.items.filter(child => child.parentID === item.id && child.itemType === type));
  }
  if (method === 'GET' && sub[0] === 'attachments' && sub.length === 3 && sub[2] === 'file') {
    const item = runtime.lookup(sub[1]);
    if (!item || item.itemType !== 'attachment' || !item.attachmentPath) throw Object.assign(new Error('Attachment file not found'), { statusCode: 404 });
    const file = insideRoot(item.attachmentPath);
    runtime.log('http.read.attachmentFile', { attachmentID: item.id, file, sha256: hashFile(file) });
    response.writeHead(200, { 'Content-Type': item.attachmentContentType || 'application/octet-stream', 'Content-Length': fs.statSync(file).size });
    fs.createReadStream(file).pipe(response); return;
  }
  if (method === 'GET' && sub[0] === 'search') {
    const query = url.searchParams.get('q') || '';
    const result = publicationSearch(query);
    runtime.log('http.read.publicationIndex', { query, DOIResults: result.map(publication => publication.DOI) });
    return sendJSON(response, 200, { simulated: true, results: result });
  }
  if (method === 'GET' && sub[0] === 'logs') return sendJSON(response, 200, parseLogs(name));
  if (method === 'GET' && sub[0] === 'tasks' && sub.length === 1) return sendJSON(response, 200, [...runtime.tasks.values()].map(task => runtime.taskSnapshot(task)));
  if (method === 'GET' && sub[0] === 'tasks' && sub.length === 2) {
    const task = runtime.tasks.get(sub[1]);
    if (!task) throw Object.assign(new Error('Task is absent from this live context; simulated restart discards volatile task state'), { statusCode: 404 });
    return sendJSON(response, 200, runtime.taskSnapshot(task));
  }
  if (method === 'POST' && sub[0] === 'js' && sub.length === 1) {
    const body = await readBody(request);
    const task = runtime.startTask(body.code, body.mode || 'async');
    let timer;
    const waitMs = body.waitMs === undefined ? 30000 : Math.max(0, Math.min(60000, Number(body.waitMs) || 0));
    response.on('close', () => {
      if (!response.writableEnded) runtime.log('http.client.disconnected', { taskID: task.id, jsCancelled: false });
    });
    const snapshot = await Promise.race([
      task.completion,
      new Promise(resolve => { timer = setTimeout(() => resolve(runtime.taskSnapshot(task)), waitMs); }),
    ]);
    clearTimeout(timer);
    return sendJSON(response, snapshot.status === 'running' ? 202 : 200, snapshot);
  }
  if (method === 'POST' && sub[0] === 'inject' && sub[1] === 'manual-setting') {
    const body = await readBody(request);
    const key = body.key || AUTO_KEY;
    if (!Object.hasOwn(body, 'value')) throw new Error('value is required');
    runtime.setPref(key, body.value, 'manual');
    return sendJSON(response, 200, { key, value: runtime.state.settings[key], source: 'manual', process: runtime.identity() });
  }
  if (method === 'POST' && sub[0] === 'inject' && sub[1] === 'attachment-failure') {
    await readBody(request);
    runtime.state.controls.failNextImport = true; runtime.persist();
    runtime.log('manual.inject.nextAttachmentFailure', { remainingFailures: 1 });
    return sendJSON(response, 200, { nextImportWillFailOnce: true });
  }
  if (method === 'POST' && sub[0] === 'restart' && sub.length === 1) {
    await readBody(request);
    const oldIdentity = runtime.identity();
    runtime.state.restartCount++; runtime.persist();
    runtime.stop('HTTP simulated restart');
    const replacement = new Runtime(name);
    runtimes.set(name, replacement);
    replacement.log('runtime.restart.ready', { previousContextID: oldIdentity.contextID, preservedItemCount: replacement.state.items.length, preservedSettings: replacement.state.settings });
    return sendJSON(response, 200, { previous: oldIdentity, current: replacement.identity() });
  }
  throw Object.assign(new Error('Unknown endpoint'), { statusCode: 404 });
}
function selfcheck() {
  const pdf = path.join(INPUTS_DIR, 'simulated_target.pdf');
  const bytes = fs.readFileSync(pdf);
  if (!bytes.subarray(0, 8).equals(Buffer.from('%PDF-1.4')) || !bytes.toString('ascii').trimEnd().endsWith('%%EOF')) throw new Error('Fixture PDF markers are invalid');
  const bib = fs.readFileSync(path.join(INPUTS_DIR, 'simulated_target.bib'), 'utf8');
  const index = JSON.parse(fs.readFileSync(path.join(INPUTS_DIR, 'publication_index.json'), 'utf8'));
  if (!bib.includes(PUBLICATION.DOI) || index.publications[0].DOI !== PUBLICATION.DOI) throw new Error('Input publication identities differ');
  for (const name of CASE_NAMES) {
    const state = JSON.parse(fs.readFileSync(path.join(caseDirectory(name), 'state.json'), 'utf8'));
    if (state.name !== name || typeof state.settings[AUTO_KEY] !== 'boolean') throw new Error(`Invalid case ${name}`);
    const ids = new Set(state.items.map(item => item.id));
    if (ids.size !== state.items.length) throw new Error(`Repeated IDs in case ${name}`);
    for (const item of state.items) {
      if (item.parentID !== null && !ids.has(item.parentID)) throw new Error(`Missing parent in case ${name}`);
      if (item.attachmentPath) {
        insideRoot(item.attachmentPath);
        if (hashFile(item.attachmentPath) !== item.sha256) throw new Error(`Attachment hash differs in case ${name}`);
      }
    }
    parseLogs(name);
  }
  return { staticChecks: 'passed', cases: CASE_NAMES.length, pdfBytes: bytes.length, pdfSHA256: hashFile(pdf), publicationDOI: PUBLICATION.DOI, serviceStarted: false };
}

initialize();
if (process.argv.includes('--init')) {
  console.log(JSON.stringify({ initialized: true, root: ROOT, cases: CASE_NAMES, automaticSettingKey: AUTO_KEY }, null, 2));
} else if (process.argv.includes('--selfcheck')) {
  console.log(JSON.stringify(selfcheck(), null, 2));
} else {
  const position = process.argv.indexOf('--port');
  const port = position >= 0 ? Number(process.argv[position + 1]) : 0;
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('--port must be an integer from 0 to 65535');
  const server = http.createServer((request, response) => {
    route(request, response).catch(error => sendJSON(response, error.statusCode || 400, { error: { name: error.name, message: error.message } }));
  });
  server.listen(port, '127.0.0.1', () => {
    const address = server.address();
    console.log(JSON.stringify({ url: `http://127.0.0.1:${address.port}`, pid: process.pid, processInstance: PROCESS_ID, root: ROOT, cases: CASE_NAMES.length }));
  });
  server.on('error', error => { console.error(error.message); process.exitCode = 1; });
  const shutdown = signal => {
    console.log(JSON.stringify({ stopping: true, signal, pid: process.pid, processInstance: PROCESS_ID }));
    for (const runtime of runtimes.values()) runtime.stop(`Server ${signal}`);
    server.close(() => process.exit(0));
    server.closeAllConnections();
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}
