function note=validate_rx_scope_memory_gui(folder)
% GUI uses injected scope only; local snapshot provenance and reopen restore.
if nargin<1,folder=msiq.validation_artifacts('directory');end
if ~isfolder(folder),mkdir(folder);end
mock=struct('capture_delay_s',0,'record_count',2001,'log_path',fullfile(folder,'io.log'), ...
    'failure_path',fullfile(folder,'fail.flag'));
io=msiq.instruments.mock_rx_scope_io(mock);couple=false;late=false;
wrapped=io;wrapped.write=@write;wrapped.query=@query;
opts=struct('visible',false,'maximize',false,'synchronous_startup',true,'use_timer',false, ...
    'find_reference',false,'io',wrapped,'config',msiq.rx_mock_config(),'preferences_path','', ...
    'scope_presets_path',fullfile(folder,'presets'));
tag=['scope_memory_' char(java.util.UUID.randomUUID())];
f=msiq.rx_workbench_app(opts);set(f,'Tag',tag);guard=onCleanup(@()close_owned(tag)); %#ok<NASGU>
s=state();invoke(s.home.h_pause);
assert(isempty(s.scope_preset),'Connection must not save external state');
assert(strcmp(get(s.home.h_reference,'Visible'),'off'));
assert(strcmp(get(s.home.h_reference_auto,'Visible'),'off'));
set(s.home.h_vdiv1,'String','0.025');enter(s.home.h_vdiv1);
s=state();assert(~isempty(s.scope_preset),s.scope_preset_error);
assert(value(s.scope_preset,'C1:VDIV')==.025);
% External and automatic changes do not overwrite the saved manual value.
io.write(s.session,'C1:VDIV 0.04');
set(s.home.h_off1,'String','.003');enter(s.home.h_off1);
s=state();assert(value(s.scope_preset,'C1:VDIV')==.025&&value(s.scope_preset,'C1:OFST')==.003);
invoke(s.home.h_scope_restore);s=state();assert(s.scope_restore_report.ok);
assert(s.scope_status.channels(1).vertical_scale_v_per_div==.025);
% Confirmed timebase-linked horizontal change is saved; unrelated old changes are not.
couple=true;d=get(s.home.h_tdiv,'UserData');set(s.home.h_tdiv,'String',num2str(6e-6/d.multiplier));enter(s.home.h_tdiv);couple=false;
s=state();assert(value(s.scope_preset,'TRDL')==2e-6&&value(s.scope_preset,'TDIV')==6e-6);
% A late response must not save an older request over a new input draft.
old=s.scope_preset;late=true;set(s.home.h_off1,'String','.009');enter(s.home.h_off1);
s=state();assert(isequaln(old,s.scope_preset));key(s.home.h_off1,'escape');
% Filesystem failure leaves previous complete file and is visible beside readback status.
s=state();old=s.scope_preset;oldopts=s.scope_presets_options;
blocked=fullfile(folder,'not_a_folder');fid=fopen(blocked,'w');fclose(fid);
s.scope_presets_options.store_path=blocked;setappdata(f,'rx_workbench_state',s);
set(s.home.h_off1,'String','.004');enter(s.home.h_off1);s=state();
assert(isequaln(old,s.scope_preset)&&contains(get(s.home.h_status,'String'),'设置未保存'));
s.scope_presets_options=oldopts;setappdata(f,'rx_workbench_state',s);invoke(s.home.h_scope_restore);s=state();
% Draft prevents restoration and is preserved.
set(s.home.h_off1,'String','.007');key(s.home.h_off1,'backspace');
before=fileread(mock.log_path);invoke(s.home.h_scope_restore);assert(strcmp(before,fileread(mock.log_path)));
key(s.home.h_off1,'escape');
close(f);f=[];
% A new simulated session starts at defaults and applies the same saved snapshot.
opts.io=msiq.instruments.mock_rx_scope_io(mock);couple=false;late=false;
wrapped=io;wrapped.write=@write;wrapped.query=@query;
f=msiq.rx_workbench_app(opts);set(f,'Tag',tag);s=state();
assert(s.scope_restore_report.ok);
assert(s.scope_status.channels(1).vertical_scale_v_per_div==.025&&s.scope_status.channels(1).offset_v==.003);
assert(isempty(s.task),'Restore must not start a formal task');
invoke(s.home.h_pause);
% A failed restore reports partial state and cannot replace the preset.
preset=s.scope_preset;opts.io.write(s.session,'C1:VDIV 0.06');
fid=fopen(mock.failure_path,'w');fprintf(fid,'C1:VDIV');fclose(fid);
invoke(s.home.h_scope_restore);s=state();assert(~s.scope_restore_report.ok&&~s.running);
assert(contains(get(s.home.h_status,'String'),'恢复未完成'));
assert(isequal(get(s.home.h_vdiv1,'BackgroundColor'),[.94 .94 .94]), ...
    'Failed restoration must not paint an old cached readback as confirmed');
assert(isequaln(s.scope_preset,preset));
delete(mock.failure_path);
close(f);f=[];
% Explicit disabled persistence remains isolated from normal preferences.
opts.scope_presets_path='';f=msiq.rx_workbench_app(opts);set(f,'Tag',tag);s=state();invoke(s.home.h_pause);
set(s.home.h_vdiv1,'String','.02');enter(s.home.h_vdiv1);s=state();assert(isempty(s.scope_preset));
close(f);f=[];clear guard;
validate_async(folder);
note='RX scope memory GUI passed: manual confirmed save, external isolation, reopen restore, draft gate and partial failure; mock only.';
 function write(session,command)
  io.write(session,command);
  if couple&&startsWith(command,'TDIV '),io.write(session,'TRDL 0.000002');end
 end
 function response=query(session,command)
  response=io.query(session,command);
  if late&&strcmp(command,'C1:OFST?')
   late=false;t=state();key(t.home.h_off1,'backspace');set(t.home.h_off1,'String','.011');
  end
 end
 function s=state(),s=getappdata(f,'rx_workbench_state');end
end
function v=value(s,key),v=s.fields(strcmp({s.fields.key},key)).value;end
function invoke(h),cb=get(h,'Callback');cb(h,[]);drawnow;end
function enter(h),key(h,'return');end
function key(h,k),cb=get(h,'KeyPressFcn');cb(h,struct('Key',k));drawnow;end

function close_owned(tag)
for f=findall(groot,'Type','figure','Tag',tag).',if isgraphics(f),close(f);end;end
end

function validate_async(folder)
opts=struct('visible',false,'maximize',false,'synchronous_startup',true,'auto_connect',true, ...
 'use_timer',false,'find_reference',false,'asynchronous',true,'config',msiq.rx_mock_config(), ...
 'preferences_path','','scope_presets_path',fullfile(folder,'async_presets'), ...
 'worker_factory','msiq.rx_daily_mock_io','worker_options',struct('capture_delay_s',0, ...
 'record_count',2001,'log_path',fullfile(folder,'async_io.log'),'failure_path',fullfile(folder,'async_failure.txt')));
f=msiq.rx_workbench_app(opts);guard=onCleanup(@()close_async(f));
await(f,@(s)s.connected,90);s=getappdata(f,'rx_workbench_state');invoke(s.home.h_pause);await(f,@(s)~s.busy,30);
s=getappdata(f,'rx_workbench_state');set(s.home.h_vdiv1,'String','.025');enter(s.home.h_vdiv1);
await(f,@(s)~s.busy&&~isempty(s.scope_preset),45);
s=getappdata(f,'rx_workbench_state');assert(value(s.scope_preset,'C1:VDIV')==.025);
close_async(f);clear guard;
f=msiq.rx_workbench_app(opts);guard=onCleanup(@()close_async(f));
await(f,@(s)isfield(s.scope_restore_report,'ok')&&s.scope_restore_report.ok,90);
s=getappdata(f,'rx_workbench_state');assert(s.scope_status.channels(1).vertical_scale_v_per_div==.025);
invoke(s.home.h_pause);await(f,@(s)~s.busy,30);assert(isempty(s.task));
s=getappdata(f,'rx_workbench_state');saved=s.scope_preset;
% Model a task-owned scale change through the same worker, without GUI provenance.
s.worker.submit(struct('action','setting','command','C1:VDIV','value',.06,'channels',{{'C1','C2'}}));
started=tic;done=false;
while toc(started)<30,[done,response]=s.worker.poll();if done,break;end;pause(.05);end
assert(done&&response.ok);s.scope_status=response.status;setappdata(f,'rx_workbench_state',s);
invoke(s.home.h_scope_restore);s=getappdata(f,'rx_workbench_state');assert(strcmp(get(s.home.h_stop,'Enable'),'on'));
invoke(s.home.h_stop);await(f,@(s)~s.busy&&isempty(s.scope_restore_pending),45);
s=getappdata(f,'rx_workbench_state');assert(~s.scope_restore_report.ok&&~s.running&&isequaln(saved,s.scope_preset));
close_async(f);clear guard;
end
function await(f,predicate,seconds)
started=tic;
while toc(started)<seconds
 s=getappdata(f,'rx_workbench_state');if predicate(s),return;end
 callback=getappdata(f,'rx_workbench_tick');callback([],[]);drawnow;pause(.05);
end
s=getappdata(f,'rx_workbench_state');error('validation:timeout','GUI timeout: %s',get(s.home.h_status,'String'));
end
function close_async(f)
if ~isgraphics(f),return;end
close(f);started=tic;
while isgraphics(f)&&toc(started)<40
 callback=getappdata(f,'rx_workbench_tick');callback([],[]);drawnow;pause(.05);
end
end
