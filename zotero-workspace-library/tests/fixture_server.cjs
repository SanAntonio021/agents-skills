// Isolated official Local API model. Any bridge or Connector use fails the contract.
const fs=require('node:fs'), path=require('node:path'), crypto=require('node:crypto'), http=require('node:http');
const {pathToFileURL}=require('node:url');
const root=process.argv[2];fs.mkdirSync(root,{recursive:true});
const items=new Map(),collections=new Map(),events=[],grants=new Map(),uploads=new Map();
let serial=0,version=0,browserTaskState='active';
let config={databaseId:crypto.randomUUID(),authorizationStatus:200,remember:false,zoteroVersion:'10.0.7'};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const clone=x=>JSON.parse(JSON.stringify(x));
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const key=()=> 'T'+String(++serial).padStart(7,'0');
function save(data,map=items) {
  data=clone(data);const current=map.get(data.key);
  data.key=data.key||key();data.version=++version;
  map.set(data.key,{key:data.key,version,data,...(current?.file?{file:current.file}:{})});
  events.push({event:map===items?(data.deleted?'trash':'save'):'collection',key:data.key,type:data.itemType});
  return map.get(data.key);
}
function publicItem(x){return {key:x.key,version:x.version,data:clone(x.data)};}
function control(body){
  Object.assign(config,body.config||{});
  if(body.restart)uploads.clear(); // saved library and remembered grants survive restarts
  if(body.update){
    const row=items.get(body.update.key);save({...row.data,...body.update.fields});
  }
  for(const row of body.seed||[]){
    const data={key:row.key||key(),itemType:row.itemType,creators:row.creators||[],tags:row.tags||[],
      collections:row.collections||[],...row.fields};
    if(row.parentKey||row.parentID)data.parentItem=row.parentKey||[...items.values()][row.parentID-1]?.key;
    if(row.note)data.note=row.note;
    if(data.itemType==='attachment')Object.assign(data,{contentType:row.contentType,linkMode:'imported_file',filename:'document.pdf'});
    const item=save(data);
    if(row.file){item.file=path.join(root,item.key+'.pdf');fs.copyFileSync(row.file,item.file);}
  }
  for(const row of body.seedCollections||[]){
    const c=save({key:row.key||key(),name:row.name,parentCollection:row.parentCollection||false},collections);
    for(const index of row.itemIndexes||[]){
      const item=[...items.values()][index];save({...item.data,collections:[...item.data.collections,c.key]});
    }
  }
  return {items:[...items.values()].map(publicItem),collections:[...collections.values()].map(x=>x.data),
    events,version,browserTaskState,prefs:{'extensions.fixture.auto':true},jobs:null};
}
const server=http.createServer(async(req,res)=>{
  const chunks=[];for await(const chunk of req)chunks.push(chunk);
  const raw=Buffer.concat(chunks),body=raw.toString('utf8'),u=new URL(req.url,'http://127.0.0.1');
  const headers=()=>({'Content-Type':'application/json','Zotero-API-Version':'3',
    'X-Zotero-Version':config.zoteroVersion,'Zotero-Server-ID':config.databaseId,'Last-Modified-Version':String(version)});
  const send=(code,value)=>{if(!res.destroyed){res.writeHead(code,headers());res.end(code===204?'':JSON.stringify(value));}};
  const sendText=value=>{res.writeHead(200,{...headers(),'Content-Type':'text/plain; charset=utf-8'});res.end(value);};
  try{
    if(u.pathname==='/control')return send(200,control(JSON.parse(body||'{}')));
    if(u.pathname.startsWith('/debug-bridge/')||u.pathname.startsWith('/connector/')){
      events.push({event:'forbidden_interface',path:u.pathname});return send(500,{});
    }
    if(u.pathname.startsWith('/v2/')){
      if(req.headers.authorization!=='Bearer synthetic-browser-credential')return send(401,{});
      const article='https://ieeexplore.ieee.org/document/1234567/';
      if(u.pathname==='/v2/tasks/fixture-task')return send(200,{state:browserTaskState});
      if(u.pathname==='/v2/tasks/fixture-task/complete'){
        if(config.completeFailure)return send(500,{});
        browserTaskState='completed';events.push({event:'browser_complete'});return send(200,{state:browserTaskState});
      }
      if(u.pathname==='/v2/tabs/fixture-tab')return send(200,{url:article,title:config.articleTitle||'Verified article'});
      if(u.pathname.endsWith('/wait'))return send(200,{});
      if(u.pathname.endsWith('/eval'))return send(200,{value:{url:article,title:config.articleTitle||'Verified article',
        meta:{citation_doi:'10.1234/fixture',citation_title:config.articleTitle||'Verified article',
          citation_pdf_url:'https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=1234567'},
        accessSignals:['Access provided by fixture institution'],openAccessSignals:[],links:[]}});
      if(u.pathname.endsWith('/download')&&config.fixturePdf){
        const bytes=fs.readFileSync(config.fixturePdf);
        events.push({event:'browser_download',sha256:hash(config.fixturePdf),bytes:bytes.length});
        res.writeHead(200,{'Content-Type':'application/pdf','x-download-is-pdf':'true','x-download-bytes':String(bytes.length),
          'x-download-sha256':hash(config.fixturePdf),'x-download-final-url':'https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber=1234567'});
        return res.end(bytes);
      }
      return send(404,{});
    }
    if(u.pathname==='/api/')return send(200,{});
    if(u.pathname==='/api/schema')return send(200,{version:42,itemTypes:[]});
    if(u.pathname==='/api/local/authorize'){
      events.push({event:'authorize'});
      if(config.authorizationStatus!==200)return send(config.authorizationStatus,{});
      const grant=crypto.randomBytes(20).toString('hex'),remember=!!config.remember;
      grants.set(grant,remember);return send(200,{key:grant,remember});
    }
    if(req.headers['zotero-server-id']!==config.databaseId)return send(412,{});
    if(u.pathname.startsWith('/api/local/uploads/')){
      const upload=uploads.get(u.pathname.split('/').pop());if(!upload)return send(404,{});
      upload.bytes=raw;events.push({event:'upload_bytes',bytes:raw.length});
      if(config.uploadDisconnect){config.uploadDisconnect=false;return res.destroy();}
      return send(200,{});
    }
    const parts=u.pathname.split('/').filter(Boolean);
    if(parts[0]!=='api'||!['users','groups'].includes(parts[1]))return send(404,{});
    const resource=parts[3],k=parts[4],map=resource==='collections'?collections:items;
    if(req.method!=='GET'){
      const credential=req.headers['zotero-api-key'];
      if(config.writeAuthStatus||!grants.has(credential))return send(config.writeAuthStatus||401,{});
      if(!grants.get(credential))grants.delete(credential);
      events.push({event:'api_write',method:req.method,resource,file:parts[5]==='file'});
      if(req.method==='DELETE')throw new Error('permanent delete forbidden');
      if(parts[5]==='file'){
        const item=items.get(k);if(!item)return send(404,{});
        if(item.file&&req.headers['if-none-match']==='*')return send(412,{});
        const form=new URLSearchParams(body);
        if(form.has('upload')){
          if(config.failImport>0){config.failImport--;return send(500,{});}
          const upload=uploads.get(form.get('upload'));
          if(!upload?.bytes||upload.key!==k)return send(400,{});
          if(crypto.createHash('md5').update(upload.bytes).digest('hex')!==upload.md5)return send(400,{});
          const saved=save(item.data);saved.file=path.join(root,k+'.pdf');fs.writeFileSync(saved.file,upload.bytes);
          events.push({event:'import',key:k,sha256:hash(saved.file),transport:'local_api'});
          uploads.delete(form.get('upload'));
          if(config.registerDisconnect){config.registerDisconnect=false;return res.destroy();}
          return send(204,null);
        }
        const uploadKey=crypto.randomBytes(20).toString('hex');uploads.set(uploadKey,{key:k,md5:form.get('md5')});
        return send(200,{url:'http://127.0.0.1:'+server.address().port+'/api/local/uploads/'+uploadKey,
          uploadKey,prefix:'',suffix:'',contentType:'application/octet-stream'});
      }
      if(req.method==='POST'&&parts.length===4){
        const rows=JSON.parse(body),current=map.get(rows[0].key),conditional=req.headers['if-unmodified-since-version'];
        if(conditional&&String(version)!==conditional)return send(412,{});
        if(current&&rows[0].version!==current.version)return send(200,{failed:{0:{code:412}}});
        if(!current&&rows[0].version!==0)return send(200,{failed:{0:{code:412}}});
        const item=save({...current?.data,...rows[0]},map);
        if(config.afterTrashNote&&item.data.deleted){
          config.afterTrashNote=false;save({key:key(),itemType:'note',note:'Concurrent reading '+item.key});
        }
        if(config.replyDelay){const delay=config.replyDelay;config.replyDelay=0;await sleep(delay);}
        return send(200,{successful:{0:publicItem(item)}});
      }
      if(req.method==='PATCH'){
        const item=map.get(k);if(!item)return send(404,{});
        if(String(item.version)!==req.headers['if-unmodified-since-version'])return send(412,{});
        save({...item.data,...JSON.parse(body)},map);return send(204,null);
      }
      return send(405,{});
    }
    if(resource==='collections')return send(200,[...collections.values()].map(publicItem));
    if(resource==='items'){
      let rows=[...items.values()];
      if(k==='top')rows=rows.filter(i=>!i.data.parentItem&&!i.data.deleted&&!['note','annotation','attachment'].includes(i.data.itemType));
      else if(k){
        const item=items.get(k);if(!item)return send(404,{});
        if(parts[5]==='file'&&parts[6]==='view'&&parts[7]==='url')
          return item.file?sendText(pathToFileURL(item.file).href):send(404,{});
        if(parts[5]==='children')rows=rows.filter(i=>i.data.parentItem===k&&(u.searchParams.has('includeTrashed')||!i.data.deleted));
        else if(u.searchParams.get('format')==='bibtex')return sendText(config.bibtex||
          '@article{fixture_'+k+',\n title={'+item.data.title+'},\n doi={'+item.data.DOI+'}\n}\n'.replaceAll('\\n','\n'));
        else return send(200,publicItem(item));
      }
      if(u.searchParams.has('itemType'))rows=rows.filter(i=>i.data.itemType===u.searchParams.get('itemType'));
      if(u.searchParams.get('q'))rows=rows.filter(i=>{
        const text=JSON.stringify(i.data).toLowerCase();return u.searchParams.get('q').toLowerCase().split(/\s+/).every(word=>text.includes(word));
      });
      const start=Number(u.searchParams.get('start')||0),limit=Number(u.searchParams.get('limit')||100);
      return send(200,rows.slice(start,start+limit).map(publicItem));
    }
    return send(404,{});
  }catch(e){send(500,{error:'fixture_api_error',detail:e.message});}
});
server.listen(0,'127.0.0.1',()=>process.stdout.write(JSON.stringify({port:server.address().port})+'\n'));