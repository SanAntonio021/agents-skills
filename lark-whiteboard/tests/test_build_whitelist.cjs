// Per-build operation whitelist checks on a synthetic native app.
// Live acceptance of each released operation is recorded in references/compatibility.md;
// this file only proves that the guard releases exactly the recorded kinds.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const production=fs.readFileSync(path.join(__dirname,'../scripts/editor.js'),'utf8');
const listed=production.match(/if\(signature==='73a62bde'&&!\[([\s\S]*?)\]\.includes\(op\.kind\)\)fail\('OPERATION_NOT_VERIFIED_FOR_BUILD:'\+op\.kind\);/);
assert.ok(listed);
const released=listed[1].split(',').map(item=>item.trim().replace(/^'|'$/g,''));
assert.deepEqual(released,['enter','observe','canvas_preview','text','caption','caption_position',
  'move','resize','bring_to_front','reconnect','connect','anchors','delete','undo']);
console.log('PASS: newer build releases exactly the live-verified operation kinds');

const buildGuard="if (!['15acf339','73a62bde'].includes(signature))";
const saveGuard="if(!['8a287314','45ddc75e','f0f97b1a'].includes(saveSignature))";
// Treat the synthetic app as the newer build so the per-build guards themselves run.
const newerBuild="if(signature==='73a62bde'&&!['enter'";
const newerUndo="if(signature==='73a62bde'&&op.undo_follows===true){";
assert.ok(production.includes(buildGuard));assert.ok(production.includes(saveGuard));
assert.equal(production.split(newerBuild).length,2);assert.equal(production.split(newerUndo).length,2);
// Without the two replacements below the synthetic app counts as the older build.
const olderSource=production.replace(buildGuard,'if(false)').replace(saveGuard,'if(false)');
const newerSource=olderSource.replace(newerBuild,"if(!['enter'").replace(newerUndo,"if(op.undo_follows===true){");

function fixture(source=newerSource){
  let selected=[],selections=0,contentCalls=0,undoCalls=0,removedNodes=[];
  const shape=id=>({id,type:13,page:{info:{locked:false,baseV2:{x:0,y:0,width:100,height:60},
    compositeShape:{shapeType:11},textV2:{text:id,fontSize:18},theme:{}}}});
  const bound=(id,start,end)=>({id,type:15,
    attachProps:{start:{id:start.id,position:{x:1,y:.5}},end:{id:end.id,position:{x:0,y:.5}}},
    lineProps:{lineType:0,points:[{x:100,y:30},{x:200,y:30}]},toGlobalPoint:p=>p,
    page:{info:{locked:false,baseV2:{x:100,y:30,width:100,height:0},connectorV2:{shape:0,
      startObject:{objectId:start.id,snapTo:2,position:{x:1,y:.5}},
      endObject:{objectId:end.id,snapTo:4,position:{x:0,y:.5}}}}}});
  const left=shape('left'),middle=shape('middle'),right=shape('right'),spare=shape('spare');
  const note={id:'note',type:3,page:{info:{locked:false,baseV2:{x:0,y:200,width:100,height:40},textV2:{text:'note',fontSize:18},theme:{}}}};
  const incoming=bound('incoming',left,middle),outgoing=bound('outgoing',middle,right);
  const nodeMap=new Map([left,middle,right,spare,note,incoming,outgoing].map(n=>[n.id,n]));
  const undoStack=[];
  const app={docState:{whiteboardToken:'BoardTest',docxToken:'DocTest',seq:0,savedSeq:0,permission:{canEdit:true}},isResourceLoaded:true,
    nodeManager:{nodeMap},api:{graphicNodeToPageNode:n=>n.page,getSelectNodes:()=>selected},
    commandManager:{handlers:new Map(['Select','Delete','TextFontSize','Group','UnGroup','LineArrow','LineType','Order','Align']
      .map(k=>[k,{execute(){}}])),execute(name,args){
      if(name==='Select'){selections++;selected=args.nodeIds.map(id=>nodeMap.get(id));return;}
      contentCalls++;
      if(name!=='Delete')throw new Error('UNEXPECTED_COMMAND:'+name);
      // Selected objects and the lines bound to them leave together in one undo group.
      const gone=new Set(selected.map(n=>n.id));
      for(const n of nodeMap.values())if(n.attachProps&&['start','end'].some(side=>gone.has(n.attachProps[side].id)))gone.add(n.id);
      removedNodes=[...gone].map(id=>nodeMap.get(id));
      for(const id of gone)nodeMap.delete(id);
      selected=[];
      undoStack.push({actionLogs:[{type:0},{type:3,ids:[...gone].sort()},{type:1}]});
    }},
    actionManager:{execAction(){},ioManager:{inited:true,pendingActions:[],docState:{appliedVersion:1},sendAction(){},sendPendingActions(){},
      channelManager:{orderChannel:{localActions:[],localProcessing:false,localOffline:false,getBaseSeq(){},addLocalAction(){},flushLocalActions(){}}}}},
    undoRedoManager:{undoStack,redoStack:[],undo(){undoCalls++;undoStack.pop();for(const n of removedNodes)nodeMap.set(n.id,n);removedNodes=[];}},
    plugins:[{saveState:'saved',httpSavingSet:new Set(),hasUncommitData(){},updateSaveState(){}}]};
  const element={closest:()=>({}),__reactFiberTest:{memoizedProps:{app},return:null}};
  const context={URL,Map,Set,location:{origin:'https://test.feishu.cn',pathname:'/docx/DocTest'},document:{querySelectorAll:()=>[element]}};
  const adapter=vm.runInNewContext('('+source+')',context);
  const request={document_url:'https://test.feishu.cn/docx/DocTest',docx_token:'DocTest',whiteboard_token:'BoardTest'};
  const ids=()=>Array.from(adapter({...request,operation:{kind:'inspect'}}).nodes,n=>n.id);
  const run=operation=>adapter({...request,expected:adapter({...request,operation:{kind:'inspect'}}).nodes,operation});
  return {run,ids,undoStack,get selections(){return selections;},get contentCalls(){return contentCalls;},get undoCalls(){return undoCalls;}};
}

// Kinds without a live trial on the newer build stop before selection or content.
const blocked=fixture();
for(const operation of [{kind:'font',id:'left',font_size:22},{kind:'font',ids:['left','right'],font_size:22},
                        {kind:'style',id:'left',style:{fill_color:'#ffffff'}},{kind:'arrow',id:'incoming',end:'none'},
                        {kind:'caption_format',id:'incoming',font_size:20},{kind:'line_type',id:'incoming',shape:'polyline'},
                        {kind:'path',id:'incoming',points:[]},{kind:'curve_point',id:'incoming',point:{x:1,y:1}},
                        {kind:'group',ids:['left','right']},{kind:'ungroup',id:'left'},
                        {kind:'align_top',ids:['left','right']},{kind:'distribute_horizontal',ids:['left','middle','right']},
                        {kind:'send_to_back',ids:['left']},{kind:'bring_forward',ids:['left']},{kind:'send_backward',ids:['left']}]){
  const refused=blocked.run(operation);
  assert.equal(refused.adapter_error,'OPERATION_NOT_VERIFIED_FOR_BUILD:'+operation.kind);
  assert.equal(refused.content_write_started,false);
}
assert.equal(blocked.selections,0);assert.equal(blocked.contentCalls,0);assert.equal(blocked.undoCalls,0);
assert.deepEqual(blocked.ids(),['incoming','left','middle','note','outgoing','right','spare']);
console.log('PASS: unreleased kinds on the newer build reject before selection and content');

// A declared scope that omits or adds an object still stops before selection.
const scope=fixture();
for(const deleteIds of [['middle','incoming'],['middle','incoming','outgoing','right'],[]]){
  const refused=scope.run({kind:'delete',ids:['middle'],delete_ids:deleteIds});
  assert.equal(refused.adapter_error,'DELETE_SCOPE_MISMATCH');
  assert.equal(refused.content_write_started,false);
}
assert.equal(scope.selections,0);assert.equal(scope.contentCalls,0);
assert.deepEqual(scope.ids(),['incoming','left','middle','note','outgoing','right','spare']);
console.log('PASS: mismatched delete scope on the newer build rejects before selection and content');

// The exact cascade reaches native Delete once.
const live=fixture();
const deleted=live.run({kind:'delete',ids:['middle'],delete_ids:['middle','incoming','outgoing']});
assert.equal(deleted.adapter_error,undefined);
assert.equal(deleted.content_write_started,true);
assert.equal(deleted.transaction_count,1);
assert.equal(live.selections,1);assert.equal(live.contentCalls,1);
assert.deepEqual(Array.from(deleted.nodes,n=>n.id),['left','note','right','spare']);
console.log('PASS: an exact cascaded deletion passes the newer build guard in one transaction');

// The live undo of a cascaded deletion restored its lines in a different layer order, and the live undo
// of a deleted text changed its saved raw. A deletion that will be undone at once therefore stops
// before selection unless it removes exactly one shape or one line.
const paired=fixture();
for(const [operation,reason] of [
  [{kind:'delete',ids:['middle'],delete_ids:['middle','incoming','outgoing']},'multi_object_delete'],
  [{kind:'delete',ids:['spare','outgoing'],delete_ids:['spare','outgoing']},'multi_object_delete'],
  [{kind:'delete',ids:['note'],delete_ids:['note']},'text_delete']]){
  const refused=paired.run({...operation,undo_follows:true});
  assert.equal(refused.adapter_error,'UNDO_NOT_VERIFIED_FOR_BUILD:'+reason);
  assert.equal(refused.content_write_started,false);
}
assert.equal(paired.selections,0);assert.equal(paired.contentCalls,0);
assert.deepEqual(paired.ids(),['incoming','left','middle','note','outgoing','right','spare']);
const single=paired.run({kind:'delete',ids:['outgoing'],delete_ids:['outgoing'],undo_follows:true});
assert.equal(single.adapter_error,undefined);
assert.equal(single.content_write_started,true);
assert.equal(single.transaction_count,1);
assert.deepEqual(Array.from(single.nodes,n=>n.id),['incoming','left','middle','note','right','spare']);
assert.equal(single.undo_receipt.depth,1);
assert.equal(typeof single.undo_receipt.top,'string');
const unowned=paired.run({kind:'undo'});
assert.equal(unowned.adapter_error,'UNDO_NOT_OWNED');assert.equal(unowned.content_write_started,false);
const stale=paired.run({kind:'undo',undo_count:1,undo_receipt:{depth:2,top:single.undo_receipt.top}});
assert.equal(stale.adapter_error,'UNDO_STACK_CHANGED');assert.equal(stale.content_write_started,false);
assert.equal(paired.undoCalls,0);
const restored=paired.run({kind:'undo',undo_count:single.transaction_count,undo_receipt:single.undo_receipt});
assert.equal(restored.adapter_error,undefined);
assert.equal(restored.content_write_started,true);
assert.equal(paired.undoCalls,1);assert.equal(paired.contentCalls,1);
assert.deepEqual(Array.from(restored.nodes,n=>n.id),['incoming','left','middle','note','outgoing','right','spare']);
const shapeOnly=paired.run({kind:'delete',ids:['spare'],delete_ids:['spare'],undo_follows:true});
assert.equal(shapeOnly.adapter_error,undefined);
assert.equal(shapeOnly.transaction_count,1);
assert.deepEqual(Array.from(shapeOnly.nodes,n=>n.id),['incoming','left','middle','note','outgoing','right']);
const shapeBack=paired.run({kind:'undo',undo_count:shapeOnly.transaction_count,undo_receipt:shapeOnly.undo_receipt});
assert.equal(shapeBack.adapter_error,undefined);
assert.deepEqual(Array.from(shapeBack.nodes,n=>n.id),['incoming','left','middle','note','outgoing','right','spare']);
assert.equal(paired.undoCalls,2);assert.equal(paired.contentCalls,2);
// Without an undo behind it the same text deletion is released.
const textOnly=paired.run({kind:'delete',ids:['note'],delete_ids:['note']});
assert.equal(textOnly.adapter_error,undefined);
assert.deepEqual(Array.from(textOnly.nodes,n=>n.id),['incoming','left','middle','outgoing','right','spare']);
console.log('PASS: only the deletion of one shape or one line is paired with undo on the newer build, with an owned receipt');

// The older build keeps its recorded acceptance: a cascaded deletion may still be followed by undo.
const older=fixture(olderSource);
const olderCascade=older.run({kind:'delete',ids:['middle'],delete_ids:['middle','incoming','outgoing'],undo_follows:true});
assert.equal(olderCascade.adapter_error,undefined);
assert.equal(olderCascade.transaction_count,1);
assert.deepEqual(Array.from(olderCascade.nodes,n=>n.id),['left','note','right','spare']);
const olderText=older.run({kind:'delete',ids:['note'],delete_ids:['note'],undo_follows:true});
assert.equal(olderText.adapter_error,undefined);
assert.deepEqual(Array.from(olderText.nodes,n=>n.id),['left','right','spare']);
console.log('PASS: the undo pairing limit applies to the newer build only');
