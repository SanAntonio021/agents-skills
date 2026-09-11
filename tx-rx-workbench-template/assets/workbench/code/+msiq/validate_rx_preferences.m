function validate_rx_preferences(output_dir)
%VALIDATE_RX_PREFERENCES Reopen real controls with isolated display-only storage.
path=fullfile(output_dir,'rx_preferences.mat');
if isfile(path), delete(path); end
mock=struct('capture_delay_s',0,'record_count',10000, ...
    'log_path',fullfile(output_dir,'preference_io.log'), ...
    'failure_path',fullfile(output_dir,'preference_failure.txt'));
io=msiq.instruments.mock_rx_scope_io(mock);
options=struct('visible',false,'maximize',false,'synchronous_startup',true, ...
    'use_timer',false,'find_reference',false,'preferences_path',path,'io',io, ...
    'config',msiq.rx_mock_config());
fig=msiq.rx_workbench_app(options);
guard=onCleanup(@() finish(fig));
state=current(fig);
data=get(state.home.h_tdiv,'UserData');
assert(strcmp(get(data.unit,'String'),'us/div') && data.multiplier==1e-6);
assert(strcmp(get(state.home.h_tdiv,'String'),'5'));
assert(~state.plot_state.psd_locked && isempty(state.preferences.channels));
tick(fig); state=current(fig);
assert(state.plot_state.psd_locked,'First valid spectrum must fit and lock.');
initial_limits=state.plot_state.psd_ylim;
tick(fig); assert(isequal(current(fig).plot_state.psd_ylim,initial_limits));
assert(contains(get(state.home.h_wave_info(1),'String'),'mV'));
% A front-panel unit change must not reinterpret an unfinished keyboard edit.
set(state.home.h_tdiv,'String','12');
io.write(state.session,'TDIV 5e-9');
tick(fig); state=current(fig); data=get(state.home.h_tdiv,'UserData');
assert(strcmp(get(state.home.h_tdiv,'String'),'12') && data.multiplier==1e-6);
invoke(state.home.h_tdiv); state=current(fig);
assert(abs(state.scope_status.timebase-12e-6)<1e-15);
invoke(state.home.h_pause);
set(state.home.h_tdiv,'String','10'); invoke(state.home.h_tdiv);
state=current(fig);
assert(abs(state.scope_status.timebase-10e-6)<1e-15, ...
    'A displayed microsecond input must write seconds, not nanoseconds.');
assert(state.raw_stale && contains(get(state.home.h_freshness,'String'),'参数已更新'));
set(state.home.h_center,'String','1'); invoke(state.home.h_center);
set(state.home.h_bandwidth,'String','2'); invoke(state.home.h_bandwidth);
set(state.home.h_psd_min,'String','-145'); invoke(state.home.h_psd_min);
set(state.home.h_ch1,'Value',3); invoke(state.home.h_ch1);
set(state.home.h_ch2,'Value',4); invoke(state.home.h_ch2);
state=current(fig);
assert(isequal(state.channels,{'C3','C4'}) && ~state.manual_band);
set(state.home.h_center,'String','2'); invoke(state.home.h_center);
set(state.home.h_bandwidth,'String','3'); invoke(state.home.h_bandwidth);
set(state.home.h_psd_min,'String','-155'); invoke(state.home.h_psd_min);
close(fig); clear guard;
% Use a fresh device mock to prove hardware settings are not restored.
options.io=msiq.instruments.mock_rx_scope_io(mock);
writes=count(fileread(mock.log_path),'WRITE ');
fig=msiq.rx_workbench_app(options); guard=onCleanup(@() finish(fig));
state=current(fig);
assert(state.running && isequal(state.channels,{'C3','C4'}));
assert(get(state.home.h_ch1,'Value')==3 && get(state.home.h_ch2,'Value')==4);
assert(state.plot_state.center_hz==2e9 && state.plot_state.bandwidth_hz==3e9);
assert(state.plot_state.psd_ylim(1)==-155);
assert(state.scope_status.timebase==5e-6 && isempty(state.pending));
assert(count(fileread(mock.log_path),'WRITE ')==writes);
invoke(state.home.h_pause);
set(state.home.h_ch1,'Value',1); invoke(state.home.h_ch1);
set(state.home.h_ch2,'Value',2); invoke(state.home.h_ch2);
state=current(fig);
assert(state.plot_state.center_hz==1e9 && state.plot_state.bandwidth_hz==2e9);
assert(state.plot_state.psd_ylim(1)==-145);
% Channel order is part of the display key, not an unordered set.
set(state.home.h_ch1,'Value',4); invoke(state.home.h_ch1);
set(state.home.h_ch2,'Value',3); invoke(state.home.h_ch2);
state=current(fig); assert(~state.manual_band && ~state.plot_state.psd_locked);
close(fig); clear guard;
fig=msiq.rx_workbench_app(options); guard=onCleanup(@() finish(fig));
assert(isequal(current(fig).channels,{'C4','C3'}) && current(fig).running);
close(fig); clear guard;
loaded=load(path); preferences=loaded.preferences;
assert(isequal(sort(fieldnames(preferences)),sort({'version';'channels';'views'})));
assert(~contains(strjoin(fieldnames(preferences.views.C3_C4)),'timebase'));
preferences.channels={'C3','C3'}; preferences.hardware=struct('timebase',99);
preferences.views.C3_C4=struct('bad',true);
save(path,'preferences');
record=msiq.rx_view_preferences('load',path);
assert(isempty(record.channels) && ~isfield(record,'hardware') && ~isfield(record.views,'C3_C4'));
fid=fopen(path,'w'); fprintf(fid,'not a MAT file'); fclose(fid);
fig=msiq.rx_workbench_app(options); guard=onCleanup(@() finish(fig));
assert(current(fig).connected && current(fig).running);
assert(isequal(current(fig).channels,{'C1','C2'}));
close(fig); clear guard;
% Empty/off channels must not consume the first valid spectrum fit.
fig=msiq.rx_workbench_app(setfield(options,'auto_connect',false)); %#ok<SFLD>
guard=onCleanup(@() finish(fig)); state=current(fig);
record=struct('channel','C1','samples',[],'time_axis_s',[],'sample_rate_hz',NaN);
raw=struct('channels',[record record]); raw.channels(2).channel='C2';
plot_state=msiq.plotting.rx_live_dashboard(state.home.axes,raw,struct(),struct(),struct());
assert(~plot_state.psd_locked);
close(fig); clear guard;
fprintf('RX preferences PASS: ordered routes, per-pair views, read-only reopen, units, first-frame fit, stale data\n');
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
function finish(fig)
if isgraphics(fig), close(fig); end
end
