function output = run_wz_sro_raw_input_regression(options)
%RUN_WZ_SRO_RAW_INPUT_REGRESSION Offline A/B/C/D regression for WZ SRO.
% C uses the production raw-input two-pass receiver. No instrument API is used.

if nargin < 1 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:sroRegression:Options', 'options must be a scalar struct.');
end
repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo, 'code', 'result_management'));
defaults = struct('results_root',repo, ...
    'legacy_result_path',fullfile(repo, 'results', 'analysis', ...
    'wz_sro_production_regression_20260824_111040', ...
    'wz_sro_production_regression.mat'));
options = merge_options(defaults, options);
policy = msiq.output_policy(options);
options.output_level = policy.output_level;
run_dir = '';
run = [];
if policy.write_results
    results_root = options.results_root;
    [parent,category] = fileparts(results_root);
    if strcmp(category,'analysis'), results_root = parent; end
    run = Result_Create_Run(struct('ProjectRoot',repo,'ResultsRoot',results_root, ...
        'RunType','analysis','NameParts',{{'wz_sro_raw_input_regression'}}, ...
        'EntryPoint','msiq.run_wz_sro_raw_input_regression', ...
        'ExecutionMode','offline_analysis','Parameters',struct('options',options)));
    run_dir = run.OutputDir;
end

rows = struct([]);
try
ppm_values = [-200 -100 -50 -25 0 25 50 100 200];
trials = regression_trials(repo);
legacy_rows = load_legacy_rows(options.legacy_result_path);
rows = repmat(empty_row(), 1, numel(trials)*numel(ppm_values));
row_index = 0;
for trial_index = 1:numel(trials)
    trial = trials(trial_index);
    [raw, tx_ref, cfg, raw_path, bundle_path] = load_trial(trial);
    trials(trial_index).effective_config = cfg;
    no_sro_cfg = cfg;
    no_sro_cfg.receiver.max_abs_sro_ppm = 0;
    baseline = decode_manual_case(raw, tx_ref, no_sro_cfg, NaN);
    if ~baseline.ok
        error('msiq:sroRegression:Baseline', '%s baseline failed: %s', ...
            trial.label, baseline.error_message);
    end
    for ppm_index = 1:numel(ppm_values)
        injected_ppm = ppm_values(ppm_index);
        epsilon = injected_ppm*1e-6;
        injected = inject_raw_time_scale(raw, epsilon);
        target = map_frame_start(baseline.selected_frame_start, epsilon);
        mode_b = decode_manual_case(injected, tx_ref, no_sro_cfg, target);
        mode_c = decode_production_case(injected, tx_ref, cfg);
        [oracle_raw, ~] = msiq.dsp.correct_raw_sro(injected, injected_ppm);
        mode_d = decode_manual_case(oracle_raw, tx_ref, no_sro_cfg, ...
            baseline.selected_frame_start);
        row_index = row_index + 1;
        rows(row_index) = make_row(trial, raw_path, bundle_path, injected_ppm, ...
            baseline, mode_b, mode_c, mode_d, target, legacy_rows);
        fprintf('%s %+4d ppm: B %.3f, C %.3f (%s), D %.3f\n', ...
            trial.label, injected_ppm, mode_b.metrics.mer_db, ...
            mode_c.metrics.mer_db, mode_c.sro_reason, mode_d.metrics.mer_db);
    end
end
rows = rows(1:row_index);
validate_rows(rows);
if policy.write_results
record = struct('rows',rows,'trials',trials,'ppm_values',ppm_values,'options',options);
if ~policy.save_raw, record = msiq.analysis_record(record); end
record.sources = msiq.analysis_record(rmfield(rows, ...
    {'baseline','mode_b','mode_c','mode_d'}));
msiq.atomic_save(msiq.output_path(run,'wz_sro_raw_input_regression.mat'),record);
msiq.import_summary(run,@(path) write_csv(path,rows),1);
Result_Write_Sources(run, unique(cellfun(@fileparts,{rows.raw_path}, ...
    'UniformOutput',false)));
Result_Update_Run_Info(run,struct('counts',struct('planned',numel(rows), ...
    'executed',numel(rows),'succeeded',numel(rows),'failed',0,'invalid',0), ...
    'source_runs',{unique([{rows.raw_path},{rows.bundle_path}])}));
Result_Finalize_Run(run,'completed','normal_completion',[], '');
end
output = struct('run_dir',run_dir,'rows',rows,'trials',trials, ...
    'ppm_values',ppm_values,'offline_only',true);
catch exception
    if ~isempty(run)
        msiq.save_failure(run_dir,msiq.analysis_record(struct('options',options,'rows',rows)));
        Result_Log_Stage(run,'ERROR','failure','%s',exception.message);
        Result_Finalize_Run(run,'failed','processing_failed',[],exception.message);
    end
    rethrow(exception);
end
end

function trials = regression_trials(repo)
trials = [ ...
    struct('label','one_frame_01_DIV2','repetitions',1,'root', ...
    fullfile(repo,'results','manual_loopback', ...
    'rdiv_compare_1frame_20260821_090329'),'trial','01_DIV2'), ...
    struct('label','one_frame_03_DIV2','repetitions',1,'root', ...
    fullfile(repo,'results','manual_loopback', ...
    'rdiv_compare_1frame_20260821_090329'),'trial','03_DIV2'), ...
    struct('label','three_frame_02_DIV4','repetitions',3,'root', ...
    fullfile(repo,'results','manual_loopback', ...
    'rdiv_compare_20260821_091514'),'trial','02_DIV4'), ...
    struct('label','three_frame_04_DIV4','repetitions',3,'root', ...
    fullfile(repo,'results','manual_loopback', ...
    'rdiv_compare_20260821_091514'),'trial','04_DIV4')];
end

function [raw, tx_ref, cfg, raw_path, bundle_path] = load_trial(trial)
diagnostics = fullfile(trial.root, 'trials', trial.trial, 'rx', 'diagnostics');
raw_path = fullfile(diagnostics, 'raw_capture.mat');
bundle_path = fullfile(diagnostics, 'tx_reference_bundle.mat');
if ~isfile(raw_path) || ~isfile(bundle_path)
    error('msiq:sroRegression:InputMissing', ...
        'Missing raw/reference for %s.', trial.label);
end
capture = load(raw_path, 'raw');
reference = msiq.load_reference_bundle(bundle_path);
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform = reference.bundle.dsp_config.waveform;
cfg.receiver = reference.bundle.dsp_config.receiver;
cfg.waveform.architecture = 'single_complex_stream';
tx_ref = reference.bundle.tx_ref;
raw = normalize_pair(capture.raw);
end

function row = make_row(trial, raw_path, bundle_path, ppm, baseline, ...
        mode_b, mode_c, mode_d, target, legacy_rows)
row = empty_row();
row.label = trial.label;
row.trial = trial.trial;
row.frame_repetitions = trial.repetitions;
row.raw_path = raw_path;
row.bundle_path = bundle_path;
row.injected_ppm = ppm;
row.baseline = baseline;
row.mode_b = mode_b;
row.mode_c = mode_c;
row.mode_d = mode_d;
row.injected_target_frame_start = target;
row.delta_c_vs_b_db = mode_c.metrics.mer_db-mode_b.metrics.mer_db;
row.delta_d_vs_c_db = mode_d.metrics.mer_db-mode_c.metrics.mer_db;
row.delta_d_vs_a_db = mode_d.metrics.mer_db-baseline.metrics.mer_db;
row.legacy_c_mer_db = legacy_mer(legacy_rows, trial.label, ppm);
row.delta_new_vs_legacy_c_db = mode_c.metrics.mer_db-row.legacy_c_mer_db;
row.outcome = outcome_label(mode_b, mode_c, mode_d);
end

function output = decode_production_case(raw, tx_ref, cfg)
output = empty_case();
try
    decoded = msiq.decode_capture(raw, tx_ref, cfg);
    stream = decoded.primary_streams(1);
    sync = decoded.synchronization;
    output.ok = true;
    output.selected_frame_start = sync.frame_start_sample;
    output.sync = sync;
    output.sro_ppm = sync.sro_ppm;
    output.sro_applied = sync.sro_applied;
    output.sro_reliable = sync.sro_reliable;
    output.sro_sigma_ppm = sync.sro_sigma_ppm;
    output.sro_apply_threshold_ppm = sync.sro_apply_threshold_ppm;
    output.sro_reason = sync.sro_reason;
    output.sro_stage = sync.sro_correction_stage;
    output.sro_low_rate_resample_applied = ...
        sync.sro_low_rate_resample_applied;
    output.metrics = struct('mer_db',stream.mer_db,'evm_rms',stream.evm_rms, ...
        'pre_fec_ber',stream.pre_fec_ber,'post_fec_ber',stream.post_fec_ber, ...
        'bler',stream.bler,'pass',stream.pass);
catch exception
    output.error_identifier = exception.identifier;
    output.error_message = exception.message;
    output.sro_reason = 'decode_failed';
end
end

function output = decode_manual_case(raw, tx_ref, cfg, expected_start)
output = empty_case();
try
    [baseband, ~] = msiq.dsp.prepare_capture(raw, cfg);
    [~, sync] = msiq.dsp.synchronize_single_wz(baseband, tx_ref, cfg, true);
    corrected = sync.corrected_capture(:);
    starts = sync.candidate_frame_starts(:);
    if isempty(starts), starts = sync.frame_start_sample; end
    if isfinite(expected_start)
        [~, selected] = min(abs(starts-expected_start));
    else
        selected = find(starts == sync.frame_start_sample, 1, 'first');
        if isempty(selected), selected = 1; end
    end
    first = round(starts(selected));
    frame_length = round(tx_ref.frame.symbol_count * ...
        cfg.receiver.single_samples_per_symbol);
    last = first+frame_length-1;
    if first < 1 || last > numel(corrected)
        error('msiq:sroRegression:FrameBounds', ...
            'Selected complete frame is outside capture.');
    end
    pair = tx_ref.pairs(find(strcmpi({tx_ref.pairs.name}, 'A'), 1));
    equalizer = msiq.dsp.equalize_single_wz(corrected(first:last), pair, cfg);
    output.ok = true;
    output.selected_frame_start = first;
    output.sync = rmfield(sync, 'corrected_capture');
    output.sro_ppm = sync.sro_ppm;
    output.sro_applied = sync.sro_applied;
    output.sro_reliable = sync.sro_reliable;
    output.sro_sigma_ppm = sync.sro_sigma_ppm;
    output.sro_apply_threshold_ppm = sync.sro_apply_threshold_ppm;
    output.sro_reason = sync.sro_reason;
    output.sro_stage = 'low_rate_legacy';
    output.sro_low_rate_resample_applied = sync.sro_applied;
    output.metrics = decode_metrics(equalizer.symbols, pair, cfg);
catch exception
    output.error_identifier = exception.identifier;
    output.error_message = exception.message;
    output.sro_reason = 'decode_failed';
end
end

function metrics = decode_metrics(symbols, pair, cfg)
known = pair.receiver_known(1);
reference = pair.metrics_only(1);
[tracked, tracking] = msiq.dsp.pilot_track(symbols(:), known, cfg);
payload = tracked(known.frame.payload_positions_frame);
payload = payload(isfinite(real(payload)) & isfinite(imag(payload)));
payload = payload(1:min(numel(payload), reference.payload_symbol_count));
if isempty(payload)
    error('msiq:sroRegression:Payload', 'No finite payload symbols.');
end
indices = qamdemod(payload, cfg.waveform.modulation_order, ...
    'UnitAveragePower', true);
decisions = qammod(indices, cfg.waveform.modulation_order, ...
    'UnitAveragePower', true);
error_value = payload-decisions;
evm = sqrt(mean(abs(error_value).^2)/max(mean(abs(decisions).^2), eps));
noise_variance = max([tracking.noise_variance, ...
    mean(abs(error_value).^2), 1e-10]);
llr = qamdemod(payload, cfg.waveform.modulation_order, ...
    'OutputType','approxllr','UnitAveragePower',true, ...
    'NoiseVariance',noise_variance);
count = min(numel(llr), numel(reference.fec.scramble_bits));
fec = msiq.fec.decode_soft(double(llr(1:count)).*(1-2* ...
    double(reference.fec.scramble_bits(1:count))), reference.fec, cfg);
metrics = struct('mer_db',-20*log10(max(evm,eps)),'evm_rms',evm, ...
    'pre_fec_ber',fec.pre_fec_ber,'post_fec_ber',fec.post_fec_ber, ...
    'bler',fec.bler,'pass',fec.valid && fec.block_count >= 1 && ...
    fec.parity_converged && fec.post_fec_ber == 0 && fec.bler == 0);
end

function raw = normalize_pair(capture)
records = capture.channels(1:2);
time = cell(1,2); samples = cell(1,2); rate = zeros(1,2);
for index = 1:2
    time{index} = double(records(index).time_axis_s(:));
    samples{index} = double(records(index).samples(:));
    rate(index) = 1/median(diff(time{index}));
end
start_time = max(cellfun(@(value)value(1), time));
end_time = min(cellfun(@(value)value(end), time));
same_grid = numel(time{1}) == numel(time{2}) && ...
    max(abs(time{1}-time{2})) <= 0.05/min(rate);
if same_grid
    common_time = time{1};
    data = [samples{1},samples{2}];
else
    common_rate = min(rate);
    count = floor((end_time-start_time)*common_rate)+1;
    common_time = start_time+(0:count-1).'/common_rate;
    data = [interp1(time{1},samples{1},common_time,'linear'), ...
        interp1(time{2},samples{2},common_time,'linear')];
end
raw = struct('samples',data,'time_axes',repmat(common_time,1,2), ...
    'sample_rate_hz',1/median(diff(common_time)),'payload_pair','A', ...
    'full_scale',NaN);
end

function injected = inject_raw_time_scale(raw, epsilon)
if 1+epsilon <= 0
    error('msiq:sroRegression:InjectionScale', 'Invalid injection scale.');
end
count = floor((size(raw.samples,1)-1)*(1+epsilon))+1;
source_axis = (0:count-1)./(1+epsilon);
injected = raw;
injected.samples = zeros(count,size(raw.samples,2));
for channel = 1:size(raw.samples,2)
    injected.samples(:,channel) = interp1((0:size(raw.samples,1)-1).', ...
        raw.samples(:,channel),source_axis.','pchip');
end
time_axis = raw.time_axes(1,1)+(0:count-1).'/raw.sample_rate_hz;
injected.time_axes = repmat(time_axis,1,size(injected.samples,2));
end

function target = map_frame_start(baseline_start, epsilon)
target = 1+round((baseline_start-1)*(1+epsilon));
end

function value = empty_case()
value = struct('ok',false,'selected_frame_start',NaN,'sync',struct(), ...
    'sro_ppm',NaN,'sro_applied',false,'sro_reliable',false, ...
    'sro_sigma_ppm',NaN,'sro_apply_threshold_ppm',NaN,'sro_reason','', ...
    'sro_stage','','sro_low_rate_resample_applied',false, ...
    'error_identifier','','error_message','','metrics',empty_metrics());
end

function value = empty_metrics()
value = struct('mer_db',NaN,'evm_rms',NaN,'pre_fec_ber',NaN, ...
    'post_fec_ber',NaN,'bler',NaN,'pass',false);
end

function value = empty_row()
value = struct('label','','trial','','frame_repetitions',NaN, ...
    'raw_path','','bundle_path','','injected_ppm',NaN,'baseline',empty_case(), ...
    'mode_b',empty_case(),'mode_c',empty_case(),'mode_d',empty_case(), ...
    'injected_target_frame_start',NaN,'delta_c_vs_b_db',NaN, ...
    'delta_d_vs_c_db',NaN, ...
    'delta_d_vs_a_db',NaN,'legacy_c_mer_db',NaN, ...
    'delta_new_vs_legacy_c_db',NaN,'outcome','');
end

function outcome = outcome_label(mode_b, mode_c, mode_d)
if ~mode_b.ok || ~mode_c.ok || ~mode_d.ok
    outcome = 'decode_failure';
elseif mode_c.sro_applied && mode_c.metrics.mer_db < mode_b.metrics.mer_db
    outcome = 'applied_and_degraded';
elseif mode_c.sro_applied
    outcome = 'applied_and_improved';
elseif mode_d.metrics.mer_db > mode_b.metrics.mer_db
    outcome = 'held_with_recovery_available';
else
    outcome = 'held_without_observed_recovery';
end
end

function rows = load_legacy_rows(path)
if ~isfile(path)
    rows = struct([]);
    return;
end
loaded = load(path, 'rows');
rows = loaded.rows;
end

function value = legacy_mer(rows, label, ppm)
value = NaN;
if isempty(rows), return; end
matches = strcmp({rows.label},label) & [rows.injected_ppm] == ppm;
if any(matches)
    value = rows(find(matches,1)).mode_c.metrics.mer_db;
end
end

function validate_rows(rows)
mode_b = [rows.mode_b];
mode_c = [rows.mode_c];
mode_d = [rows.mode_d];
if any(~[mode_b.ok]) || any(~[mode_c.ok]) || any(~[mode_d.ok])
    error('msiq:sroRegression:DecodeFailure', ...
        'One or more A/B/C/D cases could not decode.');
end
applied = [mode_c.sro_applied];
delta_c_vs_b = [rows.delta_c_vs_b_db];
if any(delta_c_vs_b(applied) < 0)
    error('msiq:sroRegression:AppliedDegraded', ...
        'A raw-stage correction reduced MER relative to no correction.');
end
zero = rows([rows.injected_ppm] == 0);
zero_mode_c = [zero.mode_c];
if any([zero_mode_c.sro_applied])
    error('msiq:sroRegression:ZeroFalseApplication', ...
        'A zero-SRO control applied correction.');
end
one_frame_minus25 = rows([rows.injected_ppm] == -25 & ...
    [rows.frame_repetitions] == 1);
one_frame_mode_c = [one_frame_minus25.mode_c];
if any([one_frame_mode_c.sro_applied])
    error('msiq:sroRegression:ConservativeGate', ...
        'A one-frame -25 ppm control unexpectedly applied correction.');
end
if any([mode_c.sro_low_rate_resample_applied])
    error('msiq:sroRegression:DoubleCorrection', ...
        'Production C applied a low-rate SRO correction after raw correction.');
end
end

function write_csv(path, rows)
fid = Result_Open_File_Retry(path, 'w', 'n', 'UTF-8');
cleanup = onCleanup(@()fclose(fid));
fprintf(fid, ['label,trial,repetitions,injected_ppm,B_mer_db,C_mer_db,D_mer_db,', ...
    'C_minus_B_db,D_minus_C_db,D_minus_A_db,new_C_minus_legacy_C_db,C_sro_ppm,', ...
    'C_applied,C_reliable,C_stage,C_low_rate_resample,C_reason,C_pass,outcome\n']);
for index = 1:numel(rows)
    row = rows(index); c = row.mode_c;
    fprintf(fid, '%s,%s,%d,%+.17g,%.17g,%.17g,%.17g,%+.17g,%+.17g,%+.17g,%+.17g,%.17g,%d,%d,%s,%d,%s,%d,%s\n', ...
        row.label,row.trial,row.frame_repetitions,row.injected_ppm, ...
        row.mode_b.metrics.mer_db,c.metrics.mer_db,row.mode_d.metrics.mer_db, ...
        row.delta_c_vs_b_db,row.delta_d_vs_c_db,row.delta_d_vs_a_db, ...
        row.delta_new_vs_legacy_c_db, ...
        c.sro_ppm,c.sro_applied,c.sro_reliable,c.sro_stage, ...
        c.sro_low_rate_resample_applied,c.sro_reason,c.metrics.pass,row.outcome);
end
clear cleanup;
end


function value = merge_options(base, override)
value = base;
names = fieldnames(override);
for index = 1:numel(names)
    value.(names{index}) = override.(names{index});
end
end
