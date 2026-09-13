function [waveforms, tx_ref] = generate_waveforms(cfg, seed)
%GENERATE_WAVEFORMS Generate two payload pairs for explicit four-DAC output.

if nargin < 1 || isempty(cfg)
    cfg = msiq.build_config('v2_default');
elseif ~isstruct(cfg)
    cfg = msiq.build_config(cfg);
end
if nargin < 2 || isempty(seed)
    seed = cfg.experiment.seed_values(1);
end
validateattributes(seed, {'numeric'}, {'scalar', 'integer', 'nonnegative'});

architecture = lower(char(string(cfg.waveform.architecture)));
if ~ismember(architecture, {'dual_iq_mimo', 'single_complex_stream'})
    error('msiq:waveform:Architecture', ...
        'Unsupported architecture: %s', architecture);
end

sps = shaping_samples_per_symbol(cfg.waveform);
rrc = rcosdesign(cfg.waveform.rolloff, ...
    cfg.waveform.rrc_span_symbols, sps, 'sqrt').';
sync_symbols = zc_sequence(cfg.waveform.sync_length_symbols, 25);
guard = zeros(cfg.waveform.guard_symbols, 1);
pair_names = {'A', 'B'};
pair_count = numel(pair_names);
stream_count = 2;

pair_refs = repmat(struct(), 1, pair_count);
symbol_frames = cell(pair_count, stream_count);
plot_frames = cell(1, pair_count);
for pair = 1:pair_count
    pair_refs(pair).name = pair_names{pair};
    pair_refs(pair).architecture = architecture;

    if strcmp(architecture, 'single_complex_stream')
        [frame, known, metrics, visual] = build_stream_frame( ...
            cfg, seed + 1000*pair + 1, sync_symbols, guard);
        symbol_frames{pair, 1} = frame;
        symbol_frames{pair, 2} = frame;
        plot_frames{pair} = visual;
        pair_refs(pair).receiver_known = repmat(known, 1, stream_count);
        pair_refs(pair).metrics_only = repmat(metrics, 1, stream_count);
    else
        known_list = cell(1, stream_count);
        metrics_list = cell(1, stream_count);
        visual_list = cell(1, stream_count);
        for stream = 1:stream_count
            stream_seed = seed + 1000*pair + 100*stream;
            [frame, known, metrics, visual] = build_stream_frame( ...
                cfg, stream_seed, sync_symbols, guard);
            symbol_frames{pair, stream} = frame;
            known_list{stream} = known;
            metrics_list{stream} = metrics;
            visual_list{stream} = visual;
        end
        plot_frames{pair} = visual_list{1};
        pair_refs(pair).receiver_known = [known_list{:}];
        pair_refs(pair).metrics_only = [metrics_list{:}];
    end
end

normalization_mode = waveform_normalization_mode(cfg.waveform);
master_columns = cell(1, 4);
scale_factors = ones(1, 4);
shaped_complex = cell(1, pair_count);
passband_complex = cell(1, pair_count);
for pair = 1:pair_count
    if strcmp(architecture, 'single_complex_stream')
        shaped = pulse_shape_at_master_rate( ...
            symbol_frames{pair, 1}, rrc, sps, cfg);
        carrier = exp(1j*2*pi*cfg.waveform.if_center_hz / ...
            cfg.waveform.master_sample_rate_hz * (0:numel(shaped)-1).');
        passband = shaped .* carrier;
        shaped_complex{pair} = shaped;
        passband_complex{pair} = passband;
        columns = {real(passband), imag(passband)};
    else
        columns = cell(1, 2);
        for stream = 1:2
            shaped = pulse_shape_at_master_rate( ...
                symbol_frames{pair, stream}, rrc, sps, cfg);
            carrier = exp(1j*2*pi*cfg.waveform.if_center_hz / ...
                cfg.waveform.master_sample_rate_hz * (0:numel(shaped)-1).');
            columns{stream} = real(shaped .* carrier);
        end
    end
    for stream = 1:2
        column_index = 2*(pair-1) + stream;
        if strcmp(normalization_mode, 'legacy_peak_scale')
            peak = max(abs(columns{stream}));
            scale_factors(column_index) = ...
                cfg.waveform.peak_scale / max(peak, eps);
        end
        master_columns{column_index} = columns{stream} * ...
            scale_factors(column_index);
    end
end

master_length = min(cellfun(@numel, master_columns));
master_data = zeros(master_length, 4);
for column = 1:4
    master_data(:, column) = master_columns{column}(1:master_length);
end
[master_data, tx_sro_precomp] = msiq.dsp.precompensate_tx_sro( ...
    master_data, cfg.waveform);
master_length = size(master_data, 1);

decimation = round(cfg.waveform.decimation);
if decimation == 1
    awg_data = master_data;
    awg_length = master_length;
else
    awg_columns = cell(1, 4);
    for column = 1:4
        awg_columns{column} = resample(master_data(:, column), 1, decimation);
    end
    awg_length = min(cellfun(@numel, awg_columns));
    awg_data = zeros(awg_length, 4);
    for column = 1:4
        awg_data(:, column) = awg_columns{column}(1:awg_length);
    end
end
[awg_data, tx_sro_precomp] = add_tx_sro_loop_guard(awg_data, tx_sro_precomp);
awg_length = size(awg_data, 1);
[awg_data, iq_calibration] = apply_iq_calibration(awg_data, cfg, architecture);
pair_scale_factors = ones(1, pair_count);
if strcmp(normalization_mode, 'pair_common_final_full_scale')
    for pair = 1:pair_count
        columns = 2*pair-1:2*pair;
        peak = max(abs(awg_data(:, columns)), [], 'all');
        if ~isfinite(peak) || peak <= 0
            error('msiq:waveform:Normalization', ...
                'Pair %s cannot be normalized because its final peak is invalid.', ...
                pair_names{pair});
        end
        pair_scale_factors(pair) = 1/peak;
        awg_data(:, columns) = awg_data(:, columns)*pair_scale_factors(pair);
        % Remove accumulated floating-point error while preserving I/Q gain.
        final_peak = max(abs(awg_data(:, columns)), [], 'all');
        awg_data(:, columns) = awg_data(:, columns)/final_peak;
        pair_scale_factors(pair) = pair_scale_factors(pair)/final_peak;
        scale_factors(columns) = pair_scale_factors(pair);
    end
end

normalization = struct('mode', normalization_mode, ...
    'target_peak', ternary(strcmp(normalization_mode, ...
    'pair_common_final_full_scale'), 1, cfg.waveform.peak_scale), ...
    'pair_scale_factors', pair_scale_factors, ...
    'dac_scale_factors', scale_factors);

reference_bytes = uint8([]);
for pair = 1:pair_count
    for stream = 1:stream_count
        reference_bytes = [reference_bytes; uint8( ...
            pair_refs(pair).metrics_only(stream).fec.transmitted_bits(:))]; %#ok<AGROW>
    end
end

waveforms = struct();
waveforms.master_dac_data = master_data;
waveforms.awg_dac_data = awg_data;
waveforms.master_sample_rate_hz = cfg.waveform.master_sample_rate_hz;
waveforms.awg_sample_rate_hz = cfg.waveform.awg_sample_rate_hz;
waveforms.dac_labels = {'I_A', 'Q_A', 'I_B', 'Q_B'};
waveforms.dac_scale_factors = scale_factors;
waveforms.normalization = normalization;
waveforms.architecture = architecture;
waveforms.seed = double(seed);
overflow = ~isfinite(awg_data) | abs(awg_data) > 1+1e-12;
waveforms.sample_range_overflow_fraction = mean(overflow, 1);
% Retain the old field name for programmatic consumers; full scale is legal.
waveforms.clipping_fraction = waveforms.sample_range_overflow_fraction;
waveforms.max_abs_sample = max(abs(awg_data), [], 1);
waveforms.iq_calibration = iq_calibration;
waveforms.tx_sro_precomp = tx_sro_precomp;
waveforms.plot_data = struct( ...
    'display_only', true, ...
    'payload_symbols', plot_frames{1}.payload_symbols, ...
    'training_symbols', plot_frames{1}.training_symbols, ...
    'pilot_symbols', plot_frames{1}.pilot_symbols, ...
    'service_symbols', plot_frames{1}.service_symbols, ...
    'sync_symbols', sync_symbols, ...
    'pulse_shaped_complex', shaped_complex{1}, ...
    'passband_complex', passband_complex{1});

tx_ref = struct();
tx_ref.schema_version = '2.0';
tx_ref.waveform_id = sprintf('SC%s_UP%s_seed%d', ...
    modulation_label(cfg.waveform.modulation_order), ...
    rate_token(cfg.waveform.selected_up), seed);
configuration = reference_configuration(cfg.waveform, iq_calibration, normalization);
if tx_sro_precomp.enabled
    configuration.tx_sro_precomp = tx_sro_precomp;
end
fec_config = msiq.fec.specification(cfg);
if strcmp(fec_config.frame_type, 'short')
    configuration.fec = fec_config;
end
tx_ref.config_hash_sha256 = msiq.sha256_bytes(jsonencode(configuration));
tx_ref.reference_hash_sha256 = msiq.sha256_bytes( ...
    uint32(seed), tx_ref.config_hash_sha256, reference_bytes);
tx_ref.seed = double(seed);
tx_ref.architecture = architecture;
tx_ref.modulation_order = cfg.waveform.modulation_order;
tx_ref.waveform_config = configuration;
tx_ref.fec_config = fec_config;
tx_ref.iq_calibration = iq_calibration;
tx_ref.tx_sro_precomp = tx_sro_precomp;
tx_ref.waveform_normalization = normalization;
tx_ref.pairs = pair_refs;
tx_ref.frame = pair_refs(1).receiver_known(1).frame;
tx_ref.frame.sync_symbols = sync_symbols;
tx_ref.frame.rrc = rrc;
tx_ref.frame.master_samples_per_symbol = cfg.waveform.master_samples_per_symbol;
tx_ref.frame.shaping_samples_per_symbol = sps;
tx_ref.frame.master_sample_rate_hz = cfg.waveform.master_sample_rate_hz;
tx_ref.frame.awg_sample_rate_hz = cfg.waveform.awg_sample_rate_hz;
tx_ref.frame.frame_repetitions = cfg.waveform.frame_repetitions;
tx_ref.frame.master_waveform_length = master_length;
tx_ref.frame.awg_waveform_length = awg_length;
alignment = 128;
if isfield(cfg.waveform,'awg_alignment_samples')
    alignment = cfg.waveform.awg_alignment_samples;
end
validateattributes(alignment,{'numeric'},{'scalar','integer','positive','finite'});
tx_ref.frame.awg_padded_waveform_length = ceil(awg_length/alignment)*alignment;
tx_ref.frame.reference_payload_policy = 'metrics_only';
tx_ref.frame.modulation_order = cfg.waveform.modulation_order;
tx_ref.frame.symbol_rate_hz = cfg.waveform.symbol_rate_hz;
tx_ref.frame.occupied_bandwidth_hz = ...
    cfg.waveform.symbol_rate_hz*(1+cfg.waveform.rolloff);
tx_ref.frame.rrc_rolloff = cfg.waveform.rolloff;
tx_ref.frame.rrc_span_symbols = cfg.waveform.rrc_span_symbols;
tx_ref.frame.pilot_interval_symbols = cfg.waveform.pilot_interval_symbols;
tx_ref.frame.ldpc_blocks_per_frame = cfg.waveform.ldpc_blocks_per_frame;
if tx_sro_precomp.applied
    % Express the fractional guard in nominal-symbol time, so the existing
    % boundary scaling uses residual SRO rather than the calibrated clock error.
    tx_ref.frame.sro_boundary_extra_awg_samples = ...
        tx_ref.frame.awg_padded_waveform_length/tx_sro_precomp.time_scale - ...
        tx_ref.frame.symbol_count*cfg.waveform.frame_repetitions * ...
        cfg.waveform.awg_sample_rate_hz/cfg.waveform.symbol_rate_hz;
end
end

function [data, info] = add_tx_sro_loop_guard(data, info)
info.signal_awg_samples = size(data,1);
info.loop_guard_samples = 0;
if info.applied
    % One download block makes the loop guard observable without changing
    % the logical frames or the receiver's existing boundary-selection rules.
    target = ceil(size(data,1)/128)*128 + 128;
    info.loop_guard_samples = target-size(data,1);
    data(end+1:target,:) = 0;
end
end

function [data, calibration] = apply_iq_calibration(data, cfg, architecture)
calibration = struct('q_relative_delay_samples', 0, ...
    'invert_i', false, 'invert_q', false, ...
    'delay_units', 'awg_digital_samples');
if ~strcmp(architecture, 'single_complex_stream')
    return;
end
waveform = cfg.waveform;
if isfield(waveform, 'q_relative_delay_samples')
    calibration.q_relative_delay_samples = ...
        round(double(waveform.q_relative_delay_samples));
end
if isfield(waveform, 'invert_i')
    calibration.invert_i = logical(waveform.invert_i);
end
if isfield(waveform, 'invert_q')
    calibration.invert_q = logical(waveform.invert_q);
end
for first = [1 3]
    if calibration.invert_i
        data(:, first) = -data(:, first);
    end
    if calibration.invert_q
        data(:, first+1) = -data(:, first+1);
    end
    data(:, first+1) = shift_with_zeros(data(:, first+1), ...
        calibration.q_relative_delay_samples);
end
end

function value = shift_with_zeros(value, delay)
delay = round(double(delay));
if delay > 0
    value = [zeros(delay, 1); value(1:end-delay)];
elseif delay < 0
    advance = -delay;
    value = [value(advance+1:end); zeros(advance, 1)];
end
end

function value = reference_configuration(waveform, iq_calibration, normalization)
names = {'architecture','modulation_order','master_sample_rate_hz', ...
    'awg_sample_rate_hz','selected_up','master_samples_per_symbol', ...
    'awg_samples_per_symbol','symbol_rate_hz','occupied_bandwidth_hz', ...
    'shaping_samples_per_symbol','rate_generation_mode', ...
    'rolloff','rrc_span_symbols','periodic_rrc', ...
    'if_center_hz','sync_length_symbols','sync_repeats','training_symbols', ...
    'pilot_interval_symbols','guard_symbols','ldpc_blocks_per_frame', ...
    'frame_repetitions','peak_scale','normalization_mode'};
value = struct();
for k = 1:numel(names)
    name = names{k};
    if ~isfield(waveform, name)
        if strcmp(name, 'periodic_rrc')
            value.(name) = false;
        elseif strcmp(name, 'occupied_bandwidth_hz')
            value.(name) = waveform.symbol_rate_hz*(1+waveform.rolloff);
        elseif strcmp(name, 'shaping_samples_per_symbol')
            value.(name) = shaping_samples_per_symbol(waveform);
        elseif strcmp(name, 'rate_generation_mode')
            value.(name) = 'legacy_integer_up';
        elseif strcmp(name, 'normalization_mode')
            value.(name) = 'legacy_peak_scale';
        end
    else
        value.(name) = waveform.(name);
    end
end
value.iq_calibration = iq_calibration;
if isfield(waveform,'awg_alignment_samples') && waveform.awg_alignment_samples ~= 128
    value.awg_alignment_samples = waveform.awg_alignment_samples;
end
value.normalization = normalization;
end

function mode = waveform_normalization_mode(waveform)
mode = lower(char(string(field_or(waveform, ...
    'normalization_mode', 'legacy_peak_scale'))));
if ~ismember(mode, {'legacy_peak_scale','pair_common_final_full_scale'})
    error('msiq:waveform:NormalizationMode', ...
        'Unsupported waveform normalization mode: %s.', mode);
end
end

function value = modulation_label(order)
if order == 4
    value = 'QPSK';
else
    value = sprintf('%dQAM', order);
end
end

function [repeated_frame, known, metrics, visual] = build_stream_frame( ...
        cfg, seed, sync_symbols, guard)
[payload_bits, fec_reference] = msiq.fec.encode_payload( ...
    cfg, seed, cfg.waveform.ldpc_blocks_per_frame);
payload_symbols = qammod(payload_bits, cfg.waveform.modulation_order, ...
    'InputType', 'bit', 'UnitAveragePower', true);

stream = RandStream('mt19937ar', 'Seed', double(seed) + 7919);
training_index = randi(stream, [0 3], cfg.waveform.training_symbols, 1);
training_symbols = pskmod(training_index, 4, pi/4, 'gray');
pilot_count = ceil(numel(payload_symbols) / ...
    cfg.waveform.pilot_interval_symbols);
pilot_index = randi(stream, [0 3], pilot_count, 1);
pilot_symbols = pskmod(pilot_index, 4, pi/4, 'gray');
[service_symbols, pilot_positions, payload_positions] = ...
    insert_pilots(payload_symbols, pilot_symbols, ...
    cfg.waveform.pilot_interval_symbols);

sync_block = repmat(sync_symbols(:), cfg.waveform.sync_repeats, 1);
frame_symbols = [guard(:); sync_block; training_symbols; service_symbols; guard(:)];
repeated_frame = repmat(frame_symbols, cfg.waveform.frame_repetitions, 1);

sync_start = numel(guard) + 1;
training_start = sync_start + numel(sync_block);
service_start = training_start + numel(training_symbols);
frame = struct();
frame.symbol_count = numel(frame_symbols);
frame.guard_symbols = numel(guard);
frame.sync_start = sync_start;
frame.sync_length = numel(sync_symbols);
frame.sync_repeats = cfg.waveform.sync_repeats;
frame.training_start = training_start;
frame.training_length = numel(training_symbols);
frame.service_start = service_start;
frame.service_length = numel(service_symbols);
frame.pilot_positions_service = pilot_positions;
frame.payload_positions_service = payload_positions;
frame.pilot_positions_frame = service_start - 1 + pilot_positions;
frame.payload_positions_frame = service_start - 1 + payload_positions;

known = struct();
known.training_symbols = training_symbols;
known.pilot_symbols = pilot_symbols;
known.frame = frame;

metrics = struct();
metrics.fec = fec_reference;
metrics.payload_symbol_count = numel(payload_symbols);
metrics.payload_bit_count = numel(payload_bits);
metrics.seed = double(seed);
visual = struct('display_only', true, ...
    'payload_symbols', payload_symbols, ...
    'training_symbols', training_symbols, ...
    'pilot_symbols', pilot_symbols, ...
    'service_symbols', service_symbols, ...
    'frame_symbols', frame_symbols);
end

function [service, pilot_positions, payload_positions] = ...
        insert_pilots(payload, pilots, interval)
payload = payload(:);
pilots = pilots(:);
chunks = ceil(numel(payload) / interval);
service = zeros(numel(payload) + chunks, 1);
pilot_positions = zeros(chunks, 1);
payload_positions = zeros(numel(payload), 1);
source = 1;
target = 1;
payload_target = 1;
for chunk = 1:chunks
    pilot_positions(chunk) = target;
    service(target) = pilots(chunk);
    target = target + 1;
    count = min(interval, numel(payload)-source+1);
    index = target:(target+count-1);
    service(index) = payload(source:(source+count-1));
    payload_positions(payload_target:(payload_target+count-1)) = index;
    source = source + count;
    payload_target = payload_target + count;
    target = target + count;
end
end

function shaped = pulse_shape(symbols, rrc, sps, cfg)
periodic = isfield(cfg.waveform, 'periodic_rrc') && ...
    logical(cfg.waveform.periodic_rrc);
if ~periodic
    shaped = upfirdn(symbols(:), rrc, sps, 1);
    return;
end

symbols = symbols(:);
sample_count = numel(symbols)*sps;
three_periods = repmat(symbols, 3, 1);
filtered = filter(rrc(:), 1, upsample(three_periods, sps));
group_delay = (numel(rrc)-1)/2;
if abs(group_delay-round(group_delay)) > eps
    error('msiq:waveform:RrcDelay', ...
        'Periodic RRC shaping requires an integer group delay.');
end
first = sample_count + round(group_delay) + 1;
last = first + sample_count - 1;
shaped = filtered(first:last);
end

function shaped = pulse_shape_at_master_rate(symbols, rrc, shaping_sps, cfg)
shaped = pulse_shape(symbols, rrc, shaping_sps, cfg);
source_rate = cfg.waveform.symbol_rate_hz*shaping_sps;
target_rate = cfg.waveform.master_sample_rate_hz;
if abs(source_rate-target_rate) <= max(1, target_rate*1e-12)
    return;
end
[p, q] = rat(target_rate/source_rate, 1e-10);
if p > 10000 || q > 10000
    error('msiq:waveform:RateRatio', ...
        'Master-rate resampling ratio is too large: %d/%d.', p, q);
end
shaped = resample(shaped, p, q);
end

function sps = shaping_samples_per_symbol(waveform)
sps = field_or(waveform, 'shaping_samples_per_symbol', ...
    field_or(waveform, 'master_samples_per_symbol', 31));
if ~isscalar(sps) || ~isfinite(sps) || sps < 2 || ...
        abs(sps-round(sps)) > 1e-9
    sps = 32;
end
sps = round(sps);
end

function value = rate_token(up)
value = sprintf('%.9g', double(up));
value = strrep(value, '.', 'p');
value = strrep(value, '-', 'm');
value = strrep(value, '+', '');
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

function sequence = zc_sequence(length_value, root)
n = (0:length_value-1).';
if mod(length_value, 2) == 0
    sequence = exp(-1j*pi*root*n.^2/length_value);
else
    sequence = exp(-1j*pi*root*n.*(n+1)/length_value);
end
end
