function note=validate_if_board_applicability()
% Real MATLAB controls and delayed fake dispatch: no instrument construction.
f=figure('Visible','off','Position',[20 20 450 690]); cleanup=onCleanup(@()delete(f));
calls={}; pending=[]; rejectionCount=0;
opt=struct('source_mode','simulation','persist',false,'dispatch',@dispatch,'onRejected',@rejected);
p=msiq.if_board_panel(f,'rx',opt); guard=onCleanup(@()p.close());
assert(p.isApplicable()); original=p.getDraft();
p.setApplicable(false,'本位置不使用 RX 中频控制。');
controls=p.controls; blocked=[controls.port;controls.refresh_ports;controls.connect;controls.config; ...
    controls.down;controls.selection;controls.edits(:);controls.minus(:);controls.plus(:)];
assert(all(strcmp(get(blocked,'Enable'),'off')));
set(controls.edits(1,1),'String','1'); set(controls.selection,'Value',6);
for k=1:numel(blocked), invoke(blocked(k)); end
assert(isempty(calls) && isequaln(p.getDraft(),original) && p.getSelection()==1);
assert(get(controls.selection,'Value')==1 && strcmp(get(controls.edits(1,1),'String'),'20.0'));
assert(rejectionCount>=numel(blocked) && ~isempty(fieldnames(p.getLastRejection())), ...
    'Expected %d rejections, got %d.',numel(blocked),rejectionCount);
p.setSelection(4); assert(p.getSelection()==4 && strcmp(get(controls.selection,'Enable'),'off'));
p.setBusy(true); p.setBusy(false); assert(all(strcmp(get(blocked,'Enable'),'off')));
bad=false; try p.loadConfig(p.getConfig()); catch err, bad=strcmp(err.identifier,'msiq:ifboard:notApplicable'); end
assert(bad);
p.setApplicable(true); assert(strcmp(get(controls.connect,'Enable'),'on'));
invoke(controls.connect); assert(p.isBusy() && numel(calls)==1);
invoke(controls.down); assert(numel(calls)==1); % Cannot bypass busy by invoking callback.
pending(struct('ok',true,'snapshot',struct('is_open',true,'state_known',false)));
assert(~p.isBusy() && p.getSnapshot().is_open);
invoke(controls.down); assert(numel(calls)==2);
known=struct('is_open',true,'state_known',true,'state',original,'sent',original);
pending(struct('ok',true,'snapshot',known));
p.setApplicable(false); assert(p.getSnapshot().is_open && isequal(p.getSnapshot(),known));
invoke(controls.connect); invoke(controls.plus(1,1));
assert(numel(calls)==2 && isequaln(p.getDraft(),original));
p.update(known); p.setBusy(false); assert(all(strcmp(get(blocked,'Enable'),'off')));
p.setApplicable(true); assert(strcmp(get(controls.connect,'String'),'断开'));
assert(strcmp(get(controls.down,'Enable'),'on') && isequaln(p.getDraft(),original));
invoke(controls.plus(1,1)); assert(numel(calls)==3 && strcmp(calls{3},'board_adjust'));
known.state.rf(1)=20.5; known.sent=known.state;
pending(struct('ok',true,'snapshot',known));
invoke(controls.connect); pending(struct('ok',true,'snapshot',struct('is_open',false,'state_known',false)));
invoke(controls.config); d=findall(0,'Tag','if_board_config_dialog'); assert(numel(d)==1);
p.setApplicable(false); assert(~isgraphics(d)); % No stale config commit after position changes.
p.close(); assert(numel(calls)==4); delete(p.panel); clear guard;
% Default TX stays available; custom dispatcher cleanup never sends a hidden command.
t=msiq.if_board_panel(f,'tx',opt); tg=onCleanup(@()t.close());
assert(t.isApplicable() && strcmp(get(t.controls.connect,'Enable'),'on'));
t.setApplicable(false); t.close(); delete(t.panel); clear tg;
note='RX 全控件真实禁用、直接回调阻断、忙态、会话与草稿保留、配置窗口失效及 TX 默认兼容通过；零仪器访问。';
    function dispatch(action,~,done), calls{end+1}=action; pending=done; end
    function rejected(~), rejectionCount=rejectionCount+1; end
end
function invoke(h)
cb=get(h,'Callback'); cb(h,[]);
end
