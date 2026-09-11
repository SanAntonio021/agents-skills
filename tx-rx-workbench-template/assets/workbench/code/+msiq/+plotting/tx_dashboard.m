function details = tx_dashboard(output_path, plan, execution)
%TX_DASHBOARD Export the traditional TX frame, mapping, and spectrum views.

if nargin < 2 || ~isstruct(plan)
    plan = struct();
end
if nargin < 3 || ~isstruct(execution)
    execution = struct();
end

% The GUI supplies four existing axes so it can reuse this exact layout and
% drawing logic without creating a temporary figure or writing a PNG.
target_axes = field_or(execution, 'target_axes', gobjects(0));
if ~isempty(target_axes)
    target_axes = target_axes(:);
    if numel(target_axes) < 4 || ~all(ishghandle(target_axes(1:4)))
        error('msiq:txDashboard:TargetAxes', ...
            'GUI rendering requires four valid target axes.');
    end
    target_axes = target_axes(1:4);
    for k = 1:numel(target_axes)
        clear_axis_content(target_axes(k));
    end
    draw_frame_overview(target_axes(1), plan, true);
    draw_payload_occupancy(target_axes(2), plan);
    draw_digital_spectrum(target_axes(3), plan, 'near', true);
    draw_digital_spectrum(target_axes(4), plan, 'full', true);
    drawnow;
    render_status = lower(char(string(field_or(execution, 'status', 'rendered'))));
    if isempty(render_status)
        render_status = 'rendered';
    end
    details = struct('output_path', '', 'status', render_status, ...
        'panel_count', 4, 'resolution_dpi', NaN);
    return;
end

output_path = char(string(output_path));
[output_dir, ~, extension] = fileparts(output_path);
if isempty(extension)
    output_path = [output_path, '.png'];
end
if ~isempty(output_dir) && ~isfolder(output_dir)
    [ok, message] = mkdir(output_dir);
    if ~ok
        error('msiq:txDashboard:Directory', ...
            'Cannot create dashboard directory %s: %s.', output_dir, message);
    end
end

fig = figure('Visible', 'off', 'Color', 'w', ...
    'Position', [60 60 1800 1800], 'InvertHardcopy', 'off');
cleanup = onCleanup(@() close_if_valid(fig));
set(fig, 'DefaultAxesFontName', 'Microsoft YaHei UI', ...
    'DefaultTextFontName', 'Microsoft YaHei UI', ...
    'DefaultAxesFontSize', 9);

sgtitle(fig, sprintf('传统 %s 发射图组', modulation_text(plan)), ...
    'FontName', 'Microsoft YaHei UI', 'FontSize', 16, 'FontWeight', 'bold', ...
    'Interpreter', 'none');

draw_frame_overview(axes('Parent', fig, 'Position', [0.040 0.655 0.630 0.255]), plan, false);
draw_payload_occupancy(axes('Parent', fig, 'Position', [0.715 0.695 0.220 0.215]), plan);
draw_digital_spectrum(axes('Parent', fig, 'Position', [0.085 0.390 0.840 0.220]), plan, 'near', false);
draw_digital_spectrum(axes('Parent', fig, 'Position', [0.085 0.080 0.840 0.220]), plan, 'full', false);

% Preserve the designed 96-dpi canvas independently of screen fitting.
set(fig,'PaperUnits','inches','PaperSize',[1800 1800]/96, ...
    'PaperPosition',[0 0 1800 1800]/96,'PaperPositionMode','manual');
archive_dir=fullfile(output_dir,'data');
if ~isfolder(archive_dir), archive_dir=fullfile(output_dir,'diagnostics'); end
msiq.plotting.save_replot_figure(fig,output_path,180);
plot_cleanup=msiq.plot_archive('begin',output_dir,archive_dir); %#ok<NASGU>
if ~msiq.plot_archive('export',fig,output_path,'print',180)
    print(fig, output_path, '-dpng', '-r180');
end
render_status = lower(char(string(field_or(execution, 'status', 'rendered'))));
if isempty(render_status)
    render_status = 'rendered';
end
details = struct('output_path', output_path, 'status', render_status, ...
    'panel_count', 4, 'resolution_dpi', 180);
clear cleanup;
end

function draw_frame_overview(ax, plan, embedded_workbench)
tx_ref = field_or(plan, 'tx_ref', struct());
frame = field_or(tx_ref, 'frame', struct());
if ~isstruct(frame) || isempty(field_or(frame, 'symbol_count', []))
    placeholder(ax, '帧结构数据不可用');
    return;
end

guard = integer_or(field_or(frame, 'guard_symbols', NaN), 0);
sync_length = integer_or(field_or(frame, 'sync_length', NaN), 0);
sync_repeats = integer_or(field_or(frame, 'sync_repeats', NaN), 0);
training = integer_or(field_or(frame, 'training_length', NaN), 0);
service = integer_or(field_or(frame, 'service_length', NaN), 0);
frame_count = integer_or(field_or(frame, 'symbol_count', NaN), 0);
frame_repetitions = max(1, integer_or(field_or(frame, ...
    'frame_repetitions', NaN), 1));
sync = sync_length * sync_repeats;
payload = count_frame_positions(frame, 'payload_positions_frame');
pilots = count_frame_positions(frame, 'pilot_positions_frame');
if payload <= 0
    data = plot_data(plan);
    payload = numel(field_or(data, 'payload_symbols', complex([])));
end
if pilots <= 0
    data = plot_data(plan);
    pilots = numel(field_or(data, 'pilot_symbols', complex([])));
end

clear_axis_content(ax);
axis(ax, [0 1 0 1]);
axis(ax, 'off');
hold(ax, 'on');
pixel_position = getpixelposition(ax);
very_compact = pixel_position(3) < 260;
if pixel_position(3) < 340
    frame_title = '1 帧结构与下载流程';
else
    frame_title = '1 总帧组成与 AWG 下载流程';
end
title(ax, frame_title, 'FontWeight', 'bold');

segment_values = [guard sync training service guard];
segment_colors = [ ...
    0.86 0.86 0.86; ...
    0.98 0.76 0.42; ...
    0.72 0.62 0.88; ...
    0.42 0.68 0.90; ...
    0.86 0.86 0.86];
bar_left = 0.055;
bar_width = 0.89;
bar_bottom = 0.72;
bar_height = 0.18;
segment_widths = bar_width * segment_values / max(sum(segment_values), 1);
% Keep short sections wide enough for their in-frame labels.
minimum_width = 0.15;
segment_widths = max(segment_widths, minimum_width);
segment_widths = bar_width * segment_widths / sum(segment_widths);
compact_labels = pixel_position(3) < 820;
service_label = service_segment_label(frame, service, payload, pilots);
if compact_labels
    segment_texts = { ...
        sprintf('保护\n%d', guard), ...
        sprintf('ZC×%d\n%d', sync_repeats, sync), ...
        sprintf('训练\n%d', training), ...
        sprintf('业务\n%d', service), ...
        sprintf('保护\n%d', guard)};
else
    segment_texts = { ...
        sprintf('前保护\n%d 符号', guard), ...
        sprintf('重复 ZC\n%d 符号', sync), ...
        sprintf('训练\n%d 符号', training), ...
        service_label, ...
        sprintf('后保护\n%d 符号', guard)};
end
x = bar_left;
for index = 1:numel(segment_values)
    width = segment_widths(index);
    rectangle(ax, 'Position', [x bar_bottom width bar_height], ...
        'FaceColor', segment_colors(index,:), ...
        'EdgeColor', [0.35 0.35 0.35], 'LineWidth', 0.8);
    label_font = 7.0;
    if compact_labels
        label_font = 6.2;
    end
    if ~very_compact
        text(ax, x + width/2, bar_bottom + bar_height/2, segment_texts{index}, ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
            'FontSize', label_font, 'Interpreter', 'none');
    end
    x = x + width;
end
text(ax, bar_left, 0.925, sprintf('逻辑帧：%d 符号，重复 %d 次', frame_count, frame_repetitions), ...
    'HorizontalAlignment', 'left', 'FontSize', 8.2, 'Interpreter', 'none');

if very_compact
    draw_compact_frame_flow(ax, plan, frame_repetitions, embedded_workbench);
    hold(ax, 'off');
    return;
end

% Lower strip: every arrow is on one center line and touches node boundaries.
% Compact GUI axes need a little more separation below the frame summary.
if compact_labels
    node_y = 0.38;
else
    node_y = 0.42;
end
node_h = 0.22;
frame_node = [0.050 node_y 0.19 node_h];
rrc_node = [0.285 node_y 0.14 node_h];
baseband_node = [0.475 node_y 0.16 node_h];
iq_node = [0.650 node_y 0.13 node_h];
awg_node = [0.830 node_y 0.15 node_h];
draw_frame_copies(ax, frame_node, frame_repetitions, compact_labels);
if compact_labels
    rrc_label = 'RRC';
    baseband_label = '复基带';
else
    rrc_label = 'RRC\n成形';
    baseband_label = '零中频\n复信号';
end
draw_flow_node(ax, rrc_node, rrc_label, [0.94 0.90 0.68]);
draw_flow_node(ax, baseband_node, baseband_label, [0.70 0.84 0.94]);
[i_factor, q_factor] = polarity_factors(plan);
if i_factor == 1 && q_factor == 1
    iq_label = 'I/Q\n输出';
else
    iq_label = sprintf('I %s\nQ %s', polarity_word(i_factor), ...
        polarity_word(q_factor));
end
draw_flow_node(ax, iq_node, iq_label, [0.77 0.88 0.78]);

samples = field_or(field_or(plan, 'waveforms', struct()), 'awg_dac_data', []);
valid_count = integer_or(field_or(plan, 'waveform_sample_count', ...
    size(samples, 1)), size(samples, 1));
padded_count = integer_or(field_or(plan, 'padded_sample_count', ...
    valid_count), valid_count);
if padded_count < valid_count
    padded_count = valid_count;
end
draw_awg_storage(ax, awg_node, valid_count, padded_count, compact_labels);
draw_flow_arrow(ax, frame_node(1)+frame_node(3), rrc_node(1), node_y+node_h/2);
draw_flow_arrow(ax, rrc_node(1)+rrc_node(3), baseband_node(1), node_y+node_h/2);
draw_flow_arrow(ax, baseband_node(1)+baseband_node(3), iq_node(1), node_y+node_h/2);
draw_flow_arrow(ax, iq_node(1)+iq_node(3), awg_node(1), node_y+node_h/2);

waveforms = field_or(plan, 'waveforms', struct());
rate = double(field_or(waveforms, 'awg_sample_rate_hz', NaN));
duration = double(field_or(plan, 'waveform_duration_s', NaN));
if ~isfinite(duration) && isfinite(rate) && valid_count > 0
    duration = valid_count / rate;
end
metrics = awg_metrics(plan);
levels = field_or(plan, 'levels', struct());
if embedded_workbench
    note_top = sprintf('波形时长 %.3f us', duration*1e6);
    note_bottom = sprintf('PAPR %.2f dB', metrics.papr_db);
else
    note_top = sprintf('AWG 采样率 %.3f GSa/s | 波形时长 %.3f us', ...
        rate/1e9, duration*1e6);
    note_bottom = sprintf('Vpp %s V | Offset %s V | PAPR %.2f dB', ...
        vector_text(field_or(levels, 'amplitude_vpp', [])), ...
        vector_text(field_or(levels, 'offset_v', [])), ...
        metrics.papr_db);
end
if metrics.clipping_samples > 0
    note_bottom = sprintf('%s | 数字样点超限 %d', ...
        note_bottom, metrics.clipping_samples);
end
note_font = 7.0;
if very_compact
    note_top = sprintf('%.3f GSa/s  %.3f us', rate/1e9, duration*1e6);
    if embedded_workbench
        note_top = sprintf('波形时长 %.3f us', duration*1e6);
    end
    note_bottom = sprintf('PAPR %.2f dB', metrics.papr_db);
    if metrics.clipping_samples > 0
        note_bottom = sprintf('%s  样点超限 %d', ...
            note_bottom, metrics.clipping_samples);
    end
    note_font = 6.5;
end

text(ax, 0.050, 0.335, note_top, 'FontSize', note_font, ...
    'Color', [0.20 0.20 0.20], 'Interpreter', 'none', 'Clipping', 'on');
text(ax, 0.050, 0.255, note_bottom, 'FontSize', note_font, ...
    'Color', [0.20 0.20 0.20], 'Interpreter', 'none', 'Clipping', 'on');
hold(ax, 'off');
end

function draw_compact_frame_flow(ax, plan, repeat_count, embedded_workbench)
samples = field_or(field_or(plan, 'waveforms', struct()), 'awg_dac_data', []);
valid_count = integer_or(field_or(plan, 'waveform_sample_count', ...
    size(samples, 1)), size(samples, 1));
padded_count = max(valid_count, integer_or(field_or(plan, ...
    'padded_sample_count', valid_count), valid_count));
node_y = 0.40;
node_h = 0.20;
frame_node = [0.06 node_y 0.24 node_h];
rrc_node = [0.40 node_y 0.18 node_h];
awg_node = [0.68 node_y 0.26 node_h];
draw_flow_node(ax, frame_node, sprintf('逻辑帧\n×%d', repeat_count), ...
    [0.70 0.84 0.94]);
draw_flow_node(ax, rrc_node, 'RRC', [0.94 0.90 0.68]);
draw_awg_storage(ax, awg_node, valid_count, padded_count, true);
draw_flow_arrow(ax, frame_node(1)+frame_node(3), rrc_node(1), node_y+node_h/2);
draw_flow_arrow(ax, rrc_node(1)+rrc_node(3), awg_node(1), node_y+node_h/2);
waveforms = field_or(plan, 'waveforms', struct());
rate = double(field_or(waveforms, 'awg_sample_rate_hz', NaN));
duration = double(field_or(plan, 'waveform_duration_s', NaN));
metrics = awg_metrics(plan);
if embedded_workbench
    rate_text = sprintf('波形时长 %.3f us', duration*1e6);
else
    rate_text = sprintf('%.3f GSa/s · %.3f us', rate/1e9, duration*1e6);
end
text(ax, 0.06, 0.31, rate_text, 'FontSize', 6.5, ...
    'Color', [0.20 0.20 0.20], 'Interpreter', 'none', 'Clipping', 'on');
text(ax, 0.06, 0.23, sprintf('PAPR %.2f dB', metrics.papr_db), ...
    'FontSize', 6.5, 'Color', [0.20 0.20 0.20], ...
    'Interpreter', 'none', 'Clipping', 'on');
end

function value = polarity_word(factor)
if factor < 0
    value = '反相';
else
    value = '正常';
end
end

function label = service_segment_label(frame, service, payload, pilots)
summary = sprintf('共 %d 导频 / %d 数据', pilots, payload);
pilot_positions = double(field_or(frame, 'pilot_positions_frame', []));
service_start = integer_or(field_or(frame, 'service_start', NaN), 0);
pilot_positions = sort(unique(round(pilot_positions(:))));
relative_positions = pilot_positions - service_start + 1;
relative_positions = relative_positions(relative_positions >= 1 & ...
    relative_positions <= service);

if service_start <= 0 || isempty(relative_positions) || ...
        relative_positions(1) ~= 1
    label = sprintf('业务区 %d 符号\n导频与数据周期交织\n%s', ...
        service, summary);
    return;
end

data_runs = diff([relative_positions; service + 1]) - 1;
if numel(data_runs) > 1 && all(data_runs(1:end-1) == data_runs(1))
    regular_run = data_runs(1);
    tail_run = data_runs(end);
    if tail_run == regular_run
        pattern = sprintf('（导频 1 + 数据 %d）重复', regular_run);
    else
        pattern = sprintf('导频 1 + 数据 %d | ... | 导频 1 + 数据 %d', ...
            regular_run, tail_run);
    end
else
    pattern = '导频与数据非等间隔交织';
end
label = sprintf('业务区 %d 符号\n%s\n%s', service, pattern, summary);
end

function draw_frame_copies(ax, position, repeat_count, compact)
if nargin < 4, compact = false; end
rectangle(ax, 'Position', position, 'FaceColor', [0.70 0.84 0.94], ...
    'EdgeColor', [0.25 0.40 0.55], 'LineWidth', 0.9);
label = sprintf('逻辑帧序列\n重复 %d 次', repeat_count);
font_size = 8.0;
if compact
    label = sprintf('逻辑帧\n×%d', repeat_count);
    font_size = 7.0;
end
text(ax, position(1)+position(3)/2, position(2)+position(4)/2, ...
    label, ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
    'FontSize', font_size, 'Interpreter', 'none');
end

function draw_flow_node(ax, position, label, color)
rectangle(ax, 'Position', position, 'FaceColor', color, ...
    'EdgeColor', [0.35 0.35 0.35], 'LineWidth', 0.8);
text(ax, position(1) + position(3)/2, position(2) + position(4)/2, ...
    sprintf(label), 'HorizontalAlignment', 'center', ...
    'VerticalAlignment', 'middle', 'FontSize', 8, 'Interpreter', 'none');
end

function draw_flow_arrow(ax, x_start, x_end, y)
head = min(0.018, max(0.006, (x_end-x_start)*0.35));
plot(ax, [x_start x_end-head], [y y], '-', 'Color', [0.30 0.30 0.30], ...
    'LineWidth', 1.0);
patch(ax, [x_end-head x_end-head x_end], [y+0.012 y-0.012 y], ...
    [0.30 0.30 0.30], 'EdgeColor', 'none');
end

function draw_awg_storage(ax, position, valid_count, padded_count, compact)
if nargin < 5, compact = false; end
rectangle(ax, 'Position', position, 'FaceColor', [0.93 0.93 0.93], ...
    'EdgeColor', [0.35 0.35 0.35], 'LineWidth', 0.8);
valid_fraction = valid_count / max(padded_count, 1);
rectangle(ax, 'Position', [position(1) position(2) ...
    position(3)*valid_fraction position(4)], ...
    'FaceColor', [0.36 0.70 0.57], 'EdgeColor', 'none');
padding_count = max(0, padded_count-valid_count);
label = sprintf('AWG\n有效 %d\n填充 %d', valid_count, padding_count);
font_size = 7.2;
if compact
    label = sprintf('AWG\n%d\n+%d', valid_count, padding_count);
    font_size = 6.5;
end
text(ax, position(1) + position(3)/2, position(2) + position(4)/2, label, ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
    'FontSize', font_size, 'Interpreter', 'none');
end

function draw_payload_occupancy(ax, plan)
clear_axis_content(ax);
data = plot_data(plan);
symbols = double(field_or(data, 'payload_symbols', complex([])));
symbols = symbols(:);
if isempty(symbols)
    placeholder(ax, '业务符号数据不可用');
    return;
end

order = modulation_order(plan);
ideal = qammod((0:order-1).', order, 'UnitAveragePower', true);
i_levels = sort(unique(real(ideal))).';
q_levels = sort(unique(imag(ideal))).';
[~, i_index] = min(abs(real(symbols) - i_levels), [], 2);
[~, q_index] = min(abs(imag(symbols) - q_levels), [], 2);
counts = accumarray([q_index i_index], 1, [numel(q_levels) numel(i_levels)]);
percent = 100 * counts / numel(symbols);
upper = max(12.5, max(percent(:))*1.15);

imagesc(ax, i_levels, q_levels, percent);
set(ax, 'YDir', 'normal');
x_step = median(diff(i_levels));
y_step = median(diff(q_levels));
xlim(ax, [min(i_levels)-x_step/2 max(i_levels)+x_step/2]);
ylim(ax, [min(q_levels)-y_step/2 max(q_levels)+y_step/2]);
axis(ax, 'square');
pixel_position = getpixelposition(ax);
shown_i_levels = i_levels;
shown_q_levels = q_levels;
if order == 64 && pixel_position(3) < 300
    shown_i_levels = i_levels([1 3 6 8]);
    shown_q_levels = q_levels([1 3 6 8]);
end
set(ax, 'XTick', shown_i_levels, 'YTick', shown_q_levels, 'FontSize', 7.5);
colormap(ax, parula(256));
clim(ax, [0 upper]);
compact_occupancy = pixel_position(3) < 240;
if compact_occupancy
    if order <= 16
        occupancy_title = sprintf('2 %s 占用率 (%%)', modulation_text(plan));
    else
        occupancy_title = sprintf('2 %s 占用 %.2g~%.2g%%', ...
            modulation_text(plan), min(percent(:)), max(percent(:)));
    end
else
    cb = colorbar(ax);
    cb.Label.String = '占用率 (%)';
    occupancy_title = sprintf('2 业务 %s 符号占用率（N = %d）', ...
        modulation_text(plan), numel(symbols));
end
title(ax, occupancy_title, 'FontWeight', 'bold');
xlabel(ax, 'I');
ylabel(ax, 'Q');
hold(ax, 'on');
% Draw decision-cell boundaries so grid lines do not cross the percentages.
for boundary = min(i_levels)-x_step/2 : x_step : max(i_levels)+x_step/2
    xline(ax, boundary, '-', 'Color', [0.35 0.35 0.35], ...
        'LineWidth', 0.6, 'HandleVisibility', 'off');
end
for boundary = min(q_levels)-y_step/2 : y_step : max(q_levels)+y_step/2
    yline(ax, boundary, '-', 'Color', [0.35 0.35 0.35], ...
        'LineWidth', 0.6, 'HandleVisibility', 'off');
end
show_percentages = order <= 16 && pixel_position(3) >= 130;
if show_percentages
    percentage_font = 7.2;
    if compact_occupancy
        percentage_font = 6.4;
    end
    for row = 1:numel(q_levels)
        for column = 1:numel(i_levels)
            if percent(row, column) > upper*0.55
                text_color = [1 1 1];
            else
                text_color = [0.10 0.10 0.10];
            end
            text(ax, i_levels(column), q_levels(row), ...
                sprintf('%.1f%%', percent(row, column)), ...
                'HorizontalAlignment', 'center', 'FontSize', percentage_font, ...
                'Color', text_color, 'Interpreter', 'none');
        end
    end
end
hold(ax, 'off');
end

function draw_digital_spectrum(ax, plan, view_mode, embedded_workbench)
if nargin < 3 || isempty(view_mode)
    view_mode = 'near';
end
if nargin < 4, embedded_workbench = false; end
clear_axis_content(ax);
[samples, sample_rate] = awg_complex_samples(plan);
if isempty(samples) || ~isfinite(sample_rate)
    placeholder(ax, '发射数字频谱数据不可用');
    return;
end
[frequency, power] = welch_spectrum(samples, sample_rate);
if isempty(frequency)
    placeholder(ax, '发射数字频谱数据不足');
    return;
end

cfg = field_or(plan, 'cfg', struct());
wave_cfg = field_or(cfg, 'waveform', struct());
symbol_rate = double(field_or(wave_cfg, 'symbol_rate_hz', NaN));
rolloff = double(field_or(wave_cfg, 'rolloff', NaN));
center = double(field_or(wave_cfg, 'if_center_hz', 0));
if ~isfinite(center)
    center = 0;
end
if isfinite(symbol_rate) && isfinite(rolloff)
    flat_edge = (1-rolloff)*symbol_rate/2;
    band_edge = (1+rolloff)*symbol_rate/2;
else
    flat_edge = NaN;
    band_edge = NaN;
end

h_psd = plot(ax, frequency/1e9, power, 'LineWidth', 0.9, ...
    'Color', [0.00 0.35 0.75], 'DisplayName', '数字复基带 PSD');
ylim(ax, [-105 5]);
grid(ax, 'on');
hold(ax, 'on');
h_flat = gobjects(0);
h_band = gobjects(0);
if isfinite(flat_edge)
    h_flat = xline(ax, (center-flat_edge)/1e9, '--', 'Color', [0.85 0.30 0.05], ...
        'LineWidth', 0.8, 'DisplayName', '平坦带边');
    xline(ax, (center+flat_edge)/1e9, '--', 'Color', [0.85 0.30 0.05], ...
        'LineWidth', 0.8, 'HandleVisibility', 'off');
end
if isfinite(band_edge)
    h_band = xline(ax, (center-band_edge)/1e9, ':', 'Color', [0.20 0.55 0.30], ...
        'LineWidth', 1.0, 'DisplayName', '滚降带边');
    xline(ax, (center+band_edge)/1e9, ':', 'Color', [0.20 0.55 0.30], ...
        'LineWidth', 1.0, 'HandleVisibility', 'off');
end
hold(ax, 'off');
if isfinite(band_edge)
    if strcmpi(view_mode, 'full')
        xlim(ax, [(center-sample_rate/2) (center+sample_rate/2)]/1e9);
    else
        span = max(2.5e9, band_edge + 1.0e9);
        xlim(ax, [(center-span) (center+span)]/1e9);
    end
end
title_text = '3 发射数字复基带近带频谱';
if strcmpi(view_mode, 'full')
    title_text = '4 发射数字复基带全频谱';
end
if abs(center) > 1
    title_text = strrep(title_text, '复基带', '复中频');
end
pixel_position = getpixelposition(ax);
compact_spectrum = pixel_position(3) < 260;
if compact_spectrum
    if strcmpi(view_mode, 'full')
        title_text = '4 全频谱';
    else
        title_text = '3 近带频谱';
    end
end
title_handle = title(ax, title_text, 'FontWeight', 'bold');
if compact_spectrum
    set(title_handle, 'FontSize', 8.5);
end
xlabel(ax, '频率 (GHz)');
if strcmpi(view_mode, 'full')
    ylabel(ax, '');
else
    ylabel(ax, '相对功率 (dB)');
end
if ~embedded_workbench && isfinite(symbol_rate) && isfinite(rolloff)
    if strcmpi(view_mode, 'full')
        note = sprintf('数字奈奎斯特范围 ±%.3f GHz | RRC 带宽边界 ±%.3f GHz', ...
            sample_rate/2e9, band_edge/1e9);
    else
        note = sprintf('符号率 %.3f Gbaud | 滚降系数 %.3f | RRC 带宽边界 ±%.3f GHz', ...
            symbol_rate/1e9, rolloff, band_edge/1e9);
    end
    note_font = 7.5;
    if compact_spectrum
        if strcmpi(view_mode, 'full')
            note = sprintf('Nyquist ±%.3g · BW ±%.3g GHz', ...
                sample_rate/2e9, band_edge/1e9);
        else
            note = sprintf('Rs %.3g GBd · BW ±%.3g GHz', ...
                symbol_rate/1e9, band_edge/1e9);
        end
        note_font = 6.5;
    end
    text(ax, 0.01, 0.04, note, ...
        'Units', 'normalized', 'FontSize', note_font, ...
        'Color', [0.25 0.25 0.25], 'BackgroundColor', [1 1 1], ...
        'Margin', 1, 'Interpreter', 'none', 'Clipping', 'on');
end
legend_handles = h_psd;
legend_labels = {'数字复基带 PSD'};
if ~isempty(h_flat)
    legend_handles(end+1) = h_flat;
    legend_labels{end+1} = '平坦带边';
end
if ~isempty(h_band)
    legend_handles(end+1) = h_band;
    legend_labels{end+1} = '滚降带边';
end
legend_font = 7.5;
if compact_spectrum
    legend(ax, 'off');
else
    legend(ax, legend_handles, legend_labels, 'Location', 'northwest', ...
        'Box', 'off', 'FontSize', legend_font, 'Interpreter', 'none');
end
end

function [samples, sample_rate] = awg_complex_samples(plan)
waveforms = field_or(plan, 'waveforms', struct());
data = field_or(waveforms, 'awg_dac_data', []);
route = field_or(plan, 'route', struct());
columns = field_or(route, 'waveform_columns', [1 2]);
sample_rate = double(field_or(waveforms, 'awg_sample_rate_hz', NaN));
if ~isempty(data) && size(data, 2) >= max(columns) && isfinite(sample_rate)
    samples = double(data(:, columns(1))) + 1j*double(data(:, columns(2)));
    return;
end

plot_values = plot_data(plan);
samples = double(field_or(plot_values, 'passband_complex', complex([])));
sample_rate = double(field_or(waveforms, 'master_sample_rate_hz', NaN));
samples = samples(:);
end

function metrics = awg_metrics(plan)
waveforms = field_or(plan, 'waveforms', struct());
data = field_or(waveforms, 'awg_dac_data', []);
route = field_or(plan, 'route', struct());
columns = field_or(route, 'waveform_columns', [1 2]);
metrics = struct('papr_db', NaN, 'clipping_samples', NaN, ...
    'digital_peak', [NaN NaN]);
if isempty(data) || size(data, 2) < max(columns)
    return;
end
selected = double(data(:, columns(1:2)));
metrics.digital_peak = max(abs(selected), [], 1);
metrics.clipping_samples = sum(any(~isfinite(selected) | ...
    abs(selected) > 1+1e-12, 2));
complex_power = abs(selected(:,1) + 1j*selected(:,2)).^2;
complex_power = complex_power(isfinite(complex_power));
if ~isempty(complex_power) && mean(complex_power) > 0
    metrics.papr_db = 10*log10(max(complex_power)/mean(complex_power));
end
end

function [frequency, power] = welch_spectrum(samples, sample_rate)
samples = double(samples(:));
samples = samples(isfinite(real(samples)) & isfinite(imag(samples)));
if numel(samples) < 8 || ~isfinite(sample_rate) || sample_rate <= 0
    frequency = zeros(0, 1);
    power = zeros(0, 1);
    return;
end
segment_length = 2^floor(log2(min(numel(samples), 65536)));
segment_length = max(8, segment_length);
overlap = floor(segment_length/2);
step = segment_length - overlap;
window = 0.5 - 0.5*cos(2*pi*(0:segment_length-1).'/max(segment_length-1, 1));
window_power = sum(window.^2);
accumulated = zeros(segment_length, 1);
segment_count = 0;
for start_index = 1:step:(numel(samples)-segment_length+1)
    segment = samples(start_index:start_index+segment_length-1);
    spectrum = fftshift(fft(segment .* window));
    accumulated = accumulated + abs(spectrum).^2 / max(window_power, eps);
    segment_count = segment_count + 1;
end
if segment_count == 0
    frequency = zeros(0, 1);
    power = zeros(0, 1);
    return;
end
accumulated = accumulated / segment_count;
power = 10*log10(accumulated/max(accumulated)+eps);
frequency = ((-segment_length/2):(segment_length/2-1)).' * ...
    sample_rate/segment_length;
end

function data = plot_data(plan)
waveforms = field_or(plan, 'waveforms', struct());
data = field_or(waveforms, 'plot_data', struct());
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end

function [i_factor, q_factor] = polarity_factors(plan)
waveforms = field_or(plan, 'waveforms', struct());
calibration = field_or(waveforms, 'iq_calibration', struct());
i_factor = 1; q_factor = 1;
if logical(field_or(calibration, 'invert_i', false)), i_factor = -1; end
if logical(field_or(calibration, 'invert_q', false)), q_factor = -1; end
end

function value = integer_or(value, fallback)
value = double(value);
if ~isscalar(value) || ~isfinite(value)
    value = fallback;
end
value = max(0, round(value));
end

function order = modulation_order(plan)
cfg = field_or(plan, 'cfg', struct());
waveform = field_or(cfg, 'waveform', struct());
order = double(field_or(waveform, 'modulation_order', 16));
if ~isscalar(order) || ~ismember(order, [4 16 64])
    order = 16;
end
end

function value = modulation_text(plan)
order = modulation_order(plan);
if order == 4
    value = 'QPSK';
else
    value = sprintf('%dQAM', order);
end
end

function count = count_frame_positions(frame, field_name)
value = field_or(frame, field_name, []);
if isnumeric(value)
    count = numel(value);
else
    count = 0;
end
end

function text_value = vector_text(value)
if isempty(value)
    text_value = 'n/a';
else
    items = arrayfun(@(item) sprintf('%.3g', double(item)), ...
        double(value(:).'), 'UniformOutput', false);
    text_value = ['[', strjoin(items, ' '), ']'];
end
end

function clear_axis_content(ax)
if ~ishghandle(ax)
    return;
end
axis_units = get(ax, 'Units');
axis_outer_position = get(ax, 'OuterPosition');
fig = ancestor(ax, 'figure');
if ishghandle(fig)
    colorbars = findall(fig, 'Type', 'ColorBar');
    for k = 1:numel(colorbars)
        try
            if isequal(colorbars(k).Axes, ax)
                delete(colorbars(k));
            end
        catch
            % Ignore stale colorbar handles during figure teardown.
        end
    end
end
cla(ax);
set(ax, 'Units', axis_units, 'PositionConstraint', 'outerposition', ...
    'OuterPosition', axis_outer_position, ...
    'Visible', 'on', 'Color', [1 1 1], ...
    'FontName', 'Microsoft YaHei UI', 'FontSize', 9);
end

function placeholder(ax, message)
axis(ax, 'off');
text(ax, 0.5, 0.5, message, 'HorizontalAlignment', 'center', ...
    'VerticalAlignment', 'middle', 'FontName', 'Microsoft YaHei UI', ...
    'FontSize', 10, 'Color', [0.55 0.10 0.10], 'Interpreter', 'none');
end

function close_if_valid(fig)
if isgraphics(fig, 'figure')
    close(fig);
end
end
