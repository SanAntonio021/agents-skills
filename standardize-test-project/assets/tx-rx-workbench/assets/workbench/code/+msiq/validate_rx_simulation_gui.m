function note=validate_rx_simulation_gui(output_dir)
%VALIDATE_RX_SIMULATION_GUI Source lifecycle and real GUI callback regression.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
[~,where]=fileattrib(output_dir); output_dir=where.Name;
opts=struct('visible',false,'maximize',false,'use_timer',false,'auto_connect',false, ...
    'preferences_path','','results_root',output_dir,'simulation',struct('cache_dir',fullfile(output_dir,'cache')));
fig=msiq.rx_workbench_app(opts); guard=onCleanup(@()finish(fig));
s=state(); assert(strcmp(s.source_mode,'simulation') && ~s.connected && isempty(s.worker) && isempty(s.reference_worker));
assert(isequal(s.channels,{'C3','C4'}) && strcmp(get(s.home.h_play,'String'),'开始观察'));
assert(isequal(s.home.board.getDraft().rf,20*ones(1,6)));
% Editing the observation band is atomic and cannot alter DSP/balance settings.
original_plot=s.plot_state; original_manual=s.manual_band; original_source=s.band_source;
original_cfg=s.cfg; original_profile=s.if_profile;
set(s.home.h_center,'String','2'); invoke(s.home.h_center);
s=state(); accepted=s.plot_state;
set(s.home.h_bandwidth,'String','1'); invoke(s.home.h_bandwidth); s=state();
assert(isequaln(s.plot_state,accepted),'Invalid interval changed the integration band');
set(s.home.h_center,'String','.5'); invoke(s.home.h_center); s=state();
assert(s.plot_state.center_hz==.75e9 && s.plot_state.bandwidth_hz==.5e9);
assert(isequal(get(s.home.h_bandwidth,'BackgroundColor'),[1 1 1]),'Corrected interval retained invalid styling');
assert(isequaln(s.cfg,original_cfg)&&isequaln(s.if_profile,original_profile),'Display band changed formal processing');
s.plot_state=original_plot; s.manual_band=original_manual; s.band_source=original_source; put(s);
for shape={[1280 720],[1920 1080]}
    set(fig,'Position',[20 20 shape{1}]); drawnow; resize=get(fig,'SizeChangedFcn'); resize(fig,[]); s=state();
    assert_accessible(s.home.h_simulation,shape{1}); assert_accessible(s.home.h_measurement,shape{1}); assert_accessible(s.home.h_stop,shape{1});
    scope=get(s.home.param_panel,'Position'); display=get(s.home.display_panel,'Position'); board=get(s.home.board.panel,'Position');
    assert(scope(2)>=display(2)+display(4) && display(2)>=board(2)+board(4));
    original=getpixelposition(s.home.plot_panel,true); slider=s.home.scroll; set(slider,'Value',get(slider,'Min')); invoke(slider);
    assert(isequal(original,getpixelposition(s.home.plot_panel,true)));
end
% Duplicate selection is rejected beside both controls, rather than only at top.
s=state(); set(s.home.h_ch2,'Value',3); invoke(s.home.h_ch2); s=state();
assert(get(s.home.h_ch2,'Value')==4 && contains(get(s.home.h_channel_error,'String'),'通道重复'));
assert(get(s.home.h_ch1,'BackgroundColor')*[1;0;0]>.9);
set(s.home.h_ch2,'Value',2); invoke(s.home.h_ch2); s=state(); assert(isempty(get(s.home.h_channel_error,'String')));
set(s.home.h_ch2,'Value',4); invoke(s.home.h_ch2);
% Programmatic invocation cannot bypass the same operation lock as the buttons.
s=state(); s.running=true; put(s); invoke(s.home.h_measurement); assert(strcmp(state().source_mode,'simulation'));
s=state(); s.running=false; s.busy=true; put(s); invoke(s.home.h_measurement); assert(strcmp(state().source_mode,'simulation'));
s=state(); s.busy=false; s.reference_busy=true; put(s); invoke(s.home.h_measurement); assert(strcmp(state().source_mode,'simulation'));
s=state(); s.reference_busy=false; s.startup_pending=false;
s.reference_path='simulation_reference'; s.all_daily_rows={struct('role','正式','capture',struct('run_dir','simulation_saved','source_mode','simulation'),'observation',struct())};
s.raw=struct('marker','old_source'); oldControl=s.home.h_play;
s.worker=fixture(false,true); s.reference_worker=fixture(false,true); put(s);
invoke(s.home.h_measurement); s=state(); assert(strcmp(s.source_switch,'measurement') && strcmp(s.source_mode,'simulation'));
assert(isgraphics(oldControl),'Old controls stay until both workers release');
s.worker.process.HasExited=true; put(s); tick(); assert(strcmp(state().source_mode,'simulation'));
s=state(); s.reference_worker.process.HasExited=true; put(s); tick(); s=state();
assert(strcmp(s.source_mode,'measurement') && ~s.connected && ~s.running && isempty(fieldnames(s.raw)) && ~isgraphics(oldControl));
assert(isempty(s.reference_path) && isempty(fieldnames(s.simulation_source)) && isempty(field_or(s,'all_daily_rows',{})));
s.reference_path='measurement_reference'; put(s); invoke(s.home.h_simulation); s=state();
assert(strcmp(s.source_mode,'simulation') && strcmp(s.reference_path,'simulation_reference') && numel(s.all_daily_rows)==1);
assert(isempty(fieldnames(s.raw)) && isempty(s.worker) && isempty(s.reference_worker));
invoke(s.home.h_history); s=state(); assert(contains(join(string(get(s.home.h_metrics,'String')),newline),'来源：模拟'));
unknown=s.all_daily_rows{1}; unknown.capture=rmfield(unknown.capture,'source_mode');
setappdata(s.home.h_history,'records',{unknown}); invoke(s.home.h_history); s=state();
assert(contains(join(string(get(s.home.h_metrics,'String')),newline),'来源未记录'));
% Successful process exit with failed session release must not change source.
s.worker=fixture(true,false); put(s); invoke(s.home.h_measurement); s=state();
assert(strcmp(s.source_mode,'simulation') && contains(get(s.home.h_status,'String'),'释放失败'));
s.worker=[]; s.source_release_error=''; put(s);
% A stale response cannot paint into the new source epoch.
s=state(); s.worker=fixture(true,true); s.worker.poll=@late_result; s.worker_request=struct('action','capture','source_epoch',s.source_epoch-1);
s.busy=true; s.raw=struct('marker','current_source'); put(s); tick(); s=state();
assert(strcmp(s.raw.marker,'current_source') && ~s.busy); s.worker=[]; s.raw=struct(); put(s);
% Explicit conflicting old/new APIs are rejected before figure creation.
reject(struct('source_mode','simulation','offline_test',false));
reject(struct('source_mode','measurement','offline_test',true));
reject(struct('source_mode','measurement','worker_factory','msiq.rx_daily_mock_io'));
% Actual native preparation and scope worker; no test waveform injected into UI.
s=state(); s.reference_path=''; s.all_daily_rows={}; s.cfg.results_root=output_dir; put(s);
invoke(s.home.h_play); await(@(q)q.first_capture_complete,180); s=state(); invoke(s.home.h_pause); await(@(q)~q.busy,60); s=state();
assert(s.connected && ~isempty(s.worker) && ~isempty(s.reference_worker));
assert(strcmp(s.simulation_source.source_mode,'simulation') && isfile(s.reference_path));
assert(strcmp(s.cfg.results_root,output_dir),'Generation must preserve the GUI result directory');
assert(numel(s.raw.channels)==2 && all([s.raw.channels.wave_valid]));
% The source selector is locked throughout observation and available only idle.
assert(strcmp(get(s.home.h_simulation,'Enable'),'inactive'));
assert(isequal(get(s.home.h_simulation,'ForegroundColor'),[1 1 1]));
assert(contains(get(s.home.h_psd_label,'String'),'dBm/Hz'));
s=state(); selection=get(s.home.position_group,'SelectionChangedFcn'); set(s.home.position_group,'SelectedObject',s.home.position_buttons(4)); selection(s.home.position_group,struct('NewValue',s.home.position_buttons(4)));
s=state(); invoke(s.home.board.controls.connect); await(@(q)q.home.board.getSnapshot().is_open && ~q.busy && isempty(q.board_pending),90);

s=state(); invoke(s.home.board.controls.down); await(@(q)q.home.board.getSnapshot().state_known && ~q.busy && isempty(q.board_pending),90);
s=state(); assert(strcmp(get(s.home.h_balance,'Enable'),'on'),'Successful full send must refresh balance readiness');
selection=get(s.home.subband_group,'SelectionChangedFcn');
set(s.home.subband_group,'SelectedObject',s.home.subband_buttons(2)); selection(s.home.subband_group,struct('NewValue',s.home.subband_buttons(2))); s=state();
assert(s.home.board.getSelection()==2 && s.measurement_subband==2,'Shared selector must update board target');
set(s.home.subband_group,'SelectedObject',s.home.subband_buttons(1)); selection(s.home.subband_group,struct('NewValue',s.home.subband_buttons(1))); s=state();
assert(strcmp(get(s.home.h_balance,'Enable'),'on'));
for shape={[1280 720],[1920 1080]}
    sz=shape{1}; set(fig,'Position',[20 20 sz],'Visible','on'); drawnow; resize=get(fig,'SizeChangedFcn'); resize(fig,[]); s=state();
    region=get(s.home.param_panel,'Position'); slider=s.home.scroll;
    set(slider,'Value',max(0,get(slider,'Max')-(s.home.content_height-sum(region([2 4]))))); invoke(slider); drawnow;
    frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,sprintf('rx_simulation_%dx%d.png',sz)));
    assert_accessible(s.home.h_stop,sz);
    region=get(s.home.board.panel,'Position'); set(slider,'Value',max(0,get(slider,'Max')-(s.home.content_height-sum(region([2 4]))))); invoke(slider); drawnow;
    frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,sprintf('rx_simulation_board_%dx%d.png',sz)));
end
old=s.worker; oldReference=s.reference_worker; invoke(s.home.h_measurement); await(@(q)strcmp(q.source_mode,'measurement'),90); s=state();
assert(old.process.HasExited && oldReference.process.HasExited && old.release_status().ok && oldReference.release_status().ok);
assert(isempty(s.worker) && isempty(s.reference_worker) && ~s.connected && isempty(fieldnames(s.raw)));
assert(strcmp(s.reference_path,'measurement_reference'),'References must remain source-specific');
assert(isequal(get(s.home.h_measurement,'ForegroundColor'),[1 1 1]));
set(fig,'Position',[20 20 1280 720],'Visible','on'); drawnow;
frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,'rx_measurement_idle_1280x720.png'));
note='PASS: simulation default; explicit conflicts; operation locks; dual-worker release/wait/failure; late result ignored; separate reference/history; real simulated acquisition; rebuilt controls and two layouts';
    function s=state(), s=getappdata(fig,'rx_workbench_state'); end
    function put(s), setappdata(fig,'rx_workbench_state',s); end
    function tick(), cb=getappdata(fig,'rx_workbench_tick'); cb([],[]); end
    function await(predicate,seconds_limit)
        started=tic;
        while ~predicate(state())
            s=state(); message=get(s.home.h_status,'String');
            assert(~startsWith(message,{'模拟准备失败','连接失败'}),'GUI source failure: %s',message);
            assert(toc(started)<seconds_limit,'GUI source timeout: %s',message);
            tick(); drawnow; pause(.05);
        end
    end
    function [ready,response]=late_result()
        ready=true; response=struct('ok',true,'source_epoch',state().source_epoch-1,'raw',struct('marker','wrong_source'));
    end
end
function w=fixture(exited,released)
w=struct('close',@()[],'process',struct('HasExited',exited,'ExitCode',0),'pending',false,'closing',false, ...
    'release_status',@()struct('ok',released,'errors',{{'fixture release failed'}}));
end
function invoke(h), cb=get(h,'Callback'); cb(h,[]); end
function reject(options)
try f=msiq.rx_workbench_app(options); close(f); error('validation:ExpectedFailure','Expected source conflict');
catch exception, assert(strcmp(exception.identifier,'RX_Workbench:SourceConflict'),exception.message); end
end
function assert_accessible(h,shape)
p=getpixelposition(h,true); assert(p(1)>=0 && p(2)>=0 && p(1)+p(3)<=shape(1) && p(2)+p(4)<=shape(2));
end
function value=field_or(s,name,fallback)
value=fallback; if isfield(s,name), value=s.(name); end
end
function finish(fig)
if ~isgraphics(fig), return; end
s=getappdata(fig,'rx_workbench_state');
if isstruct(s.worker), s.worker=[]; end
if isstruct(s.reference_worker), s.reference_worker=[]; end
setappdata(fig,'rx_workbench_state',s); close(fig); started=tic;
while isgraphics(fig) && toc(started)<45
    tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
end
assert(~isgraphics(fig),'GUI worker sessions did not finish releasing');
end
