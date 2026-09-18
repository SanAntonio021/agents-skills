function result=rx_scope_presets(action,project_root,source,snapshot,options)
%RX_SCOPE_PRESETS Atomic local presets; caller controls manual provenance.
if nargin<5,options=struct();end
assert(ismember(source,{'simulation','measurement','live'}),'RX_Workbench:Preset','未知数据来源');
if strcmp(source,'live'),source='measurement';end
assert(isstruct(snapshot)&&isfield(snapshot,'identity'),'RX_Workbench:Preset','缺少仪器身份');
if isfield(options,'store_path'),folder=options.store_path;else,folder=fullfile(prefdir,'msiq_scope_presets');end
if isempty(folder),result=[];if strcmp(action,'path'),result='';end;return;end
project_root=char(java.io.File(project_root).getCanonicalPath());
md=java.security.MessageDigest.getInstance('SHA-256');md.update(unicode2native(lower(project_root),'UTF-8'));project_key=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
md=java.security.MessageDigest.getInstance('SHA-256');md.update(unicode2native(snapshot.identity,'UTF-8'));device_key=lower(reshape(dec2hex(typecast(md.digest(),'uint8'),2).',1,[]));
path=fullfile(folder,[project_key(1:16) '_' source '_' device_key(1:16) '.mat']);
if strcmp(action,'path'),result=path;return;end
previous=[];
if isfile(path)
 data=load(path,'preset');assert(isfield(data,'preset')&&strcmp(data.preset.identity,snapshot.identity),'RX_Workbench:Preset','保存记录身份不符');previous=data.preset;
end
switch action
 case 'load',result=previous;
 case 'save'
  result=snapshot;
  if ~isempty(previous)
   result=previous; keys={snapshot.fields.key};
   if isfield(options,'keys'),keys=cellstr(string(options.keys));end
   new_channels=setdiff(snapshot.channels,previous.channels,'stable');
   % Earlier incomplete channel entries do not count as established baselines.
   for c=snapshot.channels
    if ~all(ismember(strcat(c,{':VDIV',':OFST',':TRA'}),{previous.fields.key}))
     new_channels=unique([new_channels c],'stable');
    end
   end
   for n=1:numel(snapshot.fields)
    f=snapshot.fields(n);channel=regexp(f.key,'^(C[1-4]):','tokens','once');
    initialize_channel=~isempty(channel)&&ismember(channel{1},new_channels);
    if ~ismember(f.key,keys)&&~initialize_channel,continue;end
    k=find(strcmp({result.fields.key},f.key),1);
    if isempty(k),result.fields(end+1)=f;else,result.fields(k)=f;end
   end
   result.channels=unique([previous.channels snapshot.channels],'stable');result.saved_at=snapshot.saved_at;
  end
  if ~isfolder(folder),mkdir(folder);end
  msiq.atomic_save(path,struct('preset',result));
 otherwise,error('RX_Workbench:Preset','未知设置操作');
end
end
