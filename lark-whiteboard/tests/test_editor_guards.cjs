// Fault boundary tests use a synthetic native app, never substitute for live evidence.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const production=fs.readFileSync(path.join(__dirname,'../scripts/editor.js'),'utf8');
// Explicitly bypass only the production build pin in this synthetic fixture.
const source=production.replace("if (!['54e7e6de'].includes(signature))",'if (false)')
  .replace("if(saveSignature!=='b8586b42')",'if(false)');
let contentCalls=0,selected=[];
const shape=(id,locked=false)=>({id,type:13,page:{info:{locked,baseV2:{x:0,y:0,width:100,height:60},compositeShape:{shapeType:11},textV2:{text:id,fontSize:18}}}});
const a=shape('a'),b=shape('b',true),group={id:'g',children:[a,b],page:{info:{baseV2:{x:0,y:0,width:200,height:60}}}};
a.parent=group;b.parent=group;
const line={id:'c',type:15,attachProps:{start:{id:'b',position:{x:1,y:.5}},end:{id:'a',position:{x:0,y:.5}}},lineProps:{points:[{x:100,y:30},{x:200,y:30}]},toGlobalPoint:p=>p,page:{info:{baseV2:{x:100,y:30,width:100,height:0},connectorV2:{shape:0}}}};
const app={docState:{whiteboardToken:'BoardTest',docxToken:'DocTest',seq:0,savedSeq:0},
  nodeManager:{nodeMap:new Map([a,b,group,line].map(n=>[n.id,n]))},api:{graphicNodeToPageNode:n=>n.page,getSelectNodes:()=>selected},
  commandManager:{handlers:new Map(['Select','Move','TextFontSize'].map(k=>[k,{execute(){}}])),execute(name,args){if(name==='Select'){selected=args.nodeIds.map(id=>app.nodeManager.nodeMap.get(id));return;}contentCalls++;throw new Error('CONTENT_CALL_FAILED');}},
  actionManager:{execAction(){}},undoRedoManager:{undoStack:[]}};
app.actionManager.ioManager={inited:true,pendingActions:[],docState:{appliedVersion:2},sendAction(){},sendPendingActions(){},
  channelManager:{orderChannel:{localActions:[],localProcessing:false,localOffline:false,getBaseSeq(){},addLocalAction(){},flushLocalActions(){}}}};
app.plugins=[{saveState:'saved',httpSavingSet:new Set(),hasUncommitData(){},updateSaveState(){}}];
const element={__reactFiberTest:{memoizedProps:{app},return:null}};
const ctx={URL,Map,Set,location:{origin:'https://test.feishu.cn',pathname:'/docx/DocTest'},document:{querySelectorAll:()=>[element]}};
const adapter=vm.runInNewContext('('+source+')',ctx),req={document_url:'https://test.feishu.cn/docx/DocTest',whiteboard_token:'BoardTest'};
const run=op=>adapter({...req,expected:adapter({...req,operation:{kind:'inspect'}}).nodes,operation:op});
a.getLineAttachPoint=()=>({x:200,y:30});b.getLineAttachPoint=()=>({x:200,y:30});
let geometry=adapter({...req,operation:{kind:'inspect'}}).binding_geometry.find(v=>v.id==='c');
assert.equal(geometry.valid,false);assert.equal(geometry.start.actual.x,100);assert.equal(geometry.start.expected.x,200);
b.getLineAttachPoint=()=>({x:100,y:30});
geometry=adapter({...req,operation:{kind:'inspect'}}).binding_geometry.find(v=>v.id==='c');
assert.equal(geometry.valid,true);assert.equal(geometry.start.valid,true);assert.equal(contentCalls,0);
assert.match(run({kind:'move',ids:['g'],dx:10,dy:0}).adapter_error,/LOCKED_OBJECT/);
assert.match(run({kind:'anchors',id:'c',start:{snap_to:'right',position:{x:1,y:.5}}}).adapter_error,/LOCKED_OBJECT/);
assert.equal(contentCalls,0);
assert.match(run({kind:'move',ids:['g','a'],dx:10,dy:0}).adapter_error,/LOCKED_OBJECT/);
b.page.info.locked=false;
assert.match(run({kind:'move',ids:['g','a'],dx:10,dy:0}).adapter_error,/SELECTION_OVERLAP/);
app.api.getSelectNodes=()=>[];
app.nodeManager.nodeMap.set('free',shape('free'));
const selection=run({kind:'font',id:'free',font_size:22});
assert.match(selection.adapter_error,/NATIVE_SELECTION_MISMATCH/);assert.equal(selection.content_write_started,false);assert.equal(contentCalls,0);
app.api.getSelectNodes=()=>selected;
const failure=run({kind:'font',id:'free',font_size:22});
assert.match(failure.adapter_error,/CONTENT_CALL_FAILED/);assert.equal(failure.content_write_started,true);assert.equal(contentCalls,1);
console.log('PASS: synthetic locks, selection and content-start receipts');

const io=app.actionManager.ioManager,channel=io.channelManager.orderChannel;
channel.localActions.push({});
const waiting=run({kind:'font',id:'free',font_size:22});
assert.match(waiting.adapter_error,/UNSAVED_NATIVE_IO_STATE/);
assert.equal(waiting.content_write_started,false);assert.equal(contentCalls,1);
channel.localActions=[];
io.inited=1;
const invalidSave=run({kind:'font',id:'free',font_size:22});
assert.match(invalidSave.adapter_error,/NATIVE_SAVE_STATE_INVALID/);
assert.equal(invalidSave.content_write_started,false);assert.equal(contentCalls,1);
io.inited=true;
app.commandManager.execute=(name,args)=>{
  if(name==='Select'){selected=args.nodeIds.map(id=>app.nodeManager.nodeMap.get(id));return;}
  contentCalls++;
  app.nodeManager.nodeMap.get('free').page.info.textV2.fontSize=args.fontSize;
  channel.localActions.push({});
};
const unchanged=run({kind:'font',id:'free',font_size:18});
assert.equal(unchanged.save_fence.before_applied_version,2);
assert.equal(unchanged.save_fence.requires_ack,false);
assert.equal(unchanged.native_save.ordered_pending,1);
channel.localActions=[];
const changed=run({kind:'font',id:'free',font_size:22});
assert.equal(changed.save_fence.requires_ack,true);
assert.equal(changed.native_save.ordered_pending,1);
console.log('PASS: native pending queue blocks before content and save fences distinguish visible changes');

channel.localActions=[];
const originalCommand=app.commandManager.execute;
let guardContentCalls=0,guardSelections=0;
app.commandManager.handlers.set('Delete',{execute(){}});
app.commandManager.execute=(name,args)=>{
  if(name==='Select'){guardSelections++;selected=args.nodeIds.map(id=>app.nodeManager.nodeMap.get(id));return;}
  guardContentCalls++;throw new Error('GUARD_CONTENT_BOUNDARY');
};
const boundLine=(id,start,end)=>({id,type:15,attachProps:{start:{id:start.id,position:{x:1,y:.5}},end:{id:end.id,position:{x:0,y:.5}}},
  lineProps:{points:[{x:100,y:30},{x:200,y:30}]},toGlobalPoint:p=>p,
  page:{info:{baseV2:{x:100,y:30,width:100,height:0},connectorV2:{shape:0,
    startObject:{objectId:start.id,snapTo:2,position:{x:1,y:.5}},endObject:{objectId:end.id,snapTo:4,position:{x:0,y:.5}}}}}});
const guardLeft=shape('guard-left'),guardRight=shape('guard-right'),guardLine=boundLine('guard-line',guardLeft,guardRight);
for(const n of [guardLeft,guardRight,guardLine])app.nodeManager.nodeMap.set(n.id,n);
for(const op of [{kind:'reconnect',id:guardLine.id,end_id:guardLeft.id},
                {kind:'reconnect',id:guardLine.id,start_id:guardRight.id},
                {kind:'reconnect',id:guardLine.id,start_id:guardLeft.id,end_id:guardLeft.id}]){
  const rejected=run(op);
  assert.match(rejected.adapter_error,/SELF_CONNECTION_NOT_VERIFIED/);
  assert.equal(rejected.content_write_started,false);
}
const sameEnds=run({kind:'reconnect',id:guardLine.id,start_id:guardLeft.id,end_id:guardRight.id});
assert.equal(sameEnds.adapter_error,undefined);assert.equal(sameEnds.content_write_started,false);
assert.equal(guardContentCalls,0);assert.equal(guardSelections,0);

const outside=shape('guard-outside'),spare=shape('guard-spare'),foreignLine=boundLine('guard-foreign-line',outside,spare);
const foreignGroup={id:'guard-group',children:[spare,foreignLine],page:{info:{baseV2:{x:0,y:0,width:200,height:60}}}};
spare.parent=foreignGroup;foreignLine.parent=foreignGroup;
for(const n of [outside,spare,foreignLine,foreignGroup])app.nodeManager.nodeMap.set(n.id,n);
for(const op of [{kind:'delete',ids:[outside.id],delete_ids:[outside.id,foreignLine.id]},
                {kind:'delete',ids:[foreignLine.id],delete_ids:[foreignLine.id]}]){
  const rejected=run(op);
  assert.match(rejected.adapter_error,/GROUP_MEMBER_DELETE_NOT_VERIFIED/);
  assert.equal(rejected.content_write_started,false);
}
assert.equal(guardContentCalls,0);assert.equal(guardSelections,0);
const wholeGroup=run({kind:'delete',ids:[foreignGroup.id],delete_ids:[foreignGroup.id,spare.id,foreignLine.id]});
assert.match(wholeGroup.adapter_error,/GUARD_CONTENT_BOUNDARY/);
assert.equal(wholeGroup.content_write_started,true);assert.equal(guardContentCalls,1);assert.equal(guardSelections,1);
app.commandManager.execute=originalCommand;
console.log('PASS: merged reconnect endpoints and complete deletion membership reject before content; whole-group deletion remains allowed');

// Native Group omits a selected bound line if a bound module is outside the
// selection. These synthetic checks verify rejection before Select/content.
app.commandManager.handlers.set('Group',{execute(){}});
let groupSelections=0,groupContentCalls=0;
app.commandManager.execute=(name,args)=>{
  if(name==='Select'){groupSelections++;selected=args.nodeIds.map(id=>app.nodeManager.nodeMap.get(id));return;}
  groupContentCalls++;throw new Error('GROUP_CONTENT_BOUNDARY');
};
const groupThird=shape('group-third');
const groupFree=boundLine('group-free-line',guardLeft,guardRight);
groupFree.attachProps.start.id='';groupFree.attachProps.end.id='';
delete groupFree.page.info.connectorV2.startObject;delete groupFree.page.info.connectorV2.endObject;
const groupHalfStart=boundLine('group-half-start',guardLeft,guardRight),groupHalfEnd=boundLine('group-half-end',guardLeft,guardRight);
groupHalfStart.attachProps.end.id='';delete groupHalfStart.page.info.connectorV2.endObject;
groupHalfEnd.attachProps.start.id='';delete groupHalfEnd.page.info.connectorV2.startObject;
for(const n of [groupThird,groupFree,groupHalfStart,groupHalfEnd])app.nodeManager.nodeMap.set(n.id,n);
for(const ids of [[guardLeft.id,groupThird.id,guardLine.id],
                 [guardRight.id,groupThird.id,guardLine.id],
                 [groupThird.id,guardLine.id],[groupThird.id,groupHalfStart.id],[groupThird.id,groupHalfEnd.id]]){
  const rejected=run({kind:'group',ids});
  assert.match(rejected.adapter_error,/GROUP_BOUND_ENDPOINT_OUTSIDE_SELECTION/);
  assert.equal(rejected.content_write_started,false);
}
assert.equal(groupSelections,0);assert.equal(groupContentCalls,0);
const groupMissingAttach=boundLine('group-missing-attach',guardLeft,guardRight);
delete groupMissingAttach.attachProps;app.nodeManager.nodeMap.set(groupMissingAttach.id,groupMissingAttach);
const absentAttach=run({kind:'group',ids:[guardLeft.id,guardRight.id,groupMissingAttach.id]});
assert.match(absentAttach.adapter_error,/GROUP_LINE_ATTACH_UNAVAILABLE/);
assert.equal(absentAttach.content_write_started,false);assert.equal(groupSelections,0);assert.equal(groupContentCalls,0);
for(const ids of [[guardLeft.id,guardRight.id,guardLine.id],[groupThird.id,groupFree.id],
                 [guardLeft.id,groupHalfStart.id],[guardRight.id,groupHalfEnd.id]]){
  const permitted=run({kind:'group',ids});
  assert.match(permitted.adapter_error,/GROUP_CONTENT_BOUNDARY/);
  assert.equal(permitted.content_write_started,true);
}
assert.equal(groupSelections,4);assert.equal(groupContentCalls,4);
app.commandManager.execute=originalCommand;
console.log('PASS: group endpoints outside selection reject before Select/content; complete bindings and free lines reach Group');
