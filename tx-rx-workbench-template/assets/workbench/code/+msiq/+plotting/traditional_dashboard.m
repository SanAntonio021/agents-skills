function details = traditional_dashboard(output_path, raw, validation, context, result)
%TRADITIONAL_DASHBOARD Export one compact dashboard for a manual 16QAM run.

if nargin < 5 || isempty(result)
    result = struct();
end
if nargin < 4 || ~isstruct(context)
    context = struct();
end
if nargin < 3 || ~isstruct(validation)
    validation = struct('ok', false, 'reason', 'unavailable', ...
        'summary', struct(), 'pairs', struct([]));
end
if nargin < 2 || ~isstruct(raw)
    raw = struct('channels', struct([]));
end

output_path = char(string(output_path));
[output_dir, ~, extension] = fileparts(output_path);
if isempty(extension)
    output_path = [output_path, '.png'];
end
if ~isempty(output_dir) && ~isfolder(output_dir)
    [ok, message] = mkdir(output_dir);
    if ~ok
        error('msiq:traditionalDashboard:Directory', ...
            'Cannot create dashboard directory %s: %s.', output_dir, message);
    end
end

status = dashboard_status(result, validation);
fig = figure('Visible', 'off', 'Color', 'w', ...
    'Position', [80 80 1500 920], 'InvertHardcopy', 'off');
cleanup = onCleanup(@() close_if_valid(fig));

annotation(fig, 'textbox', [0.025 0.955 0.950 0.035], ...
    'String', sprintf('Traditional 16QAM manual loopback | %s', upper(status)), ...
    'EdgeColor', 'none', 'HorizontalAlignment', 'center', ...
    'FontName', 'Microsoft YaHei UI', 'FontSize', 15, 'FontWeight', 'bold', ...
    'Interpreter', 'none');
annotation(fig, 'textbox', [0.025 0.922 0.950 0.028], ...
    'String', dashboard_subtitle(context, validation, result), ...
    'EdgeColor', 'none', 'HorizontalAlignment', 'center', ...
    'FontName', 'Microsoft YaHei UI', 'FontSize', 9, ...
    'Interpreter', 'none');

ax = subplot(2, 3, 1, 'Parent', fig);
draw_raw(ax, raw);
ax = subplot(2, 3, 2, 'Parent', fig);
draw_spectrum(ax, raw);
ax = subplot(2, 3, 3, 'Parent', fig);
draw_status(ax, status, context, validation, result);
ax = subplot(2, 3, 4, 'Parent', fig);
draw_processing(ax, result);
ax = subplot(2, 3, 5, 'Parent', fig);
draw_constellation(ax, result);
ax = subplot(2, 3, 6, 'Parent', fig);
draw_metrics(ax, status, validation, result);

msiq.plotting.save_replot_figure(fig,output_path);
print(fig, output_path, '-dpng', '-r180');
details = struct('output_path', output_path, 'status', status, ...
    'panel_count', 6, 'decoded_pair_count', decoded_pair_count(result));
clear cleanup;
end

function draw_raw(ax, raw)
records = raw_records(raw);
if isempty(records)
    placeholder(ax, 'Raw capture unavailable');
    return;
end
hold(ax, 'on');
for k = 1:numel(records)
    record = records(k);
    samples = double(record.samples(:));
    time_axis = double(record.time_axis_s(:));
    count = min(numel(samples), numel(time_axis));
    if count == 0
        continue;
    end
    index = display_index(count, 16000);
    plot(ax, time_axis(index)*1e6, samples(index), 'LineWidth', 0.8, ...
        'DisplayName', channel_name(record, k));
end
hold(ax, 'off');
title(ax, '1 Raw C1/C2 waveform', 'FontWeight', 'bold');
xlabel(ax, 'Time (us)');
ylabel(ax, 'Voltage (V)');
legend(ax, 'Location', 'best', 'Box', 'off', 'Interpreter', 'none');
grid(ax, 'on');
end

function draw_spectrum(ax, raw)
records = raw_records(raw);
if isempty(records)
    placeholder(ax, 'Spectrum unavailable');
    return;
end
hold(ax, 'on');
for k = 1:numel(records)
    samples = double(records(k).samples(:));
    rate = field_or(records(k), 'sample_rate_hz', NaN);
    if isempty(samples) || ~isfinite(rate) || rate <= 0
        continue;
    end
    [frequency, power] = simple_spectrum(samples, rate);
    plot(ax, frequency/1e9, power, 'LineWidth', 0.8, ...
        'DisplayName', channel_name(records(k), k));
end
hold(ax, 'off');
title(ax, '2 Relative spectrum', 'FontWeight', 'bold');
xlabel(ax, 'Frequency (GHz)');
ylabel(ax, 'Relative power (dB)');
legend(ax, 'Location', 'best', 'Box', 'off', 'Interpreter', 'none');
grid(ax, 'on');
end

function draw_status(ax, status, context, validation, result)
axis(ax, [0 1 0 1]);
axis(ax, 'off');
title(ax, '3 Run credentials and status', 'FontWeight', 'bold');
lines = { ...
    ['Status: ', status]; ...
    ['Route: ', route_name(context)]; ...
    ['AWG: ', awg_summary(context)]; ...
    ['Scope: ', scope_summary(context)]; ...
    ['Window: ', window_summary(validation)]; ...
    ['Reason: ', result_reason(result, validation)]};
draw_lines(ax, lines);
end

function draw_processing(ax, result)
decoded = decoded_results(result);
if isempty(decoded)
    placeholder(ax, 'Demodulation unavailable');
    return;
end
decoded = decoded(1).decoded;
if isfield(decoded, 'preparation') && ...
        isfield(decoded.preparation, 'baseband_preview') && ...
        ~isempty(decoded.preparation.baseband_preview)
    preview = decoded.preparation.baseband_preview;
    hold(ax, 'on');
    for k = 1:min(2, size(preview, 2))
        plot(ax, real(preview(:,k)), imag(preview(:,k)), '.', ...
            'MarkerSize', 2.0, 'DisplayName', sprintf('RX%d', k));
    end
    hold(ax, 'off');
    axis(ax, 'equal');
    title(ax, '4 RRC output / complex baseband', 'FontWeight', 'bold');
    xlabel(ax, 'I');
    ylabel(ax, 'Q');
    legend(ax, 'Location', 'best', 'Box', 'off');
    grid(ax, 'on');
elseif isfield(decoded, 'synchronization') && ...
        isfield(decoded.synchronization, 'sync_metric_trace')
    metric = decoded.synchronization.sync_metric_trace(:);
    plot(ax, metric, 'LineWidth', 0.8);
    title(ax, '4 Synchronization metric', 'FontWeight', 'bold');
    xlabel(ax, 'Candidate');
    ylabel(ax, 'Metric');
    grid(ax, 'on');
else
    placeholder(ax, 'Processing trace unavailable');
end
end

function draw_constellation(ax, result)
decoded = decoded_results(result);
if isempty(decoded)
    placeholder(ax, '16QAM constellation unavailable');
    return;
end
hold(ax, 'on');
for k = 1:numel(decoded)
    streams = decoded(k).decoded.primary_streams;
    for stream = 1:numel(streams)
        symbols = streams(stream).constellation_symbols(:);
        if isempty(symbols)
            continue;
        end
        index = display_index(numel(symbols), 7000);
        plot(ax, real(symbols(index)), imag(symbols(index)), '.', ...
            'MarkerSize', 3.0, 'DisplayName', sprintf('%s stream%d', ...
            decoded(k).name, stream));
    end
end
ideal = qammod((0:15).', 16, 'UnitAveragePower', true);
plot(ax, real(ideal), imag(ideal), 'ks', 'LineStyle', 'none', ...
    'MarkerSize', 6, 'LineWidth', 1.0, 'DisplayName', 'Ideal 16QAM');
hold(ax, 'off');
axis(ax, 'equal');
title(ax, '5 Demodulated 16QAM', 'FontWeight', 'bold');
xlabel(ax, 'I');
ylabel(ax, 'Q');
legend(ax, 'Location', 'best', 'Box', 'off', 'Interpreter', 'none');
grid(ax, 'on');
end

function draw_metrics(ax, status, validation, result)
axis(ax, [0 1 0 1]);
axis(ax, 'off');
title(ax, '6 Metrics', 'FontWeight', 'bold');
lines = {['Status: ', status]};
decoded = decoded_results(result);
if isempty(decoded)
    lines{end+1} = ['Required window: ', format_seconds(required_window(validation))];
    lines{end+1} = ['Overlap: ', format_seconds(overlap_window(validation))];
else
    value = decoded(1).decoded;
    sync = field_or(value, 'synchronization', struct());
    orientation = field_or(field_or(value, 'iq_orientation', struct()), ...
        'status_text', '');
    if ~isempty(orientation)
        lines{end+1} = orientation;
    end
    lines{end+1} = ['Sync: ', pass_text(field_or(value, 'sync_ok', false)), ...
        '  metric ', format_number(field_or(sync, 'sync_metric', NaN), '%.3f')];
    lines{end+1} = ['CFO: ', format_number(reported_cfo(sync)/1e3, '%.3f'), ' kHz'];
    lines{end+1} = ['SRO: ', format_number(field_or(sync, 'sro_ppm', NaN), '%.3f'), ' ppm'];
    streams = value.primary_streams;
    for stream = 1:numel(streams)
        lines{end+1} = sprintf('Stream%d EVM %.3f%% | MER %.3f dB', stream, ...
            100*streams(stream).evm_rms, streams(stream).mer_db); %#ok<AGROW>
        lines{end+1} = sprintf('Stream%d preBER %.4g | postBER %.4g | BLER %.4g', ...
            stream, streams(stream).pre_fec_ber, streams(stream).post_fec_ber, ...
            streams(stream).bler); %#ok<AGROW>
    end
end
draw_lines(ax, lines);
end

function draw_lines(ax, lines)
count = numel(lines);
if count == 0
    return;
end
y = 0.90;
step = min(0.105, 0.84/max(count, 1));
for k = 1:count
    text(ax, 0.03, y, lines{k}, 'Units', 'normalized', ...
        'VerticalAlignment', 'top', 'FontName', 'Microsoft YaHei UI', ...
        'FontSize', 8.4, 'Interpreter', 'none');
    y = y - step;
end
end

function records = raw_records(raw)
records = struct([]);
if isstruct(raw) && isfield(raw, 'channels') && ~isempty(raw.channels)
    records = raw.channels;
end
end

function value = dashboard_status(result, validation)
if isstruct(result) && isfield(result, 'status') && ~isempty(result.status)
    value = lower(char(string(result.status)));
elseif isstruct(validation) && isfield(validation, 'ok') && validation.ok
    value = 'capture_ready';
else
    value = 'capture_only';
end
end

function text_value = dashboard_subtitle(context, validation, result)
text_value = sprintf('%s | %s | %s', route_name(context), ...
    awg_summary(context), result_reason(result, validation));
end

function text_value = route_name(context)
route = field_or(context, 'route', struct());
text_value = char(string(field_or(route, 'name', 'route unavailable')));
end

function text_value = awg_summary(context)
desired = field_or(context, 'desired', struct());
if ~isstruct(desired) || isempty(fieldnames(desired))
    text_value = 'AWG unavailable';
    return;
end
tx_ref = field_or(context, 'tx_ref', struct());
frame = field_or(tx_ref, 'frame', struct());
waveform_rate = field_or(frame, 'awg_sample_rate_hz', NaN);
if ~isfinite(double(waveform_rate))
    waveform_rate = field_or(desired, 'raster_hz', NaN);
end
levels = format_vector(field_or(desired, 'amplitude_vpp', []), '%.3g');
offsets = format_vector(field_or(desired, 'offset_v', []), '%.3g');
text_value = sprintf('%s %s raster %.3f GSa/s wave %.3f GSa/s %s | level %s Vpp/%s V', ...
    char(string(field_or(desired, 'dac_mode', '?'))), ...
    char(string(field_or(desired, 'rdiv', '?'))), ...
    double(field_or(desired, 'raster_hz', NaN))/1e9, ...
    double(waveform_rate)/1e9, ...
    char(string(field_or(desired, 'memory_mode', '?'))), levels, offsets);
end

function text_value = scope_summary(context)
scope = field_or(context, 'scope_status', struct());
if isstruct(scope) && isfield(scope, 'sample_rate_hz')
    text_value = sprintf('%.3f GSa/s', double(scope.sample_rate_hz)/1e9);
else
    text_value = 'see capture metadata';
end
end

function text_value = window_summary(validation)
text_value = sprintf('required %s, overlap %s', ...
    format_seconds(required_window(validation)), ...
    format_seconds(overlap_window(validation)));
end

function value = required_window(validation)
summary = field_or(validation, 'summary', struct());
value = field_or(summary, 'required_duration_s', NaN);
end

function value = overlap_window(validation)
value = NaN;
summary = field_or(validation, 'summary', struct());
pairs = field_or(summary, 'pair_summaries', {});
if iscell(pairs)
    for k = 1:numel(pairs)
        if isstruct(pairs{k}) && isfield(pairs{k}, 'overlap_duration_s')
            if ~isfinite(value)
                value = double(pairs{k}.overlap_duration_s);
            else
                value = max(value, double(pairs{k}.overlap_duration_s));
            end
        end
    end
end
end

function text_value = result_reason(result, validation)
text_value = char(string(field_or(result, 'reason', '')));
if isempty(text_value)
    text_value = char(string(field_or(validation, 'reason', '')));
end
if isempty(text_value)
    text_value = 'no failure reported';
end
end

function values = decoded_results(result)
values = struct([]);
if ~isstruct(result) || ~isfield(result, 'pairs') || isempty(result.pairs)
    return;
end
pairs = result.pairs;
for k = 1:numel(pairs)
    if isfield(pairs(k), 'status') && strcmpi(char(string(pairs(k).status)), 'decoded') && ...
            isfield(pairs(k), 'decoded') && isstruct(pairs(k).decoded)
        if isempty(values)
            values = pairs(k);
        else
            values(end+1) = pairs(k); %#ok<AGROW>
        end
    end
end
end

function count = decoded_pair_count(result)
count = numel(decoded_results(result));
end

function value = reported_cfo(sync)
value = field_or(sync, 'coarse_cfo_hz', NaN);
if isfield(sync, 'total_cfo_hz')
    value = sync.total_cfo_hz;
end
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end

function text_value = channel_name(record, index)
text_value = char(string(field_or(record, 'channel', sprintf('CH%d', index))));
end

function text_value = pass_text(value)
if logical(value)
    text_value = 'PASS';
else
    text_value = 'FAIL';
end
end

function text_value = format_number(value, format)
if isempty(value) || ~isscalar(value) || ~isfinite(double(value))
    text_value = 'n/a';
else
    text_value = sprintf(format, double(value));
end
end

function text_value = format_seconds(value)
if isempty(value) || ~isscalar(value) || ~isfinite(double(value))
    text_value = 'n/a';
elseif abs(value) >= 1e-3
    text_value = sprintf('%.3f ms', value*1e3);
else
    text_value = sprintf('%.3f us', value*1e6);
end
end

function text_value = format_vector(value, format)
if isempty(value)
    text_value = 'n/a';
    return;
end
value = double(value(:).');
items = arrayfun(@(item) sprintf(format, item), value, 'UniformOutput', false);
text_value = ['[', strjoin(items, ' '), ']'];
end

function [frequency, power] = simple_spectrum(samples, sample_rate)
count = min(numel(samples), 65536);
if count < 2
    frequency = zeros(0,1);
    power = zeros(0,1);
    return;
end
count = 2^floor(log2(count));
samples = samples(1:count);
window = 0.5 - 0.5*cos(2*pi*(0:count-1).'/max(count-1,1));
spectrum = fftshift(fft(samples.*window));
frequency = ((-count/2):(count/2-1)).' * sample_rate/count;
power = 20*log10(abs(spectrum)/max(abs(spectrum))+eps);
end

function index = display_index(count, maximum)
if count <= 0
    index = zeros(0,1);
else
    index = unique(round(linspace(1, count, min(count, maximum)))).';
end
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
