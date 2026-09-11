function output = traditional_rx(action, selector, options)
%TRADITIONAL_RX Programmatic LeCroy actions for the traditional I/Q loopback.

if nargin < 1 || isempty(action)
    action = 'scope_status';
end
if nargin < 2
    selector = [];
end
if nargin < 3 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:traditionalRx:Options', 'Options must be a scalar struct.');
end
action = lower(char(string(action)));

switch action
    case 'scope_status'
        cfg = load_cfg(options);
        route = msiq.resolve_awg_route(options);
        output = scope_status(cfg, route);
    case 'capture'
        context = capture_context(selector, options);
        output = capture_run(context);
    case 'demod_capture'
        run_dir = run_directory(selector, options);
        context = load_tx_context(run_dir, options);
        context.artifact_prefix = char(string(field_or(options, 'artifact_prefix', '')));
        output = demod_run(context);
    otherwise
        error('msiq:traditionalRx:Action', 'Unknown RX action: %s.', action);
end
end

function cfg = load_cfg(options)
if isfield(options, 'cfg_override') && ~isempty(options.cfg_override)
    cfg = options.cfg_override;
else
    cfg = msiq.build_config('v2_traditional_wz');
end
cfg.waveform.architecture = 'single_complex_stream';
cfg.results_root = fullfile(cfg.project_root, 'measurement');
end

function context = capture_context(selector, options)
if ~has_reference_bundle_option(options)
    run_dir = run_directory(selector, options);
    context = load_tx_context(run_dir, options);
    return;
end

source_path = char(string(options.tx_reference_bundle));
[bundle, source_path] = read_reference_bundle(source_path);
cfg = load_cfg(options);
route_name = char(string(field_or(field_or(bundle, 'route', struct()), ...
    'name', 'portable_reference')));
run_dir = rx_run_directory(selector, options, cfg, route_name);
context = bundle_context(run_dir, cfg, bundle, source_path);
context.artifact_prefix = char(string(field_or(options, 'artifact_prefix', '')));
if isfield(options, 'scope_channels') && ~isempty(options.scope_channels)
    context.route.scope_channels = cellstr(string(options.scope_channels(:).'));
end
destination = msiq.artifact_path(context, 'tx_reference_bundle.mat', 'write');
msiq.save_reference_bundle(destination,bundle,source_path);
context.reference_bundle_path = destination;
[~,local_name,local_ext] = fileparts(destination);
Result_Atomic_Write_Json(msiq.artifact_path(context, ...
    'tx_reference_source.json', 'write'),struct('source_path',source_path, ...
    'local_file',[local_name local_ext], ...
    'sha256',compute_file_sha256(destination)));
end

function context = load_bundle_context(run_dir, options)
source_path = resolve_bundle_path(run_dir, options);
[bundle, source_path] = read_reference_bundle(source_path);
context = bundle_context(run_dir, load_cfg(options), bundle, source_path);
context.artifact_prefix = char(string(field_or(options, 'artifact_prefix', '')));
end

function context = bundle_context(run_dir, cfg, bundle, source_path)
required = {'route','desired','tx_ref','execution'};
for k = 1:numel(required)
    if ~isfield(bundle, required{k})
        error('msiq:traditionalRx:ReferenceBundle', ...
            'Portable reference bundle is missing %s.', required{k});
    end
end
if ~strcmpi(char(string(field_or(bundle.execution, 'status', ''))), 'applied')
    error('msiq:traditionalRx:ReferenceBundleApply', ...
        'Portable reference bundle must describe a successful awg_apply.');
end
if ~strcmpi(char(string(field_or(bundle, 'reference_payload_policy', ''))), ...
        'metrics_only') || ~isfield(bundle.tx_ref, 'frame') || ...
        ~strcmpi(char(string(bundle.tx_ref.frame.reference_payload_policy)), ...
        'metrics_only')
    error('msiq:traditionalRx:ReferenceBundlePolicy', ...
        'Portable reference bundle must retain the metrics_only policy.');
end
if isfield(bundle, 'dsp_config') && isstruct(bundle.dsp_config)
    if isfield(bundle.dsp_config, 'waveform')
        cfg.waveform = bundle.dsp_config.waveform;
    end
    if isfield(bundle.dsp_config, 'receiver')
        cfg.receiver = bundle.dsp_config.receiver;
    end
end
[cfg, tx_ref] = apply_reference_compatibility(cfg, bundle.tx_ref, bundle);
cfg.waveform.architecture = 'single_complex_stream';
context = struct('run_dir', run_dir, 'route', bundle.route, ...
    'diagnostics_dir', fullfile(run_dir, 'data'), ...
    'desired', bundle.desired, 'cfg', cfg, 'tx_ref', tx_ref, ...
    'awg_credentials', bundle.execution, ...
    'scope_status', saved_scope_status(run_dir), ...
    'reference_bundle_path', source_path, 'portable_reference', true, ...
    'reference_bundle', bundle);
end

function [bundle, path] = read_reference_bundle(path)
if ~(ischar(path) || (isstring(path) && isscalar(path))) || ...
        isempty(char(string(path))) || ~isfile(char(string(path)))
    error('msiq:traditionalRx:ReferenceBundle', ...
        'Specify an existing tx_reference_bundle.mat file.');
end
path = char(string(path));
loaded = msiq.load_reference_bundle(path);
if ~isfield(loaded, 'bundle') || ~isstruct(loaded.bundle)
    error('msiq:traditionalRx:ReferenceBundle', ...
        'Reference bundle %s does not contain a bundle struct.', path);
end
bundle = loaded.bundle;
end

function [cfg, tx_ref] = apply_reference_compatibility(cfg, tx_ref, bundle)
% Old portable bundles predate configurable modulation and I/Q calibration.
cfg = msiq.fec.apply_reference(cfg, tx_ref);
frame = field_or(tx_ref, 'frame', struct());
waveform = cfg.waveform;
waveform.modulation_order = field_or(bundle, 'modulation_order', ...
    field_or(tx_ref, 'modulation_order', ...
    field_or(frame, 'modulation_order', field_or(waveform, ...
    'modulation_order', 16))));
waveform.master_sample_rate_hz = field_or(frame, ...
    'master_sample_rate_hz', field_or(waveform, ...
    'master_sample_rate_hz', 65e9));
waveform.master_samples_per_symbol = field_or(frame, ...
    'master_samples_per_symbol', field_or(waveform, ...
    'master_samples_per_symbol', 31));
waveform.selected_up = field_or(waveform, 'selected_up', ...
    waveform.master_samples_per_symbol);
waveform.selected_up = waveform.master_samples_per_symbol;
waveform.awg_sample_rate_hz = field_or(frame, 'awg_sample_rate_hz', ...
    field_or(waveform, 'awg_sample_rate_hz', ...
    waveform.master_sample_rate_hz/4));
waveform.symbol_rate_hz = field_or(frame, 'symbol_rate_hz', ...
    waveform.master_sample_rate_hz / waveform.selected_up);
waveform.occupied_bandwidth_hz = field_or(frame, ...
    'occupied_bandwidth_hz', waveform.symbol_rate_hz*(1+waveform.rolloff));
waveform.shaping_samples_per_symbol = field_or(frame, ...
    'shaping_samples_per_symbol', field_or(waveform, ...
    'shaping_samples_per_symbol', round(waveform.selected_up)));
waveform.rate_generation_mode = field_or(waveform, ...
    'rate_generation_mode', 'legacy_integer_up');
waveform.awg_samples_per_symbol = waveform.awg_sample_rate_hz / ...
    waveform.symbol_rate_hz;
waveform.decimation = waveform.master_sample_rate_hz / ...
    waveform.awg_sample_rate_hz;
waveform.bits_per_symbol = log2(waveform.modulation_order);
waveform.sync_length_symbols = field_or(frame, 'sync_length', ...
    field_or(waveform, 'sync_length_symbols', 63));
waveform.sync_repeats = field_or(frame, 'sync_repeats', ...
    field_or(waveform, 'sync_repeats', 4));
waveform.training_symbols = field_or(frame, 'training_length', ...
    field_or(waveform, 'training_symbols', 2048));
waveform.pilot_interval_symbols = field_or(frame, ...
    'pilot_interval_symbols', field_or(waveform, ...
    'pilot_interval_symbols', 32));
waveform.guard_symbols = field_or(frame, 'guard_symbols', ...
    field_or(waveform, 'guard_symbols', 64));
waveform.ldpc_blocks_per_frame = field_or(frame, ...
    'ldpc_blocks_per_frame', field_or(waveform, ...
    'ldpc_blocks_per_frame', 1));
waveform.frame_repetitions = field_or(frame, 'frame_repetitions', ...
    field_or(waveform, 'frame_repetitions', 3));
waveform.q_relative_delay_samples = field_or(waveform, ...
    'q_relative_delay_samples', 0);
waveform.invert_i = logical(field_or(waveform, 'invert_i', false));
waveform.invert_q = logical(field_or(waveform, 'invert_q', false));
cfg.waveform = waveform;
tx_ref.modulation_order = waveform.modulation_order;
frame.modulation_order = waveform.modulation_order;
frame.master_sample_rate_hz = waveform.master_sample_rate_hz;
frame.master_samples_per_symbol = waveform.master_samples_per_symbol;
frame.awg_sample_rate_hz = waveform.awg_sample_rate_hz;
frame.sync_length = waveform.sync_length_symbols;
frame.sync_repeats = waveform.sync_repeats;
frame.training_length = waveform.training_symbols;
frame.pilot_interval_symbols = waveform.pilot_interval_symbols;
frame.guard_symbols = waveform.guard_symbols;
frame.ldpc_blocks_per_frame = waveform.ldpc_blocks_per_frame;
frame.frame_repetitions = waveform.frame_repetitions;
tx_ref.frame = frame;
end

function path = resolve_bundle_path(run_dir, options)
if has_reference_bundle_option(options)
    path = char(string(options.tx_reference_bundle));
else
    location = struct('run_dir',run_dir, ...
        'artifact_prefix',field_or(options,'artifact_prefix',''));
    path = msiq.artifact_path(location, 'tx_reference_bundle.mat', 'read');
    if ~isfile(path)
        pointer = msiq.artifact_path(location,'tx_reference_source.json','read');
        if isfile(pointer)
            reference = jsondecode(fileread(pointer));
            path = reference.source_path;
            if isfield(reference,'local_file')
                path = fullfile(fileparts(pointer),reference.local_file);
            end
            if ~isfile(path) || ~strcmpi(reference.sha256,compute_file_sha256(path))
                error('msiq:traditionalRx:ReferenceChanged', ...
                    'Saved reference is missing or changed: %s.',path);
            end
        end
    end
end
end

function yes = has_reference_bundle_option(options)
yes = isstruct(options) && isfield(options, 'tx_reference_bundle') && ...
    ~isempty(options.tx_reference_bundle);
end

function run_dir = rx_run_directory(selector, options, cfg, route_name)
run_dir = selected_run_path(selector, options);
if isempty(run_dir)
    run = msiq.create_output_run(cfg,'measurement',['manual_rx_' route_name],'');
    run_dir = run.OutputDir;
elseif ~isfolder(run_dir)
    run = msiq.create_output_run(cfg,'measurement',['manual_rx_' route_name],run_dir);
    run_dir = run.OutputDir;
else
    location = struct('run_dir',run_dir, ...
        'artifact_prefix',field_or(options,'artifact_prefix',''));
    if isfile(msiq.artifact_path(location,'raw_capture.mat','read'))
        error('msiq:traditionalRx:CaptureExists','Capture already exists in %s.',run_dir);
    end
end
if ~isfolder(run_dir)
    [ok, message] = mkdir(run_dir);
    if ~ok
        error('msiq:traditionalRx:RunDirectory', ...
            'Cannot create RX run directory %s: %s.', run_dir, message);
    end
end
diagnostics_dir = fullfile(run_dir, 'data');
if ~isfolder(diagnostics_dir)
    [ok, message] = mkdir(diagnostics_dir);
    if ~ok
        error('msiq:traditionalRx:DiagnosticsDirectory', ...
            'Cannot create diagnostics directory %s: %s.', diagnostics_dir, message);
    end
end
end

function scope_status = saved_scope_status(run_dir)
scope_status = struct();
metadata_path = msiq.artifact_path(run_dir, 'capture_metadata.json', 'read');
if ~isfile(metadata_path)
    return;
end
try
    metadata = jsondecode(fileread(metadata_path));
    if isfield(metadata, 'scope_status_before')
        scope_status = metadata.scope_status_before;
    end
catch
    scope_status = struct();
end
end

function output = scope_status(cfg, route)
session = msiq.instruments.open_session('scope', cfg.instrument.scope, 'raw');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
status = read_scope_state(session, route.scope_channels);
output = struct('status', 'ok', 'timestamp', timestamp_text(), ...
    'route', route, 'scope', status);
clear cleanup;
end

function output = capture_run(context)
record_cleanup = onCleanup(@() settle_capture(context));
session = msiq.instruments.open_session('scope', context.cfg.instrument.scope, 'raw');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
configure_runtime_scope(session, context);
before = read_scope_state(session, context.route.scope_channels);
context.scope_status = before;
try
    raw = msiq.instruments.capture_scope_raw(session, context.route.scope_channels);
catch exception
    failure = struct('schema_version', '1.0', 'status', 'capture_failed', ...
        'failed_at', timestamp_text(), 'route', context.route, ...
        'scope_status_before', before, 'error_identifier', exception.identifier, ...
        'error_message', exception.message, ...
        'trigger_restore', 'onCleanup attempted TRMD AUTO');
    Result_Atomic_Write_Json(msiq.artifact_path( ...
        context, 'capture_failure.json', 'write'), failure);
    write_failure_dashboard(context, failure);
    rethrow(exception);
end

function configure_runtime_scope(session, context)
if ~isfield(context.cfg, 'scope_runtime') || ...
        ~isstruct(context.cfg.scope_runtime)
    return;
end
runtime = context.cfg.scope_runtime;
channels = cellstr(string(field_or(runtime, 'channels', ...
    context.route.scope_channels)));
vdiv = double(field_or(runtime, 'vertical_scale_v_per_div', []));
offset = double(field_or(runtime, 'offset_v', []));
timebase = double(field_or(runtime, 'timebase_s', NaN));
if numel(vdiv) ~= numel(channels) || numel(offset) ~= numel(channels)
    error('msiq:traditionalRx:ScopeRuntimeSize', ...
        'Runtime scope settings must match the selected channel count.');
end
for k = 1:numel(channels)
    channel = upper(char(string(channels{k})));
    if ~isfinite(vdiv(k)) || vdiv(k) <= 0 || ~isfinite(offset(k))
        error('msiq:traditionalRx:ScopeRuntimeValue', ...
            'Runtime scope V/div and offset must be finite.');
    end
    msiq.instruments.write_scpi(session, sprintf('%s:VDIV %.15g', ...
        channel, vdiv(k)));
    msiq.instruments.write_scpi(session, sprintf('%s:OFST %.15g', ...
        channel, offset(k)));
end
if ~isfinite(timebase) || timebase <= 0
    error('msiq:traditionalRx:ScopeRuntimeValue', ...
        'Runtime scope timebase must be positive.');
end
msiq.instruments.write_scpi(session, sprintf('TDIV %.15g', timebase));
end
save(msiq.artifact_path(context, 'raw_capture.mat', 'write'), ...
    'raw', '-v7.3');
validation = normalize_capture(raw, context.tx_ref, context.route);
save(msiq.artifact_path(context, 'capture_preparation.mat', 'write'), ...
    'validation', '-v7.3');
metadata = struct('schema_version', '1.0', 'status', ternary(validation.ok, ...
    'captured_ready_for_demod', 'captured_not_ready_for_demod'), ...
    'captured_at', timestamp_text(), 'route', context.route, ...
    'scope_status_before', before, 'physical_window', validation.summary, ...
    'trigger_restore', 'onCleanup attempted TRMD AUTO', ...
    'awg_credentials', context.awg_credentials, ...
    'reference_bundle_path', context.reference_bundle_path, ...
    'portable_reference', context.portable_reference);
Result_Atomic_Write_Json(msiq.artifact_path( ...
    context, 'capture_metadata.json', 'write'), metadata);
dashboard_path = msiq.artifact_path(context, 'fig_rx_dashboard.png', 'write');
dashboard = msiq.plotting.rx_dashboard( ...
    dashboard_path, raw, validation, context, ...
    struct('status', metadata.status, 'pairs', struct([]), 'reason', ''));
output = struct('status', metadata.status, 'run_dir', context.run_dir, ...
    'diagnostics_dir', context.diagnostics_dir, 'dashboard_path', dashboard_path, ...
    'reference_bundle_path', context.reference_bundle_path, ...
    'route', context.route, 'physical_window', validation.summary, ...
    'demod_ready', validation.ok, 'dashboard', dashboard);
finalize_standalone_capture(context, validation, dashboard_path);
clear cleanup;
end

function output = demod_run(context)
raw_path = msiq.artifact_path(context, 'raw_capture.mat', 'read');
if ~isfile(raw_path)
    error('msiq:traditionalRx:RawCapture', ...
        'Missing raw_capture.mat in %s.', context.run_dir);
end
loaded = load(raw_path, 'raw');
validation = normalize_capture(loaded.raw, context.tx_ref, context.route);
analysis_run = [];
if isempty(field_or(context, 'artifact_prefix', ''))
    [context, analysis_run] = analysis_context(context, raw_path);
    analysis_cleanup = onCleanup(@() settle_analysis(analysis_run));
end
if ~validation.ok
    output = struct('status', 'blocked', 'run_dir', context.run_dir, ...
        'diagnostics_dir', context.diagnostics_dir, ...
        'reference_bundle_path', context.reference_bundle_path, ...
        'reason', validation.reason, 'physical_window', validation.summary);
    output.dashboard_path = msiq.artifact_path(context, 'fig_rx_dashboard.png', 'write');
    output.dashboard = msiq.plotting.rx_dashboard( ...
        output.dashboard_path, loaded.raw, validation, context, output);
    Result_Atomic_Write_Json(msiq.artifact_path( ...
        context, 'demod_result.json', 'write'), output);
    save_demod_result(context, output, validation);
    finalize_standalone_demod(analysis_run, output);
    return;
end

results = repmat(empty_pair_result(), 1, numel(validation.pairs));
for k = 1:numel(validation.pairs)
    pair = validation.pairs(k);
    try
        decoded = msiq.decode_capture(pair.raw_for_decode, context.tx_ref, context.cfg);
        results(k).name = pair.name;
        results(k).status = 'decoded';
        results(k).decoded = decoded;
    catch exception
        results(k).name = pair.name;
        results(k).status = 'failed';
        results(k).error_identifier = exception.identifier;
        results(k).error_message = exception.message;
    end
end
status = 'decoded';
if any(~strcmp({results.status}, 'decoded'))
    status = 'failed';
end
output = struct('status', status, 'run_dir', context.run_dir, ...
    'diagnostics_dir', context.diagnostics_dir, ...
    'reference_bundle_path', context.reference_bundle_path, ...
    'physical_window', validation.summary, 'pairs', results);
output.dashboard_path = msiq.artifact_path(context, 'fig_rx_dashboard.png', 'write');
output.dashboard = msiq.plotting.rx_dashboard( ...
    output.dashboard_path, loaded.raw, validation, context, output);
save_demod_result(context, output, validation);
Result_Atomic_Write_Json(msiq.artifact_path( ...
    context, 'demod_result.json', 'write'), ...
    demod_for_json(output));
finalize_standalone_demod(analysis_run, output);
end

function save_demod_result(run_dir, output, validation)
path = msiq.artifact_path(run_dir, 'demod_result.mat', 'write');
if isstruct(run_dir) && isfield(run_dir, 'source_run_dir')
    save(path, 'output', '-v7.3');
    return;
end
preparation = msiq.artifact_path(run_dir, 'capture_preparation.mat', 'read');
if isfile(preparation)
    saved = load(preparation, 'validation');
    if isfield(saved, 'validation') && isequaln(saved.validation, validation)
        save(path, 'output', '-v7.3');
        return;
    end
end
% Compacted historical runs may have no separate preparation file.
save(path, 'output', 'validation', '-v7.3');
end

function [context, run] = analysis_context(context, raw_path)
source_dir = context.run_dir;
run = msiq.create_output_run(context.cfg, 'analysis', '传统链路重新解调', '');
Result_Write_Sources(run, {source_dir});
cfg = context.cfg;
save(fullfile(run.DataDir, 'effective_config.mat'), 'cfg');
validation_path = msiq.artifact_path(source_dir, 'capture_preparation.mat');
if ~isfile(validation_path)
    validation_path = msiq.artifact_path(source_dir, 'demod_result.mat');
end
source = struct('schema_version', '1.0', 'source_run_dir', source_dir, ...
    'raw_path', raw_path, 'raw_sha256', compute_file_sha256(raw_path), ...
    'validation_path', validation_path, 'validation_sha256', '');
if isfile(validation_path)
    source.validation_sha256 = compute_file_sha256(validation_path);
end
reference_path = context.reference_bundle_path;
if isempty(reference_path)
    reference_path = msiq.artifact_path(source_dir, 'tx_reference.mat');
end
source.reference_path = reference_path;
source.reference_sha256 = compute_file_sha256(reference_path);
Result_Atomic_Write_Json(fullfile(run.DataDir, 'capture_source.json'), source);
Result_Update_Run_Info(run, struct('inputs', source));
context.source_run_dir = source_dir;
context.run_dir = run.OutputDir;
context.diagnostics_dir = run.DataDir;
initialize_rx_summary(run);
end

function initialize_rx_summary(run)
Result_Summary_Initialize(run, ...
    {'序号','Channel','MER','EVM','pre-FEC BER','post-FEC BER','BLER','状态'}, ...
    {'-','-','dB','%','-','-','-','-'});
end

function finalize_standalone_demod(run, output)
if isempty(run), return; end
success = 0;
all_passed = true;
if isfield(output, 'pairs') && ~isempty(output.pairs)
    for pair_index = 1:numel(output.pairs)
        pair = output.pairs(pair_index);
        if strcmp(pair.status, 'decoded') && isfield(pair.decoded, 'primary_streams')
            streams = pair.decoded.primary_streams;
            for stream_index = 1:numel(streams)
                value = streams(stream_index);
                passed = field_or(value, 'pass', false);
                all_passed = all_passed && passed;
                success = success + double(passed);
                Result_Summary_Append(run, {1, pair_index, ...
                    value.mer_db, 100*value.evm_rms, value.pre_fec_ber, ...
                    value.post_fec_ber, value.bler, ternary(passed, '成功', '失败')});
            end
        else
            all_passed = false;
            Result_Summary_Append(run, {1, pair_index, [], [], [], [], [], '失败'});
        end
    end
else
    all_passed = false;
    Result_Summary_Append(run, {1, '', [], [], [], [], [], '无效'});
end
overview = fullfile(run.OutputDir, 'overview.png');
copyfile(output.dashboard_path, overview);
Result_Update_Run_Info(run, struct('counts', struct('planned', 1, ...
    'executed', 1, 'succeeded', double(all_passed && success > 0), ...
    'failed', double(~all_passed || success == 0), 'invalid', 0)));
Result_Finalize_Run(run, ternary(all_passed && success > 0, 'completed', ...
    'completed_with_failures'), 'normal_completion');
end

function finalize_standalone_capture(context, validation, dashboard_path)
if ~isempty(field_or(context, 'artifact_prefix', '')), return; end
info_path = msiq.artifact_path(context, 'run_info.json');
if ~isfile(info_path), return; end
run = struct('OutputDir', context.run_dir, 'DataDir', context.diagnostics_dir, ...
    'RunInfoPath', info_path, 'LogPath', fullfile(context.diagnostics_dir, 'run_log.txt'), ...
    'SummaryPath', fullfile(context.run_dir, 'summary.csv'), ...
    'SummaryFormats', struct('Samples', 'integer', 'SampleRate', 'exact'));
if ~isfile(run.SummaryPath)
    Result_Summary_Initialize(run, {'序号','Channel','Samples','SampleRate','状态'}, ...
        {'-','-','sample','Sa/s','-'});
    for k = 1:numel(validation.pairs)
        raw = validation.pairs(k).raw_for_decode;
        samples = field_or(raw, 'samples', []);
        Result_Summary_Append(run, {1, k, size(samples, 1), ...
            field_or(raw, 'sample_rate_hz', NaN), ternary(validation.ok, '成功', '无效')});
    end
end
overview = fullfile(context.run_dir, 'overview.png');
if ~isfile(overview), copyfile(dashboard_path, overview); end
Result_Update_Run_Info(run, struct('counts', struct('planned', 1, ...
    'executed', 1, 'succeeded', double(validation.ok), ...
    'failed', 0, 'invalid', double(~validation.ok))));
Result_Finalize_Run(run, ternary(validation.ok, 'completed', ...
    'completed_with_failures'), 'normal_completion');
end

function settle_analysis(run)
try
    info = Result_Update_Run_Info(run, struct());
    if strcmp(info.status, 'running')
        Result_Finalize_Run(run, 'failed', 'processing_failed', [], ...
            'Reprocessing ended before normal completion. Source run was preserved.');
    end
catch
end
end

function settle_capture(context)
if ~isempty(field_or(context, 'artifact_prefix', '')), return; end
try
    info_path = msiq.artifact_path(context, 'run_info.json');
    if ~isfile(info_path), return; end
    info = Result_Update_Run_Info(info_path, struct());
    if ~strcmp(info.status, 'running'), return; end
    summary = fullfile(context.run_dir, 'summary.csv');
    if ~isfile(summary)
        Result_Summary_Initialize(context.run_dir, {'序号','Channel','Samples','SampleRate','状态'}, ...
            {'-','-','sample','Sa/s','-'});
        Result_Summary_Append(context.run_dir, {1, '', [], [], '失败'});
    end
    Result_Update_Run_Info(context.run_dir, struct('counts', struct('planned', 1, ...
        'executed', 1, 'succeeded', 0, 'failed', 1, 'invalid', 0)));
    Result_Finalize_Run(context.run_dir, 'failed', 'acquisition_failed', [], ...
        'Capture ended before normal completion. Acquired data was retained.');
catch
end
end

function context = load_tx_context(run_dir, options)
local_reference = msiq.artifact_path(run_dir, 'tx_reference.mat', 'read');
local_waveform = msiq.artifact_path(run_dir, 'tx_waveform.mat', 'read');
local_manifest = msiq.artifact_path(run_dir, 'tx_manifest.mat', 'read');
if has_reference_bundle_option(options) || ...
        ~isfile(local_reference) || (~isfile(local_waveform) && ~isfile(local_manifest))
    context = load_bundle_context(run_dir, options);
    return;
end
required = {msiq.artifact_path(run_dir, 'tx_reference.mat', 'read'), ...
    msiq.artifact_path(run_dir, 'execution_receipt.json', 'read')};
for k = 1:numel(required)
    if ~isfile(required{k})
        error('msiq:traditionalRx:TxContext', ...
            'Capture requires successful awg_apply artifact: %s.', required{k});
    end
end
receipt = jsondecode(fileread(required{2}));
if ~isfield(receipt, 'status') || ~strcmpi(receipt.status, 'applied')
    error('msiq:traditionalRx:TxContext', ...
        'Capture requires a successful AWG execution receipt.');
end
reference = msiq.load_tx_reference(required{1});
waveform = msiq.load_tx_waveform(run_dir);
if isfield(options, 'cfg_override') && ~isempty(options.cfg_override)
    cfg = options.cfg_override;
else
    cfg = waveform.cfg;
end
[cfg, tx_ref] = apply_reference_compatibility(cfg, reference.tx_ref, struct());
cfg.waveform.architecture = 'single_complex_stream';
scope_status = struct();
metadata_path = msiq.artifact_path(run_dir, 'capture_metadata.json', 'read');
if isfile(metadata_path)
    try
        metadata = jsondecode(fileread(metadata_path));
        if isfield(metadata, 'scope_status_before')
            scope_status = metadata.scope_status_before;
        end
    catch
        scope_status = struct();
    end
end
context = struct('run_dir', run_dir, 'route', waveform.route, ...
    'diagnostics_dir', fullfile(run_dir, 'data'), ...
    'desired', waveform.desired, 'cfg', cfg, 'tx_ref', tx_ref, ...
    'awg_credentials', receipt, 'scope_status', scope_status, ...
    'reference_bundle_path', '', 'portable_reference', false, ...
    'reference_bundle', struct());
end

function status = read_scope_state(session, channels)
channels = cellstr(string(channels));
status = struct();
status.idn = safe_query(session, '*IDN?');
status.timebase = query_number(session, 'TDIV?');
status.timebase_raw = safe_query(session, 'TDIV?');
[status.sample_rate_hz, status.sample_rate_raw, status.sample_rate_source] = ...
    read_scope_sample_rate(session);
status.memory_depth = query_number(session, 'MSIZ?');
status.memory_depth_raw = safe_query(session, 'MSIZ?');
status.channels = repmat(empty_scope_channel(), 1, numel(channels));
for k = 1:numel(channels)
    channel = upper(channels{k});
    status.channels(k) = struct('channel', channel, ...
        'trace_state', safe_query(session, sprintf('%s:TRA?', channel)), ...
        'vertical_scale_v_per_div', query_number(session, sprintf('%s:VDIV?', channel)), ...
        'vertical_scale_raw', safe_query(session, sprintf('%s:VDIV?', channel)), ...
        'offset_v', query_number(session, sprintf('%s:OFST?', channel)), ...
        'offset_raw', safe_query(session, sprintf('%s:OFST?', channel)));
end
status.preprocessing = msiq.instruments.read_scope_preprocessing( ...
    session, channels);
end

function validation = normalize_capture(raw, tx_ref, route)
pairs = route_pairs(route);
validation = struct('ok', true, 'reason', '', ...
    'pairs', repmat(empty_normalized_pair(), 1, numel(pairs)), ...
    'summary', struct());
required_duration = 1.1 * field_or(tx_ref.frame, 'awg_padded_waveform_length', ...
    tx_ref.frame.awg_waveform_length) / ...
    tx_ref.frame.awg_sample_rate_hz;
pair_summaries = cell(1, numel(pairs));
for k = 1:numel(pairs)
    indices = pairs(k).indices;
    if max(indices) > numel(raw.channels)
        validation.ok = false;
        validation.reason = sprintf('missing_%s_channels', pairs(k).name);
        break;
    end
    records = raw.channels(indices);
    [pair_validation, reason] = normalize_pair(records, required_duration, pairs(k).payload_pair);
    pair_validation.name = pairs(k).name;
    pair_validation.scope_channels = {records.channel};
    validation.pairs(k) = pair_validation;
    pair_summaries{k} = pair_validation.summary;
    if ~isempty(reason)
        validation.ok = false;
        validation.reason = reason;
        break;
    end
end
validation.summary = struct('required_duration_s', required_duration, ...
    'pair_summaries', pair_summaries, ...
    'all_pairs_ready', validation.ok);
end

function [output, reason] = normalize_pair(records, required_duration, payload_pair)
output = struct('raw_for_decode', struct(), 'summary', struct());
reason = '';
times = cell(1,2);
samples = cell(1,2);
rates = nan(1,2);
for k = 1:2
    times{k} = double(records(k).time_axis_s(:));
    samples{k} = double(records(k).samples(:));
    if numel(times{k}) < 2 || numel(samples{k}) ~= numel(times{k}) || ...
            any(~isfinite(times{k})) || any(~isfinite(samples{k})) || ...
            any(diff(times{k}) <= 0)
        reason = 'nonmonotonic_or_invalid_time_axis';
        output.summary = struct('valid', false, 'reason', reason);
        return;
    end
    rates(k) = 1/median(diff(times{k}));
end
start_time = max(cellfun(@(x) x(1), times));
end_time = min(cellfun(@(x) x(end), times));
overlap = end_time - start_time;
if ~isfinite(overlap) || overlap < required_duration
    reason = 'insufficient_physical_time_window';
    output.summary = struct('valid', false, 'reason', reason, ...
        'overlap_duration_s', overlap, 'required_duration_s', required_duration, ...
        'sample_rates_hz', rates);
    return;
end
same_grid = numel(times{1}) == numel(times{2}) && ...
    max(abs(times{1}-times{2})) <= 0.05/min(rates);
if same_grid
    common_time = times{1};
    data = [samples{1}, samples{2}];
    interpolated = false;
else
    common_rate = min(rates);
    count = floor(overlap*common_rate) + 1;
    common_time = start_time + (0:count-1).'/common_rate;
    data = zeros(count, 2);
    for k = 1:2
        data(:,k) = interp1(times{k}, samples{k}, common_time, 'linear');
    end
    interpolated = true;
end
if any(~isfinite(data(:)))
    reason = 'interpolation_outside_physical_overlap';
    output.summary = struct('valid', false, 'reason', reason);
    return;
end
raw_for_decode = struct('samples', data, 'time_axes', ...
    repmat(common_time, 1, 2), 'sample_rate_hz', 1/median(diff(common_time)), ...
    'payload_pair', payload_pair, 'full_scale', NaN);
output.raw_for_decode = raw_for_decode;
output.summary = struct('valid', true, 'reason', '', ...
    'overlap_duration_s', overlap, 'required_duration_s', required_duration, ...
    'sample_rates_hz', rates, 'common_sample_rate_hz', raw_for_decode.sample_rate_hz, ...
    'common_sample_count', numel(common_time), 'interpolated', interpolated);
end

function pairs = route_pairs(route)
count = numel(route.awg_channels);
if mod(count, 2) ~= 0
    error('msiq:traditionalRx:RoutePairs', ...
        'Traditional I/Q demodulation requires channel pairs.');
end
pairs = repmat(struct('name', '', 'indices', [], 'payload_pair', ''), 1, count/2);
for k = 1:numel(pairs)
    indices = (2*k-1):(2*k);
    columns = route.waveform_columns(indices);
    if isequal(columns, [1 2])
        payload_pair = 'A';
    elseif isequal(columns, [3 4])
        payload_pair = 'B';
    else
        error('msiq:traditionalRx:RoutePairs', ...
            'Only I/Q pairs [1 2] and [3 4] are valid for demodulation.');
    end
    pairs(k) = struct('name', ['pair_', lower(payload_pair)], ...
        'indices', indices, 'payload_pair', payload_pair);
end
end

function write_failure_dashboard(context, failure)
validation = struct('ok', false, 'reason', 'capture_failed', ...
    'pairs', struct([]), 'summary', struct());
result = struct('status', 'failed', 'reason', failure.error_message, ...
    'pairs', struct([]));
try
    msiq.plotting.rx_dashboard( ...
        msiq.artifact_path(context, 'fig_rx_dashboard.png', 'write'), ...
        struct('channels', struct([])), validation, context, result);
catch
    % A dashboard is best effort when the scope failed before returning data.
end
end

function result = demod_for_json(output)
pairs = cell(1, numel(output.pairs));
result = struct('status', output.status, 'run_dir', output.run_dir, ...
    'diagnostics_dir', output.diagnostics_dir, ...
    'dashboard_path', output.dashboard_path, ...
    'physical_window', output.physical_window, 'pairs', {pairs});
for k = 1:numel(output.pairs)
    pair = output.pairs(k);
    if strcmp(pair.status, 'decoded')
        streams = pair.decoded.primary_streams;
        metrics = repmat(struct('post_fec_ber', NaN, 'pre_fec_ber', NaN, ...
            'bler', NaN, 'evm_rms', NaN, 'mer_db', NaN), 1, numel(streams));
        for s = 1:numel(streams)
            metrics(s) = struct('post_fec_ber', streams(s).post_fec_ber, ...
                'pre_fec_ber', streams(s).pre_fec_ber, 'bler', streams(s).bler, ...
                'evm_rms', streams(s).evm_rms, 'mer_db', streams(s).mer_db);
        end
        result.pairs{k} = struct('name', pair.name, 'status', 'decoded', ...
            'sync_ok', pair.decoded.sync_ok, ...
            'iq_orientation', field_or(pair.decoded, 'iq_orientation', struct()), ...
            'streams', metrics);
    else
        result.pairs{k} = rmfield(pair, setdiff(fieldnames(pair), ...
            {'name','status','error_identifier','error_message'}));
    end
end
end

function result = empty_pair_result()
result = struct('name', '', 'status', '', 'decoded', struct(), ...
    'error_identifier', '', 'error_message', '');
end

function value = empty_scope_channel()
value = struct('channel', '', 'trace_state', '', ...
    'vertical_scale_v_per_div', NaN, 'vertical_scale_raw', '', ...
    'offset_v', NaN, 'offset_raw', '');
end

function value = empty_normalized_pair()
value = struct('raw_for_decode', struct(), 'summary', struct(), ...
    'name', '', 'scope_channels', {{}});
end

function value = safe_query(session, command)
try
    value = strtrim(char(string(msiq.instruments.query_scpi(session, command))));
catch exception
    value = ['QUERY_FAILED:', exception.identifier];
end
end

function value = query_number(session, command)
value = parse_number(safe_query(session, command));
end

function [value, raw, source] = read_scope_sample_rate(session)
% Prefer the firmware-valid VBS path; SARA? times out on this SDA845ZI-A.
candidates = { ...
    'VBS? ''return=app.Acquisition.Horizontal.SampleRate''', ...
    'SARA?', ...
    'SAMPLE_RATE?'};
value = NaN;
raw = '';
source = '';
for k = 1:numel(candidates)
    candidate_raw = safe_query(session, candidates{k});
    candidate_value = parse_number(candidate_raw);
    if isfinite(candidate_value) && candidate_value > 0
        value = candidate_value;
        raw = candidate_raw;
        source = candidates{k};
        return;
    end
    if isempty(raw)
        raw = candidate_raw;
    end
end
end

function value = parse_number(text)
tokens = regexp(char(string(text)), '[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', ...
    'match');
if isempty(tokens)
    value = NaN;
else
    % LeCroy replies prefix values with the channel name, e.g.
    % "C1:VDIV 27E-3 V".  The final numeric token is the value.
    value = str2double(tokens{end});
end
end

function path = selected_run_path(selector, options)
path = '';
if ischar(selector) || (isstring(selector) && isscalar(selector))
    path = char(selector);
end
if isempty(path) && isfield(options, 'run_dir') && ~isempty(options.run_dir)
    path = char(string(options.run_dir));
end
end

function path = run_directory(selector, options)
path = selected_run_path(selector, options);
if isempty(path) || ~isfolder(path)
    error('msiq:traditionalRx:RunDirectory', ...
        'Specify an existing manual-loopback run directory.');
end
end

function value = timestamp_text()
value = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
end

function value = ternary(condition, yes, no)
if condition
    value = yes;
else
    value = no;
end
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end
