function app = tx_workbench_app(options)
%TX_WORKBENCH_APP Interactive console for the traditional SC TX path.

if nargin < 1 || isempty(options), options = struct(); end
options = normalize_app_options(options);
set_chinese_font();
cfg = msiq.build_config('v2_traditional_wz');
fig = create_figure(options);
state = initial_state(fig, cfg, options);
setappdata(fig, 'tx_workbench_state', state);
build_ui(fig);
set(fig, 'CloseRequestFcn', @on_close, 'SizeChangedFcn', @on_resize, ...
    'WindowScrollWheelFcn', @on_scroll);
apply_parameters_to_controls(fig, state.params);
layout_ui(fig);
if options.visible, set(fig, 'Visible', 'on'); end
drawnow;
set_phase(fig, '界面已就绪');
if options.synchronous_startup
    startup_sequence([], []);
else
    schedule(fig, options.startup_delay_s, @startup_sequence);
end
if nargout > 0
    app = fig;
else
    uiwait(fig);
    app = [];
end

    function startup_sequence(~, ~)
        if ~ishghandle(fig), return; end
        if options.startup_preview, regenerate_preview(fig); end
        if ishghandle(fig) && options.auto_connect, refresh_awg_status(fig); end
    end

    function on_resize(~, ~)
        if ~ishghandle(fig), return; end
        layout_ui(fig);
        current = getappdata(fig, 'tx_workbench_state');
        if isstruct(current.plan) && isfield(current.plan, 'waveforms')
            render_preview(fig, current.plan);
        end
    end

    function on_scroll(~, event)
        if ~ishghandle(fig), return; end
        current = getappdata(fig, 'tx_workbench_state');
        if ~isfield(current.ui, 'scroll'), return; end
        pointer = get(fig, 'CurrentPoint');
        if isstruct(event) && isfield(event, 'PointerPosition')
            pointer = double(event.PointerPosition);
        end
        left_panel = get(current.ui.params_outer, 'Position');
        right_panel = get(current.ui.plan_panel, 'Position');
        if point_in_rectangle(pointer, left_panel)
            slider = current.ui.scroll;
            update_callback = @() update_scroll_position(fig);
        elseif point_in_rectangle(pointer, right_panel)
            slider = current.ui.plan_scroll;
            update_callback = @() update_plan_scroll_position(fig);
        else
            return;
        end
        maximum = get(slider, 'Max');
        offset = maximum-get(slider, 'Value');
        offset = offset + double(event.VerticalScrollCount)*44;
        set(slider, 'Value', maximum-min(max(offset, 0), maximum));
        update_callback();
    end

    function on_close(~, ~)
        if ~ishghandle(fig), return; end
        current = getappdata(fig, 'tx_workbench_state');
        save_local_parameters(current);
        stop_app_timer(fig, 'tx_workbench_timer');
        stop_app_timer(fig, 'tx_workbench_hardware_timer');
        delete(fig);
    end
end

function state = initial_state(fig, cfg, options)
defaults = default_parameters(cfg);
saved = upgrade_parameters(load_local_parameters(defaults, options), defaults);
params = upgrade_parameters(merge_struct(saved, options.initial_params), defaults);
signature = waveform_signature(params);
state = struct('figure', fig, 'cfg', cfg, 'connected', false, ...
    'busy', false, ...
    'awg_status', struct(), 'plan', struct(), 'plan_valid', false, ...
    'waveform_stale', true, 'waveform_signature', signature, ...
    'preview_signature', '', 'loaded_signature', '', ...
    'loaded_waveform_signature', '', 'loaded_route', '', ...
    'plan_route_stale', false, 'formal_plan_hash', '', ...
    'formal_plan_stale', true, 'hardware_snapshot', struct(), ...
    'hardware_dirty', false, 'hardware_dirty_fields', false(4,3), ...
    'hardware_errors', {cell(4,3)}, 'hardware_failed_request', struct(), ...
    'hardware_sync_state', 'disconnected', 'hardware_sync_error', '', ...
    'output_running', false, 'output_state', 'unknown', ...
    'last_run_dir', '', 'params', params, ...
    'defaults', defaults, 'rate_authority', params.rate_authority, ...
    'backend_options', options.backend_options, ...
    'confirmation_handler', options.confirmation_handler, ...
    'persist_parameters', options.persist_parameters, ...
    'parameter_record_path', options.parameter_record_path, ...
    'hardware_apply_delay_s', options.hardware_apply_delay_s, 'ui', struct());
end

function params = default_parameters(cfg)
w = cfg.waveform;
symbol_rate = w.master_sample_rate_hz/w.selected_up;
params = struct('route', 'pair_a_ch1_ch2', 'rdiv', 'DIV4', ...
    'amplitude_vpp', 0.2*ones(1,4), 'offset_v', zeros(1,4), ...
    'sample_clock_delay_samples', zeros(1,4), ...
    'invert_i', false, 'invert_q', false, 'modulation_order', 16, ...
    'master_sample_rate_hz', w.master_sample_rate_hz, ...
    'symbol_rate_hz', symbol_rate, ...
    'occupied_bandwidth_hz', symbol_rate*(1+w.rolloff), ...
    'rate_authority', 'symbol_rate', 'rolloff', w.rolloff, ...
    'rrc_span_symbols', 12, 'peak_scale', 1, ...
    'normalization_mode', 'pair_common_final_full_scale', ...
    'sync_length_symbols', 63, ...
    'sync_repeats', 4, 'training_symbols', 2048, ...
    'pilot_interval_symbols', 32, ...
    'guard_symbols', 64, ...
    'ldpc_blocks_per_frame', 1, ...
    'frame_repetitions', w.frame_repetitions, ...
    'seed', 26072701, 'note', '');
end

function params = upgrade_parameters(params, defaults)
original = params;
params = merge_struct(defaults, params);
if ~isfield(params, 'symbol_rate_hz') || ~isfinite_scalar(params.symbol_rate_hz)
    old_up = field_or(params, 'selected_up', defaults.master_sample_rate_hz / ...
        defaults.symbol_rate_hz);
    params.symbol_rate_hz = params.master_sample_rate_hz/double(old_up);
end
if ~isfield(params, 'occupied_bandwidth_hz') || ...
        ~isfinite_scalar(params.occupied_bandwidth_hz)
    params.occupied_bandwidth_hz = params.symbol_rate_hz*(1+params.rolloff);
end
hardware_names = {'amplitude_vpp','offset_v','sample_clock_delay_samples'};
for index = 1:numel(hardware_names)
    name = hardware_names{index};
    raw = field_or(original, name, []);
    if numel(raw) == 4 && all(isfinite(double(raw(:))))
        params.(name) = double(raw(:).');
    elseif numel(raw) == 2 && all(isfinite(double(raw(:))))
        migrated = defaults.(name);
        migrated(route_channels(field_or(original, 'route', defaults.route))) = ...
            double(raw(:).');
        params.(name) = migrated;
    else
        params.(name) = defaults.(name);
    end
end
if ~isfield(params, 'rate_authority') || ...
        ~ismember(char(string(params.rate_authority)), {'symbol_rate','bandwidth'})
    params.rate_authority = 'symbol_rate';
end
fixed_names = {'invert_i','invert_q','rrc_span_symbols','peak_scale', ...
    'normalization_mode','sync_length_symbols','sync_repeats', ...
    'training_symbols','pilot_interval_symbols','guard_symbols', ...
    'ldpc_blocks_per_frame','seed'};
for index = 1:numel(fixed_names)
    params.(fixed_names{index}) = defaults.(fixed_names{index});
end
end

function fig = create_figure(options)
fig = figure('Name', 'SC TX Workbench - 发射端工作台', ...
    'NumberTitle', 'off', 'MenuBar', 'none', 'ToolBar', 'none', ...
    'Color', [0.945 0.952 0.958], 'Resize', 'on', ...
    'Units', 'pixels', 'Visible', 'off', ...
    'DefaultUicontrolFontName', 'Microsoft YaHei UI', ...
    'DefaultAxesFontName', 'Microsoft YaHei UI', ...
    'DefaultTextFontName', 'Microsoft YaHei UI', 'Position', options.position);
set(fig, 'Renderer', 'painters'); %#ok<FGREN>
if options.maximize && options.visible
    try
        fig.WindowState = 'maximized';
    catch
    end
end
end

function options = normalize_app_options(options)
if ~isstruct(options) || ~isscalar(options)
    error('msiq:txWorkbench:Options', 'TX GUI options must be one scalar struct.');
end
options.auto_connect = logical_value(options, 'auto_connect', true);
options.startup_preview = logical_value(options, 'startup_preview', true);
options.visible = logical_value(options, 'visible', true);
options.maximize = logical_value(options, 'maximize', true);
options.synchronous_startup = logical_value(options, 'synchronous_startup', false);
options.startup_delay_s = numeric_value(options, 'startup_delay_s', 0.05);
options.hardware_apply_delay_s = numeric_value( ...
    options, 'hardware_apply_delay_s', 0.8);
options.persist_parameters = logical_value(options, 'persist_parameters', true);
options.parameter_record_path = char(string(field_or(options, ...
    'parameter_record_path', local_parameter_path())));
if isempty(strtrim(options.parameter_record_path))
    error('msiq:txWorkbench:Options', ...
        'parameter_record_path must be a nonempty path.');
end
options.position = double(field_or(options, 'position', [60 60 1500 900]));
options.position = options.position(:).';
if numel(options.position) ~= 4 || any(~isfinite(options.position)) || ...
        any(options.position(3:4) <= 0)
    error('msiq:txWorkbench:Options', 'position must be [x y width height].');
end
options.backend_options = field_or(options, 'backend_options', struct());
options.initial_params = field_or(options, 'initial_params', struct());
options.confirmation_handler = field_or(options, 'confirmation_handler', []);
if ~isstruct(options.backend_options) || ~isscalar(options.backend_options) || ...
        ~isstruct(options.initial_params) || ~isscalar(options.initial_params)
    error('msiq:txWorkbench:Options', ...
        'backend_options and initial_params must be scalar structs.');
end
if ~isempty(options.confirmation_handler) && ...
        ~isa(options.confirmation_handler, 'function_handle')
    error('msiq:txWorkbench:Options', ...
        'confirmation_handler must be a function handle.');
end
end

function build_ui(fig)
state = getappdata(fig, 'tx_workbench_state');
bg = [0.945 0.952 0.958]; panel_bg = [0.985 0.987 0.989];
state.ui.header = uipanel(fig, 'Units', 'pixels', 'BorderType', 'none', ...
    'BackgroundColor', [0.91 0.93 0.945]);
state.ui.body = uipanel(fig, 'Units', 'pixels', 'BorderType', 'none', ...
    'BackgroundColor', bg);
header_bg = get(state.ui.header, 'BackgroundColor');
state.ui.connection = uicontrol(state.ui.header, 'Style', 'text', ...
    'String', 'AWG 未连接', 'HorizontalAlignment', 'left', 'Units', 'pixels', ...
    'BackgroundColor', header_bg, 'FontWeight', 'bold', 'FontSize', 11, ...
    'ForegroundColor', [0.65 0.20 0.15]);
state.ui.phase = uicontrol(state.ui.header, 'Style', 'text', ...
    'String', '阶段：初始化', 'HorizontalAlignment', 'left', 'Units', 'pixels', ...
    'BackgroundColor', header_bg, 'FontSize', 10, 'Max', 2);
state.ui.reconnect = header_button(state.ui.header, '重新连接', ...
    @(~,~) refresh_awg_status(fig));
set(state.ui.reconnect, 'Visible', 'off');
state.ui.preview = header_button(state.ui.header, '更新预览', ...
    @(~,~) regenerate_preview(fig));
state.ui.download = header_button(state.ui.header, '下载并输出', ...
    @(~,~) download_and_output(fig));
set(state.ui.download, 'Enable', 'off', 'FontWeight', 'bold');
state.ui.output = header_button(state.ui.header, '开始输出', ...
    @(~,~) toggle_output(fig));
set(state.ui.output, 'Enable', 'off');
state.ui.preview_hint = uicontrol(state.ui.header, 'Style', 'text', ...
    'String', '', 'HorizontalAlignment', 'center', 'Units', 'pixels', ...
    'BackgroundColor', header_bg, 'ForegroundColor', [0.40 0.44 0.47], ...
    'FontSize', 8.5);
state.ui.download_hint = uicontrol(state.ui.header, 'Style', 'text', ...
    'String', 'AWG 未连接', 'HorizontalAlignment', 'center', 'Units', 'pixels', ...
    'BackgroundColor', header_bg, 'ForegroundColor', [0.40 0.44 0.47], ...
    'FontSize', 8.5);
state.ui.output_hint = uicontrol(state.ui.header, 'Style', 'text', ...
    'String', '没有匹配的已下载波形', 'HorizontalAlignment', 'center', ...
    'Units', 'pixels', 'BackgroundColor', header_bg, ...
    'ForegroundColor', [0.40 0.44 0.47], 'FontSize', 8.5);

state.ui.params_outer = uipanel(state.ui.body, 'Title', '发射参数', ...
    'Units', 'pixels', 'BackgroundColor', panel_bg, 'FontWeight', 'bold');
state.ui.params_view = uipanel(state.ui.params_outer, 'Units', 'pixels', ...
    'BorderType', 'none', 'BackgroundColor', panel_bg);
state.ui.param_content_height = 1600;
state.ui.param_content = uipanel(state.ui.params_view, 'Units', 'pixels', ...
    'BorderType', 'none', 'BackgroundColor', panel_bg);
state.ui.scroll = uicontrol(state.ui.params_outer, 'Style', 'slider', ...
    'Units', 'pixels', 'Min', 0, 'Max', 1, 'Value', 1, ...
    'Callback', @(~,~) update_scroll_position(fig));
state = build_parameter_controls(state, fig);
state = fit_parameter_content(state);
state.ui.dashboard_title = uicontrol(state.ui.body, 'Style', 'text', ...
    'Units', 'pixels', 'String', 'SC 发射波形检测', ...
    'HorizontalAlignment', 'center', 'BackgroundColor', bg, ...
    'FontWeight', 'bold', 'FontSize', 12);
state.ui.axes = gobjects(1, 4);
for k = 1:4
    state.ui.axes(k) = axes('Parent', state.ui.body, 'Units', 'pixels', ...
        'Box', 'on', 'Color', [1 1 1], 'FontName', 'Microsoft YaHei UI', ...
        'FontSize', 8.5, 'Visible', 'on', ...
        'PositionConstraint', 'innerposition');
end
state.ui.plan_panel = uipanel(state.ui.body, 'Title', 'AWG 与下载', ...
    'Units', 'pixels', 'BackgroundColor', panel_bg, 'FontWeight', 'bold');
state.ui.plan_view = uipanel(state.ui.plan_panel, 'Units', 'pixels', ...
    'BorderType', 'none', 'BackgroundColor', panel_bg);
state.ui.plan_content = uipanel(state.ui.plan_view, 'Units', 'pixels', ...
    'BorderType', 'none', 'BackgroundColor', panel_bg);
state.ui.plan_scroll = uicontrol(state.ui.plan_panel, 'Style', 'slider', ...
    'Units', 'pixels', 'Min', 0, 'Max', 1, 'Value', 1, ...
    'Callback', @(~,~) update_plan_scroll_position(fig));
[state.ui.plan_awg_header, state.ui.plan_awg_labels, ...
    state.ui.plan_awg] = plan_section(state.ui.plan_content, 'AWG 当前', 8, false);
[state.ui.plan_capacity_header, state.ui.plan_capacity_labels, ...
    state.ui.plan_capacity] = plan_section(state.ui.plan_content, '下载准备', 8, true);
[state.ui.plan_changes_header, state.ui.plan_changes_labels, ...
    state.ui.plan_changes] = plan_section(state.ui.plan_content, '设备改动', 8, false);
[state.ui.plan_fixed_header, state.ui.plan_fixed_labels, ...
    state.ui.plan_fixed] = plan_section(state.ui.plan_content, '固定设计', 8, false);
setappdata(fig, 'tx_workbench_state', state);
render_plan(fig);
end

function state = build_parameter_controls(state, fig)
parent = state.ui.param_content; width = 282;
y = state.ui.param_content_height - 32;
[~, y] = section_header(parent, 'AWG 输出', y, width);
[~, state.ui.route, y] = popup_row(parent, '下载通道', ...
    {'CH1 / CH2','CH3 / CH4'}, 1, y, width, ...
    @(src,evt) on_route_change(fig, src, evt));
state.ui.route_values = {'pair_a_ch1_ch2','pair_b_ch3_ch4'};
[~, state.ui.rdiv, y] = popup_row(parent, '目标 RDIV', {'DIV2','DIV4'}, 2, y, width, ...
    @(src,evt) on_waveform_change(fig, src, evt, 'rdiv'));
caption_x = [8 96 175 252]; caption_w = [80 70 70 26];
caption_text = {'参数','AWG 当前','目标','单位'};
state.ui.hardware_caption = gobjects(1,4);
for caption_index = 1:4
    alignment = 'left';
    if caption_index == 2 || caption_index == 3, alignment = 'right'; end
    state.ui.hardware_caption(caption_index) = uicontrol(parent, ...
        'Style', 'text', 'Units', 'pixels', ...
        'String', caption_text{caption_index}, ...
        'HorizontalAlignment', alignment, 'FontWeight', 'bold', ...
        'ForegroundColor', [0.32 0.36 0.39], ...
        'BackgroundColor', get(parent, 'BackgroundColor'), ...
        'Position', [caption_x(caption_index) y caption_w(caption_index) 22]);
end
y = y - 29;
state.ui.channel_heading = gobjects(1,2);
state.ui.channel_sync = gobjects(1,2);
state.ui.current_vpp = gobjects(1,2); state.ui.current_offset = gobjects(1,2);
state.ui.current_sdel = gobjects(1,2); state.ui.target_vpp = gobjects(1,2);
state.ui.target_offset = gobjects(1,2); state.ui.target_sdel = gobjects(1,2);
state.ui.current_delay_ps = gobjects(1,2); state.ui.target_delay_ps = gobjects(1,2);
for k = 1:2
    heading_y = y;
    [state.ui.channel_heading(k), y] = minor_header(parent, ...
        sprintf('CH%d · %s', k, char('I'+k-1)), y, width);
    state.ui.channel_sync(k) = uicontrol(parent, 'Style', 'text', ...
        'Units', 'pixels', 'String', '未连接', 'HorizontalAlignment', 'right', ...
        'FontWeight', 'bold', 'ForegroundColor', [0.42 0.45 0.47], ...
        'BackgroundColor', get(parent, 'BackgroundColor'), ...
        'Position', [168 heading_y 100 22]);
    [state.ui.current_vpp(k), state.ui.target_vpp(k), y] = ...
        hardware_row(parent, 'Vpp', 'V', y, ...
        @(src,evt) on_hardware_change(fig, src, evt, k, 'amplitude_vpp'));
    [state.ui.current_offset(k), state.ui.target_offset(k), y] = ...
        hardware_row(parent, 'Offset', 'V', y, ...
        @(src,evt) on_hardware_change(fig, src, evt, k, 'offset_v'));
    [state.ui.current_sdel(k), state.ui.target_sdel(k), y] = ...
        hardware_row(parent, '采样时钟延时', '点', y, ...
        @(src,evt) on_hardware_change(fig, src, evt, k, ...
        'sample_clock_delay_samples'));
    [state.ui.current_delay_ps(k), state.ui.target_delay_ps(k), y] = ...
        hardware_readonly_row(parent, '延时时长', 'ps', y);
end
[state.ui.current_relative_delay, state.ui.target_relative_delay, y] = ...
    hardware_readonly_row(parent, '相对延时 Q-I', '点', y);
state.ui.hardware_summary = uicontrol(parent, 'Style', 'text', ...
    'Units', 'pixels', 'String', '修改后自动写入 AWG', ...
    'HorizontalAlignment', 'left', 'ForegroundColor', [0.20 0.38 0.52], ...
    'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [8 y 174 25]);
state.ui.retry_settings = uicontrol(parent, 'Style', 'pushbutton', ...
    'Units', 'pixels', 'String', '重试', 'Position', [190 y 78 27], ...
    'Visible', 'off', 'Callback', @(~,~) retry_channel_settings(fig));
y = y - 37;

[~, y] = section_header(parent, '波形与速率', y, width);
[~, state.ui.modulation, y] = popup_row(parent, '调制方式', ...
    {'QPSK','16QAM','64QAM'}, 2, y, width, ...
    @(src,evt) on_waveform_change(fig, src, evt, 'modulation_order'));
[~, state.ui.master_rate, y] = edit_row_unit(parent, '目标 DAC 采样率', '65', ...
    'GSa/s', y, width, @(src,evt) on_waveform_change(fig, src, evt, 'master_sample_rate_hz'));
[~, state.ui.symbol_rate, y] = edit_row_unit(parent, '符号率', '--', ...
    'GBd', y, width, @(src,evt) on_waveform_change(fig, src, evt, 'symbol_rate_hz'));
[~, state.ui.bandwidth, y] = edit_row_unit(parent, '占用带宽', '--', ...
    'GHz', y, width, @(src,evt) on_waveform_change(fig, src, evt, 'occupied_bandwidth_hz'));
state.ui.rate_driver = uicontrol(parent, 'Style', 'text', ...
    'Units', 'pixels', 'String', '当前由符号率计算带宽', ...
    'HorizontalAlignment', 'right', 'ForegroundColor', [0.20 0.38 0.52], ...
    'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [10 y width-20 21]);
y = y - 25;
state.ui.rate_summary = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', '--', 'HorizontalAlignment', 'left', ...
    'ForegroundColor', [0.28 0.34 0.38], ...
    'BackgroundColor', [0.94 0.95 0.96], ...
    'Position', [10 y width-20 44]);
y = y - 51;
[~, state.ui.rolloff, y] = edit_row_unit(parent, 'RRC 滚降', '0.15', '', y, width, ...
    @(src,evt) on_waveform_change(fig, src, evt, 'rolloff'));
[~, state.ui.frame_repetitions, y] = edit_row_unit(parent, '帧重复', '3', '次', y, width, ...
    @(src,evt) on_waveform_change(fig, src, evt, 'frame_repetitions'));

[~, y] = section_header(parent, '实验信息', y, width);
state.ui.note_label = text_label(parent, '实验备注', y, width);
state.ui.note = uicontrol(parent, 'Style', 'edit', 'Units', 'pixels', ...
    'Max', 2, 'Min', 0, 'HorizontalAlignment', 'left', ...
    'Position', [122 y-32 146 58], ...
    'Callback', @(src,evt) on_note_change(fig, src, evt));
y = y - 72;
state.ui.restore_defaults = uicontrol(parent, 'Style', 'pushbutton', ...
    'Units', 'pixels', 'String', '恢复界面默认值', 'Position', [122 y 146 28], ...
    'Callback', @(~,~) restore_project_defaults(fig));
y = y - 38;
state.ui.normalization = uicontrol(parent, 'Style', 'text', ...
    'Units', 'pixels', 'String', '参数未调整', 'HorizontalAlignment', 'left', ...
    'ForegroundColor', [0.20 0.38 0.52], ...
    'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [10 max(6,y-15) width-20 48]);
end

function button = header_button(parent, label, callback)
button = uicontrol(parent, 'Style', 'pushbutton', 'Units', 'pixels', ...
    'String', label, 'Callback', callback, 'FontSize', 9.5);
end

function [header, labels, values] = plan_section(parent, title_text, font_size, bold)
weight = 'normal'; if bold, weight = 'bold'; end
header = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', title_text, 'HorizontalAlignment', 'left', ...
    'FontSize', 8.5, 'FontWeight', 'bold', ...
    'ForegroundColor', [0.10 0.26 0.38], ...
    'BackgroundColor', [0.90 0.94 0.96]);
labels = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', {'--'}, 'HorizontalAlignment', 'left', ...
    'FontSize', font_size, 'ForegroundColor', [0.38 0.42 0.45], ...
    'BackgroundColor', get(parent, 'BackgroundColor'));
values = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', {'--'}, 'HorizontalAlignment', 'right', ...
    'FontSize', font_size, 'FontWeight', weight, ...
    'ForegroundColor', [0.12 0.16 0.18], ...
    'BackgroundColor', get(parent, 'BackgroundColor'));
end

function [handle, y] = section_header(parent, label, y, width)
handle = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', label, 'HorizontalAlignment', 'left', 'FontWeight', 'bold', ...
    'ForegroundColor', [0.10 0.26 0.38], 'BackgroundColor', [0.90 0.94 0.96], ...
    'Position', [6 y width-12 26]);
y = y - 37;
end

function [handle, y] = minor_header(parent, label, y, width)
handle = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', label, 'HorizontalAlignment', 'left', 'FontWeight', 'bold', ...
    'ForegroundColor', [0.28 0.32 0.35], ...
    'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [10 y width-20 22]);
y = y - 27;
end

function [current, target, y] = hardware_row(parent, label, unit, y, callback)
uicontrol(parent, 'Style', 'text', 'Units', 'pixels', 'String', label, ...
    'HorizontalAlignment', 'left', 'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [8 y 86 24]);
current = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', '--', 'HorizontalAlignment', 'right', ...
    'BackgroundColor', [0.94 0.95 0.96], ...
    'ForegroundColor', [0.25 0.29 0.32], 'Position', [96 y 70 25]);
target = uicontrol(parent, 'Style', 'edit', 'Units', 'pixels', ...
    'String', '--', 'HorizontalAlignment', 'right', ...
    'BackgroundColor', [1 1 1], 'Position', [175 y 70 25], ...
    'Callback', callback);
uicontrol(parent, 'Style', 'text', 'Units', 'pixels', 'String', unit, ...
    'HorizontalAlignment', 'left', 'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [252 y 26 24]);
y = y - 32;
end

function [current, target, y] = hardware_readonly_row(parent, label, unit, y)
uicontrol(parent, 'Style', 'text', 'Units', 'pixels', 'String', label, ...
    'HorizontalAlignment', 'left', 'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [8 y 86 24]);
current = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', '--', 'HorizontalAlignment', 'right', ...
    'BackgroundColor', [0.94 0.95 0.96], ...
    'ForegroundColor', [0.25 0.29 0.32], 'Position', [96 y 70 25]);
target = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', '--', 'HorizontalAlignment', 'right', ...
    'BackgroundColor', [0.94 0.95 0.96], ...
    'ForegroundColor', [0.25 0.29 0.32], 'Position', [175 y 70 25]);
uicontrol(parent, 'Style', 'text', 'Units', 'pixels', 'String', unit, ...
    'HorizontalAlignment', 'left', 'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [252 y 26 24]);
y = y - 32;
end

function [label, control, y] = edit_row_unit(parent, text_value, value, unit, y, width, callback)
label = text_label(parent, text_value, y, width);
control = uicontrol(parent, 'Style', 'edit', 'Units', 'pixels', ...
    'String', value, 'Position', [122 y 100 25], 'Callback', callback);
uicontrol(parent, 'Style', 'text', 'Units', 'pixels', 'String', unit, ...
    'HorizontalAlignment', 'left', 'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [229 y 49 24]);
y = y - 33;
end

function [label, control, y] = popup_row(parent, text_value, values, selected, y, width, callback)
label = text_label(parent, text_value, y, width);
control = uicontrol(parent, 'Style', 'popupmenu', 'Units', 'pixels', ...
    'String', values, 'Value', selected, 'Position', [122 y 146 25], ...
    'Callback', callback);
y = y - 33;
end

function label = text_label(parent, text_value, y, width)
label = uicontrol(parent, 'Style', 'text', 'Units', 'pixels', ...
    'String', text_value, 'HorizontalAlignment', 'left', ...
    'BackgroundColor', get(parent, 'BackgroundColor'), ...
    'Position', [10 y 108 min(25, width)]);
end

function state = fit_parameter_content(state)
children = allchild(state.ui.param_content);
if isempty(children), return; end
positions = get(children, 'Position');
if ~iscell(positions), positions = {positions}; end
minimum_y = inf; maximum_y = -inf;
for index = 1:numel(positions)
    position = positions{index};
    minimum_y = min(minimum_y, position(2));
    maximum_y = max(maximum_y, position(2)+position(4));
end
padding = 8; shift = padding-minimum_y;
for index = 1:numel(children)
    position = positions{index}; position(2) = position(2)+shift;
    set(children(index), 'Position', position);
end
state.ui.param_content_height = ceil(maximum_y+shift+padding);
end

function layout_ui(fig)
state = getappdata(fig, 'tx_workbench_state');
if ~isfield(state.ui, 'body'), return; end
pos = get(fig, 'Position'); w = max(1100, round(pos(3))); h = max(700, round(pos(4)));
header_h = 68; margin = 10; gap = 8; left_w = 304;
right_w = 270;
if w >= 1300, right_w = 286; end
set(state.ui.header, 'Position', [0 h-header_h w header_h]);
set(state.ui.body, 'Position', [0 0 w h-header_h]);
set(state.ui.connection, 'Position', [margin 35 165 24]);
button_y = 31; first_x = w-416;
set(state.ui.phase, 'Position', [178 17 max(250,w-712) 42]);
if strcmp(get(state.ui.reconnect, 'Visible'), 'on')
    set(state.ui.reconnect, 'Position', [w-526 button_y 102 30]);
end
set(state.ui.preview, 'Position', [first_x button_y 120 30]);
set(state.ui.download, 'Position', [first_x+128 button_y 132 30]);
set(state.ui.output, 'Position', [first_x+268 button_y 138 30]);
set(state.ui.preview_hint, 'Position', [first_x 6 120 18]);
set(state.ui.download_hint, 'Position', [first_x+128 6 132 18]);
set(state.ui.output_hint, 'Position', [first_x+268 6 138 18]);
body_h = h-header_h;
set(state.ui.params_outer, 'Position', [margin 8 left_w body_h-16]);
viewport_h = max(100, body_h-45); viewport_w = 280;
set(state.ui.params_view, 'Position', [5 7 viewport_w viewport_h]);
set(state.ui.scroll, 'Position', [287 7 12 viewport_h]);
content_h = state.ui.param_content_height;
set(state.ui.param_content, 'Position', [0 viewport_h-content_h viewport_w content_h]);
maximum = max(0, content_h-viewport_h);
old_maximum = get(state.ui.scroll, 'Max');
old_value = get(state.ui.scroll, 'Value');
old_offset = max(0, old_maximum-old_value);
was_at_bottom = old_maximum > 1 && old_offset >= old_maximum-1;
set(state.ui.scroll, 'Min', 0, 'Max', max(1,maximum), ...
    'SliderStep', [min(1,44/max(1,maximum)) min(1,viewport_h/max(1,maximum))]);
if maximum == 0
    set(state.ui.scroll, 'Value', 0, 'Enable', 'off');
elseif was_at_bottom
    set(state.ui.scroll, 'Value', 0, 'Enable', 'on');
else
    set(state.ui.scroll, 'Value', maximum-min(old_offset, maximum), 'Enable', 'on');
end
update_scroll_position(fig);
right_x = w-margin-right_w; center_x = margin+left_w+gap+52;
colorbar_reserve = 0;
if w >= 1300, colorbar_reserve = 62; end
center_w = right_x-gap-center_x-colorbar_reserve;
set(state.ui.plan_panel, 'Position', [right_x 8 right_w body_h-16]);
set(state.ui.dashboard_title, 'Position', [center_x body_h-31 center_w 23]);
plot_bottom = 45; plot_top = body_h-48; row_gap = 60; column_gap = 62;
plot_h = max(165, (plot_top-plot_bottom-row_gap)/2);
plot_w = max(165, (center_w-column_gap)/2);
set(state.ui.axes(1), 'PositionConstraint', 'innerposition', 'Position', ...
    [center_x plot_bottom+plot_h+row_gap plot_w plot_h]);
set(state.ui.axes(2), 'PositionConstraint', 'innerposition', 'Position', ...
    [center_x+plot_w+column_gap ...
    plot_bottom+plot_h+row_gap plot_w plot_h]);
set(state.ui.axes(3), 'PositionConstraint', 'innerposition', 'Position', ...
    [center_x plot_bottom plot_w plot_h]);
set(state.ui.axes(4), 'PositionConstraint', 'innerposition', 'Position', ...
    [center_x+plot_w+column_gap plot_bottom plot_w plot_h]);
layout_plan_blocks(fig, right_w, body_h);
end

function layout_plan_blocks(fig, right_w, body_h)
state = getappdata(fig, 'tx_workbench_state'); ui = state.ui;
viewport_h = max(100, body_h-45);
heights = [154 142 76 104];
base_height = sum(heights)+(numel(heights)+1)*4+8;
content_h = base_height;
maximum = max(0, content_h-viewport_h);
if maximum > 0
    viewport_w = right_w-22;
    set(ui.plan_scroll, 'Position', [right_w-15 7 11 viewport_h], ...
        'Visible', 'on');
else
    viewport_w = right_w-8;
    set(ui.plan_scroll, 'Visible', 'off');
end
set(ui.plan_view, 'Position', [4 7 viewport_w viewport_h]);
headers = [ui.plan_awg_header ui.plan_capacity_header ...
    ui.plan_changes_header ui.plan_fixed_header];
labels = [ui.plan_awg_labels ui.plan_capacity_labels ...
    ui.plan_changes_labels ui.plan_fixed_labels];
values = [ui.plan_awg ui.plan_capacity ui.plan_changes ui.plan_fixed];
header_h = 24; label_w = 64; column_gap = 6;
top = content_h-4;
for k = 1:numel(headers)
    section_bottom = top-heights(k);
    set(headers(k), 'Position', [4 top-header_h viewport_w-8 header_h]);
    section_body_h = heights(k)-header_h-3;
    set(labels(k), 'Position', [8 section_bottom label_w section_body_h]);
    set(values(k), 'Position', ...
        [8+label_w+column_gap section_bottom ...
        viewport_w-20-label_w-column_gap section_body_h]);
    top = section_bottom;
    top = top-4;
end
set(ui.plan_content, 'Position', [0 viewport_h-content_h viewport_w content_h]);
old_maximum = get(ui.plan_scroll, 'Max');
old_value = get(ui.plan_scroll, 'Value');
old_offset = max(0, old_maximum-old_value);
set(ui.plan_scroll, 'Min', 0, 'Max', max(1,maximum), ...
    'SliderStep', [min(1,44/max(1,maximum)) min(1,viewport_h/max(1,maximum))]);
if maximum == 0
    set(ui.plan_scroll, 'Value', 0, 'Enable', 'off');
else
    set(ui.plan_scroll, 'Value', maximum-min(old_offset, maximum), 'Enable', 'on');
end
update_plan_scroll_position(fig);
end

function update_scroll_position(fig)
state = getappdata(fig, 'tx_workbench_state');
viewport = get(state.ui.params_view, 'Position');
content = get(state.ui.param_content, 'Position');
maximum = max(0, content(4)-viewport(4));
value = min(max(get(state.ui.scroll, 'Value'), 0), maximum);
offset = maximum-value;
set(state.ui.param_content, 'Position', ...
    [0 viewport(4)-content(4)+offset content(3:4)]);
end

function update_plan_scroll_position(fig)
state = getappdata(fig, 'tx_workbench_state');
viewport = get(state.ui.plan_view, 'Position');
content = get(state.ui.plan_content, 'Position');
maximum = max(0, content(4)-viewport(4));
value = min(max(get(state.ui.plan_scroll, 'Value'), 0), maximum);
offset = maximum-value;
set(state.ui.plan_content, 'Position', ...
    [0 viewport(4)-content(4)+offset content(3:4)]);
end

function yes = point_in_rectangle(point, rectangle)
yes = point(1) >= rectangle(1) && point(1) <= rectangle(1)+rectangle(3) && ...
    point(2) >= rectangle(2) && point(2) <= rectangle(2)+rectangle(4);
end

function on_route_change(fig, control, ~)
state = getappdata(fig, 'tx_workbench_state');
if state.busy
    apply_parameters_to_controls(fig, state.params);
    return;
end
proposed = state.ui.route_values{get(control, 'Value')};
if strcmp(proposed, state.params.route), return; end
if state.connected && isfield(state.awg_status, 'state') && ...
        isfield(state.awg_status.state, 'outputs')
    outputs = logical(state.awg_status.state.outputs);
    old_channels = route_channels(state.params.route);
    new_channels = route_channels(proposed);
    if any(outputs(old_channels))
        apply_parameters_to_controls(fig, state.params);
        set_phase(fig, '当前路由仍有输出，请先停止输出');
        return;
    end
    if any(outputs(new_channels))
        apply_parameters_to_controls(fig, state.params);
        set_phase(fig, sprintf('目标路由 CH%d/CH%d 正在输出，已拒绝切换', ...
            new_channels(1), new_channels(2)));
        return;
    end
end
state.params.route = proposed;
state.plan_route_stale = true;
state.formal_plan_stale = true;
state = clear_loaded_binding(state);
setappdata(fig, 'tx_workbench_state', state);
apply_parameters_to_controls(fig, state.params);
save_local_parameters(state);
render_plan(fig); update_action_states(fig);
set(state.ui.normalization, 'String', '路由已切换；预览保留，下载绑定已清除');
set_phase(fig, '路由已切换；下载时将按新路由重新建立计划');
end

function on_waveform_change(fig, control, ~, field_name)
state = getappdata(fig, 'tx_workbench_state');
if state.busy
    apply_parameters_to_controls(fig, state.params);
    return;
end
params = state.params;
try
    switch field_name
        case 'rdiv'
            values = get(control, 'String');
            params.rdiv = char(values{get(control, 'Value')});
        case 'modulation_order'
            orders = [4 16 64];
            params.modulation_order = orders(get(control, 'Value'));
        otherwise
            [limits, integer_value, scale, label] = ...
                waveform_control_spec(field_name);
            raw = str2double(strtrim(char(string(get(control, 'String')))));
            if ~isscalar(raw) || ~isfinite(raw)
                error('msiq:txWorkbench:Numeric', '%s 必须是数字。', label);
            end
            value = min(max(raw, limits(1)), limits(2));
            if integer_value, value = round(value); end
            params.(field_name) = value*scale;
            set(control, 'String', number_text(value), ...
                'BackgroundColor', [1 1 1], 'TooltipString', '');
            if strcmp(field_name, 'symbol_rate_hz')
                state.rate_authority = 'symbol_rate';
                params.rate_authority = 'symbol_rate';
                params.occupied_bandwidth_hz = params.symbol_rate_hz*(1+params.rolloff);
            elseif strcmp(field_name, 'occupied_bandwidth_hz')
                state.rate_authority = 'bandwidth';
                params.rate_authority = 'bandwidth';
                params.symbol_rate_hz = params.occupied_bandwidth_hz/(1+params.rolloff);
            elseif strcmp(field_name, 'rolloff')
                if strcmp(state.rate_authority, 'bandwidth')
                    params.symbol_rate_hz = params.occupied_bandwidth_hz/(1+params.rolloff);
                else
                    params.occupied_bandwidth_hz = params.symbol_rate_hz*(1+params.rolloff);
                end
            end
    end
    if params.occupied_bandwidth_hz >= params.master_sample_rate_hz
        error('msiq:txWorkbench:Bandwidth', '占用带宽必须小于 DAC 采样率。');
    end
catch exception
    set(control, 'BackgroundColor', [1.00 0.88 0.86], ...
        'TooltipString', exception.message);
    set(state.ui.normalization, 'String', ['输入无效：', exception.message]);
    set_phase(fig, ['参数错误：', exception.message]);
    return;
end
old_signature = state.waveform_signature;
state.params = params;
state.waveform_signature = waveform_signature(params);
state.waveform_stale = isempty(state.preview_signature) || ...
    ~strcmp(state.waveform_signature, state.preview_signature);
if ~strcmp(old_signature, state.waveform_signature)
    state.plan_route_stale = true;
    state.formal_plan_stale = true;
end
setappdata(fig, 'tx_workbench_state', state);
apply_parameters_to_controls(fig, params);
save_local_parameters(state);
render_plan(fig); update_action_states(fig);
set(state.ui.normalization, 'String', '波形参数已变化；更新预览并重新下载后生效');
set_phase(fig, '波形参数已变化；当前仍显示上次预览');
end

function on_note_change(fig, control, ~)
state = getappdata(fig, 'tx_workbench_state');
if state.busy, return; end
state.params.note = char(string(get(control, 'String')));
state.formal_plan_stale = true;
setappdata(fig, 'tx_workbench_state', state);
save_local_parameters(state); render_plan(fig);
set(state.ui.normalization, 'String', '备注已保存；不改变预览或下载波形');
set_phase(fig, '实验备注已更新');
end

function [limits, integer_value, scale, label] = waveform_control_spec(name)
switch name
    case 'master_sample_rate_hz'
        limits = [53.76 65]; integer_value = false; scale = 1e9; label = 'DAC 采样率';
    case 'symbol_rate_hz'
        limits = [0.001 32]; integer_value = false; scale = 1e9; label = '符号率';
    case 'occupied_bandwidth_hz'
        limits = [0.001 64]; integer_value = false; scale = 1e9; label = '占用带宽';
    case 'rolloff'
        limits = [0 1]; integer_value = false; scale = 1; label = 'RRC 滚降';
    case 'frame_repetitions'
        limits = [1 16]; integer_value = true; scale = 1; label = '帧重复';
    otherwise
        error('msiq:txWorkbench:WaveformField', '未知波形参数：%s。', name);
end
end

function on_hardware_change(fig, control, ~, channel_index, field_name)
state = getappdata(fig, 'tx_workbench_state');
if state.busy
    restore_hardware_control(control, state.params, channel_index, field_name);
    set_phase(fig, '当前操作尚未完成，请稍后修改通道设置');
    return;
end
physical_channels = route_channels(state.params.route);
physical_channel = physical_channels(channel_index);
switch field_name
    case 'amplitude_vpp'
        label = sprintf('CH%d Vpp', physical_channel);
        limits = [0.01 2]; integer_value = false;
    case 'offset_v'
        label = sprintf('CH%d Offset', physical_channel);
        limits = [-1 1]; integer_value = false;
    case 'sample_clock_delay_samples'
        label = sprintf('CH%d 采样时钟延时', physical_channel);
        limits = [0 95]; integer_value = true;
    otherwise
        error('msiq:txWorkbench:HardwareField', ...
            'Unknown hardware field: %s.', field_name);
end
raw = strtrim(char(string(get(control, 'String'))));
value = str2double(raw);
if ~isscalar(value) || ~isfinite(value)
    reject_hardware_input(fig, control, sprintf('%s 必须是数字。', label));
    return;
end
if value < limits(1) || value > limits(2)
    reject_hardware_input(fig, control, sprintf( ...
        '%s 超出允许范围 [%g, %g]。', label, limits(1), limits(2)));
    return;
end
original = value;
if integer_value, value = round(value); end
stop_app_timer(fig, 'tx_workbench_hardware_timer');
field_values = state.params.(field_name);
old_value = field_values(physical_channel);
field_values(physical_channel) = value;
state.params.(field_name) = field_values;
column = hardware_field_column(field_name);
    state.hardware_dirty_fields(physical_channel, column) = ...
        ~state.connected || ~hardware_field_matches(state, physical_channel, column);
state.hardware_errors{physical_channel, column} = '';
state.hardware_dirty = any(state.hardware_dirty_fields(:));
    if state.hardware_dirty
        state.hardware_sync_state = 'pending';
    elseif state.connected
        state.hardware_sync_state = hardware_match_state(state.awg_status.state, state.params);
    else
        state.hardware_sync_state = 'disconnected';
    end
state.hardware_sync_error = '';
if abs(value-old_value) > 1e-12 || ...
        state.hardware_dirty_fields(physical_channel, column)
    state.formal_plan_stale = true;
end
set(control, 'String', number_text(value), 'TooltipString', '');
setappdata(fig, 'tx_workbench_state', state);
save_local_parameters(state);
update_derived_values(fig, state.params);
update_hardware_sync_visuals(fig);
render_plan(fig); update_action_states(fig);
if ~state.hardware_dirty_fields(physical_channel, column)
    message = sprintf('%s 与 AWG 当前值一致；未发送命令', label);
elseif integer_value && abs(value-original) > 1e-12
    message = sprintf('%s 已调整为 %d 点；等待自动同步', label, value);
else
    message = sprintf('%s 已更新；等待自动同步', label);
end
set(state.ui.normalization, 'String', message);
if state.connected && state.hardware_dirty_fields(physical_channel, column)
    set_phase(fig, message); schedule_hardware_sync(fig);
elseif state.connected
    set_phase(fig, message);
else
    set_phase(fig, [message, '；AWG 重连后自动写入']);
end
end

function reject_hardware_input(fig, control, message)
set(control, 'BackgroundColor', [1.00 0.88 0.86], ...
    'TooltipString', message);
state = getappdata(fig, 'tx_workbench_state');
set(state.ui.normalization, 'String', ['输入无效：', message]);
set_phase(fig, ['参数错误：', message, '；未写入 AWG']);
end

function restore_hardware_control(control, params, channel_index, field_name)
channels = route_channels(params.route);
set(control, 'String', number_text(params.(field_name)(channels(channel_index))), ...
    'BackgroundColor', [1 1 1], 'TooltipString', '');
end

function [params, messages] = read_parameters(state, normalize)
messages = cell(0,1); params = state.params;
params.route = state.ui.route_values{get(state.ui.route, 'Value')};
rdiv_values = get(state.ui.rdiv, 'String');
params.rdiv = char(rdiv_values{get(state.ui.rdiv, 'Value')});
orders = [4 16 64]; params.modulation_order = orders(get(state.ui.modulation, 'Value'));
[master_gsa, messages] = read_numeric_control(state.ui.master_rate, ...
    'DAC 采样率', [53.76 65], false, normalize, messages);
params.master_sample_rate_hz = master_gsa*1e9;
[symbol_gbd, messages] = read_numeric_control(state.ui.symbol_rate, ...
    '符号率', [0.001 32], false, normalize, messages);
[bandwidth_ghz, messages] = read_numeric_control(state.ui.bandwidth, ...
    '占用带宽', [0.001 64], false, normalize, messages);
[params.rolloff, messages] = read_numeric_control(state.ui.rolloff, ...
    'RRC 滚降', [0 1], false, normalize, messages);
if strcmp(state.rate_authority, 'bandwidth')
    params.occupied_bandwidth_hz = bandwidth_ghz*1e9;
    params.symbol_rate_hz = params.occupied_bandwidth_hz/(1+params.rolloff);
    set(state.ui.symbol_rate, 'String', number_text(params.symbol_rate_hz/1e9));
else
    params.symbol_rate_hz = symbol_gbd*1e9;
    params.occupied_bandwidth_hz = params.symbol_rate_hz*(1+params.rolloff);
    set(state.ui.bandwidth, 'String', number_text(params.occupied_bandwidth_hz/1e9));
end
if params.occupied_bandwidth_hz >= params.master_sample_rate_hz
    error('msiq:txWorkbench:Bandwidth', '占用带宽必须小于 DAC 采样率。');
end
[params.frame_repetitions, messages] = read_numeric_control( ...
    state.ui.frame_repetitions, '帧重复', [1 16], true, normalize, messages);
params.note = char(string(get(state.ui.note, 'String')));
params.rate_authority = state.rate_authority;
end

function [value, messages] = read_numeric_control( ...
        control, label, limits, integer_value, normalize, messages)
raw = strtrim(char(string(get(control, 'String')))); value = str2double(raw);
if ~isscalar(value) || ~isfinite(value)
    error('msiq:txWorkbench:Numeric', '%s 必须是数字。', label);
end
original = value;
if normalize
    value = min(max(value, limits(1)), limits(2));
    if integer_value, value = round(value); end
elseif value < limits(1) || value > limits(2) || ...
        (integer_value && abs(value-round(value)) > 1e-9)
    error('msiq:txWorkbench:Range', ...
        '%s 超出允许范围 [%g, %g]。', label, limits(1), limits(2));
end
if normalize
    set(control, 'String', number_text(value), 'BackgroundColor', [1 1 1], ...
        'TooltipString', '');
    if abs(value-original) > 1e-12
        messages{end+1} = sprintf('%s 已调整为 %s', ...
            label, number_text(value));
    end
end
end

function apply_parameters_to_controls(fig, params)
state = getappdata(fig, 'tx_workbench_state');
route_index = find(strcmp(state.ui.route_values, params.route), 1);
if isempty(route_index), route_index = 1; end
set(state.ui.route, 'Value', route_index);
rdiv_values = get(state.ui.rdiv, 'String');
rdiv_index = find(strcmpi(rdiv_values, params.rdiv), 1);
if isempty(rdiv_index), rdiv_index = numel(rdiv_values); end
set(state.ui.rdiv, 'Value', rdiv_index);
channels = route_channels(params.route);
for k = 1:2
    channel = channels(k);
    set(state.ui.target_vpp(k), 'String', number_text(params.amplitude_vpp(channel)));
    set(state.ui.target_offset(k), 'String', number_text(params.offset_v(channel)));
    set(state.ui.target_sdel(k), 'String', ...
        number_text(params.sample_clock_delay_samples(channel)), 'TooltipString', '');
end
orders = [4 16 64]; order_index = find(orders == params.modulation_order, 1);
if isempty(order_index), order_index = 2; end
set(state.ui.modulation, 'Value', order_index);
set(state.ui.master_rate, 'String', number_text(params.master_sample_rate_hz/1e9));
set(state.ui.symbol_rate, 'String', number_text(params.symbol_rate_hz/1e9));
set(state.ui.bandwidth, 'String', number_text(params.occupied_bandwidth_hz/1e9));
set(state.ui.rolloff, 'String', number_text(params.rolloff));
set(state.ui.frame_repetitions, 'String', number_text(params.frame_repetitions));
set(state.ui.note, 'String', params.note);
update_route_labels(fig, params.route); update_derived_values(fig, params);
update_hardware_sync_visuals(fig);
end

function update_route_labels(fig, route)
state = getappdata(fig, 'tx_workbench_state'); channels = route_channels(route);
labels = {'I','Q'};
for k = 1:2
    set(state.ui.channel_heading(k), 'String', sprintf('CH%d · %s', channels(k), labels{k}));
end
update_current_hardware(fig);
end

function update_derived_values(fig, params)
state = getappdata(fig, 'tx_workbench_state');
divider = str2double(extractAfter(params.rdiv, 'DIV'));
up = params.master_sample_rate_hz/params.symbol_rate_hz;
set(state.ui.rate_summary, 'String', sprintf( ...
    'UP %.6g  |  波形存储采样率 %.6g GSa/s\n存储样点/符号 %.6g', ...
    up, params.master_sample_rate_hz/divider/1e9, up/divider));
if strcmp(params.rate_authority, 'bandwidth')
    set(state.ui.rate_driver, 'String', '当前由占用带宽计算符号率');
else
    set(state.ui.rate_driver, 'String', '当前由符号率计算占用带宽');
end
current_raster = NaN;
if state.connected && isfield(state.awg_status, 'state')
    current_raster = numeric_or(field_or(state.awg_status.state, 'raster_hz', NaN), NaN);
end
target_raster = params.master_sample_rate_hz;
channels = route_channels(params.route);
for k = 1:2
    target_ps = params.sample_clock_delay_samples(channels(k))/target_raster*1e12;
    current = numeric_or(str2double(get(state.ui.current_sdel(k), 'String')), NaN);
    current_ps = current/current_raster*1e12;
    set(state.ui.current_delay_ps(k), 'String', finite_text(current_ps));
    set(state.ui.target_delay_ps(k), 'String', finite_text(target_ps));
end
target_relative = params.sample_clock_delay_samples(channels(2))- ...
    params.sample_clock_delay_samples(channels(1));
current_delays = arrayfun(@(h)str2double(get(h,'String')), state.ui.current_sdel);
if all(isfinite(current_delays))
    current_relative = sprintf('%+d', ...
        round(current_delays(2)-current_delays(1)));
else
    current_relative = '--';
end

set(state.ui.current_relative_delay, 'String', current_relative);
set(state.ui.target_relative_delay, 'String', sprintf('%+d', round(target_relative)));
update_dashboard_title(fig);
end

function update_hardware_sync_visuals(fig)
state = getappdata(fig, 'tx_workbench_state');
normal = [1 1 1]; pending = [1.00 0.97 0.82]; different = [0.97 0.96 0.91];
writing = [0.88 0.95 1.00]; failed = [1.00 0.88 0.86];
channels = route_channels(state.params.route);
controls = {state.ui.target_vpp, state.ui.target_offset, state.ui.target_sdel};
for k = 1:2
    channel = channels(k);
    matches = hardware_channel_matches(state, k);
    channel_dirty = any(state.hardware_dirty_fields(channel,:));
    channel_failed = any(~cellfun(@isempty, state.hardware_errors(channel,:)));
    active_channel = field_or(state.hardware_failed_request, 'channel', NaN);
    if channel_failed
        text_value = '失败'; color = [0.72 0.18 0.12];
    elseif strcmp(state.hardware_sync_state, 'writing') && channel == active_channel
        text_value = '写入中'; color = [0.10 0.38 0.62];
    elseif channel_dirty
        text_value = ternary(state.connected, '待写入', '待重连');
        color = [0.68 0.43 0.05];
    elseif state.connected
        text_value = ternary(matches, '与目标一致', '目标不同');
        color = ternary(matches, [0.08 0.48 0.28], [0.56 0.43 0.18]);
    else
        text_value = '未连接'; color = [0.42 0.45 0.47];
    end
    set(state.ui.channel_sync(k), 'String', text_value, 'ForegroundColor', color);
    for field_index = 1:3
        background = normal;
        if ~isempty(state.hardware_errors{channel,field_index})
            background = failed;
            tooltip = state.hardware_errors{channel,field_index};
        elseif strcmp(state.hardware_sync_state, 'writing') && ...
                channel == active_channel && ...
                field_index == field_or(state.hardware_failed_request, 'field_index', NaN)
            background = writing;
            tooltip = field_or(state.hardware_failed_request, 'command', '');
        elseif state.hardware_dirty_fields(channel,field_index)
            background = pending;
            tooltip = '离开输入框后等待写入 AWG';
        elseif state.connected && ~hardware_field_matches(state, channel, field_index)
            background = different;
            tooltip = '上次目标尚未应用';
        else
            tooltip = '';
        end
        set(controls{field_index}(k), 'BackgroundColor', background, ...
            'TooltipString', tooltip);
    end
end
if strcmp(state.hardware_sync_state, 'failed')
    request = state.hardware_failed_request;
    set(state.ui.hardware_summary, 'String', sprintf('CH%d %s 写入失败', ...
        field_or(request, 'channel', 0), hardware_field_label( ...
        field_or(request, 'field_name', ''))), ...
        'ForegroundColor', [0.72 0.18 0.12], ...
        'TooltipString', state.hardware_sync_error);
    set(state.ui.retry_settings, 'Visible', 'on');
elseif strcmp(state.hardware_sync_state, 'writing')
    request = state.hardware_failed_request;
    set(state.ui.hardware_summary, 'String', sprintf('正在写入 CH%d %s', ...
        field_or(request, 'channel', 0), hardware_field_label( ...
        field_or(request, 'field_name', ''))), ...
        'ForegroundColor', [0.10 0.38 0.62], 'TooltipString', '');
    set(state.ui.retry_settings, 'Visible', 'off');
elseif state.hardware_dirty
    if state.connected, summary = '编辑字段等待写入'; else, summary = '本次编辑将在重连后写入'; end
    set(state.ui.hardware_summary, 'String', summary, ...
        'ForegroundColor', [0.68 0.43 0.05], 'TooltipString', '');
    set(state.ui.retry_settings, 'Visible', 'off');
elseif state.connected
    set(state.ui.hardware_summary, 'String', '离开输入框后写入 AWG', ...
        'ForegroundColor', [0.20 0.38 0.52], ...
        'TooltipString', '');
    set(state.ui.retry_settings, 'Visible', 'off');
else
    set(state.ui.hardware_summary, 'String', '连接后自动写入本次编辑', ...
        'ForegroundColor', [0.42 0.45 0.47], 'TooltipString', '');
    set(state.ui.retry_settings, 'Visible', 'off');
end
end

function yes = hardware_channel_matches(state, channel_index)
yes = false;
if ~state.connected || ~isfield(state.awg_status, 'state') || ...
        ~isfield(state.awg_status.state, 'traces') || ...
        numel(state.awg_status.state.traces) ~= 4
    return;
end
channels = route_channels(state.params.route);
channel = channels(channel_index);
trace = state.awg_status.state.traces(channel);
yes = abs(trace.amplitude_vpp-state.params.amplitude_vpp(channel)) <= 1e-9 && ...
    abs(trace.offset_v-state.params.offset_v(channel)) <= 1e-9 && ...
    trace.sample_clock_delay_samples == ...
    state.params.sample_clock_delay_samples(channel);
end

function update_current_hardware(fig)
state = getappdata(fig, 'tx_workbench_state'); channels = route_channels(state.params.route);
available = state.connected && isfield(state.awg_status, 'state') && ...
    isfield(state.awg_status.state, 'traces') && numel(state.awg_status.state.traces) == 4;
for k = 1:2
    if available
        trace = state.awg_status.state.traces(channels(k));
        set(state.ui.current_vpp(k), 'String', finite_text(trace.amplitude_vpp));
        set(state.ui.current_offset(k), 'String', finite_text(trace.offset_v));
        set(state.ui.current_sdel(k), 'String', finite_text(trace.sample_clock_delay_samples));
    else
        set(state.ui.current_vpp(k), 'String', '--');
        set(state.ui.current_offset(k), 'String', '--');
        set(state.ui.current_sdel(k), 'String', '--');
    end
end
update_derived_values(fig, state.params); update_hardware_sync_visuals(fig);
end

function restore_project_defaults(fig)
state = getappdata(fig, 'tx_workbench_state');
stop_app_timer(fig, 'tx_workbench_hardware_timer');
restored = state.defaults;
if ~strcmp(restored.route, state.params.route)
    current_outputs = selected_route_outputs(state, state.params.route);
    target_outputs = selected_route_outputs(state, restored.route);
    if any(current_outputs) || any(target_outputs)
        restored.route = state.params.route;
    else
        state = clear_loaded_binding(state);
    end
end
state.params = restored; state.rate_authority = restored.rate_authority;
state.waveform_signature = waveform_signature(state.params);
state.waveform_stale = isempty(state.preview_signature) || ...
    ~strcmp(state.waveform_signature, state.preview_signature);
state.plan_route_stale = true;
state.formal_plan_stale = true;
state.hardware_dirty = false; state.hardware_dirty_fields(:) = false;
state.hardware_errors(:) = {''}; state.hardware_failed_request = struct();
state.hardware_sync_state = ternary(state.connected, 'different', 'disconnected');
state.hardware_sync_error = '';
setappdata(fig, 'tx_workbench_state', state);
apply_parameters_to_controls(fig, state.params); save_local_parameters(state);
set(state.ui.normalization, 'String', '已恢复默认目标；未写入 AWG');
update_action_states(fig); render_plan(fig);
set_phase(fig, '已恢复默认目标；硬件保持不变');
end

function regenerate_preview(fig)
state = getappdata(fig, 'tx_workbench_state'); if state.busy, return; end
state.busy = true; setappdata(fig, 'tx_workbench_state', state);
update_action_states(fig); set_phase(fig, '正在生成波形预览与预检'); drawnow;
try
    [state.params, messages] = read_parameters(state, true);
    opts = backend_parameters(state.params, state.backend_options);
    if state.connected && isfield(state.awg_status, 'state'), opts.awg_state = state.awg_status.state; end
    plan = msiq.traditional_tx('preview_plan', [], opts); plan.params = state.params;
    state.waveform_signature = waveform_signature(state.params);
    state.preview_signature = state.waveform_signature;
    plan.gui_waveform_signature = state.preview_signature;
    state.plan = plan; state.plan_valid = true; state.waveform_stale = false;
    state.plan_route_stale = false; state.busy = false;
    setappdata(fig, 'tx_workbench_state', state); save_local_parameters(state);
    apply_parameters_to_controls(fig, state.params); render_preview(fig, plan);
    render_plan(fig); update_action_states(fig);
    if ~plan.preflight.ok
        set(state.ui.normalization, 'String', '波形已生成；AWG 内存容量不足');
    elseif isempty(messages)
        set(state.ui.normalization, 'String', '波形参数有效；预览已更新');
    else
        set(state.ui.normalization, 'String', strjoin(messages, '；'));
    end
    if ~plan.preflight.ok
        set_phase(fig, ['禁止下载：', plan.preflight.reason]);
    elseif state.connected
        set_phase(fig, '等待下载确认');
    else
        set_phase(fig, ['预览完成；', connection_failure_text(state.awg_status)]);
    end
catch exception
    state.busy = false; state.plan_valid = false; state.waveform_stale = true;
    setappdata(fig, 'tx_workbench_state', state); update_action_states(fig);
    render_plan_error(fig, exception);
    set_phase(fig, sprintf('预览失败 [%s]：%s', exception.identifier, exception.message));
end
end

function refresh_awg_status(fig)
state = getappdata(fig, 'tx_workbench_state'); if state.busy, return; end
state.busy = true; setappdata(fig, 'tx_workbench_state', state);
update_action_states(fig); set_phase(fig, '连接 AWG：打开会话并回读完整状态'); drawnow;
try
    result = msiq.traditional_tx('awg_status', [], state.backend_options);
    state.awg_status = result; state.connected = strcmpi(result.status, 'ok'); state.busy = false;
    if state.connected
        state.hardware_snapshot = result.state;
        state = refresh_preview_capacity(state, result.state);
        state.hardware_dirty = any(state.hardware_dirty_fields(:));
        state.hardware_sync_error = '';
        if state.hardware_dirty
            state.hardware_sync_state = 'pending';
        else
            matches = hardware_target_matches(result.state, state.params);
            state.hardware_sync_state = ternary(all(matches), 'synced', 'different');
        end
    end
    setappdata(fig, 'tx_workbench_state', state); render_awg_status(fig, result);
    render_plan(fig); update_action_states(fig);
    if state.connected
        if state.hardware_dirty
            set_phase(fig, '状态回读完成；本次离线编辑等待写入');
            schedule_hardware_sync(fig);
        else
            set_phase(fig, '状态回读完成；未修改设备');
        end
    else
        state.hardware_sync_state = 'disconnected';
        setappdata(fig, 'tx_workbench_state', state);
        set_phase(fig, ['AWG 状态查询失败：', result.health.message]);
    end
catch exception
    state.connected = false; state.busy = false;
    state.awg_status = struct('status', 'failed', 'error', exception.message, ...
        'identifier', exception.identifier);
    state.hardware_sync_state = 'disconnected';
    setappdata(fig, 'tx_workbench_state', state); render_awg_status(fig, state.awg_status);
    render_plan(fig); update_action_states(fig);
    set_phase(fig, sprintf('AWG 连接阶段失败 [%s]：%s', ...
        exception.identifier, exception.message));
end
end

function state = refresh_preview_capacity(state, awg_state)
if ~state.plan_valid || ~isstruct(state.plan) || ...
        ~isfield(state.plan, 'desired') || ~isfield(state.plan, 'download')
    return;
end
desired = state.plan.desired;
download = state.plan.download;
required = double(download.final_sample_counts(:).');
if isfield(download, 'channel_data') && iscell(download.channel_data) && ...
        numel(download.channel_data) == numel(download.channels)
    required = cellfun(@numel, download.channel_data);
end
if isfield(desired, 'channel_memory_modes')
    modes = desired.channel_memory_modes;
else
    modes = repmat({desired.memory_mode}, 1, 4);
end
capacity = msiq.instruments.awg_memory_capacity(struct( ...
    'dac_mode', desired.dac_mode, ...
    'channel_memory_modes', {modes}, ...
    'rdiv', desired.rdiv, ...
    'selected_channels', download.channels, ...
    'required_samples_per_channel', required, ...
    'option_raw', field_or(awg_state, 'options_raw', '')));
capacity.dac_raster_hz = desired.raster_hz;
state.plan.memory_capacity = capacity;
if isfield(state.plan, 'preflight')
    waveform_ok = logical(field_or(state.plan.preflight, ...
        'waveform_ok', state.plan.preflight.ok));
    state.plan.preflight.capacity = capacity;
    state.plan.preflight.ok = waveform_ok && capacity.ok;
    if ~capacity.ok
        state.plan.preflight.reason = capacity.message;
    elseif waveform_ok
        state.plan.preflight.reason = '波形与AWG内存容量检查通过';
    end
end
end

function apply_channel_settings(fig)
state = getappdata(fig, 'tx_workbench_state');
if state.busy
    schedule_hardware_sync(fig); return;
end
if ~state.connected || ~state.hardware_dirty, return; end
stop_app_timer(fig, 'tx_workbench_hardware_timer');
[channel, field_index] = first_dirty_hardware_field(state.hardware_dirty_fields);
field_name = hardware_field_name(field_index);
route = route_for_channel(channel);
request = struct('channel', channel, 'field_index', field_index, ...
    'field_name', field_name, 'route', route, ...
    'command', hardware_command_text(state.params, channel, field_name));
state.busy = true; state.hardware_sync_state = 'writing';
state.hardware_failed_request = request;
setappdata(fig, 'tx_workbench_state', state);
update_action_states(fig); update_hardware_sync_visuals(fig); render_plan(fig);
set_phase(fig, sprintf('写入 CH%d %s：暂时关闭该通道并回读', ...
    channel, hardware_field_label(field_name))); drawnow;
opts = hardware_backend_options(state.params, state.backend_options, route);
opts.physical_channels = channel;
opts.setting_names = {field_name};
try
    result = msiq.traditional_tx('awg_channel_settings', [], opts);
    state.awg_status = struct('status', 'ok', 'state', result.state, ...
        'health', struct('message', '单字段设置已写入并回读一致。'));
    trace = result.state.traces(channel);
    field_values = state.params.(field_name);
    field_values(channel) = trace.(hardware_trace_field(field_name));
    state.params.(field_name) = field_values;
    state.hardware_dirty_fields(channel, field_index) = false;
    state.hardware_errors{channel, field_index} = '';
    state.connected = true; state.hardware_dirty = any(state.hardware_dirty_fields(:));
    state.hardware_sync_state = ternary(state.hardware_dirty, 'pending', ...
        hardware_match_state(result.state, state.params));
    state.hardware_sync_error = ''; state.hardware_failed_request = struct();
    state.hardware_snapshot = result.state;
    state = update_output_tracking(state, result.state);
    state.busy = false; setappdata(fig, 'tx_workbench_state', state);
    save_local_parameters(state); apply_parameters_to_controls(fig, state.params);
    render_awg_status(fig, state.awg_status);
    render_plan(fig); update_action_states(fig);
    set_phase(fig, sprintf('CH%d %s 已写入并回读一致', ...
        channel, hardware_field_label(field_name)));
    if state.hardware_dirty, schedule_hardware_sync(fig); end
catch exception
    state.busy = false; state.hardware_dirty = true;
    state.hardware_sync_state = 'failed';
    state.hardware_sync_error = sprintf('命令 %s | [%s] %s', ...
        request.command, exception.identifier, exception.message);
    state.hardware_errors{channel, field_index} = state.hardware_sync_error;
    state.hardware_failed_request = request;
    try
        status = msiq.traditional_tx('awg_status', [], state.backend_options);
        state.awg_status = status; state.connected = strcmpi(status.status, 'ok');
    catch status_exception
        state.connected = false;
        state.awg_status = struct('status', 'failed', ...
            'error', status_exception.message, ...
            'identifier', status_exception.identifier);
    end
    setappdata(fig, 'tx_workbench_state', state); render_awg_status(fig, state.awg_status);
    render_plan(fig); update_action_states(fig);
    set_phase(fig, sprintf('CH%d %s 写入失败；命令 %s；[%s] %s；该通道保持关闭', ...
        channel, hardware_field_label(field_name), request.command, ...
        exception.identifier, exception.message));
end
end

function retry_channel_settings(fig)
state = getappdata(fig, 'tx_workbench_state');
if state.busy, return; end
if state.connected
    request = state.hardware_failed_request;
    if isstruct(request) && isfield(request, 'channel')
        state.hardware_errors{request.channel, request.field_index} = '';
    end
    state.hardware_sync_state = 'pending'; state.hardware_sync_error = '';
    setappdata(fig, 'tx_workbench_state', state);
    apply_channel_settings(fig);
else
    refresh_awg_status(fig);
end
end

function schedule_hardware_sync(fig)
if ~ishghandle(fig), return; end
state = getappdata(fig, 'tx_workbench_state');
if ~state.connected || ~state.hardware_dirty, return; end
stop_app_timer(fig, 'tx_workbench_hardware_timer');
timer_obj = timer('ExecutionMode', 'singleShot', ...
    'StartDelay', max(0.01, state.hardware_apply_delay_s), ...
    'TimerFcn', @(source,event) hardware_timer_fired(source, event, fig), ...
    'ErrorFcn', @(~,event) hardware_timer_error(fig, event));
setappdata(fig, 'tx_workbench_hardware_timer', timer_obj);
start(timer_obj);
end

function hardware_timer_fired(timer_obj, ~, fig)
cleanup = onCleanup(@() delete_timer(timer_obj));
if ~ishghandle(fig), return; end
stored = getappdata(fig, 'tx_workbench_hardware_timer');
if isequal(stored, timer_obj), rmappdata(fig, 'tx_workbench_hardware_timer'); end
state = getappdata(fig, 'tx_workbench_state');
if state.busy
    schedule_hardware_sync(fig); return;
end
apply_channel_settings(fig);
clear cleanup;
end

function hardware_timer_error(fig, event)
if ~ishghandle(fig), return; end
state = getappdata(fig, 'tx_workbench_state');
state.hardware_sync_state = 'failed'; state.hardware_dirty = true;
state.hardware_sync_error = event.Data.Message;
request = state.hardware_failed_request;
if isstruct(request) && isfield(request, 'channel')
    state.hardware_errors{request.channel, request.field_index} = event.Data.Message;
end
setappdata(fig, 'tx_workbench_state', state);
update_hardware_sync_visuals(fig); render_plan(fig); update_action_states(fig);
set_phase(fig, ['自动同步任务失败：', event.Data.Message]);
end

function download_and_output(fig)
state = getappdata(fig, 'tx_workbench_state');
if state.busy || ~state.connected || ~state.plan_valid || state.waveform_stale
    set_phase(fig, '下载不可用：请先连接 AWG 并更新预览'); return;
end
if (~isfield(state.plan, 'preflight') || ~state.plan.preflight.ok) && ...
        ~state.plan_route_stale
    update_action_states(fig);
    set_phase(fig, ['禁止下载：', state.plan.preflight.reason]);
    return;
end
try
    [state.params, ~] = read_parameters(state, true);
    state.waveform_signature = waveform_signature(state.params);
    if ~strcmp(state.waveform_signature, state.preview_signature)
        state.waveform_stale = true;
        setappdata(fig, 'tx_workbench_state', state);
        update_action_states(fig); render_plan(fig);
        set_phase(fig, '下载不可用：当前参数与预览不一致');
        return;
    end
catch exception
    set_phase(fig, ['下载参数无效：', exception.message]); return;
end
state.busy = true; setappdata(fig, 'tx_workbench_state', state);
stop_app_timer(fig, 'tx_workbench_hardware_timer');
update_action_states(fig); set_phase(fig, '创建正式计划并检查 AWG 状态漂移'); drawnow;
try
    opts = backend_parameters(state.params, state.backend_options);
    plan = msiq.traditional_tx('awg_plan', [], opts);
catch exception
    state.busy = false; setappdata(fig, 'tx_workbench_state', state);
    update_action_states(fig);
    set_phase(fig, sprintf('下载计划失败 [%s]：%s', ...
        exception.identifier, exception.message));
    if state.hardware_dirty, schedule_hardware_sync(fig); end
    return;
end
plan.params = state.params;
state.plan = plan;
state.formal_plan_hash = plan.plan_hash;
state.formal_plan_stale = false;
setappdata(fig, 'tx_workbench_state', state);
render_plan(fig);
if ~confirm_download(state, plan)
    state.busy = false; setappdata(fig, 'tx_workbench_state', state);
    update_action_states(fig); set_phase(fig, '已取消下载');
    if state.hardware_dirty, schedule_hardware_sync(fig); end
    return;
end
set_phase(fig, '正在下载波形、启动 AWG 并开启所选输出'); drawnow;
try
    receipt = msiq.traditional_tx('awg_apply', [], struct( ...
        'plan', plan, 'confirmation_phrase', plan.required_confirmation, ...
        'enable_output', true));
    plan.gui_waveform_signature = state.waveform_signature;
    state.plan = plan; state.plan_valid = true; state.waveform_stale = false;
    state.preview_signature = state.waveform_signature;
    state.loaded_signature = state.waveform_signature;
    state.loaded_waveform_signature = plan.waveform_signature;
    state.loaded_route = plan.route.name; state.plan_route_stale = false;
    channels = plan.route.awg_channels;
    for index = 1:numel(channels)
        channel = channels(index); trace = receipt.final_state.traces(channel);
        state.params.amplitude_vpp(channel) = trace.amplitude_vpp;
        state.params.offset_v(channel) = trace.offset_v;
        state.params.sample_clock_delay_samples(channel) = ...
            trace.sample_clock_delay_samples;
    end
    state.hardware_dirty_fields(channels,:) = false;
    state.hardware_errors(channels,:) = {''}; state.hardware_failed_request = struct();
    state.hardware_dirty = any(state.hardware_dirty_fields(:));
    state.hardware_sync_state = ternary(state.hardware_dirty, 'pending', 'synced');
    state.hardware_sync_error = '';
    state.formal_plan_hash = plan.plan_hash; state.formal_plan_stale = false;
    state.last_run_dir = plan.run_dir;
    state.awg_status = struct('status', 'ok', 'state', receipt.final_state, ...
        'health', struct('message', '下载完成并已输出。'));
    state.hardware_snapshot = receipt.final_state;
    state = update_output_tracking(state, receipt.final_state);
    state.busy = false; setappdata(fig, 'tx_workbench_state', state);
    render_awg_status(fig, state.awg_status); render_plan(fig);
    update_action_states(fig); set_phase(fig, '下载完成；所选通道正在输出');
    if state.hardware_dirty, schedule_hardware_sync(fig); end
catch exception
    state.busy = false; state.formal_plan_stale = true;
    state = clear_loaded_binding(state);
    setappdata(fig, 'tx_workbench_state', state); update_action_states(fig);
    if strcmp(exception.identifier, 'msiq:traditionalTx:AwgMemoryCapacity')
        set_phase(fig, sprintf('下载已拒绝 [%s]：%s', ...
            exception.identifier, exception.message));
    else
        set_phase(fig, sprintf('下载失败 [%s]：%s；所选输出已执行关闭保护', ...
            exception.identifier, exception.message));
    end
end
end

function answer = confirm_download(state, plan)
if ~isempty(state.confirmation_handler)
    answer = logical(state.confirmation_handler(plan)); return;
end
differences = difference_text(plan.public_parameter_differences);
channels = plan.route.awg_channels;
message = sprintf(['确认下载并输出？\n\n路由：%s（CH%d/CH%d）\n波形：%s\n' ...
    'RDIV：%s\n有效/填充样点：%d / %d\n' ...
    '目标设置：CH%d %.4g V / %.4g V / SDEL %d；CH%d %.4g V / %.4g V / SDEL %d\n' ...
    '公共状态差异：%s\n当前其他活动通道：%s\n\n' ...
    '将发送公共 :ABOR，所有活动通道都会停止；随后重新下载波形、' ...
    '启动 AWG，并只开启 CH%d/CH%d。'], ...
    plan.route.name, channels(1), channels(2), short_hash(plan.waveform_signature), ...
    plan.desired.rdiv, plan.waveform_sample_count, ...
    plan.padded_sample_count, channels(1), plan.levels.amplitude_vpp(1), ...
    plan.levels.offset_v(1), plan.sample_clock_delay_samples(1), channels(2), ...
    plan.levels.amplitude_vpp(2), plan.levels.offset_v(2), ...
    plan.sample_clock_delay_samples(2), differences, ...
    vector_text(plan.affected_other_channels), channels(1), channels(2));
choice = questdlg(message, '下载并输出', '下载并输出', '取消', '取消');
answer = strcmp(choice, '下载并输出');
end

function toggle_output(fig)
state = getappdata(fig, 'tx_workbench_state');
if state.busy || ~state.connected, return; end
state.busy = true; setappdata(fig, 'tx_workbench_state', state);
update_action_states(fig);
if loaded_route_has_output(state)
    set_phase(fig, '正在停止已下载路由输出');
    try
        opts = merge_struct(state.backend_options, struct('route', state.loaded_route));
        result = msiq.traditional_tx('awg_stop', [], opts);
        state.awg_status = struct('status', 'ok', 'state', result.state, ...
            'health', struct('message', '已下载路由输出已停止。'));
        state.hardware_snapshot = result.state;
        state = update_output_tracking(state, result.state);
        message = '已下载路由输出已停止';
    catch exception
        message = sprintf('停止输出失败 [%s]：%s', ...
            exception.identifier, exception.message);
    end
else
    if ~download_binding_matches(state)
        state.busy = false; setappdata(fig, 'tx_workbench_state', state);
        update_action_states(fig);
        set_phase(fig, '没有与当前参数和路由匹配的已下载波形'); return;
    end
    set_phase(fig, '正在重新开启已下载波形');
    try
        opts = merge_struct(backend_parameters(state.params, state.backend_options), struct( ...
            'route', state.loaded_route, 'run_dir', state.last_run_dir, ...
            'expected_route', state.loaded_route, ...
            'expected_waveform_signature', state.loaded_waveform_signature));
        result = msiq.traditional_tx('awg_reuse', state.last_run_dir, opts);
        state.awg_status = struct('status', 'ok', 'state', result.state, ...
            'health', struct('message', '已复用下载波形并开始输出。'));
        state.hardware_snapshot = result.state;
        state = update_output_tracking(state, result.state);
        message = sprintf('%s 已重新开始输出', route_display(state.loaded_route));
    catch exception
        state.output_running = false;
        message = sprintf('开始输出失败 [%s]：%s', ...
            exception.identifier, exception.message);
    end
end
state.busy = false; setappdata(fig, 'tx_workbench_state', state);
render_awg_status(fig, state.awg_status); render_plan(fig);
update_action_states(fig); set_phase(fig, message);
end

function opts = backend_parameters(params, base)
opts = base;
names = {'route','rdiv','invert_i','invert_q','modulation_order', ...
    'master_sample_rate_hz','symbol_rate_hz','occupied_bandwidth_hz', ...
    'rate_authority','rolloff','rrc_span_symbols','peak_scale', ...
    'normalization_mode', ...
    'sync_length_symbols','sync_repeats','training_symbols', ...
    'pilot_interval_symbols','guard_symbols','ldpc_blocks_per_frame', ...
    'frame_repetitions','seed'};
for k = 1:numel(names), opts.(names{k}) = params.(names{k}); end
opts.all_channel_amplitude_vpp = params.amplitude_vpp;
opts.all_channel_offset_v = params.offset_v;
opts.all_channel_sample_clock_delay_samples = ...
    params.sample_clock_delay_samples;
channels = route_channels(params.route);
opts.amplitude_vpp = params.amplitude_vpp(channels);
opts.offset_v = params.offset_v(channels);
opts.sample_clock_delay_samples = params.sample_clock_delay_samples(channels);
opts.q_relative_delay_samples = 0;
opts.experiment_note = params.note;
end

function render_awg_status(fig, result)
state = getappdata(fig, 'tx_workbench_state');
if strcmpi(field_or(result, 'status', ''), 'ok') && ...
        isfield(result, 'state') && isstruct(result.state) && ...
        isfield(result.state, 'outputs')
    awg = result.state; state.connected = true; state.awg_status = result;
    state.hardware_snapshot = awg;
    state = update_output_tracking(state, awg);
    setappdata(fig, 'tx_workbench_state', state);
    set(state.ui.connection, 'String', 'AWG 已连接', 'ForegroundColor', [0.08 0.48 0.28]);
    set(state.ui.reconnect, 'Visible', 'off');
else
    state.connected = false; state.output_running = false; state.output_state = 'unknown';
    state.hardware_sync_state = 'disconnected'; state.hardware_snapshot = struct();
    setappdata(fig, 'tx_workbench_state', state);
    set(state.ui.connection, 'String', 'AWG 连接失败', 'ForegroundColor', [0.72 0.18 0.12]);
    set(state.ui.reconnect, 'Visible', 'on');
end
layout_ui(fig); update_current_hardware(fig);
end

function update_action_states(fig)
state = getappdata(fig, 'tx_workbench_state'); enabled = ~state.busy;
capacity_ok = isstruct(state.plan) && isfield(state.plan, 'preflight') && ...
    isfield(state.plan.preflight, 'ok') && state.plan.preflight.ok;
if state.plan_route_stale, capacity_ok = true; end
set(state.ui.preview, 'Enable', on_off_enable(enabled));
set(state.ui.download, 'Enable', on_off_enable(enabled && state.connected && ...
    state.plan_valid && ~state.waveform_stale && ...
    capacity_ok));
set(state.ui.retry_settings, 'Enable', on_off_enable(enabled));
if loaded_route_has_output(state)
    set(state.ui.output, 'String', '停止输出', ...
        'Enable', on_off_enable(enabled && state.connected));
else
    set(state.ui.output, 'String', '开始输出', ...
        'Enable', on_off_enable(enabled && state.connected && ...
        download_binding_matches(state) && loaded_trace_matches(state)));
end
current_outputs = selected_route_outputs(state, state.params.route);
set(state.ui.route, 'Enable', on_off_enable(enabled && ~any(current_outputs)));
set(state.ui.reconnect, 'Enable', on_off_enable(enabled));
[preview_hint, download_hint, output_hint] = button_hint_texts(state, capacity_ok);
set(state.ui.preview_hint, 'String', preview_hint);
set(state.ui.download_hint, 'String', download_hint);
set(state.ui.output_hint, 'String', output_hint);
end

function render_plan(fig)
state = getappdata(fig, 'tx_workbench_state'); params = state.params;
[awg_labels, awg_values, awg_tooltip] = awg_display_rows(state);
set_plan_rows(state.ui.plan_awg_labels, state.ui.plan_awg, ...
    awg_labels, awg_values);
set(state.ui.plan_awg, 'TooltipString', awg_tooltip);
set(state.ui.plan_awg_header, 'ForegroundColor', ternary(state.connected, ...
    [0.06 0.42 0.25], [0.42 0.45 0.47]));
status_color = [0.06 0.42 0.25];
if state.plan_valid && isfield(state.plan, 'preflight') && ...
        ~state.plan.preflight.ok && ~state.plan_route_stale
    status_color = [0.68 0.14 0.09];
elseif state.waveform_stale || ~state.plan_valid || state.plan_route_stale
    status_color = [0.68 0.39 0.04];
end
set(state.ui.plan_capacity_header, 'ForegroundColor', status_color);
set_plan_rows(state.ui.plan_fixed_labels, state.ui.plan_fixed, ...
    {'FEC'; 'RRC 跨度'; 'Seed'; '归一化'}, ...
    {'DVB-S2 9/10 · 1块/帧'; ...
    sprintf('%d 符号', params.rrc_span_symbols); ...
    sprintf('%d', params.seed); ...
    'I/Q 成对 · 100% 满量程'});
if isstruct(state.plan) && isfield(state.plan, 'waveform_sample_count')
    plan = state.plan;
    if state.plan_route_stale
        capacity_labels = {'状态'; '处理'};
        capacity_values = {'路由已变化'; '下载时按新路由复核'};
    else
        [capacity_labels, capacity_values] = capacity_display_rows( ...
            plan.memory_capacity);
    end
    set_plan_rows(state.ui.plan_capacity_labels, state.ui.plan_capacity, ...
        capacity_labels, capacity_values);
    set(state.ui.plan_capacity, 'TooltipString', ...
        capacity_tooltip_text(plan.memory_capacity));
    if state.plan_route_stale || state.waveform_stale || state.formal_plan_stale
        difference_labels = {'正式计划'};
        difference_values = {'待重新建立'};
    else
        difference_labels = {'公共状态'; '其他活动通道'};
        difference_values = {difference_text(plan.public_parameter_differences); ...
            vector_text(plan.affected_other_channels)};
    end
    set_plan_rows(state.ui.plan_changes_labels, state.ui.plan_changes, ...
        difference_labels, difference_values);
else
    set_plan_rows(state.ui.plan_capacity_labels, state.ui.plan_capacity, ...
        {'状态'}, {'尚未检查'});
    set(state.ui.plan_capacity, 'TooltipString', '');
    set_plan_rows(state.ui.plan_changes_labels, state.ui.plan_changes, ...
        {'正式计划'}, {'--'});
end
end

function [labels, values, tooltip] = awg_display_rows(state)
awg_cfg = field_or(state.cfg.instrument, 'awg', struct());
resource = char(string(field_or(awg_cfg, 'resource', '--')));
reference = char(string(field_or(awg_cfg, ...
    'reference_clock_source', '本机配置')));
labels = {'IDN'; '地址'; '参考时钟'; 'DAC 模式'; 'RDIV'; 'Raster'; ...
    'CH1 / CH2'; 'CH3 / CH4'};
values = {'--'; compact_resource(resource); reference; '--'; '--'; '--'; ...
    '-- / --'; '-- / --'};
tooltip = sprintf('地址：%s', resource);
if ~state.connected || ~isfield(state.awg_status, 'state') || ...
        ~isstruct(state.awg_status.state)
    return;
end
awg = state.awg_status.state;
idn = char(string(field_or(awg, 'idn', '--')));
outputs = logical(field_or(awg, 'outputs', false(1,4)));
if numel(outputs) ~= 4, outputs = false(1,4); end
raster_hz = numeric_or(field_or(awg, 'raster_hz', NaN), NaN);
values = {compact_idn(idn); compact_resource(resource); reference; ...
    char(string(field_or(awg, 'dac_mode', '--'))); ...
    char(string(field_or(awg, 'rdiv', '--'))); ...
    finite_rate_text(raster_hz); ...
    sprintf('%s / %s', on_off_cn(outputs(1)), on_off_cn(outputs(2))); ...
    sprintf('%s / %s', on_off_cn(outputs(3)), on_off_cn(outputs(4)))};
tooltip = sprintf('IDN：%s\n地址：%s', idn, resource);
end

function value = compact_idn(raw)
parts = strsplit(char(string(raw)), ',');
if numel(parts) >= 3
    value = sprintf('%s · %s', strtrim(parts{2}), strtrim(parts{3}));
else
    value = compact_text(raw, 24);
end
end

function value = compact_resource(raw)
parts = strsplit(char(string(raw)), '::');
if numel(parts) >= 3
    value = sprintf('%s · %s', strtrim(parts{2}), strtrim(parts{3}));
else
    value = compact_text(raw, 24);
end
end

function value = compact_text(raw, limit)
value = char(string(raw));
if numel(value) > limit, value = [value(1:limit-3), '...']; end
end

function value = finite_rate_text(rate_hz)
if isfinite(rate_hz), value = sprintf('%.6g GSa/s', rate_hz/1e9);
else, value = '--'; end
end

function value = on_off_cn(enabled)
value = ternary(logical(enabled), '开', '关');
end

function [labels, values] = capacity_display_rows(capacity)
channels = capacity.selected_channels;
per_channel = capacity.per_channel;
channel_modes = arrayfun(@(entry) sprintf('CH%d %s', ...
    entry.channel, entry.memory_mode), per_channel, 'UniformOutput', false);
labels = {'目标内存'};
values = {strjoin(channel_modes, ' · ')};
for index = 1:numel(channels)
    entry = per_channel(index);
    usage_percent = 100*entry.required_samples/entry.available_samples;
    labels{end+1,1} = sprintf('CH%d 使用', entry.channel); %#ok<AGROW>
    values{end+1,1} = sprintf('%s 点 · %s', ...
        grouped_integer(entry.required_samples), ...
        percentage_text(usage_percent)); %#ok<AGROW>
    labels{end+1,1} = sprintf('CH%d 可用', entry.channel); %#ok<AGROW>
    values{end+1,1} = sprintf('%.4g GSa', ...
        entry.available_samples/1e9); %#ok<AGROW>
end
labels{end+1,1} = '依据';
values{end+1,1} = short_capacity_source(capacity);
labels{end+1,1} = '结果';
values{end+1,1} = ternary(capacity.ok, '通过', '不通过 · 禁止下载');
end

function value = capacity_tooltip_text(capacity)
lines = cell(1, numel(capacity.per_channel)+1);
for index = 1:numel(capacity.per_channel)
    entry = capacity.per_channel(index);
    lines{index} = sprintf('CH%d: 需要 %s 点，可用 %s 点', ...
        entry.channel, grouped_integer(entry.required_samples), ...
        grouped_integer(entry.available_samples));
end
lines{end} = capacity.message;
value = strjoin(lines, newline);
end

function value = grouped_integer(number)
digits = sprintf('%.0f', number);
groups = {};
while numel(digits) > 3
    groups = [{digits(end-2:end)}, groups]; %#ok<AGROW>
    digits = digits(1:end-3);
end
value = strjoin([{digits}, groups], ',');
end

function value = percentage_text(percent)
if percent < 0.01
    value = sprintf('%.4f%%', percent);
elseif percent < 1
    value = sprintf('%.3f%%', percent);
else
    value = sprintf('%.1f%%', percent);
end
end

function value = short_capacity_source(capacity)
switch capacity.capacity_source_code
    case 'keysight_16g_option'
        value = '16G 选件';
    case 'keysight_standard_no_16g'
        value = '标准 2 GSa（未检出 16G）';
    case 'keysight_standard_query_fallback'
        value = '标准 2 GSa（查询回退）';
    otherwise
        value = '标准 2 GSa（离线）';
end
end

function render_plan_error(fig, exception)
state = getappdata(fig, 'tx_workbench_state');
set(state.ui.plan_capacity_header, 'ForegroundColor', [0.68 0.14 0.09]);
set_plan_rows(state.ui.plan_capacity_labels, state.ui.plan_capacity, ...
    {'错误'; '详情'}, {exception.identifier; exception.message});
set(state.ui.plan_capacity, 'TooltipString', exception.message);
end

function render_preview(fig, plan)
state = getappdata(fig, 'tx_workbench_state'); if ~isfield(plan, 'waveforms'), return; end
try
    msiq.plotting.tx_dashboard('', plan, struct('target_axes', state.ui.axes, 'status', 'preview'));
    layout_ui(fig);
catch exception
    for k = 1:numel(state.ui.axes)
        cla(state.ui.axes(k)); axis(state.ui.axes(k), 'off');
        text(state.ui.axes(k), 0.5, 0.5, {'图组生成失败', exception.message}, ...
            'Units', 'normalized', 'HorizontalAlignment', 'center', ...
            'VerticalAlignment', 'middle', 'Color', [0.70 0.12 0.08], ...
            'Interpreter', 'none');
    end
end
update_dashboard_title(fig);
drawnow;
end

function set_phase(fig, text_value)
if ~ishghandle(fig), return; end
state = getappdata(fig, 'tx_workbench_state');
if isfield(state.ui, 'phase') && ishghandle(state.ui.phase)
    set(state.ui.phase, 'String', ['阶段：', text_value]);
end
drawnow limitrate;
end

function schedule(fig, delay, callback)
timer_obj = timer('ExecutionMode', 'singleShot', 'StartDelay', max(0.01, delay), ...
    'TimerFcn', callback, 'ErrorFcn', @(~,event) set_phase(fig, ...
    ['启动任务失败：', event.Data.Message]));
setappdata(fig, 'tx_workbench_timer', timer_obj); start(timer_obj);
end

function params = load_local_parameters(defaults, options)
params = defaults;
if ~options.persist_parameters, return; end
path = options.parameter_record_path; if ~isfile(path), return; end
try
    loaded = load(path, 'params');
    if isfield(loaded, 'params') && isstruct(loaded.params) && isscalar(loaded.params)
        params = merge_struct(defaults, loaded.params);
    end
catch
    params = defaults;
end
end

function save_local_parameters(state)
if ~state.persist_parameters, return; end
params = state.params;
path = state.parameter_record_path; folder = fileparts(path);
if ~isfolder(folder)
    [ok, ~] = mkdir(folder);
    if ~ok, return; end
end
try
    save(path, 'params', '-v7');
catch
end
end

function path = local_parameter_path()
path = fullfile(msiq.project_root(), 'tx_records', 'tx_workbench_last.mat');
end

function matches = hardware_target_matches(awg, params)
matches = false(1,2);
if ~isstruct(awg) || ~isfield(awg, 'traces') || numel(awg.traces) ~= 4, return; end
channels = route_channels(params.route);
for k = 1:2
    channel = channels(k); trace = awg.traces(channel);
    matches(k) = abs(trace.amplitude_vpp-params.amplitude_vpp(channel)) <= 1e-9 && ...
        abs(trace.offset_v-params.offset_v(channel)) <= 1e-9 && ...
        trace.sample_clock_delay_samples == params.sample_clock_delay_samples(channel);
end
end

function signature = waveform_signature(params)
value = struct('rdiv', params.rdiv, ...
    'invert_i', false, 'invert_q', false, ...
    'modulation_order', params.modulation_order, ...
    'master_sample_rate_hz', params.master_sample_rate_hz, ...
    'symbol_rate_hz', params.symbol_rate_hz, ...
    'occupied_bandwidth_hz', params.occupied_bandwidth_hz, ...
    'rolloff', params.rolloff, 'rrc_span_symbols', params.rrc_span_symbols, ...
    'normalization_mode', params.normalization_mode, ...
    'sync_length_symbols', params.sync_length_symbols, ...
    'sync_repeats', params.sync_repeats, 'training_symbols', params.training_symbols, ...
    'pilot_interval_symbols', params.pilot_interval_symbols, ...
    'guard_symbols', params.guard_symbols, ...
    'ldpc_blocks_per_frame', params.ldpc_blocks_per_frame, ...
    'frame_repetitions', params.frame_repetitions, 'seed', params.seed);
signature = msiq.sha256_bytes(jsonencode(value));
end

function state = clear_loaded_binding(state)
state.loaded_signature = '';
state.loaded_waveform_signature = '';
state.loaded_route = '';
state.last_run_dir = '';
state.output_running = false;
state.output_state = 'stopped';
end

function column = hardware_field_column(name)
names = {'amplitude_vpp','offset_v','sample_clock_delay_samples'};
column = find(strcmp(names, name), 1);
if isempty(column)
    error('msiq:txWorkbench:HardwareField', 'Unknown hardware field: %s.', name);
end
end

function name = hardware_field_name(column)
names = {'amplitude_vpp','offset_v','sample_clock_delay_samples'};
name = names{column};
end

function label = hardware_field_label(name)
switch name
    case 'amplitude_vpp', label = 'Vpp';
    case 'offset_v', label = 'Offset';
    case 'sample_clock_delay_samples', label = '采样时钟延时';
    otherwise, label = '设置';
end
end

function command = hardware_command_text(params, channel, name)
value = params.(name); value = value(channel);
switch name
    case 'amplitude_vpp'
        command = sprintf(':VOLTage%d:AMPLitude %.15g', channel, value);
    case 'offset_v'
        command = sprintf(':VOLTage%d:OFFSet %.15g', channel, value);
    case 'sample_clock_delay_samples'
        command = sprintf(':ARM:SDELay%d %d', channel, value);
    otherwise
        command = '';
end
end

function name = hardware_trace_field(name)
if ~ismember(name, {'amplitude_vpp','offset_v','sample_clock_delay_samples'})
    error('msiq:txWorkbench:HardwareField', 'Unknown hardware field: %s.', name);
end
end

function yes = hardware_field_matches(state, channel, field_index)
yes = false;
if ~state.connected || ~isfield(state.awg_status, 'state') || ...
        ~isfield(state.awg_status.state, 'traces') || ...
        numel(state.awg_status.state.traces) ~= 4
    return;
end
name = hardware_field_name(field_index);
actual = state.awg_status.state.traces(channel).(hardware_trace_field(name));
target = state.params.(name); target = target(channel);
if strcmp(name, 'sample_clock_delay_samples')
    yes = isfinite(actual) && actual == target;
else
    yes = isfinite(actual) && abs(actual-target) <= 1e-9;
end
end

function [channel, field_index] = first_dirty_hardware_field(dirty)
linear = find(dirty, 1, 'first');
if isempty(linear)
    error('msiq:txWorkbench:HardwareQueue', 'No hardware field is waiting to be written.');
end
[channel, field_index] = ind2sub(size(dirty), linear);
end

function route = route_for_channel(channel)
if ismember(channel, [1 2])
    route = 'pair_a_ch1_ch2';
elseif ismember(channel, [3 4])
    route = 'pair_b_ch3_ch4';
else
    error('msiq:txWorkbench:PhysicalChannel', 'Physical channel must be 1 through 4.');
end
end

function opts = hardware_backend_options(params, base, route)
local = params; local.route = route;
opts = backend_parameters(local, base);
end

function value = hardware_match_state(awg, params)
value = ternary(all(hardware_target_matches(awg, params)), 'synced', 'different');
end

function state = update_output_tracking(state, awg)
if ~isstruct(awg) || ~isfield(awg, 'outputs') || numel(awg.outputs) ~= 4
    state.output_state = 'unknown'; state.output_running = false; return;
end
if isempty(state.loaded_route)
    channels = route_channels(state.params.route);
else
    channels = route_channels(state.loaded_route);
end
mask = logical(awg.outputs(channels));
if all(mask)
    state.output_state = 'both';
elseif mask(1)
    state.output_state = 'i_only';
elseif mask(2)
    state.output_state = 'q_only';
else
    state.output_state = 'stopped';
end
state.output_running = ~isempty(state.loaded_route) && any(mask);
end

function yes = loaded_route_has_output(state)
yes = false;
if isempty(state.loaded_route) || ~state.connected || ...
        ~isfield(state.awg_status, 'state') || ...
        ~isfield(state.awg_status.state, 'outputs')
    return;
end
yes = any(logical(state.awg_status.state.outputs(route_channels(state.loaded_route))));
end

function values = selected_route_outputs(state, route)
values = false(1,2);
if state.connected && isfield(state.awg_status, 'state') && ...
        isfield(state.awg_status.state, 'outputs') && ...
        numel(state.awg_status.state.outputs) == 4
    values = logical(state.awg_status.state.outputs(route_channels(route)));
end
end

function yes = download_binding_matches(state)
yes = state.plan_valid && ~state.waveform_stale && ...
    ~isempty(state.last_run_dir) && isfolder(state.last_run_dir) && ...
    ~isempty(state.loaded_route) && strcmp(state.loaded_route, state.params.route) && ...
    ~isempty(state.loaded_signature) && ...
    strcmp(state.waveform_signature, state.preview_signature) && ...
    strcmp(state.waveform_signature, state.loaded_signature) && ...
    ~isempty(state.loaded_waveform_signature);
end

function yes = loaded_trace_matches(state)
yes = false;
if ~download_binding_matches(state) || ~state.connected || ...
        ~isfield(state.awg_status, 'state') || ...
        ~isfield(state.plan, 'desired') || ~isfield(state.plan, 'route') || ...
        ~strcmp(state.plan.route.name, state.loaded_route)
    return;
end
awg = state.awg_status.state; desired = state.plan.desired;
route = state.plan.route; channels = route.awg_channels;
yes = strcmpi(awg.dac_mode, desired.dac_mode) && ...
    strcmpi(awg.rdiv, desired.rdiv) && isfinite(awg.raster_hz) && ...
    abs(awg.raster_hz-desired.raster_hz) <= 1;
for index = 1:numel(channels)
    channel = channels(index); trace = awg.traces(channel);
    yes = yes && strcmpi(trace.memory_mode, desired.memory_mode) && ...
        isfinite(trace.selected_segment) && trace.selected_segment == desired.segment && ...
        isfinite(trace.segment) && trace.segment == desired.segment && ...
        isfinite(trace.length) && ...
        trace.length == desired.required_samples_per_channel(index) && ...
        isfinite(trace.amplitude_vpp) && ...
        abs(trace.amplitude_vpp-state.params.amplitude_vpp(channel)) <= 1e-9 && ...
        isfinite(trace.offset_v) && ...
        abs(trace.offset_v-state.params.offset_v(channel)) <= 1e-9 && ...
        isfinite(trace.sample_clock_delay_samples) && ...
        trace.sample_clock_delay_samples == ...
        state.params.sample_clock_delay_samples(channel);
end
if yes && isfield(desired, 'channel_memory_modes')
    for channel = 1:4
        yes = yes && strcmpi(awg.traces(channel).memory_mode, ...
            desired.channel_memory_modes{channel});
    end
end
end

function [preview, download, output] = button_hint_texts(state, capacity_ok)
preview = '';
if state.busy
    preview = '操作进行中';
end
if state.busy
    download = '操作进行中';
elseif ~state.connected
    download = 'AWG 未连接';
elseif ~state.plan_valid
    download = '尚无预览';
elseif state.waveform_stale
    download = '预览已过期';
elseif ~capacity_ok
    download = '容量不足';
else
    download = '';
end
if state.busy
    output = '操作进行中';
elseif ~state.connected
    output = 'AWG 未连接';
elseif loaded_route_has_output(state)
    output = ternary(download_binding_matches(state), ...
        '当前波形', '正在输出旧波形');
elseif ~download_binding_matches(state)
    output = '没有匹配的已下载波形';
elseif ~loaded_trace_matches(state)
    output = 'AWG trace 不匹配';
else
    output = '';
end
end

function value = route_display(route)
channels = route_channels(route);
value = sprintf('CH%d/CH%d', channels(1), channels(2));
end

function set_plan_rows(label_control, value_control, labels, values)
labels = cellstr(string(labels(:)));
values = cellstr(string(values(:)));
if numel(labels) ~= numel(values)
    error('msiq:txWorkbench:PlanRows', ...
        'Plan-section labels and values must have equal lengths.');
end
if isempty(labels)
    labels = {'--'};
    values = {'--'};
end
set(label_control, 'String', labels);
set(value_control, 'String', values);
end

function update_dashboard_title(fig)
state = getappdata(fig, 'tx_workbench_state');
suffix = '';
color = [0.08 0.18 0.25];
if state.waveform_stale && state.plan_valid
    suffix = ' · 旧预览'; color = [0.72 0.42 0.08];
end
set(state.ui.dashboard_title, 'String', sprintf('发射波形检测%s', suffix), ...
    'ForegroundColor', color);
end

function stop_app_timer(fig, key)
if ~ishghandle(fig), return; end
timer_obj = getappdata(fig, key);
if isempty(timer_obj), return; end
rmappdata(fig, key);
delete_timer(timer_obj);
end

function delete_timer(timer_obj)
try
    if ~isempty(timer_obj) && isvalid(timer_obj)
        stop(timer_obj); delete(timer_obj);
    end
catch
end
end

function channels = route_channels(route)
if strcmpi(char(string(route)), 'pair_b_ch3_ch4'), channels = [3 4];
else, channels = [1 2]; end
end

function out = merge_struct(base, extra)
out = base; if ~isstruct(extra) || ~isscalar(extra), return; end
names = fieldnames(extra);
for k = 1:numel(names), out.(names{k}) = extra.(names{k}); end
end

function text_value = difference_text(value)
if ~isstruct(value) || isempty(fieldnames(value)), text_value = 'AWG 未连接'; return; end
names = fieldnames(value); changed = names(structfun(@logical, value));
if isempty(changed), text_value = '无'; else, text_value = strjoin(changed, ', '); end
end

function value = short_hash(value)
value = char(string(value)); if numel(value) > 12, value = [value(1:12), '...']; end
end

function value = vector_text(numbers)
if isempty(numbers), value = '无'; else, value = strjoin(cellstr(string(numbers(:).')), ', '); end
end

function value = connection_failure_text(status)
identifier = field_or(status, 'identifier', '');
message = field_or(status, 'error', 'AWG 未连接');
if isempty(identifier)
    value = message;
else
    value = sprintf('AWG 连接失败 [%s]：%s', identifier, message);
end
end

function value = number_text(number)
value = sprintf('%.12g', double(number));
end

function value = finite_text(number)
if isfinite_scalar(number), value = sprintf('%.6g', double(number)); else, value = '--'; end
end

function yes = isfinite_scalar(value)
yes = isnumeric(value) && isscalar(value) && isfinite(value);
end

function value = logical_value(options, name, fallback)
value = field_or(options, name, fallback);
if ~(islogical(value) || isnumeric(value)) || ~isscalar(value)
    error('msiq:txWorkbench:Options', '%s must be scalar logical.', name);
end
value = logical(value);
end

function value = numeric_value(options, name, fallback)
value = double(field_or(options, name, fallback));
if ~isscalar(value) || ~isfinite(value) || value < 0
    error('msiq:txWorkbench:Options', '%s must be a nonnegative scalar.', name);
end
end

function value = numeric_or(value, fallback)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value), value = fallback; end
end

function value = field_or(source, name, fallback)
if isstruct(source) && isfield(source, name) && ~isempty(source.(name))
    value = source.(name);
else
    value = fallback;
end
end

function value = on_off_enable(flag)
if logical(flag), value = 'on'; else, value = 'off'; end
end

function value = ternary(condition, yes_value, no_value)
if condition, value = yes_value; else, value = no_value; end
end

function set_chinese_font()
try
    set(0, 'DefaultAxesFontName', 'Microsoft YaHei UI', ...
        'DefaultTextFontName', 'Microsoft YaHei UI', ...
        'DefaultUicontrolFontName', 'Microsoft YaHei UI');
catch
end
end
