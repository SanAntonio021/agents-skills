function report = run_wz_sro_interval_scan(options)
%RUN_WZ_SRO_INTERVAL_SCAN Scan the WZ peak-interval consistency guard.
% The production default remains 1.25 samples. This offline analysis only
% changes the candidate guard for each replay and never changes the decoder
% default or adds a ppm/MER acceptance threshold.

if nargin < 1 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:sroScan:Options', 'options must be a scalar struct.');
end
repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo, 'code', 'result_management'));

defaults = struct( ...
    'candidates_samples', [0.50 0.75 1.00 1.25 1.50 2.00], ...
    'source', 'real', ...
    'write_results', true, ...
    'rng_seed', 260825, ...
    'snr_values_db', [38 35], ...
    'global_sro_ppm', 200, ...
    'echo_amplitudes', [0.03 0.06 0.10 0.20 0.316], ...
    'echo_delays_symbols', [1 2 4], ...
    'profile_ppm_pairs', [150 250; 100 300], ...
    'families', {{'clean','noise','echo','varying'}}, ...
    'results_root', repo);
options = merge_options(defaults, options);
policy = msiq.output_policy(options);
options.output_level = policy.output_level;
options.source = lower(char(string(options.source)));
limits = double(options.candidates_samples(:).');
if isempty(limits) || any(~isfinite(limits)) || any(limits <= 0)
    error('msiq:sroScan:Candidates', ...
        'candidates_samples must contain positive finite values.');
end
if numel(unique(limits)) ~= numel(limits)
    error('msiq:sroScan:Candidates', ...
        'candidates_samples must not contain duplicates.');
end

stress_options = struct( ...
    'source', options.source, 'write_results', false, ...
    'rng_seed', options.rng_seed, 'snr_values_db', options.snr_values_db, ...
    'global_sro_ppm', options.global_sro_ppm, ...
    'echo_amplitudes', options.echo_amplitudes, ...
    'echo_delays_symbols', options.echo_delays_symbols, ...
    'profile_ppm_pairs', options.profile_ppm_pairs, ...
    'families', {{'clean','noise','echo','varying'}});
stress_options.families = options.families;

rows = repmat(empty_scan_row(), 0, 1);
planned = planned_row_count(options,limits);
run = [];
if options.write_results
    run = create_run(repo,options,limits,planned);
    Result_Log_Stage(run,'INFO','setup', ...
        'Offline SRO interval scan started for %d rows.',planned);
end
try
    for candidate_index = 1:numel(limits)
        limit = limits(candidate_index);
        fprintf('[SRO interval scan] candidate %d/%d: %.2f samples\n', ...
            candidate_index,numel(limits),limit);
        if options.write_results
            Result_Log_Stage(run,'INFO','candidate', ...
                'Candidate %d/%d started: %.2f samples.', ...
                candidate_index,numel(limits),limit);
        end
        stress_options.sro_interval_consistency_limit_samples = limit;
        stress = msiq.run_wz_sro_distortion_stress(stress_options);
        if options.write_results && policy.save_raw
            candidate = rmfield(stress,'trials');
            if strcmp(options.source,'synthetic')
                if candidate_index == 1
                    msiq.atomic_save(msiq.output_path(run,'synthetic_trials.mat'), ...
                        struct('trials',stress.trials));
                end
                candidate.trials_file = 'synthetic_trials.mat';
            else
                candidate.trials = msiq.analysis_record(stress.trials);
            end
            msiq.atomic_save(msiq.output_path(run,sprintf( ...
                'candidate%03d.mat',candidate_index)),candidate);
        end
        for row_index = 1:numel(stress.rows)
            rows(end+1,1) = make_scan_row(limit, ...
                stress.rows(row_index)); %#ok<AGROW>
        end
        if options.write_results
            Result_Log_Stage(run,'INFO','candidate', ...
                'Candidate %.2f samples completed with %d rows.', ...
                limit,numel(stress.rows));
        end
    end
    if numel(rows) ~= planned
        error('msiq:sroScan:RowCount', ...
            'Completed row count %d does not match planned count %d.', ...
            numel(rows),planned);
    end
    summary = summarize(rows, limits);
    guard = validate_rows(rows);
    if options.write_results
        write_outputs(run, rows, summary, limits, options, guard);
        write_sources(msiq.output_path(run,'sources.txt'),rows,repo);
        counts = scan_counts(rows,planned);
        Result_Update_Run_Info(run,struct('counts',counts, ...
            'parameters',struct('effective_trials',msiq.analysis_record(stress.trials)), ...
            'source_runs',{unique({rows.source_path})}, ...
            'safety',struct('preflight','not_applicable', ...
            'initial_outputs','not_applicable','shutdown','not_applicable', ...
            'shutdown_readback','not_applicable')));
        status = 'completed';
        if ~guard.ok, status = 'completed_with_failures'; end
        Result_Finalize_Run(run, status, 'normal_completion', ...
            scan_artifacts(), guard.detail);
    end
catch exception
    if options.write_results && ~isempty(run)
        failure = struct('options',options,'rows',rows);
        if exist('stress','var'), failure.stress = stress; end
        if strcmp(options.source,'real'), failure = msiq.analysis_record(failure); end
        msiq.save_failure(run.OutputDir,failure);
        Result_Log_Stage(run,'ERROR','failure','%s',exception.message);
        Result_Finalize_Run(run,'failed','processing_failed',{}, ...
            exception.message);
    end
    rethrow(exception);
end

report = struct('ok', guard.ok, 'guard', guard, 'rows', rows, ...
    'summary', summary, 'candidates_samples', limits, ...
    'run_dir', empty_path(run), 'offline_only', true, ...
    'source', options.source);
end

function run = create_run(repo,options,limits,planned)
parameters = struct('candidates_samples', limits, ...
    'source', options.source, 'rng_seed', options.rng_seed, ...
    'snr_values_db', options.snr_values_db, ...
    'global_sro_ppm', options.global_sro_ppm, ...
    'echo_amplitudes', options.echo_amplitudes, ...
    'echo_delays_symbols', options.echo_delays_symbols, ...
    'echo_combination_mode', 'cartesian', ...
    'noise_realization_policy', 'same_per_capture_scaled_by_snr', ...
    'profile_ppm_pairs', options.profile_ppm_pairs, ...
    'families', {cellstr(string(options.families))},'options',options);
run_cfg = struct('ProjectRoot', repo, 'ResultsRoot', options.results_root, ...
    'RunType', 'analysis', 'NameParts', {{'WZ_SRO_interval_candidates'}}, ...
    'RunPurpose', 'validation', 'ExecutionMode', 'offline_analysis', ...
    'EntryPoint', 'msiq.run_wz_sro_interval_scan', ...
    'Parameters', parameters, ...
    'Counts', struct('planned',planned,'executed',0, ...
    'succeeded',0,'failed',0,'invalid',0), ...
    'SourceRuns', {planned_sources(repo,options)}, ...
    'Artifacts', {scan_artifacts()});
run = Result_Create_Run(run_cfg);
end

function count = planned_row_count(options,limits)
families = cellstr(string(options.families));
scenario_count = double(any(strcmp(families,'clean')));
if any(strcmp(families,'noise'))
    scenario_count = scenario_count+numel(options.snr_values_db);
end
if any(strcmp(families,'echo'))
    scenario_count = scenario_count+numel(options.echo_amplitudes)* ...
        numel(options.echo_delays_symbols);
end
if any(strcmp(families,'varying'))
    scenario_count = scenario_count+size(options.profile_ppm_pairs,1);
end
trial_count = 1;
if strcmp(options.source,'real'), trial_count = 2; end
count = numel(limits)*scenario_count*trial_count;
end

function counts = scan_counts(rows,planned)
failed = sum([rows.processing_failure]);
invalid = sum([rows.invalid_all_decode_failed]);
counts = struct('planned',planned,'executed',numel(rows), ...
    'succeeded',numel(rows)-failed-invalid,'failed',failed, ...
    'invalid',invalid);
end

function artifacts = scan_artifacts()
artifacts = {'data/plot_data.mat','summary.csv','data/candidate_summary.csv', ...
    'overview.png','data/sources.txt','data/sro_interval_scan.mat'};
end

function sources = planned_sources(repo,options)
if strcmp(options.source,'synthetic')
    sources = {'synthetic://three_frame_control'};
    return
end
root = fullfile(repo,'results','manual_loopback', ...
    'rdiv_compare_20260821_091514','trials');
names = {'02_DIV4','04_DIV4'};
sources = cell(1,numel(names));
for k = 1:numel(names)
    sources{k} = fullfile(root,names{k},'rx','diagnostics','raw_capture.mat');
end
end

function row = make_scan_row(limit, source_row)
c = source_row.mode_c;
b = source_row.mode_b;
d = source_row.mode_d;
row = empty_scan_row();
row.limit_samples = limit;
row.label = source_row.label;
row.family = source_row.family;
row.source = source_row.source;
if isfield(source_row, 'source_path')
    row.source_path = source_row.source_path;
else
    row.source_path = source_row.source;
end
row.global_sro_ppm = source_row.global_sro_ppm;
row.profile_start_ppm = source_row.profile_start_ppm;
row.profile_end_ppm = source_row.profile_end_ppm;
row.noise_snr_db = source_row.noise_snr_db;
row.noise_seed = source_row.noise_seed;
row.echo_amplitude = source_row.echo_amplitude;
row.echo_delay_symbols = source_row.echo_delay_symbols;
row.estimate_ppm = c.sro_ppm;
row.estimate_error_ppm = estimate_error(c.sro_ppm, ...
    source_row.global_sro_ppm);
row.sigma_ppm = c.sro_sigma_ppm;
row.fit_residual_samples = c.sro_fit_residual_samples;
row.max_interval_deviation_samples = ...
    c.sro_max_interval_deviation_samples;
row.peak_count = c.sro_peak_count;
row.complete_peak_count = c.sro_complete_peak_count;
row.reliable = c.sro_reliable;
row.recommended = c.sro_recommended;
row.applied = c.sro_applied;
row.reason = c.sro_reason;
row.b_mer_db = b.metrics.mer_db;
row.c_mer_db = c.metrics.mer_db;
row.d_mer_db = d.metrics.mer_db;
row.c_minus_b_db = source_row.delta_c_vs_b_db;
row.d_minus_c_db = source_row.delta_d_vs_c_db;
row.b_decodable = b.decodable;
row.c_decodable = c.decodable;
row.d_decodable = d.decodable;
row.processing_failure = strcmp(source_row.outcome, 'processing_failure');
row.invalid_all_decode_failed = strcmp(source_row.outcome, ...
    'invalid_all_decode_failed');
row.varying_sro_accepted = strcmp(row.family, 'varying') && row.applied;
row.applied_unreliable = row.applied && ~row.reliable;
row.applied_and_degraded = row.applied && isfinite(row.b_mer_db) && ...
    isfinite(row.c_mer_db) && row.c_mer_db < row.b_mer_db;
row.held_with_recovery_available = ~row.applied && ...
    d.decodable && isfinite(row.d_mer_db) && isfinite(row.b_mer_db) && ...
    row.d_mer_db > row.b_mer_db;
end

function value = estimate_error(estimate, injected)
if isfinite(estimate) && isfinite(injected)
    value = estimate-injected;
else
    value = NaN;
end
end

function summary = summarize(rows, limits)
summary = repmat(empty_summary(), numel(limits), 1);
for k = 1:numel(limits)
    selected = abs([rows.limit_samples]-limits(k)) < eps(max(1,limits(k)));
    r = rows(selected);
    summary(k).limit_samples = limits(k);
    summary(k).case_count = numel(r);
    summary(k).applied_count = sum([r.applied]);
    summary(k).held_count = sum(~[r.applied]);
    summary(k).applied_unreliable = sum([r.applied_unreliable]);
    summary(k).applied_and_degraded = sum([r.applied_and_degraded]);
    summary(k).varying_sro_accepted = sum([r.varying_sro_accepted]);
    summary(k).held_with_recovery_available = ...
        sum([r.held_with_recovery_available]);
    summary(k).processing_failures = sum([r.processing_failure]);
    summary(k).invalid_all_decode_failed = ...
        sum([r.invalid_all_decode_failed]);
    deviations = [r.max_interval_deviation_samples];
    deviations = deviations(isfinite(deviations));
    if isempty(deviations)
        summary(k).median_max_deviation_samples = NaN;
        summary(k).p95_max_deviation_samples = NaN;
    else
        summary(k).median_max_deviation_samples = median(deviations);
        summary(k).p95_max_deviation_samples = percentile95(deviations);
    end
end
end

function guard = validate_rows(rows)
guard = struct();
guard.applied_unreliable = sum([rows.applied_unreliable]);
guard.applied_and_degraded = sum([rows.applied_and_degraded]);
guard.varying_sro_accepted = sum([rows.varying_sro_accepted]);
guard.processing_failures = sum([rows.processing_failure]);
guard.invalid_all_decode_failed = sum([rows.invalid_all_decode_failed]);
guard.ok = guard.applied_unreliable == 0 && ...
    guard.applied_and_degraded == 0 && guard.varying_sro_accepted == 0 && ...
    guard.processing_failures == 0;
guard.detail = sprintf(['interval scan guards: applied_unreliable=%d, ', ...
    'applied_and_degraded=%d, varying_sro_accepted=%d, ', ...
    'processing_failures=%d, invalid=%d'], ...
    guard.applied_unreliable, guard.applied_and_degraded, ...
    guard.varying_sro_accepted, guard.processing_failures, ...
    guard.invalid_all_decode_failed);
end

function write_outputs(run, rows, summary, limits, options, guard)
plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
msiq.import_summary(run,@(path) write_rows(path,rows),2, ...
    {'limit_samples','label','source','global_sro_ppm','noise_snr_db', ...
    'B_mer_db','C_mer_db','D_mer_db','状态'});
write_candidate_summary(msiq.output_path(run, 'candidate_summary.csv'), ...
    summary);
write_overview(msiq.output_path(run, 'overview.png'), summary);
rows = msiq.analysis_record(rows);
save(msiq.output_path(run, 'sro_interval_scan.mat'), ...
    'rows','summary','limits','options','guard','-v7.3');
end

function write_rows(path, rows)
fid = Result_Open_File_Retry(path, 'w', 'n', 'UTF-8');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s',char(65279));
fprintf(fid, ['limit_samples,label,family,source,global_sro_ppm,', ...
    'profile_start_ppm,profile_end_ppm,noise_snr_db,noise_seed,echo_amplitude,', ...
    'echo_delay_symbols,estimate_ppm,estimate_error_ppm,sigma_ppm,', ...
    'fit_residual_samples,max_interval_deviation_samples,peak_count,', ...
    'complete_peak_count,reliable,recommended,applied,reason,B_mer_db,', ...
    'C_mer_db,D_mer_db,C_minus_B_db,D_minus_C_db,B_decodable,', ...
    'C_decodable,D_decodable,varying_sro_accepted,held_with_recovery_available,', ...
    'processing_failure,invalid_all_decode_failed,状态,repeat,attempt,', ...
    '采集时间,原始数据文件,单次图片文件,错误代码,错误信息\n']);
fprintf(fid, ['samples,-,-,-,ppm,ppm,ppm,dB,-,-,symbol,ppm,ppm,ppm,', ...
    'samples,samples,count,count,-,-,-,-,dB,dB,dB,dB,dB,-,-,-,-,-,-,-,', ...
    '-,-,-,-,-,-,-,-\n']);
for k = 1:numel(rows)
    r = rows(k);
    fprintf(fid, ['%.17g,%s,%s,%s,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,', ...
        '%.17g,%.17g,%.17g,%.17g,%.17g,%d,%d,%d,%d,%d,%s,%.17g,', ...
        '%.17g,%.17g,%.17g,%.17g,%d,%d,%d,%d,%d,%d,%d,', ...
        '%s,1,1,,,,,\n'], ...
        r.limit_samples,csv_text(r.label),csv_text(r.family), ...
        csv_text(r.source),r.global_sro_ppm,r.profile_start_ppm, ...
        r.profile_end_ppm,r.noise_snr_db,r.noise_seed,r.echo_amplitude, ...
        r.echo_delay_symbols,r.estimate_ppm,r.estimate_error_ppm, ...
        r.sigma_ppm,r.fit_residual_samples,r.max_interval_deviation_samples, ...
        r.peak_count,r.complete_peak_count,r.reliable,r.recommended, ...
        r.applied,csv_text(r.reason),r.b_mer_db,r.c_mer_db,r.d_mer_db, ...
        r.c_minus_b_db,r.d_minus_c_db,r.b_decodable,r.c_decodable, ...
        r.d_decodable,r.varying_sro_accepted, ...
        r.held_with_recovery_available,r.processing_failure, ...
        r.invalid_all_decode_failed,csv_text(row_status(r)));
end
clear cleanup;
end

function write_candidate_summary(path, summary)
fid = Result_Open_File_Retry(path, 'w', 'n', 'UTF-8');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s',char(65279));
fprintf(fid, ['limit_samples,case_count,applied_count,held_count,', ...
    'applied_unreliable,applied_and_degraded,varying_sro_accepted,', ...
    'held_with_recovery_available,processing_failures,', ...
    'invalid_all_decode_failed,median_max_deviation_samples,', ...
    'p95_max_deviation_samples\n']);
for k = 1:numel(summary)
    s = summary(k);
    fprintf(fid, '%.17g,%d,%d,%d,%d,%d,%d,%d,%d,%d,%.17g,%.17g\n', ...
        s.limit_samples,s.case_count,s.applied_count,s.held_count, ...
        s.applied_unreliable,s.applied_and_degraded, ...
        s.varying_sro_accepted,s.held_with_recovery_available, ...
        s.processing_failures,s.invalid_all_decode_failed, ...
        s.median_max_deviation_samples,s.p95_max_deviation_samples);
end
clear cleanup;
end


function write_overview(path, summary)
fig = figure('Visible','off','Color','w','Position',[100 100 1250 720]);
limits = [summary.limit_samples];
applied = [summary.applied_count];
held_recovery = [summary.held_with_recovery_available];
varying = [summary.varying_sro_accepted];
degraded = [summary.applied_and_degraded];
subplot(2,1,1);
bar(limits, [applied(:), held_recovery(:)], 'grouped');
grid on; box on; xlabel('峰间最大偏差限值（处理采样点）');
ylabel('工况数'); legend({'实际校正','保持但 D 可恢复'},'Location','best');
subplot(2,1,2);
bar(limits, [varying(:), degraded(:)], 'grouped');
grid on; box on; xlabel('峰间最大偏差限值（处理采样点）');
ylabel('危险工况数'); legend({'时变 SRO 被放行','校正后 MER 下降'}, ...
    'Location','best');
if ~msiq.plot_archive('export',fig,path,'print',300)
    print(fig,path,'-dpng','-r300');
end
close(fig);
end

function write_sources(path,rows,repo)
sources = unique({rows.source_path},'stable');
fid = Result_Open_File_Retry(path,'w','n','UTF-8');
cleanup = onCleanup(@() fclose(fid));
for k = 1:numel(sources)
    value = sources{k};
    if startsWith(value,repo)
        value = strrep(value,[repo filesep],'');
    end
    fprintf(fid,'%s\n',value);
end
clear cleanup;
end

function value = row_status(row)
if row.processing_failure
    value = '失败';
elseif row.invalid_all_decode_failed
    value = '无效';
else
    value = '成功';
end
end

function value = empty_scan_row()
value = struct('limit_samples',NaN,'label','','family','','source','', ...
    'source_path','','global_sro_ppm',NaN,'profile_start_ppm',NaN, ...
    'profile_end_ppm',NaN,'noise_snr_db',NaN,'noise_seed',NaN, ...
    'echo_amplitude',NaN, ...
    'echo_delay_symbols',NaN,'estimate_ppm',NaN,'estimate_error_ppm',NaN, ...
    'sigma_ppm',NaN,'fit_residual_samples',NaN, ...
    'max_interval_deviation_samples',NaN,'peak_count',0, ...
    'complete_peak_count',0,'reliable',false,'recommended',false, ...
    'applied',false,'reason','','b_mer_db',NaN,'c_mer_db',NaN, ...
    'd_mer_db',NaN,'c_minus_b_db',NaN,'d_minus_c_db',NaN, ...
    'b_decodable',false,'c_decodable',false,'d_decodable',false, ...
    'varying_sro_accepted',false,'held_with_recovery_available',false, ...
    'applied_unreliable',false,'applied_and_degraded',false, ...
    'processing_failure',false,'invalid_all_decode_failed',false);
end

function value = empty_summary()
value = struct('limit_samples',NaN,'case_count',0,'applied_count',0, ...
    'held_count',0,'applied_unreliable',0,'applied_and_degraded',0, ...
    'varying_sro_accepted',0,'held_with_recovery_available',0, ...
    'processing_failures',0,'invalid_all_decode_failed',0, ...
    'median_max_deviation_samples',NaN,'p95_max_deviation_samples',NaN);
end

function value = percentile95(values)
values = sort(double(values(:)));
if isempty(values), value = NaN; return; end
index = 1 + 0.95*(numel(values)-1);
lo = floor(index); hi = ceil(index);
if lo == hi
    value = values(lo);
else
    value = values(lo) + (index-lo)*(values(hi)-values(lo));
end
end

function value = merge_options(base, override)
value = base;
names = fieldnames(override);
for k = 1:numel(names)
    value.(names{k}) = override.(names{k});
end
end

function text = csv_text(value)
text = char(string(value));
text = strrep(text, '"', '""');
if contains(text, ',') || contains(text, '"')
    text = ['"' text '"'];
end
end

function value = empty_path(run)
if isempty(run), value = ''; else, value = run.OutputDir; end
end
