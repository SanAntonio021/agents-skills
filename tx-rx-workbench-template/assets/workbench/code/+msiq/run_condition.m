function outcome = run_condition(cfg, condition, execution_mode)
%RUN_CONDITION Execute V2 planning, staged checks, or formal hardware runs.

if nargin < 1 || isempty(cfg)
    cfg = msiq.build_config('v2_default');
elseif ~isstruct(cfg)
    cfg = msiq.build_config(cfg);
end
if nargin < 2 || isempty(condition)
    matrix = msiq.build_experiment_matrix(cfg);
    condition = matrix.conditions(1);
end
if nargin < 3 || isempty(execution_mode)
    execution_mode = cfg.safety.default_execution_mode;
end
mode = normalize_mode(execution_mode);
addpath(fullfile(cfg.code_root, 'result_management'));
addpath(fullfile(cfg.code_root, 'plotting'));

switch mode
    case 'dry_run'
        outcome = run_dry(cfg, condition);
    case 'simulation'
        outcome = run_simulation(cfg, condition);
    case 'hardware_query'
        outcome = run_idn_preflight(cfg, condition);
    case 'awg_off_check_dry_run'
        outcome = msiq.run_awg_off_check(cfg, condition, 'dry_run');
    case 'single_dac_smoke_dry_run'
        outcome = msiq.run_single_dac_smoke(cfg, condition, 'dry_run');
    case 'awg_off_check'
        require_hardware_enabled(cfg);
        outcome = msiq.run_awg_off_check(cfg, condition, 'hardware');
    case 'single_dac_smoke'
        require_hardware_enabled(cfg);
        outcome = msiq.run_single_dac_smoke(cfg, condition, 'hardware');
    case 'hardware'
        outcome = run_hardware(cfg, condition);
    otherwise
        error('msiq:run:ExecutionMode', ...
            'Unsupported execution mode: %s', execution_mode);
end
end

function outcome = run_simulation(cfg, condition)
before = msiq.instruments.get_audit();
run_cfg = msiq.apply_condition(cfg, condition);
policy = msiq.output_policy(run_cfg);
run = [];
if policy.write_results
    run = create_run(run_cfg, condition, 'simulation', struct([]));
    plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
end
try
[waveforms, tx_ref] = msiq.generate_waveforms( ...
    run_cfg, condition.repeat_plan(1).seed);
preflight = msiq.preflight_waveform(waveforms, run_cfg, run_cfg.awg.model);
if ~preflight.ok
    error('msiq:run:WaveformPreflight', ...
        'Waveform preflight failed: %s.', preflight.reason);
end

if policy.write_results
    Result_Summary_Initialize(run, summary_columns(), summary_units());
end
    options = simulation_options(run_cfg);
    payload_pair = char(string(options.payload_pair));
    options = rmfield(options, 'payload_pair');
    if strcmpi(run_cfg.waveform.architecture, 'single_complex_stream') && ...
            isfield(run_cfg.receiver, 'single_equalizer') && ...
            strcmpi(run_cfg.receiver.single_equalizer, 'wz_wl_fse_nlms') && ...
            abs(options.sro_ppm) > 0
        % Capture several playback cycles even when the AWG stores one frame.
        options.capture_repetitions = max(5, ...
            field_or(options, 'capture_repetitions', 1));
        playback_master_samples = round(tx_ref.frame.awg_padded_waveform_length * ...
            tx_ref.frame.master_sample_rate_hz / ...
            tx_ref.frame.awg_sample_rate_hz);
        options.segment_padding_samples = ...
            playback_master_samples-size(waveforms.master_dac_data,1);
    end
    raw = msiq.simulate_capture( ...
        waveforms, run_cfg, payload_pair, options);
    decoded = msiq.decode_capture(raw, tx_ref, run_cfg);

    if ~policy.write_results
        delta = audit_delta(before,msiq.instruments.get_audit());
        if any(struct2array(delta) ~= 0)
            error('msiq:run:SimulationInstrumentAccess','simulation attempted instrument I/O.');
        end
        outcome = struct('run_dir','','status',ternary(decoded.pass, ...
            'completed','completed_with_failures'),'execution_mode','simulation', ...
            'pass',decoded.pass,'streams',decoded.primary_streams,'instrument_io_delta',delta);
        return;
    end

    raw_name = '';
    reference_name = 'tx_reference.mat';
    decoded_name = 'decoded_result.mat';
    if policy.save_raw
        raw_name = 'raw_capture.mat';
        save(msiq.output_path(run, raw_name), 'raw', '-v7.3');
        save(msiq.output_path(run, reference_name), 'tx_ref', '-v7.3');
        save(msiq.output_path(run, decoded_name), 'decoded', '-v7.3');
    end
    Result_Atomic_Write_Json(msiq.output_path(run, ...
        'simulation_options.json'), raw.simulation_options);

    physical = condition.active_physical_subbands{1};
    streams = decoded.primary_streams;
    for stream_index = 1:numel(streams)
        value = streams(stream_index);
        row = summary_row(decoded, value, physical, ...
            stream_index, 1, 1, NaN, NaN, NaN, raw_name, ...
            ternary(value.pass, '成功', '失败'), '', '');
        row{26} = '仿真';
        Result_Summary_Append(run,row);
    end
    msiq.plotting.simulation_plots(run, raw, decoded, run_cfg, condition);
    plot_path = msiq.output_path(run,'plot_data.mat');
    plot_record = load(plot_path);
    plot_record.effective_config = run_cfg;
    plot_record.condition = condition;
    plot_record.simulation_options = raw.simulation_options;
    msiq.atomic_save(plot_path,plot_record);

    after = msiq.instruments.get_audit();
    delta = audit_delta(before, after);
    if any(struct2array(delta) ~= 0)
        error('msiq:run:SimulationInstrumentAccess', ...
            'simulation attempted instrument I/O.');
    end
    passed = decoded.pass;
    status = ternary(passed, 'completed', 'completed_with_failures');
    updates = struct( ...
        'counts', struct('planned', 1, 'executed', 1, ...
        'succeeded', double(passed), 'failed', double(~passed), 'invalid', 0), ...
        'safety', struct('preflight', 'passed', ...
        'initial_outputs', 'not_accessed', 'shutdown', 'not_required', ...
        'shutdown_readback', 'not_required', 'instrument_io_delta', delta), ...
        'parameters', merge_struct(run_parameters(run_cfg, condition, tx_ref), ...
        struct('simulation', raw.simulation_options,'effective_config',run_cfg, ...
        'output_level',policy.output_level)), ...
        'inputs', {{struct('waveform_id', tx_ref.waveform_id, ...
        'tx_reference_hash', tx_ref.reference_hash_sha256)}});
    Result_Update_Run_Info(run, updates);
    Result_Log_Stage(run, 'INFO', 'simulation', ...
        'Synthetic capture decoded; no instrument I/O occurred.');
    Result_Finalize_Run(run, status, 'normal_completion', [], '');
    assert_flat(run);
    outcome = struct('run_dir', run.OutputDir, 'status', status, ...
        'execution_mode', 'simulation', 'pass', passed, ...
        'streams', streams, 'instrument_io_delta', delta);
catch exception
    if ~isempty(run)
        failure = struct('cfg',run_cfg,'condition',condition,'message',exception.message);
        if exist('waveforms','var'), failure.waveforms = waveforms; end
        if exist('raw','var'), failure.raw = raw; end
        if exist('tx_ref','var'), failure.tx_ref = tx_ref; end
        if exist('decoded','var'), failure.decoded = decoded; end
        msiq.save_failure(run.OutputDir,failure);
        finalize_failure(run, exception, 'processing_failed');
    end
    rethrow(exception);
end
end

function outcome = run_dry(cfg, condition)
before = msiq.instruments.get_audit();
run_cfg = msiq.apply_condition(cfg, condition);
policy = msiq.output_policy(run_cfg);
[waveforms, tx_ref] = msiq.generate_waveforms( ...
    run_cfg, condition.repeat_plan(1).seed);
preflight = msiq.preflight_waveform(waveforms, run_cfg, run_cfg.awg.model);
if ~preflight.ok
    error('msiq:run:WaveformPreflight', ...
        'Waveform preflight failed: %s.', preflight.reason);
end

if ~policy.write_results
    outcome = struct('run_dir','','status','completed','execution_mode','dry_run', ...
        'preflight',preflight,'instrument_io_delta',audit_delta(before,msiq.instruments.get_audit()));
    return;
end
run = create_run(cfg, condition, 'dry_run', struct([]));
plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
try
    Result_Summary_Initialize(run, summary_columns(), summary_units());
    waveform_file = msiq.output_path(run, 'tx_waveform.mat');
    reference_file = msiq.output_path(run, 'tx_reference.mat');
    if policy.save_raw
        save(waveform_file, 'waveforms', '-v7.3');
        save(reference_file, 'tx_ref', '-v7.3');
    end
    Test_Project_Plot_Plan(msiq.output_path(run, 'overview.png'), ...
        (1:condition.repetitions).', struct( ...
        'Title', ['V2 dry-run: ', condition.condition_id], ...
        'XName', '逻辑重复', 'XUnit', '-', ...
        'PlannedCount', condition.repetitions, ...
        'Stages', {{'波形检查','槽位检查','接收批次检查','安全检查'}}));

    after = msiq.instruments.get_audit();
    delta = audit_delta(before, after);
    if any(struct2array(delta) ~= 0)
        error('msiq:run:DryRunInstrumentAccess', ...
            'dry-run attempted instrument I/O.');
    end
    safety = struct('preflight', 'passed', 'initial_outputs', 'not_accessed', ...
        'shutdown', 'not_required', 'shutdown_readback', 'not_required', ...
        'instrument_io_delta', delta);
    updates = struct('counts', struct('planned', ...
        2*condition.repetitions*numel(condition.receive_batches), ...
        'executed', 0, 'succeeded', 0, 'failed', 0, 'invalid', 0), ...
        'safety', safety, 'parameters', run_parameters(run_cfg, condition, tx_ref), ...
        'inputs', {{struct('waveform_id', tx_ref.waveform_id, ...
        'tx_reference_hash', tx_ref.reference_hash_sha256)}});
    Result_Update_Run_Info(run, updates);
    Result_Log_Stage(run, 'INFO', 'safety', ...
        'No instrument connection, query, write, or capture occurred.');
    Result_Finalize_Run(run, 'completed', 'normal_completion', [], '');
    assert_flat(run);
    outcome = struct('run_dir', run.OutputDir, 'status', 'completed', ...
        'execution_mode', 'dry_run', 'preflight', preflight, ...
        'instrument_io_delta', delta);
catch exception
    finalize_failure(run, exception, 'preflight_failed');
    rethrow(exception);
end
end

function outcome = run_idn_preflight(cfg, condition)
specs = instrument_specs(cfg);
metadata = instrument_metadata(specs);
run = create_run(cfg, condition, 'hardware_query', metadata);
guard = msiq.instruments.SafetyGuard(cfg);
try
    Result_Summary_Initialize(run, summary_columns(), summary_units());
    guard.Sessions.awg = msiq.instruments.open_session( ...
        'awg', specs.awg, 'query_only');
    guard.Sessions.scope = msiq.instruments.open_session( ...
        'scope', specs.scope, 'query_only');
    guard.Sessions.source = msiq.instruments.open_session( ...
        'signal_generator', specs.source, 'query_only');
    identities = struct();
    identities.awg = msiq.instruments.query_idn(guard.Sessions.awg);
    identities.scope = msiq.instruments.query_idn(guard.Sessions.scope);
    identities.signal_generator = msiq.instruments.query_idn(guard.Sessions.source);

    % Read-only preflight closes sessions without output-control writes.
    msiq.instruments.close_session(guard.Sessions.scope);
    msiq.instruments.close_session(guard.Sessions.source);
    msiq.instruments.close_session(guard.Sessions.awg);
    guard.Sessions = struct('awg', [], 'scope', [], 'source', []);
    guard.Done = true;
    Result_Atomic_Write_Json(msiq.output_path(run, 'instrument_idn.json'), identities);
    Test_Project_Plot_Plan(msiq.output_path(run, 'overview.png'), 1:3, ...
        struct('Title', '只读 IDN 预检', 'XName', '仪器序号', ...
        'XUnit', '-', 'PlannedCount', 3, ...
        'Stages', {{'连接','读取 *IDN?','关闭会话'}}));
    Result_Update_Run_Info(run, struct( ...
        'counts', struct('planned', 3, 'executed', 3, ...
        'succeeded', 3, 'failed', 0, 'invalid', 0), ...
        'safety', struct('preflight', 'passed', ...
        'initial_outputs', 'not_modified', 'shutdown', 'not_applicable', ...
        'shutdown_readback', 'not_applicable')));
    Result_Finalize_Run(run, 'completed', 'normal_completion', [], '');
    assert_flat(run);
    outcome = struct('run_dir', run.OutputDir, 'status', 'completed', ...
        'execution_mode', 'hardware_query', 'identities', identities);
catch exception
    close_query_sessions(guard);
    finalize_failure(run, exception, 'instrument_connection_failed');
    rethrow(exception);
end
end

function outcome = run_hardware(cfg, condition)
run_cfg = msiq.apply_condition(cfg, condition);
hardware_gate(cfg, condition);
specs = instrument_specs(cfg);
metadata = instrument_metadata(specs);
run = create_run(run_cfg, condition, 'hardware', metadata);
guard = msiq.instruments.SafetyGuard(run_cfg);
repeat_pass = false(1, condition.repetitions);
executed = 0;
succeeded = 0;
failed = 0;
repeat_errors = 0;
planned_captures = 2*condition.repetitions*numel(condition.receive_batches);
acquisition_pending = false;
capture_stage = '';
current_seed = NaN;
tx_ref = [];
try
    Result_Summary_Initialize(run, summary_columns(), summary_units());
    guard.Sessions.awg = msiq.instruments.open_session('awg', specs.awg);
    guard.Sessions.scope = msiq.instruments.open_session('scope', specs.scope);
    guard.Sessions.source = msiq.instruments.open_session( ...
        'signal_generator', specs.source);
    identities = struct( ...
        'awg', msiq.instruments.query_idn(guard.Sessions.awg), ...
        'scope', msiq.instruments.query_idn(guard.Sessions.scope), ...
        'signal_generator', msiq.instruments.query_idn(guard.Sessions.source));
    Result_Atomic_Write_Json(msiq.output_path(run, 'instrument_idn.json'), identities);

    msiq.instruments.set_awg_output(guard.Sessions.awg, false);
    msiq.instruments.configure_source(guard.Sessions.source, specs.source, true);
    scope_readback = msiq.instruments.configure_scope( ...
        guard.Sessions.scope, run_cfg.scope);
    Result_Atomic_Write_Json(msiq.output_path(run, ...
        'scope_readback.json'), scope_readback);

    metric_records = repmat(struct('repeat',0,'channel','','evm',NaN,'mer',NaN), 0, 1);
    sequence = 0;
    for repeat = 1:condition.repetitions
        plan = condition.repeat_plan(repeat);
        repeat_ok = true;
        try
            if plan.seed ~= current_seed
                msiq.instruments.set_awg_output(guard.Sessions.awg, false);
                [waveforms, tx_ref] = msiq.generate_waveforms(run_cfg, plan.seed);
                msiq.instruments.download_awg( ...
                    guard.Sessions.awg, waveforms, run_cfg);
                current_seed = plan.seed;
                waveform_path = msiq.output_path(run,sprintf( ...
                    'tx_waveform_seed%d.mat',plan.seed));
                reference_path = msiq.output_path(run,sprintf( ...
                    'tx_reference_seed%d.mat',plan.seed));
                if ~isfile(waveform_path), save(waveform_path,'waveforms','-v7.3'); end
                if ~isfile(reference_path)
                    save(reference_path,'tx_ref','-v7.3');
                else
                    previous = load(reference_path,'tx_ref');
                    if ~strcmp(previous.tx_ref.reference_hash_sha256,tx_ref.reference_hash_sha256)
                        error('msiq:run:ReferenceChanged','Seed reference changed within one run.');
                    end
                end
            end
            for batch_index = 1:numel(condition.receive_batches)
                batch = condition.receive_batches(batch_index);
                msiq.instruments.set_awg_output(guard.Sessions.awg, false);
                sequence = sequence+1;
                executed = executed+1;
                acquisition_pending = true;
                capture_stage = 'OFF';
                raw_off = msiq.instruments.capture_scope( ...
                    guard.Sessions.scope, scope_channels(batch));
                off_name = sprintf('OFF_batch%02d_repeat%02d_attempt01.mat', ...
                    batch_index, repeat);
                save(msiq.output_path(run, off_name), 'raw_off', '-v7.3');
                for channel = 1:size(raw_off.samples,2)
                    off_row = cell(1,numel(summary_columns()));
                    off_row(:) = {''};
                    physical = batch.physical_subbands{ceil(channel/2)};
                    off_row([15 16 17 18 19 20 22 26]) = ...
                        {physical,sprintf('C%d',channel),batch_index,'成功', ...
                        sequence,1,off_name,'OFF'};
                    Result_Summary_Append(run,off_row);
                end
                succeeded = succeeded+1;
                acquisition_pending = false;

                msiq.instruments.set_awg_output(guard.Sessions.awg, true);
                sequence = sequence+1;
                executed = executed+1;
                acquisition_pending = true;
                capture_stage = 'ON';
                raw_on = msiq.instruments.capture_scope( ...
                    guard.Sessions.scope, scope_channels(batch));
                on_name = sprintf('ON_batch%02d_repeat%02d_attempt01.mat', ...
                    batch_index, repeat);
                save(msiq.output_path(run, on_name), 'raw_on', '-v7.3');

                on_rows = cell(0,numel(summary_columns()));
                on_records = metric_records([]);
                for local_index = 1:numel(batch.physical_subbands)
                    physical = batch.physical_subbands{local_index};
                    mapping = condition.awg_slot_map(strcmp( ...
                        {condition.awg_slot_map.physical_subband}, physical));
                    columns = 2*local_index-1:2*local_index;
                    one_raw = subset_raw(raw_on, columns);
                    one_raw.payload_pair = mapping.payload_pair;
                    if isfield(specs.scope, 'fail_stage') && ...
                            strcmpi(char(string(specs.scope.fail_stage)), 'dsp')
                        error('msiq:instrument:MockFailure', ...
                            'Injected mock failure at dsp.');
                    end
                    decoded = msiq.decode_capture(one_raw, tx_ref, run_cfg);
                    off_power = inband_power_dbm( ...
                        subset_raw(raw_off, columns), run_cfg);
                    on_power = inband_power_dbm(one_raw, run_cfg);
                    ratio = on_power-off_power;
                    repeat_ok = repeat_ok && decoded.pass;
                    for stream = 1:numel(decoded.primary_streams)
                        value = decoded.primary_streams(stream);
                        row = summary_row(decoded, value, physical, stream, ...
                            batch_index, sequence, off_power, on_power, ratio, ...
                            on_name, '成功', '', '');
                        on_rows(end+1,:) = row; %#ok<AGROW>
                        image_name = sprintf('%03d_%s_Channel%d_星座图.png', ...
                            sequence,physical,stream);
                        plot_metrics = struct('BER',value.pre_fec_ber, ...
                            'EVM',100*value.evm_rms,'MER',value.mer_db);
                        ideal = qammod((0:run_cfg.waveform.modulation_order-1).', ...
                            run_cfg.waveform.modulation_order,'UnitAveragePower',true);
                        Test_Project_Plot_Constellation(msiq.output_path(run,image_name), ...
                            {value.constellation_symbols},ideal,plot_metrics, ...
                            struct('Title',sprintf('%s Channel%d',physical,stream)));
                        on_records(end+1) = struct('repeat', sequence, ...
                            'channel',sprintf('%s_Channel%d',physical,stream), ...
                            'evm', value.evm_rms, 'mer', value.mer_db); %#ok<AGROW>
                    end
                end
                Result_Summary_Append(run,on_rows);
                metric_records(end+1:end+numel(on_records)) = on_records;
                succeeded = succeeded+1;
                acquisition_pending = false;
            end
        catch repeat_exception
            repeat_ok = false;
            repeat_errors = repeat_errors+1;
            diagnostic_name = sprintf( ...
                'FAILED_repeat%02d_attempt01_diagnostic.mat', repeat);
            save(msiq.output_path(run, diagnostic_name), ...
                'repeat_exception', 'plan');
            if acquisition_pending
                failed = failed+1;
                acquisition_pending = false;
                channels = scope_channels(batch);
                for channel = 1:numel(channels)
                    row = failure_summary_row(sequence, repeat_exception, diagnostic_name);
                    row{15} = batch.physical_subbands{ceil(channel/2)};
                    row{16} = channels{channel};
                    row{17} = batch_index;
                    row{26} = capture_stage;
                    Result_Summary_Append(run,row);
                end
            end
            Result_Log_Stage(run, 'ERROR', 'repeat', ...
                'repeat%02d failed: %s', repeat, repeat_exception.message);
        end
        repeat_pass(repeat) = repeat_ok;
        msiq.instruments.set_awg_output(guard.Sessions.awg, false);
    end

    shutdown_report = guard.shutdown();
    create_hardware_overview(run, metric_records, condition);
    passing = nnz(repeat_pass);
    acceptance_pass = passing >= cfg.experiment.minimum_passing_repeats;
    status = 'completed';
    if ~acceptance_pass || repeat_errors > 0
        status = 'completed_with_failures';
    end
    updates = struct( ...
        'counts', struct('planned', planned_captures, ...
        'executed', executed, 'succeeded', succeeded, ...
        'failed', failed, 'invalid', 0), ...
        'safety', struct('preflight', 'passed', 'initial_outputs', 'off', ...
        'shutdown', ternary(isempty(shutdown_report.errors), 'passed', 'failed'), ...
        'shutdown_readback', 'not_implemented'), ...
        'parameters', merge_struct(run_parameters(run_cfg, condition, tx_ref), ...
        struct('acceptance_pass', acceptance_pass, ...
        'passing_repeats', passing, 'repeat_pass', repeat_pass)));
    Result_Update_Run_Info(run, updates);
    Result_Finalize_Run(run, status, 'normal_completion', [], '');
    assert_flat(run);
    outcome = struct('run_dir', run.OutputDir, 'status', status, ...
        'execution_mode', 'hardware', 'acceptance_pass', acceptance_pass, ...
        'passing_repeats', passing, 'repeat_pass', repeat_pass, ...
        'shutdown', shutdown_report);
catch exception
    shutdown_report = guard.shutdown();
    failed = failed+double(acquisition_pending);
    Result_Update_Run_Info(run, struct('counts', struct( ...
        'planned',planned_captures,'executed',executed, ...
        'succeeded',succeeded,'failed',failed,'invalid',0), ...
        'safety', struct( ...
        'shutdown', ternary(isempty(shutdown_report.errors), 'passed', 'failed'))));
    finalize_failure(run, exception, classify_stop_reason(exception));
    rethrow(exception);
end
end

function run = create_run(cfg, condition, mode, instruments)
if strcmp(mode, 'dry_run')
    run_type = 'dry_run';
    planned = 'single_point';
    purpose = 'validation';
elseif strcmp(mode, 'simulation')
    run_type = 'simulation';
    planned = '';
    purpose = 'validation';
else
    run_type = 'single_point';
    planned = '';
    purpose = ternary(strcmp(mode, 'hardware'), cfg.results.purpose, 'validation');
end
policy = msiq.output_policy(cfg);
create_cfg = struct( ...
    'ProjectRoot', cfg.project_root, 'ResultsRoot', cfg.results_root, ...
    'RunType', run_type, 'NameParts', {{condition.condition_id}}, ...
    'RetentionMode', policy.output_level, ...
    'DisplayColumns', {{'序号','物理子带','Channel','MER','EVM', ...
        'pre-FEC BER','post-FEC BER','BLER','状态','采集阶段'}}, ...
    'ProjectName', 'multistream_iq_SC', ...
    'TestName', 'single_carrier_multiphysical_subband_v2', ...
    'PlannedRunKind', planned, 'RunPurpose', purpose, ...
    'ExecutionMode', mode, 'EntryPoint', 'Multistream_Workbench.m', ...
    'Parameters', run_parameters(cfg, condition, []), ...
    'Counts', struct('planned', condition.repetitions), ...
    'Instruments', instruments, ...
    'Safety', struct('preflight', 'pending', 'initial_outputs', 'pending', ...
    'shutdown', 'pending', 'shutdown_readback', 'pending'));
if isfield(cfg.results,'source_run') && ~isempty(cfg.results.source_run)
    create_cfg.SourceRuns = {cfg.results.source_run};
end
if ismember(mode, {'hardware','dry_run'})
    create_cfg.Counts.planned = 2*condition.repetitions*numel(condition.receive_batches);
elseif strcmp(mode, 'simulation')
    create_cfg.Counts.planned = 1;
end
run = Result_Create_Run(create_cfg);
effective_cfg = cfg;
save(msiq.output_path(run,'effective_config.mat'),'effective_cfg','-v7.3');
end

function options = simulation_options(cfg)
options = struct('payload_pair', 'A', 'snr_db', 2, ...
    'cfo_hz', 2e5, 'sro_ppm', 40, ...
    'channel_matrix', [1 0.08; 0.06 0.95], ...
    'image_matrix', [0.02 0.01; 0.01 0.02], ...
    'channel_skew_samples', 0.35, ...
    'time_axis_skew_samples', 0.2, 'prepend_samples', 777, ...
    'crop_start_samples', 0, 'clip_level', 1e6, 'rng_seed', 9001);
if isfield(cfg, 'simulation') && isstruct(cfg.simulation)
    options = merge_struct(options, cfg.simulation);
end
end


function value = run_parameters(cfg, condition, tx_ref)
value = struct('condition', condition, ...
    'effective_config',cfg, ...
    'waveform', struct('modulation', '16QAM', ...
    'carrier_type', 'single_carrier', 'up', condition.up, ...
    'symbol_rate_hz', condition.symbol_rate_hz, ...
    'fec', 'DVB-S2 LDPC 9/10'), ...
    'scope_settings', cfg.scope);
if ~isempty(tx_ref)
    value.waveform.waveform_id = tx_ref.waveform_id;
    value.waveform.tx_reference_hash = tx_ref.reference_hash_sha256;
end
end

function specs = instrument_specs(cfg)
required = {'awg', 'scope', 'signal_generator'};
for k = 1:numel(required)
    if ~isfield(cfg.instrument, required{k})
        error('msiq:instrument:LocalConfigRequired', ...
            ['Missing cfg.instrument.%s. Create config/instruments.local.json ', ...
            'from the example before instrument access.'], required{k});
    end
end
specs = struct('awg', cfg.instrument.awg, ...
    'scope', cfg.instrument.scope, 'source', cfg.instrument.signal_generator);
end

function metadata = instrument_metadata(specs)
names = {'awg','scope','source'};
roles = {'waveform_generator','oscilloscope','signal_generator'};
metadata = repmat(struct('role','','resource',''), 1, numel(names));
for k = 1:numel(names)
    metadata(k).role = roles{k};
    if isfield(specs.(names{k}), 'resource')
        metadata(k).resource = char(string(specs.(names{k}).resource));
    elseif isfield(specs.(names{k}), 'mock') && specs.(names{k}).mock
        metadata(k).resource = 'MOCK';
    end
end
end

function hardware_gate(cfg, condition)
if ~cfg.safety.hardware_enabled
    error('msiq:safety:HardwareDisabled', ...
        'Hardware mode is disabled in the active configuration.');
end
if cfg.safety.require_power_unit && condition.num_active > 0 && ...
        (isempty(condition.power_unit_dbm) || ...
        ~isfinite(condition.power_unit_dbm))
    error('msiq:safety:PowerUnitMissing', ...
        'P_unit must be measured in the common linear region before hardware mode.');
end
show_wiring(condition);
test_mode = isfield(cfg.safety, 'test_mode') && cfg.safety.test_mode;
granted = isfield(cfg.safety, 'confirmation_granted') && ...
    cfg.safety.confirmation_granted;
if test_mode && granted
    return;
end
if ~cfg.safety.interactive_confirmation
    error('msiq:safety:ConfirmationRequired', ...
        'Interactive hardware confirmation is required.');
end
reply = input(sprintf('Type exactly "%s" to enable RF output: ', ...
    cfg.safety.confirmation_phrase), 's');
if ~strcmp(reply, cfg.safety.confirmation_phrase)
    error('msiq:safety:ConfirmationRejected', ...
        'Hardware output confirmation was not granted.');
end
end

function show_wiring(condition)
fprintf('\nV2 wiring for %s\n', condition.condition_id);
fprintf('DAC1=I_A, DAC2=Q_A, DAC3=I_B, DAC4=Q_B\n');
for k = 1:numel(condition.awg_slot_map)
    item = condition.awg_slot_map(k);
    fprintf('  %-3s <- %-2s payload %s polarity %+d\n', ...
        item.physical_subband, item.slot, item.payload_pair, item.polarity);
end
fprintf('All active TX subbands remain on during each receive batch.\n\n');
end

function names = scope_channels(batch)
names = cell(1, 2*numel(batch.physical_subbands));
for k = 1:numel(names)
    names{k} = sprintf('C%d', k);
end
end

function one = subset_raw(raw, columns)
one = raw;
one.samples = raw.samples(:,columns);
if isfield(raw, 'time_axes') && ~isempty(raw.time_axes)
    one.time_axes = raw.time_axes(:,columns);
end
end

function power_dbm = inband_power_dbm(raw, cfg)
samples = double(raw.samples);
rate = raw.sample_rate_hz;
count = size(samples,1);
frequency = (0:count-1).'/count*rate;
positive = abs(frequency-cfg.waveform.if_center_hz) <= ...
    0.6*cfg.waveform.symbol_rate_hz;
negative_center = rate-cfg.waveform.if_center_hz;
negative = abs(frequency-negative_center) <= ...
    0.6*cfg.waveform.symbol_rate_hz;
mask = positive | negative;
power_w = zeros(1,size(samples,2));
for channel = 1:size(samples,2)
    spectrum = fft(samples(:,channel));
    band = ifft(spectrum.*mask);
    power_w(channel) = mean(abs(band).^2)/50;
end
power_dbm = 10*log10(max(mean(power_w)*1000, realmin));
end

function create_hardware_overview(run, records, condition)
if isempty(records)
    Test_Project_Plot_Plan(msiq.output_path(run, 'overview.png'), ...
        1:condition.repetitions, struct('Title','无有效解调记录', ...
        'XName','逻辑重复','XUnit','-', ...
        'PlannedCount',condition.repetitions));
    return;
end
msiq.plotting.observation_overview(msiq.output_path(run,'overview.png'), ...
    [records.repeat],{records.channel},100*[records.evm],[records.mer]);
end

function row = summary_row(decoded, stream, physical, stream_index, batch, ...
        repeat, off_power, on_power, ratio, raw_file, status, code, message)
iterations = stream.actual_iterations;
if isempty(iterations), iteration_text = ''; else, iteration_text = mat2str(iterations); end
row = {double(decoded.sync_ok), max(decoded.clip_fraction), stream.mer_db, ...
    100*stream.evm_rms, stream.pre_fec_ber, stream.post_fec_ber, ...
    stream.bler, double(stream.parity_converged), stream.block_count, ...
    double(stream.incomplete_tail_bits>0), iteration_text, off_power, ...
    on_power, ratio, physical, stream_index, batch, status, repeat, 1, ...
    char(datetime('now','Format','yyyy-MM-dd HH:mm:ss')), raw_file, '', code, message,'ON'};
end

function row = failure_summary_row(repeat, exception, diagnostic_file)
row = cell(1, numel(summary_columns()));
row(:) = {''};
row{18} = '失败';
row{19} = repeat;
row{20} = 1;
row{21} = char(datetime('now','Format','yyyy-MM-dd HH:mm:ss'));
row{22} = diagnostic_file;
row{24} = exception.identifier;
row{25} = exception.message;
end

function columns = summary_columns()
columns = {'同步状态','削顶比例','MER','EVM','pre-FEC BER', ...
    'post-FEC BER','BLER','parity收敛','完整码块','丢弃码块', ...
    '译码迭代','OFF带内功率','ON带内功率','On/Off Ratio', ...
    '物理子带','Channel','批次','状态','序号','attempt','采集时间', ...
    '原始数据文件','单次图片文件','错误代码','错误信息','采集阶段'};
end

function units = summary_units()
units = {'-','-','dB','%','-','-','-','-','block','block', ...
    'iteration','dBm','dBm','dB','-','-','-','-','-','-','-', ...
    '-','-','-','-','-'};
end

function delta = audit_delta(before, after)
names = fieldnames(before);
delta = struct();
for k = 1:numel(names)
    delta.(names{k}) = after.(names{k})-before.(names{k});
end
end

function close_query_sessions(guard)
names = {'scope','source','awg'};
for k = 1:numel(names)
    value = guard.Sessions.(names{k});
    if ~isempty(value)
        msiq.instruments.close_session(value);
        guard.Sessions.(names{k}) = [];
    end
end
guard.Done = true;
end

function finalize_failure(run, exception, reason)
try
    Result_Log_Stage(run, 'ERROR', 'failure', '%s: %s', ...
        exception.identifier, exception.message);
catch
end
try
    create_failure_overview(run, exception);
catch
end
try
    Result_Finalize_Run(run, 'failed', reason, [], exception.message);
catch
end
end

function create_failure_overview(run, exception)
path = msiq.output_path(run, 'overview.png');
if isfile(path)
    return;
end
identifier = exception.identifier;
if isempty(identifier)
    identifier = 'unhandled_exception';
end
Test_Project_Plot_Plan(path, 1, struct( ...
    'Title', ['FAILED: ', identifier], ...
    'XName', '失败运行', 'XUnit', '-', 'PlannedCount', 1, ...
    'Stages', {{'运行失败','查看 run_log.txt 和 run_info.json'}}));
end

function reason = classify_stop_reason(exception)
id = exception.identifier;
if contains(id, 'Connection') || contains(id, 'MissingResource')
    reason = 'instrument_connection_failed';
elseif contains(id, 'Capture') || contains(id, 'capture')
    reason = 'acquisition_failed';
elseif contains(id, 'dsp') || contains(id, 'decode')
    reason = 'processing_failed';
elseif contains(id, 'safety')
    reason = 'safety_stop';
else
    reason = 'unhandled_exception';
end
end

function assert_flat(run)
report = Result_Check_Flat_Directory(run);
if ~report.IsFlat
    error('msiq:run:NonFlatResult', ...
        'Run directory contains nested content.');
end
end

function mode = normalize_mode(value)
mode = lower(char(string(value)));
aliases = struct('instrument_preflight','hardware_query', ...
    'preflight','hardware_query','formal','hardware', ...
    'v212','awg_off_check','v212_dry_run','awg_off_check_dry_run', ...
    'v213','single_dac_smoke','v213_dry_run','single_dac_smoke_dry_run');
if isfield(aliases, mode)
    mode = aliases.(mode);
end
end

function require_hardware_enabled(cfg)
if ~cfg.safety.hardware_enabled
    error('msiq:safety:HardwareDisabled', ...
        'Hardware mode is disabled in the active configuration.');
end
end

function out = merge_struct(first, second)
out = first;
names = fieldnames(second);
for k = 1:numel(names)
    out.(names{k}) = second.(names{k});
end
end

function value = field_or(source, name, fallback)
if isfield(source, name) && ~isempty(source.(name)) && ...
        (~isnumeric(source.(name)) || all(isfinite(source.(name)), 'all'))
    value = source.(name);
else
    value = fallback;
end
end

function value = ternary(condition, if_true, if_false)
if condition, value = if_true; else, value = if_false; end
end
