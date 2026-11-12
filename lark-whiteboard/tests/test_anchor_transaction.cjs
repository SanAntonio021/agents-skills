const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const production=fs.readFileSync(path.join(__dirname,'../scripts/editor.js'),'utf8');
assert.match(production,/OPERATION_NOT_VERIFIED_FOR_BUILD/);
assert.match(production,/'connect','anchors','delete','undo'\]\.includes\(op\.kind\)/);
const buildGuard="if (!['15acf339','73a62bde'].includes(signature))";
const saveGuard="if(!['8a287314','45ddc75e','f0f97b1a'].includes(saveSignature))";
assert.ok(production.includes(buildGuard));assert.ok(production.includes(saveGuard));
const source=production.replace(buildGuard,'if(false)').replace(saveGuard,'if(false)');

const cloneable=value=>{
  const copy=JSON.parse(JSON.stringify(value));
  Object.defineProperty(copy,'clone',{enumerable:false,value(){return cloneable(copy);}});
  return copy;
};
function StartAction(){this.type=0;this.name='.Start';}
function EndAction(){this.type=1;this.name='.End';}
function UpdateNode(records){this.type=6;this.name='.UpdateNode';this.records=records;}

function fixture(endOffset=0){
  let selected=[],activeGroup=null,updates=0,moves=0;
  const snap={top:1,right:2,bottom:3,left:4};
  const makeShape=(id,x)=>({id,type:13,
    page:{info:{locked:false,baseV2:{x,y:0,width:100,height:60},compositeShape:{shapeType:11},
      textV2:{text:id,fontSize:18},theme:{}}},
    getLineAttachPoint(position){const b=this.page.info.baseV2;return{x:b.x+position.x*b.width,y:b.y+position.y*b.height};}
  });
  const left=makeShape('left',0),right=makeShape('right',300);
  const start={id:'left',snapTo:snap.right,position:{x:1,y:.5}},end={id:'right',snapTo:snap.left,position:{x:0,y:.5}};
  const line={id:'line',type:15,attachProps:cloneable({start:{id:start.id,snapTo:start.snapTo,position:start.position},end:{id:end.id,snapTo:end.snapTo,position:end.position}}),
    lineProps:cloneable({lineType:0,points:[{x:100,y:30},{x:300+endOffset,y:30}]}),
    toGlobalPoint:p=>({x:p.x,y:p.y}),toLocalPoint:p=>({x:p.x,y:p.y}),
    page:{info:{locked:false,baseV2:{x:100,y:30,width:200,height:10},connectorV2:{shape:0,
      startObject:{objectId:start.id,snapTo:start.snapTo,position:start.position},
      endObject:{objectId:end.id,snapTo:end.snapTo,position:end.position},
      start:{attached_object:{id:start.id,snap_to:'right',position:start.position}},
      end:{attached_object:{id:end.id,snap_to:'left',position:end.position}},captions:{data:[]}}}}};
  const nodeMap=new Map([[left.id,left],[right.id,right],[line.id,line]]);
  const undoStack=[];
  const app={docState:{whiteboardToken:'BoardTest',docxToken:'DocTest',seq:0,savedSeq:0,permission:{canEdit:true}},isResourceLoaded:true,
    nodeManager:{nodeMap},api:{graphicNodeToPageNode:n=>n.page,getSelectNodes:()=>selected},
    commandManager:{handlers:new Map(['Select','TextFontSize','Move'].map(k=>[k,{execute(){}}])),execute(name,args){
      if(name==='Select'){selected=args.nodeIds.map(id=>nodeMap.get(id));return;}
      if(name==='Move'){moves++;return;}
      if(name==='TextFontSize'){
        app.actionManager.execAction(new StartAction());
        app.actionManager.execAction(new UpdateNode([{id:'left',props:[{probe:true}]}]));
        app.actionManager.execAction(new EndAction());return;
      }
      throw new Error('UNEXPECTED_COMMAND:'+name);
    }},
    actionManager:{ioManager:{inited:true,pendingActions:[],docState:{appliedVersion:1},sendAction(){},sendPendingActions(){},
      channelManager:{orderChannel:{localActions:[],localProcessing:false,localOffline:false,getBaseSeq(){},addLocalAction(){},flushLocalActions(){}}}},
      execAction(action){
        if(action.type===0){activeGroup={actionLogs:[{type:0}]};undoStack.push(activeGroup);return;}
        if(action.type===6){updates++;activeGroup.actionLogs.push({type:6});
          for(const record of action.records){
            const target=nodeMap.get(record.id);
            for(const props of record.props){
              if(Array.isArray(props.points))target.lineProps=cloneable(props);
              else if(props.start&&props.end){target.attachProps=cloneable(props);
                for(const side of ['start','end']){
                  const e=props[side],targetInfo=target.page.info.connectorV2;
                  const endpoint={objectId:e.id,snapTo:e.snapTo,position:{...e.position}};
                  targetInfo[side+'Object']=endpoint;
                  targetInfo[side]={...targetInfo[side],attached_object:{id:e.id,snap_to:['','top','right','bottom','left'][e.snapTo],position:{...e.position}}};
                }
              }
            }
          }
          app.docState.seq++;return;
        }
        if(action.type===1){if(activeGroup)activeGroup.actionLogs.push({type:1});activeGroup=null;return;}
      }
    },
    undoRedoManager:{undoStack},plugins:[{saveState:'saved',httpSavingSet:new Set(),hasUncommitData(){},updateSaveState(){}}]};
  const element={closest:()=>({}),__reactFiberTest:{memoizedProps:{app},return:null}};
  const context={URL,Map,Set,location:{origin:'https://test.feishu.cn',pathname:'/docx/DocTest'},document:{querySelectorAll:()=>[element]}};
  const adapter=vm.runInNewContext('('+source+')',context);
  const request={document_url:'https://test.feishu.cn/docx/DocTest',docx_token:'DocTest',whiteboard_token:'BoardTest'};
  const run=operation=>adapter({...request,expected:adapter({...request,operation:{kind:'inspect'}}).nodes,operation});
  return {app,line,run,get updates(){return updates;},get moves(){return moves;}};
}

const good=fixture();
const changed=good.run({kind:'anchors',id:'line',start:{snap_to:'right',position:{x:1,y:.35}}});
assert.equal(changed.adapter_error,undefined);
assert.equal(changed.content_write_started,true);
assert.equal(changed.transaction_count,1);
assert.equal(good.updates,1);
assert.equal(good.moves,0);
assert.equal(good.line.attachProps.start.position.y,.35);
assert.equal(good.line.lineProps.points[0].y,21);
assert.deepEqual(good.line.lineProps.points[1],{x:300,y:30});
assert.equal(changed.verified_bindings[0].start.actual.y,21);
assert.equal(changed.verified_bindings[0].start.expected.y,21);
assert.equal(changed.verified_bindings[0].end.actual.x,300);
console.log('PASS: anchor metadata and changed endpoint geometry commit together; untouched endpoint and route stay fixed');

const stale=fixture(2);
const rejected=stale.run({kind:'anchors',id:'line',start:{snap_to:'right',position:{x:1,y:.35}}});
assert.match(rejected.adapter_error,/BOUND_ENDPOINT_GEOMETRY_MISMATCH:end/);
assert.equal(rejected.content_write_started,false);
assert.equal(stale.updates,0);
assert.equal(stale.moves,0);
console.log('PASS: stale untouched endpoint rejects before any content write');

const polyline=fixture();
polyline.line.lineProps=cloneable({lineType:1,points:[{x:100,y:30},{x:200,y:30},{x:300,y:30}]});
const unsupported=polyline.run({kind:'anchors',id:'line',start:{snap_to:'right',position:{x:1,y:.35}}});
assert.match(unsupported.adapter_error,/ANCHOR_GEOMETRY_REQUIRES_STRAIGHT_LINE/);
assert.equal(unsupported.content_write_started,false);
assert.equal(polyline.updates,0);
assert.equal(polyline.moves,0);
console.log('PASS: non-straight connector rejects before any content write');
