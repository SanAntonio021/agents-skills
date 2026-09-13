function output = run_wz_sro_policy_comparison(options)
%RUN_WZ_SRO_POLICY_COMPARISON Reprocess saved WZ captures with SRO policies.

if nargin < 1 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:sroPolicy:Options', 'options must be a scalar struct.');
end
repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo, 'code', 'result_management'));
defaults = struct( ...
    'source_run_dir', fullfile(repo, 'results', 'scan', ...
    'sro_small_offsets_ch3_ch4_20260903_155325'), ...
    'results_root', repo, ...
    'observation_oversample_factor', 8, ...
    'row_indices', [], 'write_results', true);
options = merge_options(defaults, options);
policy = msiq.output_policy(options);
options.output_level = policy.output_level;
factor = validate_factor(options.observation_oversample_factor);
source_csv = msiq.artifact_path(options.source_run_dir, 'sro_repeatability_summary.csv');
if ~isfile(source_csv)
    source_csv = msiq.artifact_path(options.source_run_dir,'observations.csv');
    if ~isfile(source_csv)
        error('msiq:sroPolicy:SourceSummary', ...
            'Missing source summary: %s', source_csv);
    end
    cells = Result_Read_Summary(options.source_run_dir);
    source = cell2table(cells(3:end,:), ...
        'VariableNames',cellstr(string(cells(1,:))));
else
    source = readtable(source_csv, 'TextType','string');
end
indices = resolve_indices(options.row_indices, height(source));

rows = repmat(empty_row(), numel(indices), 1);
run = []; run_dir = ''; csv_path = ''; report_path = '';
if policy.write_results
    results_root = options.results_root;
    [parent,category] = fileparts(results_root);
    if strcmp(category,'analysis'), results_root = parent; end
    run = Result_Create_Run(struct('ProjectRoot',repo,'ResultsRoot',results_root, ...
        'RunType','analysis','NameParts',{{'wz_sro_policy_comparison'}}, ...
        'EntryPoint','msiq.run_wz_sro_policy_comparison','ExecutionMode','offline_analysis', ...
        'Parameters',struct('options',options), ...
        'SourceRuns',{{source_csv}},'Inputs',{{struct('path',source_csv, ...
        'sha256',msiq.file_sha256(source_csv))}}));
    run_dir = run.OutputDir;
end
try
for output_index = 1:numel(indices)
    source_index = indices(output_index);
    rows(output_index) = process_row(source(source_index,:), factor);
    row = rows(output_index);
    fprintf(['[%d/%d] %s #%d: B %.3f, legacy %.3f, conservative %.3f, ', ...
        'weighted %.3f, D %.3f dB\n'], output_index, numel(indices), ...
        row.condition, row.trial, row.b.mer_db, row.legacy.mer_db, ...
        row.conservative.mer_db, row.weighted.mer_db, row.oracle.mer_db);
end

guard = validate_rows(rows);
if policy.write_results
    csv_path = run.FullSummaryPath;
    msiq.import_summary(run,@(path) write_csv(path,rows),1, ...
        {'condition','trial','injected_sro_ppm','B_MER_dB', ...
        'legacy_MER_dB','conservative_MER_dB','weighted_MER_dB','D_MER_dB'});
    record = msiq.analysis_record(struct('rows',rows,'guard',guard,'options',options,'factor',factor));
    msiq.atomic_save(msiq.output_path(run,'sro_policy_comparison.mat'),record);
    Result_Update_Run_Info(run,struct('counts',struct('planned',numel(rows), ...
        'executed',numel(rows),'succeeded',double(guard.ok)*numel(rows), ...
        'failed',double(~guard.ok)*numel(rows),'invalid',0)));
    Result_Finalize_Run(run,'completed','normal_completion',[],guard.message);
end
output = struct('rows',rows,'guard',guard,'source_run_dir', ...
    char(string(options.source_run_dir)),'observation_oversample_factor',factor, ...
    'run_dir',run_dir,'csv_path',csv_path,'report_path',report_path, ...
    'offline_only',true,'ok',guard.ok);
if ~guard.ok
    error('msiq:sroPolicy:Guard', '%s', guard.message);
end
catch exception
    if ~isempty(run)
        msiq.save_failure(run_dir,msiq.analysis_record(struct('options',options,'rows',rows)));
        Result_Log_Stage(run,'ERROR','failure','%s',exception.message);
        Result_Finalize_Run(run,'failed','processing_failed',[],exception.message);
    end
    rethrow(exception);
end
end

function row = process_row(source_row, factor)
run_dir = char(source_row.rx_run_dir(1));
location = run_dir;
if ismember('artifact_prefix',source_row.Properties.VariableNames)
    location = struct('run_dir',run_dir, ...
        'artifact_prefix',char(string(source_row.artifact_prefix(1))));
end
capture = msiq.load_capture_validation(location);
reference = msiq.load_reference_bundle(msiq.artifact_path(location, 'tx_reference_bundle.mat'));
raw = capture.validation.pairs(1).raw_for_decode;
bundle = reference.bundle;
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform = bundle.dsp_config.waveform;
cfg.receiver = bundle.dsp_config.receiver;
cfg.waveform.architecture = 'single_complex_stream';

no_sro = cfg;
no_sro.receiver.max_abs_sro_ppm = 0;
no_sro.receiver.sro_decision_policy = 'legacy';
no_sro.receiver.sro_observation_oversample_factor = 1;
legacy = cfg;
legacy.receiver.sro_decision_policy = 'legacy';
legacy.receiver.sro_observation_oversample_factor = 1;
conservative = cfg;
conservative.receiver.sro_decision_policy = 'conservative_ci';
conservative.receiver.sro_observation_oversample_factor = factor;
weighted = cfg;
weighted.receiver.sro_decision_policy = 'confidence_weighted';
weighted.receiver.sro_observation_oversample_factor = factor;

injected_ppm = double(source_row.injected_sro_ppm(1));
row = empty_row();
row.condition = char(source_row.condition(1));
row.trial = double(source_row.trial(1));
row.injected_sro_ppm = injected_ppm;
row.raw_run_dir = run_dir;
row.raw_path = msiq.artifact_path(run_dir,'raw_capture.mat','read');
row.bundle_path = fullfile(diagnostics,'tx_reference_bundle.mat');
row.effective_config = cfg;
row.b = decode_mode(raw, bundle.tx_ref, no_sro);
row.legacy = decode_mode(raw, bundle.tx_ref, legacy);
row.conservative = decode_mode(raw, bundle.tx_ref, conservative);
row.weighted = decode_mode(raw, bundle.tx_ref, weighted);
[oracle_raw, ~] = msiq.dsp.correct_raw_sro(raw, injected_ppm);
row.oracle = decode_mode(oracle_raw, bundle.tx_ref, no_sro);
row.saved_legacy_mer_db = double(source_row.c_mer_db(1));
row.legacy_reproduced = ...
    abs(row.legacy.mer_db-row.saved_legacy_mer_db) <= 1e-8;
row.conservative_minus_b_db = row.conservative.mer_db-row.b.mer_db;
row.weighted_minus_b_db = row.weighted.mer_db-row.b.mer_db;
row.oracle_minus_conservative_db = row.oracle.mer_db-row.conservative.mer_db;
row.oracle_minus_weighted_db = row.oracle.mer_db-row.weighted.mer_db;
end

function value = decode_mode(raw, tx_ref, cfg)
decoded = msiq.decode_capture(raw, tx_ref, cfg);
stream = decoded.primary_streams(1);
sync = decoded.synchronization;
value = empty_mode();
value.mer_db = stream.mer_db;
value.pre_fec_ber = stream.pre_fec_ber;
value.post_fec_ber = stream.post_fec_ber;
value.bler = stream.bler;
value.pass = logical(decoded.pass);
value.estimated_sro_ppm = sync.sro_ppm;
value.sro_sigma_ppm = sync.sro_sigma_ppm;
value.correction_ppm = field_or(sync, 'sro_correction_ppm', 0);
value.correction_weight = field_or(sync, 'sro_correction_weight', 0);
value.applied = logical(sync.sro_applied);
value.reliable = logical(sync.sro_reliable);
value.reason = char(string(sync.sro_reason));
value.stage = char(string(sync.sro_correction_stage));
value.low_rate_applied = logical(sync.sro_low_rate_resample_applied);
value.policy = char(string(field_or(sync, 'sro_decision_policy', 'legacy')));
value.observation_factor = double(field_or(sync, ...
    'sro_observation_oversample_factor', 1));
value.confidence_interval_ppm = double(field_or(sync, ...
    'sro_confidence_interval_ppm', [NaN NaN]));
value.jackknife_sigma_ppm = double(field_or(sync, ...
    'sro_jackknife_sigma_ppm', NaN));
value.leave_one_out_range_ppm = double(field_or(sync, ...
    'sro_leave_one_out_range_ppm', NaN));
value.peak_count = numel(sync.sro_peak_samples);
end

function guard = validate_rows(rows)
legacy_reproduced = all([rows.legacy_reproduced]);
all_modes = [[rows.b],[rows.legacy],[rows.conservative],[rows.weighted],[rows.oracle]];
no_low_rate = ~any([all_modes.low_rate_applied]);
applied = all_modes([all_modes.applied]);
raw_only = isempty(applied) || all(strcmp({applied.stage}, 'raw_input'));
new_modes = [[rows.conservative],[rows.weighted]];
new_applied = [new_modes.applied];
new_mer = [new_modes.mer_db];
b_modes = [rows.b];
b_mer = [[b_modes.mer_db],[b_modes.mer_db]];
no_applied_degradation = all(new_mer(new_applied) >= b_mer(new_applied)-1e-9);
required_modes = [[rows.legacy],[rows.conservative],[rows.weighted],[rows.oracle]];
all_decoded = all([required_modes.pass]);
guard = struct('legacy_reproduced',legacy_reproduced, ...
    'no_low_rate_double_correction',no_low_rate, ...
    'raw_input_only',raw_only, ...
    'no_applied_mer_degradation',no_applied_degradation, ...
    'all_decoded',all_decoded);
guard.ok = legacy_reproduced && no_low_rate && raw_only && ...
    no_applied_degradation && all_decoded;
guard.message = sprintf(['legacy_reproduced=%d, no_low_rate=%d, raw_only=%d, ', ...
    'no_applied_degradation=%d, all_decoded=%d'], legacy_reproduced, ...
    no_low_rate, raw_only, no_applied_degradation, all_decoded);
end

function write_csv(path, rows)
fid = Result_Open_File_Retry(path, 'w', 'n', 'UTF-8');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, ['condition,trial,injected_sro_ppm,raw_run_dir,B_MER_dB,', ...
    'legacy_MER_dB,legacy_estimated_ppm,legacy_applied,', ...
    'conservative_MER_dB,conservative_estimated_ppm,conservative_sigma_ppm,', ...
    'conservative_correction_ppm,conservative_weight,conservative_applied,', ...
    'conservative_reason,weighted_MER_dB,weighted_estimated_ppm,', ...
    'weighted_sigma_ppm,weighted_correction_ppm,weighted_weight,', ...
    'weighted_applied,weighted_reason,D_MER_dB,conservative_minus_B_dB,', ...
    'weighted_minus_B_dB,D_minus_conservative_dB,D_minus_weighted_dB,', ...
    'legacy_reproduced\n']);
for index = 1:numel(rows)
    r = rows(index);
    fprintf(fid, ['%s,%d,%.17g,%s,%.17g,%.17g,%.17g,%d,', ...
        '%.17g,%.17g,%.17g,%.17g,%.17g,%d,%s,', ...
        '%.17g,%.17g,%.17g,%.17g,%.17g,%d,%s,', ...
        '%.17g,%.17g,%.17g,%.17g,%.17g,%d\n'], ...
        csv_text(r.condition),r.trial,r.injected_sro_ppm,csv_text(r.raw_run_dir), ...
        r.b.mer_db,r.legacy.mer_db,r.legacy.estimated_sro_ppm,r.legacy.applied, ...
        r.conservative.mer_db,r.conservative.estimated_sro_ppm, ...
        r.conservative.sro_sigma_ppm,r.conservative.correction_ppm, ...
        r.conservative.correction_weight,r.conservative.applied, ...
        csv_text(r.conservative.reason),r.weighted.mer_db, ...
        r.weighted.estimated_sro_ppm,r.weighted.sro_sigma_ppm, ...
        r.weighted.correction_ppm,r.weighted.correction_weight, ...
        r.weighted.applied,csv_text(r.weighted.reason),r.oracle.mer_db, ...
        r.conservative_minus_b_db,r.weighted_minus_b_db, ...
        r.oracle_minus_conservative_db,r.oracle_minus_weighted_db, ...
        r.legacy_reproduced);
end
clear cleanup;
end


function indices = resolve_indices(value, count)
if isempty(value)
    indices = 1:count;
else
    indices = double(value(:).');
end
if any(~isfinite(indices)) || any(indices ~= round(indices)) || ...
        any(indices < 1) || any(indices > count) || numel(unique(indices)) ~= numel(indices)
    error('msiq:sroPolicy:Rows', 'row_indices must be unique valid row numbers.');
end
end

function factor = validate_factor(value)
factor = double(value);
if ~isscalar(factor) || ~isfinite(factor) || factor < 1 || factor > 16 || ...
        factor ~= round(factor)
    error('msiq:sroPolicy:Factor', ...
        'observation_oversample_factor must be an integer from 1 to 16.');
end
end

function value = empty_mode()
value = struct('mer_db',NaN,'pre_fec_ber',NaN,'post_fec_ber',NaN, ...
    'bler',NaN,'pass',false,'estimated_sro_ppm',NaN,'sro_sigma_ppm',NaN, ...
    'correction_ppm',0,'correction_weight',0,'applied',false, ...
    'reliable',false,'reason','','stage','','low_rate_applied',false, ...
    'policy','','observation_factor',NaN,'confidence_interval_ppm',[NaN NaN], ...
    'jackknife_sigma_ppm',NaN,'leave_one_out_range_ppm',NaN,'peak_count',NaN);
end

function value = empty_row()
value = struct('condition','','trial',NaN,'injected_sro_ppm',NaN, ...
    'raw_path','','bundle_path','','effective_config',struct(), ...
    'raw_run_dir','','b',empty_mode(),'legacy',empty_mode(), ...
    'conservative',empty_mode(),'weighted',empty_mode(),'oracle',empty_mode(), ...
    'saved_legacy_mer_db',NaN,'legacy_reproduced',false, ...
    'conservative_minus_b_db',NaN,'weighted_minus_b_db',NaN, ...
    'oracle_minus_conservative_db',NaN,'oracle_minus_weighted_db',NaN);
end

function value = field_or(source, name, fallback)
value = fallback;
if isstruct(source) && isfield(source, name) && ~isempty(source.(name))
    value = source.(name);
end
end

function value = merge_options(base, override)
value = base;
names = fieldnames(override);
for index = 1:numel(names)
    value.(names{index}) = override.(names{index});
end
end

function text = csv_text(value)
text = ['"', strrep(char(string(value)), '"', '""'), '"'];
end
