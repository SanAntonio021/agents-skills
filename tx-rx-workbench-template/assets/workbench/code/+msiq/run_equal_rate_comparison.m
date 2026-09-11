function output = run_equal_rate_comparison(action, options)
%RUN_EQUAL_RATE_COMPARISON Compare traditional complex 16QAM and IQ-MIMO.
%
% This isolated offline study keeps the physical 65 GSa/s path fixed. The
% IQ-MIMO waveform has two independent 16QAM streams at Rs. The traditional
% waveform has one complex 16QAM stream at 2*Rs, generated at 2 Sa/sym and
% resampled by 31/4 into the same 65 GSa/s physical capture domain.

if nargin < 1 || isempty(action)
    action = 'all';
end
if nargin < 2 || isempty(options)
    options = struct();
end
action = lower(char(string(action)));
if ~ismember(action, {'all','matched','sweep','validate'})
    error('msiq:equalrate:Action', 'Unsupported action: %s.', action);
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:equalrate:Options', 'options must be a scalar struct.');
end

defaults = struct( ...
    'results_root', '', ...
    'seed', 26072701, ...
    'matched_snr_db', 14, ...
    'snr_points_db', [8 10 12 14 16], ...
    'cfo_hz', 2e5, ...
    'sro_ppm', 40, ...
    'time_axis_skew_samples', 0.2, ...
    'common_iq_matrix', [1 0.08; 0.06 0.95], ...
    'prepend_samples', 777, ...
    'clip_level', 1e6, ...
    'save_raw', [], ...
    'output_level', 'compact', ...
    'write_results', true, ...
    'plot_visible', 'off');
opts = merge_struct(defaults, options);
policy = msiq.output_policy(options);
opts.save_raw = policy.save_raw;
opts.output_level = policy.output_level;
opts.retention_mode = policy.output_level;
validate_options(opts);

switch action
    case 'validate'
        output = validate_only(opts);
    otherwise
        before = msiq.instruments.reset_audit(); %#ok<NASGU>
        matched = struct([]);
        sweep = struct([]);
        if ismember(action, {'all','matched'})
            matched = run_matched(opts);
        end
        if ismember(action, {'all','sweep'})
            sweep = run_sweep(opts);
        end
        analysis = struct([]);
        if strcmp(action, 'all')
            analysis = run_analysis(matched, sweep, opts);
        end
        audit = msiq.instruments.get_audit();
        assert_zero_instrument_io(audit);
        output = struct('matched', matched, 'sweep', sweep, ...
            'analysis', analysis, ...
            'instrument_io_delta', audit, 'offline_only', true);
end
end

function output = run_matched(opts)
[dual_cfg, traditional_cfg, fairness] = build_pair_configs(opts);
run = create_run(dual_cfg, 'simulation', 'EQ_RATE_MATCHED', ...
    'simulation', opts, fairness, 2);
try
    if opts.write_results
    plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
    Result_Summary_Initialize(run, summary_columns(), summary_units());
    Result_Log_Stage(run, 'INFO', 'fairness', ...
        ['Equal-rate setup: dual 2 x %.9f GBd; traditional %.9f GBd; ', ...
        'common physical sample rate %.9f GSa/s.'], ...
        fairness.iqmimo_branch_symbol_rate_hz/1e9, ...
        fairness.traditional_symbol_rate_hz/1e9, ...
        fairness.physical_sample_rate_hz/1e9);
    end

    iqmimo = run_scheme('iqmimo', dual_cfg, opts, opts.matched_snr_db);
    traditional = run_scheme('traditional', traditional_cfg, opts, ...
        opts.matched_snr_db);
    if ~opts.write_results
        output = struct('run_dir','','iqmimo',iqmimo,'traditional',traditional, ...
            'fairness',fairness,'pass',iqmimo.pass && traditional.pass);
        return;
    end
    iqmimo_raw_name = ternary(opts.save_raw,'iqmimo_raw_capture.mat','');
    traditional_raw_name = ternary(opts.save_raw, ...
        'traditional_raw_capture.mat','');
    matched_summary_rows = [ ...
        scheme_summary_rows(iqmimo, 1, opts.matched_snr_db, iqmimo_raw_name); ...
        scheme_summary_rows(traditional, 2, opts.matched_snr_db, ...
        traditional_raw_name)];
    Result_Summary_Append(run, matched_summary_rows);

    if opts.save_raw
        payload = struct('iqmimo_raw',iqmimo.raw);
        save(msiq.output_path(run, iqmimo_raw_name), ...
            '-struct','payload','-v7.3');
        payload = struct('traditional_raw',traditional.raw);
        save(msiq.output_path(run, traditional_raw_name), ...
            '-struct','payload','-v7.3');
    end
    if opts.save_raw
    payload = struct('iqmimo_tx_ref',iqmimo.tx_ref, ...
        'traditional_tx_ref',traditional.tx_ref);
    save(msiq.output_path(run, 'tx_references.mat'), ...
        '-struct','payload','-v7.3');
    save(msiq.output_path(run, 'effective_configs.mat'), ...
        'dual_cfg','traditional_cfg','-v7.3');
    payload = struct('iqmimo_result',compact_scheme(iqmimo), ...
        'traditional_result',compact_scheme(traditional), ...
        'fairness',fairness,'options',opts);
    save(msiq.output_path(run, 'matched_result.mat'), ...
        '-struct','payload','-v7.3');
    end
    write_json(msiq.output_path(run, 'fairness.json'), fairness);
    plot_matched_overview(msiq.output_path(run, 'overview.png'), ...
        iqmimo, traditional, fairness, opts);
    plot_matched_constellation(msiq.output_path(run, 'constellation.png'), ...
        iqmimo, traditional, opts);
    plot_scheme_channels(run,iqmimo,1,opts.matched_snr_db);
    plot_scheme_channels(run,traditional,2,opts.matched_snr_db);

    passed = iqmimo.pass && traditional.pass;
    Result_Update_Run_Info(run, struct( ...
        'counts', struct('planned',2,'executed',2, ...
        'succeeded',double(iqmimo.pass)+double(traditional.pass), ...
        'failed',double(~iqmimo.pass)+double(~traditional.pass),'invalid',0), ...
        'safety', struct('preflight','not_applicable', ...
        'initial_outputs','not_accessed','shutdown','not_required', ...
        'shutdown_readback','not_required','instrument_io_delta', ...
        msiq.instruments.get_audit()), ...
        'parameters', struct('fairness',fairness,'impairments',impairments(opts), ...
        'matched_snr_db',opts.matched_snr_db,'options',opts, ...
        'effective_config_iqmimo',dual_cfg,'effective_config_traditional',traditional_cfg), ...
        'inputs', {{struct('scheme','iqmimo', ...
        'tx_reference_hash',iqmimo.tx_ref.reference_hash_sha256), ...
        struct('scheme','traditional', ...
        'tx_reference_hash',traditional.tx_ref.reference_hash_sha256)}}));
    Result_Log_Stage(run, 'INFO', 'decode', ...
        'Matched point complete: IQ-MIMO pass=%d, traditional pass=%d.', ...
        iqmimo.pass, traditional.pass);
    Result_Finalize_Run(run, ternary(passed,'completed', ...
        'completed_with_failures'), 'normal_completion', [], '');
    assert_flat(run);
    output = struct('run_dir',run.OutputDir,'iqmimo',iqmimo, ...
        'traditional',traditional,'fairness',fairness,'pass',passed);
catch exception
    if opts.write_results
        failure = struct('options',opts);
        if exist('iqmimo','var'), failure.iqmimo = iqmimo; end
        if exist('traditional','var'), failure.traditional = traditional; end
        msiq.save_failure(run.OutputDir,failure);
    end
    finalize_failure(run, exception);
    rethrow(exception);
end
end

function output = run_sweep(opts)
[dual_cfg, traditional_cfg, fairness] = build_pair_configs(opts);
run = create_run(dual_cfg, 'simulation', 'EQ_RATE_SNR_SWEEP', ...
    'simulation', opts, fairness, 2*numel(opts.snr_points_db));
try
    if opts.write_results
    plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
    Result_Summary_Initialize(run, summary_columns(), summary_units());
    end
    point_template = struct('snr_db',NaN,'iqmimo',struct(), ...
        'traditional',struct());
    points = repmat(point_template, 1, numel(opts.snr_points_db));
    rows = repmat(empty_metric_row(), 0, 1);
    summary_rows = cell(0,1);
    for point_index = 1:numel(opts.snr_points_db)
        snr_db = opts.snr_points_db(point_index);
        points(point_index).snr_db = snr_db;
        iqmimo = run_scheme( ...
            'iqmimo', dual_cfg, opts, snr_db);
        traditional = run_scheme( ...
            'traditional', traditional_cfg, opts, snr_db);
        if opts.write_results
        plot_scheme_channels(run,iqmimo,2*point_index-1,snr_db);
        plot_scheme_channels(run,traditional,2*point_index,snr_db);
        end
        summary_rows{end+1,1} = scheme_summary_rows(iqmimo, ...
            2*point_index-1, snr_db, ''); %#ok<AGROW>
        summary_rows{end+1,1} = scheme_summary_rows(traditional, ...
            2*point_index, snr_db, ''); %#ok<AGROW>
        for channel_index = 1:numel(iqmimo.streams)
            rows(end+1) = metric_row(iqmimo, snr_db, channel_index); %#ok<AGROW>
        end
        for channel_index = 1:numel(traditional.streams)
            rows(end+1) = metric_row(traditional, snr_db, channel_index); %#ok<AGROW>
        end
        points(point_index).iqmimo = compact_scheme(iqmimo);
        points(point_index).traditional = compact_scheme(traditional);
        if opts.write_results && opts.save_raw
            save(msiq.output_path(run, sprintf('%03d_iqmimo_full.mat', ...
                2*point_index-1)), 'iqmimo', '-v7.3');
            save(msiq.output_path(run, sprintf('%03d_traditional_full.mat', ...
                2*point_index)), 'traditional', '-v7.3');
        end
    end
    if ~opts.write_results
        output = struct('run_dir','','points',points,'rows',rows,'fairness',fairness,'pass',all([rows.pass]));
        return;
    end
    all_summary_rows = vertcat(summary_rows{:});
    Result_Summary_Append(run, all_summary_rows);
    save(msiq.output_path(run, 'effective_configs.mat'), ...
        'dual_cfg','traditional_cfg','-v7.3');
    save(msiq.output_path(run, 'sweep_result.mat'), ...
        'points', 'fairness', 'opts', '-v7.3');
    write_sweep_metrics_csv(msiq.output_path(run, 'sweep_metrics.csv'), rows);
    plot_sweep_overview(msiq.output_path(run, 'overview.png'), rows, ...
        fairness, opts);
    passed = all([rows.pass]);
    Result_Update_Run_Info(run, struct( ...
        'counts', struct('planned',numel(rows),'executed',numel(rows), ...
        'succeeded',nnz([rows.pass]),'failed',nnz(~[rows.pass]),'invalid',0), ...
        'safety', struct('preflight','not_applicable', ...
        'initial_outputs','not_accessed','shutdown','not_required', ...
        'shutdown_readback','not_required','instrument_io_delta', ...
        msiq.instruments.get_audit()), ...
        'parameters', struct('fairness',fairness,'impairments',impairments(opts), ...
        'snr_points_db',opts.snr_points_db,'options',opts, ...
        'effective_config_iqmimo',dual_cfg,'effective_config_traditional',traditional_cfg), ...
        'inputs', {{struct('source','synthetic_equal_rate_pairing')}}));
    Result_Log_Stage(run, 'INFO', 'decode', ...
        'SNR sweep completed at %d matched points.', numel(rows)/2);
    Result_Finalize_Run(run, ternary(passed,'completed', ...
        'completed_with_failures'), 'normal_completion', [], '');
    assert_flat(run);
    output = struct('run_dir',run.OutputDir,'points',points, ...
        'rows',rows,'fairness',fairness,'pass',passed);
catch exception
    if opts.write_results
        failure = struct('options',opts);
        if exist('points','var'), failure.points = points; end
        if exist('iqmimo','var'), failure.iqmimo = iqmimo; end
        if exist('traditional','var'), failure.traditional = traditional; end
        msiq.save_failure(run.OutputDir,failure);
    end
    finalize_failure(run, exception);
    rethrow(exception);
end
end

function output = run_analysis(matched, sweep, opts)
cfg = matched.iqmimo.cfg;
run = create_run(cfg, 'analysis', 'EQ_RATE_COMPARISON', ...
    'offline_analysis', opts, matched.fairness, 2);
try
    if opts.write_results
    plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
    Result_Summary_Initialize(run, summary_columns(), summary_units());
    Result_Write_Sources(run, {matched.run_dir,sweep.run_dir});
    end
    analysis_summary_rows = [ ...
        scheme_summary_rows(matched.iqmimo, 1, opts.matched_snr_db, ''); ...
        scheme_summary_rows(matched.traditional, 2, opts.matched_snr_db, '')];
    if opts.write_results, Result_Summary_Append(run, analysis_summary_rows); end
    matched_summary = struct( ...
        'iqmimo',matched.iqmimo.aggregate, ...
        'traditional',matched.traditional.aggregate, ...
        'evm_difference_percentage_points', ...
        100*(matched.traditional.aggregate.evm_rms - ...
        matched.iqmimo.aggregate.evm_rms), ...
        'mer_difference_db',matched.traditional.aggregate.mer_db - ...
        matched.iqmimo.aggregate.mer_db, ...
        'equal_gross_rate',matched.fairness.iqmimo_total_gross_rate_bps == ...
        matched.fairness.traditional_total_gross_rate_bps, ...
        'equal_physical_duration',abs(matched.fairness.duration_difference_s) ...
        <= 2/65e9);
    payload = struct('matched_summary',matched_summary, ...
        'sweep_rows',sweep.rows);
    if ~opts.write_results
        output = struct('run_dir','','matched_summary',matched_summary, ...
            'pass',matched.pass,'source_runs',{{}});
        return;
    end
    if opts.save_raw
        save(msiq.output_path(run,'analysis_result.mat'), ...
            '-struct','payload','-v7.3');
    end
    write_json(msiq.output_path(run,'matched_summary.json'),matched_summary);
    plot_analysis_overview(msiq.output_path(run,'overview.png'), ...
        matched,sweep,opts);
    passed = matched.pass;
    Result_Update_Run_Info(run,struct( ...
        'counts',struct('planned',2,'executed',2, ...
        'succeeded',double(matched.iqmimo.pass)+ ...
        double(matched.traditional.pass), ...
        'failed',double(~matched.iqmimo.pass)+ ...
        double(~matched.traditional.pass),'invalid',0), ...
        'safety',struct('preflight','not_applicable', ...
        'initial_outputs','not_accessed','shutdown','not_required', ...
        'shutdown_readback','not_required','instrument_io_delta', ...
        msiq.instruments.get_audit()), ...
        'parameters',struct('fairness',matched.fairness, ...
        'matched_summary',matched_summary,'snr_points_db',opts.snr_points_db)));
    Result_Log_Stage(run,'INFO','analysis', ...
        'Combined matched point and SNR sweep without modifying source runs.');
    Result_Finalize_Run(run,ternary(passed,'completed', ...
        'completed_with_failures'),'normal_completion',[],'');
    assert_flat(run);
    output = struct('run_dir',run.OutputDir,'matched_summary',matched_summary, ...
        'pass',passed,'source_runs',{{matched.run_dir,sweep.run_dir}});
catch exception
    if opts.write_results
        msiq.save_failure(run.OutputDir,msiq.analysis_record(struct( ...
            'options',opts,'matched',matched,'sweep',sweep)));
    end
    finalize_failure(run,exception);
    rethrow(exception);
end
end

function scheme = run_scheme(name, cfg, opts, snr_db)
seed = opts.seed;
[waveforms, tx_ref] = msiq.generate_waveforms(cfg, seed);
if strcmp(name, 'iqmimo')
    raw = simulate_iqmimo_capture(waveforms, cfg, opts, snr_db);
    decoded = msiq.decode_capture(raw, tx_ref, cfg);
    streams = decoded.primary_streams;
    role = 'two_parallel_independent_16QAM_streams';
else
    [raw, serial_reference] = simulate_traditional_capture( ...
        waveforms, tx_ref, cfg, opts, snr_db);
    decoded = decode_traditional_serial(raw, serial_reference, cfg);
    streams = decoded.primary_streams;
    role = 'one_complex_16QAM_stream_with_two_serial_codewords';
end
scheme = struct('name',name,'role',role,'cfg',cfg,'waveforms',waveforms, ...
    'tx_ref',tx_ref,'raw',raw,'decoded',decoded,'streams',streams, ...
    'pass',decoded.pass,'aggregate',aggregate_streams(streams));
scheme.aggregate.net_information_rate_bps = nominal_net_rate(cfg, name);
end

function raw = simulate_iqmimo_capture(waveforms, ~, opts, snr_db)
samples = double(waveforms.master_dac_data(:,1:2));
samples = normalize_branch_power(samples);
samples = (opts.common_iq_matrix*samples.').';
samples = normalize_branch_power(samples);
n = (0:size(samples,1)-1).';
for channel = 1:2
    analytic = hilbert(samples(:,channel));
    samples(:,channel) = real(analytic .* ...
        exp(1j*2*pi*opts.cfo_hz/65e9*n));
end
[samples, applied_sro_ppm] = apply_sro(samples, opts.sro_ppm);
samples = add_real_awgn(samples, snr_db, ...
    opts.seed + round(100*snr_db) + 17);
samples = clip_real(samples, opts.clip_level);
if opts.prepend_samples > 0
    samples = [zeros(opts.prepend_samples,2); samples];
end
time = (0:size(samples,1)-1).'/65e9;
raw = struct('samples',samples,'time_axes',[time, ...
    time + opts.time_axis_skew_samples/65e9], ...
    'sample_rate_hz',65e9,'already_baseband',false, ...
    'architecture','dual_iq_mimo','iq_pair',false, ...
    'payload_pair','A','full_scale',opts.clip_level, ...
    'clip_fraction',mean(abs(samples) >= opts.clip_level,1), ...
    'simulation_options',struct('snr_db',snr_db,'cfo_hz',opts.cfo_hz, ...
    'sro_ppm',applied_sro_ppm,'common_iq_matrix',opts.common_iq_matrix, ...
    'power_normalization','unit_total_branch_average_power'));
end

function [raw, reference] = simulate_traditional_capture( ...
        waveforms, tx_ref, cfg, opts, snr_db)
% Serialize pair A then pair B at 2 Sa/sym before the 31/4 physical rate map.
base_rate = cfg.waveform.master_sample_rate_hz;
physical_rate = 65e9;
first = complex(waveforms.master_dac_data(:,1), ...
    waveforms.master_dac_data(:,2));
second = complex(waveforms.master_dac_data(:,3), ...
    waveforms.master_dac_data(:,4));
baseband = [first; second];
baseband = normalize_average_power(baseband);
% 31/4 moves the 2 Sa/sym baseband to the common physical 65 GSa/s domain.
i_physical = resample(real(baseband), 31, 4);
q_physical = resample(imag(baseband), 31, 4);
count = min(numel(i_physical), numel(q_physical));
samples = [i_physical(1:count), q_physical(1:count)];
samples = normalize_branch_power(samples);
samples = (opts.common_iq_matrix*samples.').';
samples = normalize_branch_power(samples);
n = (0:size(samples,1)-1).';
rotated = complex(samples(:,1),samples(:,2)) .* ...
    exp(1j*2*pi*opts.cfo_hz/physical_rate*n);
samples = [real(rotated),imag(rotated)];
[samples, applied_sro_ppm] = apply_sro(samples,opts.sro_ppm);
samples = add_real_awgn(samples,snr_db, ...
    opts.seed + round(100*snr_db) + 29);
samples = clip_real(samples,opts.clip_level);
if opts.prepend_samples > 0
    samples = [zeros(opts.prepend_samples,2); samples];
end
time = (0:size(samples,1)-1).'/physical_rate;
raw = struct('samples',samples,'time_axes',[time, ...
    time + opts.time_axis_skew_samples/physical_rate], ...
    'sample_rate_hz',physical_rate,'already_baseband',true, ...
    'architecture','single_complex_stream','iq_pair',true, ...
    'payload_pair','SERIAL_AB','full_scale',opts.clip_level, ...
    'clip_fraction',mean(abs(samples) >= opts.clip_level,1), ...
    'simulation_options',struct('snr_db',snr_db,'cfo_hz',opts.cfo_hz, ...
    'sro_ppm',applied_sro_ppm,'physical_resample_p',31, ...
    'physical_resample_q',4,'baseband_sample_rate_hz',base_rate));
reference = struct('frame',tx_ref.frame,'pairs',tx_ref.pairs, ...
    'architecture','single_complex_stream','reference_payload_policy', ...
    'metrics_only','waveform_id',sprintf('EQ_RATE_SC_SERIAL_seed%d',opts.seed), ...
    'reference_hash_sha256',tx_ref.reference_hash_sha256);
end

function decoded = decode_traditional_serial(raw, reference, cfg)
[baseband, preparation] = prepare_traditional_capture(raw, cfg);
frame = reference.frame;
frame_samples = frame.symbol_count*cfg.receiver.single_samples_per_symbol;
serialized_frame_samples = frame_samples*cfg.waveform.frame_repetitions;
% Locate the two serialized payload frames from their repeated-ZC headers.
% The midpoint is only a rough expectation and drifts under SRO/resampling.
[~, synchronization] = msiq.dsp.synchronize_single_wz(baseband, ...
    reference, cfg, true);
corrected = synchronization.corrected_capture(:);
starts = synchronization.candidate_frame_starts(:);
starts = starts(isfinite(starts) & starts >= 1 & ...
    starts + serialized_frame_samples - 1 <= numel(corrected));
starts = unique(round(starts), 'stable');
if numel(starts) < 2
    error('msiq:equalrate:TraditionalLength', ...
        'Traditional capture contains fewer than two synchronized serial frames.');
end
% Pick the pair whose separation is closest to the complete serialized
% frame (all synchronization repetitions included).
pairs = nchoosek(1:numel(starts), 2);
separation_error = abs((starts(pairs(:,2))-starts(pairs(:,1))) - ...
    serialized_frame_samples);
[~, best_pair] = min(separation_error);
starts = starts(pairs(best_pair,:));
starts = sort(starts(:));
result_cells = cell(1,2);
for index = 1:2
    segment = corrected(starts(index):starts(index)+serialized_frame_samples-1);
    raw_one = struct('samples',[real(segment),imag(segment)], ...
        'sample_rate_hz',cfg.waveform.master_sample_rate_hz, ...
        'already_baseband',true,'payload_pair',char('A'+index-1), ...
        'full_scale',raw.full_scale,'clip_fraction',raw.clip_fraction);
    ref_one = struct('schema_version','2.0','waveform_id', ...
        sprintf('%s_frame%d',reference.waveform_id,index), ...
        'reference_hash_sha256',reference.reference_hash_sha256, ...
        'architecture','single_complex_stream', ...
        'pairs',reference.pairs(index),'frame',reference.frame);
    ref_one.frame.reference_payload_policy = 'metrics_only';
    result_cells{index} = msiq.decode_capture(raw_one, ref_one, cfg);
end
results = [result_cells{:}];
streams = [results(1).primary_streams, results(2).primary_streams];
decoded = struct('schema_version','2.0','waveform_id',reference.waveform_id, ...
    'architecture','single_complex_stream','sync_ok',all([results.sync_ok]), ...
    'synchronization',remove_if_present(synchronization, ...
        'corrected_capture'),'preparation',preparation, ...
    'primary_equalizer',results(1).primary_equalizer, ...
    'primary_streams',streams,'diagnostic_equalizer', ...
    struct('name','not_applicable'), ...
    'payload_reference_used_for_processing',false, ...
    'reference_payload_policy','metrics_only', ...
    'clip_fraction',raw.clip_fraction,'clipped',any(raw.clip_fraction > 0), ...
    'complete_block_count',sum([streams.block_count]), ...
    'discarded_incomplete_block_count', ...
    sum([streams.incomplete_tail_bits] > 0), ...
    'pass',all([streams.pass]) && ~any(raw.clip_fraction > 0), ...
    'serial_frame_count',2,'serial_frame_starts',starts, ...
    'serial_frame_separation_samples',diff(starts), ...
    'serialized_frame_samples',serialized_frame_samples, ...
    'serial_results',results);
end

function [baseband, info] = prepare_traditional_capture(raw, cfg)
samples = double(raw.samples);
time_axes = double(raw.time_axes);
start_time = max(time_axes(1,:));
stop_time = min(time_axes(end,:));
time = time_axes(:,1);
keep = time >= start_time & time <= stop_time;
common_time = time(keep);
aligned = zeros(numel(common_time),2);
for channel = 1:2
    aligned(:,channel) = interp1(time_axes(:,channel),samples(:,channel), ...
        common_time,'pchip');
end
valid = all(isfinite(aligned),2);
aligned = aligned(valid,:);
complex_physical = complex(aligned(:,1)-median(aligned(:,1)), ...
    aligned(:,2)-median(aligned(:,2)));
baseband = resample(complex_physical,4,31);
baseband = normalize_average_power(baseband);
info = struct('source_sample_rate_hz',raw.sample_rate_hz, ...
    'output_sample_rate_hz',cfg.waveform.master_sample_rate_hz, ...
    'resample_p',4,'resample_q',31,'processing_samples_per_symbol',2, ...
    'iq_preprocessing',struct('applied',true, ...
    'combined_as_complex_pair',true), ...
    'alignment',struct('applied',true,'offset_samples',[0, ...
    median(time_axes(:,2)-time_axes(:,1))*raw.sample_rate_hz]), ...
    'input_samples',size(raw.samples,1),'output_samples',numel(baseband), ...
    'baseband_preview',baseband(1:min(8000,numel(baseband))), ...
    'baseband_preview_indices',(1:min(8000,numel(baseband))).');
end

function [dual_cfg, traditional_cfg, fair] = build_pair_configs(opts)
dual_cfg = msiq.build_config('v2_default');
dual_cfg.waveform.frame_repetitions = 3;
dual_cfg.waveform.periodic_rrc = true;
dual_cfg.waveform.rrc_span_symbols = 24;
dual_cfg.waveform.sync_length_symbols = 1024;
dual_cfg.waveform.sync_repeats = 2;
dual_cfg.waveform.training_symbols = 2048;
dual_cfg.waveform.pilot_interval_symbols = 512;
dual_cfg.waveform.guard_symbols = 64;
dual_cfg.waveform.ldpc_blocks_per_frame = 1;

traditional_cfg = msiq.build_config('v2_traditional_wz');
traditional_cfg.waveform.master_sample_rate_hz = ...
    4*dual_cfg.waveform.symbol_rate_hz;
traditional_cfg.waveform.awg_sample_rate_hz = ...
    traditional_cfg.waveform.master_sample_rate_hz;
traditional_cfg.waveform.symbol_rate_hz = ...
    2*dual_cfg.waveform.symbol_rate_hz;
traditional_cfg.waveform.master_samples_per_symbol = 2;
traditional_cfg.waveform.awg_samples_per_symbol = 2;
traditional_cfg.waveform.decimation = 1;
traditional_cfg.waveform.if_center_hz = 0;
traditional_cfg.waveform.rrc_span_symbols = 24;
traditional_cfg.waveform.sync_length_symbols = 1024;
traditional_cfg.waveform.sync_repeats = 2;
traditional_cfg.waveform.training_symbols = 2048;
traditional_cfg.waveform.pilot_interval_symbols = 512;
traditional_cfg.waveform.guard_symbols = 64;
traditional_cfg.waveform.frame_repetitions = 3;
traditional_cfg.waveform.ldpc_blocks_per_frame = 1;
traditional_cfg.receiver.wl_taps = 61;
traditional_cfg.receiver.wl_passes = 6;
traditional_cfg.receiver.wl_step_size = 0.15;
traditional_cfg.receiver.wl_timing_offsets_samples = -4:4;
traditional_cfg.receiver.joint_track_enabled = true;
traditional_cfg.receiver.single_samples_per_symbol = 2;

if ~isempty(opts.results_root)
    dual_cfg.results_root = char(string(opts.results_root));
    traditional_cfg.results_root = char(string(opts.results_root));
end

payload_bits = dual_cfg.waveform.ldpc_blocks_per_frame * ...
    msiq.fec.build(dual_cfg).codeword_length;
dual_duration = frame_duration(dual_cfg);
traditional_duration = 2*frame_duration(traditional_cfg);
fair = struct('comparison','equal_total_gross_rate', ...
    'modulation','16QAM','fec','DVB-S2 LDPC 9/10', ...
    'physical_sample_rate_hz',65e9, ...
    'iqmimo_branch_symbol_rate_hz',dual_cfg.waveform.symbol_rate_hz, ...
    'traditional_symbol_rate_hz',traditional_cfg.waveform.symbol_rate_hz, ...
    'iqmimo_total_gross_rate_bps',2*dual_cfg.waveform.symbol_rate_hz*4, ...
    'traditional_total_gross_rate_bps',traditional_cfg.waveform.symbol_rate_hz*4, ...
    'iqmimo_parallel_codewords',2, ...
    'traditional_serial_codewords',2, ...
    'frame_repetitions',dual_cfg.waveform.frame_repetitions, ...
    'repetition_policy','same payload frame repeated for synchronization and SRO; not new information', ...
    'codeword_bits_per_stream',payload_bits, ...
    'iqmimo_unique_net_information_rate_bps', ...
        2*msiq.fec.build(dual_cfg).info_length/dual_duration, ...
    'traditional_unique_net_information_rate_bps', ...
        2*msiq.fec.build(traditional_cfg).info_length/traditional_duration, ...
    'iqmimo_physical_duration_s',dual_duration, ...
    'traditional_physical_duration_s',traditional_duration, ...
    'duration_difference_s',traditional_duration-dual_duration, ...
    'rrc_rolloff',dual_cfg.waveform.rolloff, ...
    'common_total_average_power_normalized',true, ...
    'traditional_tx_baseband_sps',2, ...
    'traditional_physical_resample_p',31, ...
    'traditional_physical_resample_q',4, ...
    'traditional_rx_resample_p',4, ...
    'traditional_rx_resample_q',31, ...
    'payload_reference_policy','metrics_only');
if abs(fair.duration_difference_s) > 2/65e9
    error('msiq:equalrate:DurationMismatch', ...
        'The two physical waveform durations are not equal.');
end
end

function duration = frame_duration(cfg)
fec = msiq.fec.build(cfg);
payload_symbols = cfg.waveform.ldpc_blocks_per_frame * ...
    fec.codeword_length/log2(cfg.waveform.modulation_order);
pilot_count = ceil(payload_symbols/cfg.waveform.pilot_interval_symbols);
symbols = 2*cfg.waveform.guard_symbols + ...
    cfg.waveform.sync_length_symbols*cfg.waveform.sync_repeats + ...
    cfg.waveform.training_symbols + payload_symbols + pilot_count;
duration = cfg.waveform.frame_repetitions*symbols/cfg.waveform.symbol_rate_hz;
end

function run = create_run(cfg, run_type, name_part, execution_mode, ...
        opts, fairness, planned)
if ~opts.write_results
    run = struct('OutputDir','','ProjectRoot',cfg.project_root);
    return;
end
run = Result_Create_Run(struct( ...
    'ProjectRoot',cfg.project_root,'ResultsRoot',cfg.results_root, ...
    'RunType',run_type,'NameParts',{{name_part}}, ...
    'RetentionMode',opts.retention_mode, ...
    'DisplayColumns',{{'序号','方案','Channel','SNR','EVM','MER', ...
        'pre-FEC BER','post-FEC BER','BLER','净信息速率','状态'}}, ...
    'ProjectName','multistream_iq_SC', ...
    'TestName','equal_rate_traditional_complex_16qam_vs_iqmimo', ...
    'RunPurpose','validation','ExecutionMode',execution_mode, ...
    'EntryPoint','EqualRate_16QAM_Comparison.m', ...
    'Parameters',struct('fairness',fairness,'options',opts), ...
    'Counts',struct('planned',planned), 'Instruments',struct([]), ...
    'Safety',struct('preflight','not_applicable', ...
    'initial_outputs','not_accessed','shutdown','not_required', ...
    'shutdown_readback','not_required')));
end

function rows = scheme_summary_rows(scheme, repeat, snr_db, raw_file)
rows = cell(numel(scheme.streams), 21);
for stream_index = 1:numel(scheme.streams)
    stream = scheme.streams(stream_index);
    rows(stream_index,:) = {scheme.name,stream_index,snr_db, ...
        100*stream.evm_rms,stream.mer_db,stream.pre_fec_ber, ...
        stream.post_fec_ber,stream.bler,stream.block_count, ...
        stream.block_error_count,double(stream.parity_converged), ...
        stream.payload_symbol_count,scheme.aggregate.net_information_rate_bps, ...
        ternary(stream.pass,'成功','失败'),repeat,1, ...
        char(datetime('now','TimeZone','local', ...
        'Format','yyyy-MM-dd''T''HH:mm:ssXXX')), ...
        raw_file,'', '', ''};
end
end

function columns = summary_columns()
columns = {'方案','Channel','SNR','EVM','MER','pre-FEC BER', ...
    'post-FEC BER','BLER','完整LDPC块','错误LDPC块','parity收敛', ...
    '有效16QAM符号','净信息速率','状态','序号','attempt', ...
    '采集时间','原始数据文件','单次图片文件','错误代码','错误信息'};
end

function units = summary_units()
units = {'-','-','dB','%','dB','-','-','-','block','block', ...
    '-','symbol','bit/s','-','-','-','-','-','-','-','-'};
end

function aggregate = aggregate_streams(streams)
payload_bits = sum(arrayfun(@(x) x.fec.post_fec_bit_count, streams));
if isempty(streams)
    aggregate = struct('pre_fec_ber',NaN,'post_fec_ber',NaN, ...
        'bler',NaN,'evm_rms',NaN,'mer_db',NaN, ...
        'net_information_rate_bps',NaN);
    return;
end
pre_errors = sum(arrayfun(@(x) x.fec.pre_fec_bit_error_count, streams));
pre_bits = sum(arrayfun(@(x) x.fec.pre_fec_bit_count, streams));
post_errors = sum(arrayfun(@(x) x.fec.post_fec_bit_error_count, streams));
post_bits = sum(arrayfun(@(x) x.fec.post_fec_bit_count, streams));
aggregate = struct('pre_fec_ber',pre_errors/max(pre_bits,1), ...
    'post_fec_ber',post_errors/max(post_bits,1), ...
    'bler',sum([streams.block_error_count])/max(sum([streams.block_count]),1), ...
    'evm_rms',sqrt(mean([streams.evm_rms].^2)), ...
    'mer_db',mean([streams.mer_db]), ...
    'complete_blocks',sum([streams.block_count]), ...
    'payload_bits',payload_bits,'net_information_rate_bps',NaN);
end

function rate = nominal_net_rate(cfg, name)
fec = msiq.fec.build(cfg);
% frame_duration includes all repeated copies. Repeated copies carry the
% same codeword and therefore contribute time, but no additional payload.
full_frame_duration = frame_duration(cfg);
if strcmp(name,'iqmimo')
    rate = 2*fec.info_length/full_frame_duration;
else
    rate = 2*fec.info_length/(2*full_frame_duration);
end
end

function row = metric_row(scheme, snr_db, channel)
row = empty_metric_row();
stream = scheme.streams(channel);
row.scheme = string(sprintf('%s_Channel%d', scheme.name, channel));
row.snr_db = snr_db;
row.evm_percent = 100*stream.evm_rms;
row.mer_db = stream.mer_db;
row.pre_fec_ber = stream.pre_fec_ber;
row.post_fec_ber = stream.post_fec_ber;
row.bler = stream.bler;
row.pass = stream.pass;
end

function row = empty_metric_row()
row = struct('scheme',"",'snr_db',NaN,'evm_percent',NaN, ...
    'mer_db',NaN,'pre_fec_ber',NaN,'post_fec_ber',NaN, ...
    'bler',NaN,'pass',false);
end

function write_sweep_metrics_csv(path, rows)
columns = {'方案','SNR','EVM','MER','pre-FEC BER','post-FEC BER','BLER','通过'};
units = {'-','dB','%','dB','-','-','-','-'};
    fid = Result_Open_File_Retry(path,'w','n','UTF-8');
if fid < 0
    error('msiq:equalrate:SweepCsv', 'Cannot create %s.', path);
end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid,uint8([239 187 191]),'uint8');
fprintf(fid,'%s\n',strjoin(columns,','));
fprintf(fid,'%s\n',strjoin(units,','));
for index = 1:numel(rows)
    fprintf(fid,'%s,%.15g,%.15g,%.15g,%.15g,%.15g,%.15g,%d\n', ...
        rows(index).scheme,rows(index).snr_db,rows(index).evm_percent, ...
        rows(index).mer_db,rows(index).pre_fec_ber, ...
        rows(index).post_fec_ber,rows(index).bler,rows(index).pass);
end
end

function plot_matched_overview(path, iqmimo, traditional, fair, opts)
style = Test_Project_Plot_Style();
fig = figure('Visible',opts.plot_visible,'Color','w', ...
    'Units','inches','Position',[1 1 8.2 5.4]);
cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig,2,2,'TileSpacing','compact','Padding','compact');
schemes = {iqmimo,traditional};
names = {'IQ-MIMO','Traditional complex'};
colors = [style.Colors(1,:); style.Colors(2,:)];

all_streams = [iqmimo.streams, traditional.streams];
channel_names = [arrayfun(@(k) sprintf('IQ-MIMO Ch%d', k), ...
    1:numel(iqmimo.streams),'UniformOutput',false), ...
    arrayfun(@(k) sprintf('Traditional Ch%d', k), ...
    1:numel(traditional.streams),'UniformOutput',false)];
nexttile(layout,1);
bar(100*[all_streams.evm_rms], ...
    'FaceColor','flat');
set(gca,'XTickLabel',channel_names); ylabel('EVM (%)');
title('Matched physical impairment'); grid on;

nexttile(layout,2);
bar([all_streams.mer_db], ...
    'FaceColor','flat');
set(gca,'XTickLabel',channel_names); ylabel('MER (dB)');
title('Receiver quality'); grid on;

nexttile(layout,3);
for index = 1:2
    stream = schemes{index}.streams(1);
    symbols = stream.constellation_symbols;
    plot(real(symbols),imag(symbols),'.','Color',colors(index,:), ...
        'MarkerSize',2); hold on;
end
ideal = qammod((0:15).',16,'UnitAveragePower',true);
plot(real(ideal),imag(ideal),'ks','LineStyle','none','MarkerSize',6);
hold off; axis equal; grid on; xlabel('I'); ylabel('Q');
title('First decoded codeword constellation');
legend({'IQ-MIMO stream 1','Traditional frame 1','Ideal 16QAM'}, ...
    'Location','best','Box','off');

nexttile(layout,4); axis off;
text(0,0.95,sprintf(['Equal-rate condition\n\nIQ-MIMO: 2 x %.6f GBd x 4 bit/sym\n', ...
    'Traditional: 1 x %.6f GBd x 4 bit/sym\n\n', ...
    'Physical Fs: %.1f GSa/s\nRRC roll-off: %.2f\n', ...
    'CFO: %.0f kHz | SRO: %.1f ppm\n', ...
    'Total TX power normalized identically\n', ...
    'Payload is metrics-only for both receivers'], ...
    fair.iqmimo_branch_symbol_rate_hz/1e9, ...
    fair.traditional_symbol_rate_hz/1e9, ...
    fair.physical_sample_rate_hz/1e9,fair.rrc_rolloff, ...
    opts.cfo_hz/1e3,opts.sro_ppm), ...
    'VerticalAlignment','top','FontName',style.FontName,'FontSize',10);
title('Fairness record');
sgtitle('Equal-rate 16QAM: traditional complex modulation versus IQ-MIMO', ...
    'FontName',style.FontName,'FontWeight','bold');
Test_Project_Export_PNG(fig,path,style);
end

function plot_matched_constellation(path, iqmimo, traditional, opts)
style = Test_Project_Plot_Style();
fig = figure('Visible',opts.plot_visible,'Color','w', ...
    'Units','inches','Position',[1 1 7.1 4.2]);
cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig,1,3,'TileSpacing','compact','Padding','compact');
items = {iqmimo.streams(1),'IQ-MIMO stream 1'; ...
    iqmimo.streams(2),'IQ-MIMO stream 2'; ...
    traditional.streams(1),'Traditional serial frame 1'};
ideal = qammod((0:15).',16,'UnitAveragePower',true);
for index = 1:3
    ax = nexttile(layout,index);
    stream = items{index,1};
    plot(ax,real(stream.constellation_symbols),imag(stream.constellation_symbols), ...
        '.','MarkerSize',2,'Color',style.Colors(index,:)); hold(ax,'on');
    plot(ax,real(ideal),imag(ideal),'ks','LineStyle','none','MarkerSize',6);
    hold(ax,'off'); axis(ax,'equal'); grid(ax,'on');
    xlabel(ax,'I'); ylabel(ax,'Q');
    title(ax,sprintf('%s\nEVM %.2f%%, MER %.2f dB',items{index,2}, ...
        100*stream.evm_rms,stream.mer_db),'FontSize',9);
end
sgtitle('Equal-rate decoded constellations','FontName',style.FontName, ...
    'FontWeight','bold');
Test_Project_Export_PNG(fig,path,style);
end

function plot_sweep_overview(path, rows, fair, opts)
style = Test_Project_Plot_Style();
fig = figure('Visible',opts.plot_visible,'Color','w', ...
    'Units','inches','Position',[1 1 7.2 7.1]);
cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig,3,1,'TileSpacing','compact','Padding','compact');
schemes = unique(string({rows.scheme}),'stable');
metrics = {'evm_percent','mer_db','post_fec_ber'};
ylabels = {'EVM (%)','MER (dB)','post-FEC BER'};
for metric_index = 1:numel(metrics)
    ax = nexttile(layout,metric_index); hold(ax,'on');
    for scheme_index = 1:numel(schemes)
        mask = string({rows.scheme}) == schemes(scheme_index);
        x = [rows(mask).snr_db];
        y = [rows(mask).(metrics{metric_index})];
        y(~[rows(mask).pass]) = NaN;
        if metric_index == 3
            y(y == 0) = 1e-8;
        end
        plot(ax,x,y,'o-','LineWidth',style.LineWidth, ...
            'MarkerSize',style.MeanMarkerSize, ...
            'Color',style.Colors(scheme_index,:), ...
            'DisplayName',schemes(scheme_index));
    end
    hold(ax,'off'); grid(ax,'on'); ylabel(ax,ylabels{metric_index});
    if metric_index == 3
        set(ax,'YScale','log');
    end
    if metric_index == numel(metrics)
        xlabel(ax,'Synthetic SNR (dB)');
    end
    legend(ax,'Location','best','Box','off');
end
sgtitle(sprintf(['Equal-rate SNR sweep | 2 x %.6f GBd IQ-MIMO versus ', ...
    '%.6f GBd traditional complex 16QAM'], ...
    fair.iqmimo_branch_symbol_rate_hz/1e9, ...
    fair.traditional_symbol_rate_hz/1e9), ...
    'FontName',style.FontName,'FontWeight','bold');
Test_Project_Export_PNG(fig,path,style);
end

function plot_analysis_overview(path, matched, sweep, opts)
style = Test_Project_Plot_Style();
fig = figure('Visible',opts.plot_visible,'Color','w', ...
    'Units','inches','Position',[1 1 8.2 6.6]);
cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig,2,2,'TileSpacing','compact','Padding','compact');
schemes = unique(string({sweep.rows.scheme}),'stable');
display_names = cellstr(schemes);

ax = nexttile(layout,1);
values = [matched.iqmimo.streams,matched.traditional.streams];
bar(ax,100*[values.evm_rms]);
set(ax,'XTickLabel',display_names); ylabel(ax,'EVM (%)');
title(ax,sprintf('Matched point: %.1f dB',opts.matched_snr_db)); grid(ax,'on');

ax = nexttile(layout,2); hold(ax,'on');
for index = 1:numel(schemes)
    mask = string({sweep.rows.scheme}) == schemes(index);
    evm = [sweep.rows(mask).evm_percent];
    evm(~[sweep.rows(mask).pass]) = NaN;
    plot(ax,[sweep.rows(mask).snr_db],evm, ...
        'o-','LineWidth',style.LineWidth,'MarkerSize',style.MeanMarkerSize, ...
        'Color',style.Colors(index,:),'DisplayName',display_names{index});
end
hold(ax,'off'); grid(ax,'on'); xlabel(ax,'Synthetic SNR (dB)');
ylabel(ax,'EVM (%)'); title(ax,'SNR sweep');
legend(ax,'Location','best','Box','off');

ax = nexttile(layout,3); hold(ax,'on');
for index = 1:numel(schemes)
    mask = string({sweep.rows.scheme}) == schemes(index);
    values = [sweep.rows(mask).post_fec_ber];
    values(~[sweep.rows(mask).pass]) = NaN;
    values(values == 0) = 1e-8;
    plot(ax,[sweep.rows(mask).snr_db],values,'o-', ...
        'LineWidth',style.LineWidth,'MarkerSize',style.MeanMarkerSize, ...
        'Color',style.Colors(index,:),'DisplayName',display_names{index});
end
hold(ax,'off'); set(ax,'YScale','log'); grid(ax,'on');
xlabel(ax,'Synthetic SNR (dB)'); ylabel(ax,'post-FEC BER');
title(ax,'FEC result (zero displayed at 1e-8)');
legend(ax,'Location','best','Box','off');

ax = nexttile(layout,4); axis(ax,'off');
fair = matched.fairness;
text(ax,0,0.95,sprintf(['Same gross rate: %.6f Gbit/s\n', ...
    'Same physical duration: %.3f us\nSame total average TX power\n', ...
    'Same 2x2 I/Q coupling, CFO, SRO, and SNR definition'], ...
    fair.iqmimo_total_gross_rate_bps/1e9, ...
    1e6*fair.iqmimo_physical_duration_s), ...
    'VerticalAlignment','top','FontName',style.FontName,'FontSize',10);
title(ax,'Fairness and matched result');
sgtitle('Equal-rate traditional complex 16QAM versus IQ-MIMO', ...
    'FontName',style.FontName,'FontWeight','bold');
Test_Project_Export_PNG(fig,path,style);
end

function compact = compact_scheme(scheme)
compact = rmfield(scheme,{'cfg','waveforms','tx_ref','raw'});
end

function plot_scheme_channels(run,scheme,sequence,snr_db)
ideal = qammod((0:15).',16,'UnitAveragePower',true);
for channel = 1:numel(scheme.streams)
    value = scheme.streams(channel);
    name = sprintf('%03d_SNR%gdB_%s_Channel%d_星座图.png', ...
        sequence,snr_db,scheme.name,channel);
    metrics = struct('BER',value.pre_fec_ber,'EVM',100*value.evm_rms, ...
        'MER',value.mer_db);
    Test_Project_Plot_Constellation(msiq.output_path(run,name), ...
        {value.constellation_symbols},ideal,metrics, ...
        struct('Title',sprintf('%s Channel%d',scheme.name,channel)));
end
end

function value = normalize_branch_power(value)
power_value = mean(sum(abs(value).^2,2));
value = value/sqrt(power_value+eps);
end

function [value, applied_ppm] = apply_sro(value, ppm)
applied_ppm = ppm;
if abs(ppm) == 0
    return;
end
scale = 1 + ppm*1e-6;
output_count = floor((size(value,1)-1)*scale)+1;
source_axis = 1 + (0:output_count-1).'/scale;
source = (1:size(value,1)).';
resampled = zeros(output_count,size(value,2));
for channel = 1:size(value,2)
    resampled(:,channel) = interp1(source,value(:,channel),source_axis, ...
        'pchip',0);
end
value = resampled;
end

function value = add_real_awgn(value, snr_db, seed)
stream = RandStream('mt19937ar','Seed',double(seed));
signal_power = mean(sum(value.^2,2));
noise_power = signal_power/10^(snr_db/10);
noise = sqrt(noise_power/size(value,2))*randn(stream,size(value));
value = value + noise;
end

function value = clip_real(value, level)
if isfinite(level)
    value = min(max(value,-level),level);
end
end

function value = normalize_average_power(value)
value = value(:);
value = value/sqrt(mean(abs(value).^2)+eps);
end

function value = impairments(opts)
value = struct('cfo_hz',opts.cfo_hz,'sro_ppm',opts.sro_ppm, ...
    'time_axis_skew_samples',opts.time_axis_skew_samples, ...
    'common_iq_matrix',opts.common_iq_matrix, ...
    'noise_definition','total_two_branch_signal_power_over_total_noise_power');
end

function output = validate_only(opts)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
opts.results_root = temporary;
opts.matched_snr_db = 22;
opts.snr_points_db = [18 22];
opts.prepend_samples = 0;
opts.sro_ppm = 0;
opts.time_axis_skew_samples = 0;
before = msiq.instruments.reset_audit(); %#ok<NASGU>
matched = run_matched(opts);
sweep = run_sweep(opts);
analysis = run_analysis(matched, sweep, opts);
audit = msiq.instruments.get_audit();
assert_zero_instrument_io(audit);
assert(matched.iqmimo.pass && matched.traditional.pass);
assert(numel(matched.traditional.streams) == 2);
assert(matched.fairness.iqmimo_total_gross_rate_bps == ...
    matched.fairness.traditional_total_gross_rate_bps);
expected_unique_rate = 2*msiq.fec.build(matched.iqmimo.cfg).info_length / ...
    matched.fairness.iqmimo_physical_duration_s;
assert(abs(matched.fairness.iqmimo_unique_net_information_rate_bps - ...
    expected_unique_rate) <= 1e-6*expected_unique_rate);
assert(abs(matched.fairness.traditional_unique_net_information_rate_bps - ...
    expected_unique_rate) <= 1e-6*expected_unique_rate);
assert(abs(matched.iqmimo.aggregate.net_information_rate_bps - ...
    expected_unique_rate) <= 1e-6*expected_unique_rate);
assert(abs(matched.traditional.aggregate.net_information_rate_bps - ...
    expected_unique_rate) <= 1e-6*expected_unique_rate);
assert(matched.fairness.frame_repetitions > 1);
assert(abs(matched.fairness.duration_difference_s) <= 2/65e9);
assert(isfile(msiq.artifact_path(matched.run_dir,'run_info.json')));
assert(isfile(msiq.artifact_path(matched.run_dir,'summary.csv')));
assert(isfile(msiq.artifact_path(matched.run_dir,'overview.png')));
assert(Result_Check_Flat_Directory(matched.run_dir).IsFlat);
assert(isfile(msiq.artifact_path(sweep.run_dir,'sweep_metrics.csv')));
assert(Result_Check_Flat_Directory(sweep.run_dir).IsFlat);
assert(isfile(msiq.artifact_path(analysis.run_dir,'sources.txt')));
assert(isfile(msiq.artifact_path(analysis.run_dir,'summary.csv')));
assert(isfile(msiq.artifact_path(analysis.run_dir,'overview.png')));
assert(Result_Check_Flat_Directory(analysis.run_dir).IsFlat);
source_lines = strtrim(splitlines(string(fileread( ...
    msiq.artifact_path(analysis.run_dir,'sources.txt')))));
source_lines = source_lines(source_lines ~= "");
assert(numel(source_lines) == 2);
assert(all(contains(source_lines, "EQ_RATE_")));
assert(isfolder(fullfile(opts.results_root, 'simulation')));
assert(isfolder(fullfile(opts.results_root, 'analysis')));
output = struct('pass',true,'matched',matched,'sweep',sweep, ...
    'analysis',analysis, ...
    'instrument_io_delta',audit);
clear cleanup;
end

function finalize_failure(run, exception)
if isempty(run.OutputDir), return; end
try
    Result_Log_Stage(run,'ERROR','failure','%s: %s', ...
        exception.identifier,exception.message);
    Result_Finalize_Run(run,'failed','processing_failed',[], ...
        sprintf('%s: %s',exception.identifier,exception.message));
catch
end
end

function assert_flat(run)
if ~Result_Check_Flat_Directory(run).IsFlat
    error('msiq:equalrate:NonFlatResult','Result directory must be flat.');
end
end

function assert_zero_instrument_io(audit)
if any(struct2array(audit) ~= 0)
    error('msiq:equalrate:InstrumentAccess', ...
        'Offline comparison attempted instrument I/O.');
end
end

function validate_options(opts)
validateattributes(opts.seed,{'numeric'},{'scalar','integer','nonnegative'});
validateattributes(opts.matched_snr_db,{'numeric'},{'scalar','finite'});
validateattributes(opts.snr_points_db,{'numeric'},{'vector','real','finite'});
validateattributes(opts.cfo_hz,{'numeric'},{'scalar','finite'});
validateattributes(opts.sro_ppm,{'numeric'},{'scalar','finite'});
validateattributes(opts.common_iq_matrix,{'numeric'},{'size',[2 2],'finite'});
end

function write_json(path, value)
Result_Atomic_Write_Json(path, value);
end

function out = merge_struct(first, second)
out = first;
names = fieldnames(second);
for index = 1:numel(names)
    out.(names{index}) = second.(names{index});
end
end

function value = ternary(condition, if_true, if_false)
if condition
    value = if_true;
else
    value = if_false;
end
end

function value = remove_if_present(value, name)
if isstruct(value) && isfield(value, name)
    value = rmfield(value, name);
end
end

function remove_temp(path)
if isfolder(path) && startsWith(path,tempdir)
    if msiq.validation_artifacts('defer',path), return; end
    rmdir(path,'s');
end
end
