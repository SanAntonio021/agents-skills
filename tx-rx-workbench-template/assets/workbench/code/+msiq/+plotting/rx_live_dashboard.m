function state = rx_live_dashboard(handles, raw, scope_status, settings, state, render)
%RX_LIVE_DASHBOARD Paired scope traces and single-sided, calibrated PSD.
% FFT spacing comes only from the returned record, never the ADC readback.
if nargin < 5, state = struct(); end
if nargin < 4, settings = struct(); end
if nargin < 3, scope_status = struct(); end
if nargin < 6, render = true; end
state = defaults(state,settings);
if ~isfield(raw,'live_spectra')
    raw = msiq.plotting.rx_live_analysis(raw,scope_status);
end
records = field_or(raw,'channels',struct([]));
if numel(records) < 2
    if ~render, return; end
    names = {'wave_top','wave_bottom','spectrum_top','spectrum_bottom','spectrum'};
    for k = 1:numel(names)
        if isfield(handles,names{k}), placeholder(handles.(names{k}),'等待采集'); end
    end
    return;
end
[limits,time_ticks,time_key] = time_geometry(records(1:2),scope_status,state);
state.time_limits_s = limits;
state.time_ticks_s = time_ticks;
state.time_geometry_key = time_key;
state.time_window_locked = true;
spectra = cell(1,2);
colors = {[.05 .34 .73],[.87 .28 .08]};
wave_axes = [handles.wave_top handles.wave_bottom];
for k = 1:2
    spectra{k} = raw.live_spectra{k};
    if ~render, continue; end
    channel = channel_status(scope_status,records(k).channel);
    wave_info = draw_wave(wave_axes(k),records(k),channel,limits,time_ticks,colors{k});
    if isfield(handles,'wave_info')
        set(handles.wave_info(k),'String',wave_info,'TooltipString',wave_info);
    else
        title(wave_axes(k),{[records(k).channel ' 时域'],wave_info},'FontSize',9,'Interpreter','none');
    end
end
frequency_limit = common_limit(spectra);
[spectra,unit] = display_spectra(spectra,scope_status);
if ~strcmp(field_or(state,'psd_unit','dbm'),unit), state.psd_locked=false; end
state.psd_unit=unit;
y_limits = spectrum_ylim(spectra,state);
state.psd_ylim = y_limits;
state.psd_locked = state.psd_locked || any(cellfun(@(s) ...
    any(isfinite(s.display_density)),spectra));
state.frequency_limit_hz = frequency_limit;
if render && isfield(handles,'spectrum_top')
    axes_list = [handles.spectrum_top handles.spectrum_bottom];
    for k = 1:2
        info = draw_spectrum(axes_list(k),spectra{k},state,y_limits,frequency_limit,colors{k});
        if isfield(handles,'spectrum_info')
            set(handles.spectrum_info(k),'String',info,'TooltipString',sprintf('%s\n%s',info,spectra{k}.details));
        else
            title(axes_list(k),{[records(k).channel ' 频谱'],info},'FontSize',9,'Interpreter','none');
        end
    end
elseif render
    % Retain the legacy single-axis offline interface.
    ax = handles.spectrum;
    cla(ax);
    hold(ax,'on');
    for k = 1:2
        plot(ax,spectra{k}.frequency_hz/1e9,spectra{k}.display_density,'Color',colors{k});
    end
    hold(ax,'off');
    decorate(ax,'频谱','频率 / GHz',psd_label(unit));
    if isfinite(frequency_limit) && frequency_limit>0
        xlim(ax,[0 frequency_limit/1e9]);
    end
    ylim(ax,y_limits);
end
state.last_time_limits_s = limits;
state.last_sample_count = [records(1:2).original_count];
state.last_sample_rate_hz = cellfun(@(s) s.sample_rate_hz,spectra);
state.spectra = spectra;
end

function state = defaults(state,settings)
fields = {'center_hz','bandwidth_hz','psd_ylim','psd_locked'};
values = {0,NaN,[NaN NaN],false};
for k = 1:numel(fields)
    if isfield(settings,fields{k}), state.(fields{k}) = settings.(fields{k});
    elseif ~isfield(state,fields{k}), state.(fields{k}) = values{k}; end
end
end

function info = draw_wave(ax,record,channel,limits,ticks,color)
samples = double(record.samples(:));
time = double(field_or(record,'time_axis_s',[]));
time = time(:);
if numel(samples) < 2 || numel(time) ~= numel(samples) || ...
        any(~isfinite(time)) || any(diff(time) <= 0) || any(~isfinite(samples))
    info=field_or(record,'wave_info','数据无效');
    placeholder(ax,info);
    decorate(ax,[record.channel ' 时域'],'','');
    return;
end
box_position = getpixelposition(ax);
index = msiq.plotting.rx_envelope_indices(samples,max(300,ceil(box_position(3)*2)));
time_scale=1e9; time_unit='ns';
if diff(limits)>=1e-6, time_scale=1e6; time_unit='us'; end
handle = findobj(ax,'Tag','rx_waveform');
if isempty(handle)
    cla(ax);
    handle = line(ax,time(index)*1e9,samples(index),'Tag','rx_waveform');
end
set(handle,'XData',time(index)*time_scale,'YData',samples(index),'Color',color,'LineWidth',.6);
delete(findall(ax,'Tag','rx_placeholder'));
decorate(ax,[record.channel ' 时域'],['示波器时间 / ' time_unit],'电压 / V');
xlim(ax,limits*time_scale);
if ~isempty(ticks)
    set(ax,'XTick',ticks*time_scale,'XTickLabel',time_tick_labels(ax,ticks*time_scale), ...
        'XTickLabelRotation',0);
end
vdiv = field_or(channel,'vertical_scale_v_per_div',NaN);
offset = field_or(channel,'offset_v',0);
if isfinite(vdiv) && vdiv > 0
    ylim(ax,[-offset-4*vdiv -offset+4*vdiv]);
    vertical_ticks=-offset+(-4:4)*vdiv;
    set(ax,'YTick',vertical_ticks,'YTickLabel',physical_tick_labels(vertical_ticks));
else
    peak = record.peak_v;
    ylim(ax,[-1 1]*max(peak*1.05,1e-6));
    set(ax,'YTickMode','auto','YTickLabelMode','auto');
end
info = record.wave_info;
end


function info = draw_spectrum(ax,spectrum,state,y_limits,frequency_limit,color)
info = spectrum.reason;
if isempty(spectrum.frequency_hz)
    placeholder(ax,spectrum.reason);
    decorate(ax,[spectrum.channel ' 频谱'],'','');
    return;
end
delete(findall(ax,'Tag','rx_placeholder'));
handle = findobj(ax,'Tag','rx_spectrum_line');
if isempty(handle)
    cla(ax);
    handle = line(ax,0,0,'Tag','rx_spectrum_line');
end
box_position = getpixelposition(ax);
index = msiq.plotting.rx_envelope_indices(spectrum.display_density,max(300,ceil(box_position(3)*2)));
set(handle,'XData',spectrum.frequency_hz(index)/1e9,'YData',spectrum.display_density(index), ...
    'Color',color,'LineWidth',.8);
xlabel_text='频率 / GHz';
if ~spectrum.limit_confirmed, xlabel_text='频率 / GHz | 采样上限'; end
decorate(ax,[spectrum.channel ' 频谱'],xlabel_text,psd_label(state.psd_unit));
set(ax,'YTickMode','auto','YTickLabelMode','auto');
if isfinite(frequency_limit) && frequency_limit>0
    xlim(ax,[0 frequency_limit/1e9]);
end
ylim(ax,y_limits);
band = findall(ax,'Tag','rx_spectrum_band');
if numel(band)>1, delete(band(2:end)); band=band(1); end
if isempty(band)
    band = patch(ax,nan(1,4),nan(1,4),color,'FaceAlpha',.045, ...
        'EdgeColor','none','Tag','rx_spectrum_band','HandleVisibility','off');
end
lo = max(0,state.center_hz-state.bandwidth_hz/2);
hi = state.center_hz+state.bandwidth_hz/2;
power = NaN;
if isfinite(lo) && isfinite(hi) && hi > lo
    clipped_hi = min(hi,spectrum.effective_limit_hz);
    if clipped_hi > lo
        set(band,'XData',[lo clipped_hi clipped_hi lo]/1e9, ...
            'YData',y_limits([1 1 2 2]),'Visible','on');
    else
        set(band,'Visible','off');
    end
    % Never present a truncated integration as the requested full-band power.
    if spectrum.impedance_known && hi <= spectrum.effective_limit_hz*(1+1e-9)
        mask = spectrum.frequency_hz >= lo & spectrum.frequency_hz <= hi;
        if any(mask)
            power = 10*log10(sum(10.^(spectrum.power_dbm_hz(mask)/10))*spectrum.delta_f_hz);
        end
    end
else
    set(band,'Visible','off');
end
if ~spectrum.impedance_known
    info = '阻抗未确认 | 功率不可用';
elseif isfinite(power)
    info = sprintf('带内功率估计 %.2f dBm',power);
else
    info = '功率不可用：统计频段越界';
end
values=spectrum.display_density;
outside='';
if all(values>y_limits(2)), outside='高于纵轴';
elseif all(values<y_limits(1)), outside='低于纵轴';
elseif any(values>y_limits(2)), outside='峰值超出纵轴';
end
if ~isempty(outside), info=[info ' | ' outside]; end
setappdata(ax,'rx_psd_outside',outside);
setappdata(ax,'rx_band_power_dbm',power);
setappdata(ax,'rx_effective_limit_hz',spectrum.effective_limit_hz);
end

function decorate(ax,name,xlabel_text,ylabel_text)
header=getappdata(ax,'rx_embedded_header');
signature={name,xlabel_text,ylabel_text,header};
if isequal(getappdata(ax,'rx_decoration'),signature)
    set(ax,'Visible','on');
    return;
end
set(ax,'Visible','on','FontSize',9,'FontName','Microsoft YaHei UI', ...
    'Units','pixels','LooseInset',[0 0 0 0], ...
    'XTickMode','auto','XTickLabelMode','auto','Color',[1 1 1]);
grid(ax,'on'); box(ax,'on');
if ~isempty(header) && isgraphics(header)
    set(ax,'PositionConstraint','innerposition');
    if ~isempty(name), set(header,'String',name); end
    set(ax.Title,'String','');
else
    set(ax,'PositionConstraint','outerposition');
    set(ax.Title,'String',name,'FontSize',10,'FontWeight','bold','Interpreter','none');
end
set(ax.XLabel,'String',xlabel_text,'Interpreter','none');
set(ax.YLabel,'String',ylabel_text,'Interpreter','none');
setappdata(ax,'rx_decoration',signature);
end

function [limits,ticks,key] = time_geometry(records,status,state)
% Lock only with an explicit horizontal-position readback, never by rounding
% waveform timestamps. Old records without this readback retain their geometry.
delay=field_or(status,'trigger_delay_s',NaN);
key=struct('channels',{{records.channel}}, ...
    'timebase',field_or(status,'timebase',NaN),'trigger_delay_s',delay, ...
    'sample_rate_hz',field_or(status,'sample_rate_hz',NaN), ...
    'memory_depth',field_or(status,'memory_depth',NaN));
if isfinite(delay) && field_or(state,'time_window_locked',false) && ...
        isequaln(field_or(state,'time_geometry_key',struct()),key) && ...
        isfield(state,'time_ticks_s') && ~isempty(state.time_ticks_s)
    limits=state.time_limits_s;
    ticks=state.time_ticks_s;
    return;
end
values = [];
origin=NaN;
for k = 1:numel(records)
    time = double(field_or(records(k),'time_axis_s',[]));
    time = time(isfinite(time));
    if ~isempty(time)
        values = [values; min(time(:)); max(time(:))]; %#ok<AGROW>
        if ~isfinite(origin), origin=time(1); end
    end
end
ticks=[];
timebase=field_or(status,'timebase',NaN);
if isfinite(timebase) && timebase>0 && isfinite(origin)
    ticks=origin+(0:10)*timebase;
    limits=ticks([1 end]);
    return;
end
if numel(values)<2 || max(values)<=min(values), limits = [0 1e-9];
else, limits = [min(values) max(values)]; end
end

function labels=physical_tick_labels(values)
% Descriptor roundoff must not add spurious decimals or a negative zero.
step=min(diff(values));
values=round(values,3-floor(log10(step)));
values(values==0)=0;
labels=arrayfun(@(x) sprintf('%.12g',x),values,'UniformOutput',false);
end

function labels=time_tick_labels(ax,values)
% Scope descriptors are binary floating point.  When the tick origin is
% within a small fraction of the time/div grid, snap labels to that grid so
% values such as -1.0001 ns do not expose descriptor roundoff.
if numel(values)>1
    step=min(abs(diff(values)));
    if isfinite(step) && step>0
        snapped=round(values/step)*step;
        tolerance=max(1e-12,abs(step)*1e-3);
        if max(abs(values-snapped))<=tolerance
            % Round again at a precision derived from the displayed grid;
            % this removes the residual left by binary floating point.
            digits=max(0,ceil(-log10(step))+3);
            values=round(snapped,digits);
        end
    end
end
labels=physical_tick_labels(values);
position=getpixelposition(ax);
cached=getappdata(ax,'rx_time_label_fit');
if isstruct(cached) && isequal(cached.labels,labels) && cached.width==position(3)
    labels=cached.fitted;
    return;
end
original=labels;
measure=text(ax,0,0,labels,'Units','pixels','Visible','off', ...
    'FontName',ax.FontName,'FontSize',ax.FontSize,'Interpreter','none');
extent=measure.Extent;
delete(measure);
% Retain all ten grid divisions; omit alternate numbers only when needed.
spacing=position(3)/(numel(values)-1);
stride=1;
for candidate=[1 2 5 10]
    stride=candidate;
    if candidate*spacing>=extent(3)+8, break; end
end
labels(mod(0:numel(labels)-1,stride)~=0)={''};
setappdata(ax,'rx_time_label_fit',struct('labels',{original}, ...
    'width',position(3),'fitted',{labels}));
end

function limit = common_limit(spectra)
bounds = cellfun(@(s) s.effective_limit_hz,spectra);
bounds = bounds(isfinite(bounds)&bounds>0);
if isempty(bounds), limit = NaN; else, limit = max(bounds); end
end

function limits = spectrum_ylim(spectra,state)
limits = state.psd_ylim;
if state.psd_locked && numel(limits)==2 && all(isfinite(limits)) && limits(2)>limits(1), return; end
values = [];
for k = 1:numel(spectra), values = [values; spectra{k}.display_density(:)]; end %#ok<AGROW>
values = values(isfinite(values));
if isempty(values), limits = [-160 -80]; return; end
peak = max(values);
limits = [max(peak-90,floor((median(values)-10)/5)*5) ceil((peak+5)/5)*5];
limits(1) = floor(limits(1)/5)*5;
if limits(2)<=limits(1), limits = [peak-60 peak+5]; end
end

function [spectra,unit] = display_spectra(spectra,status)
unit='dbm';
for k=1:numel(spectra)
    s=spectra{k}; channel=channel_status(status,s.channel);
    impedance=field_or(channel,'impedance_ohm',NaN);
    s.impedance_known=field_or(s,'impedance_known',isfinite(impedance)&&impedance>0);
    s.limit_confirmed=field_or(s,'limit_confirmed', ...
        isfinite(field_or(channel,'analog_bandwidth_hz',NaN)) || ...
        isfinite(field_or(channel,'bandwidth_limit_hz',NaN)));
    if ~s.impedance_known && ~isempty(s.frequency_hz), unit='voltage'; end
    if ~isfield(s,'voltage_dbv2_hz')
        % Older cached PSDs used a 50 Ohm fallback when impedance was unknown.
        if ~isfinite(impedance) || impedance<=0, impedance=50; end
        s.voltage_dbv2_hz=s.power_dbm_hz+10*log10(impedance/1000);
    end
    spectra{k}=s;
end
for k=1:numel(spectra)
    if strcmp(unit,'voltage'), spectra{k}.display_density=spectra{k}.voltage_dbv2_hz;
    else, spectra{k}.display_density=spectra{k}.power_dbm_hz; end
end
end

function label=psd_label(unit)
if strcmp(unit,'voltage'), label='PSD / dB(V^2/Hz)';
else, label='PSD / dBm/Hz'; end
end

function channel = channel_status(status,name)
channel = struct();
channels = field_or(status,'channels',struct([]));
if isempty(channels), return; end
index = find(strcmpi({channels.channel},name),1);
if ~isempty(index), channel = channels(index); end
end


function placeholder(ax,message)
delete(findall(ax,'Tag','rx_spectrum_band'));
cla(ax);
setappdata(ax,'rx_band_power_dbm',NaN);
setappdata(ax,'rx_effective_limit_hz',NaN);
setappdata(ax,'rx_psd_outside','');
decorate(ax,'','','');
text(ax,.5,.5,message,'Units','normalized','HorizontalAlignment','center', ...
    'VerticalAlignment','middle','Interpreter','none','Tag','rx_placeholder', ...
    'Color',[.5 .18 .12]);
end

function value = field_or(object,name,fallback)
if isstruct(object) && isfield(object,name) && ~isempty(object.(name))
    value = object.(name);
else
    value = fallback;
end
end
