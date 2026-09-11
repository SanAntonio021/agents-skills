function report = run_wz_sro_distortion_stress(options)
%RUN_WZ_SRO_DISTORTION_STRESS Offline WZ SRO estimator stress replay.
% Each stress case is replayed as B=no correction, C=the selected two-pass
% policy, and D=known oracle. The default C policy follows production.

if nargin < 1 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:sroStress:Options', 'options must be a scalar struct.');
end
repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo, 'code', 'result_management'));

% Equivalent delayed-copy amplitudes. The final two cases extend the
% stress range to approximately 14 dB and 10 dB effective return loss.
defaults = struct( ...
    'results_root', repo, ...
    'source', 'real', ...
    'write_results', true, ...
    'rng_seed', 260825, ...
    'snr_values_db', [38 35], ...
    'global_sro_ppm', 200, ...
    'echo_amplitudes', [0.03 0.06 0.10 0.20 0.316], ...
    'echo_delays_symbols', [1 2 4], ...
    'profile_ppm_pairs', [150 250; 100 300], ...
    'sro_interval_consistency_limit_samples', 1.25, ...
    'sro_decision_policy', 'conservative_ci', ...
    'sro_observation_oversample_factor', 8, ...
    'families', {{'clean','noise','echo','varying'}});
options = merge_options(defaults, options);
policy = msiq.output_policy(options);
options.output_level = policy.output_level;
options.source = lower(char(string(options.source)));
options.sro_decision_policy = lower(char(string(options.sro_decision_policy)));
if ~ismember(options.source, {'real','synthetic'})
    error('msiq:sroStress:Source', 'source must be real or synthetic.');
end
if ~ismember(options.sro_decision_policy, ...
        {'legacy','conservative_ci','confidence_weighted'})
    error('msiq:sroStress:Policy', 'Unsupported SRO decision policy.');
end
factor = double(options.sro_observation_oversample_factor);
if ~isscalar(factor) || ~isfinite(factor) || factor < 1 || factor > 16 || ...
        factor ~= round(factor)
    error('msiq:sroStress:Oversample', ...
        'sro_observation_oversample_factor must be an integer from 1 to 16.');
end
if ~isscalar(options.sro_interval_consistency_limit_samples) || ...
        ~isfinite(options.sro_interval_consistency_limit_samples) || ...
        options.sro_interval_consistency_limit_samples <= 0
    error('msiq:sroStress:ConsistencyLimit', ...
        'sro_interval_consistency_limit_samples must be positive.');
end
validate_scenario_options(options);

trials = load_trials(repo, options);
scenario_template = build_scenarios(options);
validate_scenario_matrix(scenario_template, options);
planned = numel(trials)*numel(scenario_template);
run = [];
if options.write_results
    run = create_run(repo, options, planned, trials);
    Result_Log_Stage(run, 'INFO', 'setup', ...
        'Offline WZ SRO distortion stress replay started for %d cases.', planned);
end

rows = repmat(empty_row(), 0, 1);
try
    for trial_index = 1:numel(trials)
        trial = trials(trial_index);
        for scenario_index = 1:numel(scenario_template)
            scenario = scenario_template(scenario_index);
            noise_seed = scenario_noise_seed(options.rng_seed, ...
                trial_index, scenario);
            raw = apply_scenario(trial.raw, trial.cfg, scenario, noise_seed);
            trial_cfg = trial.cfg;
            trial_cfg.receiver.sro_interval_consistency_limit_samples = ...
                options.sro_interval_consistency_limit_samples;
            trial_cfg.receiver.sro_decision_policy = ...
                options.sro_decision_policy;
            trial_cfg.receiver.sro_observation_oversample_factor = factor;
            no_sro_cfg = trial_cfg;
            no_sro_cfg.receiver.max_abs_sro_ppm = 0;
            mode_b = decode_manual_case(raw, trial.tx_ref, no_sro_cfg);
            mode_c = decode_production_case(raw, trial.tx_ref, trial_cfg);
            [oracle, oracle_source_signature] = oracle_capture( ...
                trial.raw, raw, trial_cfg, scenario);
            mode_d = decode_manual_case(oracle, trial.tx_ref, no_sro_cfg);
            mode_d.source_injection_signature = oracle_source_signature;
            row = make_row(trial, scenario, mode_b, mode_c, mode_d, ...
                noise_seed);
            rows(end+1,1) = row; %#ok<AGROW>
            if options.write_results
                Result_Log_Stage(run, 'INFO', 'case', ...
                    '%s/%s outcome=%s C_applied=%d C_reason=%s.', ...
                    trial.label, scenario.label, row.outcome, ...
                    mode_c.sro_applied, mode_c.sro_reason);
            end
        end
    end
    validate_row_matrix(rows, trials, scenario_template);
    guard = validate_rows(rows);
    if options.write_results
        write_outputs(run, rows, trials, options, guard);
        status = 'completed';
        if ~guard.ok
            status = 'completed_with_failures';
        end
        counts = result_counts(rows);
        Result_Update_Run_Info(run, struct('counts', counts, ...
            'safety', struct('preflight','not_applicable', ...
            'initial_outputs','not_applicable','shutdown','not_applicable', ...
            'shutdown_readback','not_applicable')));
        Result_Finalize_Run(run, status, 'normal_completion', ...
            output_artifacts(trials), ...
            guard.detail);
    end
catch exception
    if options.write_results && ~isempty(run)
        failure = struct('options',options,'rows',rows,'trials',trials);
        if strcmp(options.source,'real'), failure = msiq.analysis_record(failure); end
        if strcmp(options.source,'synthetic') && exist('raw','var'), failure.raw = raw; end
        msiq.save_failure(run.OutputDir,failure);
        Result_Log_Stage(run, 'ERROR', 'failure', '%s', exception.message);
        Result_Finalize_Run(run, 'failed', 'processing_failed', {}, ...
            exception.message);
    end
    rethrow(exception);
end

report = struct('ok', guard.ok, 'guard', guard, 'rows', rows, ...
    'trials', trials, 'scenarios', scenario_template, ...
    'run_dir', empty_path(run), 'offline_only', true, ...
    'source', options.source,'sro_decision_policy',options.sro_decision_policy, ...
    'sro_observation_oversample_factor',factor);
end

function run = create_run(repo, options, planned, trials)
source_paths = {};
for k = 1:numel(trials)
    source_paths{end+1} = trials(k).source_path; %#ok<AGROW>
    if ~isempty(trials(k).bundle_path)
        source_paths{end+1} = trials(k).bundle_path; %#ok<AGROW>
    end
end
parameters = struct('global_sro_ppm', options.global_sro_ppm, ...
    'snr_values_db', options.snr_values_db, ...
    'echo_amplitudes', options.echo_amplitudes, ...
    'echo_delays_symbols', options.echo_delays_symbols, ...
    'echo_combination_mode', 'cartesian', ...
    'noise_realization_policy', 'same_per_capture_scaled_by_snr', ...
    'profile_ppm_pairs', options.profile_ppm_pairs, ...
    'sro_decision_policy', options.sro_decision_policy, ...
    'sro_observation_oversample_factor', ...
    options.sro_observation_oversample_factor, ...
    'source', options.source,'options',options, ...
    'effective_trials',msiq.analysis_record(trials));
run_cfg = struct('ProjectRoot', repo, 'ResultsRoot', options.results_root, ...
    'RunType', 'analysis', 'NameParts', {{'WZ_SRO_distortion_stress'}}, ...
    'RunPurpose', 'validation', 'ExecutionMode', 'offline_analysis', ...
    'EntryPoint', 'msiq.run_wz_sro_distortion_stress', ...
    'Parameters', parameters, ...
    'Counts', struct('planned', planned, 'executed', 0, ...
    'succeeded', 0, 'failed', 0, 'invalid', 0), ...
    'SourceRuns', {source_paths}, 'Artifacts', {output_artifacts(trials)});
run = Result_Create_Run(run_cfg);
end

function trials = load_trials(repo, options)
if strcmp(options.source, 'synthetic')
    cfg = msiq.build_config('v2_traditional_wz');
    [waveforms, tx_ref] = msiq.generate_waveforms(cfg, ...
        cfg.experiment.seed_values(1));
    raw = msiq.simulate_capture(waveforms, cfg, 'A', struct( ...
        'snr_db', 42, 'channel_matrix', eye(2), ...
        'image_matrix', zeros(2), 'capture_repetitions', 3, ...
        'segment_padding_samples', 0, 'rng_seed', options.rng_seed));
    trials = struct('label','synthetic_three_frame', ...
        'repetitions',3,'raw',raw,'tx_ref',tx_ref,'cfg',cfg, ...
        'source_path','synthetic://three_frame_control', ...
        'bundle_path','');
    return
end

root = fullfile(repo, 'results', 'manual_loopback', ...
    'rdiv_compare_20260821_091514', 'trials');
names = {'02_DIV4','04_DIV4'};
trials = repmat(struct('label','','repetitions',3,'raw',struct(), ...
    'tx_ref',struct(),'cfg',struct(),'source_path','','bundle_path',''), ...
    1, numel(names));
for k = 1:numel(names)
    trial_dir = fullfile(root, names{k});
    rx_path = fullfile(trial_dir, 'rx', 'diagnostics', 'raw_capture.mat');
    tx_path = fullfile(trial_dir, 'tx', 'diagnostics', ...
        'tx_reference_bundle.mat');
    if ~isfile(rx_path) || ~isfile(tx_path)
        error('msiq:sroStress:InputMissing', ...
            'Missing long-window capture or reference for %s.', names{k});
    end
    loaded_rx = load(rx_path, 'raw');
    loaded_tx = msiq.load_reference_bundle(tx_path);
    cfg = msiq.build_config('v2_traditional_wz');
    cfg.waveform = loaded_tx.bundle.dsp_config.waveform;
    cfg.receiver = loaded_tx.bundle.dsp_config.receiver;
    cfg.waveform.architecture = 'single_complex_stream';
    trials(k).label = ['real_' names{k}];
    trials(k).raw = normalize_pair(loaded_rx.raw);
    trials(k).tx_ref = loaded_tx.bundle.tx_ref;
    trials(k).cfg = cfg;
    trials(k).source_path = rx_path;
    trials(k).bundle_path = tx_path;
end
end

function scenarios = build_scenarios(options)
scenarios = repmat(empty_scenario(), 0, 1);
families = cellstr(string(options.families));
if any(strcmp(families, 'clean'))
    scenarios(end+1,1) = scenario('clean_long_window','clean', ...
        options.global_sro_ppm,NaN,NaN,NaN,NaN,NaN);
end
if any(strcmp(families, 'noise'))
    for snr = options.snr_values_db(:).'
        scenarios(end+1,1) = scenario(sprintf('noise_snr_%gdB',snr), ...
            'noise',options.global_sro_ppm,snr,NaN,NaN,NaN,NaN); %#ok<AGROW>
    end
end
if any(strcmp(families, 'echo'))
    for amplitude = double(options.echo_amplitudes(:).')
        for delay = double(options.echo_delays_symbols(:).')
            scenarios(end+1,1) = scenario(sprintf('echo_a%.3g_d%gsym', ...
                amplitude,delay),'echo',options.global_sro_ppm,NaN, ...
                amplitude,delay,NaN,NaN); %#ok<AGROW>
        end
    end
end
if any(strcmp(families, 'varying'))
    pairs = double(options.profile_ppm_pairs);
    if size(pairs,2) ~= 2
        error('msiq:sroStress:Profile', ...
            'profile_ppm_pairs must have two columns.');
    end
    for k = 1:size(pairs,1)
        scenarios(end+1,1) = scenario(sprintf('varying_%g_to_%gppm', ...
            pairs(k,1),pairs(k,2)),'varying',NaN,NaN,NaN,NaN, ...
            pairs(k,1),pairs(k,2)); %#ok<AGROW>
    end
end
if isempty(scenarios)
    error('msiq:sroStress:EmptyPlan', 'No stress scenario family selected.');
end
end

function validate_scenario_options(options)
amplitudes = double(options.echo_amplitudes(:).');
delays = double(options.echo_delays_symbols(:).');
pairs = double(options.profile_ppm_pairs);
if isempty(amplitudes) || any(~isfinite(amplitudes)) || ...
        any(amplitudes <= 0) || numel(unique(amplitudes)) ~= numel(amplitudes)
    error('msiq:sroStress:EchoAmplitudes', ...
        'echo_amplitudes must contain unique positive finite values.');
end
if isempty(delays) || any(~isfinite(delays)) || any(delays <= 0) || ...
        numel(unique(delays)) ~= numel(delays)
    error('msiq:sroStress:EchoDelays', ...
        'echo_delays_symbols must contain unique positive finite values.');
end
if isempty(pairs) || size(pairs,2) ~= 2 || any(~isfinite(pairs(:)))
    error('msiq:sroStress:Profile', ...
        'profile_ppm_pairs must contain finite start/end pairs.');
end
end

function seed = scenario_noise_seed(base_seed, trial_index, case_spec)
if isfinite(case_spec.noise_snr_db)
    % Both SNR levels reuse one normalized noise realization per capture.
    seed = double(base_seed) + 1000*double(trial_index);
else
    seed = NaN;
end
end

function validate_scenario_matrix(scenarios, options)
families = cellstr(string(options.families));
expected = 0;
if any(strcmp(families,'clean')), expected = expected+1; end
if any(strcmp(families,'noise'))
    expected = expected+numel(options.snr_values_db);
end
if any(strcmp(families,'echo'))
    expected = expected+numel(options.echo_amplitudes)* ...
        numel(options.echo_delays_symbols);
end
if any(strcmp(families,'varying'))
    expected = expected+size(options.profile_ppm_pairs,1);
end
if numel(scenarios) ~= expected || ...
        numel(unique({scenarios.label})) ~= numel(scenarios)
    error('msiq:sroStress:ScenarioMatrix', ...
        'Scenario matrix count or labels are inconsistent.');
end
echo_rows = scenarios(strcmp({scenarios.family},'echo'));
if ~isempty(echo_rows)
    combinations = [[echo_rows.echo_amplitude].', ...
        [echo_rows.echo_delay_symbols].'];
    if size(unique(combinations,'rows'),1) ~= size(combinations,1)
        error('msiq:sroStress:EchoMatrix', ...
            'Echo amplitude/delay combinations must be unique.');
    end
end
varying_rows = scenarios(strcmp({scenarios.family},'varying'));
if ~isempty(varying_rows)
    means = ([varying_rows.profile_start_ppm] + ...
        [varying_rows.profile_end_ppm])/2;
    tolerance = eps(max(1,abs(double(options.global_sro_ppm))))*8;
    if any(abs(means-double(options.global_sro_ppm)) > tolerance)
        error('msiq:sroStress:VaryingMean', ...
            'Every varying SRO profile must have the same mean as global_sro_ppm.');
    end
end
end

function value = scenario(label,family,global_ppm,snr_db,echo_amp, ...
        echo_delay_symbols,profile_start,profile_end)
value = empty_scenario();
value.label = label;
value.family = family;
value.global_sro_ppm = global_ppm;
value.noise_snr_db = snr_db;
value.echo_amplitude = echo_amp;
value.echo_delay_symbols = echo_delay_symbols;
value.profile_start_ppm = profile_start;
value.profile_end_ppm = profile_end;
end

function raw = apply_scenario(raw,cfg,case_spec,rng_seed)
if isfinite(case_spec.profile_start_ppm)
    raw = inject_variable_sro(raw, case_spec.profile_start_ppm, ...
        case_spec.profile_end_ppm);
elseif isfinite(case_spec.global_sro_ppm) && case_spec.global_sro_ppm ~= 0
    raw = inject_global_sro(raw, case_spec.global_sro_ppm);
end
if isfinite(case_spec.noise_snr_db)
    raw = add_awgn(raw, case_spec.noise_snr_db, rng_seed);
end
if isfinite(case_spec.echo_amplitude)
    samples_per_symbol = raw.sample_rate_hz/cfg.waveform.symbol_rate_hz;
    delay = max(1,round(case_spec.echo_delay_symbols* samples_per_symbol));
    raw = add_echo(raw, case_spec.echo_amplitude, delay);
end
end

function [oracle, source_signature] = oracle_capture( ...
        pristine, stressed, cfg, case_spec) %#ok<INUSD>
source_signature = capture_signature(stressed);
if isfinite(case_spec.profile_start_ppm)
    oracle = undo_variable_sro(stressed, case_spec.profile_start_ppm, ...
        case_spec.profile_end_ppm, size(pristine.samples,1));
elseif isfinite(case_spec.global_sro_ppm) && case_spec.global_sro_ppm ~= 0
    [oracle,~] = msiq.dsp.correct_raw_sro(stressed, ...
        case_spec.global_sro_ppm);
else
    oracle = stressed;
end
% Keep this explicit: D is a known-injection oracle, not a production path.
oracle.oracle_reference = true;
end

function output = decode_production_case(raw, tx_ref, cfg)
output = empty_case();
output.input_signature = capture_signature(raw);
try
    decoded = msiq.decode_capture(raw, tx_ref, cfg);
    stream = decoded.primary_streams(1);
    sync = decoded.synchronization;
    output.ok = true;
    output.decodable = decoded.pass && stream.pass;
    output.selected_frame_start = sync.frame_start_sample;
    output.sync = sync;
    output.sro_ppm = sync.sro_ppm;
    output.sro_applied = sync.sro_applied;
    output.sro_reliable = sync.sro_reliable;
    output.sro_recommended = sync.sro_recommended;
    output.sro_sigma_ppm = sync.sro_sigma_ppm;
    output.sro_fit_residual_samples = sync.sro_fit_residual_samples;
    output.sro_max_interval_deviation_samples = ...
        sync.sro_max_interval_deviation_samples;
    output.sro_interval_consistency_limit_samples = ...
        sync.sro_interval_consistency_limit_samples;
    output.sro_peak_count = numel(sync.sro_peak_samples);
    output.sro_complete_peak_count = numel(sync.sro_complete_peak_samples);
    output.sro_reason = sync.sro_reason;
    output.sro_stage = sync.sro_correction_stage;
    output.sro_low_rate_resample_applied = ...
        sync.sro_low_rate_resample_applied;
    output.metrics = stream_metrics(stream);
catch exception
    output.error_identifier = exception.identifier;
    output.error_message = exception.message;
    output.sro_reason = 'decode_failed';
end
end

function output = decode_manual_case(raw, tx_ref, cfg)
output = empty_case();
output.input_signature = capture_signature(raw);
try
    [baseband,~] = msiq.dsp.prepare_capture(raw,cfg);
    [~,sync] = msiq.dsp.synchronize_single_wz( ...
        baseband,tx_ref,cfg,true);
    corrected = sync.corrected_capture(:);
    starts = sync.candidate_frame_starts(:);
    if isempty(starts), starts = sync.frame_start_sample; end
    [~,selected] = min(abs(starts-sync.frame_start_sample));
    first = round(starts(selected));
    length_samples = round(tx_ref.frame.symbol_count* ...
        cfg.receiver.single_samples_per_symbol);
    last = first+length_samples-1;
    if first < 1 || last > numel(corrected)
        error('msiq:sroStress:FrameBounds', ...
            'Selected complete frame is outside capture.');
    end
    pair = tx_ref.pairs(find(strcmpi({tx_ref.pairs.name},'A'),1));
    equalizer = msiq.dsp.equalize_single_wz(corrected(first:last),pair,cfg);
    output.ok = true;
    output.decodable = true;
    output.selected_frame_start = first;
    output.sync = rmfield(sync,'corrected_capture');
    output.sro_ppm = sync.sro_ppm;
    output.sro_applied = sync.sro_applied;
    output.sro_reliable = sync.sro_reliable;
    output.sro_recommended = sync.sro_recommended;
    output.sro_sigma_ppm = sync.sro_sigma_ppm;
    output.sro_fit_residual_samples = sync.sro_fit_residual_samples;
    output.sro_max_interval_deviation_samples = ...
        sync.sro_max_interval_deviation_samples;
    output.sro_interval_consistency_limit_samples = ...
        sync.sro_interval_consistency_limit_samples;
    output.sro_peak_count = numel(sync.sro_peak_samples);
    output.sro_complete_peak_count = numel(sync.sro_complete_peak_samples);
    output.sro_reason = sync.sro_reason;
    output.sro_stage = 'low_rate_legacy';
    output.sro_low_rate_resample_applied = sync.sro_applied;
    output.metrics = decode_metrics(equalizer.symbols,pair,cfg);
    output.decodable = output.metrics.pass;
catch exception
    output.error_identifier = exception.identifier;
    output.error_message = exception.message;
    output.sro_reason = 'decode_failed';
end
end

function metrics = stream_metrics(stream)
metrics = struct('mer_db',stream.mer_db,'evm_rms',stream.evm_rms, ...
    'pre_fec_ber',stream.pre_fec_ber,'post_fec_ber',stream.post_fec_ber, ...
    'bler',stream.bler,'pass',stream.pass);
end

function metrics = decode_metrics(symbols,pair,cfg)
known = pair.receiver_known(1);
reference = pair.metrics_only(1);
[tracked,tracking] = msiq.dsp.pilot_track(symbols(:),known,cfg);
payload = tracked(known.frame.payload_positions_frame);
payload = payload(isfinite(real(payload)) & isfinite(imag(payload)));
payload = payload(1:min(numel(payload),reference.payload_symbol_count));
if isempty(payload)
    error('msiq:sroStress:Payload','No finite payload symbols.');
end
indices = qamdemod(payload,cfg.waveform.modulation_order, ...
    'UnitAveragePower',true);
decisions = qammod(indices,cfg.waveform.modulation_order, ...
    'UnitAveragePower',true);
error_value = payload-decisions;
evm = sqrt(mean(abs(error_value).^2)/max(mean(abs(decisions).^2),eps));
noise_variance = max([tracking.noise_variance, ...
    mean(abs(error_value).^2),1e-10]);
llr = qamdemod(payload,cfg.waveform.modulation_order, ...
    'OutputType','approxllr','UnitAveragePower',true, ...
    'NoiseVariance',noise_variance);
count = min(numel(llr),numel(reference.fec.scramble_bits));
fec = msiq.fec.decode_soft(double(llr(1:count)).*(1-2* ...
    double(reference.fec.scramble_bits(1:count))),reference.fec,cfg);
metrics = struct('mer_db',-20*log10(max(evm,eps)), ...
    'evm_rms',evm,'pre_fec_ber',fec.pre_fec_ber, ...
    'post_fec_ber',fec.post_fec_ber,'bler',fec.bler, ...
    'pass',fec.valid && fec.block_count >= 1 && ...
    fec.parity_converged && fec.post_fec_ber == 0 && fec.bler == 0);
end

function row = make_row(trial,case_spec,mode_b,mode_c,mode_d,noise_seed)
row = empty_row();
row.label = [trial.label '_' case_spec.label];
row.family = case_spec.family;
row.source = trial.label;
row.source_path = trial.source_path;
row.global_sro_ppm = case_spec.global_sro_ppm;
row.profile_start_ppm = case_spec.profile_start_ppm;
row.profile_end_ppm = case_spec.profile_end_ppm;
row.noise_snr_db = case_spec.noise_snr_db;
row.echo_amplitude = case_spec.echo_amplitude;
row.echo_delay_symbols = case_spec.echo_delay_symbols;
row.noise_seed = noise_seed;
row.mode_b = mode_b;
row.mode_c = mode_c;
row.mode_d = mode_d;
row.shared_injection_verified = ...
    isequaln(mode_b.input_signature, mode_c.input_signature) && ...
    isequaln(mode_b.input_signature, mode_d.source_injection_signature);
row.delta_c_vs_b_db = mode_c.metrics.mer_db-mode_b.metrics.mer_db;
row.delta_d_vs_c_db = mode_d.metrics.mer_db-mode_c.metrics.mer_db;
row.outcome = outcome_label(mode_b,mode_c,mode_d);
end

function outcome = outcome_label(b,c,d)
if ~b.ok || ~c.ok || ~d.ok
    outcome = 'processing_failure';
elseif ~b.decodable && ~c.decodable && ~d.decodable
    outcome = 'invalid_all_decode_failed';
elseif c.sro_applied && ~c.sro_reliable
    outcome = 'applied_unreliable';
elseif c.sro_applied && isfinite(c.metrics.mer_db) && ...
        isfinite(b.metrics.mer_db) && c.metrics.mer_db < b.metrics.mer_db
    outcome = 'applied_and_degraded';
elseif c.sro_applied
    outcome = 'applied_and_improved';
elseif d.decodable && isfinite(d.metrics.mer_db) && ...
        isfinite(b.metrics.mer_db) && d.metrics.mer_db > b.metrics.mer_db
    outcome = 'held_with_recovery_available';
else
    outcome = 'held_without_observed_recovery';
end
end

function guard = validate_rows(rows)
outcomes = {rows.outcome};
bad_unreliable = strcmp(outcomes,'applied_unreliable').';
bad_degraded = strcmp(outcomes,'applied_and_degraded').';
bad_low_rate = false(size(rows));
bad_shared_input = ~[rows.shared_injection_verified].';
bad_varying_applied = false(size(rows));
bad_varying_changed = false(size(rows));
bad_varying_reason = false(size(rows));
for k = 1:numel(rows)
    bad_low_rate(k) = rows(k).mode_c.sro_low_rate_resample_applied;
    if strcmp(rows(k).family,'varying')
        bad_varying_applied(k) = rows(k).mode_c.sro_applied;
        b_mer = rows(k).mode_b.metrics.mer_db;
        c_mer = rows(k).mode_c.metrics.mer_db;
        bad_varying_changed(k) = ~(isequaln(b_mer,c_mer) || ...
            (isfinite(b_mer) && isfinite(c_mer) && abs(b_mer-c_mer) <= 1e-9));
        reason = rows(k).mode_c.sro_reason;
        bad_varying_reason(k) = isempty(reason) || strcmp(reason,'applied');
    end
end
bad = bad_unreliable | bad_degraded | bad_low_rate | bad_shared_input | ...
    bad_varying_applied | bad_varying_changed | bad_varying_reason;
guard = struct('ok',~any(bad),'applied_unreliable',sum(bad_unreliable), ...
    'applied_and_degraded',sum(bad_degraded), ...
    'low_rate_double_correction',sum(bad_low_rate), ...
    'shared_injection_failures',sum(bad_shared_input), ...
    'varying_sro_applied',sum(bad_varying_applied), ...
    'varying_sro_changed',sum(bad_varying_changed), ...
    'varying_sro_missing_reason',sum(bad_varying_reason), ...
    'invalid_cases',sum(strcmp(outcomes,'invalid_all_decode_failed')), ...
    'processing_failures',sum(strcmp(outcomes,'processing_failure')), ...
    'detail',sprintf(['guards: applied_unreliable=%d, ', ...
    'applied_and_degraded=%d, low_rate_double_correction=%d, ', ...
    'shared_injection_failures=%d, varying_applied=%d, ', ...
    'varying_changed=%d, varying_missing_reason=%d, invalid=%d, ', ...
    'processing_failures=%d'], ...
    sum(bad_unreliable),sum(bad_degraded),sum(bad_low_rate), ...
    sum(bad_shared_input),sum(bad_varying_applied), ...
    sum(bad_varying_changed),sum(bad_varying_reason), ...
    sum(strcmp(outcomes,'invalid_all_decode_failed')), ...
    sum(strcmp(outcomes,'processing_failure'))));
end

function validate_row_matrix(rows,trials,scenarios)
scenario_count = numel(scenarios);
if numel(rows) ~= numel(trials)*scenario_count
    error('msiq:sroStress:RowMatrix', ...
        'Result row count does not match trials times scenarios.');
end
for trial_index = 1:numel(trials)
    first = (trial_index-1)*scenario_count+1;
    selected = rows(first:first+scenario_count-1);
    if ~all(strcmp({selected.source},trials(trial_index).label))
        error('msiq:sroStress:RowMatrix', ...
            'Result rows are not grouped by source capture.');
    end
    expected_labels = strcat(trials(trial_index).label,'_', ...
        {scenarios.label});
    if ~isequal({selected.label},expected_labels) || ...
            ~isequal({selected.family},{scenarios.family})
        error('msiq:sroStress:RowMatrix', ...
            'Result condition order differs from the scenario plan.');
    end
    noise_rows = selected(strcmp({selected.family},'noise'));
    if numel(noise_rows) > 1 && ...
            numel(unique([noise_rows.noise_seed])) ~= 1
        error('msiq:sroStress:NoiseReuse', ...
            'Noise SNR cases must reuse one noise realization per capture.');
    end
end
end

function counts = result_counts(rows)
outcomes = {rows.outcome};
counts = struct('planned',numel(rows),'executed',numel(rows), ...
    'succeeded',sum(~ismember(outcomes,{'processing_failure','invalid_all_decode_failed'})), ...
    'failed',sum(strcmp(outcomes,'processing_failure')), ...
    'invalid',sum(strcmp(outcomes,'invalid_all_decode_failed')));
end

function write_outputs(run,rows,trials,options,guard)
plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
msiq.import_summary(run,@(path) write_csv(path,rows),2, ...
    {'label','source','global_sro_ppm','noise_snr_db','B_mer_db', ...
    'C_mer_db','D_mer_db','C_pre_fec_ber','C_post_fec_ber','C_bler','状态'});
for k = 1:numel(trials)
    selected = strcmp({rows.source},trials(k).label);
    write_simple_csv(msiq.output_path(run, ...
        simple_summary_filename(trials(k).label)),rows(selected));
end
write_overview(msiq.output_path(run,'overview.png'),rows);
write_sources(msiq.output_path(run,'sources.txt'),trials,run.ProjectRoot);
if strcmp(options.output_level,'compact')
    rows = msiq.analysis_record(rows);
end
if strcmp(options.output_level,'compact') || strcmp(options.source,'real')
    trials = msiq.analysis_record(trials);
end
for k = 1:numel(trials)
    trials(k).source_sha256 = '';
    trials(k).bundle_sha256 = '';
    if isfile(trials(k).source_path)
        trials(k).source_sha256 = msiq.file_sha256(trials(k).source_path);
    end
    if isfile(trials(k).bundle_path)
        trials(k).bundle_sha256 = msiq.file_sha256(trials(k).bundle_path);
    end
end
save(msiq.output_path(run,'wz_sro_distortion_stress.mat'), ...
    'rows','trials','options','guard','-v7.3');
end

function write_csv(path,rows)
fid = Result_Open_File_Retry(path,'w','n','UTF-8');
cleanup = onCleanup(@()fclose(fid));
fprintf(fid,'%s',char(65279));
headers = {'label','family','source','global_sro_ppm', ...
    'profile_start_ppm','profile_end_ppm','noise_snr_db','noise_seed', ...
    'echo_amplitude','echo_delay_symbols','B_mer_db','C_mer_db', ...
    'D_mer_db','C_minus_B_db','D_minus_C_db','C_sro_ppm', ...
    'C_sro_sigma_ppm','C_fit_residual_samples', ...
    'C_max_interval_deviation_samples','C_peak_count', ...
    'C_complete_peak_count','C_reliable','C_recommended','C_raw_applied', ...
    'C_low_rate_resample','C_reason','B_pre_fec_ber','B_post_fec_ber', ...
    'B_bler','B_fec_pass','C_pre_fec_ber','C_post_fec_ber','C_bler', ...
    'C_fec_pass','D_pre_fec_ber','D_post_fec_ber','D_bler','D_fec_pass', ...
    'B_decodable','C_decodable','D_decodable', ...
    'shared_injection_verified','outcome','状态','repeat', ...
    'attempt','采集时间','原始数据文件','单次图片文件','错误代码','错误信息'};
units = repmat({'-'},size(headers));
units(4:6) = repmat({'ppm'},1,3);
units{7} = 'dB';
units{10} = 'symbol';
units(11:15) = repmat({'dB'},1,5);
units(16:17) = repmat({'ppm'},1,2);
units(18:19) = repmat({'samples'},1,2);
units(20:21) = repmat({'count'},1,2);
fprintf(fid,'%s\n',strjoin(headers,','));
fprintf(fid,'%s\n',strjoin(units,','));
for k = 1:numel(rows)
    r = rows(k); c = r.mode_c;
    values = {csv_text(r.label),csv_text(r.family),csv_text(r.source), ...
        number_csv(r.global_sro_ppm),number_csv(r.profile_start_ppm), ...
        number_csv(r.profile_end_ppm),number_csv(r.noise_snr_db), ...
        number_csv(r.noise_seed),number_csv(r.echo_amplitude), ...
        number_csv(r.echo_delay_symbols),number_csv(r.mode_b.metrics.mer_db), ...
        number_csv(c.metrics.mer_db),number_csv(r.mode_d.metrics.mer_db), ...
        number_csv(r.delta_c_vs_b_db),number_csv(r.delta_d_vs_c_db), ...
        number_csv(c.sro_ppm),number_csv(c.sro_sigma_ppm), ...
        number_csv(c.sro_fit_residual_samples), ...
        number_csv(c.sro_max_interval_deviation_samples), ...
        integer_csv(c.sro_peak_count), ...
        integer_csv(c.sro_complete_peak_count),logical_csv(c.sro_reliable), ...
        logical_csv(c.sro_recommended),logical_csv(c.sro_applied), ...
        logical_csv(c.sro_low_rate_resample_applied),csv_text(c.sro_reason), ...
        number_csv(r.mode_b.metrics.pre_fec_ber), ...
        number_csv(r.mode_b.metrics.post_fec_ber), ...
        number_csv(r.mode_b.metrics.bler),logical_csv(r.mode_b.metrics.pass), ...
        number_csv(c.metrics.pre_fec_ber),number_csv(c.metrics.post_fec_ber), ...
        number_csv(c.metrics.bler),logical_csv(c.metrics.pass), ...
        number_csv(r.mode_d.metrics.pre_fec_ber), ...
        number_csv(r.mode_d.metrics.post_fec_ber), ...
        number_csv(r.mode_d.metrics.bler),logical_csv(r.mode_d.metrics.pass), ...
        logical_csv(r.mode_b.decodable),logical_csv(r.mode_c.decodable), ...
        logical_csv(r.mode_d.decodable), ...
        logical_csv(r.shared_injection_verified),csv_text(r.outcome), ...
        csv_text(status_text(r)),'1','1','','','','',''};
    fprintf(fid,'%s\n',strjoin(values,','));
end
clear cleanup;
end

function write_simple_csv(path,rows)
fid = Result_Open_File_Retry(path,'w','n','UTF-8');
cleanup = onCleanup(@()fclose(fid));
fprintf(fid,'%s',char(65279));
fprintf(fid,'信号条件,B MER (dB),C MER (dB),C是否补偿,D MER (dB)\n');
for k = 1:numel(rows)
    r = rows(k);
    fprintf(fid,'%s,%.6f,%.6f,%s,%.6f\n', ...
        csv_text(condition_text(r)),r.mode_b.metrics.mer_db, ...
        r.mode_c.metrics.mer_db,csv_text(correction_text(r.mode_c)), ...
        r.mode_d.metrics.mer_db);
end
clear cleanup;
end


function write_overview(path,rows)
fig = figure('Visible','off','Color','w','Position',[100 100 1400 700]);
values = [rows.delta_c_vs_b_db];
values(~isfinite(values)) = NaN;
bar(values,'FaceColor',[0 0.447 0.741]);
hold on; yline(0,'k-'); hold off;
grid on; box on;
set(gca,'XTick',1:numel(rows),'XTickLabel',{rows.label}, ...
    'XTickLabelRotation',45,'FontName','Microsoft YaHei');
ylabel('C - B MER (dB)');
title('WZ SRO distortion stress: raw-input correction versus no correction');
if ~msiq.plot_archive('export',fig,path,'print',300)
    print(fig,path,'-dpng','-r300');
end
close(fig);
end

function write_sources(path,trials,repo)
fid = Result_Open_File_Retry(path,'w','n','UTF-8');
cleanup = onCleanup(@()fclose(fid));
for k = 1:numel(trials)
    value = trials(k).source_path;
    if startsWith(value,repo)
        value = strrep(value,[repo filesep],'');
    end
    fprintf(fid,'%s\n',value);
    if ~isempty(trials(k).bundle_path)
        value = trials(k).bundle_path;
        if startsWith(value,repo)
            value = strrep(value,[repo filesep],'');
        end
        fprintf(fid,'%s\n',value);
    end
end
clear cleanup;
end

function value = inject_global_sro(raw,ppm)
scale = 1+ppm*1e-6;
if scale <= 0
    error('msiq:sroStress:Scale','Invalid global SRO scale.');
end
count = floor((size(raw.samples,1)-1)*scale)+1;
source_axis = (0:count-1).'/scale;
value = raw;
value.samples = zeros(count,size(raw.samples,2));
for k = 1:size(raw.samples,2)
    value.samples(:,k) = interp1((0:size(raw.samples,1)-1).', ...
        raw.samples(:,k),source_axis,'pchip');
end
value.time_axes = rebuild_time_axes(raw,count);
end

function value = inject_variable_sro(raw,start_ppm,end_ppm)
[~,output_axis,source_axis] = variable_map(size(raw.samples,1), ...
    start_ppm,end_ppm);
value = raw;
value.samples = zeros(numel(output_axis),size(raw.samples,2));
for k = 1:size(raw.samples,2)
    value.samples(:,k) = interp1((0:size(raw.samples,1)-1).', ...
        raw.samples(:,k),source_axis,'pchip');
end
value.time_axes = rebuild_time_axes(raw,numel(output_axis));
end

function value = undo_variable_sro(raw,start_ppm,end_ppm,original_count)
[mapping,~,~] = variable_map(original_count,start_ppm,end_ppm);
target = min(mapping(:),size(raw.samples,1)-1);
value = raw;
value.samples = zeros(original_count,size(raw.samples,2));
for k = 1:size(raw.samples,2)
    value.samples(:,k) = interp1((0:size(raw.samples,1)-1).', ...
        raw.samples(:,k),target,'pchip','extrap');
end
value.time_axes = rebuild_time_axes(raw,original_count);
end

function [mapping,output_axis,source_axis] = variable_map(count,start_ppm,end_ppm)
input_axis = (0:count-1).';
scale = 1 + (start_ppm + (end_ppm-start_ppm)* ...
    input_axis/max(count-1,1))*1e-6;
mapping = cumtrapz(input_axis,scale);
output_axis = (0:floor(mapping(end))).';
source_axis = interp1(mapping,input_axis,output_axis,'pchip');
end

function value = add_awgn(raw,snr_db,seed)
stream = RandStream('mt19937ar','Seed',seed);
z = complex(raw.samples(:,1),raw.samples(:,2));
signal_power = mean(abs(z).^2);
noise_power = signal_power/10^(snr_db/10);
noise = sqrt(noise_power/2)*(randn(stream,size(z))+1j*randn(stream,size(z)));
value = raw;
z = z+noise;
value.samples = [real(z),imag(z)];
end

function value = add_echo(raw,amplitude,delay_samples)
z = complex(raw.samples(:,1),raw.samples(:,2));
delay_samples = round(delay_samples);
if delay_samples < 1 || delay_samples >= numel(z)
    error('msiq:sroStress:EchoDelay','Echo delay is outside capture.');
end
delayed = zeros(size(z));
delayed(delay_samples+1:end) = z(1:end-delay_samples);
value = raw;
z = z+amplitude*delayed;
value.samples = [real(z),imag(z)];
end

function value = rebuild_time_axes(raw,count)
start_time = raw.time_axes(1,1);
time_axis = start_time+(0:count-1).'/raw.sample_rate_hz;
value = repmat(time_axis,1,size(raw.samples,2));
end

function raw = normalize_pair(capture)
records = capture.channels(1:2);
time = cell(1,2); samples = cell(1,2); rate = zeros(1,2);
for k = 1:2
    time{k} = double(records(k).time_axis_s(:));
    samples{k} = double(records(k).samples(:));
    rate(k) = 1/median(diff(time{k}));
end
if numel(time{1}) == numel(time{2}) && ...
        max(abs(time{1}-time{2})) <= 0.05/min(rate)
    common_time = time{1};
    data = [samples{1},samples{2}];
else
    start_time = max(cellfun(@(x)x(1),time));
    end_time = min(cellfun(@(x)x(end),time));
    common_rate = min(rate);
    count = floor((end_time-start_time)*common_rate)+1;
    common_time = start_time+(0:count-1).'/common_rate;
    data = [interp1(time{1},samples{1},common_time,'linear'), ...
        interp1(time{2},samples{2},common_time,'linear')];
end
raw = struct('samples',data,'time_axes',repmat(common_time,1,2), ...
    'sample_rate_hz',1/median(diff(common_time)), ...
    'payload_pair','A','full_scale',NaN);
end

function artifacts = output_artifacts(trials)
artifacts = {'data/plot_data.mat','summary.csv','overview.png','data/sources.txt', ...
    'data/wz_sro_distortion_stress.mat'};
for k = 1:numel(trials)
    artifacts{end+1} = ['data/' simple_summary_filename(trials(k).label)]; %#ok<AGROW>
end
end

function name = simple_summary_filename(source)
name = ['summary_' source_display_name(source) '.csv'];
name = regexprep(name,'[^A-Za-z0-9_.-]','_');
end

function name = source_display_name(source)
name = char(string(source));
if startsWith(name,'real_')
    name = extractAfter(name,5);
end
end

function text = condition_text(row)
switch row.family
    case 'clean'
        text = sprintf('固定 %g ppm',row.global_sro_ppm);
    case 'noise'
        text = sprintf('固定 %g ppm，SNR %g dB', ...
            row.global_sro_ppm,row.noise_snr_db);
    case 'echo'
        text = sprintf('固定 %g ppm，回波 %g%%，延迟 %g 符号', ...
            row.global_sro_ppm,100*row.echo_amplitude, ...
            row.echo_delay_symbols);
    case 'varying'
        text = sprintf('SRO %g 至 %g ppm', ...
            row.profile_start_ppm,row.profile_end_ppm);
    otherwise
        text = row.label;
end
end

function text = correction_text(value)
if value.sro_applied
    text = '补偿';
else
    text = ['未补偿：' reason_text(value.sro_reason)];
end
end

function text = reason_text(reason)
switch char(string(reason))
    case 'insufficient_sync_peaks'
        text = '同步峰不足';
    case 'ambiguous_awg_boundary_phase'
        text = '帧边界不明确';
    case 'insufficient_full_window_peaks'
        text = '完整窗口同步峰不足';
    case 'fit_uncertainty_unavailable'
        text = '无法计算估计不确定度';
    case 'internal_interval_scatter'
        text = '同步峰间隔不一致';
    case 'estimate_out_of_range'
        text = '估计值超出范围';
    case 'estimate_within_fit_uncertainty'
        text = '估计值未超过估计不确定度';
    case 'decode_failed'
        text = '解调失败';
    case 'disabled'
        text = '补偿已禁用';
    otherwise
        text = char(string(reason));
end
end

function text = number_csv(value)
text = sprintf('%.17g',double(value));
end

function text = integer_csv(value)
text = sprintf('%d',round(double(value)));
end

function text = logical_csv(value)
text = sprintf('%d',logical(value));
end

function value = empty_scenario()
value = struct('label','','family','','global_sro_ppm',NaN, ...
    'noise_snr_db',NaN,'echo_amplitude',NaN,'echo_delay_symbols',NaN, ...
    'profile_start_ppm',NaN,'profile_end_ppm',NaN);
end

function value = empty_case()
value = struct('ok',false,'decodable',false,'selected_frame_start',NaN, ...
    'sync',struct(),'sro_ppm',NaN,'sro_applied',false, ...
    'sro_reliable',false,'sro_recommended',false,'sro_sigma_ppm',NaN, ...
    'sro_fit_residual_samples',NaN,'sro_peak_count',0, ...
    'sro_complete_peak_count',0,'sro_reason','','sro_stage','', ...
    'sro_max_interval_deviation_samples',NaN, ...
    'sro_interval_consistency_limit_samples',NaN, ...
    'sro_low_rate_resample_applied',false,'input_signature',[], ...
    'source_injection_signature',[],'error_identifier','', ...
    'error_message','','metrics',empty_metrics());
end

function value = empty_metrics()
value = struct('mer_db',NaN,'evm_rms',NaN,'pre_fec_ber',NaN, ...
    'post_fec_ber',NaN,'bler',NaN,'pass',false);
end

function value = empty_row()
value = struct('label','','family','','source','','source_path','', ...
    'global_sro_ppm',NaN, ...
    'profile_start_ppm',NaN,'profile_end_ppm',NaN,'noise_snr_db',NaN, ...
    'noise_seed',NaN,'echo_amplitude',NaN,'echo_delay_symbols',NaN, ...
    'mode_b',empty_case(), ...
    'mode_c',empty_case(),'mode_d',empty_case(), ...
    'shared_injection_verified',false,'delta_c_vs_b_db',NaN, ...
    'delta_d_vs_c_db',NaN,'outcome','');
end

function text = status_text(row)
if strcmp(row.outcome,'processing_failure')
    text = '失败';
elseif strcmp(row.outcome,'invalid_all_decode_failed')
    text = '无效';
else
    text = '成功';
end
end

function text = csv_text(value)
text = char(string(value));
text = strrep(text,',','/');
text = strrep(text,'"','""');
if contains(text,',') || contains(text,'"')
    text = ['"' text '"'];
end
end


function value = empty_path(run)
if isempty(run), value = ''; else, value = run.OutputDir; end
end

function value = merge_options(base,override)
value = base;
names = fieldnames(override);
for k = 1:numel(names)
    value.(names{k}) = override.(names{k});
end
end

function signature = capture_signature(raw)
samples = double(raw.samples);
signature = [size(samples,1),size(samples,2),double(raw.sample_rate_hz), ...
    sum(samples(:)),sum(samples(:).^2)];
end
