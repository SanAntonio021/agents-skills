function out=rx_capture_settings(action,profile,arg,options)
%RX_CAPTURE_SETTINGS Local-only capture preferences; never creates instrument I/O.
% Imported/persisted verification claims cannot grant acquisition authority.
if nargin<2, profile=struct(); end
if nargin<3, arg=[]; end
if nargin<4, options=struct(); end
source=field(options,'source_mode','live');
assert(any(strcmp(source,{'live','simulation'})),'msiq:rx:settingsSource','未知采集设置来源。');
switch lower(action)
    case 'path'
        root=arg; if isempty(root), root=msiq.project_root(); end
        out=fullfile(root,'rx_records',['rx_capture_settings_' source '.mat']);
    case 'normalize'
        out=normalize(profile,arg,source);
    case {'load','import'}
        out=profile;
        if isempty(arg), return; end
        if strcmpi(action,'load') && ~isfile(arg), return; end
        if endsWith(lower(char(arg)),'.json'), record=jsondecode(fileread(arg));
        else, record=load(arg); end
        if isfield(record,'settings'), record=record.settings; end
        if isfield(record,'source_mode')
            assert(strcmp(record.source_mode,source),'msiq:rx:settingsSource','模拟与实测采集设置不能混用。');
        end
        if isfield(record,'profile'), candidate=record.profile;
        elseif isfield(record,'p'), candidate=record.p;
        else, candidate=record; end
        out=normalize(profile,candidate,source);
    case {'save','export'}
        out=normalize(profile,profile,source);
        if isempty(arg), return; end
        folder=fileparts(arg); if ~isempty(folder) && ~isfolder(folder), mkdir(folder); end
        stored=struct('scope',out.scope,'policy',out.policy);
        settings=struct('schema_version',1,'source_mode',source,'profile',stored);
        if endsWith(lower(char(arg)),'.json')
            temporary=[tempname(folder) '.tmp']; cleanup=onCleanup(@()removeTemp(temporary)); %#ok<NASGU>
            fid=Result_Open_File_Retry(temporary,'w');
            assert(fid>=0,'msiq:rx:settingsSave','无法写入配置文件。');
            closeFile=onCleanup(@()fclose(fid));
            fprintf(fid,'%s',jsonencode(settings)); clear closeFile;
            [ok,msg]=movefile(temporary,arg,'f'); assert(ok,'msiq:rx:settingsSave','%s',msg);
        else, msiq.atomic_save(arg,struct('settings',settings)); end
    otherwise, error('msiq:rx:settingsAction','未知采集设置操作。');
end
end
function p=normalize(base,candidate,source)
if isempty(candidate), candidate=struct(); end
assert(isstruct(candidate)&&isscalar(candidate),'msiq:rx:settingsFormat','配置必须是一个对象。');
if strcmp(source,'live')
    assert(~strcmp(field(candidate,'mode','live'),'mock') && ~field(candidate,'mock_fixture_applied',false) && ...
        ~strcmp(field(candidate,'source_mode',''),'simulation'),'msiq:rx:settingsSource','模拟配置不能用于实测。');
end
% Fill schema with live defaults only: unknown approved values remain unknown.
p=msiq.if_workbench_config(struct('mode','live'));
p=merge(p,base);
scopeKeys={'auto_range_enabled','target_divisions','edge_margin_divisions','ranges_vdiv', ...
    'max_adjustments','headroom','sample_rate_hz','window_s','sample_rate_tolerance','window_tolerance','fresh'};
policyKeys=fieldnames(p.policy);
for section={'scope','policy'}
    name=section{1}; if ~isfield(candidate,name), continue; end
    assert(isstruct(candidate.(name))&&isscalar(candidate.(name)),'msiq:rx:settingsFormat','配置分区格式无效。');
    keys=scopeKeys; if strcmp(name,'policy'), keys=policyKeys; end
    for k=1:numel(keys)
        key=keys{k}; if isfield(candidate.(name),key)
            if strcmp(key,'fresh'), p.scope.fresh=merge(p.scope.fresh,candidate.scope.fresh);
            else, p.(name).(key)=candidate.(name).(key); end
        end
    end
end
fresh=p.scope.fresh; original=field(field(base,'scope',struct()),'fresh',struct());
trusted=field(original,'verified',false);
fresh.verified=false; original.verified=false;
fresh.verified=logical(trusted)&&isequaln(fresh,original); p.scope.fresh=fresh;
% JSON encodes NaN as null; null decodes as empty. Restore unknown scalars.
for key={'max_adjustments','headroom','sample_rate_tolerance','window_tolerance'}
    if isempty(p.scope.(key{1})),p.scope.(key{1})=NaN;end
end
for k=1:numel(policyKeys), if isempty(p.policy.(policyKeys{k})),p.policy.(policyKeys{k})=NaN;end;end
for key={'timeout_s','poll_s'},if isempty(p.scope.fresh.(key{1})),p.scope.fresh.(key{1})=NaN;end;end
v=p.scope.auto_range_enabled;
assert(isscalar(v)&&(islogical(v)||(isnumeric(v)&&isfinite(v)&&any(v==[0 1]))),'msiq:rx:settingsValue','自动量程开关无效。');
p.scope.auto_range_enabled=logical(v);
target=p.scope.target_divisions; margin=p.scope.edge_margin_divisions;
assert(isnumeric(target)&&isscalar(target)&&isfinite(target)&&target>0&&target<=8, ...
    'msiq:rx:settingsValue','目标占格必须大于 0 且不超过 8。');
assert(isnumeric(margin)&&isscalar(margin)&&isfinite(margin)&&margin>=0&&margin<4&&target+2*margin<=8+1e-12, ...
    'msiq:rx:settingsValue','目标占格与上下边缘余量合计不能超过 8 格。');
r=p.scope.ranges_vdiv;
assert(isnumeric(r)&&(isempty(r)||(isvector(r)&&all(isfinite(r))&&all(r>0))), ...
    'msiq:rx:settingsValue','批准量程档位必须为正数，单位 V/div；未知可留空。');
p.scope.ranges_vdiv=sort(unique(r(:).'));
checkNumber(p.scope.max_adjustments,'量程调整次数',true);
checkNumber(p.policy.settle_s,'稳定等待',false);
policyLabels=struct('settle_s','稳定等待','balance_tolerance_db','配平容差', ...
    'balance_step_db','配平步进','max_balance_adjustments','配平调整次数', ...
    'ber_degradation','BER 退化容差','mer_degradation_db','MER 退化容差', ...
    'ber_recovery','BER 恢复容差','mer_recovery_db','MER 恢复容差','range_jump_db','量程突跳判据');
for k=1:numel(policyKeys)
    label=field(policyLabels,policyKeys{k},'策略参数');
    checkNumber(p.policy.(policyKeys{k}),label,strcmp(policyKeys{k},'max_balance_adjustments'));
end
checkNumber(p.scope.sample_rate_tolerance,'采样率检查容差',false);
checkNumber(p.scope.window_tolerance,'采集窗口检查容差',false);
checkNumber(p.scope.headroom,'配平量程余量系数',false);
checkNumber(p.scope.fresh.timeout_s,'完成等待上限',false);
checkNumber(p.scope.fresh.poll_s,'轮询间隔',false);
end
function checkNumber(value,label,integer)
assert(isnumeric(value)&&isscalar(value)&&(isnan(value)||(isfinite(value)&&value>=0&&(~integer||fix(value)==value))), ...
    'msiq:rx:settingsValue','%s 必须是非负数%s；未知可留空。',label,choose(integer,'整数',''));
end
function s=merge(s,t)
if ~isstruct(t), return; end
names=fieldnames(t);
for k=1:numel(names), n=names{k}; if isfield(s,n)&&isstruct(s.(n))&&isstruct(t.(n)), s.(n)=merge(s.(n),t.(n)); else, s.(n)=t.(n); end; end
end
function v=field(s,n,d), if isfield(s,n), v=s.(n); else, v=d; end; end
function v=choose(test,a,b), if test,v=a;else,v=b;end;end
function removeTemp(p), if isfile(p),delete(p);end;end
