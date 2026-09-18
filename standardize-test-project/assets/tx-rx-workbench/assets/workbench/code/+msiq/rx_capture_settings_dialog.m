function dlg=rx_capture_settings_dialog(parent,profile,options)
%RX_CAPTURE_SETTINGS_DIALOG Edit local capture policy without instrument access.
if nargin<3,options=struct();end
if nargin<1,parent=[];end
source=field(options,'source_mode','live');
opts=struct('source_mode',source);
baseline=profile; candidate=msiq.rx_capture_settings('normalize',baseline,struct(),opts);
path=field(options,'preferences_path',msiq.rx_capture_settings('path',profile,[],opts));
bg=[.96 .97 .98];
dlg=figure('Name','RX 采集设置','NumberTitle','off','MenuBar','none','ToolBar','none', ...
    'Position',[100 70 800 620],'Color',bg,'Resize','off','Visible',field(options,'visible','on'), ...
    'Tag','rx_capture_settings_dialog');
if ~isempty(parent)&&isgraphics(parent),setappdata(dlg,'parent_workbench',parent);end
uicontrol(dlg,'Style','text','String','采集设置','FontSize',16,'FontWeight','bold', ...
    'Position',[20 576 755 30],'BackgroundColor',bg,'HorizontalAlignment','left');
tabs=uitabgroup(dlg,'Units','pixels','Position',[20 104 760 465]);
general=uitab(tabs,'Title','日常采集'); limitsTab=uitab(tabs,'Title','高级'); balanceTab=uitab(tabs,'Title','配平');
edits=struct(); specs={}; arrows=struct();
auto=uicontrol(general,'Style','checkbox','String','自动量程', ...
    'Position',[18 390 715 32],'FontSize',13,'Tag','rx_capture_auto_range','Callback',@(~,~)refreshEnabled());
add(general,'scope.target_divisions','目标占格',340,'格',1,false);
add(general,'scope.edge_margin_divisions','上下各留余量',290,'格',1,false);
add(general,'policy.settle_s','调整后稳定等待',240,'ms',1000,false);
add(limitsTab,'scope.max_adjustments','每个正式点调整上限',385,'次',1,true);
add(limitsTab,'scope.sample_rate_tolerance','采样率检查容差',335,'%',100,false);
add(limitsTab,'scope.window_tolerance','采集窗口检查容差',285,'%',100,false);
keys={'balance_tolerance_db','balance_step_db','max_balance_adjustments','ber_degradation','mer_degradation_db','ber_recovery','mer_recovery_db','range_jump_db'};
labels={'配平容差','配平步进','配平调整上限','BER 退化容差','MER 退化容差','BER 恢复容差','MER 恢复容差','量程突跳判据'};
units={'dB','dB','次','%','dB','%','dB','dB'};
scales=[1 1 1 100 1 100 1 1];
for k=1:numel(keys),add(balanceTab,['policy.' keys{k}],labels{k},395-(k-1)*42,units{k},scales(k),k==3);end
device=figure('Name','RX 设备配置','NumberTitle','off','MenuBar','none','ToolBar','none', ...
    'Position',[130 120 800 440],'Color',bg,'Resize','off','Visible','off', ...
    'Tag','rx_capture_device_config');
set(device,'CloseRequestFcn',@(~,~)set(device,'Visible','off'));
set(dlg,'DeleteFcn',@(~,~)closeDevice());
freshStatus=uicontrol(device,'Style','text','Position',[18 402 710 28],'FontSize',12,'HorizontalAlignment','left');
freshKeys={'reset_command','start_command','completion_query','pending_response','complete_response','timeout_s','poll_s'};
freshLabels={'复位命令','启动命令','完成查询','未完成响应','完成响应','完成等待上限','轮询间隔'};
for k=1:numel(freshKeys)
    unit='';scale=1;if k==6,unit='s';elseif k==7,unit='ms';scale=1000;end
    add(device,['scope.fresh.' freshKeys{k}],freshLabels{k},360-(k-1)*43,unit,scale,false);
end
uicontrol(device,'Style','pushbutton','String','返回','Position',[665 12 100 32], ...
    'FontSize',13,'Callback',@(~,~)set(device,'Visible','off'));
status=uicontrol(dlg,'Style','text','String','', ...
    'Position',[20 50 760 49],'FontSize',12,'ForegroundColor',[.45 .2 .1],'BackgroundColor',bg,'HorizontalAlignment','left');
importButton=button('导入',20,@importSettings);exportButton=button('导出',125,@exportSettings);
deviceButton=button('设备配置',230,@(~,~)set(device,'Visible','on'));
saveButton=button('保存',570,@saveSettings);cancelButton=button('取消',675,@(~,~)delete(dlg));
controls=struct('auto_range',auto,'edits',edits,'save',saveButton,'cancel',cancelButton, ...
    'import',importButton,'export',exportButton,'status',status,'fresh_status',freshStatus,'tabs',tabs,'device',deviceButton,'device_window',device,'arrows',arrows);
setappdata(dlg,'rx_capture_settings_controls',controls);
% Programmatic import/export exercise the same paths without a modal chooser.
setappdata(dlg,'rx_capture_settings_import',@applyImport);
setappdata(dlg,'rx_capture_settings_export',@applyExport);
setappdata(dlg,'rx_capture_settings_applicability',@setBalanceApplicable);
populate();
    function add(panel,key,label,y,unit,scale,integer)
        uicontrol(panel,'Style','text','String',label,'Position',[18 y 285 29],'FontSize',13,'HorizontalAlignment','left');
        id=strrep(key,'.','_');
        edits.(id)=uicontrol(panel,'Style','edit','Position',[312 y+2 320 29],'FontSize',13, ...
            'HorizontalAlignment','left','Tag',['rx_capture_' id]);
        uicontrol(panel,'Style','text','String',unit,'Position',[678 y 64 29],'FontSize',13,'HorizontalAlignment','left');
        if integer
            arrows.(id)=[uicontrol(panel,'Style','pushbutton','String','▲','FontSize',8,'Position',[638 y+21 28 20], ...
                'Callback',@(~,~)step(id,1)),uicontrol(panel,'Style','pushbutton','String','▼','FontSize',8, ...
                'Position',[638 y+1 28 20],'Callback',@(~,~)step(id,-1))];
        end
        specs(end+1,:)={key,id,scale};
    end
    function step(id,delta)
        if ~strcmp(get(edits.(id),'Enable'),'on'),return;end
        v=str2double(get(edits.(id),'String'));if ~isfinite(v),v=0;end
        set(edits.(id),'String',num2str(max(0,round(v)+delta)));
    end
    function setBalanceApplicable(value)
        options.balance_applicable=logical(value);refreshEnabled();
    end
    function refreshEnabled()
        enabled=logical(get(auto,'Value'));balance=field(options,'balance_applicable',true);
        for id={'scope_max_adjustments'}
            setEnabled(id{1},enabled);
        end
        setEnabled('policy_settle_s',enabled||balance);
        for j=1:numel(keys),setEnabled(['policy_' keys{j}],balance);end
    end
    function setEnabled(id,enabled)
        value='off';if enabled,value='on';end
        set(edits.(id),'Enable',value);if isfield(arrows,id),set(arrows.(id),'Enable',value);end
    end
    function closeDevice()
        if isgraphics(device),delete(device);end
    end
    function b=button(label,x,cb)
        b=uicontrol(dlg,'Style','pushbutton','String',label,'Position',[x 12 100 32],'FontSize',13,'Callback',cb);
    end
    function populate()
        set(auto,'Value',candidate.scope.auto_range_enabled);
        for j=1:size(specs,1)
            value=readValue(candidate,specs{j,1});
            if isnumeric(value),value=value*specs{j,3};end
            if isnumeric(value)
                if isempty(value)||all(isnan(value)),value='';else,value=strtrim(sprintf('%.15g ',value));end
            end
            set(edits.(specs{j,2}),'String',value);
        end
        title='新采集判据：未验证';if candidate.scope.fresh.verified,title='新采集判据：已验证';end
        refreshEnabled();set(freshStatus,'String',title);setappdata(dlg,'rx_capture_settings_profile',candidate);
    end
    function result=collect()
        result=candidate;result.scope.auto_range_enabled=logical(get(auto,'Value'));
        for j=1:size(specs,1)
            key=specs{j,1};text=strtrim(get(edits.(specs{j,2}),'String'));
            old=readValue(candidate,key);
            if isnumeric(old)
                if isempty(text),value=NaN;
                else,value=str2double(text);assert(isfinite(value),'msiq:rx:settingsValue','请输入有效数值，未知可留空。');end
            else,value=text;end
            if isnumeric(value),value=value/specs{j,3};end
            result=writeValue(result,key,value);
        end
        result=msiq.rx_capture_settings('normalize',baseline,result,opts);
    end
    function saveSettings(~,~)
        try
            result=collect();
            if isfield(options,'validateSave'),options.validateSave();end
            if ~isempty(path),msiq.rx_capture_settings('save',result,path,opts);end
            if isfield(options,'onSave'),options.onSave(result);end
            delete(dlg);
        catch ex,set(status,'String',ex.message);end
    end
    function importSettings(~,~)
        [file,folder]=uigetfile({'*.mat;*.json','采集设置 (*.mat, *.json)'});if isequal(file,0),return;end
        try,applyImport(fullfile(folder,file));catch ex,set(status,'String',ex.message);end
    end
    function applyImport(file)
        candidate=msiq.rx_capture_settings('import',baseline,file,opts);populate();
        set(status,'String','已导入');
    end
    function exportSettings(~,~)
        [file,folder]=uiputfile({'*.mat','MAT 配置';'*.json','JSON 配置'},'导出采集设置');if isequal(file,0),return;end
        try,applyExport(fullfile(folder,file));catch ex,set(status,'String',ex.message);end
    end
    function applyExport(file)
        result=collect();msiq.rx_capture_settings('export',result,file,opts);set(status,'String','已导出采集设置。');
    end
end
function value=readValue(s,path)
keys=strsplit(path,'.');value=s;for k=1:numel(keys),value=value.(keys{k});end
end
function s=writeValue(s,path,value)
keys=strsplit(path,'.');
if numel(keys)==2,s.(keys{1}).(keys{2})=value;else,s.(keys{1}).(keys{2}).(keys{3})=value;end
end
function v=field(s,n,d),if isfield(s,n),v=s.(n);else,v=d;end;end
