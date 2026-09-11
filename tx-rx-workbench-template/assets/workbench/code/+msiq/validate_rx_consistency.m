function validate_rx_consistency(output_dir)
%VALIDATE_RX_CONSISTENCY Physical grids, calibrated units, and frame binding.
mock=struct('capture_delay_s',0,'record_count',20000, ...
    'log_path',fullfile(output_dir,'consistency_mock.log'), ...
    'failure_path',fullfile(output_dir,'consistency_failure.txt'));
io=msiq.instruments.mock_rx_scope_io(mock);
status=msiq.instruments.rx_scope_state([],io.query);
status.timebase=5e-6;
status.channels(1).vertical_scale_v_per_div=.5;
status.channels(1).offset_v=.16;
status.channels(2).vertical_scale_v_per_div=.05;
raw=io.capture([],{'C1','C2'});
for k=1:2
    raw.channels(k).time_axis_s=raw.channels(k).time_axis_s-25e-6-8e-12-raw.channels(k).time_axis_s(1);
    raw.channels(k).descriptor=struct('vertical_offset',status.channels(k).offset_v, ...
        'horizontal_offset_s',raw.channels(k).time_axis_s(1));
end
msiq.rx_capture_consistency(raw,status,status,{'C1','C2'});
changed=status; changed.trigger_delay_s=0.3e-12;
expect_changed(raw,status,changed,'trigger_delay_s');
for name={'timebase','sample_rate_hz','memory_depth'}
    changed=status; changed.(name{1})=2*changed.(name{1});
    expect_changed(raw,status,changed,name{1});
end
for name={'vertical_scale_v_per_div','offset_v','trace_state','coupling','bandwidth_limit_hz'}
    changed=status; value=changed.channels(1).(name{1});
    if isnumeric(value), changed.channels(1).(name{1})=1;
    else, changed.channels(1).(name{1})='changed'; end
    expect_changed(raw,status,changed,name{1});
end
changed_raw=raw;
changed_raw.channels(2).descriptor.vertical_offset=.01;
diagnostics=msiq.rx_capture_consistency(changed_raw,status,status,{'C1','C2'});
assert(diagnostics(2).offset_delta_v==.01);
% C1 coefficients from RX_HARDWARE_20260907_002620/result.mat.
changed_raw.channels(1).descriptor.vertical_offset=0.15997299551963806;
original_samples=changed_raw.channels(1).samples;
diagnostics=msiq.rx_capture_consistency(changed_raw,status,status,{'C1','C2'});
assert(abs(diagnostics(1).offset_delta_v+2.7004480361941807e-5)<1e-15);
assert(isequal(changed_raw.channels(1).samples,original_samples));
changed_raw=raw;
changed_raw.channels(2).descriptor.horizontal_offset_s=0;
expect_changed(changed_raw,status,status,'WAVEDESC /');
% Floating-point descriptor quantization is not a setting change.
changed_raw=raw;
changed_raw.channels(1).descriptor.vertical_offset=double(single(.16));
msiq.rx_capture_consistency(changed_raw,status,status,{'C1','C2'});

fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false, ...
    'use_timer',false,'auto_connect',false,'find_reference',false,'io',io, ...
    'config',msiq.rx_mock_config()));
guard=onCleanup(@() close(fig));
state=getappdata(fig,'rx_workbench_state');
state.scope_status=status; state.raw_scope_status=status;
state.raw=msiq.plotting.rx_live_analysis(raw,status);
setappdata(fig,'rx_workbench_state',state);
for dimensions={[1500 900],[1100 700]}
    dim=dimensions{1}; set(fig,'Position',[40 40 dim]);
    callback=get(fig,'SizeChangedFcn'); callback(fig,[]); drawnow;
    state=getappdata(fig,'rx_workbench_state');
    for k=1:2
        axes_list=[state.home.axes.wave_top state.home.axes.wave_bottom]; ax=axes_list(k);
        ticks=get(ax,'YTick');
        assert(numel(ticks)==9 && all(abs(diff(ticks)-status.channels(k).vertical_scale_v_per_div)<1e-12));
        assert(abs(mean(get(ax,'YLim'))+status.channels(k).offset_v)<1e-12);
        ticks=get(ax,'XTick');
        assert(numel(ticks)==11 && all(abs(diff(ticks)-5)<1e-10));
        assert(max(abs(get(ax,'XLim')-[-25 25]))<9e-6);
        labels=cellstr(get(ax,'XTickLabel'));
        assert(isequal(labels,cellstr(string(-25:5:25)')), ...
            'Descriptor roundoff changed readable tick labels.');
        position=get(ax,'Position'); inset=get(ax,'TightInset');
        assert(position(1)>=inset(1)-1 && position(2)>=inset(2)-1);
    end
end

settings=struct('center_hz',1e9,'bandwidth_hz',1e9);
validate_time_grid(state.home.axes,raw,status,settings);
known=msiq.plotting.rx_live_dashboard(state.home.axes,raw,status,settings,struct());
assert(strcmp(known.psd_unit,'dbm') && isfinite(getappdata(state.home.axes.spectrum_top,'rx_band_power_dbm')));
unknown=status; unknown.channels(2).impedance_ohm=NaN;
voltage=msiq.plotting.rx_live_dashboard(state.home.axes,raw,unknown,settings,known);
assert(strcmp(voltage.psd_unit,'voltage'));
assert(all(isnan(voltage.spectra{2}.power_dbm_hz)) && all(isfinite(voltage.spectra{2}.voltage_dbv2_hz)));
for ax=[state.home.axes.spectrum_top state.home.axes.spectrum_bottom]
    assert(contains(get(get(ax,'YLabel'),'String'),'V^2'));
    trace=findobj(ax,'Tag','rx_spectrum_line'); assert(all(isfinite(trace.YData)));
end
assert(isnan(getappdata(state.home.axes.spectrum_bottom,'rx_band_power_dbm')));
assert(contains(get(state.home.h_spectrum_info(2),'String'),'阻抗未确认'));
assert(~voltage.spectra{2}.limit_confirmed);
assert(contains(get(get(state.home.axes.spectrum_bottom,'XLabel'),'String'),'采样上限'));
% Returning to confirmed impedance refits once; subsequent frames hold.
voltage.psd_ylim=[-999 -998]; voltage.psd_locked=true;
known=msiq.plotting.rx_live_dashboard(state.home.axes,raw,status,settings,voltage);
assert(strcmp(known.psd_unit,'dbm') && ~isequal(known.psd_ylim,[-999 -998]));
fixed=known; fixed.psd_ylim=[-999 -998];
fixed=msiq.plotting.rx_live_dashboard(state.home.axes,raw,status,settings,fixed);
assert(isequal(fixed.psd_ylim,[-999 -998]));
assert(strcmp(getappdata(state.home.axes.spectrum_top,'rx_psd_outside'),'高于纵轴'));
fixed.psd_ylim=[10 20];
msiq.plotting.rx_live_dashboard(state.home.axes,raw,status,settings,fixed);
assert(strcmp(getappdata(state.home.axes.spectrum_top,'rx_psd_outside'),'低于纵轴'));
fixed.psd_ylim=[-150 -130];
msiq.plotting.rx_live_dashboard(state.home.axes,raw,status,settings,fixed);
assert(strcmp(getappdata(state.home.axes.spectrum_top,'rx_psd_outside'),'峰值超出纵轴'));
% The warning must fit the existing compact header, including unknown impedance.
fixed.psd_unit='voltage'; fixed.psd_ylim=[-999 -998];
msiq.plotting.rx_live_dashboard(state.home.axes,raw,unknown,settings,fixed); drawnow;
for label=state.home.h_spectrum_info
    extent=get(label,'Extent'); rect=get(label,'Position');
    assert(extent(3)<=rect(3)+1 && extent(4)<=rect(4)+1);
end
off=status; off.channels(2).trace_state='OFF';
msiq.plotting.rx_live_dashboard(state.home.axes,raw,off,settings,struct());
assert(contains(get(state.home.h_wave_info(2),'String'),'通道已关闭'));
assert(contains(get(state.home.h_spectrum_info(2),'String'),'通道已关闭'));
assert(isempty(findobj(state.home.axes.wave_bottom,'Tag','rx_waveform')));
% Both selected traces disabled: consistency checking and plotting must
% return an explicit no-data state, without a fake frequency range.
both_off=off; both_off.channels(1).trace_state='OFF';
empty_raw=struct('channels',struct('channel',{'C1','C2'},'samples',{[],[]}, ...
    'time_axis_s',{[],[]},'sample_rate_hz',{NaN,NaN}));
empty_diag=msiq.rx_capture_consistency(empty_raw,both_off,both_off,{'C1','C2'});
assert(numel(empty_diag)==2 && all(isnan([empty_diag.offset_delta_v])));
empty_plot=msiq.plotting.rx_live_dashboard(state.home.axes,empty_raw,both_off,settings,struct());
assert(isempty(empty_plot.spectra{1}.frequency_hz) && isempty(empty_plot.spectra{2}.frequency_hz));
assert(isnan(empty_plot.frequency_limit_hz));
missing=raw; missing.channels(2).samples=[]; missing.channels(2).time_axis_s=[];
msiq.plotting.rx_live_dashboard(state.home.axes,missing,status,settings,struct());
assert(contains(get(state.home.h_wave_info(2),'String'),'未收到波形'));
assert(contains(get(state.home.h_spectrum_info(2),'String'),'未收到足够采样点'));
missing=raw; missing.channels(2).samples(1)=NaN;
msiq.plotting.rx_live_dashboard(state.home.axes,missing,status,settings,struct());
assert(contains(get(state.home.h_wave_info(2),'String'),'无效'));
assert(contains(get(state.home.h_spectrum_info(2),'String'),'NaN'));

view=struct('manual_band',false,'center_hz',1e9,'bandwidth_hz',1e9, ...
    'psd_ylim',[-160 -60],'psd_locked',true,'psd_unit','voltage');
path=fullfile(output_dir,'voltage_preferences.mat');
msiq.rx_view_preferences('save',path,struct('channels',{{'C1','C2'}},'views',struct('C1_C2',view)));
record=msiq.rx_view_preferences('load',path);
assert(strcmp(record.views.C1_C2.psd_unit,'voltage'));
view=rmfield(view,'psd_unit');
record=msiq.rx_view_preferences('save','',struct('views',struct('C1_C2',view)));
assert(strcmp(record.views.C1_C2.psd_unit,'dbm'));
fprintf('RX consistency PASS: 8x10 physical grid, snapshot/descriptor drift, units, offscale, disabled/invalid channels\n');
end

function validate_time_grid(handles,raw,status,settings)
base=msiq.plotting.rx_live_dashboard(handles,raw,status,settings,struct());
original=raw;
for delta=[0.3e-12 -0.2e-12 0.4e-12]
    for k=1:2
        raw.channels(k).time_axis_s=original.channels(k).time_axis_s+delta*k;
    end
    current=msiq.plotting.rx_live_dashboard(handles,raw,status,settings,base);
    assert(isequal(current.time_limits_s,base.time_limits_s));
    assert(isequal(current.time_ticks_s,base.time_ticks_s));
    for ax=[handles.wave_top handles.wave_bottom]
        k=1+(ax==handles.wave_bottom);
        trace=findobj(ax,'Tag','rx_waveform');
        assert(abs(trace.XData(1)-raw.channels(k).time_axis_s(1)*1e6)<1e-12);
    end
end
% Even a real sub-picosecond position edit must unlock the display.
changed=status; changed.trigger_delay_s=0.3e-12;
current=msiq.plotting.rx_live_dashboard(handles,raw,changed,settings,base);
assert(~isequal(current.time_limits_s,base.time_limits_s));
changed=status; changed.timebase=2*status.timebase;
current=msiq.plotting.rx_live_dashboard(handles,raw,changed,settings,base);
assert(abs(diff(current.time_limits_s)-10*changed.timebase)<1e-18);
raw.channels(1).channel='C3'; raw.channels(2).channel='C4';
current=msiq.plotting.rx_live_dashboard(handles,raw,status,settings,base);
assert(~isequal(current.time_limits_s,base.time_limits_s));
legacy=rmfield(status,'trigger_delay_s');
current=msiq.plotting.rx_live_dashboard(handles,raw,legacy,settings,base);
assert(~isequal(current.time_limits_s,base.time_limits_s));
fprintf('RX time grid PASS: origin jitter locked, timestamps intact, position/timebase/route changes and legacy fallback\n');
% Short live windows retain readable labels without clipping their endpoints.
short=original; short_status=status; short_status.timebase=200e-12;
for k=1:2
    short.channels(k).time_axis_s=linspace(-1.001762e-9,.998238e-9,numel(short.channels(k).samples)).';
end
msiq.plotting.rx_live_dashboard(handles,short,short_status,settings,struct());
drawnow;
for ax=[handles.wave_top handles.wave_bottom]
    p=ax.Position; inset=ax.TightInset; box=getpixelposition(ax.Parent);
    assert(p(1)+p(3)+inset(3)<=box(3)+1);
    assert(numel(ax.XTick)==11 && nnz(~cellfun(@isempty,cellstr(ax.XTickLabel)))<11);
end
end

function expect_changed(raw,before,after,field)
failed=false;
try
    msiq.rx_capture_consistency(raw,before,after,{'C1','C2'});
catch exception
    failed=strcmp(exception.identifier,'RX_Workbench:CaptureChanged') && ...
        contains(exception.message,field) && contains(exception.message,' -> ');
end
assert(failed,'Missing consistency rejection for %s.',field);
end
