function report = validate_rx_async(output_dir, section)
%VALIDATE_RX_ASYNC Real process isolation, blocking mock reads, and large traces.
if nargin<1, output_dir=tempname; mkdir(output_dir); end
if nargin<2, section='all'; end
section=validatestring(section,{'all','reference'});
if strcmp(section,'reference')
    validate_reference_async(output_dir);
    validate_empty_transport(output_dir);
    report=struct('passed',true,'section',section);
    return;
end
mock_options=struct('capture_delay_s',2,'record_count',4000000, ...
    'log_path',fullfile(output_dir,'async_audit.log'), ...
    'failure_path',fullfile(output_dir,'async_failure.txt'));
fid=fopen(mock_options.log_path,'w'); fclose(fid);
if isfile(mock_options.failure_path), delete(mock_options.failure_path); end
options=struct('visible',true,'maximize',false,'position',[40 40 1100 700], ...
    'synchronous_startup',true,'use_timer',false,'asynchronous',true, ...
    'find_reference',false,'worker_factory','msiq.instruments.mock_rx_scope_io', ...
    'worker_options',mock_options,'config',msiq.rx_mock_config());
unsafe=options; unsafe.worker_factory=''; unsafe.io=msiq.instruments.mock_rx_scope_io(mock_options);
blocked=false;
try
    msiq.rx_workbench_app(unsafe);
catch exception
    blocked=strcmp(exception.identifier,'RX_Workbench:TestIO');
end
assert(blocked,'Injected GUI I/O must never silently fall back to real worker hardware.');
fig=msiq.rx_workbench_app(options);
state=getappdata(fig,'rx_workbench_state');
worker=state.worker;
guard=onCleanup(@() finish(fig,worker));
assert(~isempty(worker),'The app did not create a background worker.');
% The GUI remains operable even during process startup and connection.
started=tic; invoke(state.home.h_settings); drawnow;
startup_page_s=toc(started);
fprintf('RX startup page switch %.4fs\n',startup_page_s);
assert(startup_page_s<.5 && current(fig).page=="settings", ...
    'Startup settings switch took %.4fs (page %s).',startup_page_s,current(fig).page);
invoke(state.home.h_settings);
await(fig,@(s) s.connected,60);
log=fileread(mock_options.log_path);
assert(~contains(log,'WRITE '),'Automatic connection must not write.');
assert(count(log,'QUERY *IDN?')==1);
await_log(mock_options.log_path,'CAPTURE BEGIN',10);
state=current(fig);
started=tic;
invoke(state.home.h_settings);
interaction_marks=toc(started);
set(fig,'Position',[40 40 1100 500]); drawnow;
interaction_marks(end+1)=toc(started);
state=current(fig);
scroll=get(fig,'WindowScrollWheelFcn');
top=get(state.home.scroll,'Value');
scroll(fig,struct('PointerPosition',[30 200],'VerticalScrollCount',1));
assert(get(state.home.scroll,'Value')<top,'Wheel did not move during a blocked read.');
scroll(fig,struct('PointerPosition',[30 200],'VerticalScrollCount',-1));
assert(get(state.home.scroll,'Value')==top,'Wheel/slider top mapping is inconsistent.');
interaction_marks(end+1)=toc(started);
set(fig,'Position',[40 40 1100 700]);
invoke(state.home.h_settings);
invoke(state.home.h_pause);
set(state.home.h_off1,'String','.012'); invoke(state.home.h_off1);
drawnow;
response_s=toc(started);
interaction_steps=diff([0 interaction_marks response_s]);
fprintf('RX interaction steps: settings %.4fs, resize %.4fs, wheel %.4fs, return/edit %.4fs; total %.4fs\n', ...
    interaction_steps,response_s);
assert(response_s<1,'GUI interaction exceeded 1s: %.4fs; steps %s',response_s,mat2str(interaction_steps,4));
assert(~contains(fileread(mock_options.log_path),'WRITE '),'Write interleaved with capture.');
await(fig,@(s) ~s.busy && isempty(s.pending) && isfield(s.raw,'live_spectra'),20);
state=current(fig);
assert(~state.running && state.connected);
assert(state.plot_state.last_sample_count(1)==4000000);
assert(state.raw_stale,'A setting applied after capture must mark the displayed record stale.');
log=fileread(mock_options.log_path);
assert(count(log,'CAPTURE BEGIN')==1,'Pause queued another capture.');
assert(count(log,'WRITE ')==1 && contains(log,'WRITE C1:OFST 0.012'));
assert(strfind(log,'CAPTURE RELEASE')<strfind(log,'WRITE C1:OFST'));
assert(count(log,'QUERY *IDN?')==2,'Expect startup and one complete reread after the edit.');
before_capture=extractBefore(log,'CAPTURE BEGIN');
assert(count(before_capture,'QUERY *IDN?')==1,'Capture must reuse stable metadata.');
after_capture=extractBetween(log,'CAPTURE RELEASE','WRITE C1:OFST');
for command={'TDIV?','MSIZ?','BWL?','C1:VDIV?','C1:OFST?','C1:CPL?','C2:VDIV?','C2:OFST?','C2:CPL?'}
    assert(contains(after_capture,['QUERY ' command{1}]),'Missing post-capture readback: %s',command{1});
end
assert(abs(state.scope_status.channels(1).offset_v-.012)<1e-12);
assert(contains(get(state.home.h_freshness,'String'),'旧数据'));
axes_list=[state.home.axes.wave_top state.home.axes.wave_bottom ...
    state.home.axes.spectrum_top state.home.axes.spectrum_bottom];
for ax=axes_list
    line=findobj(ax,'Type','line');
    assert(~isempty(line) && numel(get(line(1),'XData'))<6000);
end
assert(max(state.raw.channels(1).samples)==.055,'Envelope lost the isolated peak.');
assert(state.plot_state.spectra{1}.segment_count<=8);
assert(state.plot_state.spectra{1}.segment_length<=65536);
psd=state.plot_state.spectra{1};
assert(abs(psd.delta_f_hz/(80e9/65536)-1)<1e-8 && abs(psd.effective_limit_hz-40e9)<400, ...
    'Returned-time precision: df=%.15g, limit=%.15g',psd.delta_f_hz,psd.effective_limit_hz);
band=psd.frequency_hz>.8e9 & psd.frequency_hz<1.2e9;
power_dbm=10*log10(sum(10.^(psd.power_dbm_hz(band)/10))*psd.delta_f_hz);
assert(abs(power_dbm-10*log10(.04^2/2/50*1000))<.02);
trace=findobj(state.home.axes.spectrum_top,'Tag','rx_spectrum_line');
in_tone=get(trace,'XData')>10.98 & get(trace,'XData')<11.02;
levels=get(trace,'YData');
assert(any(in_tone) && max(levels(in_tone))>-120,'Display compression lost the narrow 11 GHz peak.');
analysis_s=state.last_analysis_s;
before=state.raw.live_spectra;
started=tic;
for k=1:5
    callback=get(fig,'SizeChangedFcn'); callback(fig,[]);
end
resize_s=toc(started)/5;
state=current(fig); assert(isequaln(before,state.raw.live_spectra));
assert(resize_s<.4,'Resizing still performs large-record analysis.');
% Hidden plots retain their geometry and samples until the home page returns.
invoke(state.home.h_settings);
hidden_positions=get(axes_list,'Position');
hidden_lines=findobj(axes_list,'Type','line');
hidden_xdata=get(hidden_lines,'XData');
set(fig,'Position',[40 40 1100 500]); drawnow;
scroll=get(fig,'WindowScrollWheelFcn');
scroll(fig,struct('PointerPosition',[30 200],'VerticalScrollCount',1));
scroll(fig,struct('PointerPosition',[30 200],'VerticalScrollCount',-1));
set(fig,'Position',[40 40 1100 650]); drawnow;
assert(isequaln(get(axes_list,'Position'),hidden_positions), ...
    'Settings-page resize or scroll moved hidden plot axes.');
assert(all(isgraphics(hidden_lines)) && isequaln(get(hidden_lines,'XData'),hidden_xdata), ...
    'Settings-page resize or scroll changed hidden waveform samples.');
invoke(state.home.h_settings); drawnow;
assert(~isequaln(get(axes_list,'Position'),hidden_positions), ...
    'Returning home did not apply the final window size.');
set(fig,'Position',[40 40 1100 700]); drawnow;
invoke(state.home.h_settings); invoke(state.home.h_auto_psd); invoke(state.home.h_settings);
drawnow; frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,'RX_async_4M.png'));

% Horizontal position edits use the same serialized owner during observation.
state=current(fig); before_log=fileread(mock_options.log_path);
before_captures=count(before_log,'CAPTURE BEGIN');
before_writes=count(before_log,'WRITE ');
invoke(state.home.h_play);
await(fig,@(s) s.busy,10);
await(fig,@(~) count(fileread(mock_options.log_path),'CAPTURE BEGIN')>before_captures,10);
set(state.home.h_trdl,'String','-2.5'); invoke(state.home.h_trdl);
assert(count(fileread(mock_options.log_path),'WRITE ')==before_writes);
invoke(state.home.h_pause);
await(fig,@(s) ~s.busy && isempty(s.pending),20);
state=current(fig); log=fileread(mock_options.log_path);
assert(state.connected && abs(state.scope_status.trigger_delay_s+2.5e-9)<1e-21);
assert(count(log,'WRITE ')==before_writes+1 && contains(log,'WRITE TRDL -2.5e-09'));
restored=strfind(log,'CAPTURE RELEASE'); written=strfind(log,'WRITE TRDL -2.5e-09');
assert(restored(end)<written(end) && count(log,'CAPTURE BEGIN')==before_captures+1);
old_x=get(findobj(state.home.axes.wave_top,'Tag','rx_waveform'),'XData');
invoke(state.home.h_play);
await(fig,@(s) ~s.raw_stale,20);
invoke(state.home.h_pause); await(fig,@(s) ~s.busy,20);
new_x=get(findobj(state.home.axes.wave_top,'Tag','rx_waveform'),'XData');
assert(~isequal(old_x,new_x),'Next frame must use the new waveform timestamps.');
set(state.home.h_trdl,'String','0'); invoke(state.home.h_trdl);
await(fig,@(s) ~s.busy && isempty(s.pending),20);
assert(current(fig).scope_status.trigger_delay_s==0);
fprintf('RX horizontal position PASS: queued negative TRDL, zero readback, new timestamps, no repeated writes\n');

% Read-only route changes must not clear an outstanding worker request flag.
before_writes=count(fileread(mock_options.log_path),'WRITE ');
set(state.home.h_ch1,'Value',3); invoke(state.home.h_ch1);
await(fig,@(s) ~s.busy && s.connected,10);
state=current(fig);
assert(strcmp(state.channels{1},'C3') && str2double(get(state.home.h_vdiv1,'String'))==.03);
set(state.home.h_ch1,'Value',1); invoke(state.home.h_ch1);
await(fig,@(s) ~s.busy && s.connected,10);
assert(count(fileread(mock_options.log_path),'WRITE ')==before_writes);

% Front-panel drift rejects the frame without dropping the healthy session.
invoke(state.home.h_play);
await(fig,@(s) isfield(s.raw,'live_spectra'),15);
invoke(state.home.h_pause); await(fig,@(s) ~s.busy,15);
state=current(fig); saved_raw=state.raw; old_frame_status=state.raw_scope_status;
fid=fopen(mock_options.failure_path,'w'); fprintf(fid,'DRIFT'); fclose(fid);
invoke(state.home.h_play);
await(fig,@(s) s.raw_stale && contains(s.stale_reason,'offset_v'),15);
state=current(fig);
assert(state.connected && state.running && isequaln(state.raw,saved_raw));
assert(isequaln(state.raw_scope_status,old_frame_status));
delete(mock_options.failure_path);
invoke(state.home.h_pause);
await(fig,@(s) ~s.busy,15);
if current(fig).raw_stale
    invoke(state.home.h_play);
    await(fig,@(s) ~s.raw_stale,15);
    invoke(state.home.h_pause); await(fig,@(s) ~s.busy,15);
end
assert(current(fig).connected && ~current(fig).raw_stale);
assert(~contains(fileread(mock_options.log_path),'CLOSE'));

% A command timeout identifies the field, stops observation, and can reconnect.
fid=fopen(mock_options.failure_path,'w'); fprintf(fid,'C1:VDIV'); fclose(fid);
set(state.home.h_vdiv1,'String','.025'); invoke(state.home.h_vdiv1);
await(fig,@(s) ~s.busy && ~s.connected,10);
state=current(fig); data=get(state.home.h_vdiv1,'UserData');
assert(strcmp(get(data.retry,'Visible'),'on'));
assert(contains(get(state.home.h_status,'String'),'C1:VDIV'));
delete(mock_options.failure_path);
invoke(data.retry);
await(fig,@(s) ~s.busy && s.connected && isempty(s.pending),10);
state=current(fig); assert(abs(state.scope_status.channels(1).vertical_scale_v_per_div-.025)<1e-12);

% Navigating to a formal-test page releases the worker before another owner opens.
captures_before=count(fileread(mock_options.log_path),'CAPTURE BEGIN');
invoke(state.home.h_play); tick(fig);
await_log_count(mock_options.log_path,'CAPTURE BEGIN',captures_before+1,10);
invoke(state.home.h_single);
assert(current(fig).page=="single");
await(fig,@(s) ~s.busy && isempty(s.pending_page),20);
assert(~current(fig).connected && endsWith(strtrim(fileread(mock_options.log_path)),'CLOSE'));

fid=fopen(mock_options.failure_path,'w'); fprintf(fid,'OPEN'); fclose(fid);
invoke(state.pages.back_single);
await(fig,@(s) ~s.busy && ~s.connected,10);
state=current(fig); assert(contains(get(state.home.h_status,'String'),'OPEN'));
delete(mock_options.failure_path);
set(state.home.h_off2,'String','.018'); invoke(state.home.h_off2);
invoke(state.home.h_play); invoke(state.home.h_pause);
await(fig,@(s) ~s.busy && s.connected && isempty(s.pending),10);
assert(abs(current(fig).scope_status.channels(2).offset_v-.018)<1e-12);

fid=fopen(mock_options.failure_path,'w'); fprintf(fid,'C2:VDIV?'); fclose(fid);
invoke(state.home.h_play);
await(fig,@(s) ~s.busy && ~s.connected,10);
assert(contains(get(state.home.h_status,'String'),'C2:VDIV?'));
delete(mock_options.failure_path);
fid=fopen(mock_options.failure_path,'w'); fprintf(fid,'CAPTURE'); fclose(fid);
invoke(state.home.h_play);
await(fig,@(s) ~s.busy && ~s.connected,15);
assert(contains(get(state.home.h_status,'String'),'CAPTURE'));
log=fileread(mock_options.log_path);
assert(endsWith(strtrim(log),sprintf('CAPTURE RELEASE\nCLOSE')));
delete(mock_options.failure_path);

warm_interaction_s=validate_warm_interaction(fig,mock_options.log_path);
validate_hidden_capture(fig,mock_options.log_path);
log=fileread(mock_options.log_path);
report=struct('blocked_read_s',2,'samples_per_channel',4000000, ...
    'interaction_s',response_s,'cached_resize_s',resize_s, ...
    'warm_interaction_s',warm_interaction_s, ...
    'analysis_s',analysis_s, ...
    'capture_and_analysis_s',state.last_capture_elapsed_s,'worker_folder',worker.folder);
% Closing is also cooperative: no process kill while STOP cleanup is outstanding.
capture_count=count(log,'CAPTURE BEGIN');
state=current(fig);
state.timer=timer('ExecutionMode','fixedSpacing','BusyMode','drop','Period',.1, ...
    'TimerFcn',getappdata(fig,'rx_workbench_tick'));
setappdata(fig,'rx_workbench_state',state);
start(state.timer);
invoke(state.home.h_play);
await_log_count(mock_options.log_path,'CAPTURE BEGIN',capture_count+2,20);
report.warm_analysis_s=current(fig).last_analysis_s;
started=tic; close(fig); close_request_s=toc(started);
assert(close_request_s<.3);
started=tic;
while isgraphics(fig) && toc(started)<15, pause(.02); drawnow; end
assert(~isgraphics(fig),'Close never completed after the in-flight read.');
save(fullfile(output_dir,'rx_async_results.mat'),'report');
fprintf('RX async PASS: blocked=2s, N=4M/channel, callbacks=%.4fs, cached resize=%.4fs, cold/warm analysis=%.4f/%.4fs\n', ...
    response_s,resize_s,analysis_s,report.warm_analysis_s);
clear guard;
validate_default_startup(output_dir);
validate_disabled_channels(output_dir);
validate_capture_retries(output_dir);
validate_reference_async(output_dir);
validate_empty_transport(output_dir);
end

function validate_disabled_channels(output_dir)
state_path=fullfile(output_dir,'disabled_trace_states.txt');
fid=fopen(state_path,'w'); fprintf(fid,'OFF OFF OFF OFF'); fclose(fid);
mock=struct('capture_delay_s',0,'record_count',100000, ...
    'trace_state_path',state_path, ...
    'log_path',fullfile(output_dir,'disabled_channels_audit.log'), ...
    'failure_path',fullfile(output_dir,'disabled_channels_failure.txt'));
fid=fopen(mock.log_path,'w'); fclose(fid);
preferences_path=fullfile(output_dir,'disabled_channels_preferences.mat');
msiq.rx_view_preferences('save',preferences_path,struct('channels',{{'C3','C4'}}));
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false, ...
    'find_reference',false,'asynchronous',true,'worker_factory', ...
    'msiq.instruments.mock_rx_scope_io','worker_options',mock, ...
    'preferences_path',preferences_path,'config',msiq.rx_mock_config()));
guard=onCleanup(@() finish_default(fig));
await_default(fig,@(s) s.connected && isfield(s.raw,'capture_valid') && ...
    ~s.raw.capture_valid && ~s.first_capture_complete,60);
state=current(fig);
assert(state.running && state.raw_stale && ...
    contains(state.stale_reason,'C3、C4') && ~state.reference_busy);
audit=fileread(mock.log_path);
assert(~contains(audit,'CAPTURE BEGIN'),'Disabled channels issued a waveform read.');
fid=fopen(state_path,'w'); fprintf(fid,'OFF OFF ON ON'); fclose(fid);
await_default(fig,@(s) s.connected && s.first_capture_complete && ...
    isfield(s.raw,'capture_valid') && s.raw.capture_valid,30);
state=current(fig);
assert(state.running && isequal(state.channels,{'C3','C4'}) && ...
    all([state.raw.channels.wave_valid]));
assert(contains(fileread(mock.log_path),'CAPTURE END'));
fprintf('RX disabled-channel recovery PASS: C3/C4 OFF keeps connection, ON resumes capture\n');
clear guard;
end

function timings=validate_warm_interaction(fig,log_path)
state=current(fig); invoke(state.home.h_play);
await(fig,@(s) s.connected && ~s.raw_stale,20);
invoke(state.home.h_pause); await(fig,@(s) ~s.busy,20);
timings=zeros(1,3);
for k=1:3
    state=current(fig);
    assert(all(state.plot_state.last_sample_count==4000000));
    captures=count(fileread(log_path),'CAPTURE BEGIN');
    writes=count(fileread(log_path),'WRITE ');
    invoke(state.home.h_play); tick(fig);
    await_log_count(log_path,'CAPTURE BEGIN',captures+1,10);
    started=tic;
    invoke(state.home.h_settings);
    set(fig,'Position',[40 40 1100 500]); drawnow;
    scroll=get(fig,'WindowScrollWheelFcn');
    scroll(fig,struct('PointerPosition',[30 200],'VerticalScrollCount',1));
    scroll(fig,struct('PointerPosition',[30 200],'VerticalScrollCount',-1));
    set(fig,'Position',[40 40 1100 700]);
    invoke(state.home.h_settings); invoke(state.home.h_pause); drawnow;
    timings(k)=toc(started);
    assert(timings(k)<1,'Warm-frame GUI interaction exceeded 1s: %.4fs',timings(k));
    assert(count(fileread(log_path),'WRITE ')==writes);
    await(fig,@(s) ~s.busy,20);
end
fprintf('RX warm-frame pressure PASS: three 4M-point interactions %s s\n',mat2str(timings,4));
end

function validate_hidden_capture(fig,log_path)
state=current(fig);
wave=findobj(state.home.axes.wave_top,'Tag','rx_waveform');
setappdata(fig,'rx_test_draw_count',0);
listener=addlistener(wave,'XData','PostSet',@(~,~) ...
    setappdata(fig,'rx_test_draw_count',getappdata(fig,'rx_test_draw_count')+1));
guard=onCleanup(@() delete(listener));
invoke(state.home.h_settings);
old_center=get(state.home.h_center,'String'); old_min=get(state.home.h_psd_min,'String');
set(state.home.h_center,'String','1.234567'); set(state.home.h_psd_min,'String','-123.456');
writes=count(fileread(log_path),'WRITE ');
invoke(state.home.h_play);
for k=1:2
    stamp=current(fig).raw.last_new_data_at;
    await(fig,@(s) ~isequaln(s.raw.last_new_data_at,stamp),15);
end
invoke(state.home.h_pause); await(fig,@(s) ~s.busy,15);
assert(current(fig).plot_dirty && getappdata(fig,'rx_test_draw_count')==0, ...
    'New hidden frames touched graphics or were not marked pending.');
assert(strcmp(get(state.home.h_center,'String'),'1.234567'));
assert(strcmp(get(state.home.h_psd_min,'String'),'-123.456'));
set(state.home.h_center,'String',old_center); set(state.home.h_psd_min,'String',old_min);
invoke(state.home.h_auto_psd);
assert(all(isfinite(current(fig).plot_state.psd_ylim)));
assert(isfinite(str2double(get(state.home.h_psd_min,'String'))));
assert(getappdata(fig,'rx_test_draw_count')==0,'Hidden auto-PSD redrew plots.');
invoke(state.home.h_settings); drawnow;
state=current(fig);
assert(~state.plot_dirty && getappdata(fig,'rx_test_draw_count')==1);
record=state.raw.channels(1); box=getpixelposition(state.home.axes.wave_top);
index=msiq.plotting.rx_envelope_indices(record.samples,max(300,ceil(box(3)*2)));
assert(isequal(wave.YData(:),record.samples(index(:))));
resize=get(fig,'SizeChangedFcn'); resize(fig,[]); drawnow;
assert(getappdata(fig,'rx_test_draw_count')==1,'Same-size event repeated a completed redraw.');
assert(count(fileread(log_path),'WRITE ')==writes);
clear guard;
fprintf('RX hidden capture PASS: live frames and auto-PSD without drawing, unfinished edits intact, one latest-frame render on return\n');
end

function validate_capture_retries(output_dir)
mock=struct('capture_delay_s',.05,'record_count',1600,'timebase_s',2e-9, ...
    'calibration_offset_v',-2.7004480361941807e-5, ...
    'log_path',fullfile(output_dir,'retry_audit.log'), ...
    'failure_path',fullfile(output_dir,'retry_failure.txt'));
fid=fopen(mock.log_path,'w'); fclose(fid);
fid=fopen(mock.failure_path,'w'); fprintf(fid,'DRIFT_ALWAYS'); fclose(fid);
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false, ...
    'synchronous_startup',true,'use_timer',false,'asynchronous',true, ...
    'find_reference',false,'worker_factory','msiq.instruments.mock_rx_scope_io', ...
    'worker_options',mock,'config',msiq.rx_mock_config()));
worker=current(fig).worker;
guard=onCleanup(@() finish(fig,worker));
await(fig,@(s) s.connected && ~s.busy && s.capture_rejections==1,60);
state=current(fig);
assert(~state.first_capture_complete && state.running && state.raw_stale);
assert(contains(get(state.home.h_status,'String'),'1/3'));
tick(fig); tick(fig);
assert(contains(get(state.home.h_status,'String'),'校验失败'), ...
    'New capture progress overwrote the rejection reason.');
await(fig,@(s) ~s.running && ~s.busy && s.capture_rejections==3,10);
state=current(fig);
assert(state.connected && state.paused && ~state.first_capture_complete);
assert(strcmp(get(state.home.h_play,'Enable'),'on'));
assert(contains(get(state.home.h_freshness,'String'),'尚无有效波形'));
assert(contains(get(state.home.h_status,'String'),'C1 偏置'));
placeholders=findall(fig,'Tag','rx_placeholder');
assert(numel(placeholders)==4 && all(strcmp(get(placeholders,'String'),'未获得有效波形')));
assert(contains(get(state.home.h_status,'TooltipString'),' -> '));
for k=1:5, tick(fig); drawnow; end
log=fileread(mock.log_path);
assert(count(log,'CAPTURE BEGIN')==3,'Repeated rejection must stop after three frames.');
assert(~contains(log,'CLOSE') && ~contains(log,'WRITE '));
for dim={[1500 900],[1100 700]}
    set(fig,'Visible','on','Position',[40 40 dim{1}]); drawnow;
    frame=getframe(fig);
    imwrite(frame.cdata,fullfile(output_dir,sprintf('RX_rejection_%dx%d.png',dim{1})));
    for h=[state.home.h_status state.home.h_freshness]
        extent=get(h,'Extent'); box=get(h,'Position');
        assert(extent(3)<=box(3)+1 && extent(4)<=box(4)+1,'Failure text is clipped.');
    end
end
delete(mock.failure_path);
invoke(state.home.h_play);
await(fig,@(s) s.first_capture_complete && ~s.raw_stale,10);
invoke(state.home.h_pause); await(fig,@(s) ~s.busy,10);
state=current(fig);
assert(state.capture_rejections==0 && state.connected);
assert(abs(state.raw.capture_consistency(1).offset_delta_v-mock.calibration_offset_v)<1e-15);
assert(max(state.raw.channels(1).samples)==.055,'Accepted calibration changed the voltage samples.');
log=fileread(mock.log_path);
assert(count(log,'OPEN')==1 && ~contains(log,'CLOSE') && ~contains(log,'WRITE '));
for ax=[state.home.axes.wave_top state.home.axes.wave_bottom state.home.axes.spectrum_top state.home.axes.spectrum_bottom]
    line=findobj(ax,'Type','line'); assert(~isempty(line) && all(isfinite(line(1).YData)));
end
for ax=[state.home.axes.wave_top state.home.axes.wave_bottom]
    line=findobj(ax,'Tag','rx_waveform');
    assert(range(line.XData)>.99*diff(ax.XLim),'The recovery fixture does not fill the scope time window.');
end
for dim={[1500 900],[1100 700]}
    set(fig,'Position',[40 40 dim{1}]); drawnow; frame=getframe(fig);
    imwrite(frame.cdata,fullfile(output_dir,sprintf('RX_recovered_%dx%d.png',dim{1})));
end
% A subsequent persistent failure must retain the accepted waveform/settings.
saved_raw=state.raw; saved_status=state.raw_scope_status;
fid=fopen(mock.failure_path,'w'); fprintf(fid,'DRIFT_ALWAYS'); fclose(fid);
invoke(state.home.h_play);
await(fig,@(s) ~s.running && ~s.busy && s.capture_rejections==3,10);
state=current(fig);
assert(isequaln(state.raw,saved_raw) && isequaln(state.raw_scope_status,saved_status));
assert(state.connected && contains(get(state.home.h_freshness,'String'),'旧数据'));
delete(mock.failure_path);
fprintf('RX rejection/recovery PASS: bounded retries, sticky reason, restart, calibrated offset, preserved frame, zero writes\n');
end

function validate_reference_async(output_dir)
mock=struct('capture_delay_s',.05,'record_count',10000, ...
    'log_path',fullfile(output_dir,'reference_async.log'), ...
    'reference_log_path',fullfile(output_dir,'reference_files.log'), ...
    'reference_release_path',fullfile(output_dir,'reference_release.flag'), ...
    'failure_path',fullfile(output_dir,'reference_failure.txt'));
if isfile(mock.log_path), delete(mock.log_path); end
if isfile(mock.reference_log_path), delete(mock.reference_log_path); end
if isfile(mock.failure_path), delete(mock.failure_path); end
hold_reference(mock.reference_release_path);
release_guard=onCleanup(@() release_reference(mock.reference_release_path));
options=struct('visible',false,'maximize',false,'synchronous_startup',true, ...
    'use_timer',false,'asynchronous',true,'find_reference',false, ...
    'reference_bundle',fullfile(output_dir,'mock_reference_bundle.mat'), ...
    'worker_factory','msiq.instruments.mock_rx_scope_io','worker_options',mock, ...
    'config',msiq.rx_mock_config());
fig=msiq.rx_workbench_app(options); worker=current(fig).worker;
guard=onCleanup(@() finish_reference(fig,worker,mock.reference_release_path));
await(fig,@(s) s.first_capture_complete,60);
assert(isempty(current(fig).reference_worker),'Reference lookup started before the first frame rendered.');
await(fig,@(s) s.reference_busy,10);
state=current(fig);
assert(isempty(state.reference_bundle) && strcmp(state.reference_request.action,'reference'));
assert(~strcmp(state.worker_request.action,'reference'));
assert(~isempty(findobj(state.home.axes.wave_top,'Tag','rx_waveform')));
await(fig,@(~) isfile(mock.reference_log_path) && ...
    contains(fileread(mock.reference_log_path),'REFERENCE BEGIN'),60);
log=fileread(mock.log_path);
capture_count=count(log,'CAPTURE END');
% The held file request proves independence; allow cold analysis and a full
% settings refresh without imposing an unrelated two-frame throughput limit.
await(fig,@(~) count(fileread(mock.log_path),'CAPTURE END')>=capture_count+2,10);
assert(current(fig).reference_busy,'File lookup did not overlap repeated acquisition.');
started=tic;
invoke(state.home.h_pause); invoke(state.home.h_settings);
set(state.home.h_center,'String','1'); invoke(state.home.h_center);
set(state.home.h_bandwidth,'String','1'); invoke(state.home.h_bandwidth);
assert(toc(started)<.5,'Background file lookup blocked the GUI.');
set(state.home.h_off1,'String','.014'); invoke(state.home.h_off1);
await(fig,@(s) ~s.busy,10);
state=current(fig);
assert(state.reference_busy && abs(state.scope_status.channels(1).offset_v-.014)<1e-12, ...
    'The file lookup serialized a hardware edit.');
release_reference(mock.reference_release_path);
await(fig,@(s) ~s.reference_busy,10);
state=current(fig);
assert(state.connected && ~state.running && state.manual_band);
assert(state.plot_state.center_hz==1e9 && state.plot_state.bandwidth_hz==1e9, ...
    'Late reference metadata overwrote a user-edited band.');
log=fileread(mock.log_path);
assert(count(log,'CAPTURE BEGIN')>=capture_count+2 && count(log,'WRITE ')==1);
% Reference completion must also leave an unfinished input untouched.
hold_reference(mock.reference_release_path);
reference_count=count(fileread(mock.reference_log_path),'REFERENCE BEGIN');
invoke(state.home.h_settings);
set(state.home.h_ch1,'Value',3); invoke(state.home.h_ch1);
await(fig,@(s) ~s.busy,10);
invoke(state.home.h_play);
await(fig,@(s) s.first_capture_complete,10);
invoke(state.home.h_pause);
await(fig,@(s) s.reference_busy && ~s.busy,10);
await(fig,@(~) count(fileread(mock.reference_log_path),'REFERENCE BEGIN')>reference_count,10);
invoke(state.home.h_settings);
set(state.home.h_center,'String','1.25');
set(state.home.h_psd_min,'String','-137');
release_reference(mock.reference_release_path);
await(fig,@(s) ~s.reference_busy,10);
assert(strcmp(get(state.home.h_center,'String'),'1.25'));
assert(strcmp(get(state.home.h_psd_min,'String'),'-137'));
invoke(state.home.h_center); invoke(state.home.h_psd_min);
% A file-lookup exception must not close a healthy scope session.
hold_reference(mock.reference_release_path);
reference_count=count(fileread(mock.reference_log_path),'REFERENCE BEGIN');
fid=fopen(mock.failure_path,'w'); fprintf(fid,'REFERENCE'); fclose(fid);
invoke(state.home.h_settings);
await(fig,@(s) ~s.busy && ~s.settings_refresh_pending,10);
set(state.home.h_ch1,'Value',4); invoke(state.home.h_ch1);
await(fig,@(s) ~s.busy,10);
assert(isequal(current(fig).channels,{'C4','C2'}));
invoke(state.home.h_play);
await(fig,@(s) s.first_capture_complete,10);
invoke(state.home.h_pause);
await(fig,@(~) count(fileread(mock.reference_log_path),'REFERENCE BEGIN')>reference_count,10);
release_reference(mock.reference_release_path);
await(fig,@(s) ~s.reference_pending && ~s.reference_busy && ~s.busy,10);
state=current(fig);
assert(state.connected && ~state.running);
assert(contains(get(state.home.h_band_source,'TooltipString'),'REFERENCE'));
assert(~contains(fileread(mock.log_path),'CLOSE'));
delete(mock.failure_path);
% A file-only owner refuses instrument actions before opening any session.
file_worker=state.reference_worker;
file_worker.submit(struct('action','connect'));
started=tic; ready=false;
while toc(started)<10 && ~ready
    [ready,response]=file_worker.poll(); pause(.02);
end
assert(ready && ~response.ok && strcmp(response.error_id,'RX_Workbench:FileOnly'));
assert(count(fileread(mock.log_path),'OPEN')==1,'The reference process opened an instrument session.');
% Change route while a matching old-route reference is still being loaded.
invoke(state.home.h_settings);
await(fig,@(s) ~s.busy && ~s.settings_refresh_pending,10);
set(state.home.h_ch1,'Value',1); invoke(state.home.h_ch1);
await(fig,@(s) ~s.busy,10);
assert(isequal(current(fig).channels,{'C1','C2'}));
invoke(state.home.h_play);
await(fig,@(s) s.first_capture_complete,10);
invoke(state.home.h_pause); await(fig,@(s) ~s.busy,10);
await(fig,@(s) ~s.reference_pending && ~s.reference_busy,10);
hold_reference(mock.reference_release_path);
reference_count=count(fileread(mock.reference_log_path),'REFERENCE BEGIN');
state=current(fig); state.reference_pending=true; state.reference_path=options.reference_bundle;
state.manual_band=false;
state.reference_request=struct();
setappdata(fig,'rx_workbench_state',state);
tick(fig); await(fig,@(s) s.reference_busy,10);
await(fig,@(~) count(fileread(mock.reference_log_path),'REFERENCE BEGIN')>reference_count,10);
set(state.home.h_ch1,'Value',3); invoke(state.home.h_ch1);
await(fig,@(s) ~s.busy,10);
state=current(fig); band_before=state.plot_state.bandwidth_hz;
state.manual_band=false;
setappdata(fig,'rx_workbench_state',state);
release_reference(mock.reference_release_path);
await(fig,@(s) ~s.reference_busy,10);
assert(isequal(current(fig).channels,{'C3','C2'}) && isempty(current(fig).reference_bundle));
assert(current(fig).plot_state.bandwidth_hz==band_before);
fprintf('RX background reference PASS: capture/edit continue, manual edit wins, file failure isolated, no instrument access\n');
end

function hold_reference(path)
if isfile(path), delete(path); end
end

function release_reference(path)
fid=fopen(path,'w');
assert(fid>=0,'msiq:validation:ReferenceRelease','Cannot release reference worker: %s',path);
fclose(fid);
end

function finish_reference(fig,worker,path)
release_reference(path);
finish(fig,worker);
end

function validate_empty_transport(output_dir)
% A local EOF stream exercises the real byte-reader without creating VISA.
path=fullfile(output_dir,'empty_scope_stream.txt');
fid=fopen(path,'w+');
assert(fid>=0);
guard=onCleanup(@() fclose(fid));
session=struct('kind','scope','mock',false,'interface',fid);
failed=false;
try
    msiq.instruments.capture_scope_raw(session,{'C1'});
catch exception
    failed=strcmp(exception.identifier,'msiq:instrument:ScopeReadTimeout') && ...
        contains(exception.message,'C1:WAVEFORM? ALL');
end
clear guard;
assert(failed,'Empty byte read must fail immediately with the channel command.');
assert(endsWith(strtrim(fileread(path)),'TRMD AUTO'),'Timeout did not restore trigger.');
end

function validate_default_startup(output_dir)
mock=struct('capture_delay_s',.1,'record_count',100000, ...
    'startup_warning',true, ...
    'log_path',fullfile(output_dir,'default_startup_audit.log'), ...
    'failure_path',fullfile(output_dir,'default_startup_failure.txt'));
fid=fopen(mock.log_path,'w'); fclose(fid);
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false, ...
    'find_reference',false,'asynchronous',true, ...
    'worker_factory','msiq.instruments.mock_rx_scope_io','worker_options',mock, ...
    'config',msiq.rx_mock_config()));
guard=onCleanup(@() finish_default(fig));
% No manual startup or tick: exercise the same timer path as RX_Workbench().
await_default(fig,@(s) s.connected && isfield(s.raw,'live_spectra'),60);
await_log_count(mock.log_path,'CAPTURE END',3,15);
state=current(fig); invoke(state.home.h_pause);
await_default(fig,@(s) ~s.busy,15);
before=count(fileread(mock.log_path),'CAPTURE BEGIN');
pause(.5); drawnow;
assert(count(fileread(mock.log_path),'CAPTURE BEGIN')==before);
state=current(fig);
assert(strcmp(get(state.home.h_play,'Enable'),'on'));
assert(all(strcmp(get(state.home.hardware_edits,'Enable'),'on')));
set(state.home.h_off1,'String','.01'); invoke(state.home.h_off1);
await_default(fig,@(s) ~s.busy && isempty(s.pending),10);
state=current(fig);
assert(~state.running && abs(state.scope_status.channels(1).offset_v-.01)<1e-12);
invoke(state.home.h_play);
await_log_count(mock.log_path,'CAPTURE END',before+2,15);
assert(current(fig).running);
fprintf('RX default timer startup / pause / edit / resume PASS\n');
end

function await_default(fig,predicate,limit)
started=tic;
while toc(started)<limit
    pause(.05); drawnow;
    if predicate(current(fig)), return; end
end
state=current(fig);
error('msiq:validation:DefaultStartup','%s',get(state.home.h_status,'String'));
end

function finish_default(fig)
if ~isgraphics(fig), return; end
state=current(fig);
if ~isempty(state.worker), finish(fig,state.worker);
else
    if ~isempty(state.timer) && isvalid(state.timer), stop(state.timer); delete(state.timer); end
    delete(fig);
end
end

function state=current(fig)
state=getappdata(fig,'rx_workbench_state');
end
function tick(fig)
callback=getappdata(fig,'rx_workbench_tick'); callback([],[]);
end
function invoke(handle)
callback=get(handle,'Callback'); callback(handle,[]);
end
function await(fig,predicate,seconds_limit)
started=tic;
while toc(started)<seconds_limit
    tick(fig); drawnow;
    if predicate(current(fig)), return; end
    pause(.02);
end
state=current(fig);
stack=dbstack;
error('msiq:validation:AsyncTimeout','%s; caller %s:%d; busy=%d, running=%d, reference_busy=%d', ...
    get(state.home.h_status,'String'),stack(2).name,stack(2).line, ...
    state.busy,state.running,state.reference_busy);
end
function await_log(path,message,seconds_limit)
await_log_count(path,message,1,seconds_limit);
end
function await_log_count(path,message,n,seconds_limit)
started=tic;
while toc(started)<seconds_limit
    if isfile(path) && count(fileread(path),message)>=n, return; end
    pause(.02); drawnow;
end
error('msiq:validation:AsyncLog','Missing %s',message);
end
function finish(fig,worker)
workers={worker};
if isgraphics(fig)
    state=current(fig);
    if ~isempty(state.reference_worker), workers{end+1}=state.reference_worker; end
    if ~isempty(state.timer) && isvalid(state.timer), stop(state.timer); delete(state.timer); end
    delete(fig);
end
for k=1:numel(workers), workers{k}.close(); end
for k=1:numel(workers)
    started=tic;
    while ~workers{k}.process.HasExited && toc(started)<30, pause(.05); end
    assert(workers{k}.process.HasExited,'The background owner did not close safely.');
end
end
