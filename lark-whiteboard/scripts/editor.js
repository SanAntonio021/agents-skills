// Original adapter for the page's native editor; evaluated only in a task-owned tab.
// No page globals, storage, network requests, DOM coordinate clicks or raw node mutation.
(request) => {
  'use strict';
  let contentWriteStarted=false, probing=false;
  try {
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
    if (app?.docState.docxToken === doc) matches.push({app, entry, element});
  }
  if (matches.length !== 1) fail('BOARD_IDENTITY_NOT_UNIQUE_OR_NOT_LOADED');
  const {app: a, entry, element} = matches[0];
  if (!(a.nodeManager?.nodeMap instanceof Map) || typeof a.api?.graphicNodeToPageNode !== 'function') fail('EDITOR_INTERFACE_MISMATCH');
  const cmd = (name, args = {}) => {
    if (!a.commandManager.handlers.has(name)) fail('COMMAND_UNAVAILABLE:' + name);
    if(name!=='Select'&&!probing)contentWriteStarted=true;
    return a.commandManager.execute(name, args);
  };
  const selected = ids => {
    cmd('Select', {nodeIds: ids});
    const actual=a.api.getSelectNodes?.();
    if(!Array.isArray(actual)||actual.map(n=>n.id).sort().join('\n')!==[...ids].sort().join('\n'))fail('NATIVE_SELECTION_MISMATCH');
  };
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
      v.caption_font_size=captions.length ? captions[0].textStyle?.fontSize ?? null : null;
      v.caption_width=captions.length ? captions[0].textBoxWidth ?? null : null;
      v.caption_size_mode=captions.length ? captions[0].textStyle?.sizeMode ?? null : null;
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
  const worldGeometry=()=>Object.fromEntries([...a.nodeManager.nodeMap.values()].map(n=>{
    const b=n.globalBaseProps;
    return[n.id,b&&['x','y','width','height','angle'].every(k=>Number.isFinite(b[k]))
      ?Object.fromEntries(['x','y','width','height','angle'].map(k=>[k,b[k]])):null];
  }));
  const objectBounds=()=>Object.fromEntries([...a.nodeManager.nodeMap.values()].map(n=>{
    const b=n.getRectNode?.();
    return[n.id,b&&['minX','minY','maxX','maxY'].every(k=>Number.isFinite(b[k]))
      ?{x:b.minX,y:b.minY,width:b.maxX-b.minX,height:b.maxY-b.minY}:null];
  }));
  const arrangementBounds=()=>Object.fromEntries([...a.nodeManager.nodeMap.values()].filter(n=>n.type===13).map(n=>{
    const b=n.getBounds?.();
    return[n.id,b&&['minX','minY','maxX','maxY'].every(k=>Number.isFinite(b[k]))&&b.maxX>b.minX&&b.maxY>b.minY
      ?{x:b.minX,y:b.minY,width:b.maxX-b.minX,height:b.maxY-b.minY}:null];
  }));
  // Read actual attachment geometry independently of connector serialization.
  // Unrelated legacy invalid bindings remain observable without blocking inspect.
  const bindingGeometry=()=>[...a.nodeManager.nodeMap.values()].filter(n=>a.api.graphicNodeToPageNode(n).info.connectorV2).map(n=>{
    const evidence={id:n.id,valid:true};
    for(const side of ['start','end']){
      const e=n.attachProps?.[side];if(!e?.id)continue;
      try{
        const target=a.nodeManager.nodeMap.get(e.id);
        if(!e.position||typeof target?.getLineAttachPoint!=='function')throw new Error('BINDING_TARGET_UNAVAILABLE');
        const expected=target.getLineAttachPoint(e.position),actual=n.toGlobalPoint(side==='start'?n.lineProps.points[0]:n.lineProps.points.at(-1));
        const valid=[actual.x,actual.y,expected.x,expected.y].every(Number.isFinite)&&Math.hypot(actual.x-expected.x,actual.y-expected.y)<=0.02;
        evidence[side]={actual:{x:actual.x,y:actual.y},expected:{x:expected.x,y:expected.y},valid};evidence.valid&&=valid;
      }catch(error){evidence[side]={valid:false,error:String(error.message)};evidence.valid=false;}
    }
    return evidence;
  });
  const curveHandles=()=>Object.fromEntries([...a.nodeManager.nodeMap.values()].filter(n=>n.isCurveLine?.()).map(n=>[n.id,{
    turning:n.lineProps.points.slice(3,-1).filter((_,j)=>j%3===0).map(p=>{const q=n.toGlobalPoint(p);return{x:q.x,y:q.y};}),
    segment:n.getControlPoints().map(p=>({x:p.x,y:p.y,enabled:p.enabled}))
  }]));
  const viewport=()=>{
    const r=a.interactCtx?.gmlRender,rect=r?.canvas?.getBoundingClientRect?.();
    if(!rect||typeof r.transfromToViewPort!=='function')return null;
    const p=r.transfromToViewPort({x:0,y:0}),x=r.transfromToViewPort({x:1,y:0}),y=r.transfromToViewPort({x:0,y:1});
    return{rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},device_pixel_ratio:window.devicePixelRatio,
      world_to_screen:{a:x.x-p.x,b:x.y-p.y,c:y.x-p.x,d:y.y-p.y,e:p.x,f:p.y}};
  };
  const labelGeometry=()=>Object.fromEntries([...a.nodeManager.nodeMap.values()].filter(n=>n.type===15&&n.captions?.length===1&&n.graphicText).map(n=>{
    const g=n.graphicText,b=g.baseProps,r=a.interactCtx?.gmlRender;
    if(!b||typeof g.getRectPoint!=='function')return[n.id,{available:false}];
    const corners=g.getRectPoint(),world=['topLeft','topRight','bottomRight','bottomLeft'].map(k=>({x:corners[k].x,y:corners[k].y})),screen=typeof r?.transfromToViewPort==='function'?world.map(p=>{const q=r.transfromToViewPort(p);return{x:q.x,y:q.y};}):null;
    const rect=points=>({x:Math.min(...points.map(p=>p.x)),y:Math.min(...points.map(p=>p.y)),
      width:Math.max(...points.map(p=>p.x))-Math.min(...points.map(p=>p.x)),height:Math.max(...points.map(p=>p.y))-Math.min(...points.map(p=>p.y))});
    return[n.id,{available:true,angle:b.angle,world_corners:world,world_rect:rect(world),screen_corners:screen,screen_rect:screen?rect(screen):null}];
  }));
  const nativeSave = () => {
    const io=a.actionManager.ioManager,ch=io?.channelManager?.orderChannel,
      plugins=(a.plugins||[]).filter(p=>typeof p.hasUncommitData==='function'&&typeof p.updateSaveState==='function');
    if(!io||!ch||plugins.length!==1)return{available:false,reason:'NATIVE_SAVE_INTERFACE_UNAVAILABLE'};
    const p=plugins[0],functions=[io.sendAction,io.sendPendingActions,ch.getBaseSeq,ch.addLocalAction,ch.flushLocalActions,p.hasUncommitData,p.updateSaveState];
    if(functions.some(f=>typeof f!=='function'))return{available:false,reason:'NATIVE_SAVE_INTERFACE_UNAVAILABLE'};
    const sources=functions.map(f=>f.toString()).join('\n');let hash=2166136261;
    for(let j=0;j<sources.length;j++){hash^=sources.charCodeAt(j);hash=Math.imul(hash,16777619);}
    const saveSignature=(hash>>>0).toString(16);
    if(saveSignature!=='b8586b42')return{available:false,reason:'UNVERIFIED_NATIVE_SAVE_INTERFACE',signature:saveSignature};
    const applied=io.docState?.appliedVersion;
    if(typeof io.inited!=='boolean'||!Array.isArray(io.pendingActions)||!Array.isArray(ch.localActions)
      ||typeof ch.localProcessing!=='boolean'||typeof ch.localOffline!=='boolean'
      ||!Number.isInteger(applied)||applied<0||!(p.httpSavingSet instanceof Set)
      ||!['saving','saved'].includes(p.saveState))return{available:false,reason:'NATIVE_SAVE_STATE_INVALID',signature:saveSignature};
    return{available:true,signature:saveSignature,initialized:io.inited,applied_version:applied,
      pending:io.pendingActions.length,ordered_pending:ch.localActions.length,processing:ch.localProcessing,
      offline:ch.localOffline,save_state:p.saveState,http_pending:p.httpSavingSet.size};
  };
  const nativeSaveReady=s=>s.available&&s.initialized&&!s.pending&&!s.ordered_pending&&!s.processing&&!s.offline
    &&s.save_state==='saved'&&!s.http_pending;
  const result = () => ({nodes:snapshot(), render_alpha:renderAlpha(), line_endpoints:lineEndpoints(), curve_handles:curveHandles(),
    object_bounds:objectBounds(),arrangement_bounds:arrangementBounds(),world_geometry:worldGeometry(),binding_geometry:bindingGeometry(),label_geometry:labelGeometry(),viewport:viewport(), seq:a.docState.seq, savedSeq:a.docState.savedSeq, signature, text_signature:textSignature,native_save:nativeSave()});
  const op = request.operation || {kind:'inspect'};
  if (op.kind === 'inspect') return result();
  // Current signature must be recorded by a live compatibility test, never accepted dynamically.
  if (!['54e7e6de'].includes(signature)) fail('UNVERIFIED_EDITOR_BUILD:' + signature);
  const saveBefore=nativeSave();
  if(!saveBefore.available)fail(saveBefore.reason);
  if(!nativeSaveReady(saveBefore))fail('UNSAVED_NATIVE_IO_STATE');
  if (a.docState.seq !== a.docState.savedSeq) fail('UNSAVED_PAGE_STATE');
  if (request.expected && stable(snapshot()) !== stable(request.expected)) fail('STALE_PAGE_SNAPSHOT');
  if (op.kind === 'canvas_preview') {
    if (!Array.isArray(request.expected)) fail('EXPECTED_SNAPSHOT_REQUIRED');
    const canvas=a.interactCtx?.gmlRender?.canvas;
    if(typeof canvas?.toDataURL!=='function')fail('NATIVE_CANVAS_PREVIEW_UNAVAILABLE');
    return {data_url:canvas.toDataURL('image/png'),viewport:viewport()};
  }
  if (op.kind === 'enter') {
    if (typeof entry !== 'function') fail('EDITOR_ENTRY_UNAVAILABLE');
    entry(); return {entered:true};
  }
  if (op.kind === 'observe') {
    if (!Array.isArray(request.expected)) fail('EXPECTED_SNAPSHOT_REQUIRED');
    const plugins=(a.plugins||[]).filter(p=>typeof p.onResize==='function'&&typeof p.resizeCanvas==='function'
      &&p.onResize.toString().includes('this.resizeCanvas(')&&p.onResize.toString().includes('this.app.viewportManager.zoom'));
    if(plugins.length!==1||plugins[0].app!==a)fail('VIEW_RESIZE_INTERFACE_NOT_UNIQUE');
    const p=plugins[0],functions=[p.onResize,p.resizeCanvas,p.notifyApplicationResize,p.onAppResizeCallback,
      a.viewportManager?.zoom,a.viewportManager?.zoomWorker?.beforeZoom,a.renderManager?.contentDirectDraw,a.auxiliaryManager?.redraw];
    const sources=functions.map(f=>typeof f==='function'?f.toString():'').join('\n');
    let hash=2166136261;for(let j=0;j<sources.length;j++){hash^=sources.charCodeAt(j);hash=Math.imul(hash,16777619);}
    if((hash>>>0).toString(16)!=='ff0c9e81')fail('UNVERIFIED_VIEW_RESIZE_INTERFACE');
    const nodes=stable(snapshot()),alpha=stable(renderAlpha()),ends=stable(lineEndpoints()),seq=a.docState.seq,
      saved=a.docState.savedSeq,undo=stable(a.undoRedoManager.undoStack),redo=stable(a.undoRedoManager.redoStack);
    p.onResize();
    a.viewportManager.zoom(1,{synDraw:true,animation:false});
    if(nodes!==stable(snapshot())||alpha!==stable(renderAlpha())||ends!==stable(lineEndpoints())||seq!==a.docState.seq
      ||saved!==a.docState.savedSeq||undo!==stable(a.undoRedoManager.undoStack)||redo!==stable(a.undoRedoManager.redoStack))fail('OBSERVATION_CHANGED_BOARD');
    return result();
  }
  if (!Array.isArray(request.expected)) fail('EXPECTED_SNAPSHOT_REQUIRED');
  const before = snapshot(),beforeAlpha=renderAlpha(),beforeEnds=lineEndpoints(), ids = op.kind==='connect' ? [op.template_id,op.start_id,op.end_id].filter(Boolean) : op.kind==='reconnect' ? [op.id,op.start_id,op.end_id].filter(Boolean) : op.ids || (op.id ? [op.id] : []);
  let arrangementOrder=null,arrangementBeforeBounds=null;
  const node = id => a.nodeManager.nodeMap.get(id) || fail('NODE_NOT_FOUND:' + id);
  ids.forEach(node);
  const assertUnlocked=n=>{for(let p=n;p;p=p.parent)if(a.api.graphicNodeToPageNode(p)?.info?.locked)fail('LOCKED_OBJECT');};
  for (const id of ids) {
    let n=node(id);
    assertUnlocked(n);
    for(const child of n.children||[])assertUnlocked(child);
    if (node(id).children?.some(c => c.children?.length)) fail('NESTED_GROUP_NOT_VERIFIED');
    if(n.parent?.id&&a.nodeManager.nodeMap.has(n.parent.id)){
      if(n.parent.parent?.id&&a.nodeManager.nodeMap.has(n.parent.parent.id))fail('NESTED_GROUP_NOT_VERIFIED');
      if(ids.includes(n.parent.id))fail('GROUP_MEMBER_SELECTION_OVERLAP');
    }
    const group=n.children?.length?n:n.parent?.id&&a.nodeManager.nodeMap.has(n.parent.id)?n.parent:null;
    if(group&&[group,...group.children].some(member=>Math.abs(a.api.graphicNodeToPageNode(member)?.info?.baseV2?.angle||0)>1e-6))fail('ROTATED_GROUP_NOT_VERIFIED');
  }
  const shape = id => {const n=node(id); if (n.type!==13 || !a.api.graphicNodeToPageNode(n).info.compositeShape) fail('NATIVE_SHAPE_REQUIRED');return n;};
  const assertAffectedBindingsUnlocked=targetIds=>{
    const affected=new Set(targetIds);for(const id of targetIds)for(const child of node(id).children||[])affected.add(child.id);
    for(const n of a.nodeManager.nodeMap.values())if(n.attachProps&&['start','end'].some(side=>affected.has(n.attachProps[side]?.id)))assertUnlocked(n);
  };
  if(['move','resize','align_top','distribute_horizontal','delete'].includes(op.kind))assertAffectedBindingsUnlocked(ids);
  const textNode = id => {const n=node(id),i=a.api.graphicNodeToPageNode(n).info;if(!i.textV2 || i.connectorV2)fail('NATIVE_TEXT_REQUIRED');return n;};
  const line = id => {const n=node(id); if (!a.api.graphicNodeToPageNode(n).info.connectorV2) fail('CONNECTOR_REQUIRED');return n;};
  if(op.kind==='reconnect'){
    const n=line(op.id),start=op.start_id===undefined?n.attachProps.start.id:op.start_id,
      end=op.end_id===undefined?n.attachProps.end.id:op.end_id;
    if(start&&end&&start===end)fail('SELF_CONNECTION_NOT_VERIFIED');
  }
  const number = (v, positive=false) => {if (!Number.isFinite(v) || (positive && v <= 0)) fail('INVALID_NUMBER');return v;};
  const text = value => {if (typeof value !== 'string') fail('INVALID_TEXT');return value;};
  const arrows = value => {const i=arrowNames.indexOf(value);if(i<0)fail('UNSUPPORTED_ARROW');return i;};
  // Selection is itself an undo group in this editor. Count content groups separately.
  const depth = () => a.undoRedoManager.undoStack.filter(g => g.actionLogs.some(x => ![0,1,7].includes(x.type))).length;
  if (!Array.isArray(a.undoRedoManager.undoStack)) fail('UNDO_INTERFACE_MISMATCH');
  const depthBefore = depth();
  let cachedActionTypes;
  // Capture constructors without executing any action. Restore the method even on failure.
  const actionTypes = () => {
    if(cachedActionTypes)return cachedActionTypes;
    const unlocked=id=>{for(let n=node(id);n;n=n.parent)if(a.api.graphicNodeToPageNode(n)?.info?.locked)return false;return true;};
    const sample = before.find(n => ['shape','text'].includes(n.kind) && Number.isFinite(n.font_size)&&unlocked(n.id)) || before.find(n=>n.kind==='connector'&&unlocked(n.id));
    if (!sample) fail('NO_OBJECT_FOR_INTERFACE_PROBE');
    selected([sample.id]);
    const m=a.actionManager, original=m.execAction, captured=[], prior=stable(snapshot()), d=depth(), seq=a.docState.seq;
    m.execAction = x => {captured.push(x);return null;};
    probing=true;
    try {if(sample.kind==='connector')cmd('LineArrow',{lArrow:node(sample.id).borderProps.lArrow,rArrow:node(sample.id).borderProps.rArrow});else cmd('TextFontSize',{fontSize:sample.font_size});} finally {m.execAction=original;probing=false;}
    if (prior !== stable(snapshot()) || depth() !== d || a.docState.seq !== seq) fail('PROBE_CHANGED_STATE');
    const Start=captured.find(x=>x.type===0)?.constructor, End=captured.find(x=>x.type===1)?.constructor,
      Update=captured.find(x=>x.type===6)?.constructor;
    if (!Start || !End || !Update || new Set([Start,End,Update]).size !== 3 ||
      !Start.toString().includes('.Start') || !End.toString().includes('.End') || !Update.toString().includes('.UpdateNode')) fail('ACTION_CONSTRUCTOR_MISMATCH');
    return cachedActionTypes={Start,End,Update};
  };
  const transaction = (types, work) => {
    a.actionManager.execAction(new types.Start());
    try {work((id, props) => {
      const action=new types.Update([{id, props}]);
      contentWriteStarted=true;
      return a.actionManager.execAction(action);
    });}
    finally {a.actionManager.execAction(new types.End());}
  };
  const hashFunction=f=>{const s=typeof f==='function'?f.toString():'';let h=2166136261;for(let j=0;j<s.length;j++){h^=s.charCodeAt(j);h=Math.imul(h,16777619);}return(h>>>0).toString(16);};
  const validateGroupBoundsInterface=(group,types)=>{
    const interfaces=[[group.getBounds,'438a0c72'],[group.baseProps.clone,'6969ad5f'],[group.baseProps.update,'e974b34'],
      [types.Start,'156ff927'],[types.Update,'dde29aef'],[types.End,'2ce952f5'],[a.actionManager.execAction,'b5fe100a']];
    for(const child of group.children||[])interfaces.push([child.getRectNode,child.type===15?'6cbf3c17':'4a306f8d']);
    if(interfaces.some(([f,pin])=>hashFunction(f)!==pin))fail('UNVERIFIED_GROUP_BOUNDS_INTERFACE');
    if(group.baseProps.angle||group.children.some(c=>c.baseProps.angle||c.children?.length))fail('ROTATED_OR_NESTED_GROUP_NOT_VERIFIED');
  };
  const affectedParents=()=>{
    const affected=new Set(ids);for(const id of ids)for(const child of node(id).children||[])affected.add(child.id);
    if(['move','resize','align_top','distribute_horizontal'].includes(op.kind))for(const n of a.nodeManager.nodeMap.values())
      if(n.attachProps&&['start','end'].some(side=>affected.has(n.attachProps[side]?.id)))affected.add(n.id);
    const groups=new Set();for(const id of affected){const n=node(id);if(n.children?.length)groups.add(n);if(n.parent?.id&&a.nodeManager.nodeMap.has(n.parent.id))groups.add(n.parent);}
    return groups;
  };
  const boundsGroups=!['delete','undo','ungroup'].includes(op.kind)?affectedParents():new Set();
  if(boundsGroups.size){const types=actionTypes();for(const group of boundsGroups){assertUnlocked(group);validateGroupBoundsInterface(group,types);}}
  const refreshedGroups=[];
  const refreshGroupBounds=groups=>{
    if(!groups.size)return;
    const types=actionTypes(),updates=[];
    for(const group of groups){
      validateGroupBoundsInterface(group,types);
      const bounds=group.children.map(n=>n.getRectNode());
      if(!bounds.length||bounds.some(b=>!['minX','minY','maxX','maxY'].every(k=>Number.isFinite(b[k]))))fail('GROUP_MEMBER_BOUNDS_UNAVAILABLE');
      const x=Math.min(...bounds.map(b=>b.minX)),y=Math.min(...bounds.map(b=>b.minY)),
        geometry={x,y,width:Math.max(...bounds.map(b=>b.maxX))-x,height:Math.max(...bounds.map(b=>b.maxY))-y};
      if(Object.entries(geometry).every(([k,v])=>Math.abs(group.baseProps[k]-v)<=1e-6))continue;
      const children=()=>stable(group.children.map(n=>({id:n.id,page:a.api.graphicNodeToPageNode(n),base:n.baseProps.clone(),global:n.globalBaseProps,path:n.lineProps?.clone?.()})));
      const beforeChildren=children(),base=group.baseProps.clone();base.update(geometry);
      updates.push({group,base,children,beforeChildren});
    }
    if(updates.length)transaction(types,update=>updates.forEach(v=>update(v.group.id,[v.base])));
    for(const v of updates){if(v.children()!==v.beforeChildren)fail('GROUP_BOUNDS_REFRESH_CHANGED_MEMBER');refreshedGroups.push(v.group.id);}
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
  const verifiedCurvePoints=[];
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
      const n=textNode(op.id);text(op.text);if(textSignature!=='7e805832')fail('UNVERIFIED_TEXT_EDITOR_BUILD:'+textSignature);
      selected([n.id]);a.api.selectNodeText(n);
      if(a.inputManager.textInfo?.node?.id!==n.id||a.inputManager.inputStatus!=='focusing')fail('TEXT_INPUT_TARGET_MISMATCH');
      contentWriteStarted=true;a.inputManager.processInput(op.text);a.inputManager.blur();break;
    }
    case 'font': textNode(op.id);number(op.font_size,true);selected([op.id]);cmd('TextFontSize',{fontSize:op.font_size});break;
    case 'move': {
      number(op.dx);number(op.dy);
      const moving=new Set(ids);for(const id of ids)for(const child of node(id).children||[])moving.add(child.id);
      for(const id of moving){const n=node(id);if(n.attachProps&&['start','end'].some(side=>n.attachProps[side]?.id&&!moving.has(n.attachProps[side].id)))fail('BOUND_CONNECTOR_CANNOT_MOVE_WITH_FIXED_ENDPOINT');}
      // Native group Move can reroute an edited curve. When both modules move
      // together, preserve the complete native curve translated by the same delta.
      const preserved=[...a.nodeManager.nodeMap.values()].filter(n=>n.isCurveLine?.()&&(
        moving.has(n.id)||n.attachProps?.start?.id&&n.attachProps?.end?.id&&moving.has(n.attachProps.start.id)&&moving.has(n.attachProps.end.id)))
        .map(n=>{const base=n.baseProps.clone();base.x+=op.dx;base.y+=op.dy;return{id:n.id,base,path:n.lineProps.clone()};});
      selected(ids);cmd('Move',{dx:op.dx,dy:op.dy});
      const changed=preserved.filter(p=>stable(p.base)!==stable(node(p.id).baseProps.clone())||stable(p.path)!==stable(node(p.id).lineProps.clone()));
      if(changed.length){const t=actionTypes();transaction(t,update=>changed.forEach(p=>update(p.id,[p.base,p.path])));restoredPaths.push(...changed.map(p=>p.id));}
      if(preserved.some(p=>stable(p.base)!==stable(node(p.id).baseProps.clone())||stable(p.path)!==stable(node(p.id).lineProps.clone())))fail('MOVED_CURVE_PATH_RESTORE_FAILED');
      break;
    }
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
      contentWriteStarted=true;a.inputManager.processInput(op.text);a.inputManager.blur();break;
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
    case 'caption_format': {
      const n=line(op.id),p=n.captionsProps;
      if(p?.type!==10 || !Array.isArray(p.captions) || p.captions.length!==1)fail('SINGLE_CAPTION_REQUIRED');
      const has=k=>Object.prototype.hasOwnProperty.call(op,k),widthChange=has('width')||has('auto_width');
      if(Object.keys(op).some(k=>!['kind','id','font_size','width','auto_width'].includes(k)))fail('INVALID_CAPTION_FORMAT_PARAMETER');
      if(!has('font_size')&&!widthChange)fail('CAPTION_FORMAT_REQUIRED');
      if(has('font_size')){number(op.font_size);if(op.font_size<4||op.font_size>999)fail('CAPTION_FONT_SIZE_OUT_OF_RANGE');}
      if(has('width')){number(op.width);if(op.width<10)fail('CAPTION_WIDTH_OUT_OF_RANGE');}
      if(has('auto_width')&&op.auto_width!==true)fail('AUTO_WIDTH_MUST_BE_TRUE');
      if(has('width')&&has('auto_width'))fail('CAPTION_WIDTH_CONFLICT');
      if(widthChange){
        const handlers=(a.appConfig?.modes||[]).flatMap(m=>m.subModes||[]).flatMap(m=>m.streamProcessor||[])
          .filter(h=>typeof h.onStart==='function'&&typeof h.onMove==='function'&&typeof h.onUp==='function'&&h.onMove.toString().includes('textBoxWidth'));
        if(handlers.length!==1)fail('CAPTION_WIDTH_HANDLER_NOT_UNIQUE');
        const h=handlers[0],caption=p.captions[0],detector=a.interactCtx?.getDetector(8);
        const sources=[h.onStart,h.onMove,h.onUp,detector?.onDetect,p.clone,caption.clone,caption.update,caption.textProps?.update,a.actionManager.execAction]
          .map(f=>typeof f==='function'?f.toString():'').join('\n');
        let hash=2166136261;for(let j=0;j<sources.length;j++){hash^=sources.charCodeAt(j);hash=Math.imul(hash,16777619);}
        if((hash>>>0).toString(16)!=='f422b16d')fail('UNVERIFIED_CAPTION_WIDTH_INTERFACE');
      }
      if(has('font_size')){selected([n.id]);cmd('TextFontSize',{fontSize:op.font_size});}
      if(widthChange){
        const t=actionTypes(),copy=n.captionsProps.clone();
        copy.captions[0].update(has('width')?{textBoxWidth:op.width,textProps:{sizeMode:1}}:{textBoxWidth:-1});
        transaction(t,update=>update(n.id,[copy]));
      }
      break;
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
    case 'curve_point': {
      const n=line(op.id),ctx=a.interactCtx;
      if(!n.isCurveLine?.()||n.lineProps.points.length<4||(n.lineProps.points.length-1)%3!==0)fail('NATIVE_CURVE_REQUIRED');
      const handles=curveHandles()[n.id],mode=op.mode||(handles.turning.length?'turning':'segment'),index=op.index??0;
      if(!['segment','turning'].includes(mode)||!Number.isInteger(index)||index<0)fail('INVALID_CURVE_HANDLE');
      const source=handles[mode][index];if(!source||source.enabled===false)fail('CURVE_HANDLE_NOT_AVAILABLE');
      if(!op.point||Object.keys(op.point).sort().join(',')!=='x,y')fail('INVALID_CURVE_POINT');number(op.point.x);number(op.point.y);
      const handlers=(a.appConfig?.modes||[]).flatMap(m=>m.subModes||[]).flatMap(m=>m.streamProcessor||[])
        .filter(h=>typeof h.onStart==='function'&&typeof h.onMove==='function'&&typeof h.onUp==='function'
          &&h.onStart.toString().includes('CurveControlPoint')&&h.onMove.toString().includes('isPointsEdited'));
      if(handlers.length!==1)fail('CURVE_HANDLER_NOT_UNIQUE');
      const h=handlers[0],detector=ctx.getDetector(5),hash=s=>{let v=2166136261;for(let j=0;j<s.length;j++){v^=s.charCodeAt(j);v=Math.imul(v,16777619);}return(v>>>0).toString(16);};
      const fingerprint=hash([h.onStart,h.onMove,h.onUp].map(f=>f.toString()).join('\n'));
      if(fingerprint!=='feb5ede2'||hash(detector?.constructor.toString()||'')!=='63fa3cdd')fail('UNVERIFIED_CURVE_INTERFACE');
      const oldEnds=lineEndpoints()[n.id];selected([n.id]);
      const originEvent={pointerType:'mouse',button:0,buttons:1,shiftKey:false,ctrlKey:false,metaKey:false,altKey:false};
      const event=p=>({globalPoint:{x:p.x,y:p.y},originEvent});
      const detected=ctx.detect(5,event(source));
      if(!detected||detected.line!==n||detected.index!==index||detected.isTurningPoint!==(mode==='turning')||detected.enabled===false)fail('CURVE_HANDLE_DETECTION_MISMATCH');
      h.onStart(event(source),ctx);if(h.res?.line!==n)fail('CURVE_DRAG_TARGET_MISMATCH');
      try{contentWriteStarted=true;h.onMove(event(op.point),ctx);}finally{h.onUp(event(op.point),ctx);}
      const actual=n.toGlobalPoint(n.lineProps.points[3*index+3]),ends=lineEndpoints()[n.id];
      if(Math.hypot(actual.x-op.point.x,actual.y-op.point.y)>1e-5)fail('CURVE_POINT_INTENT_FAILED');
      if(['start','end'].some(s=>Math.hypot(oldEnds[s].x-ends[s].x,oldEnds[s].y-ends[s].y)>1e-5))fail('CURVE_ENDPOINT_MOVED');
      verifiedCurvePoints.push({id:n.id,mode,index,point:{x:actual.x,y:actual.y},fingerprint});break;
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
      const n=line(op.id);
      if(['start','end'].some(side=>!n.attachProps?.[side]?.id))fail('BOUND_ENDPOINTS_REQUIRED_FOR_ANCHOR_REFRESH');
      const endpointIds=[...new Set(['start','end'].map(side=>n.attachProps?.[side]?.id).filter(Boolean))];
      if(!endpointIds.length)fail('BOUND_ENDPOINT_REQUIRED');
      for(const side of ['start','end']){const e=n.attachProps?.[side];if(e?.id&&(!e.position||!['x','y'].every(k=>Number.isFinite(e.position[k]))))fail('BINDING_POSITION_UNAVAILABLE:'+side);}
      for(const id of endpointIds){const target=shape(id);assertUnlocked(target);if(target.parent?.id&&a.nodeManager.nodeMap.has(target.parent.id))fail('GROUPED_ANCHOR_REFRESH_NOT_VERIFIED');}
      assertAffectedBindingsUnlocked(endpointIds);
      for(const side of ['start','end'])if(op[side]&&!n.attachProps?.[side]?.id)fail('BOUND_ENDPOINT_REQUIRED:'+side);
      const t=actionTypes(), p=n.attachProps.clone(),preserved=preserveOtherPaths([n.id]);
      if(!op.start&&!op.end)fail('ANCHOR_REQUIRED');
      for(const side of ['start','end'])if(op[side]){
        const e=op[side], s=['','top','right','bottom','left'].indexOf(e.snap_to), pos=e.position;
        if(s<1||!pos||![pos.x,pos.y].every(v=>Number.isFinite(v)&&v>=0&&v<=1))fail('INVALID_ANCHOR');
        if((s===1&&pos.y!==0)||(s===2&&pos.x!==1)||(s===3&&pos.y!==1)||(s===4&&pos.x!==0))fail('ANCHOR_NOT_ON_EDGE');
        p[side].snapTo=s;p[side].position={x:pos.x,y:pos.y};
      }
      transaction(t,update=>update(n.id,[p]));selected(endpointIds);
      // A zero move can leave cached line geometry unchanged. Native paired moves
      // refresh bindings while returning both modules to their original positions.
      cmd('Move',{dx:1,dy:0});cmd('Move',{dx:-1,dy:0});restoreOtherPaths(t,preserved);verifyBoundGeometry(n);break;
    }
    case 'reconnect': {
      const n=line(op.id),sides=['start','end'].filter(s=>op[s+'_id']!==undefined),old={};if(!sides.length)fail('RECONNECT_TARGET_REQUIRED');
      sides.forEach(s=>{shape(op[s+'_id']);old[s]=n.attachProps[s].id;});
      assertAffectedBindingsUnlocked(sides.map(s=>op[s+'_id']));
      if(sides.every(s=>old[s]===op[s+'_id']))break;
      const t=actionTypes(),preserved=preserveOtherPaths([n.id]);transaction(t,update=>{const p=n.attachProps.clone();sides.forEach(s=>delete p[s].id);update(n.id,[p]);const q=n.attachProps.clone();sides.forEach(s=>{q[s].id=op[s+'_id'];if(!old[s]){q[s].position=s==='start'?{x:1,y:0.5}:{x:0,y:0.5};q[s].snapTo=s==='start'?2:4;q[s].attachType=1;}});update(n.id,[q]);if(n.attachProps.start.id)seedBoundStart(n,update);});
      selected([...new Set(sides.map(s=>op[s+'_id']))]);cmd('Move',{dx:0,dy:0});
      restoreOtherPaths(t,preserved);
      verifyBoundGeometry(n);
      const has=(id)=>[...(a.nodeManager.nodeLinkMap.get(id)||[])].some(x=>(typeof x==='string'?x:x.id)===n.id);
      if (sides.some(s=>(old[s] && ![n.attachProps.start.id,n.attachProps.end.id].includes(old[s]) && has(old[s])) || !has(op[s+'_id']))) fail('RECONNECT_INDEX_MISMATCH');break;
    }
    case 'connect': {
      // Duplicate is covered by the verified main command fingerprint.
      const template=line(op.template_id);shape(op.start_id);shape(op.end_id);
      assertAffectedBindingsUnlocked([op.start_id,op.end_id]);
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
    case 'group': {
      if(ids.length<2)fail('SELECT_AT_LEAST_TWO');
      if(ids.some(id=>node(id).children?.length || node(id).parent?.id))fail('NESTED_GROUP_NOT_VERIFIED');
      const members=new Set(ids);
      for(const id of ids){const n=node(id);if(a.api.graphicNodeToPageNode(n).info.connectorV2&&!n.attachProps)fail('GROUP_LINE_ATTACH_UNAVAILABLE');if(n.attachProps&&['start','end'].some(side=>n.attachProps[side]?.id&&!members.has(n.attachProps[side].id)))fail('GROUP_BOUND_ENDPOINT_OUTSIDE_SELECTION');}
      selected(ids);cmd('Group');break;
    }
    case 'ungroup': if(!node(op.id).children?.length)fail('GROUP_REQUIRED');selected([op.id]);cmd('UnGroup');break;
    case 'align_top': case 'distribute_horizontal': {
      if(ids.length<(op.kind==='align_top'?2:3))fail('INSUFFICIENT_SELECTION');
      ids.forEach(shape);const method=op.kind==='align_top'?'alignTop':'alignDistributeHorizontal';
      const handler=a.commandManager.handlers.get('Align');if(typeof handler?.[method]!=='function')fail('ALIGN_INTERFACE_MISMATCH');
      selected(ids);const selection=a.api.getSelectNodes(),bounds=arrangementBounds();
      if(selection.some(n=>!bounds[n.id]))fail('ARRANGEMENT_BOUNDS_UNAVAILABLE');
      arrangementOrder=selection.map(n=>n.id);arrangementBeforeBounds=Object.fromEntries(arrangementOrder.map(id=>[id,bounds[id]]));
      if(op.arrangement_bounds&&stable(op.arrangement_bounds)!==stable(arrangementBeforeBounds))fail('STALE_ARRANGEMENT_BOUNDS');
      contentWriteStarted=true;handler[method](selection,a.interactCtx);break;
    }
    case 'delete': {
      const removed=new Set(ids), visit=id=>{for(const child of node(id).children||[]){removed.add(child.id);visit(child.id);}};ids.forEach(visit);
      for (const n of before) if(n.kind==='connector'&&(removed.has(n.start_id)||removed.has(n.end_id)))removed.add(n.id);
      if(stable([...removed].sort())!==stable([...(op.delete_ids||[])].sort()))fail('DELETE_SCOPE_MISMATCH');
      for(const id of removed){const parent=node(id).parent;if(parent?.id&&a.nodeManager.nodeMap.has(parent.id)&&!removed.has(parent.id))fail('GROUP_MEMBER_DELETE_NOT_VERIFIED');}
      selected(ids);cmd('Delete');break;
    }
    case 'undo':
      if(op.undo_count!==1 || depthBefore<1)fail('UNDO_NOT_OWNED');
      if (!op.undo_receipt || op.undo_receipt.depth !== a.undoRedoManager.undoStack.length ||
        op.undo_receipt.top !== stable(a.undoRedoManager.undoStack.at(-1))) fail('UNDO_STACK_CHANGED');
      contentWriteStarted=true;a.undoRedoManager.undo();break;
    default: fail('UNSUPPORTED_OPERATION:' + op.kind);
  }
  if(op.kind==='group')for(const n of a.nodeManager.nodeMap.values())if(n.children?.length&&!before.some(p=>p.id===n.id))boundsGroups.add(n);
  refreshGroupBounds(boundsGroups);
  if(['move','resize','align_top','distribute_horizontal'].includes(op.kind)){
    const moved=new Set(ids);for(const id of ids)for(const child of node(id).children||[])moved.add(child.id);
    for(const n of a.nodeManager.nodeMap.values())if(n.attachProps&&['start','end'].some(side=>moved.has(n.attachProps[side]?.id)))verifyBoundGeometry(n);
  }
  const count=depth()-depthBefore;
  // Resize/reconnect also issue a zero move to update bound geometry: two native transactions.
  const max=(['connect','anchors'].includes(op.kind)?4:op.kind==='reconnect'?3:['move','resize','caption','caption_format','style'].includes(op.kind)?2:1)+(refreshedGroups.length?1:0);
  if(op.kind!=='undo' && (count<0||count>max))fail('UNEXPECTED_TRANSACTION_COUNT');
  const changed=stable(before)!==stable(snapshot())||stable(beforeAlpha)!==stable(renderAlpha())||stable(beforeEnds)!==stable(lineEndpoints());
  return {...result(), before, content_write_started:contentWriteStarted,
    ...(arrangementOrder?{arrangement_order:arrangementOrder,arrangement_before_bounds:arrangementBeforeBounds}:{}),
    save_fence:{signature:saveBefore.signature,before_applied_version:saveBefore.applied_version,requires_ack:contentWriteStarted&&changed},
    transaction_count:count,refreshed_group_ids:refreshedGroups,restored_path_ids:restoredPaths,verified_bindings:verifiedBindings,verified_curve_points:verifiedCurvePoints,
    ...(op.kind==='delete'?{undo_receipt:{depth:a.undoRedoManager.undoStack.length,top:stable(a.undoRedoManager.undoStack.at(-1))}}:{})};
  }catch(error){return{adapter_error:String(error.message),content_write_started:contentWriteStarted};}
}
