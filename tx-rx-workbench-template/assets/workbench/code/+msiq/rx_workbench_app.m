function app = rx_workbench_app(options)
%RX_WORKBENCH_APP Live scope console. Optional I/O injection is for offline tests.
if nargin < 1, options = struct(); end
options = app_options(options);
set_chinese_font();
cfg = msiq.rx_workbench_config(options);
addpath(fullfile(cfg.code_root,'result_management'));
fig = create_figure(options);
state = initial_state(cfg, fig, options);
setappdata(fig, 'rx_workbench_state', state);
state.home = build_home(fig, state);
state.pages = build_pages(fig);
setappdata(fig, 'rx_workbench_state', state);
set(fig, 'CloseRequestFcn', @on_close, 'SizeChangedFcn', @on_resize, ...
    'WindowScrollWheelFcn', @on_scroll);
set(state.home.h_play, 'Callback', @on_play);
set(state.home.h_pause, 'Callback', @on_pause);
set(state.home.h_single, 'Callback', @(~,~) enter_test_page(fig, 'single'));
set(state.home.h_repeat, 'Callback', @(~,~) enter_test_page(fig, 'repeat'));
set(state.home.h_settings,'Callback',@on_settings);
set([state.home.h_ch1 state.home.h_ch2], 'Callback', @on_channel);
for edit_handle = state.home.hardware_edits
    set(edit_handle, 'Callback', @on_hardware_edit);
end
for edit_handle = state.home.extended_edits
    set(edit_handle,'Callback',@(~,~) submit_control_edit(fig,edit_handle));
end
set([state.home.h_center state.home.h_bandwidth state.home.h_psd_min ...
    state.home.h_psd_max], 'Callback', @on_display_edit);
set(state.home.h_auto_psd, 'Callback', @on_auto_psd);
set(state.home.scroll, 'Callback', @on_slider_scroll);
set(state.pages.h_single_start, 'Callback', @(~,~) run_tests(fig, 1));
set(state.pages.h_repeat_start, 'Callback', @on_repeat_start);
for name = {'single','repeat','result'}
    set(state.pages.(['back_' name{1}]), 'Callback', @on_back);
end
setappdata(fig, 'rx_workbench_tick', @on_tick);
setappdata(fig, 'rx_workbench_startup', @on_startup);
layout_home(state.home, fig);
sync_display_controls(state);
msiq.plotting.rx_live_dashboard(state.home.axes, struct(), struct(), struct(), struct());
if options.visible
    % Materialize the same window's native settings widgets outside all
    % monitors before showing the observation page; never flash settings.
    destination=get(fig,'Position'); monitors=get(groot,'MonitorPositions');
    staged=destination; staged(1)=max(monitors(:,1)+monitors(:,3))+100;
    set(fig,'Position',staged);
    set_page(fig,'settings'); set(fig,'Visible','on'); drawnow;
    set_page(fig,'home'); drawnow;
    set(fig,'Position',destination);
end
if options.maximize && options.visible, set(fig, 'WindowState', 'maximized'); end
drawnow;
if options.synchronous_startup
    on_startup([], []);
end
if options.use_timer
    state = get_state();
    state.timer = timer('ExecutionMode', 'fixedSpacing', 'BusyMode', 'drop', ...
        'Period', options.refresh_period_s, 'StartDelay', 0.05, 'TimerFcn', @on_tick);
    setappdata(fig, 'rx_workbench_state', state);
    start(state.timer);
end
if nargout > 0
    app = fig;
else
    uiwait(fig);
    app = [];
end

    function current = get_state()
        current = getappdata(fig, 'rx_workbench_state');
    end

    function on_startup(~, ~)
        current = get_state();
        if ~current.startup_pending, return; end
        current.startup_pending = false;
        setappdata(fig, 'rx_workbench_state', current);
        if current.close_requested, on_close([],[]); return; end
        if options.auto_connect, on_play([], []); end
    end

    function on_play(~, ~)
        current = get_state();
        if ~ismember(current.page,["home","settings"]) || current.running || ...
                current.close_requested || ~isempty(current.pending_page), return; end
        if current.busy && (~current.asynchronous || ...
                strcmp(field_or(current.worker_request,'action',''),'release')), return; end
        current.capture_rejections = 0;
        setappdata(fig,'rx_workbench_state',current);
        if current.asynchronous
            current.running=true; current.paused=false;
            setappdata(fig,'rx_workbench_state',current);
            if ~current.connected, connect_scope(fig); end
            update_buttons(fig);
            return;
        end
        if ~current.connected
            connect_scope(fig);
            if ~isgraphics(fig), return; end
            current = get_state();
        end
        if ~current.connected, return; end
        current.running = true;
        current.paused = false;
        setappdata(fig, 'rx_workbench_state', current);
        set_status(fig, '观察中');
        update_buttons(fig);
    end

    function on_pause(~, ~)
        current = get_state();
        current.running = false;
        current.paused = true;
        setappdata(fig, 'rx_workbench_state', current);
        set_status(fig, ternary(current.busy, '本次采集完成后暂停', '已暂停'));
        update_buttons(fig);
    end

    function on_hardware_edit(src, ~)
        queue_hardware_edit(fig, src);
        drain_settings(fig);
    end

    function on_display_edit(src, ~)
        current = get_state();
        if ~ismember(current.page,["home","settings"]), return; end
        value = str2double(get(src, 'String'));
        if strcmp(get(src,'String'),get(src,'UserData')), return; end
        h = current.home;
        is_band = src == h.h_bandwidth;
        if ~isfinite(value) || (is_band && value <= 0) || (src == h.h_center && value < 0)
            set(src, 'BackgroundColor', [1 .88 .86], 'TooltipString', '请输入有效数值');
            set_status(fig, '显示参数无效，保留原图');
            return;
        end
        limits = current.plot_state.psd_ylim;
        if any(~isfinite(limits))
            limits = [-160 -80];
        end
        if src == h.h_psd_min, limits(1) = value; end
        if src == h.h_psd_max, limits(2) = value; end
        is_psd = src == h.h_psd_min || src == h.h_psd_max;
        if is_psd && (any(~isfinite(limits)) || limits(2) <= limits(1))
            set_status(fig, 'PSD 上限必须大于下限');
            return;
        end
        set(src, 'BackgroundColor', [1 1 1], 'TooltipString', '', ...
            'String',format_value(value),'UserData',format_value(value));
        if src == h.h_center, current.plot_state.center_hz = value*1e9; end
        if is_band, current.plot_state.bandwidth_hz = value*1e9; end
        current.plot_state.psd_ylim = limits;
        if is_psd, current.plot_state.psd_locked = true; end
        if src == h.h_center || is_band
            current.manual_band = true;
            current.band_source = '手动统计频段';
            set(h.h_band_source, 'String', current.band_source, 'TooltipString', '');
        end
        setappdata(fig, 'rx_workbench_state', current);
        redraw_current(fig);
        save_view(fig);
    end

    function on_auto_psd(~, ~)
        current = get_state();
        current.plot_state.psd_ylim = [NaN NaN];
        current.plot_state.psd_locked = false;
        setappdata(fig, 'rx_workbench_state', current);
        redraw_current(fig);
        save_view(fig);
    end

    function on_channel(src, ~)
        current = get_state();
        index = 1 + double(src == current.home.h_ch2);
        names = get(src, 'String');
        selected = names{get(src, 'Value')};
        other = current.channels{3-index};
        if current.busy || ~isempty(current.pending) || ~isempty(current.control_pending) || strcmp(selected, other)
            set(src, 'Value', str2double(current.channels{index}(2)));
            set_status(fig, ternary(strcmp(selected, other), ...
                '两路不能选择同一通道', '操作尚未完成，稍后切换通道'));
            return;
        end
        save_view(fig);
        current = get_state();
        current.channels{index} = selected;
        current.capture_rejections = 0;
        current.raw = struct();
        current.raw_stale = false;
        current.first_capture_complete = false;
        current = restore_view(current);
        setappdata(fig, 'rx_workbench_state', current);
        sync_display_controls(current);
        save_view(fig);
        % A route change is read-only, including while observation is paused.
        if current.connected
            refresh_status(fig);
        end
        current = get_state();
        sync_controls(current, true);
        msiq.plotting.rx_live_dashboard(current.home.axes, struct(), struct(), struct(), struct());
        set([current.home.h_wave_info current.home.h_spectrum_info], 'String', '等待本通道数据');
        if current.connected, set_status(fig, '通道已切换'); end
    end

    function on_back(~, ~)
        current = get_state();
        if current.busy, return; end
        set_page(fig, 'home');
        layout_home(current.home,fig);
        redraw_current(fig);
        on_play([], []);
    end

    function on_settings(~,~)
        current=get_state();
        if current.page=="settings"
            pos=get(fig,'Position');
            size_changed=~isequal(getappdata(current.home.plot_panel,'rx_layout_size'),pos(3:4));
            set_page(fig,'home');
            layout_home(current.home,fig);
            if size_changed || current.plot_dirty, redraw_current(fig); end
        else
            set_page(fig,'settings');
            current=get_state(); current.settings_refresh_pending=true;
            setappdata(fig,'rx_workbench_state',current);
            drain_settings(fig);
        end
    end

    function on_repeat_start(~, ~)
        current = get_state();
        count = str2double(get(current.pages.h_repeat_count, 'String'));
        if ~isfinite(count) || count < 1 || count > 100 || count ~= round(count)
            set_status(fig, '重复次数必须是 1 到 100 的整数');
            return;
        end
        run_tests(fig, count);
    end

    function on_tick(~, ~)
        if ~isgraphics(fig), return; end
        current = get_state();
        if current.startup_pending
            on_startup([], []);
            return;
        end
        tick_reference(fig);
        current = get_state();
        if current.asynchronous
            try
                tick_worker(fig);
            catch exception
                current=get_state(); current.running=false; current.paused=true;
                current.busy=~isempty(current.worker) && current.worker.pending;
                current.last_exception=exception;
                fprintf(2,'%s\n',getReport(exception,'extended','hyperlinks','off'));
                setappdata(fig,'rx_workbench_state',current);
                set_status(fig,['界面更新失败 | ' exception.message]);
                update_buttons(fig);
            end
            if ~isgraphics(fig), return; end
            current=get_state();
            if current.close_requested && ~current.busy, on_close([],[]); end
            return;
        end
        if current.busy, return; end
        drain_settings(fig);
        if ~isgraphics(fig), return; end
        current = get_state();
        if current.close_requested, on_close([],[]); return; end
        if ~isgraphics(fig), return; end
        current = get_state();
        if ~current.running || ~current.connected || ~ismember(current.page,["home","settings"]), return; end
        current.busy = true;
        setappdata(fig, 'rx_workbench_state', current);
        update_buttons(fig);
        try
            status = msiq.instruments.rx_scope_state(current.session, ...
                @(s,c) monitored_query(fig,s,c));
            if isempty(current.settings_last_read) || seconds(datetime('now')-current.settings_last_read)>=5
                current.scope_status.settings=read_extended(current,current.session,false);
                current.settings_last_read=datetime('now');
                setappdata(fig,'rx_workbench_state',current);
            end
            settings=field_or(current.scope_status,'settings',struct());
            if any(strcmpi(field_or(settings,'sample_mode',''),{'SEQUENCE','RIS'}))
                current.busy=false; current.running=false; current.paused=true;
                setappdata(fig,'rx_workbench_state',current);
                set_status(fig,'不支持当前采集模式，请在设置中选择实时模式');
                update_buttons(fig); return;
            end
            active = status.channels;
            active = active(ismember({active.channel}, current.channels));
            requested = current.channels(ismember(current.channels, {active(strcmp({active.trace_state},'ON')).channel}));
            if isempty(requested)
                raw = struct('channels', struct([]));
            else
                raw = current.io.capture(current.session, requested);
            end
            after=msiq.instruments.rx_scope_state(current.session,current.io.query,status,current.channels);
            before=status; status=after;
            status.settings=field_or(current.scope_status,'settings',struct());
            current=get_state(); current.scope_status=status;
            setappdata(fig,'rx_workbench_state',current);
            raw.capture_consistency=msiq.rx_capture_consistency(raw,before,after,current.channels);
            raw = complete_channels(raw, current.channels);
            current = get_state();
            raw=msiq.rx_observation_freshness(raw,current.raw,status);
            fresh_raw = msiq.plotting.rx_live_analysis(raw,status);
            fresh_raw.capture_valid = any([fresh_raw.channels.wave_valid]);
            if fresh_raw.capture_valid
                fresh_raw.capture_reason = '';
            elseif isempty(requested)
                fresh_raw.capture_reason = ['所选通道未开启：' strjoin(current.channels, '、')];
            else
                fresh_raw.capture_reason = ['未收到有效波形：' strjoin(requested, '、')];
            end
            old_has_data = isfield(current.raw,'channels') && ...
                any(arrayfun(@(r) field_or(r,'wave_valid',false), ...
                field_or(current.raw,'channels',struct([]))));
            if fresh_raw.capture_valid || ~old_has_data || isempty(requested)
                current.raw = fresh_raw;
                current.raw_scope_status = status;
            end
            if ~isequaln(status.timebase, field_or(current.scope_status, 'timebase', NaN))
                current.plot_state.time_window_locked = false;
            end
            current.scope_status = status;
            current.raw_stale = ~fresh_raw.capture_valid;
            current.stale_reason = field_or(fresh_raw,'capture_reason','');
            current.capture_rejections = 0;
            if fresh_raw.capture_valid
                current.first_capture_complete = true;
            end
            setappdata(fig, 'rx_workbench_state', current);
            sync_controls(current, false);
            redraw_current(fig);
            if fresh_raw.capture_valid
                set_status(fig,ternary(current.running,field_or(fresh_raw,'observation_status','观察中'),'已暂停'));
            else
                set_status(fig,['无有效波形 | ' current.stale_reason]);
            end
        catch exception
            current = get_state();
            current.last_exception = exception;
            current.raw_stale = true;
            changed=strcmp(exception.identifier,'RX_Workbench:CaptureChanged');
            if changed
                current=register_capture_rejection(current,exception.message);
            else
                current.running = false;
                current.paused = true;
                current.stale_reason = '读取失败';
            end
            % Decode errors stop this capture, transport/readback errors require reconnect.
            if ~changed && should_disconnect(exception)
                current.connected = false;
                current.io.close(current.session);
                current.session = [];
            end
            setappdata(fig, 'rx_workbench_state', current);
            if changed, show_capture_rejection(fig);
            else, set_status(fig, ['采集失败，保留上次图 | ' exception.message]); end
        end
        if ~isgraphics(fig), return; end
        current = get_state();
        current.busy = false;
        setappdata(fig, 'rx_workbench_state', current);
        update_buttons(fig);
        if current.close_requested
            on_close([], []);
        elseif ~isempty(current.pending_page)
            enter_test_page(fig, current.pending_page);
        else
            drain_settings(fig);
        end
    end

    function on_resize(~, ~)
        if ~isgraphics(fig), return; end
        current = get_state();
        if isempty(current) || ~isfield(current,'home'), return; end
        pos=get(fig,'Position');
        size_changed=~isequal(getappdata(current.home.plot_panel,'rx_layout_size'),pos(3:4));
        layout_home(current.home, fig);
        layout_pages(current.pages, fig);
        if current.page=="home" && (size_changed || current.plot_dirty || ...
                ~isfield(current.plot_state,'last_sample_count'))
            redraw_current(fig);
        end
    end

    function on_slider_scroll(~,~)
        current=get_state();
        layout_scroll_content(current.home,fig);
    end

    function on_scroll(~, event)
        current = get_state();
        if current.page ~= "settings", return; end
        pointer = get(fig,'CurrentPoint');
        if isstruct(event) && isfield(event,'PointerPosition'), pointer = event.PointerPosition; end
        box = get(current.home.settings_panel,'Position');
        if pointer(1) < box(1) || pointer(1) > box(1)+box(3), return; end
        h = current.home.scroll;
        set(h,'Value', min(get(h,'Max'), max(0, get(h,'Value')-event.VerticalScrollCount*40)));
        layout_scroll_content(current.home, fig);
    end

    function on_close(~, ~)
        if ~isgraphics(fig), return; end
        current = get_state();
        if current.busy
            current.close_requested = true;
            current.running = false;
            setappdata(fig,'rx_workbench_state',current);
            set_status(fig,'正在结束当前读取');
            return;
        end
        if ~isempty(current.timer) && isvalid(current.timer)
            stop(current.timer);
            delete(current.timer);
        end
        if ~isempty(current.worker), current.worker.close(); end
        if ~isempty(current.reference_worker), current.reference_worker.close(); end
        current.io.close(current.session);
        uiresume(fig);
        delete(fig);
    end
end

function options = app_options(options)
defaults = struct('visible', true, 'maximize', true, 'position', [50 50 1500 900], ...
    'auto_connect', true, 'synchronous_startup', false, 'use_timer', true, ...
    'refresh_period_s', 0.1, 'reference_bundle', '', 'find_reference', true, 'io', struct(), ...
    'asynchronous',[],'worker_factory','','worker_options',struct(),'preferences_path',[], ...
    'config',[]);
names = fieldnames(defaults);
for k = 1:numel(names)
    if ~isfield(options,names{k}), options.(names{k}) = defaults.(names{k}); end
end
if isempty(options.asynchronous), options.asynchronous=isempty(fieldnames(options.io)); end
if options.asynchronous && ~isempty(fieldnames(options.io)) && isempty(options.worker_factory)
    error('RX_Workbench:TestIO', ...
        'Asynchronous test I/O requires worker_factory; GUI function handles cannot own the worker session.');
end
default_io = struct('open', @(spec) msiq.instruments.open_session('scope',spec,'raw'), ...
    'query', @msiq.instruments.query_scpi, 'write', @msiq.instruments.write_scpi, ...
    'capture', @(s,c) msiq.instruments.capture_scope_raw(s,c,struct('mode','observation')), 'close', @close_scope);
options.injected_io = ~isempty(fieldnames(options.io));
if isempty(fieldnames(options.io))
    options.io = default_io;
    options.offline_test = false;
elseif ~all(isfield(options.io, fieldnames(default_io)))
    error('RX_Workbench:TestIO', 'I/O injection must provide open/query/write/capture/close together.');
else
    options.offline_test = true;
end
if ~isempty(options.worker_factory), options.offline_test=true; end
end

function state = initial_state(cfg, fig, options)
channels = {'C1','C2'};
if isfield(cfg.instrument.scope,'channels')
    candidates = unique(cellstr(upper(string(cfg.instrument.scope.channels))), 'stable');
    if numel(candidates) >= 2, channels = reshape(candidates(1:2),1,2); end
end
preferences_path = options.preferences_path;
if isnumeric(preferences_path) && isempty(preferences_path)
    preferences_path = '';
    if ~options.offline_test
        preferences_path = fullfile(cfg.project_root,'rx_records','rx_workbench_preferences.mat');
    end
end
preferences = msiq.rx_view_preferences('load',preferences_path);
if ~isempty(preferences.channels), channels = preferences.channels; end
state = struct('figure',fig,'cfg',cfg,'session',[],'io',options.io,'connected',false, ...
    'asynchronous',options.asynchronous,'worker',[],'worker_request',struct(), ...
    'worker_factory',options.worker_factory,'worker_options',options.worker_options, ...
    'channels',{channels},'scope_status',struct(),'raw',struct(),'timer',[], ...
    'busy',false,'running',false,'paused',true,'startup_pending',true,'capture_rejections',0, ...
    'offline_test',options.offline_test, ...
    'preferences_path',preferences_path,'preferences',preferences,'preference_error','', ...
    'reference_path',options.reference_bundle,'find_reference',options.find_reference, ...
    'reference_pending',false,'first_capture_complete',false,'stale_reason','', ...
    'reference_worker',[],'reference_busy',false,'reference_request',struct(), ...
    'pending',struct('handle',{},'command',{},'value',{},'revision',{}), ...
    'control_pending',struct('handle',{},'key',{},'value',{},'revision',{}), ...
    'settings_refresh_pending',false,'settings_last_read',[], ...
    'revision',0,'pending_page','','close_requested',false, ...
    'page',"home",'plot_dirty',false,'plot_state',struct('center_hz',0,'bandwidth_hz', ...
    cfg.waveform.symbol_rate_hz*(1+cfg.waveform.rolloff), ...
    'psd_ylim',[-160 -80],'psd_locked',false), ...
    'band_source','项目默认统计频段','reference_bundle','','results',struct([]));
state = restore_view(state);
end

function apply_reference_band(fig,channels,info)
state = getappdata(fig,'rx_workbench_state');
if ~isequal(channels,state.channels) || state.manual_band, return; end
for handle=[state.home.h_center state.home.h_bandwidth]
    if ~strcmp(get(handle,'String'),get(handle,'UserData')), return; end
end
if ~isempty(info.path)
    state.plot_state.bandwidth_hz = info.bandwidth_hz;
    state.plot_state.center_hz = info.center_hz;
    state.reference_bundle = info.path;
    state.band_source = '本通道最近 TX 参考';
elseif ~isempty(info.error)
    state.band_source = '参考不可读，使用项目默认';
end
setappdata(fig,'rx_workbench_state',state);
sync_display_controls(state,false);
set(state.home.h_band_source,'TooltipString',strtrim([info.path ' ' info.error]));
redraw_current(fig);
end

function state = restore_view(state)
state.plot_state = struct('center_hz',0,'bandwidth_hz', ...
    state.cfg.waveform.symbol_rate_hz*(1+state.cfg.waveform.rolloff), ...
    'psd_ylim',[-160 -80],'psd_locked',false,'time_window_locked',false);
state.plot_state.psd_unit='dbm';
state.manual_band = false;
state.reference_bundle = '';
state.band_source = '项目默认统计频段';
key = strjoin(state.channels,'_');
if isfield(state.preferences.views,key)
    view = state.preferences.views.(key);
    state.manual_band = view.manual_band;
    if view.manual_band
        state.plot_state.center_hz = view.center_hz;
        state.plot_state.bandwidth_hz = view.bandwidth_hz;
        state.band_source = '手动统计频段';
    end
    state.plot_state.psd_ylim = view.psd_ylim;
    state.plot_state.psd_locked = view.psd_locked;
    state.plot_state.psd_unit = field_or(view,'psd_unit','dbm');
end
state.reference_pending = ~state.manual_band && ...
    (state.find_reference || ~isempty(state.reference_path));
end

function sync_display_controls(state,force)
if nargin<2, force=true; end
handles = [state.home.h_center state.home.h_bandwidth state.home.h_psd_min state.home.h_psd_max];
values = [state.plot_state.center_hz/1e9 state.plot_state.bandwidth_hz/1e9 state.plot_state.psd_ylim];
for k=1:4
    value = format_value(values(k));
    if force || strcmp(get(handles(k),'String'),get(handles(k),'UserData'))
        set(handles(k),'String',value,'UserData',value,'BackgroundColor',[1 1 1]);
    end
end
set(state.home.h_band_source,'String',state.band_source,'TooltipString',state.reference_bundle);
sync_psd_units(state);
for k=1:2
    set(state.home.h_wave_title(k),'String',[state.channels{k} ' 时域']);
    set(state.home.h_spectrum_title(k),'String',[state.channels{k} ' 频谱']);
end
end

function save_view(fig)
state = getappdata(fig,'rx_workbench_state');
record = state.preferences;
record.channels = state.channels;
record.views.(strjoin(state.channels,'_')) = struct('manual_band',state.manual_band, ...
    'center_hz',state.plot_state.center_hz,'bandwidth_hz',state.plot_state.bandwidth_hz, ...
    'psd_ylim',state.plot_state.psd_ylim,'psd_locked',state.plot_state.psd_locked);
record.views.(strjoin(state.channels,'_')).psd_unit=state.plot_state.psd_unit;
if isequaln(record,state.preferences), return; end
try
    state.preferences = msiq.rx_view_preferences('save',state.preferences_path,record);
    state.preference_error = '';
catch exception
    state.preference_error = ['显示偏好未保存 | ' exception.message];
end
setappdata(fig,'rx_workbench_state',state);
update_freshness(state);
end

function fig = create_figure(options)
fig = figure('Name','RX Workbench - 接收端工作台','NumberTitle','off', ...
    'MenuBar','none','ToolBar','none','Color',[.96 .97 .98], ...
    'Units','pixels','Position',options.position,'Resize','on','Visible','off', ...
    'DefaultUicontrolFontName','Microsoft YaHei UI', ...
    'DefaultUicontrolFontSize',9,'DefaultAxesFontName','Microsoft YaHei UI', ...
    'DefaultTextFontName','Microsoft YaHei UI');
end

function home = build_home(fig, state)
bg = [.96 .97 .98];
home.panel = uipanel(fig,'Units','pixels','BorderType','none','BackgroundColor',bg);
home.h_pause = uicontrol(home.panel,'Style','pushbutton','String','暂停');
home.h_play = uicontrol(home.panel,'Style','pushbutton','String','开始');
home.h_single = uicontrol(home.panel,'Style','pushbutton','String','单次测试');
home.h_repeat = uicontrol(home.panel,'Style','pushbutton','String','重复测试');
home.h_settings = uicontrol(home.panel,'Style','pushbutton','String','设置');
home.h_status = ui_text(home.panel,'待连接',[0 0 1 1]);
home.h_freshness = ui_text(home.panel,'尚无采集',[0 0 1 1]);
home.param_panel = uipanel(home.panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
home.groups = gobjects(1,3);
home.hardware_edits = gobjects(1,6);
home.extended_edits=gobjects(1,0);
for k=1:3
    p = uipanel(home.param_panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
    home.groups(k)=p;
    if k<=2
        home.(['h_ch' num2str(k)])=uicontrol(p,'Style','popupmenu', ...
            'String',{'C1','C2','C3','C4'},'Value',str2double(state.channels{k}(2)), ...
            'Position',[4 104 52 25]);
        home.(['h_trace' num2str(k)])=extended_row(p,'','TRA','',1,[178 104 72 25],k);
    else
        label=ui_text(p,'整机时基',[4 102 75 22]); set(label,'FontWeight','bold');
    end
    if k==3
        label=ui_text(p,'回读',[92 102 68 22]); set(label,'HorizontalAlignment','right');
        label=ui_text(p,'输入',[178 102 72 22]); set(label,'HorizontalAlignment','center');
    end
    if k<=2
        home.(['h_vdiv' num2str(k)])=hardware_row(p,'量程','V/div',k,'VDIV',65);
        home.(['h_off' num2str(k)])=hardware_row(p,'偏置','V',k,'OFST',20);
        home.hardware_edits(2*k-1)=home.(['h_vdiv' num2str(k)]);
        home.hardware_edits(2*k)=home.(['h_off' num2str(k)]);
    else
        home.h_tdiv=hardware_row(p,'时基','ns/div',0,'TDIV',65);
        home.hardware_edits(5)=home.h_tdiv;
        home.h_trdl=hardware_row(p,'水平位置','ns',0,'TRDL',20);
        home.hardware_edits(6)=home.h_trdl;
    end
end
home.trigger_panel=uipanel(home.panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
trigger_keys={'TRMD','TRSOURCE','TRSLOPE','TRLEVEL'};
trigger_labels={'触发模式','触发源','边沿','触发电平'};
home.trigger_groups=gobjects(1,4);
for k=1:4
    p=uipanel(home.trigger_panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
    home.trigger_groups(k)=p;
    extended_row(p,trigger_labels{k},trigger_keys{k},ternary(k==4,'V',''),1,[146 16 86 25],0);
end
home.settings_panel=uipanel(home.panel,'Units','pixels','BorderType','none', ...
    'BackgroundColor',bg,'Visible','on');
home.content=uipanel(home.settings_panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
home.scroll=uicontrol(home.settings_panel,'Style','slider','Min',0,'Max',1,'Value',1);
p=home.content;
label=ui_text(p,'频谱显示',[16 450 260 24]); set(label,'FontWeight','bold','FontSize',10);
home.h_range=ui_text(p,'显示范围：等待采集',[16 412 320 24]);
home.h_psd_min=display_row('PSD 下限','dBm/Hz','-160',370);
home.h_psd_max=display_row('PSD 上限','dBm/Hz','-80',330);
home.h_auto_psd=uicontrol(p,'Style','pushbutton','String','适配纵轴','Position',[178 286 92 28]);
label=ui_text(p,'功率统计频段',[16 225 260 24]); set(label,'FontWeight','bold','FontSize',10);
home.h_center=display_row('中心','GHz',format_value(state.plot_state.center_hz/1e9),183);
home.h_bandwidth=display_row('总带宽','GHz',format_value(state.plot_state.bandwidth_hz/1e9),143);
home.h_band_source=ui_text(p,state.band_source,[16 99 340 26]);
set(home.h_band_source,'TooltipString',state.reference_bundle);
label=ui_text(p,'示波器回读',[400 450 260 24]); set(label,'FontWeight','bold','FontSize',10);
home.h_scope_info=ui_text(p,'尚未回读',[400 105 610 325]);
home.settings_groups=gobjects(1,0);
for ch=1:2
    x=16+(ch-1)*500; y=740;
    group=uipanel(home.content,'Units','pixels','Title',[state.channels{ch} ' 通道'], ...
        'Position',[x y 478 152],'BackgroundColor',bg);
    set(group,'UserData',struct('index',ch,'label','通道'));
    home.settings_groups(end+1)=group;
    extended_row(group,'耦合 / 阻抗','CPL','',1,[278 90 150 25],ch);
    extended_row(group,'带宽限制','BWL','',1,[278 48 150 25],ch);
end
for ch=1:2
    x=16+(ch-1)*500; y=520;
    group=uipanel(home.content,'Units','pixels','Title',[state.channels{ch} ' 信号处理'], ...
        'Position',[x y 478 200],'BackgroundColor',bg);
    set(group,'UserData',struct('index',ch,'label','信号处理'));
    home.settings_groups(end+1)=group;
    keys={'AVERAGE','INTERPOLATION','ERES','RESPONSE'}; labels={'连续平均','插值','增强分辨率','响应优化'};
    for n=1:4
        extended_row(group,labels{n},keys{n},ternary(n==1,'次',''),1,[278 150-(n-1)*40 150 25],ch);
    end
end
group=uipanel(home.content,'Units','pixels','Title','触发与采集', ...
    'Position',[16 920 978 156],'BackgroundColor',bg);
home.settings_groups(end+1)=group;
extended_row(group,'保持方式','HTYPE','',1,[278 88 150 25],0);
extended_row(group,'保持时间','HTIME','ns',1e-9,[278 45 150 25],0);
extended_row(group,'记录长度上限','MSIZ','点',1,[778 88 130 25],0);
extended_row(group,'采集模式','SAMPLEMODE','',1,[778 45 130 25],0);
ui_text(home.content,'参数 | 当前回读 | 目标输入 · 修改后写入并回读，打开设置不覆盖仪器',[16 1082 970 24]);
home.content_height=1120;
home.plot_panel=uipanel(home.panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
home.axes=struct();
home.plot_frames=gobjects(1,4); home.plot_titles=gobjects(1,4); home.plot_metrics=gobjects(1,4);
names={'wave_top','spectrum_top','wave_bottom','spectrum_bottom'};
for k=1:4
    panel=uipanel(home.plot_panel,'Units','pixels','BorderType','line', ...
        'HighlightColor',[.82 .84 .86],'BackgroundColor',[1 1 1]);
    home.plot_frames(k)=panel;
    home.plot_titles(k)=ui_text(panel,'',[0 0 1 1]);
    home.plot_metrics(k)=ui_text(panel,'等待采集',[0 0 1 1]);
    set(home.plot_titles(k),'FontWeight','bold','FontSize',10);
    set(home.plot_metrics(k),'HorizontalAlignment','right','FontSize',9);
    home.axes.(names{k})=axes('Parent',panel,'Units','pixels', ...
        'PositionConstraint','innerposition','LooseInset',[0 0 0 0]);
    setappdata(home.axes.(names{k}),'rx_embedded_header',home.plot_titles(k));
end
home.h_wave_info=gobjects(1,2); home.h_spectrum_info=gobjects(1,2);
for k=1:2
    home.h_wave_info(k)=home.plot_metrics(2*k-1);
    home.h_spectrum_info(k)=home.plot_metrics(2*k);
end
home.h_wave_title=home.plot_titles([1 3]); home.h_spectrum_title=home.plot_titles([2 4]);
home.axes.wave_info=home.h_wave_info; home.axes.spectrum_info=home.h_spectrum_info;
% Keep settings widgets laid out behind an opaque observation surface.
% Switching pages must not materialize hundreds of native widget peers.
home.observation_panel=uipanel(home.panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
set([home.param_panel home.trigger_panel home.plot_panel],'Parent',home.observation_panel);
uistack(home.h_freshness,'top');

    function h=hardware_row(parent,label,unit,index,command,y)
        ui_text(parent,label,[4 y+3 64 22]);
        current=ui_text(parent,'--',[92 y+3 68 22]); set(current,'HorizontalAlignment','right');
        unit_handle=ui_text(parent,unit,[260 y+3 60 22]);
        error_text=ui_text(parent,'',[4 y-17 245 16]);
        set(error_text,'ForegroundColor',[.65 .12 .08],'FontSize',8);
        retry=uicontrol(parent,'Style','pushbutton','String','重试', ...
            'Position',[264 y-17 42 18],'Visible','off');
        h=uicontrol(parent,'Style','edit','String','--','Position',[178 y 72 26], ...
            'HorizontalAlignment','right','BackgroundColor',[1 1 1]);
        multiplier=1; if index==0, multiplier=1e-9; end
        set(h,'UserData',struct('index',index,'setting',command,'multiplier',multiplier, ...
            'current',current,'unit',unit_handle,'error',error_text,'retry',retry,'displayed','--','actual',NaN));
        set(retry,'Callback',@(~,~) retry_setting(fig,h));
    end
    function h=display_row(label,unit,value,y)
        ui_text(p,label,[16 y+3 132 22]);
        h=uicontrol(p,'Style','edit','String',value,'Position',[178 y 92 28], ...
            'HorizontalAlignment','right','BackgroundColor',[1 1 1],'UserData',value);
        unit_handle=ui_text(p,unit,[282 y+3 110 22]);
        setappdata(h,'rx_display_unit',unit_handle);
    end
    function h=extended_row(parent,label,key,unit,multiplier,position,index)
        x=position(1); y=position(2); width=position(3);
        if strcmp(key,'TRA')
            current=ui_text(parent,'--',[92 y 68 22]);
            error_position=[4 y-16 244 15];
        else
            label_x=max(4,x-270); current_x=max(80,x-125);
            if x<200, label_x=4; current_x=72; end
            setting_label(parent,label,[label_x y+2 max(62,current_x-label_x-8) 22]);
            current=ui_text(parent,'--',[current_x y+2 x-current_x-10 22]);
            error_position=[label_x y-16 x+width-label_x 15];
        end
        set(current,'HorizontalAlignment','right');
        numeric=ismember(key,{'TRLEVEL','HTIME','MSIZ','AVERAGE'});
        h=uicontrol(parent,'Style',ternary(numeric,'edit','popupmenu'),'String',{'--'}, ...
            'Position',position,'BackgroundColor',[1 1 1],'HorizontalAlignment','right');
        unit_h=gobjects(0); if ~isempty(unit), unit_h=setting_label(parent,unit,[x+width+4 y+2 32 22]); end
        data=struct('key',key,'index',index,'multiplier',multiplier,'current',current,'unit',unit_h, ...
            'error',gobjects(0),'retry',gobjects(0),'error_position',error_position, ...
            'choices',{{}},'displayed','--','actual',[], ...
            'numeric',numeric,'available',false,'writable',false);
        suffix=''; if index>0, suffix=sprintf('_%d',index); end
        set(h,'UserData',data,'Tag',['rx_setting_' strrep(key,':','_') suffix]);
        home.extended_edits(end+1)=h;
    end
end

function h=setting_label(parent,value,position)
% Static labels share a graphics surface instead of separate native widgets.
canvas=getappdata(parent,'rx_setting_labels');
if isempty(canvas) || ~isgraphics(canvas)
    canvas=axes('Parent',parent,'Units','normalized','Position',[0 0 1 1], ...
        'XLim',[0 1],'YLim',[0 1],'Visible','off','HitTest','off', ...
        'HandleVisibility','off','Color','none');
    setappdata(parent,'rx_setting_labels',canvas);
    uistack(canvas,'bottom');
end
h=text(canvas,0,0,value,'Units','pixels','Position',[position(1) position(2)+5 0], ...
    'FontName',get(groot,'defaultUicontrolFontName'),'FontSize',9, ...
    'Interpreter','none','VerticalAlignment','bottom','Color',[.16 .18 .21], ...
    'HitTest','off','Clipping','on');
end

function h = ui_text(parent, value, position)
h = uicontrol(parent,'Style','text','String',value,'Units','pixels', ...
    'Position',position,'HorizontalAlignment','left', ...
    'BackgroundColor',get(parent,'BackgroundColor'),'ForegroundColor',[.16 .18 .21]);
end

function layout_home(home, fig)
pos=get(fig,'Position'); w=pos(3); h=pos(4);
if isequal(getappdata(home.panel,'rx_layout_size'),[w h])
    layout_scroll_content(home,fig);
    layout_plots(home,fig);
    return;
end
set(home.panel,'Position',[0 0 w h]);
set(home.observation_panel,'Position',[0 0 w h-50]);
buttons=[home.h_pause home.h_play home.h_single home.h_repeat home.h_settings];
for k=1:5, set(buttons(k),'Position',[16+(k-1)*82 h-46 74 30]); end
set(home.h_status,'Position',[440 h-47 max(100,w-456) 32]);
set(home.h_freshness,'Position',[16 0 max(100,w-32) 20],'FontSize',8);
set(home.param_panel,'Position',[12 h-190 w-24 132]);
column=(w-40)/3;
for k=1:3, set(home.groups(k),'Position',[(k-1)*column 0 column-12 132]); end
set(home.trigger_panel,'Position',[12 h-238 w-24 46]);
for k=1:4, set(home.trigger_groups(k),'Position',[(k-1)*(w-24)/4 0 (w-24)/4 46]); end
viewport=max(100,h-80);
set(home.settings_panel,'Position',[12 24 w-24 viewport]);
maximum=max(0,home.content_height-viewport);
old_max=get(home.scroll,'Max'); offset=min(maximum,max(0,old_max-get(home.scroll,'Value')));
set(home.scroll,'Position',[w-40 0 14 viewport],'Max',max(1,maximum), ...
    'Value',max(1,maximum)-offset,'Visible',ternary(maximum>0,'on','off'), ...
    'SliderStep',min(1,[40 viewport*.8]/max(1,maximum)));
set(home.content,'Position',[0 viewport-home.content_height+offset w-42 home.content_height]);
set(home.h_scope_info,'Position',[400 105 max(200,w-455) 325]);
setappdata(home.panel,'rx_layout_size',[w h]);
layout_plots(home,fig);
end

function layout_scroll_content(home,fig)
pos=get(fig,'Position');
viewport=max(100,pos(4)-80);
offset=get(home.scroll,'Max')-get(home.scroll,'Value');
set(home.content,'Position',[0 viewport-home.content_height+offset pos(3)-42 home.content_height]);
end

function layout_plots(home,fig)
% Hidden axes keep their last geometry; apply the latest size on return home.
if strcmp(get(home.plot_panel,'Visible'),'off'), return; end
pos=get(fig,'Position'); w=pos(3); h=pos(4);
if isequal(getappdata(home.plot_panel,'rx_layout_size'),[w h]), return; end
plot_h=max(200,h-262);
set(home.plot_panel,'Position',[12 22 w-24 plot_h]);
gap_x=24; gap_y=12; column=(w-24-gap_x)/2; row=(plot_h-gap_y)/2;
axes_list=[home.axes.wave_top home.axes.spectrum_top home.axes.wave_bottom home.axes.spectrum_bottom];
for k=1:4
    col=mod(k-1,2); r=1-floor((k-1)/2);
    x=col*(column+gap_x); y=r*(row+gap_y);
    set(home.plot_frames(k),'Position',[x y column row]);
    set(home.plot_titles(k),'Position',[12 row-27 94 22]);
    set(home.plot_metrics(k),'Position',[112 row-27 column-126 22]);
    set(axes_list(k),'Units','pixels','PositionConstraint','innerposition', ...
        'Position',[62 44 column-96 max(80,row-80)]);
end
setappdata(home.plot_panel,'rx_layout_size',[w h]);
end

function pages = build_pages(fig)
pages = struct();
for name = {'single','repeat','result'}
    key = name{1};
    panel = uipanel(fig,'Units','normalized','Position',[0 0 1 1], ...
        'Visible','off','BorderType','none','BackgroundColor',[.96 .97 .98]);
    pages.(key) = panel;
    pages.(['back_' key]) = uicontrol(panel,'Style','pushbutton','String','返回', ...
        'Units','normalized','Position',[.02 .93 .08 .045]);
    pages.(['status_' key]) = ui_text(panel,'',[1 1 1 1]);
    set(pages.(['status_' key]),'Units','normalized','Position',[.13 .91 .83 .07]);
end
pages.h_single_reference = ui_text(pages.single,'TX 参考待选择',[1 1 1 1]);
set(pages.h_single_reference,'Units','normalized','Position',[.04 .73 .92 .10]);
pages.h_single_start = uicontrol(pages.single,'Style','pushbutton','String','开始单次测试', ...
    'Units','normalized','Position',[.04 .60 .20 .055]);
h = ui_text(pages.repeat,'重复次数',[1 1 1 1]);
set(h,'Units','normalized','Position',[.04 .77 .10 .04]);
pages.h_repeat_count = uicontrol(pages.repeat,'Style','edit','String','3', ...
    'Units','normalized','Position',[.15 .77 .08 .04]);
pages.h_repeat_start = uicontrol(pages.repeat,'Style','pushbutton','String','开始重复测试', ...
    'Units','normalized','Position',[.04 .60 .20 .055]);
pages.h_result_title = ui_text(pages.result,'测试结果',[1 1 1 1]);
set(pages.h_result_title,'Units','normalized','Position',[.04 .84 .9 .045]);
pages.h_result_table = uitable(pages.result,'Units','normalized','Position',[.02 .05 .46 .75], ...
    'ColumnName',{'序号','Channel','状态','BER','BLER','MER dB','SRO ppm','结果目录'}, ...
    'ColumnWidth',{45 115 100 80 80 85 85 260},'RowName',[]);
pages.h_result_axes = axes('Parent',pages.result,'Units','normalized','Position',[.53 .1 .44 .7]);
axis(pages.h_result_axes,'off');
end

function layout_pages(~, ~)
% Test pages use normalized geometry and resize with the same window.
end

function submit_worker(fig,request)
state=getappdata(fig,'rx_workbench_state');
state.worker_request=request;
wire=request;
if isfield(wire,'handle'), wire=rmfield(wire,'handle'); end
state.worker.submit(wire);
state.busy=true;
setappdata(fig,'rx_workbench_state',state);
update_buttons(fig);
end

function tick_worker(fig)
state=getappdata(fig,'rx_workbench_state');
if isempty(state.worker), return; end
if state.busy
    transport_failed=false;
    try
        [ready,response]=state.worker.poll();
    catch exception
        transport_failed=true;
        ready=true;
        response=struct('ok',false,'error',exception.message);
    end
    if ~ready
        if ~state.paused
            progress=state.worker.progress();
            if state.capture_rejections>0, show_capture_rejection(fig);
            elseif ~isempty(progress), set_status(fig,progress); end
        end
        update_freshness(state);
        return;
    end
    request=state.worker_request;
    state.busy=false;
    if ~response.ok && strcmp(field_or(response,'error_id',''),'RX_Workbench:CaptureChanged') && ~transport_failed
        state.scope_status=response.status;
        state=register_capture_rejection(state,response.error);
        setappdata(fig,'rx_workbench_state',state);
        sync_controls(state,false);
        show_capture_rejection(fig);
        update_buttons(fig);
        return;
    elseif ~response.ok
        disconnect = transport_failed || response_requires_disconnect(response);
        state.connected=~disconnect; state.running=false; state.paused=true;
        state.last_worker_error=response.error;
        state.raw_stale=true;
        state.stale_reason=ternary(disconnect,'读取失败','后台处理失败');
        if ismember(request.action,{'setting','control'})
            field_error(request.handle,[field_or(request,'command',field_or(request,'key','')) ' | ' response.error],true);
        end
        setappdata(fig,'rx_workbench_state',state);
        set_status(fig,[ternary(disconnect,'连接失败','采集失败') ' | ' response.error]);
    else
        switch request.action
            case {'connect','status'}
                state.scope_status=response.status;
                state.settings_refresh_pending=false;
                state.connected=true;
                setappdata(fig,'rx_workbench_state',state);
                sync_controls(state,false);
                set_status(fig,ternary(state.running,'观察中','已暂停'));
            case 'capture'
                if isequal(request.channels,state.channels)
                    state.scope_status=response.status;
                    state.capture_rejections=0;
                    state.last_capture_elapsed_s=response.elapsed_s;
                    state.last_analysis_s=response.analysis_s;
                    valid=field_or(response.raw,'capture_valid',false);
                    all_off=startsWith(field_or(response.raw,'capture_reason',''),'所选通道未开启');
                    if valid || all_off || ~isfield(state.raw,'channels') || isempty(field_or(state.raw,'channels',struct([])))
                        state.raw=response.raw;
                        state.raw_scope_status=response.status;
                    end
                    state.raw_stale=~valid;
                    state.stale_reason=field_or(response.raw,'capture_reason','');
                    if valid
                        state.first_capture_complete=true;
                    end
                    setappdata(fig,'rx_workbench_state',state);
                    sync_controls(state,false);
                    redraw_current(fig);
                    if valid
                        set_status(fig,ternary(state.running,field_or(response.raw,'observation_status','观察中'),'已暂停'));
                    else
                        set_status(fig,['无有效波形 | ' state.stale_reason]);
                    end
                end
            case 'control'
                state.scope_status=response.status;
                state.settings_refresh_pending=false;
                state.raw_stale=true; state.stale_reason='参数已更新，图像尚未更新';
                setappdata(fig,'rx_workbench_state',state);
                accept_control(fig,request,response.accepted);
                sync_controls(getappdata(fig,'rx_workbench_state'),false);
                set_status(fig,['已回读 | ' request.key]);
            case 'setting'
                state.scope_status=response.status;
                state.settings_refresh_pending=false;
                state.raw_stale=true;
                state.stale_reason='参数已更新，图像尚未更新';
                data=get(request.handle,'UserData');
                newer=~isempty(state.pending) && any(strcmp({state.pending.command},request.command));
                unchanged=isequal(str2double(get(request.handle,'String'))*data.multiplier,request.value);
                if ~newer && unchanged
                    data.displayed=format_value(response.accepted/data.multiplier);
                    set(request.handle,'String',data.displayed,'UserData',data);
                    field_error(request.handle,'',false);
                end
                setappdata(fig,'rx_workbench_state',state);
                sync_controls(state,false);
                redraw_current(fig);
                set_status(fig,['已回读 | ' request.command]);
            case 'release'
                state.connected=false;
                page=state.pending_page;
                state.pending_page='';
                setappdata(fig,'rx_workbench_state',state);
                if ~isempty(page), set_page(fig,page); end
                set_status(fig,'观察会话已释放');
        end
    end
    state=getappdata(fig,'rx_workbench_state');
    update_buttons(fig);
end
if state.close_requested, return; end
if ~isempty(state.pending_page) && ~state.busy
    if state.connected
        submit_worker(fig,struct('action','release'));
    else
        page=state.pending_page; state.pending_page='';
        setappdata(fig,'rx_workbench_state',state); set_page(fig,page);
    end
    return;
end
drain_settings(fig);
state=getappdata(fig,'rx_workbench_state');
if ~state.busy && state.connected && state.running && ismember(state.page,["home","settings"])
    submit_worker(fig,struct('action','capture','channels',{state.channels}));
    if state.capture_rejections>0, show_capture_rejection(fig);
    else, set_status(fig,'读取中'); end
end
update_freshness(getappdata(fig,'rx_workbench_state'));
end

function state=register_capture_rejection(state,reason)
state.capture_rejections=state.capture_rejections+1;
state.raw_stale=true;
state.stale_reason=reason;
if state.capture_rejections>=3
    state.running=false;
    state.paused=true;
end
end

function yes=should_disconnect(exception)
% Only transport/readback failures invalidate the instrument session. A
% local data-shape or application error must leave a healthy session open.
identifier=lower(char(string(exception.identifier)));
yes=strcmp(identifier,'rx_workbench:readback') || ...
    strcmp(identifier,'rx_workbench:transport') || ...
any(contains(identifier,{'visa','timeout','transport','readfailure','block','instrument:'}));
end

function yes=response_requires_disconnect(response)
identifier=lower(char(string(field_or(response,'error_id',''))));
yes=strcmp(identifier,'rx_workbench:readback') || ...
    strcmp(identifier,'rx_workbench:transport') || ...
    any(contains(identifier,{'visa','timeout','transport','readfailure','block','instrument:'}));
end

function show_capture_rejection(fig)
state=getappdata(fig,'rx_workbench_state');
parts=strsplit(state.stale_reason,' 不一致');
parts=strsplit(parts{1},' | ');
field=strtrim(parts{end});
names={'vertical_scale_v_per_div','offset_v','timebase','sample_rate_hz', ...
    'trigger_delay_s', ...
    'memory_depth','trace_state','coupling','bandwidth_limit_hz'};
labels={'量程','偏置','时基','采样率','水平位置','记录长度','通道开关','耦合','带宽限制'};
for k=1:numel(names), field=strrep(field,names{k},labels{k}); end
if state.capture_rejections>=3
    message=['已暂停：连续3帧校验失败 | ' field];
else
    message=sprintf('采集校验失败 %d/3 | %s',state.capture_rejections,field);
end
set_status(fig,message);
set(state.home.h_status,'TooltipString', ...
    [state.stale_reason '；已保留原图。暂停后可点击开始重试。']);
if ~state.first_capture_complete
    set(findall(fig,'Tag','rx_placeholder'),'String','未获得有效波形');
    set([state.home.h_wave_info state.home.h_spectrum_info],'String','采集校验失败');
end
end

function tick_reference(fig)
state=getappdata(fig,'rx_workbench_state');
if state.close_requested, return; end
if state.reference_busy
    try
        [ready,response]=state.reference_worker.poll();
    catch exception
        ready=true; response=struct('ok',false,'error',exception.message);
    end
    if ~ready, return; end
    state.reference_busy=false;
    request=state.reference_request;
    setappdata(fig,'rx_workbench_state',state);
    if response.ok, info=response.reference;
    else, info=struct('path','','error',response.error); end
    apply_reference_band(fig,request.channels,info);
    state=getappdata(fig,'rx_workbench_state');
end
if ~state.reference_pending || ~state.first_capture_complete, return; end
state.reference_pending=false;
try
    if isempty(state.reference_worker) || state.reference_worker.process.HasExited
        state.reference_worker=msiq.RxScopeWorker(struct(),state.worker_factory,state.worker_options,'reference');
    end
    request=struct('action','reference','project_root',state.cfg.project_root, ...
        'channels',{state.channels},'path',state.reference_path,'search',state.find_reference);
    state.reference_worker.submit(request);
    state.reference_request=request;
    state.reference_busy=true;
    setappdata(fig,'rx_workbench_state',state);
catch exception
    setappdata(fig,'rx_workbench_state',state);
    apply_reference_band(fig,state.channels,struct('path','','error',exception.message));
end
end

function update_freshness(state)
stamp=field_or(state.raw,'last_new_data_at',[]);
if ~isdatetime(stamp), stamp=field_or(state.raw,'captured_at',[]); end
if isdatetime(stamp) && isscalar(stamp) && ~isnat(stamp)
    age=max(0,seconds(datetime('now')-stamp));
    stamp.Format='HH:mm:ss';
    message=sprintf('最近读取 %s | %.1f 秒前',char(stamp),age);
    if field_or(state,'raw_stale',false)
        reason=field_or(state,'stale_reason','等待重新采集');
        if contains(reason,'本帧未采用'), reason='新采集校验失败'; end
        message=[message ' | 旧数据：' reason];
    end
else
    message='尚无采集';
    if state.capture_rejections>0, message='尚无有效波形：采集校验失败'; end
end
if isfield(state.raw,'observation_status'), message=[message ' | ' state.raw.observation_status]; end
if ~isempty(state.preference_error), message=[message ' | ' state.preference_error]; end
color=[.32 .35 .39];
if field_or(state,'raw_stale',false), color=[.68 .22 .06]; end
detail=message;
if field_or(state,'raw_stale',false), detail=[detail ' | ' state.stale_reason]; end
set(state.home.h_freshness,'String',message,'ForegroundColor',color,'TooltipString',detail);
end

function connect_scope(fig)
state = getappdata(fig,'rx_workbench_state');
if state.busy, return; end
if state.asynchronous
    try
        if ~isempty(state.worker) && state.worker.closing && ~state.worker.process.HasExited
            error('RX_Workbench:WorkerClosing','上一后台会话仍在安全退出，尚不能新建连接。');
        end
        if isempty(state.worker) || state.worker.process.HasExited
            specification=state.cfg.instrument.scope; specification.timeout_s=3;
            state.worker=msiq.RxScopeWorker(specification,state.worker_factory,state.worker_options);
            setappdata(fig,'rx_workbench_state',state);
        end
        submit_worker(fig,struct('action','connect'));
        set_status(fig,'连接 | 启动后台并回读示波器');
    catch exception
        state=getappdata(fig,'rx_workbench_state');
        state.connected=false; state.running=false; state.busy=false;
        setappdata(fig,'rx_workbench_state',state);
        set_status(fig,['连接失败 | ' exception.message]);
        update_buttons(fig);
    end
    return;
end
state.io.close(state.session);
state.session = [];
state.connected = false;
state.busy = true;
setappdata(fig,'rx_workbench_state',state);
update_buttons(fig);
set_status(fig,'连接 | 打开 VISA 会话');
drawnow;
session = [];
try
    specification = state.cfg.instrument.scope;
    specification.timeout_s = 3;
    session = state.io.open(specification);
    status = msiq.instruments.rx_scope_state(session,@(s,c) monitored_query(fig,s,c));
    status.settings=read_extended(state,session,true);
    state = getappdata(fig,'rx_workbench_state');
    state.session = session;
    state.scope_status = status;
    state.settings_last_read=datetime('now');
    state.connected = true;
    state.plot_state.time_window_locked = false;
    setappdata(fig,'rx_workbench_state',state);
    sync_controls(state,false);
    set_status(fig,'已连接');
catch exception
    state = getappdata(fig,'rx_workbench_state');
    state.io.close(session);
    state.connected = false;
    state.running = false;
    state.session = [];
    setappdata(fig,'rx_workbench_state',state);
    set_status(fig,['连接失败 | ' exception.message]);
end
state = getappdata(fig,'rx_workbench_state');
state.busy = false;
setappdata(fig,'rx_workbench_state',state);
update_buttons(fig);
end

function response = monitored_query(fig,session,command)
state = getappdata(fig,'rx_workbench_state');
if ~state.connected, set_status(fig,['回读 | ' command]); end
drawnow limitrate;
response = state.io.query(session,command);
end

function refresh_status(fig)
state = getappdata(fig,'rx_workbench_state');
if state.asynchronous
    submit_worker(fig,struct('action','status','extended_status',true));
    return;
end
state.busy = true;
setappdata(fig,'rx_workbench_state',state);
try
    status = msiq.instruments.rx_scope_state(state.session,@(s,c) monitored_query(fig,s,c));
    status.settings=read_extended(state,state.session,false);
    state = getappdata(fig,'rx_workbench_state');
    state.scope_status = status;
catch exception
    state = getappdata(fig,'rx_workbench_state');
    state.io.close(state.session);
    state.session = [];
    state.connected = false;
    state.running = false;
    set_status(fig,exception.message);
end
state.busy = false;
setappdata(fig,'rx_workbench_state',state);
update_buttons(fig);
end

function queue_hardware_edit(fig, handle)
state = getappdata(fig,'rx_workbench_state');
data = get(handle,'UserData');
if strcmp(get(handle,'String'),data.displayed) && strcmp(get(data.retry,'Visible'),'off')
    return;
end
value = str2double(get(handle,'String'))*data.multiplier;
if ~isfinite(value) || (requires_positive_setting(data.setting) && value <= 0)
    field_error(handle,'请输入有效数值',false);
    return;
end
if state.connected && isequal(value,data.actual)
    field_error(handle,'',false);
    return;
end
command = data.setting;
if data.index > 0, command = [state.channels{data.index} ':' command]; end
state.revision = state.revision+1;
request = struct('handle',handle,'command',command,'value',value,'revision',state.revision);
if ~isempty(state.pending)
    state.pending(strcmp({state.pending.command},command)) = [];
end
state.pending(end+1) = request;
setappdata(fig,'rx_workbench_state',state);
field_error(handle,ternary(state.connected,'待写入','待连接后写入'),false);
end

function retry_setting(fig, handle)
queue_hardware_edit(fig,handle);
state = getappdata(fig,'rx_workbench_state');
if ~state.connected && ~state.busy, connect_scope(fig); end
drain_settings(fig);
end

function drain_settings(fig)
state = getappdata(fig,'rx_workbench_state');
if state.busy || ~state.connected, return; end
if ~isempty(state.control_pending)
    drain_control(fig); return;
end
if isempty(state.pending)
    if state.settings_refresh_pending
        state.settings_refresh_pending=false;
        setappdata(fig,'rx_workbench_state',state);
        refresh_status(fig);
        if ~state.asynchronous, sync_controls(getappdata(fig,'rx_workbench_state'),false); end
    end
    return;
end
if state.asynchronous
    request=state.pending(1); state.pending(1)=[];
    setappdata(fig,'rx_workbench_state',state);
    request.action='setting';
    submit_worker(fig,request);
    return;
end
state.busy = true;
setappdata(fig,'rx_workbench_state',state);
update_buttons(fig);
while true
    state = getappdata(fig,'rx_workbench_state');
    if isempty(state.pending) || ~state.connected, break; end
    request = state.pending(1);
    state.pending(1) = [];
    setappdata(fig,'rx_workbench_state',state);
    command = sprintf('%s %.15g',request.command,request.value);
    phase = '写入';
    active_command = command;
    try
        set_status(fig,['写入 | ' command]);
        state.io.write(state.session,command);
        phase = '回读';
        active_command = [request.command '?'];
        response = state.io.query(state.session,active_command);
        accepted = parse_number(response);
        data = get(request.handle,'UserData');
        if ~isfinite(accepted) || (requires_positive_setting(data.setting) && accepted <= 0)
            error('RX_Workbench:Readback','无效回读：%s',char(string(response)));
        end
        data.actual = accepted;
        data.displayed = format_value(accepted/data.multiplier);
        set(request.handle,'UserData',data,'String',data.displayed);
        set(data.current,'String',data.displayed,'TooltipString',sprintf('%.15g',accepted/data.multiplier));
        field_error(request.handle,'',false);
        state = getappdata(fig,'rx_workbench_state');
        state.scope_status=msiq.instruments.rx_scope_state(state.session,state.io.query);
        state.scope_status.settings=read_extended(state,state.session,false);
        % Old samples retain the scale under which they were captured.
        state.raw_stale = true;
        state.stale_reason = '参数已更新，图像尚未更新';
        setappdata(fig,'rx_workbench_state',state);
        sync_controls(state,false);
        redraw_current(fig);
        set_status(fig,['已回读 | ' request.command ' = ' data.displayed ' | 图像待下次采集']);
    catch exception
        state = getappdata(fig,'rx_workbench_state');
        field_error(request.handle,[active_command ' | ' phase ' | ' exception.message],true);
        state.running = false;
        state.paused = true;
        state.connected = false;
        state.io.close(state.session);
        state.session = [];
        setappdata(fig,'rx_workbench_state',state);
        set_status(fig,[phase '失败 | ' active_command ' | ' exception.message]);
        break;
    end
end
state = getappdata(fig,'rx_workbench_state');
state.busy = false;
setappdata(fig,'rx_workbench_state',state);
update_buttons(fig);
end

function settings=read_extended(state,session,refresh)
cached=field_or(state.scope_status,'settings',struct());
try
    settings=msiq.instruments.rx_scope_settings(session,state.io.query,cached,refresh);
catch exception
    if ~strcmp(exception.identifier,'RX_Workbench:Unsupported'), rethrow(exception); end
    settings=struct('fields',struct([]),'error',exception.message);
end
end

function submit_control_edit(fig,handle,explicit_retry)
if nargin<3, explicit_retry=false; end
state=getappdata(fig,'rx_workbench_state'); data=get(handle,'UserData');
if (~data.available || ~data.writable) && ~explicit_retry, return; end
if data.numeric
    value=str2double(get(handle,'String'))*data.multiplier;
    if ~isfinite(value), field_error(handle,'请输入有效数值',false); return; end
else
    value=data.choices{get(handle,'Value')};
end
key=data.key;
if data.index>0, key=[state.channels{data.index} ':' key]; end
retry=~isempty(data.retry) && isgraphics(data.retry) && strcmp(get(data.retry,'Visible'),'on');
if isequaln(value,data.actual) && ~retry, field_error(handle,'',false); return; end
state.revision=state.revision+1;
request=struct('handle',handle,'key',key,'value',value,'revision',state.revision);
if ~isempty(state.control_pending)
    state.control_pending(strcmp({state.control_pending.key},key))=[];
end
state.control_pending(end+1)=request;
setappdata(fig,'rx_workbench_state',state);
field_error(handle,ternary(state.connected,'待写入','待连接后写入'),false);
if explicit_retry && ~state.connected && ~state.busy, connect_scope(fig); end
drain_settings(fig);
end

function drain_control(fig)
state=getappdata(fig,'rx_workbench_state');
request=state.control_pending(1); state.control_pending(1)=[];
setappdata(fig,'rx_workbench_state',state);
if state.asynchronous
    request.action='control'; submit_worker(fig,request); return;
end
state.busy=true; setappdata(fig,'rx_workbench_state',state);
try
    accepted=msiq.instruments.apply_rx_scope_setting(state.session,request,state.io.query,state.io.write);
    status=msiq.instruments.rx_scope_state(state.session,state.io.query);
    status.settings=read_extended(state,state.session,false);
    state=getappdata(fig,'rx_workbench_state'); state.scope_status=status;
    state.raw_stale=true; state.stale_reason='参数已更新，图像尚未更新';
    setappdata(fig,'rx_workbench_state',state);
    accept_control(fig,request,accepted);
    set_status(fig,['已回读 | ' request.key]);
catch exception
    state=getappdata(fig,'rx_workbench_state');
    field_error(request.handle,[request.key ' | ' exception.message],true);
    if should_disconnect(exception)
        state.connected=false; state.running=false; state.paused=true;
        state.io.close(state.session); state.session=[];
    end
    setappdata(fig,'rx_workbench_state',state);
    set_status(fig,['设置失败 | ' exception.message]);
end
state=getappdata(fig,'rx_workbench_state'); state.busy=false;
setappdata(fig,'rx_workbench_state',state);
sync_controls(state,false); update_buttons(fig);
end

function accept_control(fig,request,accepted)
state=getappdata(fig,'rx_workbench_state'); data=get(request.handle,'UserData');
newer=~isempty(state.control_pending) && any(strcmp({state.control_pending.key},request.key));
if data.numeric, input=str2double(get(request.handle,'String'))*data.multiplier;
else, input=data.choices{get(request.handle,'Value')}; end
if newer || ~isequaln(input,request.value), return; end
data.actual=accepted;
if data.numeric
    data.displayed=format_value(accepted/data.multiplier);
    set(request.handle,'String',data.displayed);
else
    n=find(strcmp(data.choices,char(string(accepted))),1);
    if ~isempty(n), set(request.handle,'Value',n); end
    data.displayed=char(string(accepted));
end
set(request.handle,'UserData',data); field_error(request.handle,'',false);
end

function sync_extended(state,force)
for group=state.home.settings_groups
    info=get(group,'UserData');
    if isstruct(info) && isfield(info,'index')
        title=[state.channels{info.index} ' ' info.label];
        if ~strcmp(get(group,'Title'),title), set(group,'Title',title); end
    end
end
settings=field_or(state.scope_status,'settings',struct());
fields=field_or(settings,'fields',struct([]));
for handle=state.home.extended_edits
    data=get(handle,'UserData'); key=data.key;
    if data.index>0, key=[state.channels{data.index} ':' data.key]; end
    n=[]; if ~isempty(fields), n=find(strcmp({fields.key},key),1); end
    if ~state.connected || isempty(n) || ~fields(n).available
        set(data.current,'String',ternary(state.connected,'不可用','--'));
        set(handle,'Enable','off'); data.available=false; data.writable=false;
        if ~isempty(n), set(handle,'TooltipString',fields(n).error); end
        set(handle,'UserData',data); continue;
    end
    f=fields(n);
    if ~force && data.available && isfield(data,'snapshot') && ...
            isequaln(data.snapshot,f) && strcmp(field_or(data,'resolved_key',''),key)
        continue;
    end
    data.available=true; data.writable=f.writable;
    pending=~isempty(state.control_pending) && any([state.control_pending.handle]==handle);
    if state.busy && isfield(state.worker_request,'handle')
        pending=pending || state.worker_request.handle==handle;
    end
    if data.numeric
        untouched=strcmp(get(handle,'String'),data.displayed);
        display=format_value(f.value/data.multiplier);
    else
        previous='';
        if ~isempty(data.choices) && get(handle,'Value')<=numel(data.choices)
            previous=data.choices{get(handle,'Value')};
        end
        untouched=isempty(previous) || strcmp(previous,data.displayed);
        choices=f.choices; labels=f.choice_labels;
        if ~any(strcmp(choices,char(string(f.value))))
            choices=[f.choices {char(string(f.value))}];
            labels=[f.choice_labels {char(string(f.value))}];
        end
        % Do not rebuild choices while a user edit is awaiting readback.
        if ~pending && (untouched || force)
            set(handle,'String',labels,'Value',find(strcmp(choices,char(string(f.value))),1));
            data.choices=choices;
        end
        display=char(string(f.value));
        idx=find(strcmp(choices,display),1);
        if ~isempty(idx), display=labels{idx}; end
        if endsWith(key,':BWL')
            if strcmpi(f.value,'OFF'), display='全带宽'; end
            if strcmpi(f.value,'ON'), display='20 MHz'; end
            if ~pending
                labels(strcmp(choices,'OFF'))={'全带宽'}; labels(strcmp(choices,'ON'))={'20 MHz'};
                set(handle,'String',labels);
            end
        end
    end
    set(data.current,'String',display,'TooltipString',[key ' | ' display]);
    failed=~isempty(data.retry) && isgraphics(data.retry) && strcmp(get(data.retry,'Visible'),'on');
    if (force || untouched) && ~pending && ~failed
        if data.numeric, set(handle,'String',display); data.displayed=display;
        else, data.displayed=char(string(f.value)); end
        field_error(handle,'',false);
    end
    data.actual=f.value;
    data.snapshot=f; data.resolved_key=key;
    set(handle,'UserData',data,'Enable',ternary(f.writable,'on','off'));
end
end

function field_error(handle,message,retry)
data = get(handle,'UserData');
if isfield(data,'key')
    if isempty(message) && isempty(data.error), return; end
    if isempty(data.error)
        data.error=ui_text(get(handle,'Parent'),'',data.error_position);
        set(data.error,'FontSize',8,'ForegroundColor',[.65 .12 .08]);
    end
    if retry && isempty(data.retry)
        position=get(handle,'Position');
        data.retry=uicontrol(get(handle,'Parent'),'Style','pushbutton','String','重试', ...
            'Position',[position(1)+position(3)-36 position(2)-16 36 16], ...
            'Callback',@(~,~) submit_control_edit(ancestor(handle,'figure'),handle,true));
    end
    set(handle,'UserData',data);
end
visible_message = message;
if retry
    pieces = strsplit(message,'|');
    visible_message = [strtrim(pieces{1}) ' 失败'];
end
set(data.error,'String',visible_message,'TooltipString',message);
if ~isempty(data.retry), set(data.retry,'Visible',ternary(retry,'on','off')); end
set(handle,'TooltipString',message);
if isempty(message), color = [1 1 1]; elseif retry, color = [1 .88 .86]; else, color = [1 .97 .85]; end
set(handle,'BackgroundColor',color);
end

function sync_controls(state, force)
sync_extended(state,force);
if ~state.connected
    if force
        for handle = state.home.hardware_edits
            data = get(handle,'UserData');
            data.displayed = '--'; data.actual = NaN;
            set(handle,'String','--','UserData',data);
            set(data.current,'String','--');
            field_error(handle,'',false);
        end
    end
    return;
end
if ~isfield(state.scope_status,'channels'), return; end
for handle = state.home.hardware_edits
    data = get(handle,'UserData');
    if data.index == 0
        if strcmp(data.setting,'TDIV')
            value = state.scope_status.timebase;
        else
            value = state.scope_status.trigger_delay_s;
        end
    else
        idx = find(strcmp({state.scope_status.channels.channel},state.channels{data.index}),1);
        if isempty(idx), continue; end
        channel = state.scope_status.channels(idx);
        if strcmp(data.setting,'VDIV'), value = channel.vertical_scale_v_per_div; else, value = channel.offset_v; end
    end
    pending = ~isempty(state.pending) && any([state.pending.handle] == handle);
    if state.busy && isfield(state.worker_request,'handle')
        pending = pending || state.worker_request.handle == handle;
    end
    untouched = strcmp(get(handle,'String'),data.displayed);
    if strcmp(data.setting,'TDIV') && (force || (untouched && ~pending))
        [data.multiplier,unit] = timebase_unit(value);
        set(data.unit,'String',unit);
    end
    text_value = format_value(value/data.multiplier);
    if force || (untouched && ~pending)
        set(handle,'String',text_value);
        data.displayed = text_value;
        field_error(handle,'',false);
    end
    data.actual = value;
    stamp=field_or(state.scope_status,'readback_at',[]);
    set(data.current,'String',text_value,'TooltipString', ...
        sprintf('回读 %.15g\n%s',value/data.multiplier,char(string(stamp))));
    set(handle,'UserData',data);
end
update_scope_info(state);
end

function update_scope_info(state)
if ~state.connected
    set(state.home.h_scope_info,'String','未连接，当前硬件状态未知');
    return;
end
if ~isfield(state.scope_status,'channels'), return; end
status = state.scope_status;
lines = {status.idn; field_or(state.cfg.instrument.scope,'resource',''); ...
    ['回读时间 ' char(string(field_or(status,'readback_at','未记录')))]; ...
    sprintf('实际采样率  %.6g GSa/s',status.sample_rate_hz/1e9); ''};
for ch = state.channels
    if isfield(state.raw,'channels')
        records = state.raw.channels;
        idx = find(strcmp({records.channel},ch{1}),1);
        if ~isempty(idx)
            rate = records(idx).sample_rate_hz;
            if isfield(state.plot_state,'last_sample_rate_hz') && ...
                    numel(state.plot_state.last_sample_rate_hz)>=idx
                rate = state.plot_state.last_sample_rate_hz(idx);
            end
            lines{end+1} = sprintf('%s 回传 %s GSa/s | %d 点',ch{1}, ...
                format_value(rate/1e9),field_or(records(idx),'original_count',numel(records(idx).samples))); %#ok<AGROW>
        end
    end
end
set(state.home.h_scope_info,'String',lines,'TooltipString', ...
    sprintf('%s\n%s\nBWL: %s / %s',status.idn, ...
    field_or(state.cfg.instrument.scope,'resource',''), ...
    status.channels(str2double(state.channels{1}(2))).bandwidth_text, ...
    status.channels(str2double(state.channels{2}(2))).bandwidth_text));
end

function redraw_current(fig)
state = getappdata(fig,'rx_workbench_state');
if ~isfield(state.raw,'channels'), return; end
if ~isfield(state.raw,'live_spectra')
    state.raw=msiq.plotting.rx_live_analysis(state.raw,field_or(state,'raw_scope_status',state.scope_status));
end
was_locked=state.plot_state.psd_locked;
prior_unit=state.plot_state.psd_unit;
render=state.page=="home";
state.plot_state = msiq.plotting.rx_live_dashboard(state.home.axes, ...
    state.raw,field_or(state,'raw_scope_status',state.scope_status),state.plot_state,state.plot_state,render);
state.plot_dirty=~render;
update_freshness(state);
limits = state.plot_state.psd_ylim;
if all(isfinite(limits))
    handles=[state.home.h_psd_min state.home.h_psd_max];
    for k=1:2
        if strcmp(get(handles(k),'String'),get(handles(k),'UserData'))
            set(handles(k),'String',format_value(limits(k)),'UserData',format_value(limits(k)));
        end
    end
end
if isfield(state.plot_state,'frequency_limit_hz')
    limit=state.plot_state.frequency_limit_hz;
    if isfinite(limit) && limit>0
        message=sprintf('显示范围  0 - %.6g GHz',limit/1e9);
    else
        message='显示范围  无有效频谱';
    end
    set(state.home.h_range,'String',message);
end
sync_psd_units(state);
update_scope_info(state);
setappdata(fig,'rx_workbench_state',state);
if (~was_locked || ~strcmp(prior_unit,state.plot_state.psd_unit)) && state.plot_state.psd_locked
    save_view(fig);
end
end

function sync_psd_units(state)
unit='dBm/Hz';
if strcmp(state.plot_state.psd_unit,'voltage'), unit='dB(V^2/Hz)'; end
for handle=[state.home.h_psd_min state.home.h_psd_max]
    set(getappdata(handle,'rx_display_unit'),'String',unit);
end
end

function [scale,unit] = timebase_unit(value)
if value>=1, scale=1; unit='s/div';
elseif value>=1e-3, scale=1e-3; unit='ms/div';
elseif value>=1e-6, scale=1e-6; unit='us/div';
elseif value>=1e-9, scale=1e-9; unit='ns/div';
else, scale=1e-12; unit='ps/div';
end
end

function yes = requires_positive_setting(setting)
yes = ~ismember(setting, {'OFST','TRDL'});
end

function raw = complete_channels(raw, channels)
records = field_or(raw,'channels',struct([]));
if isempty(records)
    records = struct('channel','','samples',[],'time_axis_s',[],'sample_rate_hz',NaN);
end
template = records(1);
for k = 1:2
    idx = find(strcmp({records.channel},channels{k}),1);
    if isempty(idx)
        record = template;
        record.channel = channels{k};
        record.samples = [];
        record.time_axis_s = [];
        record.sample_rate_hz = NaN;
    else
        record = records(idx);
    end
    ordered(k) = record; %#ok<AGROW>
end
raw.channels = ordered;
end

function update_buttons(fig)
state = getappdata(fig,'rx_workbench_state');
sync_extended(state,false);
if ~state.connected
    for handle = state.home.hardware_edits
        data = get(handle,'UserData');
        set(data.current,'String','--');
    end
    set(state.home.h_scope_info,'String','未连接，当前硬件状态未知');
end
can_start=~state.running && ~state.close_requested && isempty(state.pending_page) && ...
    (~state.busy || (state.asynchronous && ~strcmp(field_or(state.worker_request,'action',''),'release')));
set(state.home.h_play,'Enable',ternary(can_start,'on','off'));
set(state.home.h_pause,'Enable',ternary(state.running,'on','off'));
set([state.home.h_ch1 state.home.h_ch2 state.home.h_single state.home.h_repeat], ...
    'Enable',ternary(~state.busy,'on','off'));
if state.asynchronous
    set([state.home.h_single state.home.h_repeat],'Enable','on');
end
update_freshness(state);
end

function enter_test_page(fig,page)
state = getappdata(fig,'rx_workbench_state');
if state.busy
    state.pending_page = page;
    state.running = false;
    setappdata(fig,'rx_workbench_state',state);
    if state.asynchronous
        set_page(fig,page);
        set_status(fig,'当前读取结束后释放示波器');
    end
    return;
end
if state.asynchronous && state.connected
    state.pending_page=page; state.running=false; state.paused=true;
    setappdata(fig,'rx_workbench_state',state);
    set_page(fig,page);
    submit_worker(fig,struct('action','release'));
    return;
end
state.io.close(state.session);
state.session = [];
state.connected = false;
state.running = false;
state.paused = true;
state.pending_page = '';
setappdata(fig,'rx_workbench_state',state);
set_page(fig,page);
if strcmp(page,'single')
    set(state.pages.h_single_reference,'String',state.reference_bundle);
end
end

function set_page(fig,page)
state = getappdata(fig,'rx_workbench_state');
set(state.home.panel,'Visible',ternary(ismember(string(page),["home","settings"]),'on','off'));
set([state.home.param_panel state.home.plot_panel],'Visible',ternary(strcmp(page,'home'),'on','off'));
set(state.home.observation_panel,'Visible',ternary(strcmp(page,'home'),'on','off'));
set(state.home.trigger_panel,'Visible',ternary(strcmp(page,'home'),'on','off'));
set(state.home.h_settings,'String',ternary(strcmp(page,'settings'),'返回观察','设置'));
for name = {'single','repeat','result'}
    set(state.pages.(name{1}),'Visible',ternary(strcmp(page,name{1}),'on','off'));
end
state.page = string(page);
setappdata(fig,'rx_workbench_state',state);
end

function value = edit_number(handle,label,positive)
value = str2double(get(handle,'String'));
data = get(handle,'UserData');
if isstruct(data) && isfield(data,'multiplier'), value = value*data.multiplier; end
if ~isfinite(value) || (positive && value <= 0)
    error('RX_Workbench:BadParameter','%s 必须是有效数值',label);
end
end

function value = parse_number(response)
text_value = strtrim(char(string(response)));
value = NaN;
if ~isempty(regexpi(text_value,'error|failed|unknown|invalid|support','once')), return; end
tokens = regexp(text_value,'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?:[a-zA-Z/]+)?\s*$','tokens','once');
if ~isempty(tokens), value = str2double(tokens{1}); end
end

function run_tests(fig, repeat_count)
state = getappdata(fig, 'rx_workbench_state');
if isempty(state) || state.busy, return; end
if state.offline_test
    set_status(fig,'离线界面验证，不启动仪器测试');
    return;
end
bundle = state.reference_bundle;
if isempty(bundle), [bundle, ~] = find_reference_bundle(state.cfg,state.channels); end
if isempty(bundle)
    [file, path] = uigetfile({'*tx_reference*.mat', 'TX reference bundle (*.mat)'}, ...
        '请选择 TX reference bundle', state.cfg.project_root);
    if isequal(file, 0)
        set_status(fig, '未选择 TX reference，测试取消');
        return;
    end
    bundle = fullfile(path, file);
    try
        loaded = msiq.load_reference_bundle(bundle);
        assert(isfield(loaded,'bundle') && valid_reference_bundle(loaded.bundle) && ...
            reference_matches(loaded.bundle,state.channels));
    catch
        set_status(fig,'所选文件不是有效的已执行 TX reference bundle');
        return;
    end
end
try
    test_cfg = test_config_from_state(state);
catch exception
    set_status(fig, ['测试参数无效：', exception.message]);
    return;
end
test_options = struct('tx_reference_bundle', bundle, ...
    'cfg_override', test_cfg, 'scope_channels', {state.channels});
state.busy = true;
setappdata(fig,'rx_workbench_state',state);
cleanup = onCleanup(@() finish_tests(fig));
set_status(fig, sprintf('正在执行 %d 次测试，请等待…', repeat_count));
drawnow;
rows = repmat(empty_result_row(), 1, repeat_count);
for k = 1:repeat_count
    rows(k).index = k;
    rows(k).reference = bundle;
    try
        capture = msiq.traditional_rx('capture', [], test_options);
        rows(k).run_dir = field_or(capture, 'run_dir', '');
        if isfield(capture, 'demod_ready') && capture.demod_ready
            rows(k).result = msiq.traditional_rx('demod_capture', capture.run_dir, ...
                test_options);
            rows(k) = fill_metrics(rows(k));
        else
            rows(k).status = 'capture_not_ready';
        end
    catch exception
        rows(k).status = 'failed';
        rows(k).error = exception.message;
    end
    set_status(fig, sprintf('已完成 %d/%d 次', k, repeat_count));
    drawnow;
    state = getappdata(fig,'rx_workbench_state');
    if state.close_requested || strcmp(rows(k).status,'failed')
        rows = rows(1:k);
        break;
    end
end

function cfg = test_config_from_state(state)
if state.offline_test
    cfg = state.cfg;
else
    cfg = msiq.build_config('v2_traditional_wz');
end
cfg.instrument.scope = state.cfg.instrument.scope;
cfg.scope_runtime = struct( ...
    'channels', {state.channels}, ...
    'vertical_scale_v_per_div', [
        edit_number(state.home.h_vdiv1, 'V/div 1', true), ...
        edit_number(state.home.h_vdiv2, 'V/div 2', true)], ...
    'offset_v', [
        edit_number(state.home.h_off1, '偏置 1', false), ...
        edit_number(state.home.h_off2, '偏置 2', false)], ...
    'timebase_s', edit_number(state.home.h_tdiv, 'Time/div', true));
end
state = getappdata(fig, 'rx_workbench_state');
state.results = rows;
state.page = "result";
setappdata(fig, 'rx_workbench_state', state);
set_page(fig, 'result');
show_results(fig, rows);
clear cleanup;
end

function finish_tests(fig)
if ~isgraphics(fig), return; end
state = getappdata(fig,'rx_workbench_state');
state.busy = false;
setappdata(fig,'rx_workbench_state',state);
if state.close_requested, close(fig); end
end

function row = empty_result_row()
row = struct('index', 0, 'status', 'pending', 'run_dir', '', ...
    'reference', '', 'result', struct(), 'error', '', 'ber', NaN, ...
    'bler', NaN, 'mer_db', NaN, 'sro_ppm', NaN, 'dashboard_path', '', ...
    'observations',struct([]));
end

function row = fill_metrics(row)
result = row.result;
row.status = char(string(field_or(result, 'status', 'unknown')));
row.dashboard_path = field_or(result, 'dashboard_path', '');
pairs = field_or(result, 'pairs', struct([]));
values = struct('channel',{},'ber', {}, 'bler', {}, 'mer_db', {}, 'sro_ppm', {});
for k = 1:numel(pairs)
    decoded = field_or(pairs(k), 'decoded', struct());
    streams = field_or(decoded, 'primary_streams', struct([]));
    for s = 1:numel(streams)
        sync = field_or(decoded, 'synchronization', struct());
        pair_name = char(string(field_or(pairs(k),'name',sprintf('Pair%d',k))));
        values(end+1) = struct('channel',sprintf('%s_Channel%d',pair_name,s), ...
            'ber', scalar_or(field_or(streams(s), 'post_fec_ber', NaN), NaN), ...
            'bler', scalar_or(field_or(streams(s), 'bler', NaN), NaN), ...
            'mer_db', scalar_or(field_or(streams(s), 'mer_db', NaN), NaN), ...
            'sro_ppm', scalar_or(field_or(sync, 'sro_ppm', NaN), NaN)); %#ok<AGROW>
    end
end
row.observations = values;
end

function show_results(fig, rows)
state = getappdata(fig, 'rx_workbench_state');
data = cell(0, 8);
for k = 1:numel(rows)
    observations = rows(k).observations;
    if isempty(observations)
        data(end+1,:) = {rows(k).index,'',rows(k).status, ...
            '--','--','--','--',rows(k).run_dir}; %#ok<AGROW>
    end
    for j = 1:numel(observations)
        value = observations(j);
        data(end+1,:) = {rows(k).index,value.channel,rows(k).status, ...
            metric_text(value.ber,'BER'),metric_text(value.bler,'BLER'), ...
            metric_text(value.mer_db,'MER'),metric_text(value.sro_ppm,'SRO'), ...
            rows(k).run_dir}; %#ok<AGROW>
    end
end
set(state.pages.h_result_table, 'Data', data);
last = find(~cellfun(@isempty, {rows.dashboard_path}), 1, 'last');
cla(state.pages.h_result_axes, 'reset');
if ~isempty(last) && isfile(rows(last).dashboard_path)
    image_data = imread(rows(last).dashboard_path);
    image(state.pages.h_result_axes, image_data);
    axis(state.pages.h_result_axes, 'image');
    axis(state.pages.h_result_axes, 'off');
else
    axis(state.pages.h_result_axes, 'off');
    text(state.pages.h_result_axes, 0.5, 0.5, '没有可显示的 RX 总览图', ...
        'HorizontalAlignment', 'center');
end
set(state.pages.h_result_title, 'String', sprintf('测试结果 | %d 次', numel(rows)));
setappdata(fig, 'rx_workbench_state', state);
end

function [path, message] = find_reference_bundle(cfg,channels)
if nargin < 2, channels = {}; end
path = '';
roots = {fullfile(cfg.project_root,'measurement'), ...
    fullfile(cfg.project_root,'simulation'), ...
    fullfile(cfg.project_root,'results'), ...
    fullfile(cfg.project_root,'tx_records')};
if isfield(cfg,'results_root') && ~strcmpi(cfg.results_root,cfg.project_root)
    roots{end+1} = cfg.results_root;
end
roots = unique(roots,'stable');
files = [];
for root_index = 1:numel(roots)
    matches = dir(fullfile(roots{root_index},'**','*tx_reference*.mat'));
    files = [files; matches(:)]; %#ok<AGROW>
end
if isempty(files)
    message = 'TX reference：未找到，请开始测试时手动选择。';
    return;
end
[~, order] = sort([files.datenum], 'descend');
for k = order
    candidate = fullfile(files(k).folder, files(k).name);
    try
        loaded = msiq.load_reference_bundle(candidate);
        bundle = loaded.bundle;
        if valid_reference_bundle(bundle) && ...
                (isempty(channels) || reference_matches(bundle,channels))
            path = candidate;
            message = ['TX reference：', candidate];
            return;
        end
    catch
    end
end
message = 'TX reference：未找到成功 bundle，请开始测试时手动选择。';
end

function yes = reference_matches(bundle,channels)
route = field_or(bundle,'route',struct());
saved = field_or(route,'scope_channels',{});
yes = isequal(reshape(upper(string(saved)),1,[]),reshape(upper(string(channels)),1,[]));
end

function valid = valid_reference_bundle(bundle)
valid = isstruct(bundle) && isscalar(bundle);
if ~valid, return; end
required = {'route', 'desired', 'tx_ref', 'execution'};
for k = 1:numel(required)
    if ~isfield(bundle, required{k})
        valid = false;
        return;
    end
end
execution = bundle.execution;
valid = isstruct(execution) && strcmpi( ...
    char(string(field_or(execution, 'status', ''))), 'applied');
if ~valid, return; end
policy = char(string(field_or(bundle, 'reference_payload_policy', '')));
frame = field_or(bundle.tx_ref, 'frame', struct());
valid = strcmpi(policy, 'metrics_only') && isstruct(frame) && ...
    strcmpi(char(string(field_or(frame, 'reference_payload_policy', ''))), ...
    'metrics_only');
end

function text_value = metric_text(value, name)
if isempty(value) || ~isscalar(value) || ~isfinite(double(value))
    text_value = '--';
else
    text_value = Result_Display_Value(double(value),name,'');
end
end

function close_scope(session)
if isempty(session), return; end
% capture_scope_raw owns STOP / TRMD AUTO cleanup. Closing a query session
% must not write acquisition settings.
try msiq.instruments.close_session(session); catch, end
end

function set_status(fig, text_value)
if ~ishghandle(fig), return; end
state = getappdata(fig, 'rx_workbench_state');
if ~isempty(state) && isfield(state, 'home') && isgraphics(state.home.h_status)
    set(state.home.h_status, 'String', char(string(text_value)), 'TooltipString', char(string(text_value)));
    if ~ismember(state.page,["home","settings"])
        handle = state.pages.(['status_' char(state.page)]);
        set(handle,'String',char(string(text_value)),'TooltipString',char(string(text_value)));
    end
end
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end

function value = scalar_or(value, fallback)
if isempty(value) || ~isscalar(value) || ~isfinite(double(value))
    value = fallback;
else
    value = double(value);
end
end

function text_value = format_value(value)
if isempty(value) || ~isscalar(value) || ~isfinite(double(value))
    text_value = '--';
else
    text_value = sprintf('%.6g', double(value));
    if numel(text_value)>9, text_value = sprintf('%.2e',double(value)); end
end
end

function value = ternary(condition, when_true, when_false)
if condition, value = when_true; else, value = when_false; end
end

function set_chinese_font()
try
    font_name = 'Microsoft YaHei UI';
    set(0, 'DefaultAxesFontName', font_name, 'DefaultTextFontName', font_name, ...
        'DefaultUicontrolFontName', font_name);
catch
end
end
