function snapshot=rx_scope_snapshot(status,channels)
%RX_SCOPE_SNAPSHOT Supported, trusted scope settings; never performs I/O.
if nargin<2, channels={status.channels.channel}; end
channels=reshape(cellstr(string(channels)),1,[]);
assert(~isempty(channels)&&numel(unique(channels))==numel(channels)&&all(ismember(channels,{'C1','C2','C3','C4'})), 'RX_Workbench:Snapshot','无效采集通道');
assert(isfield(status,'idn'),'RX_Workbench:Snapshot','缺少仪器身份');
parts=strtrim(strsplit(char(status.idn),','));
assert(numel(parts)>=3&&all(~cellfun('isempty',parts(1:3))),'RX_Workbench:Snapshot','仪器身份不明确');
snapshot=struct('version',1,'idn',status.idn,'identity',upper(strjoin(parts(1:3),',')), ...
 'channels',{channels},'fields',struct('key',{},'value',{}),'sample_rate_hz',status.sample_rate_hz,'saved_at',datetime('now'));
add('TDIV',status.timebase); add('TRDL',status.trigger_delay_s);
for n=1:numel(channels)
 c=status.channels(strcmp({status.channels.channel},channels{n}));
 assert(numel(c)==1,'RX_Workbench:Snapshot','缺少通道回读');
 add([channels{n} ':VDIV'],c.vertical_scale_v_per_div); add([channels{n} ':OFST'],c.offset_v);
end
if isfield(status,'settings')&&isfield(status.settings,'fields')
 for n=1:numel(status.settings.fields)
  f=status.settings.fields(n); token=regexp(f.key,'^(C[1-4]):','tokens','once');
  if ~isempty(token)&&~ismember(token{1},channels),continue;end
  if f.available&&(f.writable||(strcmp(f.key,'HTIME')&&contains(f.error,'仅按时间'))||(strcmp(f.key,'TRMD')&&ismember(f.value,{'AUTO','NORM','STOP'}))), add(f.key,f.value); end
 end
end
    function add(key,value)
      if isnumeric(value),assert(isscalar(value)&&isfinite(value),'RX_Workbench:Snapshot','无效回读 %s',key);end
      snapshot.fields(end+1)=struct('key',key,'value',value);
    end
end
