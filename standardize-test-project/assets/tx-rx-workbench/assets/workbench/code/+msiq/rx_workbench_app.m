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
setappdata(fig,'rx_source_states',struct());
setappdata(fig,'rx_source_options',source_options(options));
setappdata(fig,'rx_source_bind',@bind_home);
update_buttons(fig);
set(fig, 'CloseRequestFcn', @on_close, 'SizeChangedFcn', @on_resize, ...
    'WindowScrollWheelFcn', @on_scroll);
bind_home(state);
setappdata(fig, 'rx_workbench_tick', @on_tick);
setappdata(fig, 'rx_workbench_startup', @on_startup);
layout_home(state.home, fig);
sync_display_controls(state);
msiq.plotting.rx_live_dashboard(state.home.axes, struct(), struct(), struct(), struct());
sync_measurement_controls(state);
if options.visible, set(fig,'Visible','on'); end
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

    function bind_home(state)
        set(state.home.h_play, 'Callback', @on_play);
        set(state.home.h_pause, 'Callback', @on_pause);
        set(state.home.h_single, 'Callback', @(~,~) run_tests(fig, 1));
        set(state.home.h_repeat, 'Callback', @(~,~) run_tests(fig, str2double(get(state.home.h_count,'String'))));
        set(state.home.h_settings,'Callback',@(~,~) scroll_scope_controls(fig));
        set(state.home.h_stop,'Callback',@(~,~) stop_daily_task(fig));
        set(state.home.h_balance,'Callback',@(~,~) run_tests(fig,1,true));
        set(state.home.h_demod,'Callback',@(~,~) daily_options_changed(fig));
        set(state.home.h_history,'Callback',@(~,~) daily_select_record(fig));
        set([state.home.h_ch1 state.home.h_ch2], 'Callback', @on_channel);
        for edit_handle = state.home.hardware_edits
            msiq.rx_input_state('bind',edit_handle,@() on_hardware_edit(edit_handle,[]));
        end
        for edit_handle = state.home.extended_edits
            data=get(edit_handle,'UserData');
            if data.numeric
                msiq.rx_input_state('bind',edit_handle,@() submit_control_edit(fig,edit_handle));
            else
                set(edit_handle,'Callback',@(~,~) submit_control_edit(fig,edit_handle));
            end
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
        set(state.home.h_simulation,'Callback',@(~,~) request_source_switch(fig,'simulation'), ...
            'ButtonDownFcn',@(~,~) request_source_switch(fig,'simulation'));
        set(state.home.h_measurement,'Callback',@(~,~) request_source_switch(fig,'measurement'), ...
            'ButtonDownFcn',@(~,~) request_source_switch(fig,'measurement'));
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
        if ~isfield(current,'scope_restore_pending')
            set_status(fig,'此窗口来自旧版本，请关闭后重新打开 RX 工作台');
            return;
        end
        if ~isempty(current.source_switch), return; end
        if ~isempty(current.source_release_error), set_status(fig,['连接释放状态未确认 | ' current.source_release_error]); return; end
        if ~ismember(current.page,["home","settings"]) || current.running || ...
                current.close_requested || ~isempty(current.pending_page), return; end
        if ~isempty(current.scope_restore_pending),return;end
        if current.busy && (~current.asynchronous || ...
                strcmp(field_or(current.worker_request,'action',''),'release')), return; end
        current.capture_rejections = 0;
        setappdata(fig,'rx_workbench_state',current);
        if current.asynchronous
            current.running=true; current.paused=false;
            setappdata(fig,'rx_workbench_state',current);
            if ~current.connected
                if current.native_simulation && isempty(fieldnames(current.simulation_source)), prepare_simulation(fig);
                else, connect_scope(fig); end
            end
            update_buttons(fig);
            return;
        end
        if ~current.connected
            connect_scope(fig);
            if ~isgraphics(fig), return; end
            current = get_state();
        end
        if ~current.connected, return; end
        if isfield(current.scope_restore_report,'ok') && ~current.scope_restore_report.ok,return;end
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
        if src == h.h_center || is_band
            lo=str2double(get(h.h_center,'String'))*1e9;
            hi=str2double(get(h.h_bandwidth,'String'))*1e9;
            if ~all(isfinite([lo hi])) || lo<0 || hi<=lo
                set(src,'BackgroundColor',[1 .88 .86],'TooltipString','功率统计频段上限必须大于下限');
                set_status(fig,'功率统计频段无效，保留原图'); return;
            end
            [current.plot_state.center_hz,current.plot_state.bandwidth_hz]=msiq.rx_observation_band('to_legacy',lo,hi);
            for field=[h.h_center h.h_bandwidth]
                text_value=format_value(str2double(get(field,'String')));
                set(field,'String',text_value,'UserData',text_value,'BackgroundColor',[1 1 1], ...
                    'TooltipString','两路共用功率统计频段；只影响观察功率和频谱阴影');
            end
        end
        set(src, 'BackgroundColor', [1 1 1], 'TooltipString', '', ...
            'String',format_value(value),'UserData',format_value(value));
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
        if ~isempty(current.scope_restore_pending),set(src,'Value',str2double(current.channels{index}(2)));return;end
        was_enabled=current.second_enabled;
        names = get(src, 'String');
        selected = names{get(src, 'Value')};
        if index==2 && any(strcmp(current.measurement_position,{'tx_if','thz_if'}))
            set(src,'Value',5); return;
        end
        [blocked,reason]=msiq.rx_input_state('blocked',[current.home.hardware_edits current.home.extended_edits]);
        if blocked
            set(src,'Value',ternary(index==2 && ~current.second_enabled,5,str2double(current.channels{index}(2))));
            set_status(fig,['切换通道前：' reason]); return;
        end
        if strcmp(selected,current.channels{index}) && (index==1 || current.second_enabled)
            current.channel_selection_explicit=true; setappdata(fig,'rx_workbench_state',current); save_view(fig); return;
        end
        if index==2 && strcmp(selected,'未选择')
            if task_active(current) || current.busy, set(src,'Value',str2double(current.channels{2}(2))); return; end
            if ~current.second_enabled, return; end
            current.second_enabled=false; current.channel_selection_explicit=true;
            current=invalidate_measurement(current,'通道已更新，等待新采集');
            setappdata(fig,'rx_workbench_state',current); save_view(fig);
            set(current.home.h_wave_title(2),'String','未选择'); set(current.home.h_spectrum_title(2),'String','未选择'); update_buttons(fig); return;
        end
        if index==2, current.second_enabled=true; end
        other = current.channels{3-index};
        if task_active(current) || current.busy || ~isempty(current.pending) || ~isempty(current.control_pending) || (current.second_enabled && strcmp(selected, other))
            set(src, 'Value', ternary(index==2 && ~was_enabled,5,str2double(current.channels{index}(2))));
            if strcmp(selected,other)
                set([current.home.h_ch1 current.home.h_ch2],'BackgroundColor',[1 .83 .81],'TooltipString','两路不能选择同一通道');
                set(current.home.h_channel_error,'String','通道重复','TooltipString','两路不能选择同一通道，请改选 C1–C4 中的另一通道');
            end
            set_status(fig, ternary(strcmp(selected, other), ...
                '两路不能选择同一通道', '操作尚未完成，稍后切换通道'));
            return;
        end
        set([current.home.h_ch1 current.home.h_ch2],'BackgroundColor',[1 1 1],'TooltipString','');
        set(current.home.h_channel_error,'String','');
        save_view(fig);
        current = get_state();
        if index==2, current.second_enabled=true; end
        current.channels{index} = selected;
        current.channel_selection_explicit=true;
        current.capture_rejections = 0;
        current.raw = struct();
        current.raw_stale = false;
        current.first_capture_complete = false;
        current = restore_view(current);
        current=invalidate_measurement(current,'通道已更新，等待新采集');
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
        if current.close_finalizing, return; end
        if current.close_requested && ~current.busy
            on_close([], []);
            return;
        end
        if current.startup_pending
            on_startup([], []);
            return;
        end
        if ~isempty(current.source_switch)
            if current.close_requested
                current.source_switch=''; setappdata(fig,'rx_workbench_state',current); on_close([],[]);
            else, tick_source_switch(fig); end
            return;
        end
        tick_reference(fig);
        if ~isgraphics(fig), return; end
        tick_daily_task(fig);
        if ~isgraphics(fig), return; end
        update_task_result(fig,false);
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
            chosen=selected_channels(current); requested = chosen(ismember(chosen, {active(strcmp({active.trace_state},'ON')).channel}));
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
            raw = complete_channels(raw, selected_channels(current));
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
        if ~ismember(current.page,["home","settings"]), return; end
        pointer = get(fig,'CurrentPoint');
        if isstruct(event) && isfield(event,'PointerPosition'), pointer = event.PointerPosition; end
        box = get(current.home.settings_panel,'Position');
        if pointer(1) < box(1) || pointer(1) > box(1)+box(3), return; end
        h = current.home.scroll;
        set(h,'Value', min(get(h,'Max'), max(0, get(h,'Value')-event.VerticalScrollCount*40)));
        layout_scroll_content(current.home, fig);
    end

    function on_close(~, ~)
        close_capture_settings(fig);
        if ~isgraphics(fig), return; end
        current = get_state();
        if current.close_finalizing, return; end
        if scope_controls_locked(current), stop_daily_task(fig); current=get_state(); end
        current.close_requested = true;
        current.running = false;
        if current.asynchronous && (~isempty(current.worker) || ~isempty(current.reference_worker))
            if isempty(current.timer) || ~isvalid(current.timer)
                current.timer=timer('ExecutionMode','fixedSpacing','BusyMode','drop', ...
                    'Period',.1,'TimerFcn',@on_tick);
            end
            if strcmp(current.timer.Running,'off'), start(current.timer); end
        end
        setappdata(fig,'rx_workbench_state',current);
        if current.busy
            set_status(fig,'正在结束当前读取');
            return;
        end
        workers={current.worker,current.reference_worker};
        exited=true;
        for k=1:numel(workers)
            if isempty(workers{k}), continue; end
            try
                workers{k}.close();
            catch exception
                set_status(fig,['后台关闭待重试 | ' exception.message]);
                return;
            end
            exited=exited && workers{k}.process.HasExited;
        end
        if ~exited
            set_status(fig,'正在释放后台连接');
            return;
        end
        % stop()/WaitForExit may dispatch queued callbacks. Detach the timer
        % and guard finalization before yielding, so close cannot re-enter.
        current.close_finalizing=true;
        closing_timer=current.timer;
        current.timer=[];
        setappdata(fig,'rx_workbench_state',current);
        for k=1:numel(workers)
            if ~isempty(workers{k}), workers{k}.process.WaitForExit(); end
        end
        if ~isempty(closing_timer) && isvalid(closing_timer)
            stop(closing_timer);
            if isvalid(closing_timer), delete(closing_timer); end
        end
        current.io.close(current.session);
        result_window=getappdata(fig,'rx_result_window');
        if ~isempty(result_window) && isgraphics(result_window), delete(result_window); end
        uiresume(fig);
        delete(fig);
    end
end

function options = app_options(options)
auto_explicit=isfield(options,'auto_connect');
source_explicit=isfield(options,'source_mode') && ~isempty(options.source_mode);
offline_explicit=isfield(options,'offline_test');
offline_value=field_or(options,'offline_test',false);
defaults = struct('visible', true, 'maximize', true, 'position', [20 40 1280 720], ...
    'auto_connect', false, 'synchronous_startup', false, 'use_timer', true, ...
    'refresh_period_s', 0.1, 'reference_bundle', '', 'find_reference', true, 'io', struct(), ...
    'asynchronous',[],'worker_factory','','worker_options',struct(),'preferences_path',[], ...
    'config',[],'if_profile',struct(),'board_config',struct(),'task_timeout_s',900, ...
    'capture_settings_path',[],'reference_link_store_path','','scope_presets_path',[],'scope_restore_timeout_s',180, ...
    'source_mode','','simulation',struct(),'measurement_options',struct(),'results_root','');
names = fieldnames(defaults);
for k = 1:numel(names)
    if ~isfield(options,names{k}), options.(names{k}) = defaults.(names{k}); end
end
options.injected_io=~isempty(fieldnames(options.io));
injected=options.injected_io || ~isempty(options.worker_factory);
if ~source_explicit
    options.source_mode=ternary(offline_explicit && ~offline_value,'measurement','simulation');
end
options.source_mode=lower(char(string(options.source_mode)));
assert(ismember(options.source_mode,{'simulation','measurement'}),'RX_Workbench:SourceMode','来源只能选择模拟或实测');
simulation=strcmp(options.source_mode,'simulation');
assert(~(offline_explicit && logical(offline_value)~=simulation),'RX_Workbench:SourceConflict','来源选择与 offline_test 冲突');
assert(simulation || ~injected,'RX_Workbench:SourceConflict','实测来源不能使用模拟 I/O 或 mock worker');
options.offline_test=simulation;
options.native_simulation=simulation && ~injected;
if isempty(options.asynchronous), options.asynchronous=~options.injected_io; end
if options.native_simulation
    assert(options.asynchronous,'RX_Workbench:SimulationWorker','模拟生成和采集需要后台进程');
    options.find_reference=false;
end
if options.asynchronous && options.injected_io && isempty(options.worker_factory)
    error('RX_Workbench:TestIO','Asynchronous test I/O requires worker_factory; GUI function handles cannot own the worker session.');
end
default_io=struct('open',@(spec)msiq.instruments.open_session('scope',spec,'raw'), ...
    'query',@msiq.instruments.query_scpi,'write',@msiq.instruments.write_scpi, ...
    'capture',@(s,c)msiq.instruments.capture_scope_raw(s,c,struct('mode','observation')),'close',@close_scope);
if ~options.injected_io, options.io=default_io;
elseif ~all(isfield(options.io,fieldnames(default_io)))
    error('RX_Workbench:TestIO','I/O injection must provide open/query/write/capture/close together.');
end
if injected && options.synchronous_startup && ~auto_explicit, options.auto_connect=true; end

end

function state = initial_state(cfg, fig, options)
channels = {'C1','C2'};
if options.native_simulation, channels={'C3','C4'}; end
if isfield(cfg.instrument.scope,'channels')
    candidates = unique(cellstr(upper(string(cfg.instrument.scope.channels))), 'stable');
    if numel(candidates) >= 2, channels = reshape(candidates(1:2),1,2); end
end
preferences_path = options.preferences_path;
if isnumeric(preferences_path) && isempty(preferences_path)
    preferences_path = '';
    if ~options.offline_test
        preferences_path = fullfile(cfg.project_root,'rx_records','rx_workbench_preferences.mat');
    elseif options.native_simulation
        preferences_path=fullfile(cfg.project_root,'rx_records','rx_workbench_simulation_preferences.mat');
    end
end
preferences = msiq.rx_view_preferences('load',preferences_path);
if ~isempty(preferences.channels), channels = preferences.channels; end
state = struct('figure',fig,'cfg',cfg,'session',[],'io',options.io,'connected',false, ...
    'asynchronous',options.asynchronous,'worker',[],'worker_request',struct(), ...
    'worker_factory',options.worker_factory,'worker_options',options.worker_options, ...
    'channels',{channels},'scope_status',struct(),'raw',struct(),'timer',[], ...
    'busy',false,'running',false,'paused',true,'startup_pending',true,'capture_rejections',0, ...
    'offline_test',options.offline_test,'source_mode',options.source_mode, ...
    'native_simulation',options.native_simulation,'simulation',options.simulation, ...
    'simulation_source',struct(),'simulation_preparing',false,'source_switch','', ...
    'source_release_error','','source_epoch',0,'options',options, ...
    'preferences_path',preferences_path,'preferences',preferences,'preference_error','', ...
    'reference_path',options.reference_bundle,'find_reference',options.find_reference, ...
    'reference_pending',false,'first_capture_complete',false,'stale_reason','', ...
    'reference_worker',[],'reference_busy',false,'reference_request',struct(), ...
    'pending',struct('handle',{},'command',{},'value',{},'revision',{}), ...
    'control_pending',struct('handle',{},'key',{},'value',{},'revision',{}), ...
    'settings_refresh_pending',false,'settings_last_read',[], ...
    'revision',0,'pending_page','','close_requested',false,'close_finalizing',false, ...
    'page',"home",'plot_dirty',false,'plot_state',struct('center_hz',0,'bandwidth_hz', ...
    cfg.waveform.symbol_rate_hz*(1+cfg.waveform.rolloff), ...
    'psd_ylim',[-160 -80],'psd_locked',false), ...
    'band_source','项目默认统计频段','reference_bundle','','results',struct([]));
state.reference_factory=state.worker_factory;
if options.native_simulation, state.reference_factory=''; state.worker_factory='msiq.rx_simulation_io'; end
state.if_profile=msiq.if_workbench_config(struct('mode',ternary(options.offline_test,'mock','live')));
if options.native_simulation
    [~,state.if_profile,state.simulation]=msiq.rx_simulation_config(options.simulation);
end
assert(options.offline_test || (~strcmp(field_or(options.if_profile,'mode','live'),'mock') && ...
    ~field_or(options.if_profile,'mock_fixture_applied',false) && ~strcmp(field_or(options.if_profile,'source_mode',''),'simulation')), ...
    'RX_Workbench:MockProfile','实机界面不能加载模拟批准参数');
state.if_profile=msiq.if_workbench_config(merge_struct(state.if_profile,options.if_profile));
state.if_profile.mode=ternary(options.offline_test,'mock','live');
settings_path=options.capture_settings_path;
if isempty(settings_path) && ~ischar(settings_path) && ~isempty(preferences_path) && ~(options.offline_test && ~options.native_simulation)
    settings_path=msiq.rx_capture_settings('path',state.if_profile,cfg.project_root, ...
        struct('source_mode',ternary(options.native_simulation,'simulation','live')));
end
state.capture_settings_path=settings_path;
if ~isempty(settings_path)
    try
        state.if_profile=msiq.rx_capture_settings('load',state.if_profile,settings_path, ...
            struct('source_mode',ternary(options.offline_test,'simulation','live')));
    catch exception, state.preference_error=['采集设置未恢复：' exception.message]; end
end
state.if_profile.scope.range_strategy='computed';
state.reference_manual=~isempty(options.reference_bundle);
state.reference_info=struct(); state.reference_link_key=''; state.reference_checked_at=-Inf;
state.observation_cache=struct();
state.scope_preset=[];state.scope_preset_error='';state.scope_restore_pending=[];
state.scope_restore_resume=false;state.scope_restore_report=struct();state.scope_restore_cancelled=false;state.scope_restore_id=0;state.scope_auto_restored=false;
state.scope_presets_options=struct();
if ischar(options.scope_presets_path),state.scope_presets_options.store_path=options.scope_presets_path;
elseif isempty(preferences_path),state.scope_presets_options.store_path='';end
state.board_config=options.board_config; if isempty(fieldnames(state.board_config)), state.board_config=state.if_profile.board; end
if options.native_simulation
    state.board_config.initial_state_confirmed=false;
    state.board_config.mapping=state.if_profile.board.mapping;
end
state.task=[]; state.task_sequence=0; state.task_waiting=false; state.board_pending={};
state.second_enabled=preferences.second_enabled; state.resume_observation=false;
state.measurement_position=preferences.measurement_position; state.measurement_subband=preferences.measurement_subband;
state.measurement_routes=preferences.measurement_routes; state.measurement_revision=0;
state.measurement_second_enabled=preferences.measurement_second_enabled;
state.channel_selection_explicit=preferences.channel_selection_explicit;
state.real_if_reference=struct(); state.real_if_reference_path='';
if ~isempty(state.measurement_position) && isfield(state.measurement_routes,state.measurement_position), state.channels=state.measurement_routes.(state.measurement_position); end
if isfield(state.measurement_second_enabled,state.measurement_position), state.second_enabled=state.measurement_second_enabled.(state.measurement_position); end
if any(strcmp(state.measurement_position,{'tx_if','thz_if'})), state.second_enabled=false; end
state = restore_view(state);
end

function apply_reference_band(fig,channels,info)
state = getappdata(fig,'rx_workbench_state');
if ~(isequal(channels,state.channels) || isequal(channels,selected_channels(state))), return; end
old_identity=field_or(state.reference_info,'reference_identity','');
new_identity=field_or(info,'reference_identity','');
if ~isempty(old_identity) && ~strcmp(old_identity,new_identity)
    state=invalidate_measurement(state,'发送参考已变化，等待新波形');
end
state.reference_info=info; state.reference_bundle=info.path;
state.real_if_reference=field_or(info,'real_if_reference',struct()); state.real_if_reference_path=info.path;
if ~state.manual_band && ~isempty(info.path)
    state.plot_state.bandwidth_hz=info.bandwidth_hz; state.plot_state.center_hz=info.center_hz;
    state.band_source='发送参考统计频段';
elseif isempty(info.path) && ~isempty(info.error)
    state.band_source='未关联发送参考';
end
state.reference_pending=false;
setappdata(fig,'rx_workbench_state',state); refresh_reference_label(state);
sync_display_controls(state,false);
set(state.home.h_band_source,'TooltipString',strtrim([info.path ' ' info.error]));
redraw_current(fig); update_buttons(fig);
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
state.reference_pending = state.find_reference || ~isempty(state.reference_path);
end

function sync_display_controls(state,force)
if nargin<2, force=true; end
handles = [state.home.h_center state.home.h_bandwidth state.home.h_psd_min state.home.h_psd_max];
[lo,hi]=msiq.rx_observation_band('from_legacy',state.plot_state.center_hz,state.plot_state.bandwidth_hz);
values = [lo/1e9 hi/1e9 state.plot_state.psd_ylim];
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
sync_measurement_controls(state);
end

function save_view(fig)
state = getappdata(fig,'rx_workbench_state');
record = state.preferences;
record.channels = state.channels;
record.measurement_position=state.measurement_position; record.measurement_subband=state.measurement_subband;
record.measurement_routes=state.measurement_routes;
record.measurement_second_enabled=state.measurement_second_enabled;
record.second_enabled=state.second_enabled; record.channel_selection_explicit=state.channel_selection_explicit;
if ~isempty(state.measurement_position), record.measurement_routes.(state.measurement_position)=state.channels; end
if ~isempty(state.measurement_position), record.measurement_second_enabled.(state.measurement_position)=state.second_enabled; end
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
    'DefaultUicontrolFontSize',13,'DefaultAxesFontName','Microsoft YaHei UI', ...
    'DefaultTextFontName','Microsoft YaHei UI');
end

function home = build_home(fig, state)
bg=[.96 .97 .98];
home.panel=uipanel(fig,'Units','pixels','BorderType','none','BackgroundColor',bg);
for entry={'pause','play','single','repeat','settings','stop'}
    labels=struct('pause','暂停观察','play','开始观察','single','单次测试','repeat','重复测试','settings','示波器设置','stop','停止任务');
    home.(['h_' entry{1}])=uicontrol(home.panel,'Style','pushbutton','String',labels.(entry{1}),'FontSize',13);
end
set(home.h_stop,'ForegroundColor',[.7 .1 .1],'FontWeight','bold');
home.h_simulation=uicontrol(home.panel,'Style','text','Enable','inactive','String','模拟','FontSize',13,'Value',strcmp(state.source_mode,'simulation'));
home.h_measurement=uicontrol(home.panel,'Style','text','Enable','inactive','String','实测','FontSize',13,'Value',strcmp(state.source_mode,'measurement'));
home.h_status=ui_text(home.panel,'待操作',[0 0 1 1]);
home.h_freshness=ui_text(home.panel,'尚无采集',[0 0 1 1]);
home.settings_panel=uipanel(home.panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
home.content=uipanel(home.settings_panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
home.scroll=uicontrol(home.settings_panel,'Style','slider','Min',0,'Max',1,'Value',1);
home.content_height=3010; p=home.content;
home.position_group=uibuttongroup(p,'Units','pixels','Position',[4 2810 400 195], ...
    'Title','测量位置','FontSize',16,'FontWeight','bold','BackgroundColor',bg,'Tag','rx_measurement_position');
ids={'awg_direct','tx_if','thz_if','rx_if','rx_if_thz'};
labels={'AWG 直连','中频上变频输出','太赫兹下变频输出','中频下变频输出（未经过太赫兹）','中频下变频输出（已经过太赫兹）'};
home.position_buttons=gobjects(1,5);
for n=1:5
    home.position_buttons(n)=uicontrol(home.position_group,'Style','radiobutton','String',labels{n}, ...
        'Tag',ids{n},'FontSize',13,'BackgroundColor',bg,'Position',[8 141-(n-1)*33 380 30]);
end
set(home.position_group,'SelectedObject',[]);
idx=find(strcmp(ids,state.measurement_position),1);
if ~isempty(idx), set(home.position_group,'SelectedObject',home.position_buttons(idx)); end
set(home.position_group,'SelectionChangedFcn',@(~,event)measurement_changed(fig,get(event.NewValue,'Tag'),[]));
home.subband_group=uibuttongroup(p,'Units','pixels','Position',[4 2754 400 54], ...
    'BorderType','none','BackgroundColor',bg,'Tag','rx_measurement_subband');
ui_text(home.subband_group,'目标子带',[8 15 90 28]); home.subband_buttons=gobjects(1,6);
for n=1:6
    home.subband_buttons(n)=uicontrol(home.subband_group,'Style','radiobutton','String',num2str(n), ...
        'UserData',n,'FontSize',13,'BackgroundColor',bg,'Position',[100+(n-1)*48 16 47 28]);
end
set(home.subband_group,'SelectedObject',home.subband_buttons(state.measurement_subband));
set(home.subband_group,'SelectionChangedFcn',@(~,event)measurement_changed(fig,'',get(event.NewValue,'UserData')));
home.h_if_center=ui_text(p,'',[12 2725 380 27]); set(home.h_if_center,'FontSize',12);

home.h_profile=uicontrol(p,'Style','pushbutton','String','采集设置','FontSize',13,'Position',[245 2654 145 30], ...
    'Callback',@(~,~) load_daily_profile(fig));
home.h_reference=uicontrol(p,'Style','pushbutton','String','发送参考','FontSize',13,'Position',[235 2689 75 30], ...
    'Callback',@(~,~) choose_daily_reference(fig));
home.h_reference_auto=uicontrol(p,'Style','pushbutton','String','恢复自动','FontSize',13,'Position',[315 2689 75 30], ...
    'TooltipString','恢复自动关联本机最近成功发送记录','Callback',@(~,~)restore_auto_reference(fig));
home.h_demod=uicontrol(p,'Style','checkbox','String','采集后解调','Value',1,'FontSize',13,'Position',[12 2689 180 32]);
home.h_ldpc=uicontrol(p,'Style','checkbox','String','启用 LDPC 译码','Value',0,'FontSize',13,'Position',[12 2654 230 32]);
home.h_count_label=ui_text(home.panel,'次数',[0 0 1 1]);
home.h_count=uicontrol(home.panel,'Style','edit','String','3','FontSize',13,'TooltipString','重复测试次数：1–100；单次测试不使用此值');
home.h_view_result=uicontrol(p,'Style','pushbutton','String','详细结果','FontSize',13,'Position',[12 2617 190 34], ...
    'Callback',@(~,~)update_task_result(fig,true));
home.h_balance=uicontrol(p,'Style','pushbutton','String','自动配平','FontSize',13,'Position',[215 2617 155 34]);
home.h_gate=ui_text(p,'先连接示波器，再进行测试',[12 2590 380 24]); set(home.h_gate,'FontSize',12,'ForegroundColor',[.65 .25 .1]);
home.h_reference_info=ui_text(p,'发送参考：尚未关联',[12 2541 380 48]); set(home.h_reference_info,'FontSize',12);
home.h_range_hint=ui_text(p,'量程：等待新波形',[12 2515 380 24]); set(home.h_range_hint,'FontSize',12);
home.h_metrics=ui_text(p,'尚未取得解调指标',[12 2463 380 50]); set(home.h_metrics,'FontSize',12);
home.h_history=uicontrol(p,'Style','popupmenu','String',{'暂无记录'},'Position',[12 2426 380 32],'FontSize',12);
boardOptions=struct('config',state.board_config,'offline_test',state.offline_test,'persist',~state.offline_test || state.native_simulation, ...
    'source_mode',ternary(strcmp(state.source_mode,'simulation'),'mock','live'),'external_selection',true);
if isfield(state,'board_draft'), boardOptions.initial_settings=state.board_draft; end
if state.asynchronous, boardOptions.dispatch=@(action,payload,completion)queue_board(fig,action,payload,completion); end
boardOptions.onRejected=@(event)record_board_rejection(fig,field_or(event,'action','board_control'),field_or(event,'reason','板卡操作已被禁用'));
home.board=msiq.if_board_panel(p,'rx',boardOptions);
home.board.setSelection(state.measurement_subband);
selection_callback=get(home.board.controls.selection,'Callback');
set(home.board.controls.selection,'Callback',@(src,event) board_selection_changed(fig,selection_callback,src,event));
home.board.layout([4 1050 400 650]);
home.hardware_edits=gobjects(1,6); home.extended_edits=gobjects(1,0); home.groups=gobjects(1,3);
home.param_panel=uipanel(p,'Units','pixels','Title','示波器设置','FontSize',16,'FontWeight','bold', ...
    'Position',[4 1950 400 470],'BackgroundColor',bg);
home.h_channel_error=ui_text(home.param_panel,'',[288 415 92 26]);
set(home.h_channel_error,'FontSize',11,'ForegroundColor',[.8 .08 .05]);
for k=1:3
    group=uipanel(home.param_panel,'Units','pixels','BorderType','none','Position',[6 310-(k-1)*148 385 140],'BackgroundColor',bg); home.groups(k)=group;
    if k<=2
        names={'C1','C2','C3','C4'}; if k==2, names{5}='未选择'; end
        home.(['h_ch' num2str(k)])=uicontrol(group,'Style','popupmenu','String',names,'Value',str2double(state.channels{k}(2)),'Position',[4 104 80 28]);
        home.(['h_trace' num2str(k)])=extended_row(group,'','TRA','',1,[178 104 100 28],k);
        home.(['h_vdiv' num2str(k)])=hardware_row(group,'量程','V/div',k,'VDIV',65);
        home.(['h_off' num2str(k)])=hardware_row(group,'偏置','V',k,'OFST',20);
        home.hardware_edits(2*k-1)=home.(['h_vdiv' num2str(k)]); home.hardware_edits(2*k)=home.(['h_off' num2str(k)]);
    else
        ui_text(group,'整机时基',[4 104 160 28]);
        home.h_scope_restore=uicontrol(group,'Style','pushbutton','String','恢复设置','FontSize',13, ...
            'Position',[215 103 120 30],'Callback',@(~,~)request_scope_restore(fig,false));
        home.h_tdiv=hardware_row(group,'时基','ns/div',0,'TDIV',65);
        home.h_trdl=hardware_row(group,'水平位置','ns',0,'TRDL',20);
        home.hardware_edits(5:6)=[home.h_tdiv home.h_trdl];
    end
end
set(home.h_channel_error,'Parent',home.groups(1),'Position',[282 104 99 28]);
home.trigger_panel=uipanel(p,'Units','pixels','Title','触发设置','FontSize',16,'FontWeight','bold','Position',[4 720 400 320],'BackgroundColor',bg);
keys={'TRMD','TRSOURCE','TRSLOPE','TRLEVEL','HTYPE','HTIME'}; labels={'触发模式','触发源','边沿','触发电平','触发释抑方式','释抑时间'}; home.trigger_groups=gobjects(1,6);
for k=1:6
    group=uipanel(home.trigger_panel,'Units','pixels','Position',[4 230-(k-1)*44 386 48],'BorderType','none','BackgroundColor',bg); home.trigger_groups(k)=group;
    unit=ternary(k==4,'V',ternary(k==6,'ns','')); multiplier=ternary(k==6,1e-9,1);
    extended_row(group,labels{k},keys{k},unit,multiplier,[178 19 150 27],0);
end
home.settings_groups=gobjects(1,0);
for ch=1:2
    group=uipanel(p,'Units','pixels','Title',[state.channels{ch} ' 通道与处理'],'FontSize',16,'FontWeight','bold', ...
        'Position',[4 420-(ch-1)*300 400 290],'BackgroundColor',bg);
    set(group,'UserData',struct('index',ch,'label','通道与处理')); home.settings_groups(end+1)=group;
    keys={'CPL','BWL','AVERAGE','INTERPOLATION','ERES','RESPONSE'}; labels={'耦合/阻抗','带宽限制','连续平均','插值','增强分辨率','响应优化'};
    for n=1:6, extended_row(group,labels{n},keys{n},ternary(n==3,'次',''),1,[220 224-(n-1)*38 135 26],ch); end
end
group=uipanel(p,'Units','pixels','Title','采集设置','FontSize',16,'FontWeight','bold','Position',[4 0 400 120],'BackgroundColor',bg);
home.settings_groups(end+1)=group;
h=extended_row(group,'记录点数上限','MSIZ','点',1,[220 60 135 26],0);
set(h,'TooltipString','仪器记录长度的上限；实际返回点数还取决于采样率和时间窗口');
extended_row(group,'采集模式','SAMPLEMODE','',1,[220 20 135 26],0);
home.display_panel=uipanel(p,'Units','pixels','Title','图表显示','FontSize',16,'FontWeight','bold', ...
    'Position',[4 1710 400 230],'BackgroundColor',bg);
group=home.display_panel;
[lo,hi]=msiq.rx_observation_band('from_legacy',state.plot_state.center_hz,state.plot_state.bandwidth_hz);
home.h_center=display_row('统计频段下限','GHz',format_value(lo/1e9),165);
home.h_bandwidth=display_row('统计频段上限','GHz',format_value(hi/1e9),125);
set([home.h_center home.h_bandwidth],'TooltipString','两路共用功率统计频段；只影响观察功率和频谱阴影');
home.h_psd_min=uicontrol(group,'Style','edit','String','-160','UserData','-160','Position',[100 70 90 28]);
home.h_psd_max=uicontrol(group,'Style','edit','String','-80','UserData','-80','Position',[230 70 90 28]);
home.h_psd_label=ui_text(group,'PSD 下/上限（单位待采集确认）',[8 104 380 24]);
home.h_auto_psd=uicontrol(group,'Style','pushbutton','String','适配纵轴','Position',[215 24 140 30]);
home.h_range=ui_text(group,'等待采集',[8 24 200 28]);
home.h_band_source=ui_text(home.panel,state.band_source,[0 0 1 1]); set(home.h_band_source,'Visible','off');
home.h_scope_info=ui_text(home.panel,'未连接',[0 0 1 1]); set(home.h_scope_info,'Visible','off');
home.plot_panel=uipanel(home.panel,'Units','pixels','BorderType','none','BackgroundColor',bg);
home.observation_panel=home.plot_panel;
home.axes=struct(); home.plot_frames=gobjects(1,4); home.plot_titles=gobjects(1,4); home.plot_metrics=gobjects(1,4);
names={'wave_top','spectrum_top','wave_bottom','spectrum_bottom'};
for k=1:4
    panel=uipanel(home.plot_panel,'Units','pixels','BorderType','line','HighlightColor',[.82 .84 .86],'BackgroundColor',[1 1 1]);
    home.plot_frames(k)=panel; home.plot_titles(k)=ui_text(panel,'',[0 0 1 1]); home.plot_metrics(k)=ui_text(panel,'等待采集',[0 0 1 1]);
    set(home.plot_titles(k),'FontWeight','bold','FontSize',13); set(home.plot_metrics(k),'FontSize',10);
    home.axes.(names{k})=axes('Parent',panel,'Units','pixels','PositionConstraint','innerposition','LooseInset',[0 0 0 0]);
    setappdata(home.axes.(names{k}),'rx_embedded_header',home.plot_titles(k));
end
home.h_wave_info=home.plot_metrics([1 3]); home.h_spectrum_info=home.plot_metrics([2 4]);
home.h_wave_title=home.plot_titles([1 3]); home.h_spectrum_title=home.plot_titles([2 4]);
home.axes.wave_info=home.h_wave_info; home.axes.spectrum_info=home.h_spectrum_info;
    function h=hardware_row(parent,label,unit,index,command,y)
        ui_text(parent,label,[4 y+3 64 22]);
        current=ui_text(parent,'--',[92 y+3 68 22]); set(current,'HorizontalAlignment','right','Visible','off');
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
        ui_text(home.display_panel,label,[16 y+3 132 22]);
        h=uicontrol(home.display_panel,'Style','edit','String',value,'Position',[178 y 92 28], ...
            'HorizontalAlignment','right','BackgroundColor',[1 1 1],'UserData',value);
        unit_handle=ui_text(home.display_panel,unit,[282 y+3 110 22]);
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
        set(current,'HorizontalAlignment','right','Visible','off');
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
    'FontName',get(groot,'defaultUicontrolFontName'),'FontSize',12, ...
    'Interpreter','none','VerticalAlignment','bottom','Color',[.16 .18 .21], ...
    'HitTest','off','Clipping','on');
end

function h = ui_text(parent, value, position)
h = uicontrol(parent,'Style','text','String',value,'Units','pixels', ...
    'Position',position,'HorizontalAlignment','left', ...
    'BackgroundColor',get(parent,'BackgroundColor'),'ForegroundColor',[.16 .18 .21]);
end

function layout_home(home,fig)
pos=get(fig,'Position'); w=pos(3); h=pos(4); sidebar=430;
set(home.panel,'Position',[0 0 w h]);
buttons=[home.h_play home.h_pause home.h_single home.h_repeat home.h_settings home.h_stop];
set(home.h_simulation,'Position',[12 h-46 60 34]); set(home.h_measurement,'Position',[72 h-46 60 34]);
positions=[144 244 344 444 644 748]; widths=[94 94 94 94 98 94];
count_x=546; input_x=582; input_width=50; status_x=854;
if w<1200
    positions=[140 232 324 416 600 702]; widths=[86 86 86 86 94 90];
    count_x=510; input_x=552; input_width=40; status_x=800;
end
for k=1:numel(buttons), set(buttons(k),'Position',[positions(k) h-46 widths(k) 34]); end
set(home.h_count_label,'Position',[count_x h-46 36 30]); set(home.h_count,'Position',[input_x h-44 input_width 30]);
set(home.h_status,'Position',[status_x h-52 max(100,w-status_x-12) 44]);
set(home.h_freshness,'Position',[sidebar+8 0 max(100,w-sidebar-20) 22],'FontSize',10);
viewport=max(120,h-66); set(home.settings_panel,'Position',[8 8 sidebar-12 viewport]);
maximum=max(0,home.content_height-viewport); offset=min(maximum,max(0,get(home.scroll,'Max')-get(home.scroll,'Value')));
set(home.scroll,'Position',[sidebar-30 0 14 viewport],'Max',max(1,maximum),'Value',max(1,maximum)-offset, ...
    'SliderStep',min(1,[50 viewport*.8]/max(1,maximum)));
layout_scroll_content(home,fig); layout_plots(home,fig);
setappdata(home.panel,'rx_layout_size',[w h]);
end
function layout_scroll_content(home,fig)
pos=get(fig,'Position'); viewport=max(120,pos(4)-66);
offset=get(home.scroll,'Max')-get(home.scroll,'Value');
set(home.content,'Position',[0 viewport-home.content_height+offset 406 home.content_height]);
end
function layout_plots(home,fig)
pos=get(fig,'Position'); w=pos(3); h=pos(4); sidebar=430;
plot_h=max(220,h-78); width=max(360,w-sidebar-16);
set(home.plot_panel,'Position',[sidebar 24 width plot_h]);
gap=12; column=(width-gap)/2; row=(plot_h-gap)/2;
axes_list=[home.axes.wave_top home.axes.spectrum_top home.axes.wave_bottom home.axes.spectrum_bottom];
for k=1:4
    x=mod(k-1,2)*(column+gap); y=(1-floor((k-1)/2))*(row+gap);
    set(home.plot_frames(k),'Position',[x y column row]);
    set(home.plot_titles(k),'Position',[12 row-39 column-24 36]);
    set(home.plot_metrics(k),'Position',[12 row-71 column-24 30]);
    set(axes_list(k),'Units','pixels','Position',[64 46 max(100,column-91) max(80,row-150)]);
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
if startsWith(request.action,'board_')
    assert(board_applicable(state) && field_or(request,'board_measurement_revision',-1)==state.measurement_revision, ...
        'RX_Workbench:BoardPosition','当前测量选择不允许执行该板卡命令');
end
request.rx_position_guard=true;
request.source_epoch=state.source_epoch;
if ~isfield(request,'measurement_context'), request.measurement_context=measurement_context(state); end
request.measurement_revision=state.measurement_revision;
request.range_policy=state.if_profile.scope;
request.reference_bundle=state.reference_bundle; if isempty(request.reference_bundle), request.reference_bundle=state.reference_path; end
request.range_reference_identity=field_or(state.reference_info,'reference_identity',request.reference_bundle);
if strcmp(request.action,'capture') && strcmp(request.reference_bundle,state.real_if_reference_path)
    request.real_if_reference=state.real_if_reference;
end
state.worker_request=request;
wire=request;
if isfield(wire,'handle'), wire=rmfield(wire,'handle'); end
if isfield(wire,'completion'), wire=rmfield(wire,'completion'); end
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
    if field_or(response,'source_epoch',field_or(request,'source_epoch',state.source_epoch))~=state.source_epoch
        state.busy=false; setappdata(fig,'rx_workbench_state',state); return;
    end
    state.busy=false;
    if startsWith(request.action,'board_') || ismember(request.action,{'formal_capture','formal_range'})
        if transport_failed || response_requires_disconnect(response), state.connected=false; state.running=false; state.paused=true; end
        setappdata(fig,'rx_workbench_state',state);
        if isfield(request,'completion'), request.completion(response);
        else, accept_daily_response(fig,response); end
        update_buttons(fig); tick_daily_task(fig); return;
    end
    if strcmp(request.action,'restore_settings')
        if transport_failed||response_requires_disconnect(response),state.connected=false;end
        setappdata(fig,'rx_workbench_state',state);
        finish_scope_restore(fig,field_or(response,'report',struct('ok',false,'errors',{{field_or(response,'error','恢复失败')}})));
        update_buttons(fig);return;
    end
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
                if strcmp(request.action,'connect'),scope_connected(fig);end
            case 'capture'
                if isequal(request.channels,selected_channels(state)) && field_or(request,'measurement_revision',state.measurement_revision)==state.measurement_revision
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
                        if isfield(response,'range_decision')
                            state.observation_cache=struct('decision',response.range_decision,'status',response.status, ...
                                'observed_datenum',field_or(response,'observed_datenum',now), ...
                                'measurement_revision',request.measurement_revision,'channels',{selected_channels(state)}, ...
                                'refresh_period_s',state.options.refresh_period_s);
                        end
                    end
                    setappdata(fig,'rx_workbench_state',state);
                    sync_controls(state,false);
                    redraw_current(fig);
                    show_range_hint(getappdata(fig,'rx_workbench_state'));
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
                setappdata(fig,'rx_workbench_state',state);
                accept_control(fig,request,response.accepted);
                state=getappdata(fig,'rx_workbench_state');
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
if ~isempty(state.scope_restore_pending),drain_scope_restore(fig);return;end
if task_active(state) || ~isempty(state.board_pending), tick_daily_task(fig); return; end
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
    submit_worker(fig,struct('action','capture','channels',{selected_channels(state)}));
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
if isfield(response,'report') && isfield(response.report,'error_id')
    identifier=[identifier ' ' lower(char(string(response.report.error_id)))];
end
yes=strcmp(identifier,'rx_workbench:readback') || ...
    strcmp(identifier,'rx_workbench:transport') || ...
    any(contains(identifier,{'visa','timeout','transport','readfailure','block','instrument:','rx_workbench:readback'}));
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
if ~isgraphics(fig), return; end
state=getappdata(fig,'rx_workbench_state');
if ~isempty(state.source_switch), return; end
if state.close_requested && ~state.reference_busy, return; end
if ~task_active(state), state=poll_reference_link(fig,state,false); end
if state.reference_busy
    try
        [ready,response]=state.reference_worker.poll();
    catch exception
        ready=true; response=struct('ok',false,'error',exception.message);
    end
    if ~ready, return; end
    state.reference_busy=false;
    request=state.reference_request;
    if field_or(response,'source_epoch',field_or(request,'source_epoch',state.source_epoch))~=state.source_epoch
        setappdata(fig,'rx_workbench_state',state); return;
    end
    setappdata(fig,'rx_workbench_state',state);
    if strcmp(request.action,'prepare_simulation')
        accept_simulation_source(fig,response); return;
    end
    if ismember(request.action,{'demod','prepare_reference'})
        accept_daily_response(fig,response); tick_daily_task(fig); return;
    end
    if field_or(request,'measurement_revision',state.measurement_revision)~=state.measurement_revision
        state.reference_pending=true; setappdata(fig,'rx_workbench_state',state); return;
    end
    if response.ok, info=response.reference;
    else, info=struct('path','','error',response.error); end
    apply_reference_band(fig,request.channels,info);
    state=getappdata(fig,'rx_workbench_state');
end
if ~state.reference_pending || task_active(state) || state.close_requested, return; end
state.reference_pending=false;
try
    if isempty(state.reference_worker) || state.reference_worker.process.HasExited
        state.reference_worker=msiq.RxScopeWorker(struct(),state.reference_factory,state.worker_options,'reference');
    end
    request=struct('action','reference','project_root',state.cfg.project_root, ...
        'channels',{selected_channels(state)},'path',state.reference_path,'search',state.find_reference,'measurement_context',measurement_context(state));
    request.reference_options=reference_options(state);
    request.source_epoch=state.source_epoch; request.measurement_revision=state.measurement_revision; state.reference_worker.submit(request);
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
if ~isempty(state.source_switch) || state.busy || state.simulation_preparing, return; end
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
if state.connected,scope_connected(fig);end
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
if scope_controls_locked(getappdata(fig,'rx_workbench_state')), return; end
state = getappdata(fig,'rx_workbench_state');
data = get(handle,'UserData');
input_state=getappdata(handle,'rx_input_state');
if ~isempty(input_state) && input_state.pending && ...
        input_state.version==input_state.request_version, return; end
if strcmp(get(handle,'String'),data.displayed) && strcmp(get(data.retry,'Visible'),'off') && ...
        ~msiq.rx_input_state('protected',handle)
    return;
end
value = str2double(get(handle,'String'))*data.multiplier;
if ~isfinite(value) || (requires_positive_setting(data.setting) && value <= 0)
    field_error(handle,'请输入有效数值',false);
    return;
end
inflight=state.busy && isfield(state.worker_request,'handle') && state.worker_request.handle==handle;
queued=~isempty(state.pending) && any([state.pending.handle]==handle);
if state.connected && isequal(value,data.actual) && ~inflight && ~queued
    data.displayed=get(handle,'String'); set(handle,'UserData',data);
    msiq.rx_input_state('pending',handle,state.revision);
    msiq.rx_input_state('accept',handle,struct('revision',state.revision,'value',value),value);
    field_error(handle,'',false);
    return;
end
command = data.setting;
if data.index > 0, command = [state.channels{data.index} ':' command]; end
state.revision = state.revision+1;
request = struct('handle',handle,'command',command,'value',value,'revision',state.revision);
setappdata(handle,'rx_requested_value',value);
msiq.rx_input_state('pending',handle,state.revision);
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
    request.action='setting';request.origin='manual';request.selection_revision=state.measurement_revision;request.before_status=state.scope_status;
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
    request.origin='manual';request.selection_revision=state.measurement_revision;request.before_status=state.scope_status;
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
        state = getappdata(fig,'rx_workbench_state');
        state.scope_status=msiq.instruments.rx_scope_state(state.session,state.io.query);
        state.scope_status.settings=read_extended(state,state.session,false);
        setappdata(fig,'rx_workbench_state',state);
        accept_control(fig,request,accepted);
        state=getappdata(fig,'rx_workbench_state');
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
if scope_controls_locked(getappdata(fig,'rx_workbench_state')), return; end
if nargin<3, explicit_retry=false; end
state=getappdata(fig,'rx_workbench_state'); data=get(handle,'UserData');
input_state=getappdata(handle,'rx_input_state');
if (~data.available || ~data.writable) && ~explicit_retry, return; end
if data.numeric
    value=str2double(get(handle,'String'))*data.multiplier;
    if ~isfinite(value), field_error(handle,'请输入有效数值',false); return; end
else
    value=data.choices{get(handle,'Value')};
end
if ~explicit_retry && ~isempty(input_state) && input_state.pending && ...
        isequaln(value,getappdata(handle,'rx_requested_value')), return; end
key=data.key;
if data.index>0, key=[state.channels{data.index} ':' key]; end
retry=~isempty(data.retry) && isgraphics(data.retry) && strcmp(get(data.retry,'Visible'),'on');
inflight=state.busy && isfield(state.worker_request,'handle') && state.worker_request.handle==handle;
queued=~isempty(state.control_pending) && any([state.control_pending.handle]==handle);
if isequaln(value,data.actual) && ~retry && ~inflight && ~queued
    msiq.rx_input_state('pending',handle,state.revision);
    msiq.rx_input_state('accept',handle,struct('revision',state.revision,'value',value),value);
    field_error(handle,'',false); return;
end
state.revision=state.revision+1;
request=struct('handle',handle,'key',key,'value',value,'revision',state.revision);
setappdata(handle,'rx_requested_value',value);
msiq.rx_input_state('pending',handle,state.revision);
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
    request.action='control';request.origin='manual';request.selection_revision=state.measurement_revision;request.before_status=state.scope_status; submit_worker(fig,request); return;
end
request.origin='manual';request.selection_revision=state.measurement_revision;request.before_status=state.scope_status;
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
prior=getappdata(request.handle,'rx_input_state');
current_request=~isempty(prior)&&prior.request==request.revision&&prior.version==prior.request_version&&~prior.dirty;
msiq.rx_input_state('accept',request.handle,request,accepted);
if msiq.rx_input_state('protected',request.handle)
    field_error(request.handle,sprintf('尚未确认；实际回读 %s',char(string(accepted))),false);
else
    field_error(request.handle,'',false);
    if current_request,save_manual_scope(fig,request);end
end
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
        msiq.rx_input_state('known',handle,false);
        set(data.current,'String',ternary(state.connected,'不可用','--'));
        set(handle,'Enable','off'); data.available=false; data.writable=false;
        if ~isempty(n), set(handle,'TooltipString',fields(n).error); end
        set(handle,'UserData',data); continue;
    end
    f=fields(n);
    if state.native_simulation && endsWith(key,':BWL')
        data.available=true; data.writable=false; data.actual='OFF'; data.displayed='OFF'; data.choices={'OFF'};
        set(handle,'String',{'全带宽'},'Value',1,'Enable','off','UserData',data, ...
            'TooltipString','连接实测后读取当前通道支持的带宽限制档位');
        msiq.rx_input_state('known',handle,false);
        continue;
    end
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
        untouched=strcmp(get(handle,'String'),data.displayed) && ~msiq.rx_input_state('editing',handle);
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
    if (force || untouched) && ~pending && ~failed && ~msiq.rx_input_state('editing',handle)
        if data.numeric
            if ~isequaln(str2double(get(handle,'String'))*data.multiplier,f.value)
                set(handle,'String',display);
            end
            data.displayed=get(handle,'String');
        else, data.displayed=char(string(f.value)); end
        field_error(handle,'',false);
    end
    data.actual=f.value;
    data.snapshot=f; data.resolved_key=key;
    set(handle,'UserData',data,'Enable',ternary(f.writable,'on','off'));
    if ~f.writable
        msiq.rx_input_state('known',handle,false);
        set(handle,'TooltipString',field_or(f,'error','当前设置只读'));
    else
        msiq.rx_input_state('observed',handle);
    end
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
if retry
    msiq.rx_input_state('failed',handle);
elseif ~isempty(message)
    set(handle,'BackgroundColor',[1 .88 .86]);
else
    msiq.rx_input_state('known',handle,isnumeric(data.actual)&&isscalar(data.actual)&&isfinite(data.actual) || ...
        ischar(data.actual)&&~isempty(data.actual));
end
end

function sync_controls(state, force)
sync_extended(state,force);
if ~state.connected
    for handle=state.home.hardware_edits, msiq.rx_input_state('known',handle,false); end
    if force
        for handle = state.home.hardware_edits
            data = get(handle,'UserData');
            data.displayed = '--'; data.actual = NaN;
            if ~msiq.rx_input_state('protected',handle), set(handle,'String','--','UserData',data); end
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
        if isempty(idx)
            data.actual=NaN; msiq.rx_input_state('known',handle,false);
            if ~msiq.rx_input_state('protected',handle)
                data.displayed='--'; set(handle,'String','--');
            end
            set(data.current,'String','--'); set(handle,'UserData',data); continue;
        end
        channel = state.scope_status.channels(idx);
        if strcmp(data.setting,'VDIV'), value = channel.vertical_scale_v_per_div; else, value = channel.offset_v; end
    end
    pending = ~isempty(state.pending) && any([state.pending.handle] == handle);
    if state.busy && isfield(state.worker_request,'handle')
        pending = pending || state.worker_request.handle == handle;
    end
    protected=msiq.rx_input_state('editing',handle);
    untouched = strcmp(get(handle,'String'),data.displayed) && ~protected;
    if strcmp(data.setting,'TDIV') && ~protected && (force || (untouched && ~pending))
        [data.multiplier,unit] = timebase_unit(value);
        set(data.unit,'String',unit);
    end
    text_value = format_value(value/data.multiplier);
    if ~protected && (force || (untouched && ~pending))
        if ~isequaln(str2double(get(handle,'String'))*data.multiplier,value)
            set(handle,'String',text_value);
        end
        data.displayed = get(handle,'String');
        field_error(handle,'',false);
    end
    data.actual = value;
    stamp=field_or(state.scope_status,'readback_at',[]);
    set(data.current,'String',text_value,'TooltipString', ...
        sprintf('回读 %.15g\n%s',value/data.multiplier,char(string(stamp))));
    set(handle,'UserData',data);
    msiq.rx_input_state('observed',handle);
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
if any(strcmp(state.measurement_position,{'tx_if','thz_if'}))
    caption='原始频谱上下限';
else, caption='PSD 下/上限'; end
set(state.home.h_psd_label,'String',[caption ' / ' unit]);
for handle=[state.home.h_psd_min state.home.h_psd_max]
    label=getappdata(handle,'rx_display_unit');
    if ~isempty(label), set(label,'String',unit); end
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
for k = 1:numel(channels)
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
active_task=task_active(state);
sync_extended(state,false);
if ~state.connected
    for handle = state.home.hardware_edits
        data = get(handle,'UserData');
        set(data.current,'String','--');
    end
    set(state.home.h_scope_info,'String','未连接，当前硬件状态未知');
end
can_start=~state.running && ~state.close_requested && isempty(state.source_release_error) && isempty(state.pending_page) && ...
    (~state.busy || (state.asynchronous && ~strcmp(field_or(state.worker_request,'action',''),'release')));
set(state.home.h_play,'Enable',ternary(can_start,'on','off'));
set(state.home.h_pause,'Enable',ternary(state.running,'on','off'));
set([state.home.h_ch1 state.home.h_ch2 state.home.h_single state.home.h_repeat], ...
    'Enable',ternary(~state.busy,'on','off'));
if state.asynchronous
    set([state.home.h_single state.home.h_repeat],'Enable','on');
end
set([state.home.h_single state.home.h_repeat state.home.h_balance state.home.h_demod state.home.h_count state.home.h_ch1 state.home.h_ch2], ...
    'Enable',ternary(~active_task,'on','off'));
set([state.home.position_buttons state.home.subband_buttons],'Enable',ternary(~measurement_locked(state),'on','off'));
if any(strcmp(state.measurement_position,{'tx_if','thz_if'})), set(state.home.h_ch2,'Enable','off','Value',5); end
sync_measurement_controls(state);
set(state.home.h_ldpc,'Enable',ternary(~active_task && get(state.home.h_demod,'Value'),'on','off'));
state.home.board.setBusy(active_task);
if active_task, set([state.home.hardware_edits state.home.extended_edits state.home.h_profile],'Enable','off');
else
    set(state.home.h_profile,'Enable','on');
    set(state.home.hardware_edits,'Enable',ternary(state.connected,'on','off'));
end
set([state.home.h_center state.home.h_bandwidth],'Enable',ternary(active_task,'off','on'));
set(state.home.h_stop,'Enable',ternary(active_task||~isempty(state.scope_restore_pending),'on','off'));
if ~state.second_enabled
    set(state.home.hardware_edits(3:4),'Enable','off');
    for handle=state.home.extended_edits, data=get(handle,'UserData'); if data.index==2, set(handle,'Enable','off'); end; end
end
[ready,why]=daily_ready(state,false); [balance_ready,balance_why]=daily_ready(state,true);
set([state.home.h_single state.home.h_repeat],'Enable',ternary(~active_task && ready,'on','off'),'TooltipString',why);
set(state.home.h_balance,'Enable',ternary(~active_task && balance_ready,'on','off'),'TooltipString',balance_why);
if ready && ~balance_ready && board_applicable(state), why=['单点就绪；配平：' balance_why]; end
set_single_line(state.home.h_gate,why);
set(state.home.h_reference,'Enable',ternary(~active_task,'on','off'));
set(state.home.h_reference_auto,'Enable',ternary(~active_task && state.reference_manual,'on','off'));
set([state.home.h_reference state.home.h_reference_auto],'Visible',ternary(strcmp(state.source_mode,'simulation'),'off','on'));
refresh_reference_label(state);
window=getappdata(fig,'rx_capture_settings_window');
if ~isempty(window)&&isgraphics(window)
    setter=getappdata(window,'rx_capture_settings_applicability');if ~isempty(setter),setter(board_applicable(state));end
end
[can_restore,restore_why]=scope_restore_ready(state);
set(state.home.h_scope_restore,'Enable',ternary(can_restore,'on','off'),'TooltipString',restore_why);
if ~isempty(state.scope_restore_pending)
    set([state.home.hardware_edits state.home.extended_edits state.home.h_single state.home.h_repeat state.home.h_balance state.home.h_play state.home.h_ch1 state.home.h_ch2 state.home.h_profile],'Enable','off');
end
set(state.home.h_settings,'Enable',ternary(~active_task,'on','off'));
source_locked=~isempty(state.scope_restore_pending) || state.running || active_task || state.busy || state.reference_busy || state.simulation_preparing || ...
    ~isempty(state.pending) || ~isempty(state.control_pending) || ~isempty(state.board_pending) || state.close_requested || ~isempty(state.source_switch);
set([state.home.h_simulation state.home.h_measurement],'Enable',ternary(source_locked,'off','inactive'));
selected=ternary(strcmp(state.source_mode,'simulation'),state.home.h_simulation,state.home.h_measurement);
other=ternary(strcmp(state.source_mode,'simulation'),state.home.h_measurement,state.home.h_simulation);
set(selected,'BackgroundColor',[.10 .28 .48],'ForegroundColor',[1 1 1],'FontWeight','bold');
set(other,'BackgroundColor',[.90 .92 .94],'ForegroundColor',[.15 .20 .25],'FontWeight','normal');
set(state.home.h_simulation,'Value',strcmp(state.source_mode,'simulation'));
set(state.home.h_measurement,'Value',strcmp(state.source_mode,'measurement'));
if ~isempty(state.source_switch)
    set([state.home.h_play state.home.h_pause state.home.h_single state.home.h_repeat state.home.h_balance state.home.h_reference state.home.h_reference_auto state.home.h_profile state.home.h_demod state.home.h_ldpc state.home.h_count state.home.h_ch1 state.home.h_ch2 state.home.hardware_edits state.home.extended_edits],'Enable','off');
    state.home.board.setBusy(true);
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
state=getappdata(fig,'rx_workbench_state');
if ismember(string(page),["settings","single","repeat"]), page='home'; end
set(state.home.panel,'Visible',ternary(strcmp(page,'home'),'on','off'));
for name={'single','repeat','result'}, set(state.pages.(name{1}),'Visible',ternary(strcmp(page,name{1}),'on','off')); end
state.page=string(page); setappdata(fig,'rx_workbench_state',state);
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

function run_tests(fig,repeat_count,balance)
if nargin<3, balance=false; end
state=getappdata(fig,'rx_workbench_state');
if task_active(state), return; end
try
    assert(isempty(state.scope_restore_pending),'RX_Workbench:ScopeRestore','示波器设置正在恢复');
    [blocked,why]=msiq.rx_input_state('blocked',[state.home.hardware_edits state.home.extended_edits]);
    assert(~blocked,'RX_Workbench:Draft',why);
    assert(isempty(state.pending) && isempty(state.control_pending) && ...
        ~(state.busy && ismember(field_or(state.worker_request,'action',''),{'setting','control'})), ...
        'RX_Workbench:ScopePending','示波器设置正在下发或等待回读，请稍后开始测试');
    assert(isempty(state.board_pending) && ~(state.busy && startsWith(field_or(state.worker_request,'action',''),'board_')), ...
        'RX_Workbench:BoardBusy','请等待板卡下发完成再开始测量');
    assert(state.asynchronous,'RX_Workbench:TaskWorker','测试需启用后台进程；离线验证请提供 mock worker factory');
    assert(state.connected,'RX_Workbench:Disconnected','请先点击开始观察连接示波器');
    assert(~isempty(state.measurement_position),'RX_Workbench:Position','请先选择测量位置');
    if balance
        assert(any(strcmp(state.measurement_position,{'rx_if','rx_if_thz'})),'RX_Workbench:BalancePosition','自动配平仅用于中频下变频输出');
        check_simulation_subband(state);
    end
    channels=selected_channels(state); demod=logical(get(state.home.h_demod,'Value'));
    state=poll_reference_link(fig,state,true);
    bundle=state.reference_bundle; if isempty(bundle), bundle=state.reference_path; end
    if demod || balance
        context=measurement_context(state);
        assert(numel(channels)==1+~context.is_real_if,'RX_Workbench:Channels','实际通道数量与测量位置不符');
        assert(~isempty(bundle),'RX_Workbench:Reference','请先关联有效发送参考');

    end
    profile=state.if_profile; profile.board=state.home.board.getConfig(); profile.subband=state.home.board.getSelection();
    profile.scope.channels=channels;
    state.task_sequence=state.task_sequence+1;
    state.task_history_base=field_or(state,'all_daily_rows',{});
    opts=struct('results_root',state.cfg.results_root,'cfg_override',state.cfg,'scope_channels',{channels},'tx_reference_bundle',bundle, ...
        'source_mode',state.source_mode,'test_fixture',(state.offline_test && ~state.native_simulation) || field_or(state.simulation,'test_fixture',false), ...
        'capture_then_demod',demod,'enable_ldpc',logical(get(state.home.h_ldpc,'Value')),'measurement_context',measurement_context(state));
    if ~state.reference_manual && ~state.native_simulation && (demod || balance)
        link=field_or(state.reference_info,'reference_link',struct());
        assert(field_or(link,'valid',false),'RX_Workbench:Reference','自动发送参考尚未关联，请稍后或手动选择');
        opts.reference_association=struct('options',reference_options(state),'expected_hash',link.hash);
    end
    opts.sampling_baseline_source='front_panel';
    opts.measurement_revision=state.measurement_revision;
    opts.observation_cache=state.observation_cache;
    close_capture_settings(fig);
    state.task=msiq.RxDailyTask(state.task_sequence,opts,profile,channels,repeat_count,balance,state.home.board.getSnapshot());
    state.daily_run=msiq.rx_daily_journal('begin',state.cfg,state.task);
    state.last_task_summary='';
    state.resume_observation=state.running; state.running=false; state.task_waiting=false;
    setappdata(fig,'rx_workbench_state',state); set_page(fig,'home');
    set_status(fig,'任务准备中'); update_task_result(fig,true); update_buttons(fig); tick_daily_task(fig);
catch exception, set_status(fig,exception.message); end
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
    if startsWith(text_value,'已回读') && ~isempty(state.scope_preset_error),text_value=[char(text_value) ' | ' state.scope_preset_error];end
    passive=ismember(string(text_value),["观察中","读取中","已暂停","已读取新波形", ...
        "等待新触发或平均更新","观察中，采集时间未确认","所选通道未开启或无数据"]);
    observing=state.busy && strcmp(field_or(state.worker_request,'action',''),'capture');
    if ~isempty(field_or(state,'last_task_summary','')) && (passive || observing)
        text_value=[state.last_task_summary ' | ' char(text_value)];
    end
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

function value=merge_struct(value,extra)
for name=fieldnames(extra)'
    k=name{1}; if isfield(value,k) && isstruct(value.(k)) && isstruct(extra.(k)), value.(k)=merge_struct(value.(k),extra.(k));
    else, value.(k)=extra.(k); end
end
end
function yes=task_active(state)
yes=isfield(state,'task') && ~isempty(state.task) && state.task.active;
end
function channels=selected_channels(state)
channels=state.channels;
if isfield(state,'second_enabled') && ~state.second_enabled, channels=channels(1); end
end
function daily_options_changed(fig)
state=getappdata(fig,'rx_workbench_state');
set(state.home.h_ldpc,'Enable',ternary(get(state.home.h_demod,'Value'),'on','off'));
update_buttons(fig);
end
function queue_board(fig,action,payload,completion)
state=getappdata(fig,'rx_workbench_state');
if ~board_applicable(state)
    reason='当前测量位置不能操作 RX 中频板卡';
    record_board_rejection(fig,action,reason); completion(struct('ok',false,'error',reason)); return;
end
if task_active(state) || ~isempty(state.source_switch) || ~isempty(state.source_release_error), completion(struct('ok',false,'error','任务、来源切换或未确认的释放状态阻止下发')); return; end
request=struct('action',action,'payload',payload,'completion',completion,'timeout_s',90, ...
    'board_measurement_revision',state.measurement_revision);
state.board_pending{end+1}=request; setappdata(fig,'rx_workbench_state',state); tick_daily_task(fig);
end
function tick_daily_task(fig)
if ~isgraphics(fig), return; end
state=getappdata(fig,'rx_workbench_state');
if state.close_requested || ~isempty(state.source_switch) || state.simulation_preparing, return; end
if state.native_simulation && isempty(fieldnames(state.simulation_source))
    if ~isempty(state.board_pending), prepare_simulation(fig); end
    return;
end
if ~isempty(state.board_pending) && ~state.busy
    request=state.board_pending{1}; state.board_pending(1)=[];
    if ~board_applicable(state) || field_or(request,'board_measurement_revision',-1)~=state.measurement_revision
        setappdata(fig,'rx_workbench_state',state);
        reason='测量选择已变化，未执行板卡命令'; record_board_rejection(fig,request.action,reason);
        request.completion(struct('ok',false,'error',reason)); return;
    end
    if isempty(state.worker) || state.worker.process.HasExited
        state.worker=msiq.RxScopeWorker(state.cfg.instrument.scope,state.worker_factory,state.worker_options);
    end
    setappdata(fig,'rx_workbench_state',state);
    try submit_worker(fig,request);
    catch exception, request.completion(struct('ok',false,'error',exception.message)); end
    return;
end
if ~task_active(state) || state.task_waiting || state.busy, return; end
if state.task.stopped
    state.task.active=false; finish_daily_task(fig); return;
end
try
    request=state.task.next(); if isempty(request), return; end
    if ismember(request.action,{'demod','prepare_reference'}) && state.reference_busy, return; end
    msiq.rx_daily_journal('update',state.cfg,state.task,state.daily_run,request);
    if ismember(request.action,{'demod','prepare_reference'})
        if state.reference_busy, return; end
        if isempty(state.reference_worker) || state.reference_worker.process.HasExited
            state.reference_worker=msiq.RxScopeWorker(struct(),state.reference_factory,state.worker_options,'reference');
        end
        request.source_epoch=state.source_epoch; state.reference_worker.submit(request); state.reference_request=request; state.reference_busy=true;
    else
        request.source_epoch=state.source_epoch;
request.rx_position_guard=true;
if ~isfield(request,'measurement_context'), request.measurement_context=measurement_context(state); end
request.measurement_revision=state.measurement_revision;
request.reference_bundle=state.reference_bundle; if isempty(request.reference_bundle), request.reference_bundle=state.reference_path; end
request.range_reference_identity=field_or(state.reference_info,'reference_identity',request.reference_bundle);
if strcmp(request.action,'capture') && strcmp(request.reference_bundle,state.real_if_reference_path)
    request.real_if_reference=state.real_if_reference;
end
state.worker_request=request; state.worker.submit(request); state.busy=true;
    end
    state.task_waiting=true; setappdata(fig,'rx_workbench_state',state);
    set_status(fig,sprintf('%s | 正式 %d/%d | %.1f 秒',daily_action_label(request.action),state.task.completed,state.task.count,toc(state.task.started)));
catch exception
    state.task.active=false; state.task.reason=exception.message; setappdata(fig,'rx_workbench_state',state); finish_daily_task(fig);
end
end
function accept_daily_response(fig,response)
state=getappdata(fig,'rx_workbench_state'); state.task_waiting=false;
if isfield(response,'snapshot'), state.home.board.update(response.snapshot); end
if isfield(response,'raw') && isfield(response.raw,'channels') && ~isempty(response.raw.channels)
    state.raw=response.raw; state.raw_scope_status=response.status; state.scope_status=response.status;
end
try state.task.accept(response);
catch exception
    state.task.fail(exception); response.ok=false; response.error=exception.message; response.error_id=exception.identifier;
end
if isfield(response,'raw') && isfield(response,'observation') && ...
        isfield(response.observation,'range_decision')
    state.observation_cache=struct('decision',state.task.observation.range_decision, ...
        'status',response.status,'observed_datenum',now,'measurement_revision',state.measurement_revision, ...
        'channels',{selected_channels(state)},'refresh_period_s',state.options.refresh_period_s);
    state.raw_stale=false;
end
try msiq.rx_daily_journal('update',state.cfg,state.task,state.daily_run,response);
catch exception, state.task.active=false; state.task.reason=['记录保存失败：' exception.message]; end
setappdata(fig,'rx_workbench_state',state);
sync_controls(state,false); update_buttons(fig);show_range_hint(state);
redraw_current(fig); update_daily_history(fig);
if ~state.task.active, finish_daily_task(fig); end
end
function finish_daily_task(fig)
state=getappdata(fig,'rx_workbench_state');
state.task_waiting=false;
try msiq.rx_daily_journal('finalize',state.cfg,state.task,state.daily_run);
catch exception, state.task.reason=['记录保存失败：' exception.message]; end
state.last_task_summary=state.task.reason;
normal=~state.task.stopped && (strcmp(state.task.reason,'测量完成') || ...
    ismember(state.task.reason,{'配平完成，已达到容差','配平停止：达到调整次数上限','配平停止：达到批准边界', ...
    '通信质量确认变差，已恢复此前设置','功率差不再改善，已恢复此前设置'}));
state.running=normal && state.resume_observation; state.paused=~state.running;
setappdata(fig,'rx_workbench_state',state); update_buttons(fig); set_status(fig,state.task.reason); update_task_result(fig,false);
end
function stop_daily_task(fig)
state=getappdata(fig,'rx_workbench_state');
if ~isempty(state.scope_restore_pending)
    state.scope_restore_cancelled=true;state.scope_restore_resume=false;state.running=false;state.paused=true;
    if ~isempty(state.worker),state.worker.cancel(state.scope_restore_id);end
    setappdata(fig,'rx_workbench_state',state);set_status(fig,'已请求停止，正在结束恢复');
    if ~state.busy
        finish_scope_restore(fig,struct('ok',false,'errors',{{'已停止恢复'}},'applied',{{}},'phase','cancelled'));
    end
    return;
end
if ~task_active(state), return; end
state.task.stop(); state.running=false; state.paused=true;
if ~isempty(state.worker), state.worker.cancel(state.task.id); end
if ~isempty(state.reference_worker), state.reference_worker.cancel(state.task.id); end
setappdata(fig,'rx_workbench_state',state); set_status(fig,'已请求停止，正在收尾');
if ~state.task_waiting, state.task.active=false; finish_daily_task(fig); end
end
function label=daily_action_label(action)
switch action
    case 'formal_capture', label='新采集与保存';
    case 'demod', label='解调已保存波形';
    case 'prepare_reference', label='核对发送参考';
    case 'formal_range', label='调整并核对量程';
    otherwise, label='中频控制';
end
end
function update_task_result(fig,open_window)
% Keep a read-only result window independent from acquisition and its lifetime.
if ~isgraphics(fig), return; end
state=getappdata(fig,'rx_workbench_state');
if isempty(state.task)
    snapshot=struct('task_id',[state.source_mode ':history'],'source_mode',state.source_mode, ...
        'active',false,'reason','历史记录','rows',{field_or(state,'all_daily_rows',{})});
    window=getappdata(fig,'rx_result_window'); action='update'; if open_window, action='open'; end
    window=msiq.rx_result_window(action,window,snapshot,get(fig,'Visible'));
    setappdata(fig,'rx_result_window',window); return;
end
task=state.task;
snapshot=struct('task_id',sprintf('%s:%d',state.source_mode,task.id), ...
    'source_mode',state.source_mode,'phase',task.phase,'role',task.role, ...
    'completed',task.completed,'count',task.count,'elapsed_s',toc(task.started), ...
    'active',task.active,'reason',task.reason,'rows',{task.rows}, ...
    'current_capture',task.capture,'current_observation',task.observation, ...
    'task_dir',field_or(state.daily_run,'OutputDir',''));
if ~task.active
    previous=getappdata(fig,'rx_result_snapshot');
    if isstruct(previous) && isequal(field_or(previous,'task_id',''),snapshot.task_id) && ~field_or(previous,'active',true)
        snapshot.elapsed_s=previous.elapsed_s;
    end
end
setappdata(fig,'rx_result_snapshot',snapshot);
window=getappdata(fig,'rx_result_window');
action='update'; if open_window, action='open'; end
window=msiq.rx_result_window(action,window,snapshot,get(fig,'Visible'));
setappdata(fig,'rx_result_window',window);
if task.active
    phase=daily_action_label(task.phase);
    if strcmp(task.phase,'capture'), phase=[daily_role_label(task.role) '采集与保存']; end
    if task.stopped, phase='已请求停止，正在收尾'; end
    set_status(fig,sprintf('%s | 正式 %d/%d | %.1f 秒',phase,task.completed,task.count,snapshot.elapsed_s));
end
end
function update_daily_history(fig)
state=getappdata(fig,'rx_workbench_state'); rows=[state.task_history_base state.task.rows];
state.all_daily_rows=rows; setappdata(fig,'rx_workbench_state',state);
if isempty(rows), return; end
labels=arrayfun(@(k)daily_history_label(rows{k},k),1:numel(rows),'UniformOutput',false);
set(state.home.h_history,'String',labels,'Value',numel(rows));
setappdata(state.home.h_history,'records',rows); daily_select_record(fig);
end
function daily_select_record(fig)
state=getappdata(fig,'rx_workbench_state'); rows=getappdata(state.home.h_history,'records');
if isempty(rows), return; end
row=rows{get(state.home.h_history,'Value')}; obs=row.observation;
record_source=msiq.rx_capture_source(field_or(obs,'display_raw',struct()),row.capture);
record_context=msiq.rx_measurement_context(field_or(row.capture,'measurement_context',struct()));
record_label=record_context.label;
if isfield(record_context,'subband'), record_label=sprintf('%s · 子带 %d',record_label,record_context.subband); end
actual=field_or(row.capture,'actual_scope_channels',{});
if ~isempty(actual), record_label=[record_label ' · ' strjoin(cellstr(string(actual)),' / ')]; end
set(state.home.h_history,'TooltipString',sprintf('%s\n%s',record_label,row.capture.run_dir));
if isfield(obs,'display_raw') && isfield(obs.display_raw,'channels')
    state.raw=obs.display_raw; state.raw_scope_status=field_or(obs,'scope_status',struct());
else
    state.raw=struct(); state.raw_scope_status=struct(); state.raw_stale=true;
    state.stale_reason='该记录图件请在详细结果中查看';
    msiq.plotting.rx_live_dashboard(state.home.axes,struct(),struct(),struct(),struct());
    set(state.home.plot_titles,{'String'},{'原始波形';'原始频谱';'处理结果';'处理结果'});
    set([state.home.h_wave_info state.home.h_spectrum_info],'String',state.stale_reason);
end
if isfield(obs,'metrics') && isfield(obs.metrics,'pre_ber')
    m=obs.metrics;
    if m.valid, label=sprintf('纠错前 BER %.4g\n错误数 / 统计比特数：%.0f / %.0f\nMER %.3f dB',m.pre_ber,m.pre_error_count,m.pre_bit_count,m.mer_db);
    else, label=['指标无效：' m.reason]; end
else, label='本次未解调'; end
if ismember(row.role,{'failed','cancelled'}) && ~isempty(field_or(obs,'attempt_reason',''))
    label=[daily_role_label(row.role) '：' obs.attempt_reason];
end
if isfield(obs,'result') && ~isempty(fieldnames(obs.result))
    label=sprintf('%s\n%s',label,msiq.rx_decoder_summary(obs.result));
end
if isfield(obs,'power_dbv2')
    label=sprintf('%s\n带内功率：%s dB(V²)',label,num2str(obs.power_dbv2,' %.3f'));
    if numel(obs.power_dbv2)==2, label=sprintf('%s；差 %.3f dB',label,diff(obs.power_dbv2)); end
end
source_labels=struct('simulation','模拟','measurement','实测','unknown','来源未记录');
label=sprintf('%s\n来源：%s',label,source_labels.(record_source));
full_label=sprintf('%s\n%s',record_label,label);
if isfield(obs,'metrics') && isfield(obs.metrics,'valid') && obs.metrics.valid
    m=obs.metrics; label=sprintf('纠错前 BER %.4g · MER %.3f dB',m.pre_ber,m.mer_db);
    if ~record_context.is_real_if && isfield(obs,'power_dbv2') && numel(obs.power_dbv2)==2
        label=sprintf('%s\n功率差 %.3f dB',label,abs(diff(obs.power_dbv2)));
    end
    if ~contains(label,newline), label=[label newline]; else, label=[label ' · ']; end
    label=sprintf('%s%s · %s',label,source_labels.(record_source),daily_role_label(row.role));
else
    parts=splitlines(string(label)); label=char(join(parts(1:min(2,numel(parts))),newline));
end
set(state.home.h_metrics,'String',label,'TooltipString',full_label); setappdata(fig,'rx_workbench_state',state); redraw_current(fig);
end

function label=daily_role_label(role)
switch role
    case {'trial','试采'}, label='试采';
    case {'formal','正式'}, label='正式测量';
    case 'range_trial', label='量程试采';
    case 'balance', label='配平';
    case 'balance_confirmation', label='配平确认';
    case 'cancelled', label='已停止';
    case 'failed', label='失败排查';
    otherwise, label=role;
end
end

function [ready,why]=daily_ready(state,balance)
ready=false; why='';
try
    assert(isempty(state.scope_restore_pending),'RX_Workbench:ScopeRestore','示波器设置正在恢复');
    [blocked,why]=msiq.rx_input_state('blocked',[state.home.hardware_edits state.home.extended_edits]);
    assert(~blocked,'RX_Workbench:Draft',why);
    assert(isempty(state.pending) && isempty(state.control_pending) && ...
        ~(state.busy && ismember(field_or(state.worker_request,'action',''),{'setting','control'})), ...
        'RX_Workbench:ScopePending','示波器设置正在下发或等待回读，请稍后开始测试');
    assert(state.connected,'RX_Workbench:Gate','请先开始观察');
    assert(state.asynchronous,'RX_Workbench:Gate','测试使用后台进程；此界面为同步离线验证');
    assert(~isempty(state.measurement_position),'RX_Workbench:Position','请先选择测量位置');
    if balance
        assert(any(strcmp(state.measurement_position,{'rx_if','rx_if_thz'})),'RX_Workbench:BalancePosition','自动配平仅用于中频下变频输出');
        check_simulation_subband(state);
    end
    channels=selected_channels(state); demod=get(state.home.h_demod,'Value') || balance;
    if demod
        context=measurement_context(state);
        assert(numel(channels)==1+~context.is_real_if,'RX_Workbench:Gate','实际通道数量与测量位置不符');
        assert(~isempty(state.reference_bundle) || ~isempty(state.reference_path),'RX_Workbench:Gate','请选择发送参考');
    end
    profile=state.if_profile; profile.board=state.home.board.getConfig(); profile.subband=state.home.board.getSelection();
    options=struct('capture_then_demod',logical(demod),'measurement_context',measurement_context(state));
    task=msiq.RxDailyTask(0,options,profile,channels,1,balance,state.home.board.getSnapshot()); %#ok<NASGU>
    ready=true; why='可以开始测试';
catch exception, why=exception.message; end
end
function choose_daily_reference(fig)
state=getappdata(fig,'rx_workbench_state'); if task_active(state), return; end
[file,path]=uigetfile({'*.mat','发送参考 (*.mat)'},'选择发送参考',state.cfg.project_root);
if isequal(file,0), return; end
state.reference_path=fullfile(path,file); state.reference_manual=true; state.reference_info=struct(); state.reference_pending=true; state.reference_bundle='';
state.real_if_reference=struct(); state.real_if_reference_path='';
state=invalidate_measurement(state,'发送参考已更新，等待新采集');
setappdata(fig,'rx_workbench_state',state); tick_reference(fig); update_buttons(fig);
end
function load_daily_profile(fig)
state=getappdata(fig,'rx_workbench_state'); if task_active(state), return; end
existing=getappdata(fig,'rx_capture_settings_window');
if ~isempty(existing) && isgraphics(existing), figure(existing); return; end
options=struct('source_mode',ternary(state.offline_test,'simulation','live'), ...
    'preferences_path',state.capture_settings_path,'onSave',@(p)apply_capture_settings(fig,p,state.source_epoch), ...
    'validateSave',@()validate_capture_settings_save(fig,state.source_epoch),'balance_applicable',board_applicable(state));
window=msiq.rx_capture_settings_dialog(fig,state.if_profile,options);
setappdata(fig,'rx_capture_settings_window',window);
end
function validate_capture_settings_save(fig,source_epoch)
assert(isgraphics(fig),'RX_Workbench:SettingsClosed','工作台已关闭');
state=getappdata(fig,'rx_workbench_state');
assert(~task_active(state) && state.source_epoch==source_epoch && isempty(state.source_switch), ...
    'RX_Workbench:SettingsBusy','任务或数据来源已变化，请重新打开采集设置');
end
function apply_capture_settings(fig,profile,source_epoch)
if ~isgraphics(fig), return; end
state=getappdata(fig,'rx_workbench_state');
assert(~task_active(state) && state.source_epoch==source_epoch,'RX_Workbench:SettingsBusy','任务或数据来源已变化，请重新打开采集设置');
state.if_profile=profile;
state.if_profile.scope.range_strategy='computed';
state=invalidate_measurement(state,'采集设置已更新，等待新波形');
setappdata(fig,'rx_workbench_state',state); update_buttons(fig);
set_status(fig,'采集设置已保存；未修改示波器');
end
function show_range_hint(state)
if ~isfield(state.home,'h_range_hint'), return; end
cache=state.observation_cache;
label='量程：等待新波形'; color=[.32 .35 .39];
if isfield(cache,'decision') && cache.measurement_revision==state.measurement_revision && ~state.raw_stale
    d=cache.decision;
    if ~d.valid, label=['量程：' d.reason]; color=[.75 .18 .12];
    elseif d.needs_adjustment
        label=['量程需调整：' d.reason]; color=[.75 .18 .12];
    else, label='量程合适'; end
end
set_single_line(state.home.h_range_hint,label); set(state.home.h_range_hint,'ForegroundColor',color);
end
function set_single_line(handle,text)
set(handle,'String',text,'TooltipString',text);
rect=get(handle,'Position'); extent=get(handle,'Extent'); short=char(string(text));
while extent(3)>rect(3)-4 && numel(short)>4
    short=short(1:end-1); set(handle,'String',[short '…']); extent=get(handle,'Extent');
end
end

function restore_auto_reference(fig)
state=getappdata(fig,'rx_workbench_state'); if task_active(state), return; end
state.reference_manual=false; state.reference_path=''; state.reference_bundle='';
state.reference_info=struct(); state.real_if_reference=struct(); state.real_if_reference_path='';
state.find_reference=true; state.reference_checked_at=-Inf; state.reference_link_key='';
state=invalidate_measurement(state,'已恢复自动关联，等待新数据');
if state.native_simulation
    state.find_reference=false; state.reference_pending=false;
    if isfield(state.simulation_source,'reference_path')
        state.reference_path=state.simulation_source.reference_path;
        state.reference_pending=true;
    end
end
setappdata(fig,'rx_workbench_state',state); refresh_reference_label(state);
tick_reference(fig); update_buttons(fig);
end
function refresh_reference_label(state)
if ~isfield(state.home,'h_reference_info'), return; end
if strcmp(state.source_mode,'simulation')
    label='参考已自动生成';if isempty(state.reference_bundle),label='参考随模拟信号自动生成';end
    set(state.home.h_reference_info,'String',label,'TooltipString',state.reference_bundle);return;
end
mode=ternary(state.reference_manual,'手动','自动');
if ~isempty(state.reference_bundle)
    label=['发送参考：' mode '关联'];
    link=field_or(state.reference_info,'reference_link',struct()); rec=field_or(link,'record',struct());
    stamp=field_or(rec,'updated_at','');
    if ~isempty(stamp), label=[label ' · ' char(string(stamp))]; end
    info=field_or(state.reference_info,'real_if_reference',struct());
    if isfield(info,'symbol_rate_hz'), label=sprintf('%s\n%.4g GBd',label,info.symbol_rate_hz/1e9); end
    detail=[state.reference_bundle '；发送记录，不是 AWG 当前回读'];
else
    why=field_or(state.reference_info,'error','尚未关联');
    if isempty(why), why='尚未关联'; end
    label=['发送参考：' why]; detail=label;
end
set(state.home.h_reference_info,'String',label,'TooltipString',detail);
end

function opts=reference_options(state)
opts=struct('source',ternary(state.offline_test,'simulation','real'), ...
    'store_path',state.options.reference_link_store_path);
end
function state=poll_reference_link(fig,state,force)
if state.reference_manual || state.native_simulation || ~state.find_reference || state.reference_busy, return; end
if ~force && (now-state.reference_checked_at)*86400<2, return; end
state.reference_checked_at=now;
link=msiq.tx_reference_link('read_metadata',state.cfg.project_root,reference_options(state));
key=[link.path '|' link.hash '|' link.reason];
if ~strcmp(key,state.reference_link_key)
    had_reference=~isempty(state.reference_bundle);
    state.reference_link_key=key; state.reference_path=''; state.reference_bundle='';
    state.real_if_reference=struct(); state.real_if_reference_path='';
    if had_reference, state=invalidate_measurement(state,'发送记录已变化，等待重新关联'); end
    state.reference_info=struct('error',link.reason,'reference_link',link);
    state.reference_pending=link.valid;
end
setappdata(fig,'rx_workbench_state',state); refresh_reference_label(state);
end

function close_capture_settings(fig)
if ~isgraphics(fig), return; end
window=getappdata(fig,'rx_capture_settings_window');
if ~isempty(window) && isgraphics(window), delete(window); end
setappdata(fig,'rx_capture_settings_window',[]);
end

function scroll_scope_controls(fig)
state=getappdata(fig,'rx_workbench_state'); slider=state.home.scroll;
offset=state.home.content_height-2420; set(slider,'Value',max(0,get(slider,'Max')-offset));
layout_scroll_content(state.home,fig); set_page(fig,'home');
end

function choices=source_options(options)
% Never carry injected I/O, mock approvals, references or config across sources.
choices=struct(); choices.(options.source_mode)=options;
other=ternary(strcmp(options.source_mode,'simulation'),'measurement','simulation');
next=struct('source_mode',other,'visible',options.visible,'maximize',options.maximize, ...
    'position',options.position,'auto_connect',false,'use_timer',options.use_timer, ...
    'refresh_period_s',options.refresh_period_s,'simulation',options.simulation);
if strcmp(other,'measurement'), next=merge_struct(next,options.measurement_options); next.source_mode='measurement'; end
choices.(other)=app_options(next);
end

function request_source_switch(fig,target)
close_capture_settings(fig);
state=getappdata(fig,'rx_workbench_state');
if strcmp(state.source_mode,target), update_buttons(fig); return; end
locked=~isempty(state.scope_restore_pending) || state.running || state.busy || state.reference_busy || task_active(state) || state.simulation_preparing || ...
    ~isempty(state.pending) || ~isempty(state.control_pending) || ~isempty(state.board_pending) || state.close_requested;
if locked || ~isempty(state.source_switch)
    set_status(fig,'请先暂停观察，并等待当前操作完成后切换来源'); update_buttons(fig); return;
end
save_view(fig); state=getappdata(fig,'rx_workbench_state');
state.source_switch=target; state.source_release_error=''; state.running=false;
setappdata(fig,'rx_workbench_state',state); update_buttons(fig);
set_status(fig,'正在释放当前来源的后台会话');
tick_source_switch(fig);
end

function tick_source_switch(fig)
state=getappdata(fig,'rx_workbench_state');
if isempty(state.source_switch), return; end
workers={state.worker,state.reference_worker};
try
    for k=1:numel(workers)
        if ~isempty(workers{k}), workers{k}.close(); end
    end
    for k=1:numel(workers)
        if isempty(workers{k}), continue; end
        if ~workers{k}.process.HasExited, return; end
        assert(workers{k}.process.ExitCode==0,'RX_Workbench:SourceRelease','旧来源后台异常退出，释放状态未确认');
        evidence=workers{k}.release_status();
        assert(evidence.ok,'RX_Workbench:SourceRelease','旧来源连接释放失败：%s',strjoin(cellstr(string(evidence.errors)),'；'));
    end
    if ~isempty(state.session), state.io.close(state.session); end
catch exception
    state.source_release_error=exception.message; state.source_switch='';
    state.connected=false; state.running=false;
    setappdata(fig,'rx_workbench_state',state); update_buttons(fig);
    set_status(fig,['切换未完成 | ' exception.message]); return;
end
target=state.source_switch;
try
cache=getappdata(fig,'rx_source_states'); saved=struct();
keep={'cfg','channels','if_profile','capture_settings_path','reference_path','reference_bundle','reference_manual','reference_info','reference_link_key','reference_checked_at','find_reference', ...
    'plot_state','manual_band','band_source','preferences','preferences_path','second_enabled', ...
    'measurement_position','measurement_subband','measurement_routes','measurement_second_enabled','channel_selection_explicit','measurement_revision','real_if_reference','real_if_reference_path', ...
    'scope_presets_options','all_daily_rows','results','task_sequence','last_task_summary','simulation','simulation_source','worker_options'};
for k=1:numel(keep), if isfield(state,keep{k}), saved.(keep{k})=state.(keep{k}); end; end
saved.board_config=state.home.board.getConfig(); saved.board_draft=state.home.board.getDraft();
saved.controls=struct('demod',get(state.home.h_demod,'Value'),'ldpc',get(state.home.h_ldpc,'Value'), ...
    'count',get(state.home.h_count,'String'),'subband',state.home.board.getSelection());
cache.(state.source_mode)=saved;
choices=getappdata(fig,'rx_source_options'); opts=choices.(target);
next=initial_state(msiq.rx_workbench_config(opts),fig,opts);
if isfield(cache,target)
    restored=cache.(target); fields=fieldnames(restored);
    for k=1:numel(fields), if ~ismember(fields{k},{'controls','board_draft'}), next.(fields{k})=restored.(fields{k}); end; end
    next.board_draft=restored.board_draft;
end
next.timer=state.timer; next.source_epoch=state.source_epoch+1;
next.startup_pending=false; next.close_requested=false; next.source_switch=''; next.source_release_error='';
next.home=build_home(fig,next); next.pages=build_pages(fig);
bind=getappdata(fig,'rx_source_bind'); bind(next);
if isfield(cache,target)
    settings=cache.(target).controls;
    set(next.home.h_demod,'Value',settings.demod); set(next.home.h_ldpc,'Value',settings.ldpc); set(next.home.h_count,'String',settings.count);
    next.home.board.setSelection(settings.subband);
end
if ~next.second_enabled, set(next.home.h_ch2,'Value',5); end
rows=field_or(next,'all_daily_rows',{});
if ~isempty(rows)
    labels=arrayfun(@(k)daily_history_label(rows{k},k),1:numel(rows),'UniformOutput',false);
    set(next.home.h_history,'String',labels,'Value',numel(rows)); setappdata(next.home.h_history,'records',rows);
end
state.home.board.close(); delete(state.home.panel); delete([state.pages.single state.pages.repeat state.pages.result]);
setappdata(fig,'rx_source_states',cache); setappdata(fig,'rx_workbench_state',next);
layout_home(next.home,fig); sync_display_controls(next,true); sync_controls(next,true);
msiq.plotting.rx_live_dashboard(next.home.axes,struct(),struct(),struct(),struct());
set([next.home.h_wave_info next.home.h_spectrum_info],'String','等待当前来源采集');
set(next.home.h_metrics,'String','尚未取得当前来源的新采集指标');
update_buttons(fig); update_task_result(fig,false); set_status(fig,'来源已切换 · 点击开始观察');
catch exception
    state.source_switch=''; state.connected=false; state.running=false; state.source_release_error=exception.message;
    setappdata(fig,'rx_workbench_state',state); update_buttons(fig); set_status(fig,['切换未完成 | ' exception.message]);
end
end

function prepare_simulation(fig)
state=getappdata(fig,'rx_workbench_state');
if ~state.native_simulation || state.simulation_preparing || state.reference_busy || ~isempty(state.source_switch), return; end
try
    if isempty(state.reference_worker) || state.reference_worker.process.HasExited
        state.reference_worker=msiq.RxScopeWorker(struct(),'',struct(),'reference');
    end
    request=struct('action','prepare_simulation','simulation',state.simulation,'project_root',state.cfg.project_root,'timeout_s',900);
    request.source_epoch=state.source_epoch; state.reference_worker.submit(request); state.reference_request=request;
    state.reference_busy=true; state.simulation_preparing=true;
    setappdata(fig,'rx_workbench_state',state); update_buttons(fig); set_status(fig,'正在准备模拟波形和发送参考');
catch exception
    state.running=false; state.simulation_preparing=false;
    setappdata(fig,'rx_workbench_state',state); update_buttons(fig); set_status(fig,['模拟准备失败 | ' exception.message]);
end
end

function accept_simulation_source(fig,response)
state=getappdata(fig,'rx_workbench_state'); state.simulation_preparing=false;
if ~response.ok
    state.running=false; pending=state.board_pending; state.board_pending={};
    setappdata(fig,'rx_workbench_state',state);
    for k=1:numel(pending), pending{k}.completion(struct('ok',false,'error',field_or(response,'error','模拟准备失败'))); end
    update_buttons(fig); set_status(fig,['模拟准备失败 | ' field_or(response,'error','未取得模拟数据')]); return;
end
source=response.simulation_source;
results_root=state.cfg.results_root; state.cfg=source.cfg;
state.cfg.results_root=results_root; state.cfg.results.root=results_root;
source.cfg=state.cfg; state.simulation_source=source;
state.reference_manual=false;
state.reference_path=source.reference_path; state.reference_bundle=source.reference_path;
state.real_if_reference=source.cfg.waveform; state.real_if_reference.reference_identity=source.reference_sha256; state.real_if_reference_path=source.reference_path;
state.reference_info=struct('reference_identity',source.reference_sha256,'real_if_reference',state.real_if_reference);
state.worker_options.simulation_source=source;
if isfield(source,'if_profile')
    state.if_profile=msiq.rx_capture_settings('normalize',source.if_profile,state.if_profile,struct('source_mode','simulation'));
    state.if_profile.scope.range_strategy='computed';
end
if ~state.manual_band
    state.plot_state.bandwidth_hz=source.cfg.waveform.symbol_rate_hz*(1+source.cfg.waveform.rolloff);
    state.band_source='模拟发送参考统计频段';
end
setappdata(fig,'rx_workbench_state',state); refresh_reference_label(state); sync_display_controls(state,true); update_buttons(fig);
if state.running, connect_scope(fig); else, tick_daily_task(fig); end
end

function board_selection_changed(fig,~,src,~)
state=getappdata(fig,'rx_workbench_state');
value=get(src,'Value');
if ~board_applicable(state)
    state.home.board.setSelection(state.measurement_subband);
    record_board_rejection(fig,'board_selection','当前测量位置不能操作 RX 中频板卡'); return;
end
measurement_changed(fig,'',value);
state=getappdata(fig,'rx_workbench_state'); state.home.board.setSelection(state.measurement_subband);
end
function check_simulation_subband(state)
if ~state.native_simulation || ~isempty(state.measurement_position), return; end
band=field_or(state.simulation,'subband',1);
assert(state.home.board.getSelection()==band,'RX_Workbench:SimulationSubband', ...
    '当前模拟信号位于子带 %d，请选择对应子带',band);
end

function context=measurement_context(state)
context=msiq.rx_measurement_context(state.measurement_position,state.measurement_subband);
end

function sync_measurement_controls(state)
context=measurement_context(state);
set(state.home.subband_group,'Visible',ternary(strcmp(state.measurement_position,'awg_direct'),'off','on'));
state.home.board.setApplicable(board_applicable(state),'当前测量位置不能操作 RX 中频板卡');
if context.is_real_if
    set(state.home.h_if_center,'String',sprintf('中心频率 %.1f GHz',context.center_freq_hz/1e9),'Visible','on');
    if ~isfield(state.raw,'channels')
        set(state.home.h_wave_title(2),'String','数字 I 频谱'); set(state.home.h_spectrum_title(2),'String','数字 Q 频谱');
    end
else
    set(state.home.h_if_center,'String','','Visible','off');
end
end

function measurement_changed(fig,position,subband)
state=getappdata(fig,'rx_workbench_state');
if measurement_locked(state)
    restore_measurement_selection(state); set_status(fig,'当前操作尚未完成，不能切换测量选择'); return;
end
[blocked,why]=msiq.rx_input_state('blocked',[state.home.hardware_edits state.home.extended_edits]);
if blocked
    restore_measurement_selection(state);
    set_status(fig,['切换前：' why]); return;
end
if ~isempty(subband) && strcmp(state.measurement_position,'awg_direct'), restore_measurement_selection(state); return; end
if (isempty(position) || strcmp(position,state.measurement_position)) && ...
        (isempty(subband) || subband==state.measurement_subband), return; end
if ~isempty(position)
    if ~isempty(state.measurement_position)
        state.measurement_routes.(state.measurement_position)=state.channels;
        state.measurement_second_enabled.(state.measurement_position)=state.second_enabled;
    else
        for id={'awg_direct','rx_if','rx_if_thz'}
            state.measurement_routes.(id{1})=state.channels;
            state.measurement_second_enabled.(id{1})=state.second_enabled;
        end
    end
    state.measurement_position=position;
    realIF=any(strcmp(position,{'tx_if','thz_if'}));
    if isfield(state.measurement_routes,position)
        state.channels=state.measurement_routes.(position);
    elseif realIF
        if ~state.channel_selection_explicit, state.channels={'C2','C4'}; end
    else
        state.channels=state.preferences.channels;
        if isempty(state.channels), state.channels={'C3','C4'}; end
    end
    state.second_enabled=~realIF;
    if ~realIF && isfield(state.measurement_second_enabled,position)
        state.second_enabled=state.measurement_second_enabled.(position);
    end
    set(state.home.h_ch1,'Value',str2double(state.channels{1}(2)));
    set(state.home.h_ch2,'Value',ternary(~state.second_enabled,5,str2double(state.channels{2}(2))));
end
if ~isempty(subband), state.measurement_subband=subband; end
state.home.board.setSelection(state.measurement_subband);
state=invalidate_measurement(state,'测量选择已更新，等待新采集');
setappdata(fig,'rx_workbench_state',state);
sync_display_controls(state,true); sync_measurement_controls(state); sync_controls(state,true);
msiq.plotting.rx_live_dashboard(state.home.axes,struct(),struct(),struct(),struct());
set([state.home.h_wave_info state.home.h_spectrum_info],'String','等待本测量位置的新采集');
sync_measurement_controls(state);
save_view(fig); update_buttons(fig); set_status(fig,'测量选择已更新；未更改仪器设置');
end

function yes=board_applicable(state)
yes=ismember(state.measurement_position,{'rx_if','rx_if_thz'});
end
function yes=measurement_locked(state)
if ~isempty(state.scope_restore_pending),yes=true;return;end
yes=task_active(state) || state.busy || state.reference_busy || ~isempty(state.pending) || ...
    ~isempty(state.control_pending) || ~isempty(state.board_pending) || state.close_requested || ...
    ~isempty(state.source_switch) || state.home.board.isBusy();
end
function restore_measurement_selection(state)
set(state.home.position_group,'SelectedObject',[]);
for h=state.home.position_buttons
    if strcmp(get(h,'Tag'),state.measurement_position), set(state.home.position_group,'SelectedObject',h); end
end
set(state.home.subband_group,'SelectedObject',state.home.subband_buttons(state.measurement_subband));
end
function state=invalidate_measurement(state,reason)
state.measurement_revision=state.measurement_revision+1;
state.raw=struct(); state.raw_scope_status=struct(); state.first_capture_complete=false;
state.raw_stale=true; state.stale_reason=reason;
state.observation_cache=struct();
if isfield(state.home,'h_range_hint'), set(state.home.h_range_hint,'String','量程：等待新波形'); end
state.reference_pending=~isempty(state.reference_path) || state.find_reference;
set(state.home.h_metrics,'String','尚未取得当前设置的解调指标','TooltipString','');
set(state.home.h_history,'TooltipString','历史记录；选择后查看该次测量');
msiq.plotting.rx_live_dashboard(state.home.axes,struct(),struct(),struct(),struct());
set([state.home.h_wave_info state.home.h_spectrum_info],'String',reason,'TooltipString',reason);
end
function record_board_rejection(fig,action,reason)
if ~isgraphics(fig), return; end
state=getappdata(fig,'rx_workbench_state');
entry=struct('action',action,'reason',reason,'measurement_position',state.measurement_position, ...
    'measurement_revision',state.measurement_revision,'time',char(datetime('now')));
history=getappdata(fig,'rx_board_rejections'); if isempty(history), history={}; end
history{end+1}=entry; setappdata(fig,'rx_board_rejections',history);
set_status(fig,reason);
end

function label=daily_history_label(row,index)
context=msiq.rx_measurement_context(field_or(row.capture,'measurement_context',struct()));
short=struct('awg_direct','AWG直连','tx_if','中频上变频','thz_if','太赫兹下变频', ...
    'rx_if','中频下变频·未经过太赫兹','rx_if_thz','中频下变频·已经过太赫兹');
position='位置未记录';
if ~isempty(context.position), position=short.(context.position); end
if isfield(context,'subband'), position=sprintf('%s·子带%d',position,context.subband); end
label=sprintf('%03d · %s · %s',index,daily_role_label(row.role),position);
end

function yes=scope_controls_locked(state)
% A window created before a source update must still be able to release its
% sessions through CloseRequestFcn; it has no restore operation in flight.
yes=task_active(state)||~isempty(field_or(state,'scope_restore_pending',[]));
end
function [ready,why]=scope_restore_ready(state)
ready=false;why='';
if ~state.connected,why='请先连接示波器';return;end
if isempty(state.scope_preset),why=state.scope_preset_error;if isempty(why),why='尚无已保存的设置';end;return;end
if scope_controls_locked(state)||~isempty(state.pending)||~isempty(state.control_pending)||~isempty(state.board_pending)
    why='请等待当前任务或控制完成';return;
end
if state.busy&&~strcmp(field_or(state.worker_request,'action',''),'capture'),why='请等待回读完成';return;end
[blocked,why]=msiq.rx_input_state('blocked',[state.home.hardware_edits state.home.extended_edits]);
if blocked,return;end
channels=selected_channels(state);
if ~all(ismember(channels,state.scope_preset.channels)),why='保存记录缺少当前通道';return;end
ready=true;why='恢复本机保存的常用实验设置';
if ~isempty(state.scope_preset_error),why=state.scope_preset_error;end
end
function scope_connected(fig)
state=getappdata(fig,'rx_workbench_state');state.scope_preset=[];state.scope_preset_error='';
try
    snapshot=msiq.rx_scope_snapshot(state.scope_status,selected_channels(state));
    state.scope_preset=msiq.rx_scope_presets('load',state.cfg.project_root,state.source_mode,snapshot,state.scope_presets_options);
catch ex,state.scope_preset_error=['设置未加载：' ex.message];end
restore=strcmp(state.source_mode,'simulation')&&~state.scope_auto_restored&&~isempty(state.scope_preset);
state.scope_auto_restored=true;setappdata(fig,'rx_workbench_state',state);
if restore,request_scope_restore(fig,true);end
end
function save_manual_scope(fig,request)
state=getappdata(fig,'rx_workbench_state');
if isfield(state.scope_presets_options,'store_path')&&isempty(state.scope_presets_options.store_path),return;end
if ~strcmp(field_or(request,'origin',''),'manual')|| ...
        field_or(request,'selection_revision',-1)~=state.measurement_revision|| ...
        ~isempty(state.scope_restore_pending)||task_active(state),return;end
try
    snapshot=msiq.rx_scope_snapshot(state.scope_status,selected_channels(state));
    key=field_or(request,'key',field_or(request,'command',''));
    item=find(strcmp({snapshot.fields.key},key),1);
    assert(~isempty(item),'RX_Workbench:Preset','完整回读中缺少已提交参数');
    actual=snapshot.fields(item).value;
    if isnumeric(actual)&&isnumeric(request.value)
        equal=abs(actual-request.value)<=32*eps(max([abs(actual) abs(request.value) realmin]));
    else,equal=isequal(actual,request.value);end
    assert(equal,'RX_Workbench:Preset','完整回读与请求不一致');
    opts=state.scope_presets_options;opts.keys={key};
    if isfield(request,'before_status')
        before=msiq.rx_scope_snapshot(request.before_status,selected_channels(state));
        dependencies={};
        if ismember(key,{'TDIV','MSIZ','SAMPLEMODE'}),dependencies={'TDIV','MSIZ','SAMPLEMODE','TRDL'};
        elseif strcmp(key,'TRSOURCE'),dependencies={'TRLEVEL','TRSLOPE'};
        elseif endsWith(key,':CPL'),dependencies={[key(1:2) ':VDIV'],[key(1:2) ':OFST']};
        elseif endsWith(key,':VDIV'),dependencies={[key(1:2) ':OFST']};end
        for k=1:numel(dependencies)
            name=dependencies{k};a=find(strcmp({before.fields.key},name),1);b=find(strcmp({snapshot.fields.key},name),1);
            if ~isempty(a)&&~isempty(b)&&~isequaln(before.fields(a).value,snapshot.fields(b).value)
                opts.keys{end+1}=name;
            end
        end
    end
    state.scope_preset=msiq.rx_scope_presets('save',state.cfg.project_root,state.source_mode,snapshot,opts);
    state.scope_preset_error='';
catch ex
    state.scope_preset_error=['设置未保存：' ex.message];
    set(request.handle,'TooltipString',state.scope_preset_error);
end
setappdata(fig,'rx_workbench_state',state);
end
function request_scope_restore(fig,automatic)
state=getappdata(fig,'rx_workbench_state');
[ready,why]=scope_restore_ready(state);
if ~ready,if ~automatic,set_status(fig,why);end;return;end
state.scope_restore_pending=state.scope_preset;state.scope_restore_resume=state.running;
state.task_sequence=state.task_sequence+1;state.scope_restore_id=state.task_sequence;state.scope_restore_cancelled=false;
state=invalidate_measurement(state,'正在恢复设置，等待新采集');state.last_task_summary='';
state.running=false;state.paused=true;
setappdata(fig,'rx_workbench_state',state);
set_status(fig,'正在恢复示波器设置');update_buttons(fig);drain_scope_restore(fig);
end
function drain_scope_restore(fig)
state=getappdata(fig,'rx_workbench_state');
if isempty(state.scope_restore_pending)||state.busy,return;end
if state.close_requested
    state.scope_restore_pending=[];setappdata(fig,'rx_workbench_state',state);return;
end
if state.asynchronous
    submit_worker(fig,struct('action','restore_settings','target',state.scope_restore_pending,'channels',{selected_channels(state)},'origin','restore','task_id',state.scope_restore_id,'timeout_s',state.options.scope_restore_timeout_s));
else
    state.busy=true;setappdata(fig,'rx_workbench_state',state);
    report=msiq.rx_scope_restore(state.session,state.scope_restore_pending,selected_channels(state),state.io,struct('check',@()check_scope_restore(fig)));
    state=getappdata(fig,'rx_workbench_state');state.busy=false;setappdata(fig,'rx_workbench_state',state);
    finish_scope_restore(fig,report);
end
end
function finish_scope_restore(fig,report)
state=getappdata(fig,'rx_workbench_state');
state.scope_restore_report=report;state.scope_restore_pending=[];
state.running=state.connected&&field_or(report,'ok',false)&&state.scope_restore_resume;state.paused=~state.running;
if ~isempty(fieldnames(field_or(report,'status',struct()))),state.scope_status=report.status;end
state=invalidate_measurement(state,'设置已改变，等待新采集');state.last_task_summary='';
state.scope_restore_resume=false;setappdata(fig,'rx_workbench_state',state);
sync_controls(state,true);redraw_current(fig);
if ~field_or(report,'ok',false)
    for control=[state.home.hardware_edits state.home.extended_edits]
        msiq.rx_input_state('known',control,false);
        set(control,'TooltipString','恢复未完成，当前设置等待重新回读');
    end
end
if field_or(report,'ok',false),set_status(fig,'已恢复设置');
else,set_status(fig,['恢复未完成 | ' strjoin(field_or(report,'errors',{'未确认'}),'；')]);end
update_buttons(fig);
end

function check_scope_restore(fig)
assert(isgraphics(fig),'RX_Workbench:Cancelled','窗口已关闭');
s=getappdata(fig,'rx_workbench_state');
assert(~s.scope_restore_cancelled&&~s.close_requested,'RX_Workbench:Cancelled','已停止恢复');
end
