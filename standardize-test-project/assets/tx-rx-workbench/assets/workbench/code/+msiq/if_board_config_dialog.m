function dlg=if_board_config_dialog(cfg,role,options)
%IF_BOARD_CONFIG_DIALOG Local-only TX/RX communication and approved-range editor.
% The validate action never creates a figure, reads defaults or accesses hardware.
if ischar(cfg) && strcmp(cfg,'validate')
    dlg=validateConfig(role,options); return;
end
if nargin<3, options=struct(); end
assert(any(strcmp(role,{'tx','rx'})),'msiq:ifboard:role','请选择 TX 或 RX 板卡。');
assert(isstruct(cfg) && isscalar(cfg),'msiq:ifboard:config','板卡配置必须是单个配置对象。');
base=mergeMissing(cfg,msiq.if_board_vendor_defaults(role));
if isfield(base,'dialog_imported_initial'), base=rmfield(base,'dialog_imported_initial'); end
importedInitial=false;
if ~isfield(base,'mode'), base.mode='live'; end
base.role=role;
if ~isfield(base,'runtime'), base.runtime=struct(); end
if ~isfield(base.runtime,'protocol_verified'), base.runtime.protocol_verified=false; end
keys={'rf'}; if strcmp(role,'rx'), keys={'rf','i','q'}; end
bg=[.96 .97 .98];
dlg=figure('Name',[upper(role) ' 中频板卡配置'],'NumberTitle','off','MenuBar','none', ...
    'ToolBar','none','Units','pixels','Position',[80 40 850 630],'Resize','off', ...
    'Color',bg,'Visible',getfieldOr(options,'visible','on'),'Tag','if_board_config_dialog');
label('通信设置',[18 584 790 30],16,'bold');
evidence=label('厂家资料已核对：115200、8 位、无校验、1 停止位。无流控与 2 秒超时为程序默认。', ...
    [18 547 812 34],12,'normal');
set(evidence,'TooltipString',getfieldOr(base,'evidence_note','保存仅保存在本机，不连接串口、不下发衰减。'));
serialKeys={'baud_rate','data_bits','parity','stop_bits','flow_control','timeout','protocol_version'};
serialLabels={'波特率 / bit/s','数据位','校验','停止位','流控','通信超时 / s','控制协议'};
serialControls=struct();
for n=1:numel(serialKeys)
    col=mod(n-1,2); row=floor((n-1)/2); x=18+col*418; y=512-row*43;
    label(serialLabels{n},[x y 232 28],13,'normal');
    serialControls.(serialKeys{n})=uicontrol(dlg,'Style','edit','Position',[x+237 y+2 150 28], ...
        'FontSize',13,'HorizontalAlignment','left','Tag',['if_config_' serialKeys{n}]);
end
popupValues=struct('parity',{{'','none','odd','even','mark','space'}}, ...
    'flow_control',{{'','none','hardware','software'}}, ...
    'data_bits',{{'','5','6','7','8'}},'stop_bits',{{'','1','1.5','2'}});
set(serialControls.parity,'Style','popupmenu','String',{'请选择','无校验','奇校验','偶校验','标记校验','空格校验'});
set(serialControls.flow_control,'Style','popupmenu','String',{'请选择','无流控','硬件流控','软件流控'});
set(serialControls.data_bits,'Style','popupmenu','String',{'请选择','5','6','7','8'});
set(serialControls.stop_bits,'Style','popupmenu','String',{'请选择','1','1.5','2'});
set(serialControls.protocol_version,'Style','text','BackgroundColor',bg,'Position',[160 383 265 28]);
verified=uicontrol(dlg,'Style','checkbox','String','已核对本板卡通信参数与协议','FontSize',13, ...
    'BackgroundColor',bg,'Position',[436 385 398 30],'Tag','if_config_protocol_verified');
label('批准衰减范围 / dB',[18 340 800 30],16,'bold');
label('每类填写完整六路，或将下限、上限一起留空。范围未填写时可连接，不能下发。',[18 311 810 24],12,'normal');
columns={};
for n=1:numel(keys), columns=[columns {[upper(keys{n}) ' 下限'],[upper(keys{n}) ' 上限']}]; end %#ok<AGROW>
table=uitable(dlg,'Position',[18 117 812 188],'FontSize',13,'ColumnName',columns, ...
    'ColumnEditable',true(1,2*numel(keys)),'RowName',arrayfun(@(n)sprintf('子带 %d',n),1:6,'UniformOutput',false), ...
    'ColumnWidth',repmat({floor(730/(2*numel(keys)))},1,2*numel(keys)),'Tag','if_config_limits');
status=label('',[18 58 812 51],12,'normal'); set(status,'ForegroundColor',[.75 .15 .1]);
importButton=uicontrol(dlg,'Style','pushbutton','String','导入配置','FontSize',13, ...
    'Position',[18 15 110 32],'Callback',@importConfig);
save=uicontrol(dlg,'Style','pushbutton','String','保存','FontSize',13,'Position',[608 15 100 32],'Callback',@saveConfig);
cancel=uicontrol(dlg,'Style','pushbutton','String','取消','FontSize',13,'Position',[724 15 106 32],'Callback',@(~,~)delete(dlg));
controls=struct('save',save,'cancel',cancel,'import',importButton,'protocol_verified',verified, ...
    'serial',serialControls,'limits',table,'status',status);
setappdata(dlg,'if_board_config_controls',controls); populate();
    function h=label(value,pos,size,weight)
        h=uicontrol(dlg,'Style','text','String',value,'Position',pos,'FontSize',size, ...
            'FontWeight',weight,'BackgroundColor',bg,'HorizontalAlignment','left');
    end
    function populate()
        s=getfieldOr(base,'serial',struct());
        for j=1:numel(serialKeys)
            value=getfieldOr(s,serialKeys{j},'');
            if isnumeric(value), value=num2str(value); end
            if isfield(popupValues,serialKeys{j})
                index=find(strcmpi(popupValues.(serialKeys{j}),value),1);
                if isempty(index), index=1; end
                set(serialControls.(serialKeys{j}),'Value',index);
            elseif strcmp(serialKeys{j},'protocol_version')
                title='已导入的板卡协议';
                if startsWith(string(value),'jh005'), title='JH005 六路控制（厂家配置）'; end
                set(serialControls.protocol_version,'String',title,'TooltipString',value);
            else, set(serialControls.(serialKeys{j}),'String',value); end
        end
        set(verified,'Value',getfieldOr(base.runtime,'protocol_verified',false));
        cells=repmat({''},6,2*numel(keys));
        limits=getfieldOr(base,'limits',struct());
        for j=1:numel(keys)
            if isfield(limits,keys{j}) && isequal(size(limits.(keys{j})),[6 2])
                cells(:,2*j-1:2*j)=num2cell(limits.(keys{j}));
            end
        end
        set(table,'Data',cells);
    end
    function saveConfig(~,~)
        try
            candidate=base;
            if isfield(candidate,'dialog_imported_initial'), candidate=rmfield(candidate,'dialog_imported_initial'); end
            s=getfieldOr(base,'serial',struct());
            for j=1:numel(serialKeys)
                if isfield(popupValues,serialKeys{j})
                    choices=popupValues.(serialKeys{j}); value=choices{get(serialControls.(serialKeys{j}),'Value')};
                elseif strcmp(serialKeys{j},'protocol_version'), value=base.serial.protocol_version;
                else, value=strtrim(get(serialControls.(serialKeys{j}),'String')); end
                if ismember(serialKeys{j},{'baud_rate','data_bits','stop_bits','timeout'}), value=str2double(value); end
                s.(serialKeys{j})=value;
            end
            candidate.serial=s; candidate.runtime.protocol_verified=logical(get(verified,'Value'));
            candidate.limits=getfieldOr(candidate,'limits',struct());
            cells=get(table,'Data'); if isnumeric(cells), cells=num2cell(cells); end
            for j=1:numel(keys)
                values=nan(6,2);
                for r=1:6
                    for c=1:2
                        value=cells{r,2*j-2+c};
                        if isnumeric(value) && isscalar(value), values(r,c)=value;
                        elseif ischar(value) || (isstring(value) && isscalar(value))
                            if ~isempty(strtrim(value))
                                values(r,c)=str2double(value);
                                assert(isfinite(values(r,c)),'msiq:ifboard:config','%s 子带 %d 的批准范围不是有效数值。',upper(keys{j}),r);
                            end
                        elseif ~isempty(value), error('msiq:ifboard:config','批准范围只能填写数值。'); end
                    end
                end
                candidate.limits.(keys{j})=values;
            end
            candidate=validateConfig(candidate,role);
            if importedInitial, candidate.dialog_imported_initial=true; end
            callback=getfieldOr(options,'on_save',[]);
            if ~isempty(callback), callback(candidate); end
            setappdata(dlg,'saved_config',candidate); delete(dlg);
        catch err
            set(status,'String',['未保存：' err.message]);
        end
    end
    function importConfig(~,~)
        try
            callback=getfieldOr(options,'import',[]);
            if ~isempty(callback)
                loaded=callback(); if isempty(loaded), return; end
            else
                [name,folder]=uigetfile({'*.json;*.mat','板卡配置文件'},'导入板卡配置');
                if isequal(name,0), return; end
                path=fullfile(folder,name); [~,~,ext]=fileparts(path);
                if strcmpi(ext,'.json'), loaded=jsondecode(fileread(path)); else, loaded=load(path); end
                if isfield(loaded,'board'), loaded=loaded.board; end
                if isfield(loaded,'config'), loaded=loaded.config; end
            end
            assert(isstruct(loaded) && isscalar(loaded),'msiq:ifboard:config','文件不是单个板卡配置。');
            if ~isfield(loaded,'mode') || isempty(loaded.mode)
                % Legacy files predate mode tags; never carry their confirmation forward.
                for sourceKey={'source_mode','source'}
                    if isfield(loaded,sourceKey{1})
                        sourceValue=char(string(loaded.(sourceKey{1})));
                        if strcmp(sourceValue,'measurement'), sourceValue='live'; end
                        if strcmp(sourceValue,'simulation'), sourceValue='mock'; end
                        assert(strcmp(sourceValue,base.mode),'msiq:ifboard:modeMismatch', ...
                            '导入文件的来源信息与当前实测／模拟不匹配。');
                    end
                end
                for fixtureKey={'mock_fixture','mock_fixture_applied'}
                    if ~isfield(loaded,fixtureKey{1}), continue; end
                    fixture=loaded.(fixtureKey{1});
                    assert((islogical(fixture)||isnumeric(fixture)) && isscalar(fixture) && ismember(fixture,[0 1]), ...
                        'msiq:ifboard:modeMismatch','导入文件的模拟标记无效。');
                    assert(logical(fixture)==strcmp(base.mode,'mock'),'msiq:ifboard:modeMismatch', ...
                        '导入文件的模拟标记与当前来源不匹配。');
                end
                loaded.mode=base.mode;
                if ~isfield(loaded,'runtime'), loaded.runtime=struct(); end
                assert(isstruct(loaded.runtime) && isscalar(loaded.runtime),'msiq:ifboard:config','协议确认信息无效。');
                loaded.runtime.protocol_verified=false;
            else
                assert(strcmp(loaded.mode,base.mode),'msiq:ifboard:modeMismatch', ...
                    '导入文件必须匹配当前实测／模拟来源。');
            end
            if isfield(loaded,'role'), assert(strcmp(loaded.role,role),'msiq:ifboard:role','导入文件的 TX/RX 角色不匹配。'); end
            if isfield(loaded,'dialog_imported_initial'), loaded=rmfield(loaded,'dialog_imported_initial'); end
            loaded.role=role; loaded=validateConfig(loaded,role);
            base=loaded; importedInitial=isfield(loaded,'initial_state'); populate(); set(evidence,'TooltipString',getfieldOr(base,'evidence_note','导入的本机配置；请核对现场板卡。')); set(status,'String','已导入供检查；点击保存才应用。');
        catch err, set(status,'String',['未导入：' err.message]); end
    end
end
function cfg=validateConfig(cfg,role)
assert(isstruct(cfg) && isscalar(cfg),'msiq:ifboard:config','板卡配置必须是单个配置对象。');
assert(any(strcmp(role,{'tx','rx'})),'msiq:ifboard:role','请选择 TX 或 RX 板卡。');
if isfield(cfg,'role'), assert(strcmp(cfg.role,role),'msiq:ifboard:role','配置的 TX/RX 角色不匹配。'); end
cfg.role=role;
assert(isfield(cfg,'mode') && any(strcmp(cfg.mode,{'live','mock'})),'msiq:ifboard:config','配置必须明确实测或模拟来源。');
assert(isfield(cfg,'serial') && isstruct(cfg.serial) && isscalar(cfg.serial),'msiq:ifboard:config','缺少通信参数。');
s=cfg.serial;
if isfield(s,'port')
    assert((ischar(s.port) && (isrow(s.port)||isempty(s.port))) || (isstring(s.port) && isscalar(s.port)), ...
        'msiq:ifboard:config','串口名称必须是文本。');
end
for pair={{'baud_rate','波特率'},{'data_bits','数据位'},{'stop_bits','停止位'},{'timeout','通信超时'}}
    p=pair{1}; key=p{1};
    assert(isfield(s,key) && isnumeric(s.(key)) && isscalar(s.(key)) && isfinite(s.(key)) && s.(key)>0, ...
        'msiq:ifboard:config','请填写有效的%s。',p{2});
end
assert(s.baud_rate==fix(s.baud_rate),'msiq:ifboard:config','波特率必须为正整数。');
assert(ismember(s.data_bits,[5 6 7 8]),'msiq:ifboard:config','数据位应为 5、6、7 或 8。');
assert(ismember(s.stop_bits,[1 1.5 2]),'msiq:ifboard:config','停止位应为 1、1.5 或 2。');
for key={'parity','flow_control','protocol_version'}
    name=key{1};
    assert(isfield(s,name) && ((ischar(s.(name)) && isrow(s.(name))) || (isstring(s.(name)) && isscalar(s.(name)))) && ...
        strlength(strtrim(string(s.(name))))>0,'msiq:ifboard:config','请补全校验、流控与协议版本。');
    s.(name)=char(strtrim(string(s.(name))));
end
s.parity=lower(s.parity); s.flow_control=lower(s.flow_control);
assert(any(strcmp(s.parity,{'none','odd','even','mark','space'})),'msiq:ifboard:config','校验值应为 none、odd、even、mark 或 space。');
assert(any(strcmp(s.flow_control,{'none','hardware','software'})),'msiq:ifboard:config','流控值应为 none、hardware 或 software。');
cfg.serial=s;
if ~isfield(cfg,'runtime'), cfg.runtime=struct(); end
assert(isstruct(cfg.runtime) && isscalar(cfg.runtime),'msiq:ifboard:config','协议确认信息无效。');
if ~isfield(cfg.runtime,'protocol_verified'), cfg.runtime.protocol_verified=false; end
v=cfg.runtime.protocol_verified;
assert((isnumeric(v)||islogical(v)) && isscalar(v) && isfinite(v) && ismember(v,[0 1]),'msiq:ifboard:config','协议确认值无效。');
cfg.runtime.protocol_verified=logical(v);
keys={'rf'}; if strcmp(role,'rx'), keys={'rf','i','q'}; end
if ~isfield(cfg,'limits'), cfg.limits=struct(); end
assert(isstruct(cfg.limits) && isscalar(cfg.limits),'msiq:ifboard:config','批准范围格式无效。');
for j=1:numel(keys)
    key=keys{j};
    if isfield(cfg.limits,key)
        values=cfg.limits.(key);
        if isempty(values) || (isnumeric(values) && isequal(size(values),[6 2]) && all(isnan(values(:))))
            cfg.limits=rmfield(cfg.limits,key);
        else
            assert(isnumeric(values) && isequal(size(values),[6 2]) && all(isfinite(values(:))) && ...
                all(values(:)>=0 & values(:)<=31.5) && ...
                all(ceil(values(:,1)*2)<=floor(values(:,2)*2)),'msiq:ifboard:config', ...
                '%s 批准范围需完整填写六行，位于 0–31.5 dB，且每行至少包含一个 0.5 dB 合法档位。',upper(key));
        end
    end
    if isfield(cfg,'initial_state')
        assert(isstruct(cfg.initial_state) && isfield(cfg.initial_state,key),'msiq:ifboard:config','初始设置缺少完整六路 %s。',upper(key));
        msiq.instruments.if_board_encode(key,cfg.initial_state.(key));
        if isfield(cfg.limits,key)
            v=cfg.initial_state.(key)(:); lim=cfg.limits.(key);
            assert(all(v>=lim(:,1) & v<=lim(:,2)),'msiq:ifboard:config','初始 %s 设置超出批准范围。',upper(key));
        end
    end
end
end
function value=getfieldOr(s,key,fallback)
if isfield(s,key), value=s.(key); else, value=fallback; end
end
function out=mergeMissing(out,defaults)
for names=fieldnames(defaults).'
    key=names{1};
    if ~isfield(out,key) || isempty(out.(key)), out.(key)=defaults.(key);
    elseif isstruct(out.(key)) && isstruct(defaults.(key)), out.(key)=mergeMissing(out.(key),defaults.(key)); end
end
end
