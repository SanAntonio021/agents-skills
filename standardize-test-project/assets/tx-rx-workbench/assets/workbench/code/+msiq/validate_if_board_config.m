function note=validate_if_board_config()
% Actual controls, local persistence and fake dispatch; no serial construction.
folder=tempname; mkdir(folder); msiq.validation_artifacts('defer',folder);
f=figure('Visible','off','Position',[20 20 450 690]); cleanup=onCleanup(@()delete(f));
calls=0;
for item={'tx','rx'}
    role=item{1}; path=fullfile(folder,[role '.mat']);
    opt=struct('source_mode','measurement','persist',true,'record_path',path, ...
        'port_list_fn',@(){'COM7'},'dispatch',@dispatch);
    p=msiq.if_board_panel(f,role,opt); guard=onCleanup(@()p.close());
    assert(strcmp(get(p.controls.connect,'Enable'),'off'));
    set(p.controls.port,'Value',2); invoke(p.controls.port);
    invoke(p.controls.config); d=findall(0,'Tag','if_board_config_dialog'); assert(numel(d)==1);
    c=getappdata(d,'if_board_config_controls');
    assert(strcmp(get(c.serial.baud_rate,'String'),'115200') && get(c.protocol_verified,'Value')==0);
    assert(all(cellfun(@isempty,get(c.limits,'Data')),'all'));
    invoke(c.cancel); assert(calls==0 && ~isfile([path '.config.mat']));
    invoke(p.controls.config); d=findall(0,'Tag','if_board_config_dialog'); c=getappdata(d,'if_board_config_controls');
    set(c.protocol_verified,'Value',1); invoke(c.save);
    assert(~isgraphics(d) && calls==0 && isfile([path '.config.mat']));
    assert(strcmp(get(p.controls.connect,'Enable'),'on') && strcmp(get(p.controls.down,'Enable'),'off'));
    assert(all(isnan(p.getDraft().rf)) && ~p.getSnapshot().is_open);
    invoke(p.controls.connect); assert(calls==1 && p.getSnapshot().is_open && ~p.getSnapshot().state_known);
    assert(strcmp(get(p.controls.config,'Enable'),'off')); invoke(p.controls.connect); calls=0;
    invoke(p.controls.config); d=findall(0,'Tag','if_board_config_dialog'); c=getappdata(d,'if_board_config_controls');
    cells=get(c.limits,'Data'); cells{1,1}=2; set(c.limits,'Data',cells); invoke(c.save);
    assert(isgraphics(d) && contains(get(c.status,'String'),'未保存'));
    for j=1:2:size(cells,2), cells(:,j)=num2cell(ones(6,1)); cells(:,j+1)=num2cell(30*ones(6,1)); end
    set(c.limits,'Data',cells); invoke(c.save); assert(~isgraphics(d));
    % Editing communication must not restore an old imported initial value.
    existing=p.getConfig(); existing.initial_state=struct('rf',20*ones(1,6));
    if strcmp(role,'rx'), existing.initial_state.i=20*ones(1,6); existing.initial_state.q=20*ones(1,6); end
    p.loadConfig(existing);
    set(p.controls.edits(1,1),'String','10'); invoke(p.controls.edits(1,1));
    invoke(p.controls.config); d=findall(0,'Tag','if_board_config_dialog'); c=getappdata(d,'if_board_config_controls');
    invoke(c.save); assert(p.getDraft().rf(1)==10,'Communication save restored stale attenuation.');
    p.close(); delete(p.panel); clear guard;
    restored=msiq.if_board_panel(f,role,opt); rg=onCleanup(@()restored.close());
    assert(strcmp(restored.getConfig().serial.port,'COM7') && restored.getConfig().runtime.protocol_verified);
    assert(all(restored.getConfig().limits.rf(:,1)==1) && all(restored.getDraft().rf==20));
    assert(~restored.getSnapshot().is_open && calls==0);
    invoke(restored.controls.config); d=findall(0,'Tag','if_board_config_dialog');
    restored.close(); assert(~isgraphics(d)); delete(restored.panel); clear rg;
end
base=msiq.if_board_vendor_defaults('tx'); base.mode='live';
assert(~base.runtime.protocol_verified && ~isfield(base,'limits') && ~isfield(base.serial,'port'));
base.runtime.protocol_verified=true; base.limits=struct('rf',repmat([1 30],6,1));
compat=base; compat.limits.rf=repmat([.1 31.4],6,1);
checked=msiq.if_board_config_dialog('validate',compat,'tx'); assert(isequal(checked.limits,compat.limits));
bad=base; bad.serial.baud_rate=nan; rejected=false;
try msiq.if_board_config_dialog('validate',bad,'tx'); catch, rejected=true; end; assert(rejected);
bad=base; bad.initial_state=struct('rf',zeros(1,6)); rejected=false;
try msiq.if_board_config_dialog('validate',bad,'tx'); catch, rejected=true; end; assert(rejected);
% Legacy import is accepted without inheriting an unverified live confirmation.
received=struct(); legacy=rmfield(base,'mode'); legacy.dialog_imported_initial=true;
d=msiq.if_board_config_dialog(base,'tx',struct('visible','off','import',@()legacy,'on_save',@receive));
c=getappdata(d,'if_board_config_controls'); invoke(c.import);
assert(get(c.protocol_verified,'Value')==0); invoke(c.save);
assert(~received.runtime.protocol_verified && ~isfield(received,'dialog_imported_initial'));
legacy.mode='mock';
d=msiq.if_board_config_dialog(base,'tx',struct('visible','off','import',@()legacy));
c=getappdata(d,'if_board_config_controls'); invoke(c.import);
assert(contains(get(c.status,'String'),'未导入')); invoke(c.cancel);
assert(calls==0);
note='TX/RX 首次配置、取消、保存零控制、连接门禁、范围检查、本机恢复与角色隔离通过。';
    function receive(value), received=value; end
    function dispatch(action,~,done)
        if strcmp(action,'board_connect'), calls=calls+1; opened=true;
        else, assert(strcmp(action,'board_close')); opened=false; end
        done(struct('ok',true,'snapshot',struct('is_open',opened,'state_known',false)));
    end
end
function invoke(h)
cb=get(h,'Callback'); cb(h,[]);
end
