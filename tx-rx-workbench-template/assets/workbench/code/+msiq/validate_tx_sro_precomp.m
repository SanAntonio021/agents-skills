function note = validate_tx_sro_precomp(outdir)
%VALIDATE_TX_SRO_PRECOMP Offline waveform, loop-boundary and receiver checks.
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.frame_repetitions = 4;
seed = 26072701;
[baseline, base_ref] = msiq.generate_waveforms(cfg, seed);
calibration = struct('enabled', false, 'measured_sro_ppm', 2.55661838632904, ...
    'calibrated_at', '2026-09-06', 'calibration_source', 'offline_unit_test');
cfg.waveform.tx_sro_precomp = calibration;
[disabled, disabled_ref] = msiq.generate_waveforms(cfg, seed);
assert(isequal(baseline.awg_dac_data, disabled.awg_dac_data));
assert(strcmp(base_ref.config_hash_sha256, disabled_ref.config_hash_sha256));
calibration.enabled = true;
calibration.measured_sro_ppm = 0;
cfg.waveform.tx_sro_precomp = calibration;
[zero, zero_ref] = msiq.generate_waveforms(cfg, seed);
assert(isequal(baseline.master_dac_data, zero.master_dac_data));
assert(isequal(baseline.awg_dac_data, zero.awg_dac_data));
assert(~zero_ref.tx_sro_precomp.applied);

% Analytic signal tests isolate fractional timing from the SRO estimator.
w = cfg.waveform;
w.tx_sro_precomp.measured_sro_ppm = 200;
n = (0:10000).';
tone = [cos(2*pi*0.027*n), sin(2*pi*0.027*n)];
[shifted, info] = msiq.dsp.precompensate_tx_sro(tone, w);
q = (0:size(shifted,1)-1).' / info.time_scale;
expected = [cos(2*pi*0.027*q), sin(2*pi*0.027*q)];
assert(max(abs(shifted(20:end-20,:)-expected(20:end-20,:)), [], 'all') < 1e-5);
assert(info.output_samples == ceil(size(tone,1)*info.time_scale));
bad = w; bad.tx_sro_precomp.calibration_source = '';
expect_error(@() msiq.dsp.precompensate_tx_sro(tone,bad), 'msiq:txSro:Metadata');
bad = w; bad.frame_repetitions = 1;
expect_error(@() msiq.dsp.precompensate_tx_sro(tone,bad), 'msiq:txSro:Scope');
bad = w; bad.architecture = 'dual_iq_mimo';
expect_error(@() msiq.dsp.precompensate_tx_sro(tone,bad), 'msiq:txSro:Scope');
bad = w; bad.modulation_order = 64;
expect_error(@() msiq.dsp.precompensate_tx_sro(tone,bad), 'msiq:txSro:Scope');

values = [0 2.55661838632904 -2.55661838632904 200 -200];
rows = repmat(struct('measured_ppm',0,'residual_ppm',0,'mer_db',0, ...
    'rx_applied',false,'fec_pass',false,'padding_samples',0), numel(values),1);
if nargin < 1
    if msiq.validation_artifacts('active')
        outdir = msiq.validation_artifacts('directory');
    else
        outdir = fullfile(cfg.project_root, 'results', 'analysis', ...
            ['TX_SRO_OFFLINE_', char(datetime('now','Format','yyyyMMdd_HHmmss'))]);
    end
end
if ~isfolder(outdir), mkdir(outdir); end
for k = 1:numel(values)
    ppm = values(k);
    cfg.waveform.tx_sro_precomp.measured_sro_ppm = ppm;
    [wave, ref] = msiq.generate_waveforms(cfg, seed);
    assert(wave.master_sample_rate_hz == baseline.master_sample_rate_hz);
    assert(wave.awg_sample_rate_hz == baseline.awg_sample_rate_hz);
    assert(ref.frame.symbol_rate_hz == base_ref.frame.symbol_rate_hz);
    assert(isequal(ref.pairs, base_ref.pairs));
    if ppm ~= 0
        assert(~strcmp(ref.config_hash_sha256, base_ref.config_hash_sha256));
        axis_value = (0:size(wave.master_dac_data,1)-1).' / wave.tx_sro_precomp.time_scale;
        valid = (64:min(floor(axis_value(end))-64,size(baseline.master_dac_data,1)-65)).';
        restored = interp1(axis_value,wave.master_dac_data,valid,'spline');
        original = baseline.master_dac_data(valid+1,:);
        % Compare the transmitted band. Finite-span RRC images at the master
        % rate are removed by the normal AWG decimation filter in both paths.
        restored = resample(restored,1,cfg.waveform.decimation);
        original = resample(original,1,cfg.waveform.decimation);
        interpolation_evm = norm(restored-original,'fro')/norm(original,'fro');
        assert(interpolation_evm < 1e-4, 'TX interpolation exceeds the numerical error budget.');
        fprintf('TX interpolation round-trip EVM %.6g\n',interpolation_evm);
    end
    prepared = msiq.instruments.prepare_awg_download( ...
        wave.awg_dac_data, [3 4], [1 2]);
    assert(all(mod(prepared.final_sample_counts,128) == 0));
    assert(all(prepared.final_sample_counts == ref.frame.awg_padded_waveform_length));
    % Simulate the actual downloaded samples including 8-bit DAC quantization,
    % padding and two whole playback periods. RX keeps the nominal reference.
    samples = [prepared.channel_data{:}];
    samples = double(int8(round(127*samples)))/127;
    transmitted = wave;
    % Reconstruct the DAC output before the independent clock-rate error;
    % low-rate pchip alone would introduce an extra interpolation impairment.
    reconstructed = resample(samples, cfg.waveform.decimation, 1);
    transmitted.master_dac_data = [reconstructed reconstructed];
    transmitted.master_sample_rate_hz = wave.master_sample_rate_hz;
    raw = msiq.simulate_capture(transmitted, cfg, 'A', struct( ...
        'snr_db',25,'cfo_hz',0,'sro_ppm',ppm,'channel_matrix',eye(2), ...
        'image_matrix',zeros(2),'prepend_samples',117, ...
        'capture_repetitions',2,'rng_seed',902));
    decoded = msiq.decode_capture(raw, ref, cfg);
    sync = decoded.synchronization;
    assert(decoded.pass, 'Compensated waveform failed FEC.');
    assert(~sync.sro_low_rate_resample_applied);
    assert(abs(sync.sro_ppm) <= sync.sro_apply_threshold_ppm, ...
        'Residual SRO lies outside its dynamic uncertainty bound.');
    assert(~sync.sro_raw_correction.applied, 'Matched precompensation was corrected again.');
    rows(k) = struct('measured_ppm',ppm,'residual_ppm',sync.sro_ppm, ...
        'mer_db',decoded.primary_streams(1).mer_db, ...
        'rx_applied',sync.sro_raw_correction.applied, ...
        'fec_pass',logical(decoded.pass), ...
        'padding_samples',wave.tx_sro_precomp.loop_guard_samples + ...
        prepared.final_sample_counts(1)-size(wave.awg_dac_data,1));
    fprintf('TX precomp %+g ppm: residual %+.6f, MER %.4f, RX correction %d\n', ...
        ppm, rows(k).residual_ppm, rows(k).mer_db, rows(k).rx_applied);
end
summary = struct2table(rows);
fid = Result_Open_File_Retry(fullfile(outdir,'offline_summary.csv'), 'w','n','UTF-8');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', strjoin(summary.Properties.VariableNames, ','));
fprintf(fid, '%.12g,%.12g,%.12g,%d,%d,%d\n', table2array(summary).');
clear cleanup;
assert(all(summary.mer_db >= summary.mer_db(1)-0.5), ...
    'Waveform precompensation materially changed the quantized clean-link MER.');

% The existing I/Q calibration is applied after the common time mapping.
cfg.waveform.q_relative_delay_samples = 3;
[skewed, ~] = msiq.generate_waveforms(cfg, seed);
cfg.waveform.q_relative_delay_samples = 0;
[unskewed, ~] = msiq.generate_waveforms(cfg, seed);
assert(isequal(skewed.awg_dac_data(:,1), unskewed.awg_dac_data(:,1)));
assert(isequal(skewed.awg_dac_data(4:end,2), unskewed.awg_dac_data(1:end-3,2)));

% The public TX preview accepts the calibration without touching hardware.
calibration.measured_sro_ppm = 2.55661838632904;
opts = struct('cfg_override',cfg,'route','pair_b_ch3_ch4', ...
    'tx_sro_precomp',calibration,'frame_repetitions',4, ...
    'master_sample_rate_hz',64.99e9,'seed',seed);
plan = TX_Workbench('preview_plan', [], opts);
assert(plan.hardware_sro_injection_ppm == 0);
assert(plan.awg_raster_hz == plan.nominal_awg_raster_hz);
assert(plan.tx_ref.tx_sro_precomp.enabled);
assert(plan.tx_ref.tx_sro_precomp.applied);
assert(plan.memory_capacity.ok);
% A changed hardware clock leaves a residual for the unchanged RX algorithm.
wave = plan.waveforms;
samples = [plan.download.channel_data{:}];
samples = resample(double(int8(round(127*samples)))/127,4,1);
wave.master_dac_data = [samples samples];
raw = msiq.simulate_capture(wave,plan.cfg,'B',struct( ...
    'snr_db',25,'sro_ppm',20,'channel_matrix',eye(2),'image_matrix',zeros(2), ...
    'capture_repetitions',2,'rng_seed',902));
decoded = msiq.decode_capture(raw,plan.tx_ref,plan.cfg);
assert(decoded.pass && decoded.synchronization.sro_raw_correction.applied);
assert(~decoded.synchronization.sro_low_rate_resample_applied);
no_sro = plan.cfg; no_sro.receiver.max_abs_sro_ppm = 0;
uncorrected = msiq.decode_capture(raw,plan.tx_ref,no_sro);
assert(decoded.primary_streams(1).mer_db >= uncorrected.primary_streams(1).mer_db);
note = sprintf('bypass, signs, I/Q delay, aligned cyclic playback, FEC and TX preview; %s',outdir);
end

function expect_error(action, identifier)
try
    action();
catch exception
    assert(strcmp(exception.identifier, identifier), exception.message);
    return;
end
error('msiq:txSro:MissingError', 'Expected rejection: %s.', identifier);
end
