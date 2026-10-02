// Fault boundary tests use a synthetic native app, never substitute for live evidence.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const production=fs.readFileSync(path.join(__dirname,'../scripts/editor.js'),'utf8');
// Explicitly bypass only the production build pin in this synthetic fixture.
const source=production.replace("if (!['54e7e6de'].includes(signature))",'if (false)');
let contentCalls=0,selected=[];
const shape=(id,locked=false)=>({id,type:13,page:{info:{locked,baseV2:{x:0,y:0,width:100,height:60},compositeShape:{shapeType:11},textV2:{text:id,fontSize:18}}}});
const a=shape('a'),b=shape('b',true),group={id:'g',children:[a,b],page:{info:{baseV2:{x:0,y:0,width:200,height:60}}}};
a.parent=group;b.parent=group;
const line={id:'c',type:15,attachProps:{start:{id:'b',position:{x:1,y:.5}},end:{id:'a',position:{x:0,y:.5}}},lineProps:{points:[{x:100,y:30},{x:200,y:30}]},toGlobalPoint:p=>p,page:{info:{baseV2:{x:100,y:30,width:100,height:0},connectorV2:{shape:0}}}};
const app={docState:{whiteboardToken:'BoardTest',docxToken:'DocTest',seq:0,savedSeq:0},
  nodeManager:{nodeMap:new Map([a,b,group,line].map(n=>[n.id,n]))},api:{graphicNodeToPageNode:n=>n.page,getSelectNodes:()=>selected},
  commandManager:{handlers:new Map(['Select','Move','TextFontSize'].map(k=>[k,{execute(){}}])),execute(name,args){if(name==='Select'){selected=args.nodeIds.map(id=>app.nodeManager.nodeMap.get(id));return;}contentCalls++;throw new Error('CONTENT_CALL_FAILED');}},
  actionManager:{execAction(){}},undoRedoManager:{undoStack:[]}};
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
