function details = demod_dashboard(output_path, raw, decoded, cfg, condition)
%DEMOD_DASHBOARD Export the V2 receiver processing chain as one overview.

style = Test_Project_Plot_Style();
fig = figure('Visible', 'off', 'Units', 'inches', ...
    'Position', [1 1 12.8 7.2], 'Color', style.FigureColor);
cleanup = onCleanup(@() close_figure(fig));

streams = decoded.primary_streams;
is_single = strcmpi(decoded.architecture, 'single_complex_stream');
axis_limit = shared_constellation_limit(streams, cfg.waveform.modulation_order);
draw_header(fig, raw, decoded, cfg, condition, style);
draw_raw_waveform(fig, [0.035 0.690 0.430 0.205], raw, decoded, cfg, style);
draw_relative_psd(fig, [0.500 0.690 0.465 0.205], raw, cfg, style);
draw_baseband_preview(fig, [0.035 0.370 0.200 0.195], decoded, style);
draw_sync_trace(fig, [0.265 0.370 0.290 0.195], decoded, style);
draw_equalizer_panel(fig, [0.585 0.370 0.170 0.195], decoded, style);
draw_pilot_tracking(fig, [0.785 0.370 0.180 0.195], decoded, style);
if is_single
    draw_stream_panel(fig, [0.035 0.110 0.930 0.210], streams(1), 1, ...
        axis_limit, cfg.waveform.modulation_order, style, true);
else
    draw_stream_panel(fig, [0.035 0.110 0.445 0.210], streams(1), 1, ...
        axis_limit, cfg.waveform.modulation_order, style, false);
    draw_stream_panel(fig, [0.520 0.110 0.445 0.210], streams(2), 2, ...
        axis_limit, cfg.waveform.modulation_order, style, false);
end
draw_footer(fig, decoded, cfg, style);

Test_Project_Export_PNG(fig, output_path, style);
details = struct('output_path', output_path, 'panel_count', 8, ...
    'stream_count', numel(streams), 'constellation_axis_limit', axis_limit, ...
    'resolution_dpi', style.ResolutionDPI);
end

function draw_header(fig, raw, decoded, cfg, condition, style)
snr_text = '实测/未定义SNR';
if isfield(raw, 'simulation_options') && ...
        isfield(raw.simulation_options, 'snr_db')
    snr_text = sprintf('合成SNR %.1f dB', raw.simulation_options.snr_db);
end
if strcmpi(decoded.architecture, 'single_complex_stream')
    architecture_text = sprintf('%s 传统复数零中频', ...
        modulation_text(cfg.waveform.modulation_order));
    equalizer_text = 'WZ WL-FSE-NLMS';
else
    architecture_text = sprintf('%s 双独立流', ...
        modulation_text(cfg.waveform.modulation_order));
    equalizer_text = '2x2 RZF';
end
title_text = sprintf(['V2 RX解调面板 | %s | %s | ', ...
    'Rs %.6f GBd | %s'], condition.condition_id, ...
    architecture_text, cfg.waveform.symbol_rate_hz/1e9, snr_text);
annotation(fig, 'textbox', [0.025 0.955 0.950 0.035], ...
    'String', title_text, 'EdgeColor', 'none', ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
    'FontName', style.FontName, 'FontSize', 13, 'FontWeight', 'bold', ...
    'Interpreter', 'none');
sync = decoded.synchronization;
reported_cfo = sync.coarse_cfo_hz;
if isfield(sync, 'total_cfo_hz')
    reported_cfo = sync.total_cfo_hz;
end
orientation = field_or(field_or(decoded, 'iq_orientation', struct()), ...
    'status_text', '');
if ~isempty(orientation)
    orientation = [orientation, ' | '];
end
subtitle = sprintf(['%s同步 %s | metric %.3f | CFO %.3f kHz | SRO %.3f ppm | ', ...
    '采样相位 %d | %s | DVB-S2 LDPC 9/10 | 总体 %s'], orientation, ...
    pass_text(decoded.sync_ok), sync.sync_metric, reported_cfo/1e3, ...
    sync.sro_ppm, sync.sample_phase, equalizer_text, pass_text(decoded.pass));
annotation(fig, 'textbox', [0.025 0.918 0.950 0.030], ...
    'String', subtitle, 'EdgeColor', 'none', ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
    'FontName', style.FontName, 'FontSize', 9.2, ...
    'Color', [0.18 0.18 0.18], 'Interpreter', 'none');
end

function draw_raw_waveform(fig, position, raw, decoded, cfg, style)
ax = axes('Parent', fig, 'Units', 'normalized', 'Position', position);
samples = double(raw.samples);
index = display_index(size(samples,1), 16000);
if isfield(raw, 'time_axes') && ~isempty(raw.time_axes)
    time_us = 1e6*double(raw.time_axes(index,1));
else
    time_us = 1e6*(index(:)-1)/double(raw.sample_rate_hz);
end
hold(ax, 'on');
for channel = 1:min(2,size(samples,2))
    if strcmpi(cfg.waveform.architecture, 'single_complex_stream')
        names = {'I','Q'};
        display_name = names{channel};
    else
        display_name = sprintf('RX%d 实部', channel);
    end
    plot(ax, time_us, real(samples(index,channel)), ...
        'Color', style.Colors(channel,:), 'LineWidth', 0.65, ...
        'DisplayName', display_name);
end
hold(ax, 'off');
title(ax, '1 原始采集波形', 'FontWeight', 'bold');
xlabel(ax, '时间 (us)');
ylabel(ax, '归一化幅度');
legend(ax, 'Location', 'northwest', 'Box', 'off', 'FontSize', 7.5);
alignment = decoded.preparation.alignment.offset_samples;
note = sprintf('Fs %.3f GSa/s | N %d | I/Q时轴偏移 %s sample', ...
    raw.sample_rate_hz/1e9, size(samples,1), compact_vector(alignment, '%.3f'));
text(ax, 0.99, 0.04, note, 'Units', 'normalized', ...
    'HorizontalAlignment', 'right', 'VerticalAlignment', 'bottom', ...
    'FontName', style.FontName, 'FontSize', 7.2, ...
    'BackgroundColor', 'w', 'Margin', 2, 'Interpreter', 'none');
apply_style(ax, style);
end

function draw_relative_psd(fig, position, raw, cfg, style)
ax = axes('Parent', fig, 'Units', 'normalized', 'Position', position);
samples = double(raw.samples);
is_single = strcmpi(cfg.waveform.architecture, 'single_complex_stream');
if is_single && size(samples,2) >= 2 && isreal(samples)
    samples = complex(samples(:,1), samples(:,2));
end
count = min(size(samples,1), 262144);
if count < 256
    placeholder(ax, '样点不足，无法计算PSD', style);
    return;
end
samples = samples(1:count,:);
window_count = min(4096, count);
nfft = 4096;
spectra = cell(1,min(2,size(samples,2)));
frequency = [];
peak = 0;
for channel = 1:numel(spectra)
    [spectra{channel}, frequency] = pwelch(samples(:,channel), ...
        hann(window_count,'periodic'), floor(window_count/2), nfft, ...
        raw.sample_rate_hz, 'centered');
    peak = max(peak, max(spectra{channel}));
end
hold(ax, 'on');
for channel = 1:numel(spectra)
    relative = 10*log10(max(spectra{channel},realmin)/max(peak,realmin));
    if is_single
        display_name = 'I+jQ';
    else
        display_name = sprintf('RX%d',channel);
    end
    plot(ax, frequency/1e9, relative, 'Color', style.Colors(channel,:), ...
        'LineWidth', 1.0, 'DisplayName', display_name);
end
hold(ax, 'off');
title(ax, '2 输入复基带相对PSD', 'FontWeight', 'bold');
xlabel(ax, '频率 (GHz)');
ylabel(ax, '相对PSD (dB)');
ylim(ax, [-80 5]);
legend(ax, 'Location', 'best', 'Box', 'off', 'FontSize', 7.5);
apply_style(ax, style);
end

function draw_baseband_preview(fig, position, decoded, style)
ax = axes('Parent', fig, 'Units', 'normalized', 'Position', position);
preview = decoded.preparation.baseband_preview;
if isempty(preview)
    placeholder(ax, '无RRC后复基带预览', style);
    return;
end
hold(ax, 'on');
for channel = 1:min(2,size(preview,2))
    plot(ax, real(preview(:,channel)), imag(preview(:,channel)), '.', ...
        'Color', style.Colors(channel,:), 'MarkerSize', 2.2, ...
        'DisplayName', sprintf('RX%d',channel));
end
hold(ax, 'off');
axis(ax, 'equal');
title(ax, '3 RRC后复基带 I/Q', 'FontWeight', 'bold');
xlabel(ax, 'I');
ylabel(ax, 'Q');
legend(ax, 'Location', 'best', 'Box', 'off', 'FontSize', 7.0);
apply_style(ax, style);
end

function draw_sync_trace(fig, position, decoded, style)
ax = axes('Parent', fig, 'Units', 'normalized', 'Position', position);
sync = decoded.synchronization;
metric = sync.sync_metric_trace(:);
if isempty(metric)
    placeholder(ax, '无同步相关曲线', style);
    return;
end
plot(ax, (1:numel(metric)).', metric, 'Color', style.Colors(1,:), ...
    'LineWidth', 0.8);
hold(ax, 'on');
peaks = sync.sync_peak_locations(:);
peaks = peaks(peaks >= 1 & peaks <= numel(metric));
if ~isempty(peaks)
    plot(ax, peaks, metric(peaks), 'o', 'Color', style.Colors(2,:), ...
        'MarkerFaceColor', 'w', 'MarkerSize', 4, 'LineWidth', 1.0);
end
hold(ax, 'off');
title(ax, '4 重复ZC同步峰', 'FontWeight', 'bold');
xlabel(ax, '符号起点');
ylabel(ax, '归一化相关和');
note = sprintf(['选中 %d | frame %d\nmetric %.3f | CFO %.3f kHz\n', ...
    'SRO %.3f ppm | 完整帧 %d'], sync.sync_start_symbol, ...
    sync.frame_start_symbol, sync.sync_metric, reported_cfo(sync)/1e3, ...
    sync.sro_ppm, sync.complete_frames);
text(ax, 0.98, 0.95, note, 'Units', 'normalized', ...
    'HorizontalAlignment', 'right', 'VerticalAlignment', 'top', ...
    'FontName', style.FontName, 'FontSize', 7.0, ...
    'BackgroundColor', 'w', 'EdgeColor', [0.75 0.75 0.75], ...
    'Margin', 3, 'Interpreter', 'none');
apply_style(ax, style);
end

function draw_equalizer_panel(fig, position, decoded, style)
ax = axes('Parent', fig, 'Units', 'normalized', 'Position', position);
if isfield(decoded.primary_equalizer, 'training_timing_offsets_samples')
    offsets = decoded.primary_equalizer.training_timing_offsets_samples;
    nmse = decoded.primary_equalizer.training_timing_nmse;
    plot(ax, offsets, 10*log10(nmse+eps), 'o-', ...
        'Color', style.Colors(1,:), 'MarkerFaceColor', 'w', ...
        'MarkerSize', 3.5, 'LineWidth', 1.0);
    best_offset = decoded.primary_equalizer.training_timing_offset_samples;
    best_nmse = decoded.primary_equalizer.training_nmse;
    title(ax, {'5 WZ WL-FSE训练', ...
        sprintf('best %+d sample, %.2f dB',best_offset,10*log10(best_nmse+eps))}, ...
        'FontWeight', 'bold', 'FontSize', 8.0);
    xlabel(ax, '定时偏移 (sample)');
    ylabel(ax, '训练NMSE (dB)');
    apply_style(ax, style);
    return;
end
matrix = decoded.primary_equalizer.channel_matrix;
magnitude = abs(matrix);
imagesc(ax, magnitude);
axis(ax, 'equal', 'tight');
colormap(ax, parula(128));
colorbar(ax, 'Location', 'eastoutside', 'FontSize', 6.5);
for row = 1:size(magnitude,1)
    for column = 1:size(magnitude,2)
        text(ax, column, row, sprintf('%.3f',magnitude(row,column)), ...
            'HorizontalAlignment', 'center', 'FontWeight', 'bold', ...
            'FontSize', 7.5, 'Color', contrast_color(magnitude(row,column),magnitude));
    end
end
condition_number = cond(matrix);
offset = decoded.primary_equalizer.training_timing_offset_symbols;
title(ax, { '5 训练与2x2信道', ...
    sprintf('|H|, cond %.2f, timing %+d',condition_number,offset)}, ...
    'FontWeight', 'bold', 'FontSize', 8.2);
xlabel(ax, 'TX流');
ylabel(ax, 'RX路');
set(ax, 'XTick', 1:2, 'YTick', 1:2);
apply_style(ax, style);
end

function draw_pilot_tracking(fig, position, decoded, style)
ax = axes('Parent', fig, 'Units', 'normalized', 'Position', position);
streams = decoded.primary_streams;
yyaxis(ax, 'left');
hold(ax, 'on');
for stream = 1:numel(streams)
    phase = streams(stream).tracking.phase_track(:)*180/pi;
    index = display_index(numel(phase), 1200);
    plot(ax, index, phase(index), 'Color', style.Colors(stream,:), ...
        'LineStyle', style.LineStyles{stream}, 'LineWidth', 0.9);
end
hold(ax, 'off');
ylabel(ax, '相位校正 (deg)');
yyaxis(ax, 'right');
hold(ax, 'on');
for stream = 1:numel(streams)
    amplitude = streams(stream).tracking.amplitude_track(:);
    index = display_index(numel(amplitude), 1200);
    plot(ax, index, amplitude(index), 'Color', style.Colors(stream,:), ...
        'LineStyle', ':', 'LineWidth', 0.9);
end
hold(ax, 'off');
ylabel(ax, '幅度校正');
xlabel(ax, '帧内符号');
pilot_evm = arrayfun(@(value) 100*value.tracking.pilot_evm, streams);
title(ax, {'6 分布式导频跟踪', ...
    sprintf('pilot EVM %s %%',compact_vector(pilot_evm,'%.2f'))}, ...
    'FontWeight', 'bold', 'FontSize', 8.2);
if numel(streams) == 1
    tracking_note = '蓝=相位 | 橙=幅度';
else
    tracking_note = '蓝/橙=流1/流2 | 实线/点线=相位/幅度';
end
text(ax, 0.02, 0.03, tracking_note, ...
    'Units', 'normalized', 'HorizontalAlignment', 'left', ...
    'VerticalAlignment', 'bottom', 'FontName', style.FontName, ...
    'FontSize', 6.4, 'Color', [0.20 0.20 0.20], ...
    'BackgroundColor', 'w', 'Margin', 2, 'Interpreter', 'none');
apply_style(ax, style);
end

function draw_stream_panel(fig, position, stream, stream_index, axis_limit, order, style, is_single)
gap = 0.010;
plot_width = position(3)*0.59;
table_width = position(3)-plot_width-gap;
plot_ax = axes('Parent', fig, 'Units', 'normalized', ...
    'Position', [position(1) position(2) plot_width position(4)]);
table_ax = axes('Parent', fig, 'Units', 'normalized', ...
    'Position', [position(1)+plot_width+gap position(2) table_width position(4)]);

symbols = stream.constellation_symbols(:);
color = style.Colors(min(stream_index,size(style.Colors,1)),:);
plot(plot_ax, real(symbols), imag(symbols), '.', 'Color', color, 'MarkerSize', 2.5);
hold(plot_ax, 'on');
ideal = qammod((0:order-1).', order, 'UnitAveragePower', true);
plot(plot_ax, real(ideal), imag(ideal), 'ks', 'LineStyle', 'none', ...
    'MarkerSize', 5.5, 'LineWidth', 1.0);
hold(plot_ax, 'off');
axis(plot_ax, 'equal');
xlim(plot_ax, [-axis_limit axis_limit]);
ylim(plot_ax, [-axis_limit axis_limit]);
if is_single
    plot_title = sprintf('7 传统复数%s星座图', modulation_text(order));
else
    plot_title = sprintf('%d 解调流%d星座图',6+stream_index,stream_index);
end
title(plot_ax, plot_title, 'FontWeight', 'bold');
xlabel(plot_ax, 'I');
ylabel(plot_ax, 'Q');
apply_style(plot_ax, style);

outside = nnz(abs(real(symbols)) > axis_limit | abs(imag(symbols)) > axis_limit);
iterations = mat2str(stream.actual_iterations);
rows = {
    '状态', pass_text(stream.pass);
    '有效符号', sprintf('%d',stream.payload_symbol_count);
    'EVM', sprintf('%.3f %%',100*stream.evm_rms);
    'MER', sprintf('%.3f dB',stream.mer_db);
    'pre-FEC BER', sprintf('%.4g',stream.pre_fec_ber);
    'pre-FEC错比特', sprintf('%d/%d',stream.fec.pre_fec_bit_error_count,stream.fec.pre_fec_bit_count);
    'post-FEC BER', sprintf('%.4g',stream.post_fec_ber);
    'BLER', sprintf('%.4g',stream.bler);
    'parity', pass_text(stream.parity_converged);
    'LDPC迭代', iterations;
    '完整块/尾比特', sprintf('%d / %d',stream.block_count,stream.incomplete_tail_bits);
    '图外符号', sprintf('%d',outside)
    };
if is_single
    table_heading = '8 传统复数流指标与FEC';
else
    table_heading = sprintf('流%d指标与FEC',stream_index);
end
draw_table(table_ax, table_heading, rows, style);
end

function draw_table(ax, heading, rows, style)
axis(ax, [0 1 0 1]);
axis(ax, 'off');
rectangle(ax, 'Position', [0.01 0.01 0.98 0.98], ...
    'EdgeColor', [0.68 0.68 0.68], 'LineWidth', 0.8);
text(ax, 0.05, 0.955, heading, 'FontName', style.FontName, ...
    'FontSize', 8.5, 'FontWeight', 'bold', 'VerticalAlignment', 'top', ...
    'Interpreter', 'none');
y = linspace(0.84,0.07,size(rows,1));
for row = 1:size(rows,1)
    text(ax, 0.05, y(row), rows{row,1}, 'FontName', style.FontName, ...
        'FontSize', 6.8, 'Color', [0.18 0.18 0.18], 'Interpreter', 'none');
    text(ax, 0.95, y(row), rows{row,2}, 'FontName', style.FontName, ...
        'FontSize', 6.8, 'HorizontalAlignment', 'right', ...
        'FontWeight', 'bold', 'Interpreter', 'none');
end
end

function draw_footer(fig, decoded, cfg, style)
policy = decoded.equalizer_selection_policy;
if strcmpi(cfg.waveform.architecture, 'single_complex_stream')
    equalizer_chain = '2 Sa/sym WZ WL-FSE-NLMS -> 导频/可靠判决跟踪';
else
    equalizer_chain = '训练序列2x2 RZF -> 分布式导频跟踪';
end
text_value = sprintf(['处理链：时轴对齐 -> I/Q复数组合 -> RRC -> 重复ZC同步 -> ', ...
    'CFO/SRO校正 -> %s -> %s软LLR -> LDPC | ', ...
    'payload仅用于最终指标：%s | 均衡器策略：%s'], ...
    equalizer_chain, modulation_text(cfg.waveform.modulation_order), ...
    pass_text(~decoded.payload_reference_used_for_processing), policy);
annotation(fig, 'textbox', [0.025 0.015 0.950 0.035], ...
    'String', text_value, 'EdgeColor', [0.80 0.80 0.80], ...
    'BackgroundColor', [0.97 0.97 0.97], ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
    'FontName', style.FontName, 'FontSize', 7.3, 'Interpreter', 'none');
end

function limit = shared_constellation_limit(streams, order)
ideal = qammod((0:order-1).', order, 'UnitAveragePower', true);
minimum = 1.25*max([abs(real(ideal));abs(imag(ideal))]);
values = [];
for stream = 1:numel(streams)
    symbols = streams(stream).constellation_symbols(:);
    values = [values; abs(real(symbols)); abs(imag(symbols))]; %#ok<AGROW>
end
values = sort(values(isfinite(values)));
if isempty(values)
    limit = minimum;
else
    index = max(1,ceil(0.995*numel(values)));
    limit = max(minimum,1.05*values(index));
end
limit = min(limit,2.0);
end

function index = display_index(count, maximum)
if count <= 0
    index = zeros(0,1);
    return;
end
shown = min(count, maximum);
index = unique(round(linspace(1,count,shown))).';
end

function apply_style(ax, style)
Test_Project_Apply_Axes_Style(ax, style);
set(ax, 'FontSize', 7.5);
end

function placeholder(ax, message, style)
axis(ax, 'off');
text(ax, 0.5, 0.5, message, 'HorizontalAlignment', 'center', ...
    'VerticalAlignment', 'middle', 'FontName', style.FontName, ...
    'FontSize', 8, 'Color', [0.55 0.10 0.10], 'Interpreter', 'none');
end

function text_value = compact_vector(value, format)
items = arrayfun(@(item) sprintf(format,item), value(:).', ...
    'UniformOutput', false);
text_value = ['[',strjoin(items,' '),']'];
end

function color = contrast_color(value, matrix)
threshold = 0.55*max(matrix(:));
if value >= threshold
    color = [1 1 1];
else
    color = [0.05 0.05 0.05];
end
end

function value = modulation_text(order)
if order == 4
    value = 'QPSK';
else
    value = sprintf('%dQAM', order);
end
end

function text_value = pass_text(value)
if logical(value)
    text_value = 'PASS';
else
    text_value = 'FAIL';
end
end

function value = reported_cfo(sync)
value = sync.coarse_cfo_hz;
if isfield(sync, 'total_cfo_hz')
    value = sync.total_cfo_hz;
end
end

function value = field_or(source, name, fallback)
if isstruct(source) && isfield(source, name) && ~isempty(source.(name))
    value = source.(name);
else
    value = fallback;
end
end

function close_figure(fig)
if isgraphics(fig, 'figure')
    close(fig);
end
end
