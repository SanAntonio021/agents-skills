function matrix = build_experiment_matrix(cfg)
%BUILD_EXPERIMENT_MATRIX Build balanced formal and staged acceptance plans.

if nargin < 1 || isempty(cfg)
    cfg = msiq.build_config('v2_default');
elseif ~isstruct(cfg)
    cfg = msiq.build_config(cfg);
end

conditions = repmat(empty_condition(), 0, 1);
sequence = 0;
channels = cellstr(string(cfg.channels.logical_labels));

% Indoor architecture comparison: six channels, two architectures.
architectures = {'single_complex_stream', 'dual_iq_mimo'};
for channel_index = 1:numel(channels)
    for architecture_index = 1:numel(architectures)
        sequence = sequence + 1;
        id = sprintf('INDOOR_%s_%s', channels{channel_index}, ...
            upper(architecture_tag(architectures{architecture_index})));
        conditions(end+1) = make_condition(cfg, id, 'indoor_formal', ...
            {channels{channel_index}}, architectures{architecture_index}, ...
            'single_merged', cfg.experiment.formal_repeats, sequence); %#ok<AGROW>
    end
end

% 1 km single-channel conditions merge the two power definitions at N=1.
for channel_index = 1:numel(channels)
    sequence = sequence + 1;
    id = sprintf('1KM_%s_N1', channels{channel_index});
    conditions(end+1) = make_condition(cfg, id, 'one_km_formal', ...
        {channels{channel_index}}, 'dual_iq_mimo', 'single_merged', ...
        cfg.experiment.formal_repeats, sequence); %#ok<AGROW>
end

balanced = {
    {'CH1','CH2'}, {'CH3','CH4'}, {'CH5','CH6'};
    {'CH1','CH3','CH5'}, {'CH2','CH4','CH6'}, {};
    {'CH1','CH2','CH3','CH4'}, {'CH1','CH2','CH5','CH6'}, ...
        {'CH3','CH4','CH5','CH6'}};
for row = 1:size(balanced, 1)
    for column = 1:size(balanced, 2)
        active = balanced{row, column};
        if isempty(active)
            continue;
        end
        for power_index = 1:numel(cfg.experiment.power_modes)
            power_mode = char(string(cfg.experiment.power_modes{power_index}));
            sequence = sequence + 1;
            id = sprintf('1KM_%s_%s', strjoin(active, ''), ...
                upper(power_tag(power_mode)));
            conditions(end+1) = make_condition(cfg, id, ...
                'one_km_formal', active, 'dual_iq_mimo', power_mode, ...
                cfg.experiment.formal_repeats, sequence); %#ok<AGROW>
        end
    end
end

qualification = repmat(empty_condition(), 0, 1);
qualification_sequence = 0;
for up_index = 1:numel(cfg.experiment.qualification_up_order)
    up_value = cfg.experiment.qualification_up_order(up_index);
    for channel_index = 1:numel(channels)
        qualification_sequence = qualification_sequence + 1;
        id = sprintf('QUAL_%s_UP%d', channels{channel_index}, up_value);
        item = make_condition(cfg, id, 'six_channel_qualification', ...
            {channels{channel_index}}, 'dual_iq_mimo', 'single_merged', ...
            cfg.experiment.support_repeats, qualification_sequence);
        item.up = up_value;
        item.symbol_rate_hz = cfg.waveform.master_sample_rate_hz / up_value;
        qualification(end+1) = item; %#ok<AGROW>
    end
end

support = repmat(empty_condition(), 0, 1);
support(1) = make_condition(cfg, 'IF_LOOP_CH1', 'if_loop', {'CH1'}, ...
    'dual_iq_mimo', 'single_merged', cfg.experiment.support_repeats, 1);
support(2) = make_condition(cfg, 'SHORT_RANGE_CH1_CH2', 'short_range', ...
    {'CH1','CH2'}, 'dual_iq_mimo', 'fixed_per_subband', ...
    cfg.experiment.support_repeats, 2);

matrix = struct();
matrix.schema_version = '2.0';
matrix.conditions = conditions;
matrix.qualification = qualification;
matrix.support = support;
matrix.stage_order = {'idn_preflight', 'awg_off', 'single_dac_smoke', ...
    'if_loop', 'six_channel_qualification', 'short_range', 'one_km_formal'};
matrix.acceptance = struct( ...
    'minimum_passing_repeats', cfg.experiment.minimum_passing_repeats, ...
    'required_repeats', cfg.experiment.formal_repeats, ...
    'all_active_channels_required', true, ...
    'all_streams_required', true, ...
    'minimum_complete_blocks_per_stream', 1, ...
    'post_fec_ber_required', 0, ...
    'bler_required', 0, ...
    'parity_convergence_required', true, ...
    'clipping_allowed', false);
matrix.counts = struct( ...
    'indoor_formal', nnz(strcmp({conditions.phase}, 'indoor_formal')), ...
    'one_km_single', nnz(strcmp({conditions.phase}, 'one_km_formal') & ...
        [conditions.num_active] == 1), ...
    'one_km_multichannel', nnz(strcmp({conditions.phase}, 'one_km_formal') & ...
        [conditions.num_active] > 1), ...
    'qualification', numel(qualification), ...
    'formal_total', numel(conditions));
end

function condition = make_condition(cfg, id, phase, active, architecture, ...
        power_mode, repetitions, sequence)
condition = empty_condition();
condition.condition_id = id;
condition.phase = phase;
condition.active_physical_subbands = active;
condition.num_active = numel(active);
condition.architecture = architecture;
condition.power_mode = power_mode;
condition.power_unit_dbm = cfg.experiment.power_unit_dbm;
condition.up = cfg.waveform.selected_up;
condition.symbol_rate_hz = cfg.waveform.master_sample_rate_hz / condition.up;
condition.waveform_seed_count = numel(cfg.experiment.seed_values);
condition.repetitions = repetitions;
condition.repeat_plan = build_repeat_plan(cfg, repetitions);
condition.awg_slot_map = balanced_slot_map(active, sequence);
condition.receive_batches = receive_batches(active, ...
    cfg.channels.scope_iq_pairs_per_capture);
condition.scope_settings = cfg.scope;

payload_pairs = unique({condition.awg_slot_map.payload_pair}, 'stable');
condition.unique_payload_pairs = payload_pairs;
condition.unique_payload_pair_count = numel(payload_pairs);
[gross_pair, net_pair] = pair_rates(cfg, condition.symbol_rate_hz);
condition.physical_loading_rate_bps = condition.num_active * gross_pair;
condition.unique_information_rate_bps = ...
    condition.unique_payload_pair_count * net_pair;
condition.duplicate_payload_loading = ...
    condition.num_active > condition.unique_payload_pair_count;
condition.off_on_pair_required = cfg.experiment.require_off_on_pair;
end

function plan = build_repeat_plan(cfg, repetitions)
plan = repmat(struct('repeat', 0, 'seed', 0, 'seed_index', 0, ...
    'capture_index', 0, 'requires_awg_off', true, ...
    'requires_awg_on', true), 1, repetitions);
for repeat = 1:repetitions
    seed_index = ceil(repeat / cfg.experiment.captures_per_seed);
    seed_index = mod(seed_index-1, numel(cfg.experiment.seed_values)) + 1;
    capture_index = mod(repeat-1, cfg.experiment.captures_per_seed) + 1;
    plan(repeat).repeat = repeat;
    plan(repeat).seed = cfg.experiment.seed_values(seed_index);
    plan(repeat).seed_index = seed_index;
    plan(repeat).capture_index = capture_index;
end
end

function mapping = balanced_slot_map(active, sequence)
templates = slot_templates(numel(active));
slots = templates{mod(sequence-1, numel(templates)) + 1};
mapping = repmat(struct('physical_subband', '', 'slot', '', ...
    'payload_pair', '', 'polarity', 1, 'is_complement', false, ...
    'source_slot', ''), 1, numel(active));
for k = 1:numel(active)
    [pair, polarity, source, is_complement] = slot_details(slots{k});
    mapping(k).physical_subband = active{k};
    mapping(k).slot = slots{k};
    mapping(k).payload_pair = pair;
    mapping(k).polarity = polarity;
    mapping(k).is_complement = is_complement;
    mapping(k).source_slot = source;
end
end

function templates = slot_templates(count)
switch count
    case 1
        templates = {{'A+'}, {'B+'}, {'A-'}, {'B-'}};
    case 2
        templates = {{'A+','B+'}, {'A-','B+'}, ...
            {'A+','B-'}, {'A-','B-'}};
    case 3
        templates = {{'A+','B+','A-'}, {'A+','B+','B-'}, ...
            {'A+','A-','B-'}, {'A-','B+','B-'}};
    case 4
        templates = {{'A+','B+','A-','B-'}, ...
            {'B+','A-','B-','A+'}};
    otherwise
        error('msiq:matrix:ActiveCount', ...
            'Only one to four simultaneous physical subbands are supported.');
end
end

function [pair, polarity, source, is_complement] = slot_details(slot)
pair = slot(1);
is_complement = slot(2) == '-';
if is_complement
    polarity = -1;
else
    polarity = 1;
end
source = [pair, '+'];
end

function batches = receive_batches(active, batch_size)
count = ceil(numel(active) / batch_size);
batches = repmat(struct('batch', 0, 'physical_subbands', {{}}, ...
    'keep_all_transmit_subbands_on', true), 1, count);
for batch = 1:count
    first = (batch-1)*batch_size + 1;
    last = min(batch*batch_size, numel(active));
    batches(batch).batch = batch;
    batches(batch).physical_subbands = active(first:last);
end
end

function [gross_pair, net_pair] = pair_rates(cfg, symbol_rate)
bits_per_symbol = log2(cfg.waveform.modulation_order);
gross_pair = 2 * symbol_rate * bits_per_symbol;
fec = msiq.fec.build(cfg);
payload_symbols = cfg.waveform.ldpc_blocks_per_frame * ...
    fec.codeword_length / bits_per_symbol;
pilots = ceil(payload_symbols / cfg.waveform.pilot_interval_symbols);
frame_symbols = 2*cfg.waveform.guard_symbols + ...
    cfg.waveform.sync_repeats*cfg.waveform.sync_length_symbols + ...
    cfg.waveform.training_symbols + payload_symbols + pilots;
overhead_efficiency = payload_symbols / frame_symbols;
net_pair = gross_pair * cfg.fec.rate * overhead_efficiency;
end

function tag = architecture_tag(value)
if strcmp(value, 'single_complex_stream')
    tag = 'SCALAR';
else
    tag = 'DUAL';
end
end

function tag = power_tag(value)
if strcmp(value, 'fixed_per_subband')
    tag = 'PERSUB';
else
    tag = 'TOTAL';
end
end

function condition = empty_condition()
condition = struct( ...
    'condition_id', '', 'phase', '', ...
    'active_physical_subbands', {{}}, 'num_active', 0, ...
    'architecture', '', 'power_mode', '', 'power_unit_dbm', NaN, ...
    'up', NaN, 'symbol_rate_hz', NaN, ...
    'waveform_seed_count', 0, 'repetitions', 0, ...
    'repeat_plan', struct([]), 'awg_slot_map', struct([]), ...
    'receive_batches', struct([]), 'scope_settings', struct(), ...
    'unique_payload_pairs', {{}}, 'unique_payload_pair_count', 0, ...
    'physical_loading_rate_bps', NaN, ...
    'unique_information_rate_bps', NaN, ...
    'duplicate_payload_loading', false, ...
    'off_on_pair_required', true);
end
