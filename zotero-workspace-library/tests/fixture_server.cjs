// Isolated model of native Zotero APIs. Executes the shipped native.js via Debug Bridge.
// This is contract testing, not evidence of a real Zotero write or third-party plugin audit.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const http = require('node:http');
const {pathToFileURL} = require('node:url');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const root = process.argv[2]; fs.mkdirSync(root, {recursive:true});
const items = new Map(), collections = new Map(), events = [];
let nextID=0, nextObserver=0, epoch=1, inTransaction=false;
let config = {delay:0, failImport:0, auth:201, replyDelay:0, external:false, noImport:false,
  addonsOnStart:null, databaseId:'isolated-database', authorizationStatus:200, noLocalAPI:false};
const grants = new Map(), uploads = new Map();
let addons = [{id:'debug-bridge@iris-advies.com',version:'3.0.1',isActive:true}];
const prefs = new Map([['extensions.fixture.auto',true]]), observers = new Map();
let browserTaskState = 'active';
const key = id => 'T' + String(id).padStart(7,'0');
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const sleep = ms => new Promise(r=>setTimeout(r,ms));
class Item {
  constructor(type='document') { this.itemType=type; this.libraryID=1; this.fields={};
    this.creators=[]; this.collections=[]; this.deleted=false; this.tags=[]; this.note=''; }
  get parentKey() { return items.get(this.parentID)?.key || false; }
  async loadAllData() {}
  setField(k,v) { this.fields[k]=v; }
  getField(k) { return this.fields[k] || ''; }
  setCreators(v) { this.creators=JSON.parse(JSON.stringify(v)); }
  getCreatorsJSON() { return this.creators; }
  getCollections() { return [...this.collections]; }
  addToCollection(id) { if(!this.collections.includes(id)) this.collections.push(id); }
  isAttachment() { return this.itemType==='attachment'; }
  isFileAttachment() { return this.isAttachment() && this.attachmentLinkMode!==3; }
  isRegularItem() { return !['attachment','annotation','note'].includes(this.itemType); }
  getAttachments(trashed=false) { return [...items.values()].filter(i=>i.parentID===this.id && i.isAttachment() && (trashed||!i.deleted)).map(i=>i.id); }
  getNotes(trashed=false) { return [...items.values()].filter(i=>i.parentID===this.id && i.itemType==='note' && (trashed||!i.deleted)).map(i=>i.id); }
  getAnnotations(trashed=false) {
    if(!this.isFileAttachment()) throw new Error('annotations require file attachment');
    return [...items.values()].filter(i=>i.parentID===this.id && i.itemType==='annotation' && (trashed||!i.deleted));
  }
  getNote() { return this.note; }
  async getFilePathAsync() { return this.file || false; }
  async saveTx() {
    if(inTransaction) throw new Error('nested transaction');
    if(config.delay) await sleep(config.delay);
    if(!this.id) { this.id=++nextID; this.key=this.key||key(this.id); }
    this.version=(this.version||0)+1;
    items.set(this.id,this); events.push({event:'save',key:this.key,type:this.itemType});
    if(config.external) { config.external=false; Zotero.Prefs.set('extensions.fixture.auto',true); }
    return this.id;
  }
  toJSON() {
    const data={key:this.key,version:this.version,itemType:this.itemType,...this.fields,creators:this.creators,
      collections:this.collections.map(id=>collections.get(id).key),tags:this.tags};
    if(this.parentID) data.parentItem=this.parentKey;
    if(this.isAttachment()) { data.contentType=this.attachmentContentType; data.linkMode='imported_file'; }
    if(this.note) data.note=this.note;
    if(this.deleted) data.deleted=1;
    return data;
  }
}
class Collection {
  constructor() { this.libraryID=1; this.parentID=false; }
  async saveTx() { this.id=++nextID; this.key=this.key||key(this.id); collections.set(this.id,this);
    events.push({event:'collection',key:this.key,name:this.name}); return this.id; }
  toJSON() { return {key:this.key,name:this.name,parentCollection:collections.get(this.parentID)?.key || false}; }
}
class Search {
  constructor() { this.conditions=[]; }
  addCondition(...v) { this.conditions.push(v); }
  async search() { return [...items.values()].filter(i=> i.libraryID===this.libraryID &&
    this.conditions.every(([field,op,value])=> {
      const actual=field==='note'?i.note:i.getField(field);
      return op==='contains'?actual.toLowerCase().includes(value.toLowerCase()):actual.toLowerCase()===value.toLowerCase();
    })).map(i=>i.id); }
}
async function importFromFile({file,parentItemID,moveFile}) {
  if(moveFile!==false) throw new Error('source must be copied');
  if(config.failImport>0) { config.failImport--; throw new Error('isolated import failure'); }
  const item=new Item('attachment'); item.parentID=parentItemID; item.attachmentContentType='application/pdf';
  await item.saveTx(); item.file=path.join(root,item.key+'.pdf'); fs.copyFileSync(file,item.file);
  events.push({event:'import',key:item.key,sha256:hash(item.file)}); return item;
}
const Zotero = {
  version:'10.0.7', Item, Collection, Search,
  Server:{LocalAPI:{getServerID:()=>config.databaseId}},
  Utilities:{Internal:{md5Async:async p=>crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex')}},
  Libraries:{userLibraryID:1,get:id=>id===1?{libraryID:1,editable:true,filesEditable:true}:null},
  Groups:{getLibraryIDFromGroupID:id=>id===100?1:null},
  Items:{getAsync:async id=>items.get(id),get:ids=>ids.map(id=>items.get(id)),
    getByLibraryAndKeyAsync:async (lib,k)=>[...items.values()].find(i=>i.libraryID===lib&&i.key===k),
    async trash(ids) { if(!inTransaction) throw new Error('transaction required');
      for(const id of ids) { items.get(id).deleted=true; events.push({event:'trash',key:items.get(id).key}); } },
    async trashTx(ids) { return Zotero.DB.executeTransaction(()=>Zotero.Items.trash(ids)); }},
  Collections:{getByLibrary:id=>[...collections.values()].filter(c=>c.libraryID===id),
    getByLibraryAndKey:(id,k)=>[...collections.values()].find(c=>c.libraryID===id&&c.key===k)},
  Attachments:{importFromFile,LINK_MODE_LINKED_URL:3},
  DB:{async executeTransaction(fn) { if(inTransaction) throw new Error('nested transaction');
    inTransaction=true; try { return await fn(); } finally { inTransaction=false; } }},
  File:{pathToFile:p=>({path:p,exists:()=>fs.existsSync(p),isFile:()=>fs.statSync(p).isFile(),get fileSize(){return fs.statSync(p).size;}})},
  Prefs:{get:k=>prefs.get(k),set(k,v) { prefs.set(k,v); events.push({event:'pref',key:k,value:v});
      for(const o of observers.values()) if(o.key===k) o.fn(); },
    registerObserver(k,fn){const id=++nextObserver;observers.set(id,{key:k,fn});return id;},
    unregisterObserver:id=>observers.delete(id)}
};
const Services={appinfo:{processID:99999},startup:{getStartupInfo:()=>({process:new Date(epoch)})}};
const ChromeUtils={importESModule:()=>({AddonManager:{getAddonsByTypes:async()=>addons}}),importGlobalProperties:()=>{}};
const IOUtils={stat:async p=>({size:fs.statSync(p).size,lastModified:fs.statSync(p).mtimeMs}),
  read:async p=>new Uint8Array(fs.readFileSync(p))};
const Components={interfaces:{},classes:{
  '@mozilla.org/network/file-input-stream;1':{createInstance:()=>({init(f){this.file=f.path;},close(){}})},
  '@mozilla.org/security/hash;1':{createInstance:()=>({SHA256:1,init(){},updateFromStream(s){this.data=fs.readFileSync(s.file);},
    finish(){return crypto.createHash('sha256').update(this.data).digest('latin1');}})}
}};
function apiItem(i) { return {key:i.key,version:i.version,data:i.toJSON()}; }
async function control(body) {
  Object.assign(config,body.config||{});
  Zotero.Attachments.importFromFile=config.noImport?undefined:importFromFile;
  Zotero.Server.LocalAPI=config.noLocalAPI?{}:{getServerID:()=>config.databaseId};
  ChromeUtils.importGlobalProperties=config.noGlobalImport?undefined:()=>{};
  if(body.addons) addons=body.addons.map(a=>({...a,isActive:true}));
  if('legacy' in body) Zotero.__paperDownloadBatches={active:body.legacy};
  if(body.restart) {epoch++; delete Zotero.__zoteroLibraryBatches;}
  if(body.clearMarker) delete Zotero.__zoteroLibraryBatches;
  if(body.update) {
    const item=[...items.values()].find(i=>i.key===body.update.key);
    Object.assign(item.fields,body.update.fields);
  }
  if(body.seed) {
    for(const row of body.seed) {
      const i=new Item(row.itemType); i.fields={...row.fields};
      i.parentID=row.parentKey?[...items.values()].find(i=>i.key===row.parentKey)?.id:row.parentID;
      i.note=row.note||''; i.tags=row.tags||[]; i.attachmentContentType=row.contentType;
      i.key=row.key;
      i.creators=row.creators||[]; i.collections=row.collections||[];
      await i.saveTx(); if(row.file) {i.file=path.join(root,i.key+'.pdf');fs.copyFileSync(row.file,i.file);}
    }
  }
  for(const row of body.seedCollections||[]) {
    const c=new Collection(); c.name=row.name; await c.saveTx();
    const ordered=[...items.values()];
    for(const index of row.itemIndexes||[]) ordered[index].addToCollection(c.id);
  }
  return {items:[...items.values()].map(apiItem),collections:[...collections.values()].map(c=>c.toJSON()),
    events,prefs:Object.fromEntries(prefs),jobs:Zotero.__zoteroLibraryBatches||null,browserTaskState};
}
const server=http.createServer(async(req,res)=>{
  const chunks=[];for await(const chunk of req)chunks.push(chunk);
  const rawBody=Buffer.concat(chunks),body=rawBody.toString('utf8');
  const u=new URL(req.url,'http://127.0.0.1');
  const headers={'Content-Type':'application/json','Zotero-API-Version':'3','X-Zotero-Version':'10.0.7',
    'Zotero-Server-ID':config.databaseId};
  const send=(status,value)=>{res.writeHead(status,headers);res.end(status===204?'':JSON.stringify(value));};
  const sendText=value=>{res.writeHead(200,{...headers,'Content-Type':'text/plain; charset=utf-8'});res.end(value);};
  try {
    if(u.pathname==='/control') return send(200,await control(JSON.parse(body||'{}')));
    // Synthetic owned browser task for download-to-finalize behavioral trials.
    if(u.pathname.startsWith('/v2/')) {
      if(req.headers.authorization!=='Bearer synthetic-browser-credential') return send(401,{});
      const article='https://ieeexplore.ieee.org/document/1234567/';
      if(u.pathname==='/v2/tasks/fixture-task') return send(200,{state:browserTaskState});
      if(u.pathname==='/v2/tasks/fixture-task/complete') {
        browserTaskState='completed'; events.push({event:'browser_complete'}); return send(200,{state:browserTaskState});
      }
      if(u.pathname==='/v2/tabs/fixture-tab') return send(200,{url:article,title:config.articleTitle||'Verified article'});
      if(u.pathname==='/v2/tabs/fixture-tab/wait') return send(200,{});
      if(u.pathname==='/v2/tabs/fixture-tab/eval') return send(200,{value:{
        url:article,title:config.articleTitle||'Verified article',
        meta:{citation_doi:'10.1234/fixture',citation_title:config.articleTitle||'Verified article',
          citation_pdf_url:'https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=1234567'},
        accessSignals:['Access provided by fixture institution'],openAccessSignals:[],links:[]}});
      if(u.pathname==='/v2/tabs/fixture-tab/download' && config.fixturePdf) {
        const bytes=fs.readFileSync(config.fixturePdf);
        events.push({event:'browser_download',sha256:hash(config.fixturePdf),bytes:bytes.length});
        res.writeHead(200,{'Content-Type':'application/pdf','x-download-is-pdf':'true',
          'x-download-bytes':String(bytes.length),'x-download-sha256':hash(config.fixturePdf),
          'x-download-final-url':'https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=1234567'});
        return res.end(bytes);
      }
      return send(404,{});
    }
    if(u.pathname==='/api/') return send(200,{});
    if(u.pathname==='/api/schema') return send(200,{version:42,itemTypes:[]});
    if(u.pathname==='/api/local/authorize') {
      events.push({event:'authorize'});
      if(config.authorizationStatus!==200) return send(config.authorizationStatus,{});
      const grant=crypto.randomBytes(20).toString('hex'),remember=!!config.remember;
      grants.set(grant,remember);return send(200,{key:grant,remember});
    }
    if(u.pathname.startsWith('/api/local/uploads/')) {
      if(req.headers['zotero-allowed-request']!=='true')return send(403,{});
      const upload=uploads.get(u.pathname.split('/').pop());
      if(!upload) return send(404,{});
      upload.bytes=rawBody;events.push({event:'upload_bytes',bytes:rawBody.length});
      if(config.uploadDisconnect) {config.uploadDisconnect=false;res.destroy();return;}
      return send(200,{});
    }
    if(u.pathname==='/connector/ping') return send(200,'Zotero is running');
    if(u.pathname.startsWith('/connector/')) {events.push({event:'forbidden_connector_write'}); return send(500,{});}
    if(u.pathname==='/debug-bridge/execute') {
      if(config.auth!==201) return send(config.auth,{error:'server synthetic-token-do-not-print'});
      if(req.headers.authorization!=='Bearer synthetic-fixture-credential') return send(401,{});
      const isStart=body.includes('"action": "start"');
      if(isStart && config.addonsOnStart) {
        addons=config.addonsOnStart.map(a=>({...a,isActive:true})); config.addonsOnStart=null;
      }
      const result=await new AsyncFunction('Zotero','Services','ChromeUtils','Components','IOUtils',body)(Zotero,Services,ChromeUtils,Components,IOUtils);
      if(isStart && config.replyDelay) {const delay=config.replyDelay;config.replyDelay=0;await sleep(delay);}
      return send(201,result);
    }
    const parts=u.pathname.split('/').filter(Boolean);
    if(parts[0]==='api' && ['users','groups'].includes(parts[1])) {
      if(req.method!=='GET') {
        if(req.headers['zotero-allowed-request']!=='true')return send(403,{});
        if(req.headers['zotero-server-id']!==config.databaseId) return send(412,{});
        const credential=req.headers['zotero-api-key'];
        if(config.writeAuthStatus || !grants.has(credential)) return send(config.writeAuthStatus||401,{});
        if(!grants.get(credential))grants.delete(credential);
        events.push({event:'api_write',method:req.method,resource:parts[3],file:parts[5]==='file'});
        if(parts[5]==='file') {
          const item=[...items.values()].find(i=>i.key===parts[4]);if(!item)return send(404,{});
          const form=new URLSearchParams(body);
          if(form.has('upload')) {
            if(config.failImport>0) {config.failImport--;return send(500,{});}
            const upload=uploads.get(form.get('upload'));
            if(!upload?.bytes || upload.key!==item.key)return send(400,{});
            if(crypto.createHash('md5').update(upload.bytes).digest('hex')!==upload.md5)return send(400,{});
            item.file=path.join(root,item.key+'.pdf');fs.writeFileSync(item.file,upload.bytes);
            item.version++;events.push({event:'import',key:item.key,sha256:hash(item.file),transport:'local_api'});
            uploads.delete(form.get('upload'));return send(204,null);
          }
          const uploadKey=crypto.randomBytes(20).toString('hex');
          uploads.set(uploadKey,{key:item.key,md5:form.get('md5')});
          return send(200,{url:`http://127.0.0.1:${server.address().port}/api/local/uploads/${uploadKey}`,
            uploadKey,prefix:'',suffix:'',contentType:'application/octet-stream'});
        }
        if(req.method==='POST' && parts.length===4) {
          const row=JSON.parse(body)[0],isCollection=parts[3]==='collections';
          const map=isCollection?collections:items;
          if([...map.values()].some(i=>i.key===row.key))return send(200,{failed:{'0':{code:412}}});
          const item=isCollection?new Collection():new Item(row.itemType);item.key=row.key;
          if(isCollection) {
            item.name=row.name;item.parentID=[...collections.values()].find(c=>c.key===row.parentCollection)?.id||false;
          } else {
            item.fields=Object.fromEntries(Object.entries(row).filter(([k])=>!['key','version','itemType','creators','parentItem','contentType','linkMode'].includes(k)));
            item.creators=row.creators||[];item.attachmentContentType=row.contentType;
            item.parentID=[...items.values()].find(i=>i.key===row.parentItem)?.id;
          }
          await item.saveTx();return send(200,{successful:{'0':isCollection?{key:item.key,data:item.toJSON()}:apiItem(item)}});
        }
        if(req.method==='PATCH' && parts[3]==='items') {
          const item=[...items.values()].find(i=>i.key===parts[4]);if(!item)return send(404,{});
          if(String(item.version)!==req.headers['if-unmodified-since-version'])return send(412,{});
          const patch=JSON.parse(body);item.collections=patch.collections.map(k=>[...collections.values()].find(c=>c.key===k)?.id);
          await item.saveTx();return send(204,null);
        }
        return send(405,{});
      }
      if(parts[3]==='collections') return send(200,[...collections.values()].map(c=>({key:c.key,data:c.toJSON()})));
      if(parts[3]==='items') {
        let rows=[...items.values()]; const k=parts[4];
        if(k==='top') rows=rows.filter(i=>!i.parentID && !i.deleted && i.isRegularItem());
        else if(k) {
          const item=rows.find(i=>i.key===k); if(!item) return send(404,{});
          if(parts[5]==='file' && parts[6]==='view' && parts[7]==='url')
            return item.file?sendText(pathToFileURL(item.file).href):send(404,{});
          if(parts[5]==='children') rows=rows.filter(i=>i.parentID===item.id && (u.searchParams.has('includeTrashed')||!i.deleted));
          else if(u.searchParams.get('format')==='bibtex') return sendText(config.bibtex||
            `@article{fixture_${item.key},\n  title = {${item.getField('title')}},\n  doi = {${item.getField('DOI')}}\n}\n`);
          else return send(200,apiItem(item));
        }
        if(u.searchParams.has('itemType'))rows=rows.filter(i=>i.itemType===u.searchParams.get('itemType'));
        if(u.searchParams.get('q')) rows=rows.filter(i=> {
          const text=Object.values(i.toJSON()).map(v=>typeof v==='string'?v:JSON.stringify(v)).join(' ').toLowerCase();
          return u.searchParams.get('q').toLowerCase().split(/\s+/).every(word=>text.includes(word));
        });
        const start=Number(u.searchParams.get('start')||0), limit=Number(u.searchParams.get('limit')||100);
        return send(200,rows.slice(start,start+limit).map(apiItem));
      }
    }
    return send(404,{});
  } catch(e) {send(500,{error:'fixture_api_error',detail:e.message});}
});
server.listen(0,'127.0.0.1',()=>process.stdout.write(JSON.stringify({port:server.address().port})+'\n'));
