function result = decode_capture(raw, tx_ref, cfg)
%DECODE_CAPTURE Synchronize, equalize, form LLRs, and decode one subband.

if nargin < 3 || isempty(cfg)
    cfg = msiq.build_config('v2_default');
elseif ~isstruct(cfg)
    cfg = msiq.build_config(cfg);
end
if ~isstruct(tx_ref) || ~isfield(tx_ref, 'pairs')
    error('msiq:decode:ReferenceFormat', ...
        'tx_ref from msiq.generate_waveforms is required.');
end
if ~strcmp(tx_ref.frame.reference_payload_policy, 'metrics_only')
    error('msiq:decode:ReferencePolicy', ...
        'Reference payload policy must remain metrics_only.');
end
assert_reference_configuration(tx_ref, cfg);

pair_name = 'A';
if isfield(raw, 'payload_pair') && ~isempty(raw.payload_pair)
    pair_name = upper(char(string(raw.payload_pair)));
end
pair_index = find(strcmp({tx_ref.pairs.name}, pair_name), 1);
if isempty(pair_index)
    error('msiq:decode:PayloadPair', ...
        'Unknown payload pair: %s', pair_name);
end
pair_ref = tx_ref.pairs(pair_index);
if ~strcmpi(pair_ref.architecture, cfg.waveform.architecture)
    error('msiq:decode:ArchitectureMismatch', ...
        'Decoder architecture does not match the TX reference.');
end

architecture = lower(char(string(pair_ref.architecture)));
use_wz_single = strcmp(architecture, 'single_complex_stream') && ...
    isfield(cfg.receiver, 'single_equalizer') && ...
    strcmpi(cfg.receiver.single_equalizer, 'wz_wl_fse_nlms');
if use_wz_single
    [frame_symbols, synchronization, preparation, iq_orientation, ...
        primary_equalizer] = ...
        synchronize_wz_with_iq_orientation(raw, tx_ref, cfg, pair_ref);
else
    [baseband, preparation] = msiq.dsp.prepare_capture(raw, cfg);
    [frame_symbols, synchronization] = ...
        msiq.dsp.synchronize(baseband, tx_ref, cfg);
end

if strcmp(architecture, 'dual_iq_mimo')
    if size(frame_symbols,2) ~= 2
        error('msiq:decode:DualInputCount', ...
            'Dual IQ-MIMO decoding requires two received inputs.');
    end
    [primary_equalizer, diagnostic_equalizer] = ...
        msiq.dsp.equalize_dual(frame_symbols, pair_ref, cfg);
    primary_streams = decode_streams(primary_equalizer.symbols, pair_ref, cfg);
    diagnostic_streams = decode_streams( ...
        diagnostic_equalizer.symbols, pair_ref, cfg);
else
    if ~use_wz_single
        primary_equalizer = msiq.dsp.equalize_single_wl( ...
            frame_symbols, pair_ref, cfg);
    end
    diagnostic_equalizer = struct('name', 'not_applicable', ...
        'selection_policy', 'single_stream_wl_fse_only');
    primary_streams = decode_streams( ...
        primary_equalizer.symbols, pair_ref, cfg);
    diagnostic_streams = struct([]);
end

clip_fraction = capture_clip_fraction(raw);
result = struct();
result.schema_version = '2.0';
result.waveform_id = tx_ref.waveform_id;
result.payload_pair = pair_name;
result.architecture = architecture;
result.sync_ok = synchronization.ok;
result.synchronization = synchronization;
result.preparation = preparation;
if use_wz_single
    result.iq_orientation = iq_orientation;
end
result.primary_equalizer = rmfield(primary_equalizer, 'symbols');
result.primary_streams = primary_streams;
result.diagnostic_equalizer = remove_if_present( ...
    diagnostic_equalizer, 'symbols');
result.diagnostic_streams = diagnostic_streams;
if use_wz_single
    result.equalizer_selection_policy = ...
        'wz_training_pilot_dd_no_payload_reference';
else
    result.equalizer_selection_policy = ...
        'fixed_primary_no_payload_ber_selection';
end
result.payload_reference_used_for_processing = false;
result.reference_payload_policy = 'metrics_only';
result.clip_fraction = clip_fraction;
result.clipped = any(clip_fraction > 0);
result.complete_block_count = sum([primary_streams.block_count]);
result.discarded_incomplete_block_count = ...
    sum([primary_streams.incomplete_tail_bits] > 0);
result.pass = stream_pass(primary_streams) && ~result.clipped;
if isfield(cfg.receiver, 'debug_pre_fec_only') && ...
        isequal(cfg.receiver.debug_pre_fec_only, true)
    result.debug_pre_fec_only = true;
    result.valid = result.sync_ok && ~result.clipped && ...
        ~isempty(primary_streams) && all([primary_streams.valid]);
    result.pass = result.valid;
    result.pass_policy = 'complete_pre_fec_statistics_not_zero_ber';
end
end

function [frame_symbols, synchronization, preparation, orientation, ...
        primary_equalizer] = ...
        synchronize_wz_with_iq_orientation(raw, tx_ref, cfg, pair_ref)
[observation_baseband, observation_preparation] = ...
    msiq.dsp.prepare_capture(raw, cfg);
candidates = [evaluate_orientation(observation_baseband, false, tx_ref, cfg), ...
    evaluate_orientation(observation_baseband, true, tx_ref, cfg)];
valid = [candidates.valid];
if ~any(valid)
    error('msiq:decode:IQOrientationFailed', ...
        '正常和镜像候选均无法同步，解调停止。正常：%s；镜像：%s', ...
        candidate_reason(candidates(1)), candidate_reason(candidates(2)));
end
if all(valid)
    candidates = score_orientation_training(candidates, pair_ref, cfg);
end
selected = select_orientation_candidate(candidates);
alternate = 3-selected;
retry_count = 0;
selected_error = '';
try
    [frame_symbols, synchronization, preparation, primary_equalizer] = ...
        run_orientation(raw, candidates(selected), tx_ref, cfg, pair_ref, ...
        observation_preparation);
catch exception
    selected_error = sprintf('[%s] %s', exception.identifier, exception.message);
    retry_count = 1;
    try
        [frame_symbols, synchronization, preparation, primary_equalizer] = ...
            run_orientation(raw, candidates(alternate), tx_ref, cfg, ...
            pair_ref, observation_preparation);
        selected = alternate;
    catch alternate_exception
        error('msiq:decode:IQOrientationFailed', ...
            ['正常和镜像候选均无法同步，解调停止。首选失败：%s；' ...
            '备用失败：[%s] %s'], selected_error, ...
            alternate_exception.identifier, alternate_exception.message);
    end
end
orientation = struct('selected', candidates(selected).name, ...
    'conjugate_applied', candidates(selected).conjugate_applied, ...
    'status_text', ternary(candidates(selected).conjugate_applied, ...
    '检测到 IQ 镜像，已自动校正', 'IQ 镜像正常'), ...
    'selection_policy', ...
    'sync_valid_then_probe_nmse_then_sync_metric_normal_on_exact_tie', ...
    'locked_for_capture', true, 'alternate_retry_count', retry_count, ...
    'selected_attempt_error', selected_error, ...
    'candidates', public_orientation_candidates(candidates));
preparation.iq_orientation = orientation;
end

function candidate = evaluate_orientation(baseband, conjugate_applied, ...
        tx_ref, cfg)
candidate = struct('name', ternary(conjugate_applied, 'conjugate', 'normal'), ...
    'conjugate_applied', conjugate_applied, 'valid', false, ...
    'sync_valid', false, 'training_evaluated', false, ...
    'training_valid', false, 'sync_metric', NaN, ...
    'training_nmse', Inf, 'training_taps', NaN, 'training_passes', NaN, ...
    'error_identifier', '', 'error_message', '', ...
    'observation', struct(), 'frame_symbols', complex([]));
trial = orient_baseband(baseband, conjugate_applied);
trial_cfg = cfg;
required_metric = double(cfg.receiver.sync_metric_min);
trial_cfg.receiver.sync_metric_min = 0;
warning_id = 'signal:findpeaks:largeMinPeakHeight';
warning_state = warning('query', warning_id);
warning_cleanup = onCleanup(@() warning(warning_state.state, warning_id));
warning('off', warning_id);
try
    [frame, observation] = msiq.dsp.synchronize_single_wz( ...
        trial, tx_ref, trial_cfg, false, 'observe');
    candidate.observation = observation;
    candidate.frame_symbols = frame;
    candidate.sync_metric = double(observation.sync_metric);
    candidate.sync_valid = isfinite(candidate.sync_metric) && ...
        candidate.sync_metric >= required_metric;
    candidate.valid = candidate.sync_valid;
catch exception
    candidate.error_identifier = exception.identifier;
    candidate.error_message = exception.message;
end
end

function candidates = score_orientation_training(candidates, pair_ref, cfg)
probe_cfg = orientation_probe_config(cfg);
for index = 1:numel(candidates)
    candidates(index).training_evaluated = true;
    candidates(index).training_taps = probe_cfg.receiver.wl_taps;
    candidates(index).training_passes = probe_cfg.receiver.wl_passes;
    try
        equalizer = msiq.dsp.equalize_single_wz( ...
            candidates(index).frame_symbols, pair_ref, probe_cfg, true);
        candidates(index).training_nmse = double(equalizer.training_nmse);
        candidates(index).training_valid = ...
            isfinite(candidates(index).training_nmse);
        candidates(index).valid = candidates(index).sync_valid && ...
            candidates(index).training_valid;
    catch exception
        candidates(index).valid = false;
        candidates(index).error_identifier = exception.identifier;
        candidates(index).error_message = exception.message;
    end
end
end

function probe_cfg = orientation_probe_config(cfg)
probe_cfg = cfg;
taps = min(41, round(double(cfg.receiver.wl_taps)));
if mod(taps, 2) == 0
    taps = taps-1;
end
probe_cfg.receiver.wl_taps = max(3, taps);
probe_cfg.receiver.wl_passes = max(1, min(2, ...
    round(double(cfg.receiver.wl_passes))));
end

function selected = select_orientation_candidate(candidates)
sync_valid = find([candidates.sync_valid]);
if numel(sync_valid) == 1
    selected = sync_valid;
    return;
end
training_valid = find([candidates.training_valid]);
if numel(training_valid) == 1
    selected = training_valid;
    return;
end
normal = candidates(1);
mirrored = candidates(2);
if all([normal.training_valid, mirrored.training_valid]) && ...
        normal.training_nmse < mirrored.training_nmse
    selected = 1;
elseif all([normal.training_valid, mirrored.training_valid]) && ...
        mirrored.training_nmse < normal.training_nmse
    selected = 2;
elseif normal.sync_metric >= mirrored.sync_metric
    selected = 1;
else
    selected = 2;
end
end

function [frame_symbols, synchronization, preparation, primary_equalizer] = ...
        run_orientation(raw, candidate, tx_ref, cfg, pair_ref, ...
        observation_preparation)
if isstruct(candidate.observation) && isfield(candidate.observation, ...
        'sro_recommended')
    observation = candidate.observation;
else
    [baseband, ~] = msiq.dsp.prepare_capture(raw, cfg);
    baseband = orient_baseband(baseband, candidate.conjugate_applied);
    trial_cfg = cfg;
    trial_cfg.receiver.sync_metric_min = 0;
    [~, observation] = msiq.dsp.synchronize_single_wz( ...
        baseband, tx_ref, trial_cfg, false, 'observe');
end
[raw_for_decode, raw_sro_correction] = apply_observed_raw_sro(raw, observation);
[baseband, preparation] = msiq.dsp.prepare_capture(raw_for_decode, cfg);
baseband = orient_baseband(baseband, candidate.conjugate_applied);
[frame_symbols, synchronization] = msiq.dsp.synchronize_single_wz( ...
    baseband, tx_ref, cfg, false, 'disabled');
primary_equalizer = msiq.dsp.equalize_single_wz( ...
    frame_symbols, pair_ref, cfg);
synchronization = attach_raw_sro_diagnostics(synchronization, ...
    observation, raw_sro_correction);
preparation.sro_observation = compact_preparation(observation_preparation);
preparation.raw_sro_correction = raw_sro_correction;
end

function value = orient_baseband(value, conjugate_applied)
if conjugate_applied
    value = conj(value);
end
end

function reason = candidate_reason(candidate)
if ~isempty(candidate.error_message)
    reason = sprintf('[%s] %s', candidate.error_identifier, ...
        candidate.error_message);
elseif ~candidate.sync_valid
    reason = sprintf('同步指标 %.4g 未达到门限', candidate.sync_metric);
elseif ~candidate.training_valid
    reason = '训练段无法建立有效均衡';
else
    reason = '候选有效';
end
end

function value = public_orientation_candidates(candidates)
value = rmfield(candidates, {'observation','frame_symbols'});
end

function [raw_for_decode, correction] = apply_observed_raw_sro(raw, observation)
correction_ppm = observation.sro_ppm;
if isfield(observation, 'sro_correction_ppm') && ...
        isfinite(observation.sro_correction_ppm)
    correction_ppm = observation.sro_correction_ppm;
end
if observation.sro_recommended
    [raw_for_decode, correction] = msiq.dsp.correct_raw_sro( ...
        raw, correction_ppm);
else
    raw_for_decode = raw;
    sample_count = size(raw.samples,1);
    channel_count = size(raw.samples,2);
    correction = struct('applied',false,'stage','not_applied', ...
        'sro_ppm',observation.sro_ppm,'inverse_resample_scale',NaN, ...
        'input_samples',sample_count,'output_samples',sample_count, ...
        'time_axes_rebuilt',false,'channel_time_offsets_samples', ...
        zeros(1,channel_count));
end

correction.recommended = observation.sro_recommended;
correction.reliable = observation.sro_reliable;
correction.reason = observation.sro_reason;
correction.estimated_sro_ppm = observation.sro_ppm;
correction.requested_correction_ppm = correction_ppm;
correction.correction_weight = field_or(observation, ...
    'sro_correction_weight', double(observation.sro_recommended));
correction.decision_policy = char(string(field_or(observation, ...
    'sro_decision_policy', 'legacy')));
end

function assert_reference_configuration(tx_ref, cfg)
spec = msiq.fec.specification(cfg);
if isfield(tx_ref, 'fec_config')
    reference_spec = tx_ref.fec_config;
else
    reference_spec = struct('frame_type', 'normal', ...
        'codeword_length', 64800, 'info_length', 58320);
end
if ~strcmp(spec.frame_type, reference_spec.frame_type) || ...
        spec.codeword_length ~= reference_spec.codeword_length || ...
        spec.info_length ~= reference_spec.info_length
    error('msiq:decode:ConfigurationMismatch', ...
        'Decoder FEC does not match the TX reference.');
end
frame = tx_ref.frame;
waveform = cfg.waveform;
mismatches = cell(0, 1);
mismatches = compare_number(mismatches, frame, ...
    'master_samples_per_symbol', waveform.master_samples_per_symbol, 0, 'UP');
mismatches = compare_number(mismatches, frame, ...
    'master_sample_rate_hz', waveform.master_sample_rate_hz, 1, ...
    'master sample rate');
reference_order = field_or(tx_ref, 'modulation_order', ...
    field_or(frame, 'modulation_order', 16));
if double(reference_order) ~= double(waveform.modulation_order)
    mismatches{end+1} = sprintf('modulation TX=%g RX=%g', ...
        double(reference_order), double(waveform.modulation_order));
end
checks = { ...
    'sync_length', 'sync_length_symbols', 'sync length'; ...
    'sync_repeats', 'sync_repeats', 'sync repeats'; ...
    'training_length', 'training_symbols', 'training length'; ...
    'pilot_interval_symbols', 'pilot_interval_symbols', 'pilot interval'; ...
    'guard_symbols', 'guard_symbols', 'guard length'; ...
    'ldpc_blocks_per_frame', 'ldpc_blocks_per_frame', 'LDPC blocks/frame'; ...
    'frame_repetitions', 'frame_repetitions', 'frame repetitions'};
for k = 1:size(checks, 1)
    if isfield(frame, checks{k, 1})
        mismatches = compare_number(mismatches, frame, checks{k, 1}, ...
            waveform.(checks{k, 2}), 0, checks{k, 3});
    end
end
if ~isempty(mismatches)
    error('msiq:decode:ConfigurationMismatch', ...
        'Decoder configuration does not match the TX reference: %s.', ...
        strjoin(mismatches, '; '));
end
end

function mismatches = compare_number(mismatches, source, name, expected, ...
        tolerance, label)
if ~isfield(source, name) || isempty(source.(name)) || ...
        ~isfinite(double(source.(name))) || ...
        abs(double(source.(name))-double(expected)) > tolerance
    actual = NaN;
    if isfield(source, name) && ~isempty(source.(name))
        actual = double(source.(name));
    end
    mismatches{end+1} = sprintf('%s TX=%g RX=%g', ...
        label, actual, double(expected));
end
end

function synchronization = attach_raw_sro_diagnostics( ...
        synchronization, observation, correction)
final = struct('sro_ppm',synchronization.sro_ppm, ...
    'sro_recommended',synchronization.sro_recommended, ...
    'sro_reliable',synchronization.sro_reliable, ...
    'sro_reason',synchronization.sro_reason, ...
    'sro_correction_mode',synchronization.sro_correction_mode, ...
    'sro_low_rate_resample_applied', ...
    synchronization.sro_low_rate_resample_applied);
synchronization.sro_observation = observation;
synchronization.sro_raw_correction = correction;
synchronization.sro_correction_stage = correction.stage;
synchronization.sro_final_pass = final;
synchronization.sro_ppm = observation.sro_ppm;
synchronization.sro_applied = correction.applied;
synchronization.sro_recommended = observation.sro_recommended;
synchronization.sro_reliable = observation.sro_reliable;
synchronization.sro_reason = observation.sro_reason;
observation_fields = {'sro_estimator','sro_decision_policy', ...
    'sro_observation_oversample_factor','sro_correction_ppm', ...
    'sro_correction_weight','sro_confidence_level', ...
    'sro_confidence_interval_ppm','sro_resolution_sigma_ppm', ...
    'sro_jackknife_sigma_ppm','sro_leave_one_out_range_ppm', ...
    'sro_robust_weights','sro_robust_outlier_count', ...
    'sro_measured_boundary_extra_samples','sro_boundary_scale', ...
    'sro_sigma_ppm','sro_apply_threshold_ppm'};
for index = 1:numel(observation_fields)
    name = observation_fields{index};
    if isfield(observation, name)
        synchronization.(name) = observation.(name);
    end
end
synchronization.sro_correction_mode = 'raw_input_two_pass';
synchronization.sro_low_rate_resample_applied = false;
end

function value = compact_preparation(preparation)
value = rmfield(preparation, {'baseband_preview_indices','baseband_preview'});
end

function streams = decode_streams(equalized, pair_ref, cfg)
if isvector(equalized)
    equalized = equalized(:);
end
stream_count = size(equalized,2);
streams = repmat(empty_stream(), 1, stream_count);
for stream = 1:stream_count
    known_index = min(stream, numel(pair_ref.receiver_known));
    metrics_index = min(stream, numel(pair_ref.metrics_only));
    known = pair_ref.receiver_known(known_index);
    metrics_ref = pair_ref.metrics_only(metrics_index);
    pre_tracking = equalized(known.frame.payload_positions_frame, stream);
    [tracked, tracking] = msiq.dsp.pilot_track( ...
        equalized(:,stream), known, cfg);
    payload = tracked(known.frame.payload_positions_frame);
    finite = isfinite(real(pre_tracking)) & isfinite(imag(pre_tracking)) & ...
        isfinite(real(payload)) & isfinite(imag(payload));
    pre_tracking = pre_tracking(finite);
    payload = payload(finite);
    expected_symbols = metrics_ref.payload_symbol_count;
    payload_count = min([numel(pre_tracking), numel(payload), expected_symbols]);
    pre_tracking = pre_tracking(1:payload_count);
    payload = payload(1:payload_count);

    [evm, mer, noise_variance] = decision_metrics(payload, ...
        cfg.waveform.modulation_order, tracking.noise_variance);
    llr = qamdemod(payload, cfg.waveform.modulation_order, ...
        'OutputType', 'approxllr', 'UnitAveragePower', true, ...
        'NoiseVariance', noise_variance);
    scramble = metrics_ref.fec.scramble_bits(:);
    llr_count = min(numel(llr), numel(scramble));
    llr = double(llr(1:llr_count)) .* ...
        (1-2*double(scramble(1:llr_count)));
    fec_result = msiq.fec.decode_soft(llr, metrics_ref.fec, cfg);
    debug_pre = isfield(cfg.receiver, 'debug_pre_fec_only') && ...
        isequal(cfg.receiver.debug_pre_fec_only, true);
    if debug_pre && (~all(finite) || payload_count ~= expected_symbols)
        % Dropping a symbol changes bit alignment: no shortened BER is valid.
        fec_result.valid = false;
        fec_result.status = 'INCOMPLETE_PAYLOAD';
        fec_result.pre_fec_ber = NaN;
        fec_result.pre_fec_bit_count = 0;
        fec_result.pre_fec_bit_error_count = 0;
    end

    streams(stream).stream = stream;
    streams(stream).valid = fec_result.valid;
    streams(stream).evm_rms = evm;
    streams(stream).mer_db = mer;
    streams(stream).noise_variance = noise_variance;
    streams(stream).payload_symbol_count = numel(payload);
    streams(stream).pre_tracking_symbols = pre_tracking;
    streams(stream).constellation_symbols = payload;
    streams(stream).tracking = tracking;
    streams(stream).fec = fec_result;
    streams(stream).block_count = fec_result.block_count;
    streams(stream).block_error_count = fec_result.block_error_count;
    streams(stream).bler = fec_result.bler;
    streams(stream).pre_fec_ber = fec_result.pre_fec_ber;
    streams(stream).pre_fec_bit_error_count = fec_result.pre_fec_bit_error_count;
    streams(stream).pre_fec_bit_count = fec_result.pre_fec_bit_count;
    streams(stream).post_fec_ber = fec_result.post_fec_ber;
    streams(stream).actual_iterations = fec_result.actual_iterations;
    streams(stream).final_parity_checks = fec_result.final_parity_checks;
    streams(stream).parity_converged = fec_result.parity_converged;
    streams(stream).incomplete_tail_bits = fec_result.incomplete_tail_bits;
    streams(stream).pass = fec_result.valid && ...
        fec_result.block_count >= 1 && fec_result.parity_converged && ...
        fec_result.post_fec_ber == 0 && fec_result.bler == 0;
    if debug_pre
        streams(stream).pass = fec_result.valid;
    end
end
end

function [evm, mer, noise_variance] = decision_metrics(symbols, order, pilot_nv)
if isempty(symbols)
    evm = NaN;
    mer = NaN;
    noise_variance = max(pilot_nv, 1e-6);
    return;
end
indices = qamdemod(symbols, order, 'UnitAveragePower', true);
decisions = qammod(indices, order, 'UnitAveragePower', true);
error_value = symbols-decisions;
signal_power = mean(abs(decisions).^2);
error_power = mean(abs(error_value).^2);
evm = sqrt(error_power/max(signal_power, eps));
mer = 10*log10(max(signal_power, eps)/max(error_power, eps));
noise_variance = max([pilot_nv, error_power, 1e-10]);
end

function value = capture_clip_fraction(raw)
if isfield(raw, 'clip_fraction') && ~isempty(raw.clip_fraction)
    value = double(raw.clip_fraction(:)).';
elseif isfield(raw, 'full_scale') && ~isempty(raw.full_scale)
    scale = double(raw.full_scale);
    samples = double(raw.samples);
    value = mean(abs(samples) >= scale, 1);
else
    value = zeros(1, size(raw.samples,2));
end
end

function tf = stream_pass(streams)
tf = ~isempty(streams) && all([streams.pass]);
end

function value = remove_if_present(value, name)
if isstruct(value) && isfield(value, name)
    value = rmfield(value, name);
end
end

function value = field_or(source, name, fallback)
if isstruct(source) && isfield(source, name) && ~isempty(source.(name))
    value = source.(name);
else
    value = fallback;
end
end

function value = ternary(condition, yes_value, no_value)
if condition
    value = yes_value;
else
    value = no_value;
end
end

function stream = empty_stream()
stream = struct('stream', 0, 'valid', false, 'evm_rms', NaN, ...
    'mer_db', NaN, 'noise_variance', NaN, ...
    'payload_symbol_count', 0, 'pre_tracking_symbols', complex([]), ...
    'constellation_symbols', complex([]), ...
    'tracking', struct(), ...
    'fec', struct(), 'block_count', 0, 'block_error_count', 0, ...
    'bler', NaN, 'pre_fec_ber', NaN, 'post_fec_ber', NaN, ...
    'pre_fec_bit_error_count', 0, 'pre_fec_bit_count', 0, ...
    'actual_iterations', [], 'final_parity_checks', [], ...
    'parity_converged', false, 'incomplete_tail_bits', 0, ...
    'pass', false);
end
