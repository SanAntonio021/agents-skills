// Original adapter for the page's native editor; evaluated only in a task-owned tab.
// No page globals, storage, network requests, DOM coordinate clicks or raw node mutation.
(request) => {
  'use strict';
  const fail = message => { throw new Error(message); };
  const wanted = new URL(request.document_url);
  if (location.origin !== wanted.origin || location.pathname !== wanted.pathname) fail('DOCUMENT_URL_MISMATCH');
  const doc = wanted.pathname.match(/^\/docx\/([A-Za-z0-9]+)\/?$/)?.[1];
  if (!doc || !/^[A-Za-z0-9]+$/.test(request.whiteboard_token)) fail('INVALID_TARGET');
  const matches = [];
  for (const element of document.querySelectorAll('.whiteboard-canvas-container')) {
    let fiber = element[Object.keys(element).find(k => /^__react(InternalInstance|Fiber)/.test(k))];
    let app, entry;
    for (let i = 0; fiber && i < 8; i++, fiber = fiber.return) {
      const p = fiber.memoizedProps || {};
      if (p.app?.docState?.whiteboardToken === request.whiteboard_token) app = p.app;
      if (typeof p.onDoubleClick === 'function') entry = p.onDoubleClick;
    }
    if (app?.docState.docxToken === doc) matches.push({app, entry});
  }
  if (matches.length !== 1) fail('BOARD_IDENTITY_NOT_UNIQUE_OR_NOT_LOADED');
  const {app: a, entry} = matches[0];
  if (!(a.nodeManager?.nodeMap instanceof Map) || typeof a.api?.graphicNodeToPageNode !== 'function') fail('EDITOR_INTERFACE_MISMATCH');
  const cmd = (name, args = {}) => {
    if (!a.commandManager.handlers.has(name)) fail('COMMAND_UNAVAILABLE:' + name);
    return a.commandManager.execute(name, args);
  };
  const selected = ids => cmd('Select', {nodeIds: ids});
  const stable = value => JSON.stringify(value, (_, v) => v && !Array.isArray(v) && typeof v === 'object'
    ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
  const arrowNames=['none','line_arrow','triangle_arrow','empty_triangle_arrow','circle_arrow','empty_circle_arrow','diamond_arrow','empty_diamond_arrow','single_arrow','multi_arrow','exact_single_arrow','zero_or_single_arrow','single_or_multi_arrow','zero_or_multi_arrow','x_arrow'];
  const lineNames=['straight','polyline','curve','right_angled_polyline'];
  const widthNames=['','extra_narrow','narrow',null,'medium',null,'bold'];
  const placements=['on_line','above_line','below_line'];
  // Native custom colors encode percentage alpha in the high byte.
  const opaqueColor=value=>(100*0x1000000)+parseInt(value.slice(1),16);
  const snapshot = () => [...a.nodeManager.nodeMap.values()].map(n => {
    const p = a.api.graphicNodeToPageNode(n), i = p.info, b = i.baseV2;
    const v = {id: n.id, kind: i.connectorV2 ? 'connector' : n.type===3 ? 'text' : n.type===13 ? 'shape' : n.children?.length ? 'group' : 'other',
      x:b.x, y:b.y, width:b.width, height:b.height};
    if (i.textV2) {v.text = i.textV2.text; v.font_size = i.textV2.fontSize;}
    const theme=i.theme||{}, hex=c=>'#'+(c&0xffffff).toString(16).padStart(6,'0');
    v.style={};
    const border=i.connectorV2?theme.connectColor:theme.borderColorCode;
    if(border>=0 && theme.borderColorCodeType===1)v.style.border_color=hex(border);
    else if(typeof n.borderProps?.borderColor==='string'&&n.borderProps.borderColor)v.style.border_color=n.borderProps.borderColor.toLowerCase();
    if(n.type===13 && theme.fillColorCode>=0 && theme.fillCodeType===1)v.style.fill_color=hex(theme.fillColorCode);
    else if(n.type===13 && typeof n.colorProps?.color==='string'&&n.colorProps.color)v.style.fill_color=n.colorProps.color.toLowerCase();
    const dash=i.connectorV2?theme.connectStyleCode:theme.borderStyleCode;
    if(dash>=1&&dash<=3)v.style.border_style=['','solid','dash','dot'][dash];
    const width=i.connectorV2?theme.connectWidthCode:theme.borderWidthCode;
    if(width>=1)v.style.border_width=widthNames[width]||'narrow';
    const textInfo=i.connectorV2?i.connectorV2.captions?.data?.[0]?.textStyle:i.textV2;
    if(textInfo && theme.textColorCode>=0 && theme.textColorCodeType===1)v.style.text_color=hex(theme.textColorCode);
    else if(textInfo && typeof n.textProps?.fontColor==='string' && /^#[0-9a-f]{6}$/i.test(n.textProps.fontColor))v.style.text_color=n.textProps.fontColor.toLowerCase();
    if (n.type===13) v.shape = i.compositeShape.shapeType === 8 ? 'round_rect' : i.compositeShape.shapeType === 11 ? 'rect' : 'unsupported';
    if (n.parent?.id && a.nodeManager.nodeMap.has(n.parent.id)) v.parent_id = n.parent.id;
    if (n.children?.length) v.children = n.children.map(x => x.id).sort();
    if (i.connectorV2) {
      const c = i.connectorV2, arrows = i.borderV2?.borderStyleItem?.advanceSettings;
      v.start_id = c.startObject?.objectId || ''; v.end_id = c.endObject?.objectId || '';
      for(const side of ['start','end']) {const e=c[side+'Object']; if(e?.objectId&&e.position)v[side+'_anchor']={snap_to:['','top','right','bottom','left'][e.snapTo],position:{x:e.position.x,y:e.position.y}};}
      v.shape = lineNames[c.shape] || 'unsupported';
      v.start_arrow = arrowNames[arrows?.start] || 'unsupported';
      v.end_arrow = arrowNames[arrows?.end] || 'unsupported';
      v.points=n.lineProps.points.slice(1,-1).map(p=>{const q=n.toGlobalPoint(p);return {x:q.x,y:q.y};});
      const captions=c.captions?.data || [];
      v.caption_texts=captions.map(c => c.textStyle?.text || '');
      v.caption=v.caption_texts.join('\n');
      v.caption_position=captions.length ? captions[0].t ?? 0.5 : null;
      v.caption_position_type=captions.length ? captions[0].positionType ?? 0 : null;
      v.caption_auto_direction=captions[0]?.autoDirection ?? false;
    }
    return v;
  }).sort((x,y) => x.id.localeCompare(y.id, 'en'));
  const sources = ['Select','Move','TextFontSize','Delete','Group','UnGroup','LineArrow','LineType','LineTextAdd','Theme','Duplicate']
    .map(k => a.commandManager.handlers.get(k)?.execute?.toString() || '').join('\n')
    + a.actionManager.execAction.toString();
  let h = 2166136261; for (let j = 0; j < sources.length; j++) {h ^= sources.charCodeAt(j); h = Math.imul(h, 16777619);}
  const signature = (h >>> 0).toString(16);
  const textSources=[a.api.selectNodeText,a.inputManager?.processInput,a.inputManager?.blur].map(f=>f?.toString() || '').join('');
  let th=2166136261;for(let j=0;j<textSources.length;j++){th^=textSources.charCodeAt(j);th=Math.imul(th,16777619);}
  const textSignature=(th>>>0).toString(16);
  const renderAlpha=()=>Object.fromEntries([...a.nodeManager.nodeMap.values()].map(n=>{
    const v={};if(Number.isFinite(n.borderProps?.borderAlpha))v.border=n.borderProps.borderAlpha;
    if(n.type===13&&Number.isFinite(n.colorProps?.alpha))v.fill=n.colorProps.alpha;
    const color=n.type===15?n.captions?.[0]?.textProps?.fontColor:n.textProps?.fontColor;
    if(typeof color==='string'&&color){const match=color.match(/^rgba\([^)]*,\s*([\d.]+)\)$/i);if(match)v.text=Number(match[1]);else if(/^#|^rgb\(/i.test(color))v.text=1;}
    return[n.id,v];
  }));
  const lineEndpoints=()=>Object.fromEntries([...a.nodeManager.nodeMap.values()].filter(n=>a.api.graphicNodeToPageNode(n).info.connectorV2).map(n=>{
    const s=n.toGlobalPoint(n.lineProps.points[0]),e=n.toGlobalPoint(n.lineProps.points.at(-1));
    return[n.id,{start:{x:s.x,y:s.y},end:{x:e.x,y:e.y}}];
  }));
  const result = () => ({nodes:snapshot(), render_alpha:renderAlpha(), line_endpoints:lineEndpoints(), seq:a.docState.seq, savedSeq:a.docState.savedSeq, signature, text_signature:textSignature});
  const op = request.operation || {kind:'inspect'};
  if (op.kind === 'inspect') return result();
  // Current signature must be recorded by a live compatibility test, never accepted dynamically.
  if (!['54e7e6de'].includes(signature)) fail('UNVERIFIED_EDITOR_BUILD:' + signature);
  if (a.docState.seq !== a.docState.savedSeq) fail('UNSAVED_PAGE_STATE');
  if (request.expected && stable(snapshot()) !== stable(request.expected)) fail('STALE_PAGE_SNAPSHOT');
  if (op.kind === 'enter') {
    if (typeof entry !== 'function') fail('EDITOR_ENTRY_UNAVAILABLE');
    entry(); return {entered:true};
  }
  if (!Array.isArray(request.expected)) fail('EXPECTED_SNAPSHOT_REQUIRED');
  const before = snapshot(), ids = op.kind==='connect' ? [op.template_id,op.start_id,op.end_id].filter(Boolean) : op.kind==='reconnect' ? [op.id,op.start_id,op.end_id].filter(Boolean) : op.ids || (op.id ? [op.id] : []);
  const node = id => a.nodeManager.nodeMap.get(id) || fail('NODE_NOT_FOUND:' + id);
  ids.forEach(node);
  for (const id of ids) {
    let n=node(id);
    while(n) {if(a.api.graphicNodeToPageNode(n)?.info?.locked)fail('LOCKED_OBJECT');n=n.parent;}
    if (node(id).children?.some(c => c.children?.length)) fail('NESTED_GROUP_NOT_VERIFIED');
  }
  const shape = id => {const n=node(id); if (n.type!==13 || !a.api.graphicNodeToPageNode(n).info.compositeShape) fail('NATIVE_SHAPE_REQUIRED');return n;};
  const textNode = id => {const n=node(id),i=a.api.graphicNodeToPageNode(n).info;if(!i.textV2 || i.connectorV2)fail('NATIVE_TEXT_REQUIRED');return n;};
  const line = id => {const n=node(id); if (!a.api.graphicNodeToPageNode(n).info.connectorV2) fail('CONNECTOR_REQUIRED');return n;};
  const number = (v, positive=false) => {if (!Number.isFinite(v) || (positive && v <= 0)) fail('INVALID_NUMBER');return v;};
  const text = value => {if (typeof value !== 'string') fail('INVALID_TEXT');return value;};
  const arrows = value => {const i=arrowNames.indexOf(value);if(i<0)fail('UNSUPPORTED_ARROW');return i;};
  // Selection is itself an undo group in this editor. Count content groups separately.
  const depth = () => a.undoRedoManager.undoStack.filter(g => g.actionLogs.some(x => ![0,1,7].includes(x.type))).length;
  if (!Array.isArray(a.undoRedoManager.undoStack)) fail('UNDO_INTERFACE_MISMATCH');
  const depthBefore = depth();
  // Capture constructors without executing any action. Restore the method even on failure.
  const actionTypes = () => {
    const sample = before.find(n => ['shape','text'].includes(n.kind) && Number.isFinite(n.font_size)) || before.find(n=>n.kind==='connector');
    if (!sample) fail('NO_OBJECT_FOR_INTERFACE_PROBE');
    selected([sample.id]);
    const m=a.actionManager, original=m.execAction, captured=[], prior=stable(snapshot()), d=depth(), seq=a.docState.seq;
    m.execAction = x => {captured.push(x);return null;};
    try {if(sample.kind==='connector')cmd('LineArrow',{lArrow:node(sample.id).borderProps.lArrow,rArrow:node(sample.id).borderProps.rArrow});else cmd('TextFontSize',{fontSize:sample.font_size});} finally {m.execAction=original;}
    if (prior !== stable(snapshot()) || depth() !== d || a.docState.seq !== seq) fail('PROBE_CHANGED_STATE');
    const Start=captured.find(x=>x.type===0)?.constructor, End=captured.find(x=>x.type===1)?.constructor,
      Update=captured.find(x=>x.type===6)?.constructor;
    if (!Start || !End || !Update || new Set([Start,End,Update]).size !== 3 ||
      !Start.toString().includes('.Start') || !End.toString().includes('.End') || !Update.toString().includes('.UpdateNode')) fail('ACTION_CONSTRUCTOR_MISMATCH');
    return {Start,End,Update};
  };
  const transaction = (types, work) => {
    a.actionManager.execAction(new types.Start());
    try {work((id, props) => {
      const action=new types.Update([{id, props}]);
      return a.actionManager.execAction(action);
    });}
    finally {a.actionManager.execAction(new types.End());}
  };
  // Refreshing one module also reroutes its other attached lines. Preserve their
  // existing path through native UpdateNode actions after the binding refresh.
  const preserveOtherPaths = excluded => before.filter(v=>v.kind==='connector'&&!excluded.includes(v.id))
    .map(v=>({v,base:node(v.id).baseProps.clone(),path:node(v.id).lineProps.clone()}));
  const restoredPaths=[];
  const restoreOtherPaths = (types, preserved) => {
    const current=new Map(snapshot().map(v=>[v.id,v])),changed=[];
    for(const item of preserved){
      const now=current.get(item.v.id);if(!now)fail('UNRELATED_CONNECTOR_REMOVED');
      const metadata=v=>Object.fromEntries(Object.entries(v).filter(([k])=>!['x','y','width','height','points'].includes(k)));
      if(stable(metadata(item.v))!==stable(metadata(now)))fail('UNRELATED_CONNECTOR_CHANGED');
      const live=node(item.v.id);
      if(stable(item.base)!==stable(live.baseProps.clone())||stable(item.path)!==stable(live.lineProps.clone()))changed.push(item);
    }
    if(changed.length){transaction(types,update=>changed.forEach(p=>update(p.v.id,[p.base,p.path])));restoredPaths.push(...changed.map(p=>p.v.id));}
    const restored=new Map(snapshot().map(v=>[v.id,v]));
    if(preserved.some(p=>stable(p.v)!==stable(restored.get(p.v.id))))fail('UNRELATED_PATH_RESTORE_FAILED');
    if(preserved.some(p=>stable(p.base)!==stable(node(p.v.id).baseProps.clone())||stable(p.path)!==stable(node(p.v.id).lineProps.clone())))fail('UNRELATED_NATIVE_PATH_RESTORE_FAILED');
  };
  const seedBoundStart = (n,update) => {
    const e=n.attachProps.start;if(!e.id||!e.position)fail('BOUND_START_REQUIRED');
    const p=n.lineProps.clone(),q=n.toLocalPoint(shape(e.id).getLineAttachPoint(e.position));
    p.points[0]={...p.points[0],x:q.x,y:q.y};update(n.id,[p]);
  };
  const verifiedBindings=[];
  const verifyBoundGeometry = n => {
    const evidence={id:n.id};
    for(const side of ['start','end']){
      const e=n.attachProps[side];if(!e.id||!e.position)continue;
      const expected=shape(e.id).getLineAttachPoint(e.position),actual=n.toGlobalPoint(side==='start'?n.lineProps.points[0]:n.lineProps.points.at(-1));
      if(![actual.x,actual.y,expected.x,expected.y].every(Number.isFinite)||Math.abs(actual.x-expected.x)>0.02||Math.abs(actual.y-expected.y)>0.02)fail('BOUND_ENDPOINT_GEOMETRY_MISMATCH:'+side);
      evidence[side]={actual:{x:actual.x,y:actual.y},expected:{x:expected.x,y:expected.y}};
    }
    verifiedBindings.push(evidence);
  };
  switch (op.kind) {
    case 'text': {
      const n=textNode(op.id);text(op.text);selected([n.id]);a.api.selectNodeText(n);a.inputManager.processInput(op.text);a.inputManager.blur();break;
    }
    case 'font': textNode(op.id);number(op.font_size,true);selected([op.id]);cmd('TextFontSize',{fontSize:op.font_size});break;
    case 'move': ids.forEach(id=>node(id));number(op.dx);number(op.dy);selected(ids);cmd('Move',{dx:op.dx,dy:op.dy});break;
    case 'resize': {
      const n=textNode(op.id);number(op.width,true);number(op.height,true);const t=actionTypes(),b=n.baseProps.clone();b.width=op.width;b.height=op.height;
      const props=[b];if(n.type===3){const p=n.textProps.clone();p.sizeMode=2;props.push(p);}
      transaction(t, update=>update(n.id,props));selected([n.id]);cmd('Move',{dx:0,dy:0});break;
    }
    case 'arrow': line(op.id);arrows(op.start);arrows(op.end);selected([op.id]);cmd('LineArrow',{lArrow:arrows(op.start),rArrow:arrows(op.end)});break;
    case 'caption': {
      const n=line(op.id);text(op.text);
      const captions=a.api.graphicNodeToPageNode(n).info.connectorV2.captions?.data || [];
      if(textSignature!=='7e805832')fail('UNVERIFIED_TEXT_EDITOR_BUILD:'+textSignature);
      if(captions.length>1)fail('MULTIPLE_CAPTIONS_NOT_EDITABLE');
      if(!captions.length && !op.text)break;
      selected([op.id]);
      if(captions.length)a.api.selectNodeText(n);else cmd('LineTextAdd');
      if(a.inputManager.textInfo?.node?.id!==n.id || a.inputManager.textInfo?.inputableText?.type!==3 || a.inputManager.inputStatus!=='focusing')fail('CAPTION_INPUT_TARGET_MISMATCH');
      a.inputManager.processInput(op.text);a.inputManager.blur();break;
    }
    case 'caption_position': {
      const n=line(op.id),p=n.captionsProps;
      if(p?.type!==10 || !Array.isArray(p.captions) || p.captions.length!==1 || ![0,1,2].includes(p.captions[0].positionType))fail('CAPTION_POSITION_NOT_VERIFIED');
      if(op.position===undefined&&op.placement===undefined)fail('CAPTION_POSITION_REQUIRED');
      if(op.position!==undefined){number(op.position);if(op.position<0 || op.position>1)fail('CAPTION_POSITION_OUT_OF_RANGE');}
      if(op.placement!==undefined && !placements.includes(op.placement))fail('INVALID_CAPTION_PLACEMENT');
      const t=actionTypes(),copy=p.clone();if(op.position!==undefined)copy.captions[0].t=op.position;
      if(op.placement!==undefined)copy.captions[0].positionType=placements.indexOf(op.placement);
      transaction(t,update=>update(n.id,[copy]));break;
    }
    case 'line_type': line(op.id);if(!lineNames.includes(op.shape))fail('UNSUPPORTED_LINE_TYPE');selected([op.id]);cmd('LineType',{lineType:lineNames.indexOf(op.shape)});break;
    case 'path': {
      const n=line(op.id),p=n.lineProps.clone();if(p.lineType===0)fail('STRAIGHT_LINE_HAS_NO_TURNING_POINTS');
      if(p.lineType===2&&(!n.attachProps.start.id||!n.attachProps.end.id))fail('CURVE_PATH_REQUIRES_BOUND_ENDPOINTS');
      if(!Array.isArray(op.points)||(p.lineType===2&&op.points.length!==2)||op.points.length<1)fail('INVALID_PATH_POINTS');
      const middle=op.points.map(p=>{number(p.x);number(p.y);const q=n.toLocalPoint(p);return {x:q.x,y:q.y,edited:true};});
      p.points=[{...n.lineProps.points[0]},...middle,{...n.lineProps.points.at(-1)}];p.isPointsEdited=true;
      if(p.lineType===3 && p.points.some((q,i)=>i && Math.abs(q.x-p.points[i-1].x)>0.001 && Math.abs(q.y-p.points[i-1].y)>0.001))fail('NON_ORTHOGONAL_PATH');
      const t=actionTypes();transaction(t,update=>update(n.id,[p]));break;
    }
    case 'style': {
      const n=node(op.id),i=a.api.graphicNodeToPageNode(n).info,s=op.style;
      if(!s || typeof s!=='object' || Array.isArray(s) || !Object.keys(s).length)fail('STYLE_REQUIRED');
      const allowed=i.connectorV2?['border_color','border_style','border_width','text_color']:n.type===13?['border_color','fill_color','border_style','border_width','text_color']:n.type===3?['text_color']:[];
      for(const [k,v] of Object.entries(s)){if(!allowed.includes(k))fail('UNSUPPORTED_STYLE_FIELD:'+k);if(k.endsWith('_color') && !/^#[0-9a-f]{6}$/i.test(v))fail('INVALID_COLOR');}
      if(s.border_style!==undefined&&!['solid','dash','dot'].includes(s.border_style))fail('INVALID_BORDER_STYLE');
      if(s.border_width!==undefined&&!widthNames.slice(1).includes(s.border_width))fail('INVALID_BORDER_WIDTH');
      if(s.text_color!==undefined&&i.connectorV2&&!n.captions.length)fail('CAPTION_REQUIRED_FOR_TEXT_COLOR');
      const theme={};if(s.border_color!==undefined){theme[i.connectorV2?'connectColor':'borderColorCode']=opaqueColor(s.border_color);theme.borderColorCodeType=1;}
      if(s.fill_color!==undefined){theme.fillColorCode=opaqueColor(s.fill_color);theme.fillCodeType=1;}
      if(s.border_style!==undefined)theme[i.connectorV2?'connectStyleCode':'borderStyleCode']=['','solid','dash','dot'].indexOf(s.border_style);
      if(s.border_width!==undefined)theme[i.connectorV2?'connectWidthCode':'borderWidthCode']=widthNames.indexOf(s.border_width);
      selected([n.id]);if(Object.keys(theme).length)cmd('Theme',{type:s.fill_color!==undefined?0:1,themeCapability:theme,nodeIds:[n.id]});
      if(s.text_color!==undefined){const t=actionTypes(),p=n.themeProps.clone();p.textColorCode=opaqueColor(s.text_color);p.textColorCodeType=1;const q=i.connectorV2?n.captionsProps.clone():n.textProps.clone();if(i.connectorV2)q.captions[0].textProps.fontColor=s.text_color;else q.fontColor=s.text_color;transaction(t,update=>update(n.id,[p,q]));}
      break;
    }
    case 'anchors': {
      const n=line(op.id), t=actionTypes(), p=n.attachProps.clone(),preserved=preserveOtherPaths([n.id]);
      if(!op.start&&!op.end)fail('ANCHOR_REQUIRED');
      for(const side of ['start','end'])if(op[side]){
        const e=op[side], s=['','top','right','bottom','left'].indexOf(e.snap_to), pos=e.position;
        if(s<1||!pos||![pos.x,pos.y].every(v=>Number.isFinite(v)&&v>=0&&v<=1))fail('INVALID_ANCHOR');
        if((s===1&&pos.y!==0)||(s===2&&pos.x!==1)||(s===3&&pos.y!==1)||(s===4&&pos.x!==0))fail('ANCHOR_NOT_ON_EDGE');
        p[side].snapTo=s;p[side].position={x:pos.x,y:pos.y};
      }
      transaction(t,update=>update(n.id,[p]));selected([n.attachProps.start.id,n.attachProps.end.id]);
      // A zero move can leave cached line geometry unchanged. Native paired moves
      // refresh bindings while returning both modules to their original positions.
      cmd('Move',{dx:1,dy:0});cmd('Move',{dx:-1,dy:0});restoreOtherPaths(t,preserved);verifyBoundGeometry(n);break;
    }
    case 'reconnect': {
      const n=line(op.id),sides=['start','end'].filter(s=>op[s+'_id']!==undefined),old={};if(!sides.length)fail('RECONNECT_TARGET_REQUIRED');
      sides.forEach(s=>{shape(op[s+'_id']);old[s]=n.attachProps[s].id;});
      if(sides.every(s=>old[s]===op[s+'_id']))break;
      const t=actionTypes(),preserved=preserveOtherPaths([n.id]);transaction(t,update=>{const p=n.attachProps.clone();sides.forEach(s=>delete p[s].id);update(n.id,[p]);const q=n.attachProps.clone();sides.forEach(s=>{q[s].id=op[s+'_id'];if(!old[s]){q[s].position=s==='start'?{x:1,y:0.5}:{x:0,y:0.5};q[s].snapTo=s==='start'?2:4;q[s].attachType=1;}});update(n.id,[q]);if(n.attachProps.start.id)seedBoundStart(n,update);});
      selected([...new Set(sides.map(s=>op[s+'_id']))]);cmd('Move',{dx:0,dy:0});
      restoreOtherPaths(t,preserved);
      verifyBoundGeometry(n);
      const has=(id)=>[...(a.nodeManager.nodeLinkMap.get(id)||[])].some(x=>(typeof x==='string'?x:x.id)===n.id);
      if (sides.some(s=>(old[s] && ![n.attachProps.start.id,n.attachProps.end.id].includes(old[s]) && has(old[s])) || !has(op[s+'_id']))) fail('RECONNECT_INDEX_MISMATCH');break;
    }
    case 'connect': {
      const duplicateSource='execute(e,r){let i=[...e.getSelectNodes()];if(0!==i.length){if(1===i.length){let e=i[0];if(ea.Al.isTableLike(e.type)&&e.tableStatus.hasSelectItem())return}this.worker.work(e)}}';
      if(a.commandManager.handlers.get('Duplicate')?.execute?.toString()!==duplicateSource)fail('DUPLICATE_INTERFACE_MISMATCH');
      const template=line(op.template_id);shape(op.start_id);shape(op.end_id);
      if(op.start_id===op.end_id)fail('SELF_CONNECTION_NOT_VERIFIED');
      const t=actionTypes(),originalAttachment=template.attachProps.clone(), priorIds=new Set(before.map(n=>n.id)),preserved=preserveOtherPaths([]);
      selected([template.id]);cmd('Duplicate');
      const added=[...a.nodeManager.nodeMap.values()].filter(n=>!priorIds.has(n.id));
      if(added.length!==1)fail('DUPLICATE_CREATED_UNEXPECTED_OBJECTS');
      const n=line(added[0].id),old=[n.attachProps.start.id,n.attachProps.end.id];
      transaction(t,update=>{
        const detached=n.attachProps.clone();delete detached.start.id;delete detached.end.id;update(n.id,[detached]);
        const bound=n.attachProps.clone();bound.start=originalAttachment.start;bound.end=originalAttachment.end;
        bound.start.id=op.start_id;bound.end.id=op.end_id;update(n.id,[bound]);seedBoundStart(n,update);
      });
      selected([op.start_id,op.end_id]);cmd('Move',{dx:0,dy:0});
      restoreOtherPaths(t,preserved);
      verifyBoundGeometry(n);
      const has=id=>[...(a.nodeManager.nodeLinkMap.get(id)||[])].some(x=>(typeof x==='string'?x:x.id)===n.id);
      if(!has(op.start_id)||!has(op.end_id)||old.some(id=>id&&![op.start_id,op.end_id].includes(id)&&has(id)))fail('CONNECT_INDEX_MISMATCH');
      break;
    }
    case 'group': if(ids.length<2)fail('SELECT_AT_LEAST_TWO');if(ids.some(id=>node(id).children?.length || node(id).parent?.id))fail('NESTED_GROUP_NOT_VERIFIED');selected(ids);cmd('Group');break;
    case 'ungroup': if(!node(op.id).children?.length)fail('GROUP_REQUIRED');selected([op.id]);cmd('UnGroup');break;
    case 'align_top': case 'distribute_horizontal': {
      if(ids.length<(op.kind==='align_top'?2:3))fail('INSUFFICIENT_SELECTION');
      ids.forEach(shape);const method=op.kind==='align_top'?'alignTop':'alignDistributeHorizontal';
      const handler=a.commandManager.handlers.get('Align');if(typeof handler?.[method]!=='function')fail('ALIGN_INTERFACE_MISMATCH');
      selected(ids);handler[method](a.api.getSelectNodes(),a.interactCtx);break;
    }
    case 'delete': {
      const removed=new Set(ids), visit=id=>{for(const child of node(id).children||[]){removed.add(child.id);visit(child.id);}};ids.forEach(visit);
      for (const n of before) if(n.kind==='connector'&&(removed.has(n.start_id)||removed.has(n.end_id)))removed.add(n.id);
      if(stable([...removed].sort())!==stable([...(op.delete_ids||[])].sort()))fail('DELETE_SCOPE_MISMATCH');
      selected(ids);cmd('Delete');break;
    }
    case 'undo':
      if(op.undo_count!==1 || depthBefore<1)fail('UNDO_NOT_OWNED');
      if (!op.undo_receipt || op.undo_receipt.depth !== a.undoRedoManager.undoStack.length ||
        op.undo_receipt.top !== stable(a.undoRedoManager.undoStack.at(-1))) fail('UNDO_STACK_CHANGED');
      a.undoRedoManager.undo();break;
    default: fail('UNSUPPORTED_OPERATION:' + op.kind);
  }
  const count=depth()-depthBefore;
  // Resize/reconnect also issue a zero move to update bound geometry: two native transactions.
  const max=['connect','anchors'].includes(op.kind)?4:op.kind==='reconnect'?3:['resize','caption','style'].includes(op.kind)?2:1;
  if(op.kind!=='undo' && (count<0||count>max))fail('UNEXPECTED_TRANSACTION_COUNT');
  return {...result(), before, transaction_count:count,restored_path_ids:restoredPaths,verified_bindings:verifiedBindings,
    ...(op.kind==='delete'?{undo_receipt:{depth:a.undoRedoManager.undoStack.length,top:stable(a.undoRedoManager.undoStack.at(-1))}}:{})};
}
