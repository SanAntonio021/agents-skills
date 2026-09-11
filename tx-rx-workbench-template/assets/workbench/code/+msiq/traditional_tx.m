function output = traditional_tx(action, selector, options)
%TRADITIONAL_TX Programmatic TX actions for the traditional complex-I/Q path.

if nargin < 1 || isempty(action)
    action = 'status';
end
if nargin < 2
    selector = [];
end
if nargin < 3 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:traditionalTx:Options', 'Options must be a scalar struct.');
end
action = lower(char(string(action)));

switch action
    case 'awg_status'
        cfg = load_cfg(options);
        output = awg_status(cfg);
    case 'preview_plan'
        cfg = load_cfg(options);
        output = create_preview(cfg, options);
    case 'awg_plan'
        cfg = load_cfg(options);
        output = create_plan(cfg, options);
    case 'awg_apply'
        if ~isfield(options, 'plan') || ~isstruct(options.plan)
            error('msiq:traditionalTx:Plan', ...
                'awg_apply requires options.plan from awg_plan.');
        end
        output = apply_plan(options.plan, options);
    case 'awg_level'
        cfg = load_cfg(options);
        output = set_levels(cfg, options);
    case 'awg_channel_settings'
        cfg = load_cfg(options);
        output = set_channel_settings(cfg, options);
    case 'awg_reuse'
        cfg = load_cfg(options);
        output = reuse_route(cfg, selector, options);
    case 'awg_stop'
        cfg = load_cfg(options);
        output = stop_route(cfg, options);
    otherwise
        error('msiq:traditionalTx:Action', 'Unknown TX action: %s.', action);
end
end

function cfg = load_cfg(options)
if isfield(options, 'cfg_override') && ~isempty(options.cfg_override)
    cfg = options.cfg_override;
else
    cfg = msiq.build_config('v2_traditional_wz');
end
if ~isstruct(cfg) || ~isfield(cfg, 'waveform') || ~isfield(cfg, 'instrument')
    error('msiq:traditionalTx:Config', 'Traditional TX needs a V2 config struct.');
end
cfg.waveform.architecture = 'single_complex_stream';
cfg.results_root = fullfile(cfg.project_root, 'measurement');
cfg = apply_preview_overrides(cfg, options);
cfg = configure_rdiv(cfg, options);
end

function output = awg_status(cfg)
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
state = msiq.instruments.read_awg_public_state(session);
health = inspect_awg_state(state);
output = struct('status', health.status, 'timestamp', timestamp_text(), ...
    'state', state, 'state_fingerprint', state_fingerprint(state), ...
    'health', health);
clear cleanup;
end

function plan = create_preview(cfg, options)
%CREATE_PREVIEW Generate a complete hardware-free draft for the GUI.
% The optional awg_state is read-only data supplied by a prior awg_status call.
route = msiq.resolve_awg_route(options);
levels = route_levels(cfg, route, options);
delays = route_delays(cfg, route, options);
hardware_targets = all_channel_targets(cfg, route, levels, delays, options);
seed = get_seed(cfg, options);
injected_sro_ppm = requested_hardware_sro_ppm(options);
[waveforms, tx_ref, download, desired, waveform_preflight] = ...
    prepare_playback(cfg, seed, route, levels, delays, injected_sro_ppm);
state_available = isfield(options, 'awg_state') && isstruct(options.awg_state) && ...
    isscalar(options.awg_state) && isfield(options.awg_state, 'traces');
if state_available
    state = options.awg_state;
    require_outputs_off(state, desired);
    comparison = compare_state(state, desired, route);
    snapshot_fingerprint = state_fingerprint(state);
else
    state = struct();
    comparison = empty_comparison();
    snapshot_fingerprint = '';
end
capacity = capacity_preflight(desired, download, state);
preflight = merge_capacity_preflight(waveform_preflight, capacity);
waveform_hashes = cell(1, numel(route.awg_channels));
for k = 1:numel(route.awg_channels)
    waveform_hashes{k} = msiq.sha256_bytes(download.channel_data{k});
end
plan = struct();
plan.schema_version = '1.0-preview';
plan.status = 'preview';
plan.created_at = timestamp_text();
plan.route = route;
plan.levels = levels;
plan.sample_clock_delay_samples = delays;
plan.seed = seed;
plan.experiment_note = char(string(field_or(cfg.experiment, 'note', '')));
plan.waveform_id = tx_ref.waveform_id;
plan.config_hash = tx_ref.config_hash_sha256;
plan.waveform_hashes = waveform_hashes;
plan.waveform_normalization = waveforms.normalization;
plan.waveform_signature = waveform_fingerprint( ...
    plan.config_hash, waveform_hashes);
plan.hardware_targets = hardware_targets;
plan.parameter_hash = parameter_fingerprint(route, levels, delays, ...
    plan.config_hash, waveform_hashes, plan.experiment_note, ...
    injected_sro_ppm, hardware_targets);
plan.hardware_sro_injection_ppm = injected_sro_ppm;
plan.nominal_awg_raster_hz = waveforms.master_sample_rate_hz;
plan.waveform_sample_count = size(waveforms.awg_dac_data, 1);
plan.padded_sample_count = desired.padded_sample_count;
plan.final_sample_counts = download.final_sample_counts;
plan.waveform_sample_rate_hz = waveforms.awg_sample_rate_hz;
plan.waveform_duration_s = size(waveforms.awg_dac_data,1) / ...
    waveforms.awg_sample_rate_hz;
plan.awg_raster_hz = desired.raster_hz;
plan.actual_waveform_sample_rate_hz = desired.actual_waveform_sample_rate_hz;
plan.actual_waveform_duration_s = desired.padded_sample_count / ...
    desired.actual_waveform_sample_rate_hz;
plan.preflight = preflight;
plan.memory_capacity = capacity;
plan.awg_snapshot = state;
plan.awg_snapshot_fingerprint = snapshot_fingerprint;
plan.awg_state_available = state_available;
plan.public_parameter_changes = comparison.public_parameter_changes;
plan.public_parameter_differences = comparison.public_parameter_differences;
plan.channel_setting_differences = comparison.channel_setting_differences;
plan.active_channels = active_channels_from_state(state);
plan.affected_other_channels = comparison.affected_other_channels;
plan.impact = comparison.impact;
plan.desired = desired;
plan.download = download;
plan.tx_ref = tx_ref;
plan.waveforms = waveforms;
plan.cfg = cfg;
end

function cfg = apply_preview_overrides(cfg, options)
if ~isstruct(options)
    return;
end
waveform = cfg.waveform;
if isfield(options, 'tx_sro_precomp')
    waveform.tx_sro_precomp = options.tx_sro_precomp;
end
waveform.modulation_order = integer_option(options, 'modulation_order', ...
    waveform.modulation_order, [4 64]);
if ~ismember(waveform.modulation_order, [4 16 64])
    error('msiq:traditionalTx:Modulation', ...
        'Traditional TX supports only QPSK, 16QAM, and 64QAM.');
end
waveform.master_sample_rate_hz = numeric_option(options, ...
    'master_sample_rate_hz', waveform.master_sample_rate_hz, [53.76e9 65e9]);
waveform.rolloff = numeric_option(options, 'rolloff', ...
    waveform.rolloff, [0 1]);
legacy_up = field_or(waveform, 'selected_up', 31);
if isfield(options, 'selected_up') && ~isempty(options.selected_up)
    legacy_up = numeric_option(options, 'selected_up', legacy_up, [2 256]);
elseif isfield(options, 'up') && ~isempty(options.up)
    legacy_up = numeric_option(options, 'up', legacy_up, [2 256]);
end
[symbol_rate_hz, rate_source] = resolve_symbol_rate(options, waveform, ...
    legacy_up, waveform.rolloff);
waveform.symbol_rate_hz = symbol_rate_hz;
waveform.occupied_bandwidth_hz = symbol_rate_hz*(1+waveform.rolloff);
waveform.selected_up = waveform.master_sample_rate_hz/symbol_rate_hz;
waveform.master_samples_per_symbol = waveform.selected_up;
if strcmp(rate_source, 'legacy_up') && ...
        abs(waveform.selected_up-round(waveform.selected_up)) <= 1e-9
    waveform.shaping_samples_per_symbol = round(waveform.selected_up);
    waveform.rate_generation_mode = 'legacy_integer_up';
else
    waveform.shaping_samples_per_symbol = 32;
    waveform.rate_generation_mode = 'fixed_rate_rational_resample';
end
waveform.rrc_span_symbols = integer_option(options, 'rrc_span_symbols', ...
    waveform.rrc_span_symbols, [2 64]);
if mod(waveform.rrc_span_symbols * ...
        waveform.shaping_samples_per_symbol, 2) ~= 0
    error('msiq:traditionalTx:RrcOrder', ...
        'RRC span times the shaping rate must be even.');
end
waveform.peak_scale = numeric_option(options, 'peak_scale', ...
    waveform.peak_scale, [0.05 1]);
waveform.normalization_mode = text_option(options, 'normalization_mode', ...
    field_or(waveform, 'normalization_mode', 'legacy_peak_scale'), ...
    {'legacy_peak_scale','pair_common_final_full_scale'});
waveform.sync_length_symbols = integer_option(options, ...
    'sync_length_symbols', waveform.sync_length_symbols, [7 4096]);
waveform.sync_repeats = integer_option(options, 'sync_repeats', ...
    waveform.sync_repeats, [1 16]);
waveform.training_symbols = integer_option(options, 'training_symbols', ...
    waveform.training_symbols, [128 16384]);
waveform.pilot_interval_symbols = integer_option(options, ...
    'pilot_interval_symbols', waveform.pilot_interval_symbols, [1 4096]);
waveform.guard_symbols = integer_option(options, 'guard_symbols', ...
    waveform.guard_symbols, [0 4096]);
waveform.ldpc_blocks_per_frame = integer_option(options, ...
    'ldpc_blocks_per_frame', waveform.ldpc_blocks_per_frame, [1 8]);
waveform.frame_repetitions = integer_option(options, ...
    'frame_repetitions', waveform.frame_repetitions, [1 16]);
waveform.q_relative_delay_samples = integer_option(options, ...
    'q_relative_delay_samples', field_or(waveform, ...
    'q_relative_delay_samples', 0), [-16 16]);
waveform.invert_i = logical_option(options, 'invert_i', ...
    field_or(waveform, 'invert_i', false));
waveform.invert_q = logical_option(options, 'invert_q', ...
    field_or(waveform, 'invert_q', false));
waveform.bits_per_symbol = log2(waveform.modulation_order);
cfg.waveform = waveform;
if isfield(options, 'experiment_note')
    cfg.experiment.note = char(string(options.experiment_note));
elseif ~isfield(cfg.experiment, 'note')
    cfg.experiment.note = '';
end
end

function [symbol_rate_hz, source] = resolve_symbol_rate( ...
        options, waveform, legacy_up, rolloff)
authority = '';
if isfield(options, 'rate_authority') && ~isempty(options.rate_authority)
    authority = lower(char(string(options.rate_authority)));
end
has_symbol = isfield(options, 'symbol_rate_hz') && ...
    ~isempty(options.symbol_rate_hz);
has_bandwidth = isfield(options, 'occupied_bandwidth_hz') && ...
    ~isempty(options.occupied_bandwidth_hz);
if strcmp(authority, 'bandwidth') || (~has_symbol && has_bandwidth)
    bandwidth = numeric_option(options, 'occupied_bandwidth_hz', NaN, ...
        [1e6 waveform.master_sample_rate_hz]);
    symbol_rate_hz = bandwidth/(1+rolloff);
    source = 'occupied_bandwidth';
elseif strcmp(authority, 'symbol_rate') || has_symbol
    symbol_rate_hz = numeric_option(options, 'symbol_rate_hz', NaN, ...
        [1e6 waveform.master_sample_rate_hz]);
    source = 'symbol_rate';
else
    symbol_rate_hz = waveform.master_sample_rate_hz/legacy_up;
    source = 'legacy_up';
end
occupied = symbol_rate_hz*(1+rolloff);
if occupied >= waveform.master_sample_rate_hz || ...
        abs(waveform.if_center_hz)+occupied/2 >= waveform.master_sample_rate_hz/2
    error('msiq:traditionalTx:OccupiedBandwidth', ...
        'Occupied bandwidth does not fit inside the master-rate Nyquist band.');
end
end

function plan = create_plan(cfg, options)
route = msiq.resolve_awg_route(options);
levels = route_levels(cfg, route, options);
delays = route_delays(cfg, route, options);
hardware_targets = all_channel_targets(cfg, route, levels, delays, options);
seed = get_seed(cfg, options);
injected_sro_ppm = requested_hardware_sro_ppm(options);
[waveforms, tx_ref, download, desired, waveform_preflight] = ...
    prepare_playback(cfg, seed, route, levels, delays, injected_sro_ppm);
state = awg_status(cfg);
if ~strcmpi(state.status, 'ok')
    error('msiq:traditionalTx:AwgReadback', ...
        'AWG status readback is incomplete: %s.', state.health.message);
end
require_outputs_off(state.state, desired);
capacity = capacity_preflight(desired, download, state.state);
preflight = merge_capacity_preflight(waveform_preflight, capacity);
if ~capacity.ok
    throw_capacity_error(capacity);
end
comparison = compare_state(state.state, desired, route);
run_dir = create_run_dir(cfg, route.name, options);
waveform_hashes = cell(1, numel(route.awg_channels));
for k = 1:numel(route.awg_channels)
    waveform_hashes{k} = msiq.sha256_bytes(download.channel_data{k});
end
plan = struct();
plan.schema_version = '1.0';
plan.status = 'planned';
plan.run_id = string(last_path_part(run_dir));
if isfield(options,'storage_run_root')
    plan.storage_run_root = options.storage_run_root;
end
plan.run_dir = run_dir;
plan.artifact_prefix = char(string(field_or(options, 'artifact_prefix', '')));
plan.diagnostics_dir = fullfile(run_dir, 'data');
plan.created_at = timestamp_text();
plan.route = route;
plan.levels = levels;
plan.sample_clock_delay_samples = delays;
plan.seed = seed;
plan.experiment_note = char(string(field_or(cfg.experiment, 'note', '')));
plan.waveform_id = tx_ref.waveform_id;
plan.config_hash = tx_ref.config_hash_sha256;
plan.waveform_hashes = waveform_hashes;
plan.waveform_normalization = waveforms.normalization;
plan.waveform_signature = waveform_fingerprint( ...
    plan.config_hash, waveform_hashes);
plan.hardware_targets = hardware_targets;
plan.parameter_hash = parameter_fingerprint(route, levels, delays, ...
    plan.config_hash, waveform_hashes, plan.experiment_note, ...
    injected_sro_ppm, hardware_targets);
plan.hardware_sro_injection_ppm = injected_sro_ppm;
plan.nominal_awg_raster_hz = waveforms.master_sample_rate_hz;
plan.waveform_sample_count = size(waveforms.awg_dac_data, 1);
plan.padded_sample_count = desired.padded_sample_count;
plan.final_sample_counts = download.final_sample_counts;
plan.waveform_sample_rate_hz = waveforms.awg_sample_rate_hz;
plan.waveform_duration_s = size(waveforms.awg_dac_data,1) / ...
    waveforms.awg_sample_rate_hz;
plan.awg_raster_hz = desired.raster_hz;
plan.actual_waveform_sample_rate_hz = desired.actual_waveform_sample_rate_hz;
plan.actual_waveform_duration_s = desired.padded_sample_count / ...
    desired.actual_waveform_sample_rate_hz;
plan.preflight = preflight;
plan.memory_capacity = capacity;
plan.awg_snapshot = state.state;
plan.awg_snapshot_fingerprint = state.state_fingerprint;
plan.public_parameter_changes = comparison.public_parameter_changes;
plan.public_parameter_differences = comparison.public_parameter_differences;
plan.channel_setting_differences = comparison.channel_setting_differences;
plan.active_channels = find(state.state.outputs);
plan.affected_other_channels = comparison.affected_other_channels;
plan.global_abort_required = true;
plan.global_abort_command = ':ABOR';
plan.impact = comparison.impact;
plan.confirmation_nonce = plan_nonce();
plan.required_confirmation = confirmation_phrase(comparison, route, waveform_hashes, ...
    state.state_fingerprint, plan.confirmation_nonce);
plan.plan_hash = msiq.sha256_bytes( ...
    state.state_fingerprint, plan.parameter_hash, plan.confirmation_nonce);
plan.desired = desired;
plan.download = download;
plan.tx_ref = tx_ref;
plan.waveforms = waveforms;
plan.cfg = cfg;
plan.tx_dashboard_path = msiq.artifact_path(plan, 'fig_tx_dashboard.png', 'write');
plan.reference_bundle_path = msiq.artifact_path(plan, ...
    'tx_reference_bundle.mat', 'write');
persist_plan(plan);
end

function output = apply_plan(plan, options)
required = {'run_dir','route','levels','desired','download','waveforms','tx_ref','cfg', ...
    'awg_snapshot_fingerprint','required_confirmation','plan_hash'};
for k = 1:numel(required)
    if ~isfield(plan, required{k})
        error('msiq:traditionalTx:PlanFormat', ...
            'Plan is missing %s.', required{k});
    end
end
if ~isfield(plan, 'diagnostics_dir') || isempty(plan.diagnostics_dir)
    plan.diagnostics_dir = fullfile(plan.run_dir, 'data');
end
if ~isfield(plan, 'tx_dashboard_path') || isempty(plan.tx_dashboard_path)
    plan.tx_dashboard_path = msiq.artifact_path(plan, 'fig_tx_dashboard.png', 'write');
end
if ~isfield(plan, 'reference_bundle_path') || isempty(plan.reference_bundle_path)
    plan.reference_bundle_path = msiq.artifact_path(plan, ...
        'tx_reference_bundle.mat', 'write');
end
if ~isfield(options, 'confirmation_phrase') || ~strcmp( ...
        char(string(options.confirmation_phrase)), ...
        char(string(plan.required_confirmation)))
    error('msiq:traditionalTx:Confirmation', ...
        'Set confirmation_phrase to plan.required_confirmation.');
end
strict_switch = field_or(plan.desired, 'explicit_memory_mode', false);
enable_output = logical_option(options, 'enable_output', ~strict_switch);
capacity = capacity_preflight(plan.desired, plan.download, struct());
if strcmpi(plan.desired.memory_mode, 'INT') && ~capacity.ok
    throw_capacity_error(capacity);
end
cfg = plan.cfg;
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
current = msiq.instruments.read_awg_public_state(session);
require_outputs_off(current, plan.desired);
if ~strcmp(state_fingerprint(current), char(string(plan.awg_snapshot_fingerprint)))
    error('msiq:traditionalTx:PlanDrift', ...
        'AWG state changed after awg_plan; create a new plan.');
end

capacity = capacity_preflight(plan.desired, plan.download, current);
if ~capacity.ok
    throw_capacity_error(capacity);
end

route = plan.route;
comparison = compare_state(current, plan.desired, route);
selected = double(route.awg_channels(:).');
other_active = comparison.affected_other_channels;
output_enabled = false;
try
    % New waveform transfer is the one deliberately global operation.
    check_apply_cancel(options);
    msiq.instruments.write_scpi(session, ':ABOR');
    msiq.instruments.set_awg_channels_output(session, selected, false);
    other_disabled = [];
    if comparison.public_parameter_changes && ~isempty(other_active)
        % Shared settings are about to change, so leave the other route off.
        msiq.instruments.set_awg_channels_output(session, other_active, false);
        other_disabled = other_active;
    end
    apply_common_state(session, current, plan.desired);
    check_apply_cancel(options);
    download_selected_waveforms(session, plan.download, route, plan.levels, plan.desired);
    check_apply_cancel(options);

    after_download = msiq.instruments.read_awg_public_state(session);
    verify_route_downloaded(after_download, plan.desired, route);
    other_verified = other_state_matches(current, after_download, selected);
    if ~comparison.public_parameter_changes && ~other_verified && ~isempty(other_active)
        % Unexpected drift means their prior output state cannot be restored safely.
        msiq.instruments.set_awg_channels_output(session, other_active, false);
        other_disabled = other_active;
    end

    % A fresh direct download may start the common AWG engine only here.
    msiq.instruments.write_scpi(session, ':FUNCtion:MODE ARBitrary');
    msiq.instruments.write_scpi(session, ':INIT:IMM');
    wait_for_awg_ready(session);
    if enable_output
        check_apply_cancel(options);
        final_outputs = msiq.instruments.set_awg_channels_output( ...
            session, selected, true);
        output_enabled = true;
        final_state = msiq.instruments.read_awg_public_state(session);
        verify_route_loaded(final_state, plan.desired, route);
        receipt_status = 'applied';
    else
        final_state = msiq.instruments.read_awg_public_state(session);
        verify_route_downloaded(final_state, plan.desired, route);
        if any(final_state.outputs(selected))
            error('msiq:traditionalTx:StagedOutputReadback', ...
                'Staged download unexpectedly enabled a selected output.');
        end
        final_outputs = logical(final_state.outputs);
        receipt_status = 'staged';
    end
    receipt = struct('schema_version', '1.0', 'status', receipt_status, ...
        'applied_at', timestamp_text(), 'run_id', plan.run_id, ...
        'run_dir', plan.run_dir, 'diagnostics_dir', plan.diagnostics_dir, ...
        'route', route, 'plan_hash', plan.plan_hash, ...
        'required_confirmation', plan.required_confirmation, ...
        'global_abort_used', true, 'global_start_used', true, ...
        'requested_output_enable', enable_output, ...
        'public_parameter_changes', comparison.public_parameter_changes, ...
        'memory_capacity', capacity, ...
        'hardware_sro_injection_ppm', field_or(plan, ...
        'hardware_sro_injection_ppm', 0), ...
        'other_active_before', other_active, ...
        'other_outputs_disabled', other_disabled, ...
        'other_outputs_restored', isempty(other_disabled) && other_verified, ...
        'initial_state', current, 'after_download_state', after_download, ...
        'final_state', final_state, 'output_mask', logical(final_outputs));
    msiq.save_tx_manifest(plan, plan, receipt);
    Result_Atomic_Write_Json(msiq.artifact_path( ...
        plan, 'execution_receipt.json', 'write'), ...
        receipt_for_json(receipt));
    write_reference_bundle(plan, receipt);
    output = receipt;
    output.diagnostics_dir = plan.diagnostics_dir;
    output.tx_dashboard_path = plan.tx_dashboard_path;
    output.reference_bundle_path = plan.reference_bundle_path;
    try
        msiq.plotting.tx_dashboard(plan.tx_dashboard_path, plan, receipt);
    catch dashboard_exception
        output.dashboard_warning = dashboard_exception.message;
    end
catch exception
    shutdown_channels = selected;
    if strict_switch, shutdown_channels = 1:4; end
    shutdown_verified = false;
    shutdown_error = '';
    if output_enabled || ~isempty(session)
        try
            mask = msiq.instruments.set_awg_channels_output(session, shutdown_channels, false);
            shutdown_verified = ~any(mask(shutdown_channels));
        catch shutdown_exception
            shutdown_error = shutdown_exception.message;
        end
    end
    verified_disabled = [];
    if shutdown_verified, verified_disabled = shutdown_channels; end
    failure = struct('schema_version', '1.0', 'status', 'failed', ...
        'failed_at', timestamp_text(), 'plan_hash', plan.plan_hash, ...
        'route', route, 'error_identifier', exception.identifier, ...
        'error_message', exception.message, 'shutdown_channels', shutdown_channels, ...
        'shutdown_verified', shutdown_verified, 'shutdown_error', shutdown_error, ...
        'selected_channels_disabled', verified_disabled);
    try
        Result_Atomic_Write_Json(msiq.artifact_path( ...
            plan, 'execution_failure.json', 'write'), failure);
    catch
    end
    try
        msiq.plotting.tx_dashboard(plan.tx_dashboard_path, plan, failure);
    catch
    end
    rethrow(exception);
end
clear cleanup;
end

function check_apply_cancel(options)
% Optional session-only cancellation hook; never copied into plan/receipt.
if isfield(options,'cancel_check') && isa(options.cancel_check,'function_handle')
    options.cancel_check();
end
end

function wait_for_awg_ready(session)
% Extended-memory initialization can outlast the short status-query timeout.
if session.mock
    msiq.instruments.query_scpi(session, '*OPC?');
    return;
end
original_timeout = session.interface.Timeout;
cleanup = onCleanup(@() restore_timeout(session.interface, original_timeout));
session.interface.Timeout = max(original_timeout, 15);
response = msiq.instruments.query_scpi(session, '*OPC?');
if str2double(strtrim(response)) ~= 1
    error('msiq:traditionalTx:AwgReady', ...
        'AWG did not confirm completion after INIT:IMM: %s.', response);
end
clear cleanup;
end

function restore_timeout(interface, value)
try
    interface.Timeout = value;
catch
end
end

function output = set_levels(cfg, options)
route = msiq.resolve_awg_route(options);
levels = route_levels(cfg, route, options);
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
state = msiq.instruments.set_awg_channel_levels(session, route.awg_channels, ...
    levels.amplitude_vpp, levels.offset_v);
output = struct('status', 'ok', 'route', route, 'levels', levels, ...
    'state', state, 'state_fingerprint', state_fingerprint(state));
clear cleanup;
end

function output = set_channel_settings(cfg, options)
route = msiq.resolve_awg_route(options);
levels = route_levels(cfg, route, options);
delays = route_delays(cfg, route, options);
selected = selected_setting_channels(route, options);
setting_names = selected_setting_names(options);
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
try
    before = msiq.instruments.read_awg_public_state(session);
    restore_mask = logical(before.outputs(selected));
    msiq.instruments.set_awg_channels_output(session, selected, false);
    for k = 1:numel(selected)
        channel = selected(k);
        route_index = find(route.awg_channels == channel, 1);
        write_selected_channel_settings(session, channel, route_index, ...
            setting_names, levels, delays);
    end
    applied = msiq.instruments.read_awg_public_state(session);
    verify_channel_settings(applied, route, levels, delays, selected, setting_names);
    if any(restore_mask)
        msiq.instruments.set_awg_channels_output( ...
            session, selected(restore_mask), true);
    end
    final_state = msiq.instruments.read_awg_public_state(session);
    verify_channel_settings(final_state, route, levels, delays, selected, setting_names);
    if ~isequal(logical(final_state.outputs(selected)), restore_mask)
        error('msiq:traditionalTx:ChannelSettingsOutputRestore', ...
            'Selected output state did not return to its pre-apply value.');
    end
    output = struct('status', 'applied', 'route', route, 'levels', levels, ...
        'sample_clock_delay_samples', delays, 'initial_state', before, ...
        'applied_state', applied, 'state', final_state, ...
        'physical_channels', selected, 'setting_names', {setting_names}, ...
        'state_fingerprint', state_fingerprint(final_state));
catch exception
    try
        msiq.instruments.set_awg_channels_output(session, selected, false);
    catch
    end
    rethrow(exception);
end

function channels = selected_setting_channels(route, options)
channels = double(route.awg_channels(:).');
if isfield(options, 'physical_channels') && ~isempty(options.physical_channels)
    channels = unique(double(options.physical_channels(:).'), 'stable');
end
if isempty(channels) || any(~isfinite(channels)) || ...
        any(abs(channels-round(channels)) > 1e-9) || ...
        any(~ismember(channels, route.awg_channels))
    error('msiq:traditionalTx:PhysicalChannels', ...
        'physical_channels must be an integer subset of the selected route.');
end
channels = round(channels);
end

function names = selected_setting_names(options)
allowed = {'amplitude_vpp','offset_v','sample_clock_delay_samples'};
names = allowed;
if isfield(options, 'setting_names') && ~isempty(options.setting_names)
    names = cellstr(string(options.setting_names));
end
names = unique(names, 'stable');
if isempty(names) || any(~ismember(names, allowed))
    error('msiq:traditionalTx:SettingNames', ...
        ['setting_names must contain amplitude_vpp, offset_v, ', ...
        'or sample_clock_delay_samples.']);
end
end

function write_selected_channel_settings( ...
        session, channel, route_index, names, levels, delays)
for index = 1:numel(names)
    switch names{index}
        case 'amplitude_vpp'
            command = sprintf(':VOLTage%d:AMPLitude %.15g', ...
                channel, levels.amplitude_vpp(route_index));
        case 'offset_v'
            command = sprintf(':VOLTage%d:OFFSet %.15g', ...
                channel, levels.offset_v(route_index));
        case 'sample_clock_delay_samples'
            command = sprintf(':ARM:SDELay%d %d', ...
                channel, delays(route_index));
        otherwise
            error('msiq:traditionalTx:SettingNames', ...
                'Unsupported channel setting: %s.', names{index});
    end
    msiq.instruments.write_scpi(session, command);
end
end
clear cleanup;
end

function output = reuse_route(cfg, selector, options)
run_dir = run_directory(selector, options);
manifest_path = msiq.artifact_path(run_dir, 'tx_manifest.mat', 'read');
if ~isfile(manifest_path)
    error('msiq:traditionalTx:ReuseManifest', ...
        'Missing successful TX manifest: %s.', manifest_path);
end
saved = msiq.load_tx_manifest(manifest_path);
if ~isfield(saved, 'receipt') || ~ismember(lower(char(string( ...
        saved.receipt.status))), {'applied','staged'})
    error('msiq:traditionalTx:ReuseManifest', ...
        'TX manifest does not describe a successful apply.');
end
route = saved.route;
desired = saved.plan.desired;
if isfield(options, 'memory_mode') && ...
        ~strcmpi(char(string(options.memory_mode)), desired.memory_mode)
    error('msiq:traditionalTx:ReuseMemoryMode', ...
        'Reuse cannot switch memory mode. Create and apply a new download plan.');
end
strict_channel_settings = true;
if isfield(options, 'expected_route') && ~isempty(options.expected_route) && ...
        ~strcmpi(char(string(options.expected_route)), char(string(route.name)))
    error('msiq:traditionalTx:ReuseRouteBinding', ...
        'Saved waveform route %s does not match expected route %s.', ...
        route.name, char(string(options.expected_route)));
end
if isfield(options, 'expected_waveform_signature') && ...
        ~isempty(options.expected_waveform_signature)
    saved_signature = field_or(saved.plan, 'waveform_signature', '');
    expected_signature = char(string(options.expected_waveform_signature));
    if isempty(saved_signature) || ~strcmp(saved_signature, expected_signature)
        error('msiq:traditionalTx:ReuseWaveformBinding', ...
            'Saved waveform identity is missing or does not match the current preview.');
    end
    current_levels = route_levels(cfg, route, options);
    current_delays = route_delays(cfg, route, options);
    desired.amplitude_vpp = current_levels.amplitude_vpp;
    desired.offset_v = current_levels.offset_v;
    desired.sample_clock_delay_samples = current_delays;
    strict_channel_settings = false;
end
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
before = msiq.instruments.read_awg_public_state(session);
if ~route_matches(before, desired, route)
    error('msiq:traditionalTx:ReuseState', ...
        'Recorded segment, length, selection, or shared AWG state changed.');
end
after_outputs = msiq.instruments.set_awg_channels_output( ...
    session, route.awg_channels, true);
after = msiq.instruments.read_awg_public_state(session);
verify_route_loaded(after, desired, route);
if strcmpi(saved.receipt.status, 'staged')
    staged_receipt = saved.receipt;
    receipt = staged_receipt;
    receipt.status = 'applied';
    receipt.applied_at = timestamp_text();
    receipt.reused_from_staged = true;
    receipt.final_state = after;
    receipt.output_mask = logical(after_outputs);
    plan = saved.plan;
    msiq.save_tx_manifest(run_dir, plan, receipt, staged_receipt);
    Result_Atomic_Write_Json(msiq.artifact_path( ...
        run_dir, 'execution_receipt.json', 'write'), ...
        receipt_for_json(receipt));
    write_reference_bundle(plan, receipt);
end
output = struct('status', 'reused', 'run_dir', run_dir, 'route', route, ...
    'diagnostics_dir', fullfile(run_dir, 'data'), ...
    'waveform_signature', field_or(saved.plan, 'waveform_signature', ''), ...
    'before', before, 'state', after, 'output_mask', logical(after_outputs), ...
    'state_fingerprint', state_fingerprint(after));
output.channel_settings_rebound = ~strict_channel_settings;
clear cleanup;
end

function output = stop_route(cfg, options)
route = msiq.resolve_awg_route(options);
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
output_mask = msiq.instruments.set_awg_channels_output( ...
    session, route.awg_channels, false);
state = msiq.instruments.read_awg_public_state(session);
output = struct('status', 'stopped', 'route', route, 'state', state, ...
    'output_mask', logical(output_mask), ...
    'state_fingerprint', state_fingerprint(state));
clear cleanup;
end

function desired = desired_state(waveforms, route, levels, delays, cfg, ...
        injected_sro_ppm, download)
divider = round(waveforms.master_sample_rate_hz / waveforms.awg_sample_rate_hz);
is_int = strcmpi(cfg.awg.memory_mode, 'INT');
if (~is_int && ~ismember(divider, [2 4])) || (is_int && divider ~= 1) || ...
        abs(waveforms.master_sample_rate_hz / waveforms.awg_sample_rate_hz-divider) > 1e-9
    error('msiq:traditionalTx:Divider', ...
        'Traditional TX supports only DIV2 and DIV4 waveform rates.');
end
if divider == 2 && numel(route.awg_channels) ~= 2
    error('msiq:traditionalTx:Div2Route', ...
        'DIV2 requires exactly one I/Q route pair.');
end
if nargin < 6 || isempty(injected_sro_ppm)
    injected_sro_ppm = 0;
end
scale = 1 + double(injected_sro_ppm)*1e-6;
actual_raster_hz = waveforms.master_sample_rate_hz / scale;
if ~isfinite(actual_raster_hz) || actual_raster_hz < 53.76e9 || ...
        actual_raster_hz > 65e9
    error('msiq:traditionalTx:SroInjectionRange', ...
        ['The requested hardware SRO injection needs an AWG raster of ', ...
        '%.12g Hz, outside [53.76e9, 65e9] Hz.'], actual_raster_hz);
end
desired = struct('dac_mode', 'FOUR', 'rdiv', sprintf('DIV%d', divider), ...
    'raster_hz', actual_raster_hz, ...
    'nominal_raster_hz', waveforms.master_sample_rate_hz, ...
    'hardware_sro_injection_ppm', double(injected_sro_ppm), ...
    'actual_waveform_sample_rate_hz', actual_raster_hz/divider, ...
    'memory_mode', 'EXT', 'segment', 1, ...
    'sample_count', max(download.source_sample_counts), ...
    'source_sample_counts', download.source_sample_counts, ...
    'padded_sample_count', max(download.final_sample_counts), ...
    'required_samples_per_channel', download.final_sample_counts, ...
    'amplitude_vpp', levels.amplitude_vpp, 'offset_v', levels.offset_v, ...
    'sample_clock_delay_samples', delays, ...
    'route_channels', route.awg_channels, ...
    'route_columns', route.waveform_columns);
desired.explicit_memory_mode = cfg.awg.explicit_memory_mode;
if is_int
    desired.rdiv = 'DIV4';
    desired.memory_mode = 'INT';
    desired.channel_memory_modes = repmat({'INT'},1,4);
elseif numel(route.awg_channels) == 2
    modes = repmat({'INT'}, 1, 4);
    if strcmpi(route.name, 'pair_b_ch3_ch4')
        % In FOUR mode, CH3/CH4 use extended memory with all four waveform
        % sources in the same topology. Outputs remain independent.
        modes(:) = {'EXT'};
        desired.memory_mode = 'EXT';
    else
        modes(route.awg_channels) = repmat({'EXT'}, 1, ...
            numel(route.awg_channels));
    end
    desired.channel_memory_modes = modes;
end
if ~strcmpi(desired.rdiv, cfg.awg.requested_rdiv)
    error('msiq:traditionalTx:DividerConfig', ...
        'Waveform rate does not match the requested AWG divider.');
end
end

function [waveforms, tx_ref, download, desired, report] = ...
        prepare_playback(cfg, seed, route, levels, delays, injected_sro_ppm)
if strcmpi(cfg.awg.memory_mode,'INT') && ...
        (~ismember(route.name, {'pair_a_ch1_ch2','pair_b_ch3_ch4'}) || ...
        numel(route.awg_channels) ~= 2)
    error('msiq:traditionalTx:IntRoute', 'INT supports one I/Q route pair only.');
end
[waveforms, tx_ref] = msiq.generate_waveforms(cfg, seed);
report = msiq.preflight_waveform(waveforms, cfg, preflight_model(cfg,route));
if ~report.ok
    error('msiq:traditionalTx:Preflight', 'Waveform preflight failed: %s.',report.reason);
end
download = msiq.instruments.prepare_awg_download(waveforms.awg_dac_data, ...
    route.awg_channels, route.waveform_columns, cfg.waveform.awg_alignment_samples);
desired = desired_state(waveforms,route,levels,delays,cfg,injected_sro_ppm,download);
if strcmpi(desired.memory_mode,'INT')
    capacity = capacity_preflight(desired,download,struct());
    if ~capacity.ok, throw_capacity_error(capacity); end
end
tx_ref.frame.memory_mode = desired.memory_mode;
tx_ref.frame.awg_padded_waveform_length = max(download.final_sample_counts);
tx_ref.frame.playback_period_s = tx_ref.frame.awg_padded_waveform_length / ...
    waveforms.awg_sample_rate_hz;
end

function require_outputs_off(state, desired)
if ~field_or(desired,'explicit_memory_mode',false), return; end
if ~isfield(state,'outputs') || numel(state.outputs) ~= 4 || ...
        any(~isfinite(double(state.outputs))) || any(state.outputs)
    error('msiq:traditionalTx:MemorySwitchOutputsOn', ...
        'Explicit INT/EXT downloads require all four outputs already OFF. No writes performed.');
end
end

function capacity = capacity_preflight(desired, download, state)
if ~isfield(download, 'channel_data') || ~iscell(download.channel_data) || ...
        numel(download.channel_data) ~= numel(download.channels)
    error('msiq:traditionalTx:DownloadData', ...
        'Prepared AWG download data is incomplete.');
end
actual_counts = cellfun(@numel, download.channel_data);
if ~isequal(double(actual_counts(:).'), ...
        double(download.final_sample_counts(:).'))
    error('msiq:traditionalTx:DownloadLengthMismatch', ...
        'Prepared AWG download lengths do not match the actual channel data.');
end
if isfield(desired, 'channel_memory_modes')
    modes = desired.channel_memory_modes;
else
    modes = repmat({desired.memory_mode}, 1, 4);
end
option_raw = '';
if isstruct(state) && isscalar(state) && isfield(state, 'options_raw')
    option_raw = state.options_raw;
end
capacity = msiq.instruments.awg_memory_capacity(struct( ...
    'dac_mode', desired.dac_mode, ...
    'channel_memory_modes', {modes}, ...
    'rdiv', desired.rdiv, ...
    'selected_channels', download.channels, ...
    'required_samples_per_channel', actual_counts, ...
    'option_raw', option_raw));
capacity.dac_raster_hz = desired.raster_hz;
end

function report = merge_capacity_preflight(waveform_report, capacity)
report = waveform_report;
report.waveform_ok = logical(waveform_report.ok);
report.waveform_reason = waveform_report.reason;
report.capacity = capacity;
report.ok = logical(waveform_report.ok && capacity.ok);
if ~capacity.ok
    report.reason = capacity.message;
elseif isempty(report.reason)
    report.reason = '波形与AWG内存容量检查通过';
end
end

function throw_capacity_error(capacity)
error('msiq:traditionalTx:AwgMemoryCapacity', '%s', capacity.message);
end

function comparison = compare_state(state, desired, route)
differences = struct( ...
    'dac_mode', ~strcmpi(state.dac_mode, desired.dac_mode), ...
    'rdiv', ~strcmpi(state.rdiv, desired.rdiv), ...
    'raster_hz', ~isfinite(state.raster_hz) || ...
        abs(state.raster_hz-desired.raster_hz) > 1);
differences.memory_topology = false;
if isfield(desired, 'channel_memory_modes')
    actual = upper(string({state.traces.memory_mode}));
    expected = upper(string(desired.channel_memory_modes));
    differences.memory_topology = any(actual ~= expected);
end

common = differences.dac_mode || differences.rdiv || differences.raster_hz || ...
    differences.memory_topology;
other = setdiff(find(state.outputs), route.awg_channels, 'stable');
channel_differences = repmat(struct('channel', NaN, 'amplitude_vpp', true, ...
    'offset_v', true, 'sample_clock_delay_samples', true), ...
    1, numel(route.awg_channels));
for k = 1:numel(route.awg_channels)
    channel = route.awg_channels(k);
    trace = state.traces(channel);
    channel_differences(k) = struct('channel', channel, ...
        'amplitude_vpp', ~isfinite(trace.amplitude_vpp) || ...
        abs(trace.amplitude_vpp-desired.amplitude_vpp(k)) > 1e-9, ...
        'offset_v', ~isfinite(trace.offset_v) || ...
        abs(trace.offset_v-desired.offset_v(k)) > 1e-9, ...
        'sample_clock_delay_samples', ...
        ~isfinite(trace.sample_clock_delay_samples) || ...
        trace.sample_clock_delay_samples ~= ...
        desired.sample_clock_delay_samples(k));
end
comparison = struct('public_parameter_changes', logical(common), ...
    'public_parameter_differences', differences, ...
    'channel_setting_differences', channel_differences, ...
    'affected_other_channels', double(other), ...
    'impact', struct('global_abort', true, 'global_abort_command', ':ABOR', ...
        'other_active_channels', double(other), ...
        'shared_parameter_change', logical(common), ...
        'shared_parameter_differences', differences, ...
        'other_channels_restart_allowed_only_if_verified', ~logical(common)));
end

function health = inspect_awg_state(state)
%INSPECT_AWG_STATE Convert silent QUERY_FAILED values into explicit GUI state.
issues = cell(0, 1);
if ~isstruct(state) || ~isscalar(state)
    issues{end+1} = 'state is not a scalar struct';
    health = health_result(issues);
    return;
end
required_text = {'idn', 'dac_mode', 'rdiv'};
for k = 1:numel(required_text)
    name = required_text{k};
    if ~isfield(state, name) || isempty(state.(name)) || ...
            contains(char(string(state.(name))), 'QUERY_FAILED', 'IgnoreCase', true)
        issues{end+1} = [name, ' query failed']; %#ok<AGROW>
    end
end
if ~isfield(state, 'raster_hz') || ~isfinite(double(state.raster_hz))
    issues{end+1} = 'raster frequency query failed';
end
if ~isfield(state, 'outputs') || numel(state.outputs) ~= 4
    issues{end+1} = 'output state query failed';
end
if ~isfield(state, 'traces') || numel(state.traces) ~= 4
    issues{end+1} = 'trace state query failed';
else
    for channel = 1:4
        trace = state.traces(channel);
        if ~isfield(trace, 'memory_mode') || isempty(trace.memory_mode) || ...
                contains(char(string(trace.memory_mode)), 'QUERY_FAILED', 'IgnoreCase', true)
            issues{end+1} = sprintf( ...
                'CH%d memory mode query failed', channel); %#ok<AGROW>
        end
        numeric_fields = {'selected_segment','segment','length','amplitude_vpp', ...
            'offset_v','sample_clock_delay_samples'};
        for k = 1:numel(numeric_fields)
            name = numeric_fields{k};
            if ~isfield(trace, name) || ~isfinite(double(trace.(name)))
                issues{end+1} = sprintf( ...
                    'CH%d %s query failed', channel, name); %#ok<AGROW>
            end
        end
    end
end
health = health_result(issues);
end

function health = health_result(issues)
if isempty(issues)
    health = struct('status', 'ok', 'message', 'AWG IDN and all public state fields read back successfully.', ...
        'issues', {cell(0,1)});
else
    health = struct('status', 'partial', ...
        'message', strjoin(issues, '; '), 'issues', {issues});
end
end

function comparison = empty_comparison()
comparison = struct('public_parameter_changes', false, ...
    'public_parameter_differences', struct(), ...
    'channel_setting_differences', struct([]), ...
    'affected_other_channels', zeros(1,0), ...
    'impact', struct('global_abort', true, 'global_abort_command', ':ABOR', ...
        'other_active_channels', zeros(1,0), ...
        'shared_parameter_change', false, ...
        'shared_parameter_differences', struct(), ...
        'other_channels_restart_allowed_only_if_verified', false));
end

function channels = active_channels_from_state(state)
channels = zeros(1,0);
if isstruct(state) && isfield(state, 'outputs') && numel(state.outputs) == 4
    channels = find(logical(state.outputs));
end
end

function phrase = confirmation_phrase(comparison, route, hashes, state_hash, nonce)
digest = msiq.sha256_bytes(route.name, strjoin(hashes, ','), state_hash, nonce);
token = upper(digest(1:12));
if comparison.public_parameter_changes
    phrase = sprintf('FORCE PUBLIC CHANGE %s %s', upper(route.name), token);
else
    phrase = sprintf('APPLY NEW WAVEFORM %s %s', upper(route.name), token);
end
end

function apply_common_state(session, current, desired)
rdiv_changed = ~strcmpi(current.rdiv, desired.rdiv);
current_divider = rdiv_number(current.rdiv);
desired_divider = rdiv_number(desired.rdiv);
% More EXT channels become legal only after increasing RDIV. When reducing
% RDIV, release the EXT channels first so the intermediate state stays legal.
if rdiv_changed && desired_divider > current_divider
    msiq.instruments.write_scpi(session, ...
        sprintf(':INST:MEM:EXT:RDIV %s', desired.rdiv));
end
if isfield(desired, 'channel_memory_modes')
    for channel = 1:4
        requested = desired.channel_memory_modes{channel};
        if ~strcmpi(current.traces(channel).memory_mode, requested)
            msiq.instruments.write_scpi(session, ...
                sprintf(':TRACe%d:MMOD %s', channel, requested));
        end
    end
end
if ~strcmpi(current.dac_mode, desired.dac_mode)
    msiq.instruments.write_scpi(session, sprintf(':INST:DACM %s', desired.dac_mode));
end
if rdiv_changed && desired_divider <= current_divider
    msiq.instruments.write_scpi(session, ...
        sprintf(':INST:MEM:EXT:RDIV %s', desired.rdiv));
end
if ~isfinite(current.raster_hz) || abs(current.raster_hz-desired.raster_hz) > 1
    msiq.instruments.write_scpi(session, ...
        sprintf(':FREQuency:RASTer %.15g', desired.raster_hz));
end
end

function value = rdiv_number(value)
text = upper(char(string(value)));
token = regexp(text, '^DIV([124])$', 'tokens', 'once');
if isempty(token)
    error('msiq:traditionalTx:RdivReadback', ...
        'Unexpected AWG RDIV value: %s.', text);
end
value = str2double(token{1});
end

function download_selected_waveforms(session, download, route, levels, desired)
for k = 1:numel(route.awg_channels)
    channel = route.awg_channels(k);
    samples = download.channel_data{k};
    msiq.instruments.write_scpi(session, ...
        sprintf(':TRACe%d:MMOD %s', channel, desired.memory_mode));
    msiq.instruments.write_scpi(session, ...
        sprintf(':TRACe%d:DELete %d', channel, desired.segment));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':TRACe%d:DEFine %d,%d', channel, desired.segment, numel(samples)));
    binary = int8(round(127*max(min(samples,1),-1)));
    msiq.instruments.io_audit('record_binary_write', 'awg');
    if session.mock
        fail_if_requested(session, 'download');
    else
        header = sprintf(':TRACe%d:DATA %d,0,', channel, desired.segment);
        binblockwrite(session.interface, binary, 'int8', header);
        fprintf(session.interface, '');
        msiq.instruments.query_scpi(session, '*OPC?');
    end
    msiq.instruments.write_scpi(session, ...
        sprintf(':TRACe%d:SELect %d', channel, desired.segment));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':VOLTage%d:AMPLitude %.15g', channel, levels.amplitude_vpp(k)));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':VOLTage%d:OFFSet %.15g', channel, levels.offset_v(k)));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':ARM:SDELay%d %d', channel, desired.sample_clock_delay_samples(k)));
end
end

function verify_route_loaded(state, desired, route)
if ~all(state.outputs(route.awg_channels))
    error('msiq:traditionalTx:OutputReadback', ...
        'Selected DAC outputs did not remain enabled.');
end
if ~route_matches(state, desired, route)
    error('msiq:traditionalTx:RouteReadback', ...
        'AWG route readback does not match the applied plan.');
end
end

function verify_route_downloaded(state, desired, route)
if ~route_matches(state, desired, route)
    error('msiq:traditionalTx:DownloadReadback', ...
        'AWG route readback does not match the downloaded plan.');
end
end

function yes = route_matches(state, desired, route)
yes = strcmpi(state.dac_mode, desired.dac_mode) && ...
    strcmpi(state.rdiv, desired.rdiv) && isfinite(state.raster_hz) && ...
    abs(state.raster_hz-desired.raster_hz) <= 1;
for k = 1:numel(route.awg_channels)
    channel = route.awg_channels(k);
    trace = state.traces(channel);
    yes = yes && strcmpi(trace.memory_mode, desired.memory_mode) && ...
        isfinite(trace.selected_segment) && ...
        trace.selected_segment == desired.segment && ...
        isfinite(trace.segment) && trace.segment == desired.segment && ...
        isfinite(trace.length) && ...
        trace.length == desired.required_samples_per_channel(k) && ...
        isfinite(trace.amplitude_vpp) && ...
        abs(trace.amplitude_vpp-desired.amplitude_vpp(k)) <= 1e-9 && ...
        isfinite(trace.offset_v) && ...
        abs(trace.offset_v-desired.offset_v(k)) <= 1e-9 && ...
        isfinite(trace.sample_clock_delay_samples) && ...
        trace.sample_clock_delay_samples == ...
        desired.sample_clock_delay_samples(k);
end
if isfield(desired, 'channel_memory_modes')
    for channel = 1:4
        yes = yes && strcmpi(state.traces(channel).memory_mode, ...
            desired.channel_memory_modes{channel});
    end
end
end

function yes = other_state_matches(before, after, selected)
other = setdiff(find(before.outputs), selected, 'stable');
yes = true;
for channel = other
    a = before.traces(channel);
    b = after.traces(channel);
    yes = yes && strcmpi(a.memory_mode, b.memory_mode) && ...
        numbers_equal(a.selected_segment, b.selected_segment) && ...
        numbers_equal(a.segment, b.segment) && numbers_equal(a.length, b.length);
end
yes = yes && isequal(logical(before.outputs(other)), logical(after.outputs(other)));
end

function yes = numbers_equal(a, b)
yes = isfinite(a) && isfinite(b) && abs(a-b) <= 1e-9;
end

function levels = route_levels(cfg, route, options)
channels = route.awg_channels;
amplitude = cfg.awg.amplitude_vpp(channels);
offset = cfg.awg.offset_v(channels);
if isfield(options, 'amplitude_vpp') && ~isempty(options.amplitude_vpp)
    amplitude = expand(options.amplitude_vpp, numel(channels), 'amplitude_vpp', true);
end
if isfield(options, 'offset_v') && ~isempty(options.offset_v)
    offset = expand(options.offset_v, numel(channels), 'offset_v', false);
end
levels = struct('amplitude_vpp', amplitude, 'offset_v', offset);
end

function delays = route_delays(cfg, route, options)
defaults = zeros(1, numel(route.awg_channels));
if isfield(cfg.awg, 'sample_clock_delay_samples') && ...
        ~isempty(cfg.awg.sample_clock_delay_samples)
    all_delays = double(cfg.awg.sample_clock_delay_samples(:).');
    if numel(all_delays) == 4
        defaults = all_delays(route.awg_channels);
    end
end
raw = defaults;
if isfield(options, 'sample_clock_delay_samples') && ...
        ~isempty(options.sample_clock_delay_samples)
    raw = options.sample_clock_delay_samples;
elseif isfield(options, 'sdel_samples') && ~isempty(options.sdel_samples)
    raw = options.sdel_samples;
end
delays = expand(raw, numel(route.awg_channels), ...
    'sample_clock_delay_samples', false);
if any(delays < 0) || any(delays > 95) || ...
        any(abs(delays-round(delays)) > 1e-9)
    error('msiq:traditionalTx:SampleClockDelay', ...
        'sample_clock_delay_samples must contain integers in [0, 95].');
end
delays = round(delays);
end

function targets = all_channel_targets(cfg, route, levels, delays, options)
amplitude = double(cfg.awg.amplitude_vpp(:).');
offset = double(cfg.awg.offset_v(:).');
sample_delay = zeros(1,4);
if isfield(cfg.awg, 'sample_clock_delay_samples') && ...
        numel(cfg.awg.sample_clock_delay_samples) == 4
    sample_delay = double(cfg.awg.sample_clock_delay_samples(:).');
end
amplitude = four_channel_option(options, 'all_channel_amplitude_vpp', ...
    amplitude, [0 Inf], false);
offset = four_channel_option(options, 'all_channel_offset_v', ...
    offset, [-Inf Inf], false);
sample_delay = four_channel_option(options, ...
    'all_channel_sample_clock_delay_samples', sample_delay, [0 95], true);
channels = route.awg_channels;
amplitude(channels) = levels.amplitude_vpp;
offset(channels) = levels.offset_v;
sample_delay(channels) = delays;
targets = struct('amplitude_vpp', amplitude, 'offset_v', offset, ...
    'sample_clock_delay_samples', sample_delay);
end

function values = four_channel_option(options, name, fallback, limits, integer_value)
values = double(fallback(:).');
if isfield(options, name) && ~isempty(options.(name))
    values = double(options.(name)(:).');
end
if numel(values) ~= 4 || any(~isfinite(values)) || ...
        any(values < limits(1)) || any(values > limits(2)) || ...
        (integer_value && any(abs(values-round(values)) > 1e-9))
    error('msiq:traditionalTx:AllChannelTargets', ...
        '%s must contain four valid channel values.', name);
end
if integer_value, values = round(values); end
end

function verify_channel_settings(state, route, levels, delays, channels, names)
if nargin < 5 || isempty(channels), channels = route.awg_channels; end
if nargin < 6 || isempty(names)
    names = {'amplitude_vpp','offset_v','sample_clock_delay_samples'};
end
for k = 1:numel(channels)
    channel = channels(k);
    route_index = find(route.awg_channels == channel, 1);
    trace = state.traces(channel);
    matches = true;
    if ismember('amplitude_vpp', names)
        matches = matches && isfinite(trace.amplitude_vpp) && ...
            abs(trace.amplitude_vpp-levels.amplitude_vpp(route_index)) <= 1e-9;
    end
    if ismember('offset_v', names)
        matches = matches && isfinite(trace.offset_v) && ...
            abs(trace.offset_v-levels.offset_v(route_index)) <= 1e-9;
    end
    if ismember('sample_clock_delay_samples', names)
        matches = matches && isfinite(trace.sample_clock_delay_samples) && ...
            trace.sample_clock_delay_samples == delays(route_index);
    end
    if ~matches
        error('msiq:traditionalTx:ChannelSettingsReadback', ...
            'CH%d %s readback did not match.', channel, strjoin(names, ', '));
    end
end
end

function value = expand(value, count, name, positive)
value = double(value(:).');
if isscalar(value), value = repmat(value, 1, count); end
if numel(value) ~= count || any(~isfinite(value)) || (positive && any(value <= 0))
    error('msiq:traditionalTx:LevelInput', ...
        '%s must be finite and scalar or match the route.', name);
end
end

function seed = get_seed(cfg, options)
seed = cfg.experiment.seed_values(1);
if isfield(options, 'seed') && ~isempty(options.seed)
    seed = double(options.seed);
end
validateattributes(seed, {'numeric'}, {'scalar','integer','nonnegative'});
end

function cfg = configure_rdiv(cfg, options)
memory_mode = text_option(options, 'memory_mode', 'EXT', {'ext','int'});
cfg.awg.memory_mode = upper(memory_mode);
cfg.awg.explicit_memory_mode = isfield(options,'memory_mode') && ~isempty(options.memory_mode);
rdiv = 'DIV4';
if isfield(options, 'rdiv') && ~isempty(options.rdiv)
    rdiv = upper(char(string(options.rdiv)));
end
if strcmpi(memory_mode,'INT') && ~strcmpi(rdiv,'DIV4')
    error('msiq:traditionalTx:IntRdiv', ...
        'INT uses full raster playback with the RDIV register fixed at DIV4.');
end
if strcmpi(rdiv, 'DIV1')
    error('msiq:traditionalTx:Div1Unsupported', ...
        ['M8195A FOUR mode rejects EXT/DIV1. CH3/CH4 full-rate ', ...
        'playback cannot use the current long-frame waveform.']);
end
if ~ismember(rdiv, {'DIV2','DIV4'})
    error('msiq:traditionalTx:RequestedDivider', ...
        'Traditional TX supports rdiv DIV2 or DIV4 only.');
end
divider = str2double(extractAfter(rdiv, 'DIV'));
cfg.awg.requested_rdiv = rdiv;
cfg.waveform.awg_alignment_samples = 128;
if strcmpi(memory_mode,'INT')
    divider = 1;
    cfg.waveform.awg_alignment_samples = 512;
end
cfg.waveform.awg_sample_rate_hz = cfg.waveform.master_sample_rate_hz/divider;
cfg.waveform.awg_samples_per_symbol = ...
    cfg.waveform.awg_sample_rate_hz/cfg.waveform.symbol_rate_hz;
cfg.waveform.decimation = divider;
end

function model = preflight_model(cfg, route)
if strcmpi(cfg.awg.memory_mode,'INT')
    model = 'M8195A_4int';
elseif strcmpi(cfg.awg.requested_rdiv, 'DIV2')
    if numel(route.awg_channels) ~= 2
        error('msiq:traditionalTx:Div2Route', ...
            'DIV2 requires exactly one I/Q route pair.');
    end
    model = 'M8195A_2ext_div2';
else
    model = cfg.awg.model;
end
end

function run_dir = create_run_dir(cfg, route_name, options)
if nargin < 3 || isempty(options)
    options = struct();
end
requested = '';
if isstruct(options) && isfield(options, 'run_dir') && ~isempty(options.run_dir)
    requested = char(string(options.run_dir));
end
if ~isempty(requested)
    run_dir = requested;
    if isfolder(run_dir) && ~isempty(field_or(options, 'artifact_prefix', ''))
        location = struct('run_dir',run_dir, ...
            'artifact_prefix',options.artifact_prefix);
        if isfile(msiq.artifact_path(location, 'tx_manifest.mat'))
            error('msiq:traditionalTx:RunDirectoryExists', ...
                'TX observation already exists in %s.', run_dir);
        end
        return;
    end
    if isfolder(run_dir)
        error('msiq:traditionalTx:RunDirectoryExists', ...
            'AWG plan requires a new run directory, but %s already exists.', ...
            run_dir);
    end
end
run = msiq.create_output_run(cfg,'measurement', ...
    ['manual_16qam_' route_name],requested);
run_dir = run.OutputDir;
end

function persist_plan(plan)
public = plan_for_json(plan);
Result_Atomic_Write_Json(msiq.artifact_path(plan, 'awg_plan.json', 'write'), public);
msiq.save_tx_manifest(plan, plan, struct('status', 'planned'));
tx_ref = plan.tx_ref;
reference_path = msiq.artifact_path(plan, 'tx_reference.mat', 'write');
if isfield(plan,'storage_run_root')
    stored = load(msiq.artifact_path(plan,'tx_manifest.mat','read'),'plan');
    msiq.atomic_save(reference_path,struct('shared_data',stored.plan.shared_data));
else
    save(reference_path,'tx_ref','-v7.3');
end
write_reference_bundle(plan, struct('status', 'planned'));
try
    msiq.plotting.tx_dashboard(plan.tx_dashboard_path, plan, ...
        struct('status', 'planned'));
catch
    % Plotting is best effort; the plan and reference remain authoritative.
end
end

function public = plan_for_json(plan)
keep = {'schema_version','run_id','run_dir','diagnostics_dir','created_at', ...
    'status','route','levels','hardware_targets','seed','experiment_note', ...
    'config_hash','parameter_hash', ...
    'hardware_sro_injection_ppm','nominal_awg_raster_hz', ...
    'waveform_id','waveform_hashes','waveform_normalization', ...
    'waveform_signature','waveform_sample_count', ...
    'padded_sample_count','final_sample_counts','waveform_sample_rate_hz', ...
    'waveform_duration_s','memory_capacity', ...
    'awg_raster_hz','actual_waveform_sample_rate_hz', ...
    'actual_waveform_duration_s','preflight','awg_snapshot','awg_snapshot_fingerprint', ...
    'public_parameter_changes','active_channels','affected_other_channels', ...
    'sample_clock_delay_samples','channel_setting_differences', ...
    'public_parameter_differences','global_abort_required','global_abort_command', ...
    'impact','confirmation_nonce','required_confirmation','plan_hash','desired'};
keep{end+1} = 'tx_dashboard_path';
keep{end+1} = 'reference_bundle_path';
public = struct();
for k = 1:numel(keep)
    public.(keep{k}) = plan.(keep{k});
end
end

function public = receipt_for_json(receipt)
public = receipt;
end

function bundle = reference_bundle(plan)
% Keep the portable bundle independent of local VISA configuration.
bundle = struct();
bundle.schema_version = '2.0';
bundle.created_at = plan.created_at;
bundle.waveform_id = plan.waveform_id;
bundle.waveform_hashes = plan.waveform_hashes;
bundle.waveform_signature = field_or(plan, 'waveform_signature', ...
    waveform_fingerprint(plan.config_hash, plan.waveform_hashes));
bundle.waveform_sample_count = plan.waveform_sample_count;
bundle.padded_sample_count = plan.padded_sample_count;
bundle.final_sample_counts = plan.final_sample_counts;
bundle.memory_capacity = plan.memory_capacity;
bundle.waveform_sample_rate_hz = plan.waveform_sample_rate_hz;
bundle.waveform_duration_s = plan.waveform_duration_s;
bundle.awg_raster_hz = plan.awg_raster_hz;
bundle.hardware_sro_injection_ppm = plan.hardware_sro_injection_ppm;
bundle.nominal_awg_raster_hz = plan.nominal_awg_raster_hz;
bundle.actual_waveform_sample_rate_hz = plan.actual_waveform_sample_rate_hz;
bundle.actual_waveform_duration_s = plan.actual_waveform_duration_s;
bundle.seed = plan.seed;
bundle.experiment_note = plan.experiment_note;
bundle.config_hash = plan.config_hash;
bundle.parameter_hash = plan.parameter_hash;
bundle.route = plan.route;
bundle.desired = plan.desired;
bundle.levels = plan.levels;
bundle.sample_clock_delay_samples = plan.sample_clock_delay_samples;
bundle.hardware_targets = field_or(plan, 'hardware_targets', struct());
bundle.plan_hash = plan.plan_hash;
bundle.tx_ref = plan.tx_ref;
bundle.reference_payload_policy = ...
    plan.tx_ref.frame.reference_payload_policy;
bundle.dsp_config = struct('waveform', plan.cfg.waveform, ...
    'receiver', plan.cfg.receiver);
bundle.modulation_order = plan.cfg.waveform.modulation_order;
bundle.frame_structure = reference_frame_structure(plan.cfg.waveform);
bundle.rate_relationship = struct( ...
    'memory_mode', plan.desired.memory_mode, ...
    'master_sample_rate_hz', plan.cfg.waveform.master_sample_rate_hz, ...
    'selected_up', plan.cfg.waveform.selected_up, ...
    'symbol_rate_hz', plan.cfg.waveform.symbol_rate_hz, ...
    'occupied_bandwidth_hz', plan.cfg.waveform.occupied_bandwidth_hz, ...
    'rate_generation_mode', plan.cfg.waveform.rate_generation_mode, ...
    'shaping_samples_per_symbol', ...
    plan.cfg.waveform.shaping_samples_per_symbol, ...
    'rdiv', plan.cfg.awg.requested_rdiv, ...
    'awg_sample_rate_hz', plan.cfg.waveform.awg_sample_rate_hz, ...
    'actual_awg_sample_rate_hz', plan.actual_waveform_sample_rate_hz, ...
    'hardware_sro_injection_ppm', plan.hardware_sro_injection_ppm, ...
    'awg_samples_per_symbol', plan.cfg.waveform.awg_samples_per_symbol);
bundle.iq_calibration = struct( ...
    'q_relative_delay_samples', plan.cfg.waveform.q_relative_delay_samples, ...
    'invert_i', logical(plan.cfg.waveform.invert_i), ...
    'invert_q', logical(plan.cfg.waveform.invert_q));
bundle.waveform_normalization = field_or(plan.waveforms, 'normalization', ...
    struct('mode', field_or(plan.cfg.waveform, 'normalization_mode', ...
    'legacy_peak_scale')));
bundle.awg_channel_settings = struct( ...
    'route_channels', plan.route.awg_channels, ...
    'target_amplitude_vpp', plan.levels.amplitude_vpp, ...
    'target_offset_v', plan.levels.offset_v, ...
    'target_sample_clock_delay_samples', plan.sample_clock_delay_samples, ...
    'target_all_amplitude_vpp', field_or(bundle.hardware_targets, ...
    'amplitude_vpp', nan(1,4)), ...
    'target_all_offset_v', field_or(bundle.hardware_targets, ...
    'offset_v', nan(1,4)), ...
    'target_all_sample_clock_delay_samples', ...
    field_or(bundle.hardware_targets, 'sample_clock_delay_samples', nan(1,4)), ...
    'readback_amplitude_vpp', [plan.awg_snapshot.traces.amplitude_vpp], ...
    'readback_offset_v', [plan.awg_snapshot.traces.offset_v], ...
    'readback_sample_clock_delay_samples', ...
    [plan.awg_snapshot.traces.sample_clock_delay_samples]);
bundle.execution = struct('status', 'planned');
end

function value = reference_frame_structure(waveform)
names = {'sync_length_symbols','sync_repeats','training_symbols', ...
    'pilot_interval_symbols','guard_symbols','ldpc_blocks_per_frame', ...
    'frame_repetitions'};
value = struct();
for k = 1:numel(names)
    value.(names{k}) = waveform.(names{k});
end
end

function value = parameter_fingerprint(route, levels, delays, config_hash, ...
        waveform_hashes, experiment_note, injected_sro_ppm, hardware_targets)
if isempty(experiment_note)
    experiment_note = '<empty-note>';
end
value = msiq.sha256_bytes(jsonencode(route), jsonencode(levels), ...
    jsonencode(delays), jsonencode(hardware_targets), ...
    config_hash, strjoin(waveform_hashes, ','), experiment_note, ...
    sprintf('hardware_sro_injection_ppm=%.15g', injected_sro_ppm));
end

function value = waveform_fingerprint(config_hash, waveform_hashes)
value = msiq.sha256_bytes(config_hash, strjoin(waveform_hashes, ','));
end

function write_reference_bundle(plan, execution)
bundle = reference_bundle(plan);
bundle.execution = portable_execution(execution);
path = msiq.artifact_path(plan,'tx_reference_bundle.mat','write');
if isfield(plan,'storage_run_root')
    stored = load(msiq.artifact_path(plan,'tx_manifest.mat','read'),'plan');
    bundle.shared_data = stored.plan.shared_data;
end
msiq.save_reference_bundle(path,bundle,path);
end

function execution = portable_execution(receipt)
execution = struct('status', char(string(field_or(receipt, 'status', 'planned'))));
keep = {'applied_at','plan_hash','route','output_mask','global_abort_used', ...
    'global_start_used','public_parameter_changes','hardware_sro_injection_ppm'};
for k = 1:numel(keep)
    name = keep{k};
    if isstruct(receipt) && isfield(receipt, name)
        execution.(name) = receipt.(name);
    end
end
end

function value = requested_hardware_sro_ppm(options)
value = 0;
if isstruct(options) && isfield(options, 'hardware_sro_injection_ppm') && ...
        ~isempty(options.hardware_sro_injection_ppm)
    value = double(options.hardware_sro_injection_ppm);
end
if ~isscalar(value) || ~isfinite(value) || 1 + value*1e-6 <= 0
    error('msiq:traditionalTx:SroInjection', ...
        'hardware_sro_injection_ppm must be a finite scalar with positive time scale.');
end
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end

function value = numeric_option(options, name, fallback, limits)
value = fallback;
if isfield(options, name) && ~isempty(options.(name))
    value = double(options.(name));
end
if ~isscalar(value) || ~isfinite(value) || value < limits(1) || ...
        value > limits(2)
    error('msiq:traditionalTx:ParameterRange', ...
        '%s must be a finite scalar in [%g, %g].', ...
        name, limits(1), limits(2));
end
end

function value = integer_option(options, name, fallback, limits)
value = numeric_option(options, name, fallback, limits);
if abs(value-round(value)) > 1e-9
    error('msiq:traditionalTx:ParameterInteger', ...
        '%s must be an integer.', name);
end
value = round(value);
end

function value = logical_option(options, name, fallback)
value = logical(fallback);
if ~isfield(options, name) || isempty(options.(name))
    return;
end
raw = options.(name);
if islogical(raw) && isscalar(raw)
    value = raw;
elseif isnumeric(raw) && isscalar(raw) && isfinite(raw) && ...
        ismember(raw, [0 1])
    value = logical(raw);
else
    error('msiq:traditionalTx:ParameterLogical', ...
        '%s must be a scalar logical value.', name);
end
end

function value = text_option(options, name, fallback, allowed)
value = lower(char(string(fallback)));
if isfield(options, name) && ~isempty(options.(name))
    value = lower(char(string(options.(name))));
end
if ~ismember(value, allowed)
    error('msiq:traditionalTx:ParameterText', ...
        '%s must be one of: %s.', name, strjoin(allowed, ', '));
end
end

function path = run_directory(selector, options)
path = '';
if ischar(selector) || (isstring(selector) && isscalar(selector))
    path = char(selector);
end
if isempty(path) && isfield(options, 'run_dir') && ~isempty(options.run_dir)
    path = char(string(options.run_dir));
end
if isempty(path) || ~isfolder(path)
    error('msiq:traditionalTx:RunDirectory', ...
        'Specify an existing manual-loopback run directory.');
end
end

function hash = state_fingerprint(state)
canonical = struct('dac_mode', char(string(state.dac_mode)), ...
    'rdiv', char(string(state.rdiv)), 'raster_hz', double(state.raster_hz), ...
    'options_raw', char(string(field_or(state, 'options_raw', ''))), ...
    'outputs', logical(state.outputs), 'traces', state.traces);
hash = msiq.sha256_bytes(jsonencode(canonical));
end

function value = last_path_part(path)
[~, value] = fileparts(path);
end

function value = timestamp_text()
value = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
end

function value = plan_nonce()
[~, generated] = fileparts(tempname);
value = msiq.sha256_bytes(generated, timestamp_text());
end

function fail_if_requested(session, stage)
spec = session.specification;
if isfield(spec, 'fail_stage') && strcmpi(char(string(spec.fail_stage)), stage)
    error('msiq:traditionalTx:MockDownloadFailure', ...
        'Injected TX download failure at %s.', stage);
end
end
