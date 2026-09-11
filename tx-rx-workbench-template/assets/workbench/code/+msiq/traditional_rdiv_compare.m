function output = traditional_rdiv_compare(action, selector, options)
%TRADITIONAL_RDIV_COMPARE Controlled DIV2/DIV4 manual-loopback comparison.

if nargin < 1 || isempty(action)
    action = 'rdiv_compare_plan';
end
if nargin < 2
    selector = [];
end
if nargin < 3 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:traditionalRdiv:Options', ...
        'Comparison options must be a scalar struct.');
end

action = lower(char(string(action)));
switch action
    case 'rdiv_compare_plan'
        cfg = load_cfg(options);
        output = create_comparison_plan(cfg, selector, options);
    case 'rdiv_compare_apply'
        if ~isfield(options, 'plan') || ~isstruct(options.plan) || ...
                ~isscalar(options.plan)
            error('msiq:traditionalRdiv:Plan', ...
                'rdiv_compare_apply requires options.plan from rdiv_compare_plan.');
        end
        output = apply_comparison_plan(options.plan, options);
    otherwise
        error('msiq:traditionalRdiv:Action', ...
            'Unknown comparison action: %s.', action);
end
end

function cfg = load_cfg(options)
if isfield(options, 'cfg_override') && ~isempty(options.cfg_override)
    cfg = options.cfg_override;
else
    cfg = msiq.build_config('v2_traditional_wz');
end
if ~isstruct(cfg) || ~isfield(cfg, 'waveform') || ...
        ~isfield(cfg, 'instrument') || ~isfield(cfg, 'awg')
    error('msiq:traditionalRdiv:Config', ...
        'DIV2/DIV4 comparison needs a traditional V2 configuration.');
end
cfg.waveform.architecture = 'single_complex_stream';
% The controlled divider comparison uses one information-bearing logical
% frame per AWG segment. The AWG continuously loops that segment, so a
% multi-frame scope window still supplies independent sync peaks for SRO.
cfg.waveform.frame_repetitions = 1;
if isfield(options, 'frame_repetitions') && ~isempty(options.frame_repetitions)
    validateattributes(options.frame_repetitions, {'numeric'}, ...
        {'scalar','integer','>=',1});
    cfg.waveform.frame_repetitions = double(options.frame_repetitions);
end
cfg.results_root = fullfile(cfg.project_root, 'measurement');
end

function plan = create_comparison_plan(cfg, selector, options)
route = comparison_route(options);
request = comparison_request(cfg, options);
awg = msiq.traditional_tx('awg_status', [], struct('cfg_override', cfg));
scope = read_scope(cfg, route);
require_all_outputs_off(awg.state);

run_dir = create_comparison_run_dir(cfg, selector, options);
previews = [preview_condition(cfg, route, request, 'DIV2'), ...
    preview_condition(cfg, route, request, 'DIV4')];
sequence = build_sequence(previews, request.repeats_per_rdiv);
minimum_window = max([30.1156e-6, ...
    [previews.waveform_duration_s] * 1.1]);

plan = struct();
plan.schema_version = '1.0';
plan.run_id = string(last_path_part(run_dir));
plan.run_dir = run_dir;
plan.diagnostics_dir = fullfile(run_dir, 'data');
plan.created_at = timestamp_text();
plan.route = route;
plan.repeats_per_rdiv = request.repeats_per_rdiv;
plan.frame_repetitions = cfg.waveform.frame_repetitions;
plan.seed = request.seed;
plan.levels = request.levels;
plan.minimum_capture_window_s = minimum_window;
plan.awg_snapshot = awg.state;
plan.awg_snapshot_fingerprint = awg_fingerprint(awg.state);
plan.scope_snapshot = scope.scope;
plan.scope_snapshot_fingerprint = scope_fingerprint(scope.scope);
plan.conditions = previews;
plan.sequence = sequence;
plan.global_abort_per_trial = true;
plan.global_abort_command = ':ABOR';
plan.required_initial_output_mask = false(1, 4);
plan.confirmation_nonce = plan_nonce();
plan.required_confirmation = batch_confirmation_phrase(plan);
plan.plan_hash = msiq.sha256_bytes( ...
    plan.awg_snapshot_fingerprint, plan.scope_snapshot_fingerprint, ...
    jsonencode(sequence), plan.confirmation_nonce);
plan.cfg = cfg;
persist_comparison_plan(plan);
end

function result = apply_comparison_plan(plan, options)
validate_plan(plan);
if ~isfield(options, 'confirmation_phrase') || ~strcmp( ...
        char(string(options.confirmation_phrase)), ...
        char(string(plan.required_confirmation)))
    error('msiq:traditionalRdiv:Confirmation', ...
        'Set confirmation_phrase to plan.required_confirmation.');
end

cfg = plan.cfg;
route = plan.route;
result = initial_result(plan);
result.started_at = timestamp_text();
cleanup = onCleanup(@() cleanup_stop(cfg, route));
expected_awg_fingerprint = plan.awg_snapshot_fingerprint;
active_trial = 0;

try
    verify_current_baseline(cfg, route, plan, expected_awg_fingerprint);
    for index = 1:numel(plan.sequence)
        active_trial = index;
        cfg = invoke_mock_hook(options, 'before_trial', index, cfg, plan);
        [current_awg, current_scope] = verify_current_baseline( ...
            cfg, route, plan, expected_awg_fingerprint);

        trial = result.trials(index);
        trial.status = 'running';
        trial.started_at = timestamp_text();
        trial.awg_before = current_awg;
        trial.scope_before = current_scope;
        result.trials(index) = trial;
        result.status = 'running';
        persist_comparison_result(plan, result);

        tx_dir = plan.run_dir;
        tx_prefix = sprintf('%03d_%s_TX', index, trial.rdiv);
        rx_prefix = sprintf('%03d_%s_RX', index, trial.rdiv);
        trial.tx_artifact_prefix = tx_prefix;
        trial.rx_artifact_prefix = rx_prefix;
        tx_options = struct('cfg_override', cfg, 'route', route.name, ...
            'rdiv', trial.rdiv, 'seed', plan.seed, ...
            'amplitude_vpp', plan.levels.amplitude_vpp, ...
            'offset_v', plan.levels.offset_v, 'run_dir', tx_dir, ...
            'storage_run_root',fullfile(plan.run_dir,'data'), ...
            'artifact_prefix', tx_prefix);
        tx_plan = msiq.traditional_tx('awg_plan', [], tx_options);
        trial.tx_run_dir = tx_plan.run_dir;
        trial.tx_plan_hash = tx_plan.plan_hash;
        trial.tx_required_confirmation = tx_plan.required_confirmation;
        trial.waveform_hashes = tx_plan.waveform_hashes;
        result.trials(index) = trial;

        cfg = invoke_mock_hook(options, 'after_tx_plan', index, cfg, plan);
        receipt = msiq.traditional_tx('awg_apply', [], struct( ...
            'plan', tx_plan, ...
            'confirmation_phrase', tx_plan.required_confirmation));
        trial.awg_after_apply = receipt.final_state;
        verify_trial_readback(receipt.final_state, trial, plan);

        cfg = invoke_mock_hook(options, 'before_capture', index, cfg, plan);
        scope_before_capture = read_scope(cfg, route);
        if ~strcmp(scope_fingerprint(scope_before_capture.scope), ...
                plan.scope_snapshot_fingerprint)
            error('msiq:traditionalRdiv:ScopeStateDrift', ...
                'LeCroy settings changed before trial %d capture.', index);
        end
        trial.scope_before_capture = scope_before_capture.scope;
        result.trials(index) = trial;

        rx_dir = plan.run_dir;
        capture = msiq.traditional_rx('capture', [], struct( ...
            'run_dir', rx_dir, 'artifact_prefix', rx_prefix, ...
            'tx_reference_bundle', receipt.reference_bundle_path, ...
            'cfg_override', cfg));
        trial.rx_run_dir = capture.run_dir;
        trial.capture_status = capture.status;
        trial.capture_physical_window = capture.physical_window;
        if ~capture.demod_ready || minimum_overlap(capture.physical_window) + 1e-12 < ...
                plan.minimum_capture_window_s
            error('msiq:traditionalRdiv:CaptureWindow', ...
                ['Trial %d physical overlap is insufficient: %.9g s; ', ...
                'at least %.9g s is required.'], index, ...
                minimum_overlap(capture.physical_window), plan.minimum_capture_window_s);
        end

        demod = msiq.traditional_rx('demod_capture', capture.run_dir, ...
            struct('cfg_override', cfg, 'artifact_prefix', rx_prefix));
        trial.demod_status = demod.status;
        if ~strcmpi(demod.status, 'decoded')
            error('msiq:traditionalRdiv:Demodulation', ...
                'Trial %d did not decode: %s.', index, demod.status);
        end
        trial.metrics = extract_metrics(demod, tx_plan);
        result.trials(index) = trial;
        persist_comparison_result(plan, result);
        if ~trial.metrics.decoder_pass
            error('msiq:traditionalRdiv:DecoderFailure', ...
                'Trial %d FEC decoder did not pass.', index);
        end
        if ~trial.metrics.sync_ok
            error('msiq:traditionalRdiv:Synchronization', ...
                'Trial %d returned decoded data without a valid synchronization.', index);
        end

        stopped = stop_selected(cfg, route);
        trial.awg_after_stop = stopped.state;
        trial.stopped_at = timestamp_text();
        trial.status = 'decoded';
        result.trials(index) = trial;
        expected_awg_fingerprint = awg_fingerprint(stopped.state);
        persist_comparison_result(plan, result);
    end
    result.status = 'completed';
    result.completed_at = timestamp_text();
catch exception
    if active_trial > 0 && active_trial <= numel(result.trials)
        trial = result.trials(active_trial);
        trial.status = failure_trial_status(exception);
        trial.error_identifier = exception.identifier;
        trial.error_message = exception.message;
        trial.finished_at = timestamp_text();
        result.trials(active_trial) = trial;
    end
    result.status = failure_result_status(exception);
    result.failure = struct('occurred_at', timestamp_text(), ...
        'trial_index', active_trial, 'error_identifier', exception.identifier, ...
        'error_message', exception.message);
    result.completed_at = timestamp_text();
end

try
    stopped = stop_selected(cfg, route);
    result.final_stop = stopped;
catch exception
    if ~isfield(result, 'failure') || isempty(field_or(result.failure, ...
            'error_identifier', ''))
        result.status = 'failed';
        result.failure = struct('occurred_at', timestamp_text(), ...
            'trial_index', active_trial, 'error_identifier', exception.identifier, ...
            'error_message', ['Final selected-channel stop failed: ', exception.message]);
    end
end
result.completed_at = timestamp_text();
result.conclusion = comparison_conclusion(result.trials, result.status);
persist_comparison_result(plan, result);
Result_Finalize_Run(plan.run_dir,result.status,'',[], '');
clear cleanup;
end

function request = comparison_request(cfg, options)
repeats = field_or(options, 'repeats_per_rdiv', 5);
validateattributes(repeats, {'numeric'}, {'scalar','integer','finite'});
if double(repeats) ~= 5
    error('msiq:traditionalRdiv:Repeats', ...
        'This controlled comparison is fixed at five DIV2/DIV4 pairs.');
end
seed = field_or(options, 'seed', 26072701);
validateattributes(seed, {'numeric'}, {'scalar','integer','nonnegative'});
amplitude = cfg.awg.amplitude_vpp([1 2]);
offset = cfg.awg.offset_v([1 2]);
if isfield(options, 'amplitude_vpp') && ~isempty(options.amplitude_vpp)
    amplitude = expand_level(options.amplitude_vpp, 'amplitude_vpp', true);
end
if isfield(options, 'offset_v') && ~isempty(options.offset_v)
    offset = expand_level(options.offset_v, 'offset_v', false);
end
request = struct('repeats_per_rdiv', double(repeats), 'seed', double(seed), ...
    'levels', struct('amplitude_vpp', amplitude, 'offset_v', offset));
end

function route = comparison_route(options)
route = msiq.resolve_awg_route(options);
if ~strcmpi(route.name, 'pair_a_ch1_ch2') || ...
        ~isequal(route.awg_channels, [1 2]) || ...
        ~isequal(route.waveform_columns, [1 2]) || ...
        ~isequal(upper(string(route.scope_channels)), ["C1" "C2"])
    error('msiq:traditionalRdiv:Route', ...
        ['DIV2/DIV4 comparison is restricted to pair_a_ch1_ch2 ', ...
        '(AWG CH1/CH2 and LeCroy C1/C2).']);
end
end

function value = expand_level(value, name, positive)
value = double(value(:).');
if isscalar(value)
    value = repmat(value, 1, 2);
end
if numel(value) ~= 2 || any(~isfinite(value)) || ...
        (positive && any(value <= 0))
    error('msiq:traditionalRdiv:Level', ...
        '%s must be finite and scalar or contain two values.', name);
end
end

function preview = preview_condition(cfg, route, request, rdiv)
trial_cfg = config_for_rdiv(cfg, rdiv);
[waveforms, tx_ref] = msiq.generate_waveforms(trial_cfg, request.seed);
model = cfg.awg.model;
if strcmpi(rdiv, 'DIV2')
    model = 'M8195A_2ext_div2';
end
preflight = msiq.preflight_waveform(waveforms, trial_cfg, model);
if ~preflight.ok
    error('msiq:traditionalRdiv:Preflight', ...
        '%s waveform preflight failed: %s.', rdiv, preflight.reason);
end
hashes = cell(1, 2);
for k = 1:2
    hashes{k} = msiq.sha256_bytes( ...
        double(waveforms.awg_dac_data(:, route.waveform_columns(k))));
end
preview = struct();
preview.rdiv = upper(char(string(rdiv)));
preview.waveform_sample_rate_hz = waveforms.awg_sample_rate_hz;
preview.waveform_sample_count = size(waveforms.awg_dac_data, 1);
preview.padded_sample_count = ceil(preview.waveform_sample_count/128)*128;
preview.waveform_duration_s = preview.waveform_sample_count / ...
    preview.waveform_sample_rate_hz;
preview.awg_samples_per_symbol = trial_cfg.waveform.awg_samples_per_symbol;
preview.awg_raster_hz = waveforms.master_sample_rate_hz;
preview.waveform_hashes = hashes;
preview.waveform_id = tx_ref.waveform_id;
preview.preflight = preflight;
preview.desired = desired_for_preview(route, request.levels, preview);
end

function cfg = config_for_rdiv(cfg, rdiv)
rdiv = upper(char(string(rdiv)));
if ~ismember(rdiv, {'DIV2','DIV4'})
    error('msiq:traditionalRdiv:RDIV', 'Only DIV2 and DIV4 are allowed.');
end
divider = str2double(extractAfter(rdiv, 'DIV'));
cfg.awg.requested_rdiv = rdiv;
cfg.waveform.awg_sample_rate_hz = cfg.waveform.master_sample_rate_hz/divider;
cfg.waveform.awg_samples_per_symbol = cfg.waveform.awg_sample_rate_hz / ...
    cfg.waveform.symbol_rate_hz;
cfg.waveform.decimation = divider;
end

function desired = desired_for_preview(route, levels, preview)
desired = struct('dac_mode', 'FOUR', 'rdiv', preview.rdiv, ...
    'raster_hz', preview.awg_raster_hz, 'memory_mode', 'EXT', ...
    'segment', 1, 'sample_count', preview.waveform_sample_count, ...
    'padded_sample_count', preview.padded_sample_count, ...
    'amplitude_vpp', levels.amplitude_vpp, 'offset_v', levels.offset_v, ...
    'route_channels', route.awg_channels, ...
    'route_columns', route.waveform_columns, ...
    'channel_memory_modes', {{'EXT','EXT','INT','INT'}});
end

function sequence = build_sequence(previews, repeats)
template = empty_trial();
sequence = repmat(template, 1, 2*repeats);
index = 0;
for pair_index = 1:repeats
    for preview_index = 1:numel(previews)
        index = index + 1;
        preview = previews(preview_index);
        sequence(index) = template;
        sequence(index).trial_index = index;
        sequence(index).pair_index = pair_index;
        sequence(index).rdiv = preview.rdiv;
        sequence(index).trial_name = sprintf('%02d_%s', index, preview.rdiv);
        sequence(index).planned_waveform_sample_rate_hz = ...
            preview.waveform_sample_rate_hz;
        sequence(index).planned_waveform_sample_count = ...
            preview.waveform_sample_count;
        sequence(index).planned_padded_sample_count = ...
            preview.padded_sample_count;
        sequence(index).planned_awg_samples_per_symbol = ...
            preview.awg_samples_per_symbol;
        sequence(index).planned_waveform_hashes = preview.waveform_hashes;
        sequence(index).planned_desired = preview.desired;
        sequence(index).status = 'pending';
    end
end
end

function run_dir = create_comparison_run_dir(cfg, selector, options)
requested = selected_run_path(selector, options);
if ~isempty(requested)
    run_dir = requested;
    if isfolder(run_dir)
        error('msiq:traditionalRdiv:RunDirectoryExists', ...
            'Comparison run directory already exists: %s.', run_dir);
    end
end
run = msiq.create_output_run(cfg,'measurement','rdiv_compare',requested);
run_dir = run.OutputDir;
end

function path = selected_run_path(selector, options)
path = '';
if ischar(selector) || (isstring(selector) && isscalar(selector))
    path = char(string(selector));
end
if isempty(path) && isfield(options, 'run_dir') && ~isempty(options.run_dir)
    path = char(string(options.run_dir));
end
end

function persist_comparison_plan(plan)
Result_Atomic_Write_Json(msiq.artifact_path( ...
    plan.run_dir, 'comparison_plan.json', 'write'), plan_for_json(plan));
save(msiq.artifact_path(plan.run_dir, 'comparison_plan.mat', 'write'), ...
    'plan', '-v7.3');
end

function public = plan_for_json(plan)
keep = {'schema_version','run_id','run_dir','diagnostics_dir','created_at', ...
    'route','repeats_per_rdiv','frame_repetitions','seed','levels', ...
    'minimum_capture_window_s', ...
    'awg_snapshot','awg_snapshot_fingerprint','scope_snapshot', ...
    'scope_snapshot_fingerprint','conditions','sequence', ...
    'global_abort_per_trial','global_abort_command', ...
    'required_initial_output_mask','confirmation_nonce', ...
    'required_confirmation','plan_hash'};
public = struct();
for index = 1:numel(keep)
    public.(keep{index}) = plan.(keep{index});
end
end

function result = initial_result(plan)
result = struct('schema_version', '1.0', 'status', 'planned', ...
    'run_id', plan.run_id, 'run_dir', plan.run_dir, ...
    'diagnostics_dir', plan.diagnostics_dir, 'plan_hash', plan.plan_hash, ...
    'route', plan.route, 'seed', plan.seed, 'levels', plan.levels, ...
    'minimum_capture_window_s', plan.minimum_capture_window_s, ...
    'awg_baseline', plan.awg_snapshot, 'scope_baseline', plan.scope_snapshot, ...
    'trials', plan.sequence, 'failure', struct(), ...
    'final_stop', struct(), 'conclusion', struct(), ...
    'dashboard_path', fullfile(plan.run_dir, 'overview.png'));
end

function [awg_state, scope_state] = verify_current_baseline(cfg, route, plan, expected_awg_fingerprint)
awg = msiq.traditional_tx('awg_status', [], struct('cfg_override', cfg));
awg_state = awg.state;
if ~strcmp(awg_fingerprint(awg_state), char(string(expected_awg_fingerprint)))
    error('msiq:traditionalRdiv:AwgStateDrift', ...
        'AWG state drifted from the approved comparison state.');
end
scope = read_scope(cfg, route);
scope_state = scope.scope;
if ~strcmp(scope_fingerprint(scope_state), ...
        char(string(plan.scope_snapshot_fingerprint)))
    error('msiq:traditionalRdiv:ScopeStateDrift', ...
        'LeCroy settings drifted from the comparison baseline.');
end
end

function scope = read_scope(cfg, route)
scope = msiq.traditional_rx('scope_status', [], struct( ...
    'cfg_override', cfg, 'route', route.name));
end

function require_all_outputs_off(state)
if ~isfield(state, 'outputs') || numel(state.outputs) ~= 4 || any(state.outputs)
    error('msiq:traditionalRdiv:OutputsActive', ...
        ['DIV2/DIV4 comparison requires AWG CH1-CH4 to be OFF before ', ...
        'the batch plan is created.']);
end
end

function verify_trial_readback(state, trial, ~)
if ~isfield(state, 'outputs') || ~all(state.outputs(1:2)) || ...
        any(state.outputs(3:4))
    error('msiq:traditionalRdiv:OutputReadback', ...
        'Trial %d output mask is not [1 1 0 0].', trial.trial_index);
end
desired = trial.planned_desired;
if ~strcmpi(state.dac_mode, 'FOUR') || ...
        ~strcmpi(state.rdiv, trial.rdiv) || ...
        ~isfinite(state.raster_hz) || abs(state.raster_hz-65e9) > 1
    error('msiq:traditionalRdiv:PublicReadback', ...
        'Trial %d public AWG settings do not match the planned condition.', ...
        trial.trial_index);
end
actual_modes = upper(string({state.traces.memory_mode}));
expected_modes = upper(string(desired.channel_memory_modes));
if any(actual_modes ~= expected_modes)
    error('msiq:traditionalRdiv:MemoryTopology', ...
        'Trial %d is not EXT/EXT/INT/INT.', trial.trial_index);
end
for channel = 1:2
    trace = state.traces(channel);
    if ~strcmpi(trace.memory_mode, 'EXT') || ...
            trace.selected_segment ~= desired.segment || ...
            trace.segment ~= desired.segment || ...
            trace.length ~= desired.padded_sample_count
        error('msiq:traditionalRdiv:SegmentReadback', ...
            'Trial %d selected segment or length does not match.', trial.trial_index);
    end
end
end

function metrics = extract_metrics(demod, tx_plan)
if ~isfield(demod, 'pairs') || isempty(demod.pairs) || ...
        ~strcmpi(demod.pairs(1).status, 'decoded')
    error('msiq:traditionalRdiv:Metrics', ...
        'Decoded trial does not contain a primary I/Q result.');
end
decoded = demod.pairs(1).decoded;
if ~isfield(decoded, 'primary_streams') || isempty(decoded.primary_streams)
    error('msiq:traditionalRdiv:Metrics', ...
        'Decoded trial does not contain primary stream metrics.');
end
stream = decoded.primary_streams(1);
fec = field_or(stream, 'fec', struct());
sync = field_or(decoded, 'synchronization', struct());
metrics = empty_metrics();
metrics.sync_ok = logical(field_or(decoded, 'sync_ok', false));
metrics.sync_metric = numeric_or(field_or(sync, 'sync_metric', NaN), NaN);
metrics.sro_ppm = numeric_or(field_or(sync, 'sro_ppm', NaN), NaN);
metrics.cfo_hz = reported_cfo(sync);
metrics.pre_fec_bit_error_count = numeric_or( ...
    field_or(fec, 'pre_fec_bit_error_count', NaN), NaN);
metrics.pre_fec_bit_count = numeric_or( ...
    field_or(fec, 'pre_fec_bit_count', NaN), NaN);
metrics.post_fec_bit_error_count = numeric_or( ...
    field_or(fec, 'post_fec_bit_error_count', NaN), NaN);
metrics.post_fec_bit_count = numeric_or( ...
    field_or(fec, 'post_fec_bit_count', NaN), NaN);
metrics.block_error_count = numeric_or( ...
    field_or(fec, 'block_error_count', field_or(stream, 'block_error_count', NaN)), NaN);
metrics.block_count = numeric_or( ...
    field_or(fec, 'block_count', field_or(stream, 'block_count', NaN)), NaN);
metrics.pre_fec_ber = ratio_or(metrics.pre_fec_bit_error_count, ...
    metrics.pre_fec_bit_count, field_or(stream, 'pre_fec_ber', NaN));
metrics.post_fec_ber = ratio_or(metrics.post_fec_bit_error_count, ...
    metrics.post_fec_bit_count, field_or(stream, 'post_fec_ber', NaN));
metrics.bler = ratio_or(metrics.block_error_count, metrics.block_count, ...
    field_or(stream, 'bler', NaN));
metrics.evm_rms = numeric_or(field_or(stream, 'evm_rms', NaN), NaN);
metrics.mer_db = numeric_or(field_or(stream, 'mer_db', NaN), NaN);
metrics.decoder_pass = logical(field_or(decoded, 'pass', false));
metrics.waveform_id = char(string(field_or(tx_plan, 'waveform_id', '')));
metrics.waveform_hash = strjoin(cellstr(string( ...
    field_or(tx_plan, 'waveform_hashes', {}))), ';');
end

function stopped = stop_selected(cfg, route)
stopped = msiq.traditional_tx('awg_stop', [], struct( ...
    'cfg_override', cfg, 'route', route.name));
end

function cleanup_stop(cfg, route)
try
    stop_selected(cfg, route);
catch
end
end

function cfg = invoke_mock_hook(options, phase, index, cfg, plan)
if ~isfield(options, 'mock_hook') || isempty(options.mock_hook)
    return;
end
if ~isfield(cfg.instrument, 'awg') || ~isfield(cfg.instrument.awg, 'mock') || ...
        ~logical(cfg.instrument.awg.mock) || ...
        ~isfield(cfg.instrument, 'scope') || ~isfield(cfg.instrument.scope, 'mock') || ...
        ~logical(cfg.instrument.scope.mock)
    error('msiq:traditionalRdiv:MockHook', ...
        'mock_hook is accepted only when both instruments are mock sessions.');
end
hook = options.mock_hook;
if ~isa(hook, 'function_handle')
    error('msiq:traditionalRdiv:MockHook', ...
        'mock_hook must be a function handle.');
end
updated = hook(phase, index, cfg, plan);
if ~isempty(updated)
    cfg = updated;
end
end

function persist_comparison_result(plan, result)
result.conclusion = comparison_conclusion(result.trials, result.status);
save(msiq.artifact_path(plan.run_dir, 'comparison_result.mat', 'write'), ...
    'result', '-v7.3');
Result_Atomic_Write_Json(msiq.artifact_path( ...
    plan.run_dir, 'comparison_result.json', 'write'), result_for_json(result));
write_metrics_csv(msiq.artifact_path( ...
    plan.run_dir, 'comparison_metrics.csv', 'write'), result.trials);
write_observations(plan, result.trials);
try
    msiq.plotting.rdiv_compare_dashboard(result.dashboard_path, plan, result);
catch dashboard_exception
    result.dashboard_warning = dashboard_exception.message;
end
end

function write_observations(plan, trials)
run = struct('OutputDir',plan.run_dir,'DataDir',fullfile(plan.run_dir,'data'), ...
    'SummaryPath',fullfile(plan.run_dir,'summary.csv'), ...
    'FullSummaryPath',fullfile(plan.run_dir,'data','observations.csv'));
seen = [];
if ~isfile(run.SummaryPath)
    Result_Summary_Initialize(run, {'序号','RDIV','Channel','EVM','MER', ...
        'pre-FEC BER','post-FEC BER','BLER','状态'}, ...
        {'-','-','-','%','dB','-','-','-','-'});
else
    previous = readcell(run.FullSummaryPath,'NumHeaderLines',2);
    if ~isempty(previous), seen = cell2mat(previous(:,1)); end
end
for k = 1:numel(trials)
    trial = trials(k);
    if ismember(trial.status, {'planned','pending','running'}) || ...
            ismember(trial.trial_index,seen), continue; end
    value = field_or(trial,'metrics',empty_metrics());
    Result_Summary_Append(run, {trial.trial_index,trial.rdiv,plan.route.name, ...
        100*value.evm_rms,value.mer_db,value.pre_fec_ber,value.post_fec_ber, ...
        value.bler,trial.status});
end
end

function public = result_for_json(result)
public = result;
if isfield(public, 'final_stop') && isstruct(public.final_stop) && ...
        isfield(public.final_stop, 'state')
    public.final_stop = struct('status', field_or(public.final_stop, 'status', ''), ...
        'output_mask', field_or(public.final_stop, 'output_mask', []), ...
        'state_fingerprint', field_or(public.final_stop, 'state_fingerprint', ''));
end
end

function write_metrics_csv(path, trials)
fid = Result_Open_File_Retry(path, 'w', 'n', 'UTF-8');
cleanup = onCleanup(@() fclose(fid));
header = ['trial_index,pair_index,rdiv,status,sync_ok,sync_metric,sro_ppm,cfo_hz,', ...
    'pre_fec_bit_error_count,pre_fec_bit_count,pre_fec_ber,', ...
    'post_fec_bit_error_count,post_fec_bit_count,post_fec_ber,', ...
    'block_error_count,block_count,bler,evm_rms,mer_db,decoder_pass,', ...
    'waveform_hash,tx_run_dir,rx_run_dir,error_identifier,error_message'];
fprintf(fid, '%s\n', header);
for index = 1:numel(trials)
    trial = trials(index);
    metrics = field_or(trial, 'metrics', empty_metrics());
    row = {number_text(trial.trial_index), number_text(trial.pair_index), ...
        csv_text(trial.rdiv), csv_text(trial.status), ...
        number_text(metrics.sync_ok), number_text(metrics.sync_metric), ...
        number_text(metrics.sro_ppm), number_text(metrics.cfo_hz), ...
        number_text(metrics.pre_fec_bit_error_count), ...
        number_text(metrics.pre_fec_bit_count), number_text(metrics.pre_fec_ber), ...
        number_text(metrics.post_fec_bit_error_count), ...
        number_text(metrics.post_fec_bit_count), number_text(metrics.post_fec_ber), ...
        number_text(metrics.block_error_count), number_text(metrics.block_count), ...
        number_text(metrics.bler), number_text(metrics.evm_rms), ...
        number_text(metrics.mer_db), number_text(metrics.decoder_pass), ...
        csv_text(metrics.waveform_hash), csv_text(trial.tx_run_dir), ...
        csv_text(trial.rx_run_dir), csv_text(trial.error_identifier), ...
        csv_text(trial.error_message)};
    fprintf(fid, '%s\n', strjoin(row, ','));
end
clear cleanup;
end

function write_report(path, plan, result)
fid = Result_Open_File_Retry(path, 'w', 'n', 'UTF-8');
cleanup = onCleanup(@() fclose(fid));
conclusion = comparison_conclusion(result.trials, result.status);
fprintf(fid, '# DIV2/DIV4 传统 16QAM 回环对比\n\n');
fprintf(fid, '- 状态：%s\n', result.status);
fprintf(fid, '- 路由：%s（CH1=I，CH2=Q）\n', plan.route.name);
fprintf(fid, '- 固定条件：FOUR；CH1/CH2=EXT；CH3/CH4=INT；65 GSa/s raster；0.2 Vpp / 0 V（或 plan 中给定电平）。\n');
fprintf(fid, '- 固定 seed：%d；顺序：DIV2、DIV4 重复 %d 组。\n', ...
    plan.seed, plan.repeats_per_rdiv);
fprintf(fid, '- 每个 AWG 段的逻辑帧重复数：%d（重复帧不增加 payload 信息）。\n', ...
    plan.frame_repetitions);
fprintf(fid, '- 最低公共物理时间窗：%.4f us。\n\n', ...
    plan.minimum_capture_window_s*1e6);
fprintf(fid, '## 每轮记录\n\n');
fprintf(fid, '|轮次|配对|RDIV|状态|pre-FEC error/bit|post-FEC error/bit|BLER|EVM|MER|\n');
fprintf(fid, '|---:|---:|---|---|---:|---:|---:|---:|---:|\n');
for index = 1:numel(result.trials)
    trial = result.trials(index);
    metrics = field_or(trial, 'metrics', empty_metrics());
    fprintf(fid, '|%d|%d|%s|%s|%s/%s|%s/%s|%s|%s|%s|\n', ...
        trial.trial_index, trial.pair_index, trial.rdiv, trial.status, ...
        number_text(metrics.pre_fec_bit_error_count), ...
        number_text(metrics.pre_fec_bit_count), ...
        number_text(metrics.post_fec_bit_error_count), ...
        number_text(metrics.post_fec_bit_count), number_text(metrics.bler), ...
        number_text(metrics.evm_rms), number_text(metrics.mer_db));
end
fprintf(fid, '\n## 结论\n\n%s\n', conclusion.message);
if isfield(result, 'failure') && ~isempty(field_or(result.failure, 'error_message', ''))
    fprintf(fid, '\n## 中止原因\n\n`%s`\n', result.failure.error_message);
end
clear cleanup;
end

function conclusion = comparison_conclusion(trials, status, statistics_requested)
if nargin < 3 || ~statistics_requested
    conclusion = struct('status',status,'winner','not_requested', ...
        'message','逐次结果已保留，未计算跨次统计。');
    return;
end
metrics = decoded_trials(trials);
conclusion = struct('status', status, 'winner', 'unavailable', ...
    'message', '', 'div2', aggregate_metrics(metrics, 'DIV2'), ...
    'div4', aggregate_metrics(metrics, 'DIV4'), ...
    'paired_mer_delta_db', [], 'paired_evm_delta', [], ...
    'mer_direction_consistent', false);
if ~strcmpi(status, 'completed')
    conclusion.message = sprintf('对比未完成（状态：%s），不生成模式优胜结论。', status);
    return;
end
if isempty(metrics)
    conclusion.message = '没有可用于结论的成功解调记录。';
    return;
end

div2 = conclusion.div2;
div4 = conclusion.div4;
if div2.success_count ~= div4.success_count
    if div2.success_count > div4.success_count
        winner = 'DIV2';
        text = sprintf('解调成功次数：DIV2 更多（%d vs %d）。', ...
            div2.success_count, div4.success_count);
    else
        winner = 'DIV4';
        text = sprintf('解调成功次数：DIV4 更多（%d vs %d）。', ...
            div4.success_count, div2.success_count);
    end
    conclusion.winner = winner;
    conclusion.message = text;
    return;
end
if counts_comparable(div2.post_fec_bit_error_count, div4.post_fec_bit_error_count) && ...
        div2.post_fec_bit_error_count ~= div4.post_fec_bit_error_count
    [winner, text] = lower_is_better(div2.post_fec_bit_error_count, ...
        div4.post_fec_bit_error_count, '聚合 post-FEC 错误比特数');
    conclusion.winner = winner;
    conclusion.message = text;
    return;
end
if counts_comparable(div2.block_error_count, div4.block_error_count) && ...
        div2.block_error_count ~= div4.block_error_count
    [winner, text] = lower_is_better(div2.block_error_count, ...
        div4.block_error_count, '聚合 block error 数');
    conclusion.winner = winner;
    conclusion.message = text;
    return;
end
if finite_difference(div2.bler, div4.bler, 1e-15)
    [winner, text] = lower_is_better(div2.bler, div4.bler, '聚合 BLER');
    conclusion.winner = winner;
    conclusion.message = text;
    return;
end
if counts_comparable(div2.pre_fec_bit_error_count, div4.pre_fec_bit_error_count) && ...
        div2.pre_fec_bit_error_count ~= div4.pre_fec_bit_error_count
    [winner, text] = lower_is_better(div2.pre_fec_bit_error_count, ...
        div4.pre_fec_bit_error_count, '聚合 pre-FEC 错误比特数');
    conclusion.winner = winner;
    conclusion.message = text;
    return;
end
if finite_difference(div2.pre_fec_ber, div4.pre_fec_ber, 1e-15)
    [winner, text] = lower_is_better(div2.pre_fec_ber, div4.pre_fec_ber, ...
        '聚合 pre-FEC BER');
    conclusion.winner = winner;
    conclusion.message = text;
    return;
end

[mer_delta, evm_delta] = paired_deltas(metrics);
conclusion.paired_mer_delta_db = mer_delta;
conclusion.paired_evm_delta = evm_delta;
finite_mer = mer_delta(isfinite(mer_delta));
positive = all(finite_mer > 0.05);
negative = all(finite_mer < -0.05);
conclusion.mer_direction_consistent = ~isempty(finite_mer) && (positive || negative);
if ~conclusion.mer_direction_consistent
    conclusion.winner = 'no_clear_advantage';
    conclusion.message = ['BER 层面持平，但五组相邻配对的 MER 差异方向不一致或不足 ', ...
        '0.05 dB；无明确优势。'];
    return;
end
if positive && (isempty(evm_delta) || all(evm_delta(isfinite(evm_delta)) <= 0))
    conclusion.winner = 'DIV2';
    conclusion.message = sprintf(['BER 层面持平；DIV2 在每个有效配对中 MER 均更高，', ...
        '中位差 %.3f dB。'], median(finite_mer));
elseif negative && (isempty(evm_delta) || all(evm_delta(isfinite(evm_delta)) >= 0))
    conclusion.winner = 'DIV4';
    conclusion.message = sprintf(['BER 层面持平；DIV4 在每个有效配对中 MER 均更高，', ...
        '中位差 %.3f dB。'], median(-finite_mer));
else
    conclusion.winner = 'no_clear_advantage';
    conclusion.message = ['BER 与 MER 的方向没有得到 EVM 一致支持；', ...
        '无明确优势。'];
end
end

function metrics = decoded_trials(trials)
base = empty_metrics();
base.rdiv = '';
base.pair_index = NaN;
base.trial_index = NaN;
metrics = repmat(base, 0, 1);
for index = 1:numel(trials)
    if strcmpi(field_or(trials(index), 'status', ''), 'decoded') && ...
            isstruct(field_or(trials(index), 'metrics', struct()))
        value = trials(index).metrics;
        value.rdiv = trials(index).rdiv;
        value.pair_index = trials(index).pair_index;
        value.trial_index = trials(index).trial_index;
        metrics = [metrics, value]; %#ok<AGROW>
    end
end
end

function aggregate = aggregate_metrics(metrics, rdiv)
selected = metrics(strcmpi({metrics.rdiv}, rdiv));
aggregate = struct('count', numel(selected), 'success_count', numel(selected), ...
    'pre_fec_bit_error_count', sum_metric(selected, 'pre_fec_bit_error_count'), ...
    'pre_fec_bit_count', sum_metric(selected, 'pre_fec_bit_count'), ...
    'post_fec_bit_error_count', sum_metric(selected, 'post_fec_bit_error_count'), ...
    'post_fec_bit_count', sum_metric(selected, 'post_fec_bit_count'), ...
    'block_error_count', sum_metric(selected, 'block_error_count'), ...
    'block_count', sum_metric(selected, 'block_count'), ...
    'pre_fec_ber', NaN, 'post_fec_ber', NaN, 'bler', NaN, ...
    'mer_median_db', median_metric(selected, 'mer_db'), ...
    'mer_std_db', std_metric(selected, 'mer_db'), ...
    'evm_median', median_metric(selected, 'evm_rms'), ...
    'evm_std', std_metric(selected, 'evm_rms'));
aggregate.pre_fec_ber = ratio_or(aggregate.pre_fec_bit_error_count, ...
    aggregate.pre_fec_bit_count, NaN);
aggregate.post_fec_ber = ratio_or(aggregate.post_fec_bit_error_count, ...
    aggregate.post_fec_bit_count, NaN);
aggregate.bler = ratio_or(aggregate.block_error_count, ...
    aggregate.block_count, NaN);
end

function [mer_delta, evm_delta] = paired_deltas(metrics)
mer_delta = nan(1, 5);
evm_delta = nan(1, 5);
for pair_index = 1:5
    div2 = metrics(strcmpi({metrics.rdiv}, 'DIV2') & ...
        [metrics.pair_index] == pair_index);
    div4 = metrics(strcmpi({metrics.rdiv}, 'DIV4') & ...
        [metrics.pair_index] == pair_index);
    if numel(div2) == 1 && numel(div4) == 1
        mer_delta(pair_index) = div2.mer_db-div4.mer_db;
        evm_delta(pair_index) = div2.evm_rms-div4.evm_rms;
    end
end
end

function [winner, text] = lower_is_better(div2, div4, criterion)
if div2 < div4
    winner = 'DIV2';
    text = sprintf('%s：DIV2 更低（%.6g vs %.6g）。', criterion, div2, div4);
else
    winner = 'DIV4';
    text = sprintf('%s：DIV4 更低（%.6g vs %.6g）。', criterion, div4, div2);
end
end

function value = sum_metric(metrics, field)
if isempty(metrics)
    value = NaN;
    return;
end
values = [metrics.(field)];
if any(~isfinite(values))
    value = NaN;
else
    value = sum(values);
end
end

function value = median_metric(metrics, field)
if isempty(metrics)
    value = NaN;
    return;
end
values = [metrics.(field)];
values = values(isfinite(values));
if isempty(values)
    value = NaN;
else
    value = median(values);
end
end

function value = std_metric(metrics, field)
if isempty(metrics)
    value = NaN;
    return;
end
values = [metrics.(field)];
values = values(isfinite(values));
if numel(values) < 2
    value = NaN;
else
    value = std(values, 0);
end
end

function yes = counts_comparable(a, b)
yes = isfinite(a) && isfinite(b);
end

function yes = finite_difference(a, b, tolerance)
yes = isfinite(a) && isfinite(b) && abs(a-b) > tolerance;
end

function overlap = minimum_overlap(summary)
overlap = NaN;
pairs = field_or(summary, 'pair_summaries', {});
if isstruct(pairs)
    pairs = num2cell(pairs);
elseif ~iscell(pairs)
    return;
end
values = nan(1, numel(pairs));
for index = 1:numel(pairs)
    values(index) = numeric_or(field_or(pairs{index}, ...
        'overlap_duration_s', NaN), NaN);
end
values = values(isfinite(values));
if ~isempty(values)
    overlap = min(values);
end
end

function value = reported_cfo(sync)
value = numeric_or(field_or(sync, 'coarse_cfo_hz', NaN), NaN);
if isstruct(sync) && isfield(sync, 'total_cfo_hz') && ...
        isfinite(numeric_or(sync.total_cfo_hz, NaN))
    value = numeric_or(sync.total_cfo_hz, NaN);
end
end

function fingerprint = awg_fingerprint(state)
canonical = struct('dac_mode', char(string(field_or(state, 'dac_mode', ''))), ...
    'rdiv', char(string(field_or(state, 'rdiv', ''))), ...
    'raster_hz', numeric_or(field_or(state, 'raster_hz', NaN), NaN), ...
    'outputs', logical(field_or(state, 'outputs', false(1,4))), ...
    'traces', field_or(state, 'traces', struct([])));
fingerprint = msiq.sha256_bytes(jsonencode(canonical));
end

function fingerprint = scope_fingerprint(scope)
channels = field_or(scope, 'channels', struct([]));
canonical_channels = repmat(struct('channel', '', 'trace_state', '', ...
    'vertical_scale_raw', '', 'offset_raw', ''), 1, numel(channels));
for index = 1:numel(channels)
    canonical_channels(index) = struct( ...
        'channel', char(string(field_or(channels(index), 'channel', ''))), ...
        'trace_state', char(string(field_or(channels(index), 'trace_state', ''))), ...
        'vertical_scale_raw', char(string(field_or(channels(index), ...
            'vertical_scale_raw', ''))), ...
        'offset_raw', char(string(field_or(channels(index), 'offset_raw', ''))));
end
preprocessing = field_or(scope, 'preprocessing', struct());
records = field_or(preprocessing, 'channels', struct([]));
canonical_preprocessing = repmat(struct('channel', '', 'status', '', ...
    'interpolation', '', 'average_sweeps', '', 'enhance_resolution', '', ...
    'optimize_group_delay', ''), 1, numel(records));
for index = 1:numel(records)
    raw = field_or(records(index), 'raw', struct());
    canonical_preprocessing(index) = struct( ...
        'channel', char(string(field_or(records(index), 'channel', ''))), ...
        'status', char(string(field_or(records(index), 'status', ''))), ...
        'interpolation', char(string(field_or(raw, 'interpolation', ''))), ...
        'average_sweeps', char(string(field_or(raw, 'average_sweeps', ''))), ...
        'enhance_resolution', char(string(field_or(raw, 'enhance_resolution', ''))), ...
        'optimize_group_delay', char(string(field_or(raw, 'optimize_group_delay', ''))));
end
canonical = struct('idn', char(string(field_or(scope, 'idn', ''))), ...
    'timebase_raw', char(string(field_or(scope, 'timebase_raw', ''))), ...
    'sample_rate_raw', char(string(field_or(scope, 'sample_rate_raw', ''))), ...
    'sample_rate_source', char(string(field_or(scope, 'sample_rate_source', ''))), ...
    'memory_depth_raw', char(string(field_or(scope, 'memory_depth_raw', ''))), ...
    'channels', canonical_channels, 'preprocessing', canonical_preprocessing);
fingerprint = msiq.sha256_bytes(jsonencode(canonical));
end

function phrase = batch_confirmation_phrase(plan)
digest = msiq.sha256_bytes(plan.awg_snapshot_fingerprint, ...
    plan.scope_snapshot_fingerprint, jsonencode(plan.sequence), ...
    plan.confirmation_nonce);
phrase = sprintf('FORCE RDIV COMPARISON PAIR_A_CH1_CH2 %s', ...
    upper(digest(1:12)));
end

function validate_plan(plan)
required = {'run_dir','diagnostics_dir','route','cfg','sequence','conditions', ...
    'awg_snapshot_fingerprint','scope_snapshot_fingerprint', ...
    'required_confirmation','plan_hash','minimum_capture_window_s'};
for index = 1:numel(required)
    if ~isfield(plan, required{index})
        error('msiq:traditionalRdiv:PlanFormat', ...
            'Comparison plan is missing %s.', required{index});
    end
end
if numel(plan.sequence) ~= 10 || ~all(strcmpi({plan.sequence.rdiv}, ...
        {'DIV2','DIV4','DIV2','DIV4','DIV2','DIV4','DIV2','DIV4','DIV2','DIV4'}))
    error('msiq:traditionalRdiv:PlanSequence', ...
        'Comparison plan must contain the fixed DIV2/DIV4 x5 sequence.');
end
end

function trial = empty_trial()
trial = struct('trial_index', NaN, 'pair_index', NaN, 'rdiv', '', ...
    'trial_name', '', 'status', 'pending', 'started_at', '', ...
    'finished_at', '', 'stopped_at', '', ...
    'planned_waveform_sample_rate_hz', NaN, ...
    'planned_waveform_sample_count', NaN, 'planned_padded_sample_count', NaN, ...
    'planned_awg_samples_per_symbol', NaN, ...
    'planned_waveform_hashes', {{}}, 'planned_desired', struct(), ...
    'tx_run_dir', '', 'rx_run_dir', '', 'tx_plan_hash', '', ...
    'tx_artifact_prefix','','rx_artifact_prefix','', ...
    'tx_required_confirmation', '', ...
    'waveform_hashes', {{}}, 'capture_status', '', 'demod_status', '', ...
    'capture_physical_window', struct(), 'awg_before', struct(), ...
    'awg_after_apply', struct(), 'awg_after_stop', struct(), ...
    'scope_before', struct(), 'scope_before_capture', struct(), ...
    'metrics', empty_metrics(), 'error_identifier', '', 'error_message', '');
end

function metrics = empty_metrics()
metrics = struct('sync_ok', false, 'sync_metric', NaN, 'sro_ppm', NaN, ...
    'cfo_hz', NaN, 'pre_fec_bit_error_count', NaN, ...
    'pre_fec_bit_count', NaN, 'pre_fec_ber', NaN, ...
    'post_fec_bit_error_count', NaN, 'post_fec_bit_count', NaN, ...
    'post_fec_ber', NaN, 'block_error_count', NaN, 'block_count', NaN, ...
    'bler', NaN, 'evm_rms', NaN, 'mer_db', NaN, 'decoder_pass', false, ...
    'waveform_id', '', 'waveform_hash', '');
end

function status = failure_result_status(exception)
identifier = lower(char(string(exception.identifier)));
if contains(identifier, 'drift') || contains(identifier, 'capturewindow') || ...
        contains(identifier, 'outputsactive')
    status = 'blocked';
else
    status = 'failed';
end
end

function status = failure_trial_status(exception)
status = failure_result_status(exception);
end

function value = ratio_or(numerator, denominator, fallback)
numerator = numeric_or(numerator, NaN);
denominator = numeric_or(denominator, NaN);
if isfinite(numerator) && isfinite(denominator) && denominator > 0
    value = numerator/denominator;
else
    value = numeric_or(fallback, NaN);
end
end

function value = numeric_or(value, fallback)
if isempty(value) || ~isscalar(value) || ~isfinite(double(value))
    value = fallback;
else
    value = double(value);
end
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end

function text = number_text(value)
if islogical(value) && isscalar(value)
    text = sprintf('%d', value);
    return;
end
value = numeric_or(value, NaN);
if isfinite(value)
    text = sprintf('%.12g', value);
else
    text = '';
end
end

function text = csv_text(value)
text = char(string(value));
text = strrep(text, '"', '""');
text = ['"', text, '"'];
end

function value = timestamp_text()
value = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
end

function value = plan_nonce()
[~, generated] = fileparts(tempname);
value = msiq.sha256_bytes(generated, timestamp_text());
end

function value = last_path_part(path)
[~, value] = fileparts(path);
end
