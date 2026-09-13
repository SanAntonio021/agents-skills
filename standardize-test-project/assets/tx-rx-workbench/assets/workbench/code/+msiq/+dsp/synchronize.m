function [symbols, info] = synchronize(baseband, tx_ref, cfg)
%SYNCHRONIZE Recover timing, repeated-ZC CFO, and repeated-frame SRO.

sps = cfg.waveform.master_samples_per_symbol;
sync = tx_ref.frame.sync_symbols(:);
sync_reference = repmat(sync, cfg.waveform.sync_repeats, 1);
[baseband, sro] = correct_sro_samples(baseband, sync_reference, ...
    tx_ref.frame.symbol_count*sps, sps, cfg);
best_metric = -Inf;
best_phase = 1;
best_start = 1;
best_symbols = [];
for phase = 1:sps
    candidate = baseband(phase:sps:end,:);
    [start, peak, locations] = correlation_peak(candidate, sync_reference);
    if peak > best_metric
        best_metric = peak;
        best_phase = phase;
        if isempty(locations)
            best_start = start;
        else
            best_start = locations(1);
        end
        best_symbols = candidate;
    end
end

if isempty(best_symbols) || best_metric < cfg.receiver.sync_metric_min
    error('msiq:dsp:SyncFailed', ...
        'Repeated-ZC synchronization failed (metric %.4g).', best_metric);
end

coarse_cfo = repeated_zc_cfo(best_symbols, best_start, ...
    numel(sync), cfg.waveform.symbol_rate_hz);
axis_value = (0:size(best_symbols,1)-1).';
best_symbols = best_symbols .* exp(-1j*2*pi*coarse_cfo / ...
    cfg.waveform.symbol_rate_hz * axis_value);

[~, initial_peak] = correlation_peak(best_symbols, sync_reference);
% SRO is corrected before symbol-rate sampling so timing phase is retained.
sro_corrected = best_symbols;
[maximum_start, exact_peak, peak_locations, ~, metric_trace] = ...
    correlation_peak(sro_corrected, sync_reference);
if isempty(peak_locations)
    sync_start = maximum_start;
else
    candidate_frame_starts = peak_locations - (tx_ref.frame.sync_start-1);
    complete = candidate_frame_starts >= 1 & ...
        candidate_frame_starts + tx_ref.frame.symbol_count - 1 <= ...
        size(sro_corrected,1);
    first_complete = find(complete, 1, 'first');
    if isempty(first_complete)
        sync_start = peak_locations(1);
    else
        sync_start = peak_locations(first_complete);
    end
end
frame_start = sync_start - (tx_ref.frame.sync_start-1);
if frame_start < 1
    frame_start = frame_start + tx_ref.frame.symbol_count;
end

complete_frames = floor((size(sro_corrected,1)-frame_start+1) / ...
    tx_ref.frame.symbol_count);
if complete_frames < 1
    error('msiq:dsp:IncompleteFrame', ...
        'No complete frame remains after synchronization.');
end
last = frame_start + tx_ref.frame.symbol_count - 1;
symbols = sro_corrected(frame_start:last,:);
discarded_tail = size(sro_corrected,1) - last;

info = struct();
info.ok = true;
info.sample_phase = best_phase;
info.frame_start_symbol = frame_start;
info.sync_start_symbol = sync_start;
info.coarse_cfo_hz = coarse_cfo;
info.sync_metric_initial = initial_peak;
info.sync_metric = exact_peak;
info.sync_peak_locations = peak_locations;
info.sync_metric_trace = metric_trace;
info.sro_ppm = sro.sro_ppm;
info.sro_applied = sro.applied;
info.measured_frame_symbols = sro.measured_frame_symbols;
info.complete_frames = complete_frames;
info.discarded_tail_symbols = discarded_tail;
end

function [start, peak, locations, fractional_locations, metric] = ...
        correlation_peak(samples, reference)
metric = correlation_values(samples, reference);
if isempty(metric)
    start = 1;
    peak = 0;
    locations = [];
    fractional_locations = [];
    return;
end
[peak, start] = max(metric);
threshold = max(0.35*peak, eps);
try
    [~, locations] = findpeaks(metric, ...
        'MinPeakHeight', threshold, ...
        'MinPeakDistance', max(1, round(0.6*numel(reference))));
catch
    locations = start;
end
fractional_locations = double(locations(:));
for k = 1:numel(locations)
    index = locations(k);
    if index > 1 && index < numel(metric)
        left = metric(index-1);
        center = metric(index);
        right = metric(index+1);
        denominator = left - 2*center + right;
        if abs(denominator) > eps
            delta = 0.5*(left-right)/denominator;
            fractional_locations(k) = index + max(min(delta,0.5),-0.5);
        end
    end
end
end

function metric = correlation_values(samples, reference)
metric = zeros(size(samples,1)-numel(reference)+1, 1);
if isempty(metric)
    return;
end
reference_energy = sum(abs(reference).^2);
for channel = 1:size(samples,2)
    value = conv(samples(:,channel), flipud(conj(reference)), 'valid');
    energy = conv(abs(samples(:,channel)).^2, ...
        ones(numel(reference),1), 'valid');
    metric = metric + abs(value).^2 ./ ...
        max(reference_energy*energy, eps);
end
end

function cfo = repeated_zc_cfo(symbols, start, length_value, symbol_rate)
first = start:(start+length_value-1);
second = first + length_value;
if second(end) > size(symbols,1)
    cfo = 0;
    return;
end
correlation = 0;
for channel = 1:size(symbols,2)
    correlation = correlation + sum(conj(symbols(first,channel)) .* ...
        symbols(second,channel));
end
cfo = angle(correlation) * symbol_rate / (2*pi*length_value);
end

function [corrected, info] = correct_sro_samples( ...
        samples, reference, nominal_frame_samples, sps, cfg)
combined_metric = zeros(size(samples,1), 1);
for phase = 1:sps
    candidate = samples(phase:sps:end,:);
    metric = correlation_values(candidate, reference);
    indices = phase + (0:numel(metric)-1)*sps;
    combined_metric(indices) = metric;
end
[peak, ~] = max(combined_metric);
threshold = max(0.35*peak, eps);
try
    [~, locations] = findpeaks(combined_metric, ...
        'MinPeakHeight', threshold, ...
        'MinPeakDistance', round(0.8*nominal_frame_samples));
catch
    locations = [];
end
fractional_locations = double(locations(:));
for k = 1:numel(locations)
    index = locations(k);
    if index > 1 && index < numel(combined_metric)
        left = combined_metric(index-1);
        center = combined_metric(index);
        right = combined_metric(index+1);
        denominator = left-2*center+right;
        if abs(denominator) > eps
            fractional_locations(k) = index + max(min( ...
                0.5*(left-right)/denominator, 0.5), -0.5);
        end
    end
end
if numel(fractional_locations) < 3
    corrected = samples;
    info = struct('applied', false, 'sro_ppm', 0, ...
        'measured_frame_symbols', nominal_frame_samples/sps, ...
        'peak', peak, 'peak_samples', locations);
    return;
end
frame_index = (0:numel(fractional_locations)-1).';
fit_value = polyfit(frame_index, fractional_locations, 1);
measured_samples = fit_value(1);
sro_ppm = (measured_samples/nominal_frame_samples-1)*1e6;
if ~isfinite(sro_ppm) || abs(sro_ppm) > cfg.receiver.max_abs_sro_ppm
    corrected = samples;
    info = struct('applied', false, 'sro_ppm', 0, ...
        'measured_frame_symbols', measured_samples/sps, ...
        'peak', peak, 'peak_samples', locations);
    return;
end
if abs(sro_ppm) < 0.25
    corrected = samples;
    applied = false;
else
    scale = nominal_frame_samples/measured_samples;
    output_count = floor((size(samples,1)-1)*scale)+1;
    source_axis = 1 + (0:output_count-1).'/scale;
    corrected = zeros(output_count, size(samples,2));
    corrected = complex(corrected);
    for channel = 1:size(samples,2)
        corrected(:,channel) = interp1((1:size(samples,1)).', ...
            samples(:,channel), source_axis, 'linear');
    end
    applied = true;
end
info = struct('applied', applied, 'sro_ppm', sro_ppm, ...
    'measured_frame_symbols', measured_samples/sps, ...
    'peak', peak, 'peak_samples', locations);
end
