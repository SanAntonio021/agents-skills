function note=validate_rx_native_memory(folder)
% Normal RX entry and generated simulation, with isolated persistent files.
if nargin<1,folder=msiq.validation_artifacts('directory');end
if ~isfolder(folder),mkdir(folder);end
options=struct('visible',false,'maximize',false,'use_timer',false,'auto_connect',false, ...
    'preferences_path',fullfile(folder,'view.mat'),'scope_presets_path',fullfile(folder,'presets'), ...
    'capture_settings_path',fullfile(folder,'capture.mat'),'results_root',folder, ...
    'simulation',struct('cache_dir',fullfile(folder,'cache'),'test_fixture',true));
f=RX_Workbench('gui',options);guard=onCleanup(@()finish(f));
s=state();assert(s.native_simulation&&~s.connected&&isempty(s.worker));
set(s.home.h_ch1,'Value',1);invoke(s.home.h_ch1);s=state();
set(s.home.h_ch2,'Value',2);invoke(s.home.h_ch2);s=state();
set(s.home.position_group,'SelectedObject',s.home.position_buttons(1));
cb=get(s.home.position_group,'SelectionChangedFcn');cb(s.home.position_group,struct('NewValue',s.home.position_buttons(1)));
s=state();set(s.home.h_center,'String','.1');invoke(s.home.h_center);
expected_plot=state().plot_state;
invoke(s.home.h_play);await(@(q)q.first_capture_complete,240);
s=state();invoke(s.home.h_pause);await(@(q)~q.busy,60);
s=state();assert(isfile(s.reference_bundle)&&strcmp(get(s.home.h_reference,'Visible'),'off'));
assert(s.plot_state.center_hz==expected_plot.center_hz&&s.plot_state.bandwidth_hz==expected_plot.bandwidth_hz);
edit_value(s.home.h_vdiv1,.08);s=state();edit_value(s.home.h_off1,.002);
s=state();edit_value(s.home.h_tdiv,4e-6);s=state();edit_value(s.home.h_trdl,2e-7);
h=findobj(f,'Tag','rx_setting_TRSLOPE');d=get(h,'UserData');set(h,'Value',find(strcmp(d.choices,'NEG')));invoke(h);await(@(q)~q.busy,60);
s=state();saved=s.scope_preset;assert(~isempty(saved),s.scope_preset_error);
assert(strcmp(s.measurement_position,'awg_direct'));expected_plot=s.plot_state;
assert(isempty(s.task),'Manual preferences must not start tests');
finish(f);clear guard;
f=RX_Workbench('gui',options);guard=onCleanup(@()finish(f));
s=state();assert(~s.connected&&isempty(s.worker)&&~s.running);
assert(isequal(s.channels,{'C1','C2'})&&strcmp(s.measurement_position,'awg_direct'));
assert(s.plot_state.center_hz==expected_plot.center_hz&&s.plot_state.bandwidth_hz==expected_plot.bandwidth_hz);
invoke(s.home.h_play);await(@(q)isfield(q.scope_restore_report,'ok')&&q.scope_restore_report.ok,240);
s=state();invoke(s.home.h_pause);await(@(q)~q.busy,60);s=state();
assert(s.plot_state.center_hz==expected_plot.center_hz&&s.plot_state.bandwidth_hz==expected_plot.bandwidth_hz);
assert(s.scope_status.channels(1).vertical_scale_v_per_div==.08&&s.scope_status.channels(1).offset_v==.002);
assert(abs(s.scope_status.timebase-4e-6)<1e-15&&abs(s.scope_status.trigger_delay_s-2e-7)<1e-15);
assert(strcmp(s.scope_status.settings.fields(strcmp({s.scope_status.settings.fields.key},'TRSLOPE')).value,'NEG'));
assert(isequaln(saved.fields,s.scope_preset.fields)&&isempty(s.task));
finish(f);clear guard;
note='Normal RX simulation entry: generated paired reference, persisted channels/position/display and verified vertical/time/trigger restore after reopen; no formal test or hardware.';
    function s=state(),s=getappdata(f,'rx_workbench_state');end
    function await(predicate,limit)
        started=tic;
        while ~predicate(state())
            s=state();assert(toc(started)<limit,'validation:timeout','%s',get(s.home.h_status,'String'));
            tick=getappdata(f,'rx_workbench_tick');tick([],[]);drawnow;pause(.05);
        end
    end
    function edit_value(h,value)
        d=get(h,'UserData');set(h,'String',num2str(value/d.multiplier,16));
        cb=get(h,'KeyPressFcn');cb(h,struct('Key','return'));await(@(q)~q.busy&&isempty(q.pending),60);
    end
end
function invoke(h),cb=get(h,'Callback');cb(h,[]);end
function finish(f)
if ~isgraphics(f),return;end
close(f);started=tic;
while isgraphics(f)&&toc(started)<60
    tick=getappdata(f,'rx_workbench_tick');tick([],[]);drawnow;pause(.05);
end
assert(~isgraphics(f),'validation:release','Native simulation did not release its worker');
end
