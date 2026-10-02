const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../scripts/editor.js'),'utf8');
let writes = 0;
const app = {
  docState:{whiteboardToken:'BoardTest',docxToken:'DocTest',seq:0,savedSeq:0},
  nodeManager:{nodeMap:new Map()}, api:{graphicNodeToPageNode:n=>n},
  commandManager:{handlers:new Map(),execute:()=>writes++},
  actionManager:{execAction:()=>writes++}
};
const element = {__reactInternalInstanceTest:{memoizedProps:{},return:{memoizedProps:{app,onDoubleClick:()=>writes++}}}};
const context = {URL,Map,Set,location:{origin:'https://test.feishu.cn',pathname:'/docx/DocTest'},
  document:{querySelectorAll:()=>[element]}};
const adapter = vm.runInNewContext('('+source+')',context);
const req = {document_url:'https://test.feishu.cn/docx/DocTest',whiteboard_token:'BoardTest',operation:{kind:'inspect'}};
assert.equal(adapter(req).nodes.length,0);
const rejected=(r,pattern)=>{const result=adapter(r);assert.match(result.adapter_error,pattern);assert.equal(result.content_write_started,false);};
rejected({...req,document_url:'https://test.feishu.cn/docx/Wrong'},/DOCUMENT_URL_MISMATCH/);
rejected({...req,whiteboard_token:'Wrong'},/BOARD_IDENTITY/);
rejected({...req,operation:{kind:'enter'}},/UNVERIFIED_EDITOR_BUILD/);
context.document.querySelectorAll=()=>[element,element];
rejected(req,/NOT_UNIQUE/);
assert.equal(writes,0);
console.log('PASS: read-only inspection and four failure paths make no editor calls');

// Native corners are an object, and include any rotation already applied.
context.document.querySelectorAll=()=>[element];
context.window={devicePixelRatio:2};
app.interactCtx={gmlRender:{canvas:{getBoundingClientRect:()=>({x:10,y:20,width:800,height:300})},
  transfromToViewPort:p=>({x:2*p.x+30,y:2*p.y+50})}};
app.api.graphicNodeToPageNode=n=>n.page;
const corners={topLeft:{x:10,y:15},topRight:{x:30,y:25},bottomLeft:{x:5,y:25},bottomRight:{x:25,y:35}};
const caption={textProps:{fontSize:18,sizeMode:1},textBoxWidth:180};
app.nodeManager.nodeMap.set('line',{id:'line',type:15,captions:[caption],lineProps:{points:[{x:0,y:0},{x:100,y:0}]},toGlobalPoint:p=>p,
  graphicText:{baseProps:{angle:30},getRectPoint:()=>corners},
  page:{info:{baseV2:{x:0,y:0,width:100,height:0},connectorV2:{shape:0,captions:{data:[{textStyle:{text:'label',fontSize:18},t:0.5,positionType:0}]}}}}});
const feedback=adapter(req);
assert.deepEqual(JSON.parse(JSON.stringify(feedback.label_geometry.line.world_corners)),[corners.topLeft,corners.topRight,corners.bottomRight,corners.bottomLeft]);
assert.deepEqual(JSON.parse(JSON.stringify(feedback.label_geometry.line.screen_rect)),{x:40,y:80,width:50,height:40});
assert.deepEqual(JSON.parse(JSON.stringify(feedback.viewport.world_to_screen)),{a:2,b:0,c:0,d:2,e:30,f:50});
assert.equal(feedback.viewport.device_pixel_ratio,2);
assert.equal(writes,0);
console.log('PASS: native label corners and observed screen transform preserve read-only behavior');
