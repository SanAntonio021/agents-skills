function widget=if_board_panel(parent,role,options)
%IF_BOARD_PANEL Shared daily board controls; construction never opens hardware.
if nargin<3, options=struct(); end
assert(any(strcmp(role,{'tx','rx'})),'msiq:ifboard:role','TX/RX role required.');
offline=field(options,'offline_test',false);
source=field(options,'source_mode',ternarySource(offline));
if strcmp(source,'simulation'), source='mock'; end
if strcmp(source,'measurement'), source='live'; end
assert(any(strcmp(source,{'mock','live'})),'msiq:ifboard:source','来源必须是 live 或 mock。');
if isfield(options,'source_mode') && isfield(options,'offline_test')
    assert(offline==strcmp(source,'mock'),'msiq:ifboard:source','来源与模拟标志不一致。');
end
offline=strcmp(source,'mock');
sourceTag='measurement'; if offline, sourceTag='simulation'; end
cfg=normalizeConfig(field(options,'config',struct()),role,offline,false);
if offline
    cfg.mode='mock';
    if ~isfield(cfg,'limits')
        cfg.limits=struct('rf',repmat([0 31.5],6,1),'i',repmat([0 31.5],6,1),'q',repmat([0 31.5],6,1));
    end
end
persist=field(options,'persist',true);
record=field(options,'record_path',fullfile(prefdir,['msiq_if_' role '_' source '_last.mat']));
if isfield(options,'record_paths') && isfield(options.record_paths,source), record=options.record_paths.(source); end
if isfield(options,'record_paths') && isfield(options.record_paths,sourceTag), record=options.record_paths.(sourceTag); end
configPath=[record '.config.mat'];
configNote='';
if persist && isfile(configPath) && isempty(fieldnames(field(options,'config',struct())))
    try
        savedConfig=load(configPath);
        assert(strcmp(savedConfig.role,role) && strcmp(savedConfig.source_mode,sourceTag),'配置来源或角色不匹配。');
        restored=msiq.if_board_config_dialog('validate',savedConfig.config,role);
        assert(strcmp(restored.mode,source),'配置来源不匹配。');
        cfg=restored;
    catch err, configNote=['本机配置未载入：' err.message]; end
end
draft=struct('rf',nan(1,6),'i',nan(1,6),'q',nan(1,6));
if offline, draft=struct('rf',20*ones(1,6),'i',20*ones(1,6),'q',20*ones(1,6)); end
if isfield(cfg,'initial_state'), draft=completeDraft(cfg.initial_state); end
historyNote=''; historyPort='';
if persist
    readPath=record;
    if ~isfile(readPath) && ~offline && ~isfield(options,'record_path') && ~isfield(options,'record_paths')
        readPath=fullfile(prefdir,['msiq_if_' role '_last.mat']);
    end
    [savedSettings,historyPort,historyNote]=msiq.if_board_history(readPath,source,role);
    if ~isempty(fieldnames(savedSettings)), draft=savedSettings; end
end
if isfield(options,'initial_settings'), draft=options.initial_settings; end
draft=completeDraft(draft);
snapshot=struct('is_open',false,'state_known',false); busy=false; externalBusy=false;
applicable=true; applicabilityReason='当前测量位置不使用 RX 中频控制。';
selectedSubband=1; lastRejection=struct();
selectedPort=historyPort;
if isfield(cfg,'serial') && isfield(cfg.serial,'port'), selectedPort=char(cfg.serial.port); end
portState=msiq.if_board_ports(source,selectedPort,field(options,'port_list_fn',[]),['MOCK_' upper(role)]);
selectedPort=portState.values{portState.index}; selectedAvailable=portState.available;
dispatcher=[];
if isfield(options,'dispatch'), dispatch=options.dispatch;
else, dispatcher=msiq.IfBoardDispatch(offline); dispatch=@dispatcher.send; end
bg=[.95 .97 .98];
panel=uipanel(parent,'Units','pixels','Title',[upper(role) ' 中频衰减'], ...
    'FontSize',16,'FontWeight','bold','BackgroundColor',bg,'Tag',['if_' role '_panel']);
portLabel=text('串口'); port=uicontrol(panel,'Style','popupmenu','FontSize',13,'String',portState.labels, ...
    'Value',portState.index,'Tag','if_port','Callback',@portChanged);
refreshPortsButton=button('刷新',@(~,~) refreshPorts());
connect=button('连接',@connectBoard); import=button('配置',@openConfig);
down=button('下发',@initialize); set(down,'TooltipString','发送本板完整六路设置；RX 同时关闭全部 AGC。');
selection=uicontrol(panel,'Style','popupmenu','String',arrayfun(@(n)sprintf('子带 %d',n),1:6,'UniformOutput',false), ...
    'FontSize',13,'Callback',@selectionChanged,'Tag','if_subband');
kinds={'rf'}; if strcmp(role,'rx'), kinds={'rf','i','q'}; end
nc=numel(kinds); headings=gobjects(1,nc); edits=gobjects(6,nc); minus=edits; plus=edits;
labels=gobjects(6,1); sent=labels;
for c=1:nc
    headings(c)=text([upper(kinds{c}) ' / dB']);
    for r=1:6
        edits(r,c)=uicontrol(panel,'Style','edit','FontSize',13,'String','', ...
            'Callback',@(src,~) editValue(r,c,get(src,'String')), ...
            'Tag',sprintf('if_%s_%d',kinds{c},r));
        minus(r,c)=button('−',@(~,~) step(r,c,-.5));
        plus(r,c)=button('+',@(~,~) step(r,c,.5));
    end
end
for r=1:6, labels(r)=text(sprintf('%d',r)); sent(r)=text('已发送：—'); set(sent(r),'FontSize',12); end
status=text('未连接 · 设置尚未下发'); set(status,'FontSize',12,'ForegroundColor',[.55 .25 .10]);
if ~offline && all(isnan(draft.rf)), set(status,'String','无实测历史：请填写六路值后下发。'); end
if ~isempty(historyNote), set(status,'String',historyNote); end
if ~isempty(configNote), set(status,'String',configNote); end
configDialog=[];
detail=text('点击配置设置通信参数和允许衰减范围。'); set(detail,'FontSize',12);
closeCallback=@()[];
if ~isempty(dispatcher), closeCallback=@dispatcher.close; end
widget=struct('panel',panel,'layout',@layout,'update',@update,'setBusy',@setBusy, ...
    'setApplicable',@setApplicable,'isApplicable',@isApplicable,'isBusy',@isBusy, ...
    'getLastRejection',@getLastRejection,'getSelection',@getSelection,'setSelection',@setSelection,'getDraft',@getDraft,'getSnapshot',@getSnapshot,'getConfig',@getConfig, ...
    'close',@closePanel,'loadConfig',@loadConfig,'refreshPorts',@refreshPorts,'getRecordPath',@()record, ...
    'controls',struct('edits',edits,'plus',plus,'minus',minus,'port',port,'refresh_ports',refreshPortsButton, ...
    'config',import,'connect',connect,'down',down,'selection',selection,'status',status,'detail',detail));
% TX edits each RF row independently; the selector is only meaningful for
% RX target-subband operations and is kept hidden for API compatibility.
if strcmp(role,'tx') || field(options,'external_selection',false)
    set(selection,'Visible','off');
end
layout([0 0 400 650]); refresh();
    function setSelection(value)
        assert(isscalar(value) && ismember(value,1:6),'msiq:ifboard:subband','子带必须为 1–6。');
        selectedSubband=value; set(selection,'Value',value); refresh();
    end
    function h=text(value)
        h=uicontrol(panel,'Style','text','String',value,'FontSize',13,'HorizontalAlignment','left','BackgroundColor',bg);
    end
    function h=button(value,callback)
        h=uicontrol(panel,'Style','pushbutton','String',value,'FontSize',13,'Callback',callback);
    end
    function layout(position)
        set(panel,'Position',position); w=position(3); h=position(4); y=h-55;
        set(portLabel,'Position',[10 y 45 26]); set(port,'Position',[56 y max(80,w-134) 30]);
        set(refreshPortsButton,'Position',[w-72 y 62 30]); y=y-38;
        set(connect,'Position',[10 y 80 30]); set(import,'Position',[100 y 80 30]);
        if strcmp(role,'tx')
            % TX has no target-subband action. Put its only board action on
            % the same toolbar row so the hidden compatibility control
            % cannot cover it or consume layout space.
            set(down,'Position',[w-78 y 68 30]);
            set(selection,'Position',[0 0 1 1]);
            y=y-34;
        else
            y=y-34;
            set(selection,'Position',[10 y max(95,w-96) 30]); set(down,'Position',[w-78 y 68 30]); y=y-38;
        end
        cellw=(w-38)/nc;
        for c=1:nc, set(headings(c),'Position',[30+(c-1)*cellw y cellw 24]); end
        y=y-33;
        for r=1:6
            set(labels(r),'Position',[8 y 22 28]);
            for c=1:nc
                x=30+(c-1)*cellw; bw=22; ew=cellw-2*bw-6;
                set(minus(r,c),'Position',[x y bw 28]);
                set(edits(r,c),'Position',[x+bw y ew 28]);
                set(plus(r,c),'Position',[x+bw+ew y bw 28]);
            end
            set(sent(r),'Position',[30 y-23 w-40 22]); y=y-61;
        end
        set(status,'Position',[10 max(35,y-25) w-20 48]);
        set(detail,'Position',[10 max(2,y-82) w-20 44]);
    end
    function refresh()
        if ~ishghandle(panel), return; end
        set(selection,'Value',selectedSubband); set(port,'Value',portState.index);
        set([edits(:);minus(:);plus(:);connect;import;port;selection;refreshPortsButton;down],'TooltipString','');
        for c=1:nc
            key=kinds{c};
            for r=1:6
                value=draft.(key)(r); valueText=''; if isfinite(value), valueText=sprintf('%.1f',value); end
                set(edits(r,c),'String',valueText);
                color=[1 1 1];
                if ~strcmp(role,'tx') && r==get(selection,'Value'), color=[.86 .94 1]; end
                set(edits(r,c),'BackgroundColor',color);
                if hasLimits(key,r)
                    lim=cfg.limits.(key)(r,:); tip=sprintf('批准范围 %.1f–%.1f dB；步进 0.5 dB',lim);
                else, tip='批准范围尚未配置'; end
                set(edits(r,c),'TooltipString',tip);
            end
        end
        for r=1:6
            parts={};
            if isfield(snapshot,'sent')
                for c=1:nc
                    key=kinds{c};
                    if isfield(snapshot.sent,key) && isfinite(snapshot.sent.(key)(r))
                        parts{end+1}=sprintf('%s %.1f',upper(key),snapshot.sent.(key)(r)); %#ok<AGROW>
                    end
                end
            end
            if isempty(parts), parts={'—'}; end
            set(sent(r),'String',['已发送：' strjoin(parts,' / ')]);
        end
        enable=onoff(~busy && ~externalBusy);
        set([edits(:);minus(:);plus(:);connect;import;port;selection],'Enable',enable);
        [ready,reason]=initialReady();
        set(down,'Enable',onoff(~busy && ~externalBusy && field(snapshot,'is_open',false) && ready));
        if ready
            set(down,'TooltipString','发送本板完整六路设置；RX 同时关闭全部 AGC。');
            set(detail,'String','批准范围见输入框提示。');
        else, set(down,'TooltipString',reason); set(detail,'String',reason); end
        if field(snapshot,'is_open',false), set(connect,'String','断开'); else, set(connect,'String','连接'); end
        set(port,'Enable',onoff(~busy && ~externalBusy && ~field(snapshot,'is_open',false)));
        set(refreshPortsButton,'Enable',onoff(~busy && ~externalBusy && ~field(snapshot,'is_open',false) && ~offline));
        if offline, set(port,'Enable','off'); end
        set(import,'Enable',onoff(~busy && ~externalBusy && ~field(snapshot,'is_open',false)));
        if ~field(snapshot,'is_open',false) && ~offline
            set(connect,'Enable',onoff(~busy && ~externalBusy && connectReady()));
            set(connect,'TooltipString','请点击“配置”填写通信参数并确认适用板卡。');
            if ~connectReady(), set(detail,'String','请点击“配置”完成通信设置及协议确认。'); end
            if ~selectedAvailable, set(detail,'String',portState.message); end
        end
        if ~applicable
            set([edits(:);minus(:);plus(:);connect;import;port;selection;refreshPortsButton;down], ...
                'Enable','off','TooltipString',applicabilityReason);
        end
    end
    function [ready,reason]=initialReady()
        ready=false; reason='请补全六路数值和批准范围。';
        for index=1:nc
            key=kinds{index};
            if ~isfield(draft,key) || numel(draft.(key))~=6 || any(~isfinite(draft.(key))), return; end
            for row=1:6
                if ~hasLimits(key,row), return; end
                try
                    accepted=msiq.if_board_quantize(draft.(key)(row),cfg.limits.(key)(row,:));
                    if accepted~=draft.(key)(row), reason='数值超出批准范围或不是 0.5 dB 档位。'; return; end
                catch, return; end
            end
        end
        ready=true; reason='';
    end
    function ready=connectReady()
        ready=false;
        if ~isfield(cfg,'runtime') || ~field(cfg.runtime,'protocol_verified',false) || ~isfield(cfg,'serial'), return; end
        keys={'baud_rate','data_bits','parity','stop_bits','flow_control','timeout','protocol_version'};
        for index=1:numel(keys)
            if ~isfield(cfg.serial,keys{index}) || isempty(cfg.serial.(keys{index})), return; end
        end
        ready=~isempty(selectedPort) && selectedAvailable;
    end
    function yes=hasLimits(key,r)
        yes=isfield(cfg,'limits') && isfield(cfg.limits,key) && isequal(size(cfg.limits.(key)),[6 2]) && all(isfinite(cfg.limits.(key)(r,:)));
    end
    function editValue(r,c,value)
        if rejectUnavailable('edit'), refresh(); return; end
        key=kinds{c};
        try
            assert(hasLimits(key,r),'msiq:ifboard:limits','请先配置本路批准范围。');
            value=msiq.if_board_quantize(value,cfg.limits.(key)(r,:));
            if isequal(draft.(key)(r),value), refresh(); return; end
            draft.(key)(r)=value; refresh();
            if field(snapshot,'state_known',false)
                request('board_adjust',struct('kind',key,'subband',r,'value',value));
            else, set(status,'String','设置已修改 · 尚未下发'); end
        catch err, set(status,'String',['未下发：' err.message]); refresh(); end
    end
    function step(r,c,delta)
        if rejectUnavailable('step'), refresh(); return; end
        value=draft.(kinds{c})(r);
        if ~isfinite(value), set(status,'String','请先输入本路衰减值。'); return; end
        editValue(r,c,value+delta);
    end
    function connectBoard(~,~)
        if rejectUnavailable('control'), refresh(); return; end
        if field(snapshot,'is_open',false), request('board_close',struct()); return; end
        if ~offline && ~connectReady(), set(status,'String','当前串口不可用或配置不完整，未连接。'); return; end
        cfg.role=role;
        cfg.initial_state_confirmed=false;
        if ~isfield(cfg,'serial'), cfg.serial=struct(); end
        cfg.serial.port=selectedPort;
        request('board_connect',struct('cfg',cfg));
    end
    function initialize(~,~), request('board_initialize',struct('settings',draft)); end
    function request(action,payload)
        if rejectUnavailable('control'), refresh(); return; end
        busy=true; refresh(); set(status,'String','正在执行板卡操作…');
        try dispatch(action,payload,@(response) finish(action,response));
        catch err, finish(action,struct('ok',false,'error',err.message)); end
    end
    function finish(action,response)
        busy=false;
        if ~ishghandle(panel), return; end
        if isfield(response,'snapshot') && ~isempty(fieldnames(response.snapshot)), snapshot=response.snapshot; end
        if field(response,'ok',false)
            if strcmp(action,'board_connect'), set(status,'String','已连接 · 设置尚未下发');
            elseif strcmp(action,'board_close'), set(status,'String','已断开 · 再次连接后需要下发');
            else
                set(status,'String','已发送，未回读');
                if field(snapshot,'state_known',false)
                    draft=snapshot.state;
                    saveSettings();
                end
            end
        else
            if ~strcmp(action,'board_connect'), snapshot.state_known=false; end
            set(status,'String',['状态未确认：' field(response,'error','操作未完成')]);
        end
        refresh();
        if isfield(options,'onChange'), options.onChange(snapshot); end
    end
    function update(value)
        snapshot=value;
        if field(value,'state_known',false) && ~busy
            draft=value.state; set(status,'String','已发送，未回读'); saveSettings();
        elseif ~field(value,'state_known',false)
            set(status,'String','状态未确认 · 需要完整下发');
        end
        refresh();
    end
    function saveSettings()
        if persist
            try
                if isfile(record)
                    [~,~,existingNote]=msiq.if_board_history(record,source,role);
                    assert(~any(contains(existingNote,{'其他来源','模拟历史','角色不匹配','来源无法识别'})), ...
                        'msiq:ifboard:historySource','历史路径属于另一来源，未覆盖原文件。');
                end
                msiq.atomic_save(record,struct('settings',draft,'role',role,'source_mode',sourceTag,'port',selectedPort));
            catch err, set(status,'String',['已发送；历史保存失败：' err.message]); end
        end
    end
    function value=getDraft(), value=draft; end
    function value=isApplicable(), value=applicable; end
    function value=isBusy(), value=busy; end
    function value=getLastRejection(), value=lastRejection; end
    function value=getSelection(), value=selectedSubband; end
    function value=getSnapshot(), value=snapshot; end
    function value=getConfig()
        value=cfg;
        if ~isfield(value,'serial'), value.serial=struct(); end
        value.serial.port=selectedPort;
    end
    function portChanged(~,~)
        if rejectUnavailable('configuration') || field(snapshot,'is_open',false), refresh(); return; end
        index=get(port,'Value'); selectedPort=portState.values{index}; portState.index=index;
        selectedAvailable=~isempty(selectedPort) && ~contains(portState.labels{index},'（不可用）');
        if isempty(selectedPort), portState.message='请选择本次板卡的串口。'; end
        refresh();
    end
    function refreshPorts()
        if rejectUnavailable('ports') || field(snapshot,'is_open',false) || offline, refresh(); return; end
        portState=msiq.if_board_ports(source,selectedPort,field(options,'port_list_fn',[]));
        selectedPort=portState.values{portState.index}; selectedAvailable=portState.available;
        set(port,'String',portState.labels,'Value',portState.index); refresh();
    end
    function setBusy(value), externalBusy=logical(value); refresh(); end
    function setApplicable(value,reason)
        validateattributes(value,{'logical','numeric'},{'scalar'});
        applicable=logical(value);
        if nargin>1 && ~isempty(reason), applicabilityReason=char(reason); end
        % Close a stale editor so it cannot later commit under another position.
        if ~applicable && ~isempty(configDialog) && isgraphics(configDialog)
            delete(configDialog); configDialog=[];
        end
        refresh();
    end
    function selectionChanged(~,~)
        if rejectUnavailable('selection'), refresh(); return; end
        selectedSubband=get(selection,'Value'); refresh();
    end
    function rejected=rejectUnavailable(action)
        rejected=~applicable || busy || externalBusy;
        if ~rejected, return; end
        reason='板卡操作尚未完成，当前操作未执行。';
        if ~applicable, reason=applicabilityReason; end
        lastRejection=struct('action',action,'reason',reason,'timestamp',datestr(now,30));
        if isfield(options,'onRejected'), options.onRejected(lastRejection); end
    end
    function closePanel()
        if ~isempty(configDialog) && isgraphics(configDialog), delete(configDialog); end
        closeCallback();
    end
    function openConfig(~,~)
        if rejectUnavailable('configuration') || field(snapshot,'is_open',false), refresh(); return; end
        if ~isempty(configDialog) && isgraphics(configDialog), figure(configDialog); return; end
        configDialog=msiq.if_board_config_dialog(getConfig(),role,struct( ...
            'on_save',@saveConfig,'visible',get(ancestor(panel,'figure'),'Visible')));
    end
    function saveConfig(candidate)
        assert(applicable,'msiq:ifboard:notApplicable','%s',applicabilityReason);
        assert(~busy && ~externalBusy && ~field(snapshot,'is_open',false), ...
            'msiq:ifboard:connected','请先断开板卡再修改配置。');
        importedInitial=field(candidate,'dialog_imported_initial',false);
        if isfield(candidate,'dialog_imported_initial'), candidate=rmfield(candidate,'dialog_imported_initial'); end
        candidate=msiq.if_board_config_dialog('validate',candidate,role);
        candidate.serial.port=selectedPort; % Port selection stays with the main panel.
        assert(strcmp(candidate.mode,cfg.mode),'msiq:ifboard:source','配置来源不匹配。');
        nextDraft=draft;
        if importedInitial && isfield(candidate,'initial_state'), nextDraft=completeDraft(candidate.initial_state); end
        if persist
            if isfile(configPath)
                previous=load(configPath);
                assert(isfield(previous,'role') && strcmp(previous.role,role) && ...
                    isfield(previous,'source_mode') && strcmp(previous.source_mode,sourceTag), ...
                    'msiq:ifboard:historySource','此配置文件属于其他角色或来源，未覆盖。');
            end
            msiq.atomic_save(configPath,struct('config',candidate,'role',role,'source_mode',sourceTag));
        end
        cfg=candidate; draft=nextDraft;
        selectedPort=field(cfg.serial,'port',selectedPort);
        portState=msiq.if_board_ports(source,selectedPort,field(options,'port_list_fn',[]),['MOCK_' upper(role)]);
        selectedPort=portState.values{portState.index}; selectedAvailable=portState.available;
        set(port,'String',portState.labels,'Value',portState.index);
        set(status,'String','配置已保存 · 尚未连接或下发'); refresh();
    end
    function loadConfig(loaded)
        assert(applicable,'msiq:ifboard:notApplicable','%s',applicabilityReason);
        assert(~busy && ~externalBusy && ~field(snapshot,'is_open',false), ...
            'msiq:ifboard:connected','请先断开板卡再更换串口配置。');
        candidate=normalizeConfig(loaded,role,offline,true);
        candidateDraft=draft;
        if isfield(candidate,'initial_state'), candidateDraft=completeDraft(candidate.initial_state); end
        candidatePort='';
        if isfield(candidate,'serial') && isfield(candidate.serial,'port'), candidatePort=candidate.serial.port; end
        % Commit only after every imported field passed validation.
        candidatePorts=msiq.if_board_ports(source,candidatePort,field(options,'port_list_fn',[]),['MOCK_' upper(role)]);
        cfg=candidate; draft=candidateDraft; portState=candidatePorts;
        selectedPort=portState.values{portState.index}; selectedAvailable=portState.available;
        set(port,'String',portState.labels,'Value',portState.index);
        set(status,'String','配置已载入 · 尚未连接或下发'); refresh();
    end
end
function cfg=normalizeConfig(cfg,role,offline,strict)
assert(isstruct(cfg) && isscalar(cfg),'msiq:ifboard:config','板卡配置必须是单个配置对象。');
if offline
    cfg.mode='mock';
elseif ~isfield(cfg,'mode') || isempty(cfg.mode)
    cfg.mode='live';
else
    assert(strcmp(cfg.mode,'live'),'msiq:ifboard:modeMismatch', ...
        '实机界面不接受模拟配置；请提供独立的实机批准配置。');
end
cfg.role=role;
if ~strict, return; end
keys={'rf'}; if strcmp(role,'rx'), keys={'rf','i','q'}; end
assert(isfield(cfg,'limits') && isstruct(cfg.limits),'msiq:ifboard:config','缺少完整批准范围。');
for index=1:numel(keys)
    key=keys{index};
    assert(isfield(cfg.limits,key),'msiq:ifboard:config','缺少 %s 的六路批准范围。',upper(key));
    values=cfg.limits.(key);
    assert(isnumeric(values) && isequal(size(values),[6 2]) && all(isfinite(values(:))) && ...
        all(values(:)>=0 & values(:)<=31.5) && all(ceil(2*values(:,1))<=floor(2*values(:,2))), ...
        'msiq:ifboard:config','%s 批准范围必须是合法的六行两列数值。',upper(key));
    if isfield(cfg,'initial_state')
        assert(isstruct(cfg.initial_state) && isfield(cfg.initial_state,key), ...
            'msiq:ifboard:config','导入初始设置时必须提供完整六路 %s。',upper(key));
        msiq.instruments.if_board_encode(key,cfg.initial_state.(key));
        initial=cfg.initial_state.(key)(:);
        assert(all(initial>=values(:,1) & initial<=values(:,2)), ...
            'msiq:ifboard:config','导入初始设置超出批准范围。');
    end
end
if isfield(cfg,'runtime')
    assert(isstruct(cfg.runtime) && isscalar(cfg.runtime),'msiq:ifboard:config','协议确认配置无效。');
end
if isfield(cfg,'serial')
    serial=cfg.serial;
    assert(isstruct(serial) && isscalar(serial),'msiq:ifboard:config','串口配置无效。');
    if isfield(serial,'port'), assert((ischar(serial.port) && isrow(serial.port)) || (isstring(serial.port) && isscalar(serial.port)), ...
        'msiq:ifboard:config','串口名称必须是文本。'); end
    for name={'baud_rate','timeout'}
        key=name{1};
        if isfield(serial,key), validateattributes(serial.(key),{'numeric'},{'scalar','positive','finite'}); end
    end
end
end
function draft=completeDraft(draft)
for name={'rf','i','q'}
    key=name{1};
    if ~isfield(draft,key) || ~isnumeric(draft.(key)) || numel(draft.(key))~=6
        draft.(key)=nan(1,6);
    else, draft.(key)=double(draft.(key)(:).'); end
end
end
function value=field(s,key,fallback)
if isfield(s,key), value=s.(key); else, value=fallback; end
end
function value=onoff(flag)
if flag, value='on'; else, value='off'; end
end
function value=ternarySource(offline)
if offline, value='mock'; else, value='live'; end
end
