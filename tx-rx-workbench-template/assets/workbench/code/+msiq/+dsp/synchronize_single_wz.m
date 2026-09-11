function [frame_samples, info] = synchronize_single_wz( ...
        baseband, tx_ref, cfg, include_corrected_capture, sro_mode)
%SYNCHRONIZE_SINGLE_WZ WZ-style 2 Sa/sym repeated-ZC synchronization.

if nargin < 4 || isempty(include_corrected_capture)
    include_corrected_capture = false;
end
if nargin < 5 || isempty(sro_mode)
    sro_mode = 'apply';
end
sro_mode = normalize_sro_mode(sro_mode);

if size(baseband,2) ~= 1
    error('msiq:dsp:WzSingleInput', ...
        'WZ traditional synchronization requires one complex I/Q stream.');
end
sps = cfg.receiver.single_samples_per_symbol;
if sps ~= round(sps) || sps < 2
    error('msiq:dsp:WzSingleSps', ...
        'WZ traditional synchronization requires at least 2 samples/symbol.');
end
sps = round(sps);
samples = baseband(:,1).';
frame = tx_ref.frame;
sync_one = frame.sync_symbols(:);
sync_reference = repmat(sync_one, frame.sync_repeats, 1);
nominal_frame_samples = frame.symbol_count*sps;

[samples, sro] = correct_sro_dispatch(samples, sync_reference, ...
    nominal_frame_samples, sps, cfg.receiver.max_abs_sro_ppm, frame, cfg, ...
    sro_mode);
sample_rate = cfg.waveform.symbol_rate_hz*sps;
[repeat_metric, repeat_correlation] = repeated_metric(samples, ...
    numel(sync_one)*sps, frame.sync_repeats);
[repeat_peak, approximate_start] = max(repeat_metric);
if isempty(approximate_start)
    error('msiq:dsp:WzSyncLength', ...
        'Capture is too short for repeated-ZC synchronization.');
end
coarse_cfo = angle(repeat_correlation(approximate_start)) / ...
    (2*pi*numel(sync_one)/cfg.waveform.symbol_rate_hz);
axis_value = 0:numel(samples)-1;
coarse_corrected = samples .* exp(-1j*2*pi*coarse_cfo/sample_rate*axis_value);

initial = exact_sync(coarse_corrected, sync_reference, frame, sps);
fine_correlation = 0;
for repeat = 0:frame.sync_repeats-2
    first = initial.sync_start_sample + ...
        (repeat*numel(sync_one)+(0:numel(sync_one)-1))*sps;
    second = first + numel(sync_one)*sps;
    if second(end) <= numel(coarse_corrected)
        fine_correlation = fine_correlation + ...
            sum(conj(coarse_corrected(first)).*coarse_corrected(second));
    end
end
fine_cfo = angle(fine_correlation) / ...
    (2*pi*numel(sync_one)/cfg.waveform.symbol_rate_hz);
total_cfo = coarse_cfo + fine_cfo;
corrected = samples .* exp(-1j*2*pi*total_cfo/sample_rate*axis_value);
final = exact_sync(corrected, sync_reference, frame, sps);

if final.metric_peak < cfg.receiver.sync_metric_min
    error('msiq:dsp:WzSyncFailed', ...
        'WZ repeated-ZC synchronization failed (metric %.4g).', ...
        final.metric_peak);
end
first = final.frame_start_sample;
last = first + nominal_frame_samples - 1;
if first < 1 || last > numel(corrected)
    error('msiq:dsp:WzIncompleteFrame', ...
        'No complete traditional complex frame remains after synchronization.');
end
frame_samples = corrected(first:last).';

info = struct();
info.ok = true;
info.sample_phase = final.sample_phase;
info.frame_start_sample = final.frame_start_sample;
info.sync_start_sample = final.sync_start_sample;
info.frame_start_symbol = floor((final.frame_start_sample-1)/sps)+1;
info.sync_start_symbol = floor((final.sync_start_sample-1)/sps)+1;
info.coarse_cfo_hz = coarse_cfo;
info.fine_cfo_hz = fine_cfo;
info.total_cfo_hz = total_cfo;
info.sync_metric_initial = initial.metric_peak;
info.sync_metric = final.metric_peak;
info.sync_peak_locations = final.peak_locations;
info.sync_metric_trace = final.metric_trace;
info.repeat_metric_peak = repeat_peak;
info.repeat_metric_trace = repeat_metric(:);
info.repeat_peak_locations = metric_peak_locations(repeat_metric);
info.sro_ppm = sro.sro_ppm;
info.sro_applied = sro.applied;
info.sro_recommended = sro.recommended;
info.sro_correction_mode = sro.mode;
info.sro_low_rate_resample_applied = sro.applied;
info.measured_frame_symbols = sro.measured_frame_samples/sps;
info.sro_peak_samples = sro.peak_samples;
info.sro_complete_peak_samples = sro.complete_peak_samples;
info.sro_candidate_frame_starts = sro.candidate_frame_starts;
if isfield(sro, 'fit_peak_samples')
    info.sro_fit_peak_samples = sro.fit_peak_samples;
else
    info.sro_fit_peak_samples = sro.peak_samples;
end
info.sro_adjusted_fit_peak_samples = sro.adjusted_fit_peak_samples;
if isfield(sro, 'fit_interval_samples')
    info.sro_fit_interval_samples = sro.fit_interval_samples;
else
    info.sro_fit_interval_samples = diff(sro.peak_samples);
end
if isfield(sro, 'boundary_interval_indices')
    info.sro_boundary_interval_indices = sro.boundary_interval_indices;
else
    info.sro_boundary_interval_indices = zeros(0,1);
end
% Keep an unprefixed alias for offline/legacy diagnostic consumers.
info.boundary_interval_indices = info.sro_boundary_interval_indices;
if isfield(sro, 'sro_fit_residual_samples')
    info.sro_fit_residual_samples = sro.sro_fit_residual_samples;
else
    info.sro_fit_residual_samples = NaN;
end
if isfield(sro, 'sro_phase_margin')
    info.sro_phase_margin = sro.sro_phase_margin;
else
    info.sro_phase_margin = NaN;
end
if isfield(sro, 'sro_reason')
    info.sro_reason = sro.sro_reason;
else
    info.sro_reason = '';
end
info.sro_nominal_period_samples = sro.nominal_period_samples;
info.sro_boundary_extra_samples = sro.boundary_extra_samples;
if isfield(sro, 'measured_boundary_extra_samples')
    info.sro_measured_boundary_extra_samples = ...
        sro.measured_boundary_extra_samples;
    info.sro_boundary_scale = sro.boundary_scale;
else
    info.sro_measured_boundary_extra_samples = sro.boundary_extra_samples;
    info.sro_boundary_scale = 1;
end
info.sro_boundary_classified = sro.boundary_classified;
info.sro_boundary_absent = sro.boundary_absent;
info.sro_boundary_score = sro.boundary_score;
info.sro_fit_interval_count = sro.fit_interval_count;
info.sro_max_interval_deviation_samples = sro.max_interval_deviation_samples;
info.sro_interval_consistency_limit_samples = ...
    sro.interval_consistency_limit_samples;
info.sro_sigma_ppm = sro.sro_sigma_ppm;
info.sro_fit_slope_samples = sro.fit_slope_samples;
info.sro_fit_slope_sigma_samples = sro.fit_slope_sigma_samples;
info.sro_quantization_ppm = sro.quantization_ppm;
info.sro_apply_threshold_ppm = sro.apply_threshold_ppm;
info.sro_reliable = sro.reliable;
info.sro_estimator = sro.estimator;
info.sro_decision_policy = sro.decision_policy;
info.sro_observation_oversample_factor = ...
    sro.observation_oversample_factor;
info.sro_correction_ppm = sro.correction_ppm;
info.sro_correction_weight = sro.correction_weight;
info.sro_confidence_level = sro.confidence_level;
info.sro_confidence_interval_ppm = sro.confidence_interval_ppm;
info.sro_resolution_sigma_ppm = sro.resolution_sigma_ppm;
info.sro_jackknife_sigma_ppm = sro.jackknife_sigma_ppm;
info.sro_leave_one_out_range_ppm = sro.leave_one_out_range_ppm;
info.sro_robust_weights = sro.robust_weights;
info.sro_robust_outlier_count = sro.robust_outlier_count;
info.complete_frames = numel(final.candidate_frame_starts);
info.candidate_frame_starts = final.candidate_frame_starts;
info.discarded_tail_symbols = floor((numel(corrected)-last)/sps);
info.processing_samples_per_symbol = sps;
if include_corrected_capture
    % Used only by the equal-rate serial-frame splitter.
    info.corrected_capture = corrected(:).';
end
end

function [metric, correlation] = repeated_metric(samples, block_length, repeats)
base_length = numel(samples)-(repeats-1)*block_length;
count = base_length-block_length+1;
if count < 1
    metric = zeros(0,1);
    correlation = zeros(0,1);
    return;
end
correlation = zeros(1,count);
energy = zeros(1,count);
for repeat = 0:repeats-2
    first = samples(1+repeat*block_length:repeat*block_length+base_length);
    second = samples(1+(repeat+1)*block_length: ...
        (repeat+1)*block_length+base_length);
    product_sum = [0,cumsum(conj(first).*second)];
    energy_sum = [0,cumsum(abs(first).^2+abs(second).^2)];
    correlation = correlation + ...
        product_sum(block_length+1:end)-product_sum(1:end-block_length);
    energy = energy + ...
        energy_sum(block_length+1:end)-energy_sum(1:end-block_length);
end
metric = abs(correlation).^2./(0.25*energy.^2+eps);
end

function locations = metric_peak_locations(metric)
metric = double(metric(:));
locations = zeros(0,1);
finite = isfinite(metric);
if ~any(finite)
    return;
end
peak = max(metric(finite));
if ~isfinite(peak)
    return;
end
try
    [~, locations] = findpeaks(metric, ...
        'MinPeakHeight', max(0.25*peak, eps), ...
        'MinPeakDistance', max(1, floor(numel(metric)/96)));
catch
    [~, location] = max(metric);
    locations = location;
end
locations = double(locations(:));
if numel(locations) > 24
    [~, order] = sort(metric(locations), 'descend');
    locations = sort(locations(order(1:24)));
end
end

function result = exact_sync(samples, reference, frame, sps)
reference = reference(:);
reference_energy = sum(abs(reference).^2);
best_peak = -Inf;
best_phase = 0;
best_sync_sample = NaN;
best_trace = zeros(0,1);
best_locations = zeros(0,1);
candidate_starts = zeros(0,1);
candidate_peaks = zeros(0,1);

for phase = 0:sps-1
    symbols = samples(phase+1:sps:end).';
    if numel(symbols) < numel(reference)
        continue;
    end
    correlation = conv(symbols, flipud(conj(reference)), 'valid');
    energy = conv(abs(symbols).^2, ones(numel(reference),1), 'valid');
    metric = abs(correlation).^2./max(reference_energy*energy, eps);
    threshold = max(0.25*max(metric), 0.05);
    try
        [peaks, locations] = findpeaks(metric, ...
            'MinPeakHeight', threshold, ...
            'MinPeakDistance', max(1,round(0.8*frame.symbol_count)));
    catch
        [peaks, locations] = max(metric);
    end
    for index = 1:numel(locations)
        sync_sample = phase+1+(locations(index)-1)*sps;
        frame_sample = sync_sample-(frame.sync_start-1)*sps;
        if frame_sample >= 1 && ...
                frame_sample+frame.symbol_count*sps-1 <= numel(samples)
            candidate_starts(end+1,1) = frame_sample; %#ok<AGROW>
            candidate_peaks(end+1,1) = peaks(index); %#ok<AGROW>
        end
    end
    valid = false(size(metric));
    for index = 1:numel(metric)
        sync_sample = phase+1+(index-1)*sps;
        frame_sample = sync_sample-(frame.sync_start-1)*sps;
        valid(index) = frame_sample >= 1 && ...
            frame_sample+frame.symbol_count*sps-1 <= numel(samples);
    end
    metric(~valid) = -Inf;
    [peak, location] = max(metric);
    if peak > best_peak
        best_peak = peak;
        best_phase = phase;
        best_sync_sample = phase+1+(location-1)*sps;
        trace = metric;
        trace(~isfinite(trace)) = 0;
        best_trace = trace(:);
        best_locations = locations(:);
    end
end

if ~isfinite(best_peak) || isnan(best_sync_sample)
    error('msiq:dsp:WzCompleteFrame', ...
        'No complete WZ traditional frame was found.');
end
[candidate_starts, order] = sort(candidate_starts);
candidate_peaks = candidate_peaks(order);
if isempty(candidate_starts)
    candidate_starts = best_sync_sample-(frame.sync_start-1)*sps;
    candidate_peaks = best_peak;
end
result = struct('frame_start_sample', ...
    best_sync_sample-(frame.sync_start-1)*sps, ...
    'sync_start_sample', best_sync_sample, ...
    'sample_phase', best_phase, 'metric_peak', best_peak, ...
    'metric_trace', best_trace, 'peak_locations', best_locations, ...
    'candidate_frame_starts', candidate_starts, ...
    'candidate_peaks', candidate_peaks);
end

function [corrected, info] = correct_sro_dispatch( ...
        samples, reference, nominal_frame_samples, sps, maximum_ppm, ...
        frame, cfg, mode)
policy = sro_decision_policy(cfg);
factor = sro_observation_oversample_factor(cfg);
if strcmp(policy, 'legacy') && factor == 1
    [corrected, info] = correct_sro(samples, reference, ...
        nominal_frame_samples, sps, maximum_ppm, frame, cfg, mode);
    info.estimator = 'legacy_peak_slope';
    info.decision_policy = 'legacy';
    info.observation_oversample_factor = 1;
    info.correction_weight = double(info.recommended);
    info.correction_ppm = info.correction_weight*info.sro_ppm;
    info.confidence_level = NaN;
    info.confidence_interval_ppm = [info.sro_ppm-info.apply_threshold_ppm, ...
        info.sro_ppm+info.apply_threshold_ppm];
    info.resolution_sigma_ppm = NaN;
    info.jackknife_sigma_ppm = NaN;
    info.leave_one_out_range_ppm = NaN;
    info.robust_weights = ones(numel(info.fit_peak_samples),1);
    info.robust_outlier_count = 0;
    return;
end
[corrected, info] = correct_sro_experimental(samples, reference, ...
    nominal_frame_samples, sps, maximum_ppm, frame, cfg, mode, policy, factor);
end

function [corrected, info] = correct_sro( ...
        samples, reference, nominal_frame_samples, sps, maximum_ppm, ...
        frame, cfg, mode)
combined = zeros(numel(samples),1);
for phase = 0:sps-1
    symbols = samples(phase+1:sps:end).';
    if numel(symbols) < numel(reference)
        continue;
    end
    correlation = conv(symbols, flipud(conj(reference)), 'valid');
    energy = conv(abs(symbols).^2, ones(numel(reference),1), 'valid');
    metric = abs(correlation).^2./max(sum(abs(reference).^2)*energy,eps);
    indices = phase+1+(0:numel(metric)-1)*sps;
    combined(indices) = metric;
end
[peak,~] = max(combined);
locations = zeros(0,1);
if isfinite(peak) && peak > 0
    try
        [~, locations] = findpeaks(combined, ...
            'MinPeakHeight', max(0.35*peak,eps), ...
            'MinPeakDistance', round(0.8*nominal_frame_samples));
    catch
        [~, locations] = max(combined);
    end
end
locations = double(locations(:));
locations = refine_peak_locations(combined, locations, sps);
candidate_frame_starts = locations-(frame.sync_start-1)*sps;
complete_mask = candidate_frame_starts >= 1 & ...
    candidate_frame_starts+nominal_frame_samples-1 <= numel(samples);
complete_peak_samples = locations(complete_mask);

repeat_count = 1;
if isfield(frame,'frame_repetitions') && isfinite(frame.frame_repetitions)
    repeat_count = max(1,round(double(frame.frame_repetitions)));
end
processing_rate = cfg.waveform.symbol_rate_hz*sps;
boundary_extra = NaN;
if isfield(frame,'awg_padded_waveform_length') && ...
        isfield(frame,'awg_waveform_length') && ...
        isfield(frame,'awg_sample_rate_hz') && ...
        isfinite(frame.awg_padded_waveform_length) && ...
        isfinite(frame.awg_waveform_length) && ...
        isfinite(frame.awg_sample_rate_hz) && frame.awg_sample_rate_hz > 0
    boundary_extra = (double(frame.awg_padded_waveform_length)- ...
        double(frame.awg_waveform_length))*processing_rate/ ...
        double(frame.awg_sample_rate_hz);
    if isfield(frame, 'sro_boundary_extra_awg_samples')
        boundary_extra = double(frame.sro_boundary_extra_awg_samples) * ...
            processing_rate/double(frame.awg_sample_rate_hz);
    end
end
if repeat_count == 1 && isfinite(boundary_extra)
    nominal_period_samples = double(frame.awg_padded_waveform_length)* ...
        processing_rate/double(frame.awg_sample_rate_hz);
else
    nominal_period_samples = double(nominal_frame_samples);
end

spacing = diff(locations);
[fit_interval_indices,boundary_interval_indices,fit_meta] = ...
    select_sro_peaks(spacing,repeat_count,boundary_extra);
if isempty(fit_interval_indices)
    fit_interval_indices = (1:numel(spacing)).';
end
adjusted_locations = locations;
if fit_meta.classified && isfinite(boundary_extra)
    for k = 2:numel(adjusted_locations)
        adjusted_locations(k) = adjusted_locations(k) - boundary_extra * ...
            sum(ismember(1:k-1,boundary_interval_indices(:).'));
    end
end
adjusted_spacing = diff(adjusted_locations);
fit_intervals = adjusted_spacing(fit_interval_indices);
raw_fit_intervals = spacing(fit_interval_indices);
fit_locations = locations;
fit = fit_peak_line(adjusted_locations, nominal_period_samples);

if isfinite(fit.slope_samples) && isfinite(nominal_period_samples) && ...
        nominal_period_samples > 0
    measured = fit.slope_samples;
    sro_ppm = (measured/nominal_period_samples-1)*1e6;
else
    measured = NaN;
    sro_ppm = NaN;
end
if isempty(fit_intervals)
    interval_median = NaN;
    max_deviation = NaN;
else
    interval_median = median(fit_intervals);
    max_deviation = max(abs(fit_intervals-interval_median));
end
fit_residual = fit.rmse_samples;
quantization_ppm = 1e6/max(nominal_period_samples,eps);
if numel(fit_intervals) >= 3
    mad_samples = median(abs(fit_intervals-interval_median));
    interval_sigma_ppm = 1.4826*mad_samples/sqrt(numel(fit_intervals)) / ...
        max(nominal_period_samples,eps)*1e6;
else
    interval_sigma_ppm = Inf;
end
slope_sigma_ppm = abs(fit.slope_sigma_samples / ...
    max(nominal_period_samples,eps))*1e6;
sro_sigma_ppm = max(interval_sigma_ppm,slope_sigma_ppm);
apply_threshold_ppm = max(0.5*quantization_ppm,3*sro_sigma_ppm);
has_boundary_requirement = repeat_count > 1 && isfinite(boundary_extra) && ...
    boundary_extra >= 2;
boundary_ok = ~has_boundary_requirement || fit_meta.classified || fit_meta.absent;
enough_peaks = numel(locations) >= 4;
enough_intervals = numel(fit_intervals) >= 2;
interval_consistency_limit = sro_interval_consistency_limit(cfg);
consistent = ~isempty(fit_intervals) && isfinite(max_deviation) && ...
    max_deviation <= interval_consistency_limit;
in_range = isfinite(sro_ppm) && abs(sro_ppm) <= maximum_ppm;
reliable = boundary_ok && enough_peaks && enough_intervals && consistent && ...
    isfinite(sro_sigma_ppm) && in_range;
recommended = reliable && abs(sro_ppm) > apply_threshold_ppm;
applied = recommended && strcmp(mode, 'apply');

if strcmp(mode, 'disabled')
    reason = 'disabled';
elseif isempty(locations)
    reason = 'insufficient_sync_peaks';
elseif has_boundary_requirement && ~fit_meta.classified && ~fit_meta.absent
    reason = 'ambiguous_awg_boundary_phase';
elseif ~enough_peaks || ~enough_intervals
    reason = 'insufficient_full_window_peaks';
elseif ~isfinite(sro_sigma_ppm)
    reason = 'fit_uncertainty_unavailable';
elseif ~consistent
    reason = 'internal_interval_scatter';
elseif ~in_range
    reason = 'estimate_out_of_range';
elseif abs(sro_ppm) <= apply_threshold_ppm
    reason = 'estimate_within_fit_uncertainty';
else
    reason = 'applied';
end

if applied
    scale = nominal_period_samples/measured;
    output_count = floor((numel(samples)-1)*scale)+1;
    source_axis = 1+(0:output_count-1)/scale;
    corrected = interp1(1:numel(samples),samples,source_axis,'pchip');
else
    corrected = samples;
end
info = struct('applied',applied,'recommended',recommended,'mode',mode, ...
    'sro_ppm',sro_ppm, ...
    'measured_frame_samples',measured,'nominal_period_samples', ...
    nominal_period_samples,'peak_samples',locations, ...
    'complete_peak_samples',complete_peak_samples, ...
    'eligible_peak_samples',complete_peak_samples, ...
    'fit_peak_samples',fit_locations, ...
    'adjusted_fit_peak_samples',adjusted_locations, ...
    'fit_interval_samples',fit_intervals, ...
    'raw_fit_interval_samples',raw_fit_intervals, ...
    'boundary_interval_indices',boundary_interval_indices, ...
    'boundary_extra_samples',boundary_extra, ...
    'boundary_classified',fit_meta.classified, ...
    'boundary_absent',fit_meta.absent, ...
    'boundary_score',fit_meta.score, ...
    'sro_phase_margin',fit_meta.phase_margin, ...
    'sro_fit_residual_samples',fit_residual, ...
    'max_interval_deviation_samples',max_deviation, ...
    'interval_consistency_limit_samples',interval_consistency_limit, ...
    'sro_sigma_ppm',sro_sigma_ppm, ...
    'fit_slope_samples',fit.slope_samples, ...
    'fit_slope_sigma_samples',fit.slope_sigma_samples, ...
    'quantization_ppm',quantization_ppm, ...
    'apply_threshold_ppm',apply_threshold_ppm, ...
    'fit_interval_count',numel(fit_intervals), ...
    'reliable',reliable,'sro_reason',reason, ...
    'candidate_frame_starts',candidate_frame_starts, ...
    'complete_frames',sum(complete_mask));
end

function [corrected, info] = correct_sro_experimental( ...
        samples, reference, nominal_frame_samples, sps, maximum_ppm, ...
        frame, cfg, mode, policy, factor)
analysis_samples = samples;
if factor > 1
    analysis_samples = resample(samples(:), factor, 1).';
end
analysis_sps = sps*factor;
analysis_frame_samples = nominal_frame_samples*factor;

combined = zeros(numel(analysis_samples),1);
for phase = 0:analysis_sps-1
    symbols = analysis_samples(phase+1:analysis_sps:end).';
    if numel(symbols) < numel(reference)
        continue;
    end
    correlation = conv(symbols, flipud(conj(reference)), 'valid');
    energy = conv(abs(symbols).^2, ones(numel(reference),1), 'valid');
    metric = abs(correlation).^2./max(sum(abs(reference).^2)*energy,eps);
    indices = phase+1+(0:numel(metric)-1)*analysis_sps;
    combined(indices) = metric;
end

[peak,~] = max(combined);
locations = zeros(0,1);
if isfinite(peak) && peak > 0
    try
        [~, locations] = findpeaks(combined, ...
            'MinPeakHeight', max(0.35*peak,eps), ...
            'MinPeakDistance', round(0.8*analysis_frame_samples));
    catch
        [~, locations] = max(combined);
    end
end
locations = double(locations(:));
locations = refine_peak_locations(combined, locations, 1);
candidate_frame_starts = locations-(frame.sync_start-1)*analysis_sps;
complete_mask = candidate_frame_starts >= 1 & ...
    candidate_frame_starts+analysis_frame_samples-1 <= numel(analysis_samples);
complete_peak_samples = locations(complete_mask);

repeat_count = 1;
if isfield(frame,'frame_repetitions') && isfinite(frame.frame_repetitions)
    repeat_count = max(1,round(double(frame.frame_repetitions)));
end
processing_rate = cfg.waveform.symbol_rate_hz*sps;
boundary_extra_original = NaN;
if isfield(frame,'awg_padded_waveform_length') && ...
        isfield(frame,'awg_waveform_length') && ...
        isfield(frame,'awg_sample_rate_hz') && ...
        isfinite(frame.awg_padded_waveform_length) && ...
        isfinite(frame.awg_waveform_length) && ...
        isfinite(frame.awg_sample_rate_hz) && frame.awg_sample_rate_hz > 0
    boundary_extra_original = (double(frame.awg_padded_waveform_length)- ...
        double(frame.awg_waveform_length))*processing_rate/ ...
        double(frame.awg_sample_rate_hz);
    if isfield(frame, 'sro_boundary_extra_awg_samples')
        boundary_extra_original = double(frame.sro_boundary_extra_awg_samples) * ...
            processing_rate/double(frame.awg_sample_rate_hz);
    end
end
if repeat_count == 1 && isfinite(boundary_extra_original)
    nominal_period_original = double(frame.awg_padded_waveform_length)* ...
        processing_rate/double(frame.awg_sample_rate_hz);
else
    nominal_period_original = double(nominal_frame_samples);
end
boundary_extra = boundary_extra_original*factor;
nominal_period_samples = nominal_period_original*factor;

spacing = diff(locations);
[fit_interval_indices,boundary_interval_indices,fit_meta] = ...
    select_sro_peaks(spacing,repeat_count,boundary_extra);
if isempty(fit_interval_indices)
    fit_interval_indices = (1:numel(spacing)).';
end
adjusted_locations = locations;
boundary_scale = 1;
measured_boundary_extra = boundary_extra;
if fit_meta.classified && isfinite(boundary_extra)
    internal_spacing = spacing(fit_interval_indices);
    candidate_scale = median(internal_spacing) / ...
        max(nominal_period_samples,eps);
    if isfinite(candidate_scale) && candidate_scale > 0
        boundary_scale = candidate_scale;
        measured_boundary_extra = boundary_extra*boundary_scale;
    end
    for k = 2:numel(adjusted_locations)
        adjusted_locations(k) = adjusted_locations(k) - measured_boundary_extra * ...
            sum(ismember(1:k-1,boundary_interval_indices(:).'));
    end
end
adjusted_spacing = diff(adjusted_locations);
fit_intervals = adjusted_spacing(fit_interval_indices);
raw_fit_intervals = spacing(fit_interval_indices);
fit = fit_peak_line_robust(adjusted_locations);

if isfinite(fit.slope_samples) && nominal_period_samples > 0
    measured = fit.slope_samples;
    sro_ppm = (measured/nominal_period_samples-1)*1e6;
else
    measured = NaN;
    sro_ppm = NaN;
end
if isempty(fit_intervals)
    interval_median = NaN;
    max_deviation = NaN;
else
    interval_median = median(fit_intervals);
    max_deviation = max(abs(fit_intervals-interval_median));
end
quantization_ppm = 1e6/max(nominal_period_samples,eps);
if numel(fit_intervals) >= 3
    mad_samples = median(abs(fit_intervals-interval_median));
    interval_sigma_ppm = 1.4826*mad_samples/sqrt(numel(fit_intervals)) / ...
        max(nominal_period_samples,eps)*1e6;
else
    interval_sigma_ppm = Inf;
end
resolution_sigma_samples = 1/sqrt(12*max(fit.sxx,eps));
fit.resolution_sigma_samples = resolution_sigma_samples;
fit.slope_sigma_samples = max([fit.slope_sigma_samples, ...
    fit.jackknife_sigma_samples,resolution_sigma_samples]);
slope_sigma_ppm = abs(fit.slope_sigma_samples / ...
    max(nominal_period_samples,eps))*1e6;
sro_sigma_ppm = max(interval_sigma_ppm,slope_sigma_ppm);
confidence_level = 0.99;
confidence_multiplier = student_t_critical(confidence_level, ...
    max(1,numel(adjusted_locations)-2));
apply_threshold_ppm = max(0.5*quantization_ppm, ...
    confidence_multiplier*sro_sigma_ppm);

has_boundary_requirement = repeat_count > 1 && isfinite(boundary_extra) && ...
    boundary_extra >= 2*factor;
boundary_ok = ~has_boundary_requirement || fit_meta.classified || fit_meta.absent;
enough_peaks = numel(locations) >= 4;
enough_intervals = numel(fit_intervals) >= 2;
interval_consistency_limit = sro_interval_consistency_limit(cfg);
consistent = ~isempty(fit_intervals) && isfinite(max_deviation) && ...
    max_deviation/factor <= interval_consistency_limit;
in_range = isfinite(sro_ppm) && abs(sro_ppm) <= maximum_ppm;
robust_support = numel(fit.weights) >= 4 && ...
    nnz(fit.weights >= 0.25) >= 4 && fit.outlier_count <= 1;
reliable = boundary_ok && enough_peaks && enough_intervals && consistent && ...
    isfinite(sro_sigma_ppm) && in_range && robust_support;

correction_weight = 0;
switch policy
    case 'conservative_ci'
        recommended = reliable && abs(sro_ppm) > apply_threshold_ppm;
        correction_weight = double(recommended);
    case 'confidence_weighted'
        if reliable && isfinite(sro_ppm) && abs(sro_ppm) > eps
            correction_weight = max(0,min(1, ...
                1-(sro_sigma_ppm/abs(sro_ppm))^2));
        end
        recommended = reliable && correction_weight > sqrt(eps);
    otherwise
        error('msiq:dsp:WzSroPolicy', ...
            'Experimental estimator requires a non-legacy decision policy.');
end
correction_ppm = correction_weight*sro_ppm;
applied = recommended && strcmp(mode, 'apply');

if strcmp(mode, 'disabled')
    reason = 'disabled';
elseif isempty(locations)
    reason = 'insufficient_sync_peaks';
elseif has_boundary_requirement && ~fit_meta.classified && ~fit_meta.absent
    reason = 'ambiguous_awg_boundary_phase';
elseif ~enough_peaks || ~enough_intervals
    reason = 'insufficient_full_window_peaks';
elseif ~isfinite(sro_sigma_ppm)
    reason = 'fit_uncertainty_unavailable';
elseif ~consistent
    reason = 'internal_interval_scatter';
elseif ~robust_support
    reason = 'unstable_peak_influence';
elseif ~in_range
    reason = 'estimate_out_of_range';
elseif ~recommended && strcmp(policy, 'confidence_weighted')
    reason = 'confidence_weight_zero';
elseif ~recommended
    reason = 'estimate_within_fit_uncertainty';
elseif strcmp(policy, 'conservative_ci')
    reason = 'recommended_conservative_ci';
else
    reason = 'recommended_confidence_weighted';
end

if applied
    scale = 1/(1+correction_ppm*1e-6);
    output_count = floor((numel(samples)-1)*scale)+1;
    source_axis = 1+(0:output_count-1)/scale;
    corrected = interp1(1:numel(samples),samples,source_axis,'pchip');
else
    corrected = samples;
end

to_original = @(value) 1+(value-1)/factor;
confidence_interval_ppm = [sro_ppm-apply_threshold_ppm, ...
    sro_ppm+apply_threshold_ppm];
info = struct('applied',applied,'recommended',recommended,'mode',mode, ...
    'sro_ppm',sro_ppm,'correction_ppm',correction_ppm, ...
    'correction_weight',correction_weight, ...
    'estimator','oversampled_robust_peak_slope', ...
    'decision_policy',policy,'observation_oversample_factor',factor, ...
    'confidence_level',confidence_level, ...
    'confidence_multiplier',confidence_multiplier, ...
    'confidence_interval_ppm',confidence_interval_ppm, ...
    'measured_frame_samples',measured/factor, ...
    'nominal_period_samples',nominal_period_original, ...
    'peak_samples',to_original(locations), ...
    'complete_peak_samples',to_original(complete_peak_samples), ...
    'eligible_peak_samples',to_original(complete_peak_samples), ...
    'fit_peak_samples',to_original(locations), ...
    'adjusted_fit_peak_samples',to_original(adjusted_locations), ...
    'fit_interval_samples',fit_intervals/factor, ...
    'raw_fit_interval_samples',raw_fit_intervals/factor, ...
    'boundary_interval_indices',boundary_interval_indices, ...
    'boundary_extra_samples',boundary_extra_original, ...
    'measured_boundary_extra_samples',measured_boundary_extra/factor, ...
    'boundary_scale',boundary_scale, ...
    'boundary_classified',fit_meta.classified, ...
    'boundary_absent',fit_meta.absent,'boundary_score',fit_meta.score/factor, ...
    'sro_phase_margin',fit_meta.phase_margin, ...
    'sro_fit_residual_samples',fit.rmse_samples/factor, ...
    'max_interval_deviation_samples',max_deviation/factor, ...
    'interval_consistency_limit_samples',interval_consistency_limit, ...
    'sro_sigma_ppm',sro_sigma_ppm, ...
    'resolution_sigma_ppm',resolution_sigma_samples / ...
    max(nominal_period_samples,eps)*1e6, ...
    'jackknife_sigma_ppm',fit.jackknife_sigma_samples / ...
    max(nominal_period_samples,eps)*1e6, ...
    'leave_one_out_range_ppm',fit.leave_one_out_range_samples / ...
    max(nominal_period_samples,eps)*1e6, ...
    'robust_weights',fit.weights(:), ...
    'robust_outlier_count',fit.outlier_count, ...
    'fit_slope_samples',fit.slope_samples/factor, ...
    'fit_slope_sigma_samples',fit.slope_sigma_samples/factor, ...
    'quantization_ppm',quantization_ppm, ...
    'apply_threshold_ppm',apply_threshold_ppm, ...
    'fit_interval_count',numel(fit_intervals), ...
    'reliable',reliable,'sro_reason',reason, ...
    'candidate_frame_starts',to_original(candidate_frame_starts), ...
    'complete_frames',sum(complete_mask));
end

function limit = sro_interval_consistency_limit(cfg)
limit = 1.25;
if isstruct(cfg) && isfield(cfg, 'receiver') && ...
        isstruct(cfg.receiver) && isfield(cfg.receiver, ...
        'sro_interval_consistency_limit_samples') && ...
        ~isempty(cfg.receiver.sro_interval_consistency_limit_samples) && ...
        isscalar(cfg.receiver.sro_interval_consistency_limit_samples) && ...
        isfinite(cfg.receiver.sro_interval_consistency_limit_samples) && ...
        cfg.receiver.sro_interval_consistency_limit_samples > 0
    limit = double(cfg.receiver.sro_interval_consistency_limit_samples);
end
end

function policy = sro_decision_policy(cfg)
policy = 'legacy';
if isstruct(cfg) && isfield(cfg, 'receiver') && ...
        isstruct(cfg.receiver) && isfield(cfg.receiver, ...
        'sro_decision_policy') && ~isempty(cfg.receiver.sro_decision_policy)
    policy = lower(char(string(cfg.receiver.sro_decision_policy)));
end
allowed = {'legacy','conservative_ci','confidence_weighted'};
if ~ismember(policy, allowed)
    error('msiq:dsp:WzSroPolicy', ...
        'SRO decision policy must be legacy, conservative_ci, or confidence_weighted.');
end
end

function factor = sro_observation_oversample_factor(cfg)
factor = 1;
if isstruct(cfg) && isfield(cfg, 'receiver') && ...
        isstruct(cfg.receiver) && isfield(cfg.receiver, ...
        'sro_observation_oversample_factor') && ...
        ~isempty(cfg.receiver.sro_observation_oversample_factor)
    factor = double(cfg.receiver.sro_observation_oversample_factor);
end
if ~isscalar(factor) || ~isfinite(factor) || factor < 1 || ...
        factor > 16 || abs(factor-round(factor)) > 1e-12
    error('msiq:dsp:WzSroOversample', ...
        'SRO observation oversample factor must be an integer from 1 to 16.');
end
factor = round(factor);
end

function critical = student_t_critical(confidence, degrees_of_freedom)
alpha = 1-double(confidence);
degrees_of_freedom = max(1,double(degrees_of_freedom));
beta_value = betaincinv(alpha, degrees_of_freedom/2, 0.5);
critical = sqrt(degrees_of_freedom*(1/max(beta_value,eps)-1));
end

function mode = normalize_sro_mode(value)
mode = lower(char(string(value)));
if ~ismember(mode, {'apply','observe','disabled'})
    error('msiq:dsp:WzSroMode', ...
        'SRO mode must be apply, observe, or disabled.');
end
end

function refined = refine_peak_locations(metric, locations, sps)
refined = double(locations(:));
metric = double(metric(:));
for k = 1:numel(refined)
    index = round(refined(k));
    if index-sps < 1 || index+sps > numel(metric)
        continue;
    end
    ym = metric(index-sps);
    y0 = metric(index);
    yp = metric(index+sps);
    denominator = ym-2*y0+yp;
    if ~isfinite(denominator) || abs(denominator) < eps
        continue;
    end
    delta = 0.5*(ym-yp)/denominator;
    if isfinite(delta) && abs(delta) <= 0.5
        refined(k) = index+delta*sps;
    end
end
end

function fit = fit_peak_line(locations, nominal_period)
fit = struct('slope_samples',NaN,'slope_sigma_samples',Inf, ...
    'rmse_samples',NaN);
if numel(locations) < 2 || ~isfinite(nominal_period) || nominal_period <= 0
    return;
end
x = (0:numel(locations)-1).';
y = double(locations(:));
coefficients = polyfit(x,y,1);
residuals = y-polyval(coefficients,x);
fit.slope_samples = coefficients(1);
fit.rmse_samples = sqrt(mean(residuals.^2));
if numel(y) >= 3
    fit.slope_sigma_samples = sqrt(sum(residuals.^2) / ...
        max(1,numel(y)-2) / max(sum((x-mean(x)).^2),eps));
end
end

function fit = fit_peak_line_robust(locations)
locations = double(locations(:));
fit = struct('slope_samples',NaN,'slope_sigma_samples',Inf, ...
    'jackknife_sigma_samples',Inf,'leave_one_out_range_samples',Inf, ...
    'resolution_sigma_samples',Inf,'rmse_samples',NaN,'weights',zeros(0,1), ...
    'outlier_count',0,'sxx',0);
if numel(locations) < 2
    return;
end
x = (0:numel(locations)-1).';
[coefficients, weights, residuals] = huber_line_core(x, locations);
fit.slope_samples = coefficients(2);
fit.rmse_samples = sqrt(mean(residuals.^2));
fit.weights = weights;
fit.outlier_count = nnz(weights < 0.25);
weighted_mean = sum(weights.*x)/max(sum(weights),eps);
fit.sxx = sum(weights.*(x-weighted_mean).^2);

design = [ones(size(x)),x];
bread = pinv(design.'*(design.*weights));
variance = sum(weights.*residuals.^2)/max(1,sum(weights)-2);
fit.slope_sigma_samples = sqrt(max(0,variance*bread(2,2)));

if numel(locations) >= 4
    leave_one_out = NaN(numel(locations),1);
    for index = 1:numel(locations)
        keep = true(numel(locations),1);
        keep(index) = false;
        reduced = huber_line_core(x(keep), locations(keep));
        leave_one_out(index) = reduced(2);
    end
    center = mean(leave_one_out,'omitnan');
    fit.jackknife_sigma_samples = sqrt((numel(locations)-1)/ ...
        numel(locations)*sum((leave_one_out-center).^2,'omitnan'));
    fit.leave_one_out_range_samples = ...
        max(leave_one_out)-min(leave_one_out);
end
end

function [coefficients, weights, residuals] = huber_line_core(x, y)
x = double(x(:));
y = double(y(:));
design = [ones(size(x)),x];
coefficients = design\y;
weights = ones(size(y));
for iteration = 1:12
    residuals = y-design*coefficients;
    scale = 1.4826*median(abs(residuals-median(residuals)));
    if ~isfinite(scale) || scale <= eps(max(1,max(abs(y))))
        break;
    end
    normalized = abs(residuals)/scale;
    next_weights = ones(size(weights));
    tail = normalized > 1.345;
    next_weights(tail) = 1.345./normalized(tail);
    weighted_design = design.*sqrt(next_weights);
    next_coefficients = weighted_design\(y.*sqrt(next_weights));
    if norm(next_coefficients-coefficients) <= ...
            1e-12*max(1,norm(coefficients))
        coefficients = next_coefficients;
        weights = next_weights;
        break;
    end
    coefficients = next_coefficients;
    weights = next_weights;
end
residuals = y-design*coefficients;
end

function [fit_interval_indices,boundary_indices,meta] = ...
        select_sro_peaks(spacing,repeat_count,boundary_extra)
% Classify only a known AWG padding boundary; all other intervals are internal.
spacing = double(spacing(:));
fit_interval_indices = zeros(0,1);
boundary_indices = zeros(0,1);
meta = struct('classified',false,'absent',false, ...
    'phase_margin',NaN,'score',Inf);
if repeat_count <= 1 || ~isfinite(boundary_extra) || ...
        boundary_extra < 2 || numel(spacing) < repeat_count
    return;
end
base = median(spacing);
scatter = median(abs(spacing-base));
boundary_tolerance = max(1.5,0.35*boundary_extra);
if scatter <= max(1.25,0.02*boundary_extra) && ...
        ~any(abs(spacing-(base+boundary_extra)) <= boundary_tolerance)
    meta.absent = true;
    meta.phase_margin = Inf;
    meta.score = scatter;
    fit_interval_indices = (1:numel(spacing)).';
    return;
end
scores = Inf(repeat_count,1);
boundary_masks = false(numel(spacing),repeat_count);
for phase = 0:repeat_count-1
    is_boundary = mod((1:numel(spacing)).'-phase, repeat_count) == 0;
    internal = spacing(~is_boundary);
    boundary = spacing(is_boundary);
    if numel(internal) < 2 || isempty(boundary)
        continue;
    end
    base = median(internal);
    internal_error = median(abs(internal-base));
    boundary_error = median(abs(boundary-(base+boundary_extra)));
    scores(phase+1) = internal_error + boundary_error;
    boundary_masks(:,phase+1) = is_boundary;
end
[best_score,best_phase] = min(scores);
if ~isfinite(best_score)
    return;
end
finite_scores = sort(scores(isfinite(scores)));
if numel(finite_scores) >= 2
    phase_margin = finite_scores(2)/(best_score+eps);
else
    phase_margin = Inf;
end
boundary_mask = boundary_masks(:,best_phase);
internal = spacing(~boundary_mask);
boundary = spacing(boundary_mask);
base = median(internal);
offset = median(boundary)-base;
boundary_residual = median(abs((boundary-base)-boundary_extra));
meta.classified = isfinite(best_score) && phase_margin >= 1.25 && ...
    offset >= max(2,0.5*boundary_extra) && ...
    boundary_residual <= max(1.5,0.35*boundary_extra);
meta.phase_margin = phase_margin;
meta.score = best_score;
if meta.classified
    boundary_indices = find(boundary_mask);
    fit_interval_indices = find(~boundary_mask);
end
end
