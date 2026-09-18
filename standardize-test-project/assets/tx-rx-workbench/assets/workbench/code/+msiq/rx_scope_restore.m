function report=rx_scope_restore(session,target,channels,io,options)
%RX_SCOPE_RESTORE Restore a supported snapshot through an existing session.
% No connection creation, retry, preference save, or cancellation bypass.
if nargin<5,options=struct();end
report=struct('ok',false,'status',struct(),'applied',{{}},'errors',{{}},'phase','preflight','sent_commands',{{}},'attempted_commands',{{}});
try
 channels=reshape(cellstr(string(channels)),1,[]);
 assert(isstruct(target)&&isfield(target,'version')&&target.version==1,'RX_Workbench:Restore','缺少有效设置快照');
 check(); current=read(); now=msiq.rx_scope_snapshot(current,channels);
 assert(strcmp(now.identity,target.identity),'RX_Workbench:Restore','仪器身份与保存设置不符');
 assert(all(ismember(channels,target.channels)),'RX_Workbench:Restore','保存记录缺少当前通道');
 fields=target.fields;
 keep=true(size(fields));
 for k=1:numel(fields)
  ch=regexp(fields(k).key,'^(C[1-4]):','tokens','once');
  if ~isempty(ch),keep(k)=ismember(ch{1},channels);end
 end
 fields=fields(keep);
 required={'TDIV','TRDL','TRMD'};
 for c=channels,required=[required strcat(c,{':VDIV',':OFST',':TRA'})];end %#ok<AGROW>
 assert(all(ismember(required,{fields.key})),'RX_Workbench:Restore','快照缺少当前通道或全局基本设置');
 assert(numel(unique({fields.key}))==numel(fields),'RX_Workbench:Restore','快照包含重复参数');
 for k=1:numel(fields)
  key=fields(k).key; v=fields(k).value;
  if basic(key)
   assert(isnumeric(v)&&isscalar(v)&&isfinite(v),'RX_Workbench:Restore','无效数值 %s',key);
   if strcmp(key,'TDIV')||endsWith(key,':VDIV'),assert(v>0,'RX_Workbench:Restore','无效量程或时基');end
  else
   f=cap(current,key);assert(f.available,'RX_Workbench:Restore','参数不可用：%s',key);
   run_state=strcmp(key,'TRMD')&&ismember(f.value,{'AUTO','NORM','STOP'})&&ismember(v,{'AUTO','NORM','STOP'});
   dependency=strcmp(key,'HTIME')&&ismember(value(fields,'HTYPE'),{'TI','OFF'})&&contains(f.error,'仅按时间');
   assert(f.writable||dependency||run_state,'RX_Workbench:Restore','参数不可恢复：%s %s',key,f.error);
   if strcmp(f.kind,'enum')&&~run_state,assert(ismember(v,f.choices),'RX_Workbench:Restore','不支持保存值：%s',key);end
   if strcmp(f.kind,'number')
    assert(isnumeric(v)&&isscalar(v)&&isfinite(v),'RX_Workbench:Restore','无效数值：%s',key);
    if ~strcmp(key,'TRLEVEL'),assert(v>=f.minimum&&v<=f.maximum,'RX_Workbench:Restore','保存值超出当前能力：%s',key);end
    if f.integer,assert(v==round(v),'RX_Workbench:Restore','保存值不是整数：%s',key);end
   end
  end
 end
 unchanged=true;
 for k=1:numel(fields),unchanged=unchanged&&equal(get_value(current,fields(k).key),fields(k).value);end
 if unchanged,report.ok=true;report.status=current;report.phase='complete';return;end
 % No write before identity, channel and capability preflight completes.
 check();report.phase='pause'; send('TRMD STOP');report.applied{end+1}='TRMD STOP';
 stopped=upper(strtrim(char(io.query(session,'TRMD?'))));
 assert(~isempty(regexp(stopped,'(?:^|\s)STOP$','once')),'RX_Workbench:Restore','停止采集未确认');
 rank=zeros(1,numel(fields));
 for k=1:numel(fields),rank(k)=order(fields(k).key);end
 [~,idx]=sort(rank);
 for n=idx
  key=fields(n).key;expected=fields(n).value;check();report.phase=key;
  if strcmp(key,'TRMD'),continue;end
  current=read();actual=get_value(current,key);
  if equal(actual,expected),continue;end
  if basic(key)
   send(sprintf('%s %.17g',key,expected));report.applied{end+1}=key;
   current=read();actual=get_value(current,key);
  else
   % Live adapter rechecks ranges after source, scale and mode dependencies.
   temporary_holdoff=false;
   if strcmp(key,'HTIME')&&~strcmp(get_value(current,'HTYPE'),'TI')
    check();msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','TI'),io.query,@(~,command)send(command));
    report.applied{end+1}='HTYPE temporary TI';temporary_holdoff=true;
   end
   check();
   actual=msiq.instruments.apply_rx_scope_setting(session,struct('key',key,'value',expected),io.query,@(~,command)send(command));
   report.applied{end+1}=key;
   assert(equal(actual,expected),'RX_Workbench:Restore','恢复后回读不一致：%s',key);
   if temporary_holdoff
    check();msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value',value(fields,'HTYPE')),io.query,@(~,command)send(command));
    report.applied{end+1}='HTYPE restored';
   end
  end
  assert(equal(actual,expected),'RX_Workbench:Restore','恢复后回读不一致：%s',key);
 end
 check();report.phase='verify';current=read();
 for n=1:numel(fields)
  if strcmp(fields(n).key,'TRMD'),continue;end
  assert(equal(get_value(current,fields(n).key),fields(n).value),'RX_Workbench:Restore','恢复后联动检查不一致：%s',fields(n).key);
 end
 check();report.phase='run_state';run=value(fields,'TRMD');
 % STOP is an existing acquisition command, never a newly inferred enum.
 assert(ismember(run,{'AUTO','NORM','STOP'}),'RX_Workbench:Restore','不支持保存的运行状态');
 send(['TRMD ' run]);report.applied{end+1}='TRMD';
 actual=upper(strtrim(char(io.query(session,'TRMD?'))));
 assert(strcmp(regexprep(actual,'^TRMD\s+',''),run),'RX_Workbench:Restore','运行状态恢复未确认');
 report.status=read();
 for n=1:numel(fields)
  assert(equal(get_value(report.status,fields(n).key),fields(n).value),'RX_Workbench:Restore','最终回读不一致：%s',fields(n).key);
 end
 report.ok=true;report.phase='complete';
catch exception
 report.errors{end+1}=exception.message;report.error_id=exception.identifier;
 % Preserve known state; a failed transport is never silently reopened.
end
    function send(command)
      report.attempted_commands{end+1}=command;
      io.write(session,command);
      report.sent_commands{end+1}=command;
    end
    function check()
      if isfield(options,'check')&&~isempty(options.check),options.check();end
    end
    function s=read()
      s=msiq.instruments.rx_scope_state(session,io.query);
      s.settings=msiq.instruments.rx_scope_settings(session,io.query,struct(),true);
      report.status=s;
    end
end
function yes=basic(key)
yes=ismember(key,{'TDIV','TRDL'})||~isempty(regexp(key,'^C[1-4]:(VDIV|OFST)$','once'));
end
function f=cap(s,key)
k=find(strcmp({s.settings.fields.key},key),1);assert(~isempty(k),'RX_Workbench:Restore','不支持参数：%s',key);f=s.settings.fields(k);
end
function v=get_value(s,key)
if strcmp(key,'TDIV'),v=s.timebase;elseif strcmp(key,'TRDL'),v=s.trigger_delay_s;
elseif basic(key)
 c=s.channels(strcmp({s.channels.channel},key(1:2)));if endsWith(key,':VDIV'),v=c.vertical_scale_v_per_div;else,v=c.offset_v;end
else,f=cap(s,key);assert(f.available,'RX_Workbench:Restore','回读不可用：%s',key);v=f.value;end
end
function v=value(fields,key)
k=find(strcmp({fields.key},key),1);v=[];if ~isempty(k),v=fields(k).value;end
end
function yes=equal(a,b)
if isnumeric(a)&&isnumeric(b),yes=isscalar(a)&&isscalar(b)&&isfinite(a)&&isfinite(b)&&abs(a-b)<=max(1e-15,1e-9*max(abs([a b])));else,yes=isequal(a,b);end
end
function n=order(key)
if strcmp(key,'SAMPLEMODE'),n=1;elseif strcmp(key,'MSIZ'),n=2;elseif strcmp(key,'TDIV'),n=3;elseif strcmp(key,'TRDL'),n=4;
elseif ~isempty(regexp(key,'^C[1-4]:','once')),n=10;if endsWith(key,':CPL'),n=8;elseif endsWith(key,':VDIV'),n=9;end
elseif strcmp(key,'TRSOURCE'),n=20;elseif strcmp(key,'TRSLOPE'),n=21;elseif strcmp(key,'TRLEVEL'),n=22;elseif strcmp(key,'HTYPE'),n=23;elseif strcmp(key,'HTIME'),n=24;else,n=100;end
end
