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
assert.throws(()=>adapter({...req,document_url:'https://test.feishu.cn/docx/Wrong'}),/DOCUMENT_URL_MISMATCH/);
assert.throws(()=>adapter({...req,whiteboard_token:'Wrong'}),/BOARD_IDENTITY/);
assert.throws(()=>adapter({...req,operation:{kind:'enter'}}),/UNVERIFIED_EDITOR_BUILD/);
context.document.querySelectorAll=()=>[element,element];
assert.throws(()=>adapter(req),/NOT_UNIQUE/);
assert.equal(writes,0);
console.log('PASS: read-only inspection and four failure paths make no editor calls');
