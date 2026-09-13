function report = run_v2_validation(selection)
%RUN_V2_VALIDATION Hardware-free acceptance for isolated multistream V2.

if nargin < 1 || isempty(selection), selection = 'all'; end
selection = validatestring(char(string(selection)), ...
    {'all','if_workbench','int_playback','int_controls','short_frame','single_frame','tx_controls','tx_gui', ...
    'rx_gui','rx_plots','plot_export','awg_memory','pair_b','rdiv_compare','storage', ...
    'tx_sro','rx_storage','acquisition'});
root = fileparts(mfilename('fullpath'));
addpath(fullfile(root, 'code'));
addpath(fullfile(root, 'code', 'result_management'));
addpath(fullfile(root, 'code', 'plotting'));
report_cleanup = msiq.validation_report('begin',root,selection); %#ok<NASGU>
set(0, 'DefaultFigureVisible', 'off');
if strcmp(selection, 'tx_sro')
    entries = [run_case('tx_waveform_sro_precompensation', @msiq.validate_tx_sro_precomp), ...
        run_case('wz_raw_input_sro_two_pass_correction', @test_wz_raw_input_sro_two_pass_correction), ...
        run_case('mock_traditional_pair_b_extended_memory', @test_mock_traditional_pair_b_extended_memory)];
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if any(report.Status == "FAIL")
        error('msiq:validation:Failed', 'TX SRO precompensation validation failed.');
    end
    return;
end
if strcmp(selection, 'rx_gui')
    entry = run_case('mock_rx_workbench_interaction_and_layout', @msiq.validate_rx_workbench);
    report = struct2table(entry);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if entry.Status == "FAIL"
        error('msiq:validation:Failed', 'RX GUI validation failed.');
    end
    return;
end
if strcmp(selection, 'plot_export')
    entries = [run_case('plot_export_geometry', @msiq.validate_plot_export_geometry), ...
        run_case('traditional_tx_rx_process_dashboards_and_bundle', @test_traditional_dashboard_rendering)];
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if any(report.Status == "FAIL")
        error('msiq:validation:Failed', 'Plot export validation failed.');
    end
    return;
end
if strcmp(selection, 'rx_plots')
    entries = [run_case('rx_eleven_panel_data_and_layout', @msiq.validate_rx_dashboard), ...
        run_case('traditional_tx_rx_process_dashboards_and_bundle', @test_traditional_dashboard_rendering)];
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if any(report.Status == "FAIL")
        error('msiq:validation:Failed', 'RX dashboard validation failed.');
    end
    return;
end
if strcmp(selection,'if_workbench')
    entries = [run_case('if_state_machine',@msiq.validate_if_workbench), ...
        run_case('if_board',@() if_validation_note(@msiq.validate_if_board)), ...
        run_case('if_pre_fec',@() if_validation_note(@msiq.validate_if_pre_fec)), ...
        run_case('if_ui',@() if_validation_note(@msiq.validate_if_ui)), ...
        run_case('if_capture',@() if_validation_note(@msiq.validate_if_capture)), ...
        run_case('if_replay',@() if_validation_note(@msiq.validate_if_replay)), ...
        run_case('if_boundaries',@() if_validation_note(@msiq.validate_if_boundaries))];
    entries(end+1)=run_case('if_fresh_handshake',@() if_validation_note(@msiq.validate_if_fresh));
    entries(end+1)=run_case('if_awg_contract',@() if_validation_note(@msiq.validate_if_awg));
    entries(end+1)=run_case('if_api_inventory',@() if_validation_note(@msiq.validate_if_compatibility));
    report=struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:,{'Name','Status','Seconds','Note'}));
    assert(~any(report.Status=="FAIL"),'IF validation failed.');
    return;
end
if strcmp(selection, 'int_controls')
    report = struct2table(run_case('int_mock_controls', @() test_short_frame_dependency(@test_int_playback_controls)));
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    assert(~any(report.Status == "FAIL"), 'INT controls validation failed.');
    return;
elseif strcmp(selection, 'int_playback')
    entries = [run_case('int_mock_controls', @() test_short_frame_dependency(@test_int_playback_controls)), ...
        run_case('int_reference_replay', @() test_short_frame_dependency(@msiq.validate_short_frame)), ...
        run_case('legacy_ext_div2', @test_mock_traditional_div2), ...
        run_case('legacy_ext_pair_b', @test_mock_traditional_pair_b_extended_memory), ...
        run_case('legacy_plan_guards', @test_mock_traditional_plan_guards)];
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    assert(~any(report.Status == "FAIL"), 'INT playback validation failed.');
    return;
end
if strcmp(selection, 'short_frame')
    entries = run_case('short_frame_software', @() test_short_frame_dependency(@msiq.validate_short_frame));
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    assert(~any(report.Status == "FAIL"), 'Short-frame validation failed.');
    return;
end
if strcmp(selection, 'acquisition')
    cfg = msiq.build_config('v2_default');
    entries = [run_case('smoke_capture_counts', @() test_mock_single_dac_smoke(cfg)), ...
        run_case('hardware_capture_counts', @() test_mock_success_and_replay(cfg)), ...
        run_case('connection_failure_counts', @() test_mock_failure(cfg,'connect_scope')), ...
        run_case('capture_failure_counts', @() test_mock_failure(cfg,'capture')), ...
        run_case('dsp_failure_counts', @() test_mock_failure(cfg,'dsp'))];
    report = struct2table(entries);
    msiq.validation_report('set',report);
    assert(~any(report.Status == "FAIL"), 'Acquisition validation failed.');
    return;
end
if strcmp(selection, 'rx_storage')
    entries = run_case('mock_traditional_scope_capture', @test_mock_traditional_scope_capture);
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if any(report.Status == "FAIL")
        error('msiq:validation:Failed', 'RX storage validation failed.');
    end
    return;
end
if strcmp(selection, 'tx_controls')
    entries = run_case('mock_traditional_tx_selected_channel_controls', ...
        @test_mock_traditional_tx_controls);
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if any(report.Status == "FAIL")
        error('msiq:validation:Failed', 'TX control validation failed.');
    end
    return;
end
if strcmp(selection, 'single_frame')
    entries = [run_case('single_frame_cyclic_capture', @test_single_frame_cyclic_capture), ...
        run_case('wz_segment_padding_sro_guard', @test_wz_segment_padding_sro_guard), ...
        run_case('wz_segment_boundary_absent_sro_guard', @test_wz_segment_boundary_absent_sro_guard), ...
        run_case('wz_sro_full_window_tail_peak', @test_wz_sro_full_window_tail_peak), ...
        run_case('wz_sro_reliability_and_application_gates', @test_wz_sro_reliability_and_application_gates), ...
        run_case('mock_traditional_tx_selected_channel_controls', @test_mock_traditional_tx_controls), ...
        run_case('mock_traditional_div2_memory_topology', @test_mock_traditional_div2), ...
        run_case('mock_traditional_raw_scope_cleanup_and_time_window', @test_mock_traditional_scope_capture), ...
        run_case('mock_traditional_rdiv_comparison', @test_mock_traditional_rdiv_comparison), ...
        run_case('traditional_tx_rx_process_dashboards_and_bundle', @test_traditional_dashboard_rendering), ...
        run_case('wz_traditional_simulation_and_dashboard', @test_wz_traditional_simulation), ...
        run_case('mock_tx_workbench_interaction_and_layout', @test_mock_tx_workbench_gui)];
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if any(report.Status == "FAIL")
        error('msiq:validation:Failed', 'Single-frame validation failed.');
    end
    return;
end
if strcmp(selection, 'storage')
    entries = [run_case('output_storage_and_replot',@msiq.validate_output_storage), ...
        run_case('compact_artifact_compatibility', @test_compact_artifacts), ...
        run_case('mock_traditional_tx_selected_channel_controls', @test_mock_traditional_tx_controls), ...
        run_case('mock_traditional_plan_guards', @test_mock_traditional_plan_guards), ...
        run_case('mock_traditional_scope_capture', @test_mock_traditional_scope_capture), ...
        run_case('mock_traditional_rdiv_comparison', @test_mock_traditional_rdiv_comparison)];
    report = struct2table(entries);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if any(report.Status == "FAIL")
        error('msiq:validation:Failed', 'Storage compatibility validation failed.');
    end
    return;
end
if strcmp(selection, 'tx_gui')
    entry = run_case('mock_tx_workbench_interaction_and_layout', ...
        @() test_mock_tx_workbench_gui());
    report = struct2table(entry);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if entry.Status == "FAIL"
        error('msiq:validation:Failed', 'TX GUI validation failed.');
    end
    return;
end
if strcmp(selection, 'awg_memory')
    entry = run_case('m8195a_awg_memory_capacity_preflight', ...
        @() test_awg_memory_capacity_preflight());
    report = struct2table(entry);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if entry.Status == "FAIL"
        error('msiq:validation:Failed', ...
            'AWG memory capacity validation failed.');
    end
    return;
end
if strcmp(selection, 'pair_b')
    entry = run_case('mock_traditional_pair_b_extended_memory', ...
        @() test_mock_traditional_pair_b_extended_memory());
    report = struct2table(entry);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if entry.Status == "FAIL"
        error('msiq:validation:Failed', ...
            'PAIR B extended-memory validation failed.');
    end
    return;
end
if strcmp(selection, 'rdiv_compare')
    entry = run_case('mock_traditional_rdiv_comparison', ...
        @() test_mock_traditional_rdiv_comparison());
    report = struct2table(entry);
    msiq.validation_report('set',report);
    disp(report(:, {'Name','Status','Seconds','Note'}));
    if entry.Status == "FAIL"
        error('msiq:validation:Failed', ...
            'Traditional RDIV comparison validation failed.');
    end
    return;
end
cfg = msiq.build_config('v2_default');
entries = repmat(empty_entry(), 0, 1);
entries(end+1)=run_case('if_state_machine',@msiq.validate_if_workbench);
entries(end+1)=run_case('if_board',@() if_validation_note(@msiq.validate_if_board));
entries(end+1)=run_case('if_pre_fec',@() if_validation_note(@msiq.validate_if_pre_fec));
entries(end+1)=run_case('if_ui',@() if_validation_note(@msiq.validate_if_ui));
entries(end+1)=run_case('if_capture',@() if_validation_note(@msiq.validate_if_capture));
entries(end+1)=run_case('if_replay',@() if_validation_note(@msiq.validate_if_replay));
entries(end+1)=run_case('if_boundaries',@() if_validation_note(@msiq.validate_if_boundaries));
entries(end+1)=run_case('if_fresh_handshake',@() if_validation_note(@msiq.validate_if_fresh));
entries(end+1)=run_case('if_awg_contract',@() if_validation_note(@msiq.validate_if_awg));
entries(end+1)=run_case('if_api_inventory',@() if_validation_note(@msiq.validate_if_compatibility));

entries(end+1) = run_case('int_mock_controls', @() test_short_frame_dependency(@test_int_playback_controls));
entries(end+1) = run_case('short_frame_software', @() test_short_frame_dependency(@msiq.validate_short_frame));
entries(end+1) = run_case('config_and_matrix', @() test_matrix(cfg));
entries(end+1) = run_case('single_frame_cyclic_capture', @test_single_frame_cyclic_capture);
entries(end+1) = run_case('compact_artifact_compatibility', @test_compact_artifacts);
entries(end+1) = run_case('plot_export_geometry', @msiq.validate_plot_export_geometry);
entries(end+1) = run_case('output_storage_and_replot',@msiq.validate_output_storage);

try
    tic_value = tic;
    [dual_waveforms, dual_ref] = msiq.generate_waveforms(cfg, ...
        cfg.experiment.seed_values(1));
    test_waveform_preflight(cfg, dual_waveforms, dual_ref);
    entries(end+1) = pass_entry('waveform_and_memory_preflight', toc(tic_value));
catch exception
    entries(end+1) = fail_entry('waveform_and_memory_preflight', exception);
    dual_waveforms = [];
    dual_ref = [];
end

entries(end+1) = run_case('fec_noiseless_and_incomplete_tail', ...
    @() test_fec(cfg));
if ~isempty(dual_waveforms)
    entries(end+1) = run_case('dual_identity_2x2_and_4x4', ...
        @() test_dual_identity(cfg, dual_waveforms, dual_ref));
    entries(end+1) = run_case('cfo_sro_skew_image_awgn_cross_window', ...
        @() test_impairments(cfg, dual_waveforms, dual_ref));
    entries(end+1) = run_case('payload_reference_independence', ...
        @() test_reference_independence(cfg, dual_waveforms, dual_ref));
end
entries(end+1) = run_case('single_stream_wl_fse', ...
    @() test_single_stream(cfg));
entries(end+1) = run_case('tx_waveform_sro_precompensation', @msiq.validate_tx_sro_precomp);
entries(end+1) = run_case('scope_wavedesc_rate_quantization_resample', ...
    @() test_scope_rate_quantization_resample());
entries(end+1) = run_case('wz_segment_padding_sro_guard', ...
    @() test_wz_segment_padding_sro_guard());
entries(end+1) = run_case('wz_segment_boundary_absent_sro_guard', ...
    @() test_wz_segment_boundary_absent_sro_guard());
entries(end+1) = run_case('wz_sro_full_window_tail_peak', ...
    @() test_wz_sro_full_window_tail_peak());
entries(end+1) = run_case('wz_sro_reliability_and_application_gates', ...
    @() test_wz_sro_reliability_and_application_gates());
entries(end+1) = run_case('wz_raw_input_sro_two_pass_correction', ...
    @() test_wz_raw_input_sro_two_pass_correction());
entries(end+1) = run_case('wz_sro_experimental_confidence_policies', ...
    @() test_wz_sro_experimental_confidence_policies());
entries(end+1) = run_case('wz_sro_distortion_stress_guards', ...
    @() test_wz_sro_distortion_stress_guards());
entries(end+1) = run_case('wz_sro_interval_scan_guards', ...
    @() test_wz_sro_interval_scan_guards());
entries(end+1) = run_case('default_hardware_gate_before_io', ...
    @() test_default_gate(cfg));
entries(end+1) = run_case('query_only_idn_without_ivi_or_writes', ...
    @() test_query_only_preflight(cfg));
entries(end+1) = run_case('dry_run_zero_instrument_io', ...
    @() test_dry_run(cfg));
entries(end+1) = run_case('simulation_zero_instrument_io_and_artifacts', ...
    @() test_simulation(cfg));
entries(end+1) = run_case('wz_traditional_simulation_and_dashboard', ...
    @() test_wz_traditional_simulation());
entries(end+1) = run_case('equal_rate_traditional_vs_iqmimo_offline', ...
    @() test_equal_rate_comparison());
entries(end+1) = run_case('v212_v213_dry_run_zero_instrument_io', ...
    @() test_staged_dry_runs(cfg));
entries(end+1) = run_case('mock_awg_off_readback_without_source', ...
    @() test_mock_awg_off(cfg));
entries(end+1) = run_case('mock_single_dac_two_stage_sequence', ...
    @() test_mock_single_dac_smoke(cfg));
entries(end+1) = run_case('m8195a_awg_memory_capacity_preflight', ...
    @() test_awg_memory_capacity_preflight());
entries(end+1) = run_case('mock_traditional_tx_selected_channel_controls', ...
    @() test_mock_traditional_tx_controls());
entries(end+1) = run_case('mock_traditional_sdel_channel_settings', ...
    @() test_mock_traditional_sdel_settings());
entries(end+1) = run_case('traditional_variable_rate_modulation_loopback', ...
    @() test_traditional_variable_rate_loopback());
entries(end+1) = run_case('mock_tx_workbench_interaction_and_layout', ...
    @() test_mock_tx_workbench_gui());
entries(end+1) = run_case('mock_rx_workbench_interaction_and_layout', ...
    @msiq.validate_rx_workbench);
entries(end+1) = run_case('mock_traditional_pair_b_extended_memory', ...
    @() test_mock_traditional_pair_b_extended_memory());
entries(end+1) = run_case('mock_traditional_div2_memory_topology', ...
    @() test_mock_traditional_div2());
entries(end+1) = run_case('mock_traditional_plan_drift_and_public_confirmation', ...
    @() test_mock_traditional_plan_guards());
entries(end+1) = run_case('mock_traditional_other_channel_restore_policy', ...
    @() test_mock_traditional_other_channel_policy());
entries(end+1) = run_case('mock_traditional_raw_scope_cleanup_and_time_window', ...
    @() test_mock_traditional_scope_capture());
entries(end+1) = run_case('mock_traditional_rdiv_comparison', ...
    @() test_mock_traditional_rdiv_comparison());
entries(end+1) = run_case('traditional_tx_rx_process_dashboards_and_bundle', ...
    @() test_traditional_dashboard_rendering());
entries(end+1) = run_case('rx_eleven_panel_data_and_layout', ...
    @msiq.validate_rx_dashboard);
entries(end+1) = run_case('mock_smoke_download_failure_shutdown', ...
    @() test_mock_smoke_failure(cfg, 'download'));
entries(end+1) = run_case('mock_smoke_capture_failure_shutdown', ...
    @() test_mock_smoke_failure(cfg, 'capture'));
entries(end+1) = run_case('mock_smoke_readback_failure_shutdown', ...
    @() test_mock_smoke_failure(cfg, 'readback'));
entries(end+1) = run_case('mock_hardware_success_and_replay_immutable', ...
    @() test_mock_success_and_replay(cfg));
entries(end+1) = run_case('mock_connection_failure_shutdown', ...
    @() test_mock_failure(cfg, 'connect_scope'));
entries(end+1) = run_case('mock_acquisition_failure_shutdown', ...
    @() test_mock_failure(cfg, 'capture'));
entries(end+1) = run_case('mock_dsp_failure_shutdown', ...
    @() test_mock_failure(cfg, 'dsp'));
entries(end+1) = run_case('v1_1km_golden_bler_parity', ...
    @() test_v1_golden());

report = struct2table(entries);
msiq.validation_report('set',report);
fprintf('\nV2 validation: PASS=%d FAIL=%d\n', ...
    nnz(report.Status == "PASS"), nnz(report.Status == "FAIL"));
disp(report(:, {'Name','Status','Seconds','Note'}));
if any(report.Status == "FAIL")
    error('msiq:validation:Failed', ...
        '%d V2 validation cases failed.', nnz(report.Status == "FAIL"));
end
end

function note = test_compact_artifacts()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
plan = struct('waveforms', struct('awg_dac_data', [1 2;3 4], ...
    'plot_data', struct('samples', [NaN 2])), 'route', struct('name','test'), ...
    'desired', struct('raster_hz',65e9), 'cfg', struct('seed',42));
msiq.save_tx_manifest(temporary, plan, struct('status','planned'));
saved = msiq.load_tx_waveform(temporary);
assert(isequaln(saved.waveforms, plan.waveforms));
msiq.save_tx_manifest(temporary, plan, struct('status','applied'), struct('status','staged'));
manifest_path = msiq.artifact_path(temporary, 'tx_manifest.mat');
manifest = load(manifest_path);
assert(strcmp(manifest.receipt.status, 'applied'));
assert(strcmp(manifest.staged_receipt.status, 'staged'));
assert(isempty(dir(fullfile(temporary,'diagnostics','*.tmp'))));

legacy = saved;
legacy.cfg.seed = 7;
save(fullfile(temporary, 'tx_waveform.mat'), '-struct', 'legacy');
loaded = msiq.load_tx_waveform(temporary);
assert(loaded.cfg.seed == 7);
delete(fullfile(temporary, 'tx_waveform.mat'));
movefile(manifest_path, fullfile(temporary, 'tx_manifest.mat'));
loaded = msiq.load_tx_waveform(temporary);
assert(loaded.cfg.seed == 42);
delete(fullfile(temporary, 'tx_manifest.mat'));
save(fullfile(temporary, 'awg_plan.mat'), 'plan');
loaded = msiq.load_tx_waveform(temporary);
assert(isequaln(loaded.waveforms, plan.waveforms));

validation = struct('ok',true,'samples',[1 NaN 3]);
save(fullfile(temporary, 'demod_result.mat'), 'validation');
loaded = msiq.load_capture_validation(temporary);
assert(isequaln(loaded.validation, validation));
validation.samples = [4 5 6];
save(msiq.artifact_path(temporary,'capture_preparation.mat','write'),'validation');
loaded = msiq.load_capture_validation(temporary);
assert(isequaln(loaded.validation, validation));
delete(msiq.artifact_path(temporary,'capture_preparation.mat'));
output = struct('status','decoded');
save(fullfile(temporary,'demod_result.mat'),'output');
failed = false;
try
    msiq.load_capture_validation(temporary);
catch exception
    failed = strcmp(exception.identifier,'msiq:captureArtifact:Invalid');
end
assert(failed);
note = 'legacy and compact TX/RX artifacts, precedence and missing validation checked without I/O';
clear cleanup;
end

function note = test_matrix(cfg)
matrix = msiq.build_experiment_matrix(cfg);
assert(matrix.counts.indoor_formal == 12);
assert(matrix.counts.one_km_single == 6);
assert(matrix.counts.one_km_multichannel == 16);
assert(matrix.counts.formal_total == 34);
assert(matrix.counts.qualification == 18);
expected = {'CH1CH2','CH3CH4','CH5CH6','CH1CH3CH5', ...
    'CH2CH4CH6','CH1CH2CH3CH4','CH1CH2CH5CH6','CH3CH4CH5CH6'};
multi = matrix.conditions([matrix.conditions.num_active] > 1);
actual = unique(cellfun(@(x) strjoin(x,''), ...
    {multi.active_physical_subbands}, 'UniformOutput', false), 'stable');
assert(all(ismember(expected, actual)));
for k = 1:numel(multi)
    assert(numel(multi(k).receive_batches) == ceil(multi(k).num_active/2));
    if multi(k).num_active > 2
        assert(multi(k).duplicate_payload_loading);
        assert(multi(k).unique_payload_pair_count == 2);
    end
end
note = '34 formal conditions; balanced slots and receive batches verified';
end

function test_waveform_preflight(cfg, waveforms, reference)
assert(size(waveforms.awg_dac_data,2) == 4);
assert(waveforms.awg_sample_rate_hz == 16.25e9);
assert(size(waveforms.master_dac_data,1) > cfg.awg.diagnostic_max_samples);
assert(all(waveforms.clipping_fraction == 0));
assert(numel(reference.reference_hash_sha256) == 64);
formal = msiq.preflight_waveform(waveforms, cfg, 'M8195A_4ch');
assert(formal.ok);
diagnostic = waveforms;
diagnostic.awg_dac_data = waveforms.master_dac_data;
diagnostic.awg_sample_rate_hz = waveforms.master_sample_rate_hz;
rejected = msiq.preflight_waveform(diagnostic, cfg, 'M8195A_4ch_256k');
assert(~rejected.ok && strcmp(rejected.reason, ...
    'diagnostic_256k_memory_exceeded'));
end

function note = test_fec(cfg)
[~, reference] = msiq.fec.encode_payload(cfg, 77, 1);
llr = 20*(1-2*reference.coded_bits);
decoded = msiq.fec.decode_soft(llr, reference, cfg);
assert(decoded.block_count == 1 && decoded.block_error_count == 0);
assert(decoded.bler == 0 && decoded.parity_converged);
assert(decoded.post_fec_ber == 0 && all(decoded.final_parity_checks(:) == 0));
tail = msiq.fec.decode_soft([llr; ones(123,1)], reference, cfg);
assert(tail.block_count == 1 && tail.incomplete_tail_bits == 123);
bad = msiq.fec.decode_soft(-llr, reference, cfg);
assert(bad.block_error_count == 1 && bad.bler == 1);
note = 'real DVB-S2 soft decode, BLER/parity, and 123-bit tail verified';
end

function note = test_dual_identity(cfg, waveforms, reference)
raw = struct('samples',waveforms.master_dac_data(:,1:2), ...
    'sample_rate_hz',waveforms.master_sample_rate_hz,'payload_pair','A');
decoded = msiq.decode_capture(raw, reference, cfg);
assert(decoded.pass && numel(decoded.primary_streams) == 2);
assert(decoded.primary_equalizer.output_dimension == 2);
assert(decoded.diagnostic_equalizer.full_output_dimension == 4);
assert(decoded.diagnostic_equalizer.reported_output_dimension == 2);
assert(all([decoded.primary_streams.post_fec_ber] == 0));
assert(all([decoded.primary_streams.bler] == 0));
note = 'two independent streams pass; fixed 2x2/4x4 dimensions verified';
end

function note = test_impairments(cfg, waveforms, reference)
options = struct('snr_db',28,'cfo_hz',2e5,'sro_ppm',40, ...
    'channel_skew_samples',0.35,'time_axis_skew_samples',0.2, ...
    'image_matrix',[0.02 0.01;0.01 0.02], ...
    'prepend_samples',777,'channel_matrix',[1 0.08;0.06 0.95]);
raw = msiq.simulate_capture(waveforms,cfg,'A',options);
decoded = msiq.decode_capture(raw,reference,cfg);
assert(decoded.pass);
assert(abs(decoded.synchronization.coarse_cfo_hz-options.cfo_hz) < 500);
assert(abs(decoded.synchronization.sro_ppm-options.sro_ppm) < 1);
assert(decoded.preparation.alignment.applied);
assert(all([decoded.primary_streams.post_fec_ber] == 0));
note = sprintf('CFO %.0f Hz and SRO %.2f ppm recovered with zero post-FEC BER', ...
    decoded.synchronization.coarse_cfo_hz,decoded.synchronization.sro_ppm);
end

function note = test_reference_independence(cfg, waveforms, reference)
raw = msiq.simulate_capture(waveforms,cfg,'A', ...
    struct('snr_db',35,'channel_matrix',[1 .1;.07 .93]));
first = msiq.decode_capture(raw,reference,cfg);
mutated = reference;
for stream = 1:2
    mutated.pairs(1).metrics_only(stream).fec.info_bits = ...
        1-mutated.pairs(1).metrics_only(stream).fec.info_bits;
    mutated.pairs(1).metrics_only(stream).fec.coded_bits = ...
        1-mutated.pairs(1).metrics_only(stream).fec.coded_bits;
end
second = msiq.decode_capture(raw,mutated,cfg);
assert(norm(first.primary_equalizer.channel_matrix - ...
    second.primary_equalizer.channel_matrix,'fro') == 0);
assert(norm(first.primary_equalizer.equalizer_matrix - ...
    second.primary_equalizer.equalizer_matrix,'fro') == 0);
assert(~first.payload_reference_used_for_processing && ...
    ~second.payload_reference_used_for_processing);
for stream = 1:2
    assert(isequal(first.primary_streams(stream).fec.decoded_bits, ...
        second.primary_streams(stream).fec.decoded_bits));
end
note = 'mutating payload truth changes metrics only, not equalizer or decoded bits';
end

function note = test_single_stream(cfg)
single_cfg = cfg;
single_cfg.waveform.architecture = 'single_complex_stream';
[waveforms, reference] = msiq.generate_waveforms(single_cfg, ...
    cfg.experiment.seed_values(2));
raw = msiq.simulate_capture(waveforms,single_cfg,'A', ...
    struct('snr_db',35,'channel_matrix',eye(2), ...
    'image_matrix',[.03 0;0 .02]));
decoded = msiq.decode_capture(raw,reference,single_cfg);
assert(decoded.pass && numel(decoded.primary_streams) == 1);
assert(strcmp(decoded.primary_equalizer.name,'wl_fse'));
assert(decoded.primary_equalizer.output_dimension == 1);
assert(decoded.primary_equalizer.training_only);
assert(~decoded.primary_equalizer.payload_reference_used);
note = 'single complex stream uses standalone training-only WL-FSE';
end

function note = test_scope_rate_quantization_resample()
cfg = msiq.build_config('v2_traditional_wz');
source_rate = 3.9999999465942726e10;
count = 4096;
axis_value = (0:count-1).';
raw = struct('samples', [sin(2*pi*axis_value/97), cos(2*pi*axis_value/89)], ...
    'sample_rate_hz', source_rate);
[~, preparation] = msiq.dsp.prepare_capture(raw, cfg);
assert(preparation.resample_p == 13 && preparation.resample_q == 124);
note = 'single-precision 25 ps WAVEDESC interval resolves to the 13/124 resample ratio';
end

function note = test_wz_segment_padding_sro_guard()
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.frame_repetitions = 3;
[waveforms, reference] = msiq.generate_waveforms(cfg, ...
    cfg.experiment.seed_values(1));
segment = resample(complex(waveforms.master_dac_data(:,1), ...
    waveforms.master_dac_data(:,2)), 2, 31);
captured = [segment; zeros(10,1); segment; zeros(10,1); segment];
[~, synchronization] = msiq.dsp.synchronize_single_wz( ...
    captured, reference, cfg);
assert(~synchronization.sro_applied && ...
    abs(synchronization.sro_ppm) <= synchronization.sro_apply_threshold_ppm);
assert(strcmp(synchronization.sro_reason, 'estimate_within_fit_uncertainty'));
assert(synchronization.sro_boundary_classified && ...
    ~synchronization.sro_boundary_absent);
assert(isequal(synchronization.boundary_interval_indices, ...
    synchronization.sro_boundary_interval_indices));
note = 'logical-frame timing remains unchanged across padded AWG segment boundaries';
end

function note = test_wz_segment_boundary_absent_sro_guard()
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.frame_repetitions = 3;
[waveforms, reference] = msiq.generate_waveforms(cfg, ...
    cfg.experiment.seed_values(1));
segment = resample(complex(waveforms.master_dac_data(:,1), ...
    waveforms.master_dac_data(:,2)), 2, 31);
injected_ppm = 200;
captured = [segment; segment; segment];
scale = 1+injected_ppm*1e-6;
count = floor((numel(captured)-1)*scale)+1;
stretched = interp1(1:numel(captured), captured, ...
    1+(0:count-1).'/scale, 'pchip');
[~, synchronization] = msiq.dsp.synchronize_single_wz( ...
    stretched, reference, cfg);
assert(synchronization.sro_boundary_absent && ...
    ~synchronization.sro_boundary_classified);
assert(synchronization.sro_applied && synchronization.sro_reliable);
assert(strcmp(synchronization.sro_reason, 'recommended_conservative_ci'));
assert(abs(synchronization.sro_ppm-injected_ppm) < 30);
note = sprintf('no-padding three-segment control classified boundary_absent and applied %.2f ppm', ...
    synchronization.sro_ppm);
end

function note = test_wz_sro_full_window_tail_peak()
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.frame_repetitions = 3;
[waveforms, reference] = msiq.generate_waveforms(cfg, ...
    cfg.experiment.seed_values(1));
segment = resample(complex(waveforms.master_dac_data(:,1), ...
    waveforms.master_dac_data(:,2)), 2, 31);
sync_symbols = numel(reference.frame.sync_symbols)*reference.frame.sync_repeats;
tail_samples = 2*(reference.frame.sync_start-1+sync_symbols+8);
assert(tail_samples < reference.frame.symbol_count*2);
captured = [segment; zeros(10,1); segment; zeros(10,1); ...
    segment; zeros(10,1); segment(1:tail_samples)];
[frame_samples, synchronization] = msiq.dsp.synchronize_single_wz( ...
    captured, reference, cfg);
assert(~isempty(frame_samples));
assert(numel(synchronization.sro_peak_samples) > ...
    numel(synchronization.sro_complete_peak_samples));
assert(numel(synchronization.sro_fit_peak_samples) == ...
    numel(synchronization.sro_peak_samples));
assert(max(synchronization.sro_peak_samples) > ...
    numel(captured)-tail_samples);
assert(~synchronization.sro_applied);
note = sprintf('full-window SRO fit retained %d tail-only reliable peak(s)', ...
    numel(synchronization.sro_peak_samples)- ...
    numel(synchronization.sro_complete_peak_samples));
end

function note = test_wz_sro_reliability_and_application_gates()
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.frame_repetitions = 3;
[waveforms, reference] = msiq.generate_waveforms(cfg, ...
    cfg.experiment.seed_values(1));
segment = resample(complex(waveforms.master_dac_data(:,1), ...
    waveforms.master_dac_data(:,2)), 2, 31);

% Three AWG segments expose two expected padding boundaries and six internal
% intervals after boundary removal. The stretch is a software-only control.
captured = [segment; zeros(10,1); segment; zeros(10,1); segment];
injected_ppm = 200;
scale = 1+injected_ppm*1e-6;
count = floor((numel(captured)-1)*scale)+1;
stretched = interp1(1:numel(captured), captured, ...
    1+(0:count-1).'/scale, 'pchip');
[~, synchronization] = msiq.dsp.synchronize_single_wz( ...
    stretched, reference, cfg);
assert(synchronization.sro_applied);
assert(strcmp(synchronization.sro_reason, 'recommended_conservative_ci'));
assert(abs(synchronization.sro_ppm-injected_ppm) < 30);
assert(synchronization.sro_fit_interval_count >= 3);
assert(synchronization.sro_reliable);
assert(synchronization.sro_max_interval_deviation_samples <= 1.25);
assert(~isempty(synchronization.sro_boundary_interval_indices));
required = {'sro_ppm','sro_applied','sro_peak_samples', ...
    'sro_complete_peak_samples','sro_candidate_frame_starts', ...
    'sro_fit_peak_samples','sro_adjusted_fit_peak_samples', ...
    'boundary_interval_indices','sro_boundary_absent','sro_sigma_ppm', ...
    'sro_fit_slope_samples','sro_fit_slope_sigma_samples', ...
    'candidate_frame_starts','complete_frames','frame_start_sample', ...
    'sro_reason','sro_fit_residual_samples','sro_apply_threshold_ppm'};
assert(all(isfield(synchronization, required)));
note = sprintf('+%g ppm software control estimated %.2f ppm and applied robust SRO', ...
    injected_ppm, synchronization.sro_ppm);
end

function note = test_wz_raw_input_sro_two_pass_correction()
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.frame_repetitions = 3; % Preserve this historical multi-frame fixture.
[waveforms, reference] = msiq.generate_waveforms(cfg, ...
    cfg.experiment.seed_values(1));
base_options = struct('snr_db',42,'cfo_hz',0,'channel_matrix',eye(2), ...
    'image_matrix',zeros(2),'capture_repetitions',3, ...
    'segment_padding_samples',0,'rng_seed',260824);

injected_ppm = 200;
damaged = msiq.simulate_capture(waveforms, cfg, 'A', ...
    merge_options(base_options, struct('sro_ppm', injected_ppm)));
decoded = msiq.decode_capture(damaged, reference, cfg);
sync = decoded.synchronization;
correction = sync.sro_raw_correction;
assert(decoded.pass);
assert(correction.applied && strcmp(correction.stage, 'raw_input'));
assert(correction.output_samples ~= correction.input_samples);
assert(abs(sync.sro_ppm-injected_ppm) < 30);
assert(strcmp(sync.sro_correction_mode, 'raw_input_two_pass'));
assert(~sync.sro_low_rate_resample_applied);
assert(strcmp(sync.sro_final_pass.sro_correction_mode, 'disabled'));
assert(~sync.sro_final_pass.sro_low_rate_resample_applied);
assert(decoded.preparation.raw_sro_correction.applied);

zero = msiq.simulate_capture(waveforms, cfg, 'A', ...
    merge_options(base_options, struct('sro_ppm', 0)));
zero_decoded = msiq.decode_capture(zero, reference, cfg);
zero_correction = zero_decoded.synchronization.sro_raw_correction;
assert(zero_decoded.pass);
assert(~zero_correction.applied && ...
    zero_correction.input_samples == zero_correction.output_samples);
assert(strcmp(zero_decoded.synchronization.sro_final_pass.sro_correction_mode, ...
    'disabled'));

single = msiq.simulate_capture(waveforms, cfg, 'A', ...
    merge_options(base_options, struct('sro_ppm', injected_ppm, ...
    'capture_repetitions', 1)));
single_decoded = msiq.decode_capture(single, reference, cfg);
single_correction = single_decoded.synchronization.sro_raw_correction;
assert(~single_correction.applied && ...
    single_correction.input_samples == single_correction.output_samples);
assert(~single_decoded.synchronization.sro_reliable);

[probe_corrected, probe_info] = msiq.dsp.correct_raw_sro(damaged, ...
    injected_ppm);
assert(probe_info.time_axes_rebuilt);
original_offsets = damaged.time_axes(1,:) - damaged.time_axes(1,1);
corrected_offsets = probe_corrected.time_axes(1,:) - ...
    probe_corrected.time_axes(1,1);
assert(max(abs(original_offsets-corrected_offsets)) < 1e-18);
note = sprintf('two-pass raw-I/Q correction applied %.2f ppm once; zero and single-window controls held', ...
    sync.sro_ppm);
end

function note = test_wz_sro_experimental_confidence_policies()
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.frame_repetitions = 3; % Preserve this historical multi-frame fixture.
assert(strcmp(cfg.receiver.sro_decision_policy,'conservative_ci'));
assert(cfg.receiver.sro_observation_oversample_factor == 8);
[waveforms, reference] = msiq.generate_waveforms(cfg, ...
    cfg.experiment.seed_values(1));
base_options = struct('snr_db',38,'cfo_hz',0,'channel_matrix',eye(2), ...
    'image_matrix',zeros(2),'capture_repetitions',4, ...
    'segment_padding_samples',0,'rng_seed',260904);

injected_ppm = 10;
damaged = msiq.simulate_capture(waveforms, cfg, 'A', ...
    merge_options(base_options, struct('sro_ppm',injected_ppm)));
conservative = msiq.decode_capture(damaged, reference, cfg);
assert(strcmp(conservative.synchronization.sro_decision_policy, ...
    'conservative_ci'));
assert(conservative.synchronization.sro_observation_oversample_factor == 8);

legacy_cfg = cfg;
legacy_cfg.receiver.sro_decision_policy = 'legacy';
legacy_cfg.receiver.sro_observation_oversample_factor = 1;
legacy = msiq.decode_capture(damaged, reference, legacy_cfg);
assert(strcmp(legacy.synchronization.sro_decision_policy,'legacy'));
assert(legacy.synchronization.sro_observation_oversample_factor == 1);
assert(~legacy.synchronization.sro_applied);

weighted_cfg = cfg;
weighted_cfg.receiver.sro_decision_policy = 'confidence_weighted';
weighted = msiq.decode_capture(damaged, reference, weighted_cfg);
for decoded = {conservative,weighted}
    item = decoded{1};
    sync = item.synchronization;
    assert(item.pass && sync.sro_applied);
    assert(strcmp(sync.sro_correction_stage,'raw_input'));
    assert(~sync.sro_low_rate_resample_applied);
    assert(strcmp(sync.sro_final_pass.sro_correction_mode,'disabled'));
    assert(abs(sync.sro_ppm-injected_ppm) < 0.5);
    assert(sync.sro_sigma_ppm < 1);
    assert(sync.sro_observation_oversample_factor == 8);
    assert(item.primary_streams(1).mer_db >= ...
        legacy.primary_streams(1).mer_db);
end
assert(conservative.synchronization.sro_correction_weight == 1);
assert(weighted.synchronization.sro_correction_weight > 0 && ...
    weighted.synchronization.sro_correction_weight <= 1);
assert(abs(weighted.synchronization.sro_correction_ppm) <= ...
    abs(weighted.synchronization.sro_ppm));

zero = msiq.simulate_capture(waveforms, cfg, 'A', ...
    merge_options(base_options, struct('sro_ppm',0,'rng_seed',260905)));
for policy = {'conservative_ci','confidence_weighted'}
    trial_cfg = cfg;
    trial_cfg.receiver.sro_decision_policy = policy{1};
    trial_cfg.receiver.sro_observation_oversample_factor = 8;
    [baseband, ~] = msiq.dsp.prepare_capture(zero, trial_cfg);
    [~, sync] = msiq.dsp.synchronize_single_wz( ...
        baseband, reference, trial_cfg, false, 'observe');
    assert(~sync.sro_recommended && sync.sro_correction_weight == 0);
    stress = msiq.run_wz_sro_distortion_stress(struct( ...
        'source','synthetic','write_results',false,'families',{{'varying'}}, ...
        'profile_ppm_pairs',[100 300], ...
        'sro_decision_policy',policy{1}, ...
        'sro_observation_oversample_factor',8));
    assert(stress.ok && stress.guard.varying_sro_applied == 0 && ...
        stress.guard.varying_sro_changed == 0);
end

% An AWG padding boundary stretches with the waveform clock. Verify that the
% experimental estimator scales the known padding before fitting peak drift.
segment = resample(complex(waveforms.master_dac_data(:,1), ...
    waveforms.master_dac_data(:,2)), 2, 31);
captured = [segment; zeros(10,1); segment; zeros(10,1); segment];
boundary_ppm = 25;
boundary_scale = 1+boundary_ppm*1e-6;
count = floor((numel(captured)-1)*boundary_scale)+1;
stretched = interp1(1:numel(captured), captured, ...
    1+(0:count-1).'/boundary_scale, 'pchip');
    boundary_cfg = cfg;
[~, boundary_sync] = msiq.dsp.synchronize_single_wz( ...
    stretched, reference, boundary_cfg, false, 'observe');
assert(boundary_sync.sro_boundary_classified && ...
    boundary_sync.sro_reliable && boundary_sync.sro_recommended);
assert(abs(boundary_sync.sro_boundary_scale-boundary_scale) < 2e-5);
assert(abs(boundary_sync.sro_measured_boundary_extra_samples- ...
    boundary_sync.sro_boundary_extra_samples* ...
    boundary_sync.sro_boundary_scale) < 1e-9);
note = sprintf(['8x timing observation resolved +10 ppm; conservative and ', ...
    'weighted policies corrected raw I/Q once, true zero was held, and ', ...
    'AWG padding followed the measured clock scale']);
end

function note = test_wz_sro_distortion_stress_guards()
% A compact Cartesian matrix checks the same invariants as the full replay.
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
stress = msiq.run_wz_sro_distortion_stress(struct( ...
    'source','synthetic','write_results',true,'results_root',temporary, ...
    'snr_values_db',[38 35],'echo_amplitudes',[0.03 0.10], ...
    'echo_delays_symbols',[1 4], ...
    'profile_ppm_pairs',[150 250;100 300]));
assert(stress.offline_only && stress.ok);
assert(~stress.guard.applied_unreliable);
assert(~stress.guard.applied_and_degraded);
assert(~stress.guard.low_rate_double_correction);
assert(~stress.guard.shared_injection_failures);
assert(~stress.guard.varying_sro_applied);
assert(~stress.guard.varying_sro_changed);
assert(~stress.guard.varying_sro_missing_reason);
families = {stress.rows.family};
assert(all(ismember({'clean','noise','echo','varying'},families)));
assert(numel(stress.scenarios) == 9 && numel(stress.rows) == 9);
assert(sum(strcmp(families,'clean')) == 1);
assert(sum(strcmp(families,'noise')) == 2);
assert(sum(strcmp(families,'echo')) == 4);
assert(sum(strcmp(families,'varying')) == 2);

echo_cases = stress.scenarios(strcmp({stress.scenarios.family},'echo'));
actual_echo = sortrows([[echo_cases.echo_amplitude].', ...
    [echo_cases.echo_delay_symbols].']);
expected_echo = sortrows([0.03 1;0.03 4;0.10 1;0.10 4]);
assert(max(abs(actual_echo(:)-expected_echo(:))) < 1e-12);

noise_rows = stress.rows(strcmp(families,'noise'));
assert(numel(unique([noise_rows.noise_seed])) == 1);
varying_cases = stress.scenarios(strcmp({stress.scenarios.family},'varying'));
varying_means = ([varying_cases.profile_start_ppm] + ...
    [varying_cases.profile_end_ppm])/2;
assert(all(abs(varying_means-200) < 1e-12));

expected_labels = strcat('synthetic_three_frame_', ...
    {stress.scenarios.label});
assert(isequal({stress.rows.label},expected_labels));
low_rate = false(numel(stress.rows),1);
for k = 1:numel(stress.rows)
    low_rate(k) = stress.rows(k).mode_c.sro_low_rate_resample_applied;
    assert(stress.rows(k).shared_injection_verified);
    if strcmp(stress.rows(k).family,'varying')
        assert(~stress.rows(k).mode_c.sro_applied);
        assert(abs(stress.rows(k).delta_c_vs_b_db) <= 1e-9);
        assert(~isempty(stress.rows(k).mode_c.sro_reason));
    end
end
assert(all(~low_rate));

simple_path = msiq.artifact_path(stress.run_dir, ...
    'summary_synthetic_three_frame.csv');
simple_lines = readlines(simple_path);
simple_lines = simple_lines(strlength(simple_lines) > 0);
assert(numel(simple_lines) == 10);
assert(simple_lines(1) == ...
    "信号条件,B MER (dB),C MER (dB),C是否补偿,D MER (dB)");
assert(summary_data_rows(fullfile(stress.run_dir,'summary.csv')) == 9);
header = string(summary_header(msiq.artifact_path(stress.run_dir,'observations.csv')));
assert(contains(header,'C_max_interval_deviation_samples'));
assert(contains(header,'shared_injection_verified'));
flat = Result_Check_Flat_Directory(stress.run_dir);
assert(flat.IsFlat && isfile(fullfile(stress.run_dir,'overview.png')));
note = sprintf(['synthetic Cartesian guards and one %d-row simple table ', ...
    'passed with shared B/C/D injection'],numel(stress.rows));
clear cleanup;
end

function note = test_wz_sro_interval_scan_guards()
% Bounded synthetic scan smoke; the full real-capture scan is separate.
scan = msiq.run_wz_sro_interval_scan(struct( ...
    'source','synthetic','write_results',false, ...
    'candidates_samples',[0.75 1.25], ...
    'snr_values_db',[38 35],'echo_amplitudes',0.03, ...
    'echo_delays_symbols',2, ...
    'profile_ppm_pairs',[150 250;100 300]));
assert(scan.offline_only && scan.ok);
assert(numel(scan.rows) == 12);
assert(all([scan.summary.applied_unreliable] == 0));
assert(all([scan.summary.applied_and_degraded] == 0));
assert(all([scan.summary.varying_sro_accepted] == 0));
assert(all([scan.summary.processing_failures] == 0));
first = scan.rows([scan.rows.limit_samples] == 0.75);
second = scan.rows([scan.rows.limit_samples] == 1.25);
assert(numel(first) == 6 && numel(second) == 6);
assert(isequal({first.label},{second.label}));
assert(isequaln([first.noise_seed],[second.noise_seed]));
noise = first(strcmp({first.family},'noise'));
assert(numel(noise) == 2 && numel(unique([noise.noise_seed])) == 1);
note = sprintf('synthetic consistency-limit scan passed (%d candidates, %d cases)', ...
    numel(scan.candidates_samples), numel(scan.rows));
end

function value = merge_options(base, override)
value = base;
names = fieldnames(override);
for k = 1:numel(names)
    value.(names{k}) = override.(names{k});
end
end

function note = test_default_gate(cfg)
matrix = msiq.build_experiment_matrix(cfg);
before = msiq.instruments.reset_audit(); %#ok<NASGU>
failed = false(1,3);
modes = {'hardware','awg_off_check','single_dac_smoke'};
conditions = {matrix.conditions(1),matrix.conditions(1), ...
    first_dual_condition(matrix)};
for k = 1:numel(modes)
    try
        msiq.run_condition(cfg,conditions{k},modes{k});
    catch exception
        failed(k) = strcmp(exception.identifier,'msiq:safety:HardwareDisabled');
    end
end
assert(all(failed));
audit = msiq.instruments.get_audit();
assert(all(struct2array(audit) == 0));
note = 'formal, V212, and V213 gates stop before run creation and instrument I/O';
end

function note = test_dry_run(cfg)
cfg.results.output_level = 'full';
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
test_cfg = cfg;
test_cfg.results_root = temporary;
test_cfg.waveform.frame_repetitions = 1;
matrix = msiq.build_experiment_matrix(test_cfg);
condition = matrix.conditions(1);
condition.up = 30;
condition.symbol_rate_hz = ...
    test_cfg.waveform.master_sample_rate_hz/condition.up;
msiq.instruments.reset_audit();
outcome = msiq.run_condition(test_cfg,condition,'dry_run');
audit = msiq.instruments.get_audit();
assert(all(struct2array(audit) == 0));
assert(isfile(msiq.artifact_path(outcome.run_dir,'run_info.json')));
assert(isfile(fullfile(outcome.run_dir,'summary.csv')));
assert(isfile(fullfile(outcome.run_dir,'overview.png')));
saved = load(msiq.artifact_path(outcome.run_dir,'tx_reference.mat'),'tx_ref');
assert(saved.tx_ref.frame.master_samples_per_symbol == 30);
assert(strcmp(saved.tx_ref.architecture,'single_complex_stream'));
assert(contains(saved.tx_ref.waveform_id,'UP30'));
flat = Result_Check_Flat_Directory(outcome.run_dir);
assert(flat.IsFlat);
note = ['single-stream UP30 applied; flat artifacts created with zero ', ...
    'connection/query/write/capture'];
clear cleanup;
end

function note = test_simulation(cfg)
cfg.results.output_level = 'full';
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
test_cfg = cfg;
test_cfg.results_root = temporary;
matrix = msiq.build_experiment_matrix(test_cfg);
condition = first_dual_condition(matrix);
test_cfg.results.retention_mode = 'full';
msiq.instruments.reset_audit();
outcome = msiq.run_condition(test_cfg, condition, 'simulation');
audit = msiq.instruments.get_audit();
assert(all(struct2array(audit) == 0));
assert(strcmp(outcome.status, 'completed') && outcome.pass);
    required = {'run_info.json','summary.csv','overview.png', ...
        'metrics_overview.png','constellation.png','raw_capture.mat', ...
        'tx_reference.mat','decoded_result.mat','simulation_options.json'};
assert(all(cellfun(@(name) isfile(msiq.artifact_path(outcome.run_dir, name)), required)));
    info = jsondecode(fileread(msiq.artifact_path(outcome.run_dir,'run_info.json')));
    info_text = fileread(msiq.artifact_path(outcome.run_dir,'run_info.json'));
    assert(strcmp(info.run_kind, 'simulation'));
    assert(strcmp(info.execution_mode, 'simulation') && isempty(info.instruments));
    assert(contains(info_text, '"planned_run_kind": null'));
    assert(~any(contains(string({info.artifacts.file}), '.baiduyun.')));
assert(summary_data_rows(fullfile(outcome.run_dir, 'summary.csv')) == 2);
saved = load(msiq.artifact_path(outcome.run_dir,'decoded_result.mat'), 'decoded');
assert(saved.decoded.pass && ...
    all([saved.decoded.primary_streams.post_fec_ber] == 0));
    assert(all([saved.decoded.primary_streams.bler] == 0));
    assert(all(arrayfun(@(value) ~isempty(value.constellation_symbols), ...
        saved.decoded.primary_streams)));
    assert(~isempty(saved.decoded.preparation.baseband_preview));
    assert(~isempty(saved.decoded.preparation.baseband_preview_indices));
    assert(~isempty(saved.decoded.synchronization.sync_metric_trace));
    assert_nonblank_dashboard(fullfile(outcome.run_dir,'overview.png'));
    flat = Result_Check_Flat_Directory(outcome.run_dir);
    assert(flat.IsFlat);
    note = ['persistent dual-stream simulation created an eight-panel RX ', ...
        'dashboard, metrics, and constellation with zero instrument I/O'];
clear cleanup;
end


function note = test_short_frame_dependency(callback)
% Skip only a missing licensed local fixture; all other failures remain failures.
try
    cfg = msiq.short_frame_config();
    msiq.fec.short_parity_check(cfg);
catch exception
    if strcmp(exception.identifier,'msiq:fec:ShortMatrixMissing')
        error('validation:skip','Short-frame prerequisite unavailable: %s',exception.message);
    end
    rethrow(exception);
end
note = callback();
end

function note = test_int_playback_controls()
root = msiq.project_root();
run = Result_Create_Run(struct('ProjectRoot',root,'RunType','checks', ...
    'NameParts',{{'int_mock_controls'}},'ExecutionMode','simulation', ...
    'OutputCategory','checks','Counts',struct('planned',6), ...
    'EntryPoint','run_v2_validation(''int_playback'')'));
cfg = msiq.short_frame_config();
cfg = attach_mock_instruments(cfg,[]);
assert(cfg.instrument.awg.mock && cfg.instrument.scope.mock && cfg.instrument.signal_generator.mock);
opts = struct('cfg_override',cfg,'symbol_rate_hz',65e9/15, ...
    'rate_authority','symbol_rate','rdiv','DIV4','memory_mode','INT', ...
    'run_dir',run.OutputDir,'artifact_prefix','int');
Result_Summary_Initialize(run,{'case','pass'},{'-','-'});
try
    for pair = 1:2
        routes = {'pair_a_ch1_ch2','pair_b_ch3_ch4'};
        opts.route = routes{pair};
        msiq.instruments.reset_audit();
        opts.memory_mode = 'EXT';
        ext = msiq.traditional_tx('preview_plan',[],opts);
        opts.memory_mode = 'INT';
        preview = msiq.traditional_tx('preview_plan',[],opts);
        assert(preview.padded_sample_count == 224768 && preview.waveform_sample_count == 224370);
        assert(preview.waveform_sample_rate_hz == 65e9);
        assert(isequaln(preview.waveforms.master_dac_data,ext.waveforms.master_dac_data));
        assert(isequal(preview.tx_ref.pairs,ext.tx_ref.pairs));
        assert(abs(preview.actual_waveform_duration_s-ext.actual_waveform_duration_s)<1e-15);
        assert(all(struct2array(msiq.instruments.get_audit()) == 0));
        for mode = {'EXT','INT','EXT'}
            opts.memory_mode = mode{1};
            opts.artifact_prefix = sprintf('p%d_%s_%d',pair,mode{1}, ...
                numel(msiq.instruments.get_command_history()));
            plan = msiq.traditional_tx('awg_plan',[],opts);
            receipt = apply_traditional_plan(plan);
            assert(strcmp(receipt.status,'staged') && ~any(receipt.final_state.outputs));
            assert(receipt.memory_capacity.ok);
            channels = plan.route.awg_channels;
            assert(all([receipt.final_state.traces(channels).length] == plan.padded_sample_count));
            if strcmp(mode{1},'INT')
                assert(isequal({receipt.final_state.traces.memory_mode},repmat({'INT'},1,4)));
                assert(receipt.final_state.raster_hz == 65e9);
            end
        end
        commands = audit_commands();
        assert(~any(contains(commands,' ON')));
        other = setdiff(1:4,channels);
        for ch = other
            assert(~any(contains(commands,sprintf(':TRACe%d:DEFine',ch),'IgnoreCase',true)));
        end
        audit = msiq.instruments.get_audit();
        assert(audit.scope_connections == 0 && audit.source_connections == 0);
        assert(audit.driver_initializations == 0);
        save(fullfile(run.DataDir,sprintf('pair_%d.mat',pair)),'preview','ext','receipt','commands','audit');
        record_int_check(run,sprintf('pair_%d_transition',pair));
    end
    opts.memory_mode = 'INT'; opts.route = 'pair_a_ch1_ch2';
    for failure = {'download','readback'}
        msiq.instruments.reset_audit();
        opts.artifact_prefix = ['failure_' failure{1}];
        plan = msiq.traditional_tx('awg_plan',[],opts);
        if strcmp(failure{1},'download')
            plan.cfg.instrument.awg.fail_stage = 'download';
            identifier = 'msiq:traditionalTx:MockDownloadFailure';
        else
            plan.cfg.instrument.awg.mock_fail_readback_after_binary_writes = 2;
            identifier = 'msiq:instrument:MockReadbackFailure';
        end
        expect_int_error(@() apply_traditional_plan(plan),identifier);
        saved = jsondecode(fileread(msiq.artifact_path(plan,'execution_failure.json')));
        assert(saved.shutdown_verified == strcmp(failure{1},'download'));
        assert(~any(contains(audit_commands(),' ON')));
        record_int_check(run,['failure_' failure{1}]);
    end
    msiq.instruments.reset_audit();
    set_mock_outputs(cfg,4,true);
    before = msiq.instruments.get_audit();
    expect_int_error(@() msiq.traditional_tx('awg_plan',[],opts), ...
        'msiq:traditionalTx:MemorySwitchOutputsOn');
    after = msiq.instruments.get_audit(); assert(after.writes == before.writes);
    assert(msiq.instruments.io_audit('get_awg_output',4));
    msiq.instruments.reset_audit();
    opts.artifact_prefix = 'drift';
    plan = msiq.traditional_tx('awg_plan',[],opts);
    set_mock_outputs(cfg,4,true);
    before = msiq.instruments.get_audit();
    expect_int_error(@() apply_traditional_plan(plan),'msiq:traditionalTx:MemorySwitchOutputsOn');
    after = msiq.instruments.get_audit(); assert(after.writes == before.writes);
    set_mock_outputs(cfg,4,false);
    msiq.instruments.set_mock_awg_state(struct('raster_hz',64e9));
    before = msiq.instruments.get_audit();
    expect_int_error(@() apply_traditional_plan(plan),'msiq:traditionalTx:PlanDrift');
    after = msiq.instruments.get_audit(); assert(after.writes == before.writes);
    msiq.instruments.reset_audit();
    opts.artifact_prefix = 'enable';
    plan = msiq.traditional_tx('awg_plan',[],opts);
    enabled = msiq.traditional_tx('awg_apply',[],struct('plan',plan, ...
        'confirmation_phrase',plan.required_confirmation,'enable_output',true));
    assert(isequal(enabled.final_state.outputs,[true true false false]));
    copyfile(msiq.artifact_path(plan,'tx_manifest.mat'), ...
        fullfile(run.DataDir,'tx_manifest.mat'));
    expect_int_error(@() msiq.traditional_tx('awg_reuse',run.OutputDir, ...
        struct('cfg_override',cfg,'memory_mode','EXT')), 'msiq:traditionalTx:ReuseMemoryMode');
    set_mock_outputs(cfg,1:4,false);
    state = msiq.instruments.io_audit('get_mock_awg_state','');
    state.traces(1).memory_mode = 'EXT';
    msiq.instruments.set_mock_awg_state(state);
    expect_int_error(@() msiq.traditional_tx('awg_reuse',run.OutputDir, ...
        struct('cfg_override',cfg,'memory_mode','INT')), 'msiq:traditionalTx:ReuseState');
    record_int_check(run,'off_drift_enable_reuse_guards');
    msiq.instruments.reset_audit();
    bad = opts; bad.cfg_override = attach_mock_instruments(msiq.build_config('v2_traditional_wz'),[]);
    expect_int_error(@() msiq.traditional_tx('awg_plan',[],bad),'msiq:traditionalTx:AwgMemoryCapacity');
    assert(all(struct2array(msiq.instruments.get_audit()) == 0));
    bad = opts; bad.route = 'all_four';
    expect_int_error(@() msiq.traditional_tx('preview_plan',[],bad),'msiq:traditionalTx:IntRoute');
    bad = opts; bad.rdiv = 'DIV1';
    expect_int_error(@() msiq.traditional_tx('preview_plan',[],bad),'msiq:traditionalTx:IntRdiv');
    context = struct('dac_mode','FOUR','rdiv','DIV4', ...
        'channel_memory_modes',{{'INT','INT','INT','INT'}}, ...
        'selected_channels',[1 2],'required_samples_per_channel',[262144 262144]);
    capacity = msiq.instruments.awg_memory_capacity(context); assert(capacity.ok);
    context.required_samples_per_channel = [262656 262656];
    capacity = msiq.instruments.awg_memory_capacity(context); assert(~capacity.ok);
    record_int_check(run,'capacity_and_mode_guards');
    Result_Finalize_Run(run,'completed');
catch exception
    Result_Finalize_Run(run,'completed_with_failures');
    rethrow(exception);
end
note = ['Mock-only pair transitions, capacity, OFF/failure/reuse guards: ' run.OutputDir];
end

function expect_int_error(action, identifier)
try
    action();
catch exception
    assert(strcmp(exception.identifier,identifier),exception.message);
    return;
end
error('msiq:int:MissingError','Expected %s.',identifier);
end

function record_int_check(run, name)
Result_Summary_Append(run,{name,true});
info = Result_Update_Run_Info(run,struct());
Result_Update_Run_Info(run,struct('counts',struct( ...
    'executed',info.counts.executed+1,'succeeded',info.counts.succeeded+1)));
end

function note = test_single_frame_cyclic_capture()
cfg = msiq.build_config('v2_traditional_wz');
assert(cfg.waveform.frame_repetitions == 1);
msiq.instruments.reset_audit();
plan = msiq.traditional_tx('preview_plan', [], struct('cfg_override',cfg));
assert(plan.cfg.waveform.frame_repetitions == 1);
assert(plan.tx_ref.frame.frame_repetitions == 1);
assert(size(plan.waveforms.master_dac_data,1) == ...
    plan.tx_ref.frame.symbol_count*cfg.waveform.master_samples_per_symbol);

% The stored frame stays single; only the simulated capture spans AWG cycles.
[playback,period_samples] = awg_playback_waveforms(plan.waveforms);
assert(mod(period_samples,128) == 0);
assert(period_samples == plan.tx_ref.frame.awg_padded_waveform_length);
values = [0 -100 100];
estimated = zeros(size(values));
for index = 1:numel(values)
    raw = msiq.simulate_capture(playback,plan.cfg,'A',struct( ...
        'snr_db',60,'cfo_hz',0,'sro_ppm',values(index), ...
        'channel_matrix',eye(2),'image_matrix',zeros(2), ...
        'capture_repetitions',6,'segment_padding_samples',0, ...
        'crop_start_samples',round(0.35*period_samples), ...
        'rng_seed',609060+index));
    assert(size(raw.samples,1) > 5*period_samples);
    decoded = msiq.decode_capture(raw,plan.tx_ref,plan.cfg);
    sync = decoded.synchronization;
    estimated(index) = sync.sro_ppm;
    assert(decoded.pass && decoded.sync_ok);
    assert(numel(sync.sro_complete_peak_samples) >= 4);
    assert(abs(estimated(index)-values(index)) < 3);
    assert(~sync.sro_low_rate_resample_applied);
    assert(all([decoded.primary_streams.post_fec_ber] == 0));
    if values(index) == 0
        assert(~sync.sro_raw_correction.applied);
    else
        assert(sync.sro_raw_correction.applied);
    end
    fprintf('Single-frame loop: injected %g ppm, estimated %.6f ppm, peaks %d\n', ...
        values(index),estimated(index),numel(sync.sro_complete_peak_samples));
end
legacy_cfg = cfg;
legacy_cfg.waveform.frame_repetitions = 3;
[legacy, legacy_ref] = msiq.generate_waveforms(legacy_cfg,cfg.experiment.seed_values(1));
assert(legacy_ref.frame.frame_repetitions == 3);
assert(size(legacy.master_dac_data,1) == 3*size(plan.waveforms.master_dac_data,1));
audit = msiq.instruments.get_audit();
assert(all(struct2array(audit) == 0));
note = sprintf(['one stored frame, %d aligned DAC samples, six-cycle capture; ', ...
    '0/-100/+100 ppm estimates %.3f/%.3f/%.3f; legacy 3-frame generation retained'], ...
    period_samples,estimated(1),estimated(2),estimated(3));
end

function [playback,period_samples] = awg_playback_waveforms(waveforms)
prepared = msiq.instruments.prepare_awg_download( ...
    waveforms.awg_dac_data, 1:4, 1:4, 128);
playback = waveforms;
playback.master_dac_data = round(127*[prepared.channel_data{:}])/127;
playback.master_sample_rate_hz = playback.awg_sample_rate_hz;
period_samples = size(playback.master_dac_data,1);
end

function note = test_wz_traditional_simulation()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = msiq.build_config('v2_traditional_wz');
cfg.results_root = temporary;
cfg.results.output_level = 'full';
matrix = msiq.build_experiment_matrix(cfg);
condition = first_scalar_condition(matrix);
msiq.instruments.reset_audit();
outcome = msiq.run_condition(cfg,condition,'simulation');
audit = msiq.instruments.get_audit();
assert(all(struct2array(audit) == 0));
assert(outcome.pass && numel(outcome.streams) == 1);
assert(summary_data_rows(fullfile(outcome.run_dir,'summary.csv')) == 1);
saved = load(msiq.artifact_path(outcome.run_dir,'decoded_result.mat'),'decoded');
decoded = saved.decoded;
assert(strcmp(decoded.architecture,'single_complex_stream'));
assert(strcmp(decoded.primary_equalizer.name,'wz_wl_fse_nlms'));
assert(decoded.preparation.processing_samples_per_symbol == 2);
assert(decoded.preparation.iq_preprocessing.combined_as_complex_pair);
assert(decoded.primary_equalizer.processing_samples_per_symbol == 2);
assert(~decoded.payload_reference_used_for_processing && ...
    ~decoded.primary_equalizer.payload_reference_used);
assert(isfinite(decoded.primary_streams.pre_fec_ber) && ...
    decoded.primary_streams.pre_fec_ber >= 0);
assert(decoded.primary_streams.post_fec_ber == 0 && ...
    decoded.primary_streams.bler == 0 && ...
    decoded.primary_streams.parity_converged);
assert(strcmp(decoded.synchronization.sro_correction_mode, ...
    'raw_input_two_pass'));
assert(~decoded.synchronization.sro_low_rate_resample_applied);
assert_nonblank_dashboard(fullfile(outcome.run_dir,'overview.png'));
flat = Result_Check_Flat_Directory(outcome.run_dir);
assert(flat.IsFlat);
note = ['WZ zero-IF single complex 16QAM used 2-Sa/sym WL-FSE, ', ...
    'passed FEC through raw-input SRO correction with zero instrument I/O'];
clear cleanup;
end

function note = test_query_only_preflight(cfg)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
test_cfg = cfg;
test_cfg.results_root = temporary;
test_cfg = attach_mock_instruments(test_cfg, []);
matrix = msiq.build_experiment_matrix(test_cfg);
msiq.instruments.reset_audit();
outcome = msiq.run_condition( ...
    test_cfg, matrix.conditions(1), 'hardware_query');
audit = msiq.instruments.get_audit();
assert(strcmp(outcome.status,'completed'));
assert(audit.connections == 3 && audit.queries == 3 && audit.closes == 3);
assert(audit.writes == 0 && audit.captures == 0 && ...
    audit.binary_writes == 0 && audit.driver_initializations == 0 && ...
    audit.shutdown_calls == 0);
assert(isfile(msiq.artifact_path(outcome.run_dir,'instrument_idn.json')));
note = 'three IDN queries used query-only VISA; zero IVI init/write/capture';
clear cleanup;
end

function note = test_staged_dry_runs(cfg)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
test_cfg = cfg;
test_cfg.results_root = temporary;
test_cfg.waveform.frame_repetitions = 1;
matrix = msiq.build_experiment_matrix(test_cfg);
condition = first_dual_condition(matrix);
msiq.instruments.reset_audit();
off = msiq.run_condition(test_cfg,condition,'awg_off_check_dry_run');
smoke = msiq.run_condition(test_cfg,condition,'single_dac_smoke_dry_run');
audit = msiq.instruments.get_audit();
assert(all(struct2array(audit) == 0));
assert(isfile(msiq.artifact_path(off.run_dir,'awg_off_plan.json')));
assert(isfile(msiq.artifact_path(smoke.run_dir,'smoke_plan.json')));
assert(isfile(msiq.artifact_path(smoke.run_dir,'smoke_waveform_sources.mat')));
assert(isfile(msiq.artifact_path(smoke.run_dir,'smoke_tx_reference.mat')));
assert(isfile(fullfile(off.run_dir,'overview.png')));
assert(isfile(fullfile(smoke.run_dir,'overview.png')));
plan = jsondecode(fileread(msiq.artifact_path(smoke.run_dir,'smoke_plan.json')));
assert(numel(plan) == 8);
assert(isequal(sort([plan.dac]),[1 1 2 2 3 3 4 4]));
assert(nnz(strcmp({plan.waveform_stage},'tone')) == 4);
assert(nnz(strcmp({plan.waveform_stage},'v2_component')) == 4);
info = jsondecode(fileread(msiq.artifact_path(smoke.run_dir,'run_info.json')));
assert(strcmp(info.execution_mode,'dry_run') && isempty(info.instruments));
flat_off = Result_Check_Flat_Directory(off.run_dir);
flat_smoke = Result_Check_Flat_Directory(smoke.run_dir);
assert(flat_off.IsFlat && flat_smoke.IsFlat);
note = 'V212/V213 plans created eight DAC/stage points with zero instrument I/O';
clear cleanup;
end

function note = test_mock_awg_off(cfg)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
[test_cfg, condition] = bench_test_config(cfg, temporary);
msiq.instruments.reset_audit();
outcome = msiq.run_condition(test_cfg,condition,'awg_off_check');
audit = msiq.instruments.get_audit();
assert(strcmp(outcome.status,'completed'));
assert(~any(outcome.initial_state) && ~any(outcome.off_state));
assert(audit.connections == 2 && audit.awg_connections == 1 && ...
    audit.scope_connections == 1 && audit.source_connections == 0);
assert(audit.source_queries == 0 && audit.source_writes == 0 && ...
    audit.source_closes == 0 && audit.max_awg_outputs_enabled == 0);
assert(audit.awg_output_mask == 0 && audit.shutdown_calls == 1);
assert(summary_data_rows(fullfile(outcome.run_dir,'summary.csv')) == 1);
assert(isfile(msiq.artifact_path(outcome.run_dir,'AWG_OFF_repeat01_attempt01.mat')));
info = jsondecode(fileread(msiq.artifact_path(outcome.run_dir,'run_info.json')));
assert(numel(info.instruments) == 2);
assert(~any(strcmp({info.instruments.role},'signal_generator')));
note = 'V212 used AWG+scope only; initial, forced-OFF, and shutdown readbacks all OFF';
clear cleanup;
end

function note = test_mock_single_dac_smoke(cfg)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
[test_cfg, condition] = bench_test_config(cfg, temporary);
msiq.instruments.reset_audit();
outcome = msiq.run_condition(test_cfg,condition,'single_dac_smoke');
audit = msiq.instruments.get_audit();
assert(strcmp(outcome.status,'completed') && outcome.stage_count == 8);
assert(audit.connections == 2 && audit.source_connections == 0);
assert(audit.source_queries == 0 && audit.source_writes == 0 && ...
    audit.source_closes == 0 && audit.source_binary_writes == 0);
assert(audit.max_awg_outputs_enabled == 1 && ...
    audit.multi_output_events == 0 && audit.awg_output_mask == 0);
assert(audit.binary_writes == 8 && audit.captures == 16);
assert(audit.shutdown_calls == 1 && outcome.shutdown.awg_readback_ok);
info = jsondecode(fileread(msiq.artifact_path(outcome.run_dir,'run_info.json')));
assert(info.counts.executed == audit.captures && info.counts.executed == 16);
assert(info.counts.succeeded == 16 && info.counts.failed == 0);
assert(summary_data_rows(fullfile(outcome.run_dir,'summary.csv')) == 16);
assert(numel(dir(fullfile(outcome.run_dir,'data','OFF_DAC*.mat'))) == 8);
assert(numel(dir(fullfile(outcome.run_dir,'data','ON_DAC*.mat'))) == 8);
assert(isfile(fullfile(outcome.run_dir,'overview.png')));
assert(isfile(fullfile(outcome.run_dir,'spectrum_overview.png')));
assert(isfile(msiq.artifact_path(outcome.run_dir,'awg_state_readback.json')));
header = summary_header(fullfile(outcome.run_dir,'summary.csv'));
assert(~contains(header,'MER') && ~contains(header,'BER'));
for k = 1:numel(outcome.state_records)
    expected = false(1,4);
    expected(outcome.state_records(k).dac) = true;
    assert(isequal(outcome.state_records(k).on,expected));
    assert(~any(outcome.state_records(k).after_download));
    assert(~any(outcome.state_records(k).after_stage));
end

info = jsondecode(fileread(msiq.artifact_path(outcome.run_dir,'run_info.json')));
assert(numel(info.instruments) == 2 && ...
    ~any(strcmp({info.instruments.role},'signal_generator')));
note = ['four DACs x tone/V2 component passed; max one DAC ON; ', ...
    '16 paired captures; zero source access'];
clear cleanup;
end

function note = test_mock_traditional_tx_controls()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();
plan = msiq.traditional_tx('awg_plan', [], struct('cfg_override',cfg));
assert(plan.cfg.waveform.frame_repetitions == 1);
assert(plan.waveform_sample_count == 148297);
assert(plan.padded_sample_count == 148352);
assert(abs(plan.waveform_sample_rate_hz-16.25e9) < 1);
assert(abs(plan.awg_raster_hz-65e9) < 1);
assert(plan.memory_capacity.ok);
assert(isequal(plan.final_sample_counts, ...
    plan.memory_capacity.required_samples_per_channel));
assert(contains(plan.required_confirmation, 'FORCE PUBLIC CHANGE'));
assert(isfield(plan, 'public_parameter_differences'));
assert(plan.public_parameter_changes);
applied = apply_traditional_plan(plan);
assert(isequal(applied.output_mask, [true true false false]));
diagnostics_dir = fullfile(plan.run_dir, 'data');
assert(strcmp(plan.diagnostics_dir, diagnostics_dir));
assert(isfile(fullfile(diagnostics_dir, 'awg_plan.json')));
assert(~isfile(fullfile(diagnostics_dir, 'awg_plan.mat')));
  assert(isfile(fullfile(diagnostics_dir, 'execution_receipt.json')));
  assert(isfile(fullfile(diagnostics_dir, 'tx_reference.mat')));
  assert(~isfile(fullfile(diagnostics_dir, 'tx_waveform.mat')));
  assert(~isfile(fullfile(diagnostics_dir, 'tx_plot_data.mat')));
  saved_waveform = msiq.load_tx_waveform(plan.run_dir);
  assert(isequaln(saved_waveform.waveforms, plan.waveforms));
  assert(isfile(plan.reference_bundle_path));
  assert(isfile(plan.tx_dashboard_path));
  assert_nonblank_dashboard(plan.tx_dashboard_path, 'tx');
  portable = load(plan.reference_bundle_path, 'bundle');
  assert(strcmpi(portable.bundle.execution.status, 'applied'));
  assert(strcmpi(portable.bundle.reference_payload_policy, 'metrics_only'));
  assert(~has_forbidden_bundle_fields(portable.bundle));
  root_entries = dir(plan.run_dir);
  root_files = root_entries(~[root_entries.isdir]);
  assert(numel(root_files) == 1 && strcmp(root_files.name, 'fig_tx_dashboard.png'));
commands = audit_commands();
assert(~any(contains(commands, ':OUTPut3', 'IgnoreCase', true)));
assert(~any(contains(commands, ':OUTPut4', 'IgnoreCase', true)));

command_count = numel(commands);
reused = msiq.traditional_tx('awg_reuse', plan.run_dir, ...
    struct('cfg_override',cfg));
assert(all(reused.output_mask(1:2)));
commands = audit_commands();
reuse_commands = commands(command_count+1:end);
assert(~any(contains(reuse_commands, 'ABOR', 'IgnoreCase', true)));
assert(~any(contains(reuse_commands, ':INIT', 'IgnoreCase', true)));
assert(~any(contains(reuse_commands, ':FUNCtion', 'IgnoreCase', true)));
command_count = numel(audit_commands());
msiq.traditional_tx('awg_level', [], struct('cfg_override',cfg, ...
    'amplitude_vpp', 0.25, 'offset_v', 0));
commands = audit_commands();
level_commands = commands(command_count+1:end);
assert(~any(contains(level_commands, 'ABOR', 'IgnoreCase', true)));
assert(~any(contains(level_commands, ':INIT', 'IgnoreCase', true)));
assert(~any(contains(level_commands, ':FUNCtion', 'IgnoreCase', true)));
assert(~any(contains(level_commands, ':OUTPut3', 'IgnoreCase', true)));
command_count = numel(audit_commands());
stopped = msiq.traditional_tx('awg_stop', [], struct('cfg_override',cfg));
assert(~any(stopped.output_mask(1:2)));
commands = audit_commands();
stop_commands = commands(command_count+1:end);
assert(~any(contains(stop_commands, 'ABOR', 'IgnoreCase', true)));
assert(~any(contains(stop_commands, ':INIT', 'IgnoreCase', true)));
assert(~any(contains(stop_commands, ':FUNCtion', 'IgnoreCase', true)));
assert(~any(contains(stop_commands, ':OUTPut3', 'IgnoreCase', true)));
audit = msiq.instruments.get_audit();
assert(audit.source_connections == 0 && audit.scope_connections == 0);
note = 'selected CH1/CH2 TX controls retained no CH3/CH4 write and no ABOR outside apply';
clear cleanup;
end

function note = test_awg_memory_capacity_preflight()
base = struct('dac_mode', 'FOUR', 'channel_memory_modes', 'IIII', ...
    'selected_channels', [3 4], ...
    'required_samples_per_channel', [593280 593280], ...
    'option_raw', '0');
for divider = [1 2 4]
    context = base;
    context.rdiv = sprintf('DIV%d', divider);
    report = msiq.instruments.awg_memory_capacity(context);
    assert(~report.ok && strcmp(report.reason_code, 'int_capacity_exceeded'));
    assert(isequal(report.available_samples_per_channel, [262144 262144]));
    assert(report.total_required_samples == 1186560);
    assert(report.total_available_samples == 524288);
    assert(contains(report.message, 'DIV1、DIV2和DIV4均不会改变INT容量'));
end

small = base;
small.rdiv = 'DIV4';
small.required_samples_per_channel = [262144 262143];
small_report = msiq.instruments.awg_memory_capacity(small);
assert(small_report.ok);

for counts = {[593280 593280], [1779584 1779584]}
    extended = base;
    extended.channel_memory_modes = 'EEEE';
    extended.rdiv = 'DIV4';
    extended.required_samples_per_channel = counts{1};
    extended_report = msiq.instruments.awg_memory_capacity(extended);
    assert(extended_report.ok);
    assert(isequal(extended_report.available_samples_per_channel, ...
        [536870912 536870912]));
end

option16 = extended;
option16.option_raw = '001,16G,0';
option16_report = msiq.instruments.awg_memory_capacity(option16);
assert(option16_report.option_16g_detected);
assert(all(option16_report.available_samples_per_channel == 4294967296));

prepared = msiq.instruments.prepare_awg_download( ...
    {zeros(262143,1), zeros(262145,1)}, [3 4], [1 2], 128);
assert(isequal(prepared.source_sample_counts, [262143 262145]));
assert(isequal(prepared.final_sample_counts, [262144 262272]));
unequal = base;
unequal.rdiv = 'DIV1';
unequal.required_samples_per_channel = prepared.final_sample_counts;
unequal_report = msiq.instruments.awg_memory_capacity(unequal);
assert(~unequal_report.ok && unequal_report.per_channel(1).ok && ...
    ~unequal_report.per_channel(2).ok);

temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();
msiq.instruments.set_mock_awg_state(struct('options_raw', '001,16G,0'));
status16 = msiq.traditional_tx('awg_status', [], struct('cfg_override', cfg));
assert(status16.state.options_query_ok && contains(status16.state.options_raw, '16G'));

msiq.instruments.reset_audit();
failure_cfg = cfg;
failure_cfg.instrument.awg.mock_options_query_failure = true;
fallback = msiq.traditional_tx('awg_status', [], ...
    struct('cfg_override', failure_cfg));
assert(strcmp(fallback.status, 'ok') && ~fallback.state.options_query_ok);
assert(contains(fallback.state.options_raw, 'QUERY_FAILED'));
fallback_context = extended;
fallback_context.option_raw = fallback.state.options_raw;
fallback_report = msiq.instruments.awg_memory_capacity(fallback_context);
assert(fallback_report.ok && ...
    strcmp(fallback_report.capacity_source_code, ...
    'keysight_standard_query_fallback'));

for active = [false true]
    msiq.instruments.reset_audit();
    if active
        set_mock_outputs(cfg, 1, true);
    end
    status = msiq.traditional_tx('awg_status', [], ...
        struct('cfg_override', cfg));
    plan = msiq.traditional_tx('preview_plan', [], struct( ...
        'cfg_override', cfg, 'route', 'pair_b_ch3_ch4', ...
        'rdiv', 'DIV4', 'frame_repetitions', 1, ...
        'awg_state', status.state));
    plan.run_dir = temporary;
    plan.required_confirmation = 'TEST CAPACITY PREFLIGHT';
    plan.plan_hash = 'test-capacity-preflight';
    plan.desired.memory_mode = 'INT';
    plan.desired.channel_memory_modes = {'INT','INT','INT','INT'};
    plan.download.source_sample_counts = [593280 593280];
    plan.download.final_sample_counts = [593280 593280];
    plan.download.channel_data = {zeros(593280,1,'int8'), ...
        zeros(593280,1,'int8')};
    plan.desired.source_sample_counts = [593280 593280];
    plan.desired.required_samples_per_channel = [593280 593280];
    plan.desired.sample_count = 593280;
    plan.desired.padded_sample_count = 593280;
    before_audit = msiq.instruments.get_audit();
    before_commands = audit_commands();
    before_awg = msiq.instruments.io_audit('get_mock_awg_state', '');
    rejected = false;
    try
        apply_traditional_plan(plan);
    catch exception
        rejected = strcmp(exception.identifier, ...
            'msiq:traditionalTx:AwgMemoryCapacity');
    end
    assert(rejected);
    after_audit = msiq.instruments.get_audit();
    after_commands = audit_commands();
    after_awg = msiq.instruments.io_audit('get_mock_awg_state', '');
    assert(after_audit.awg_writes == before_audit.awg_writes);
    assert(after_audit.awg_binary_writes == before_audit.awg_binary_writes);
    assert(after_audit.scope_connections == before_audit.scope_connections && ...
        after_audit.scope_queries == before_audit.scope_queries && ...
        after_audit.scope_captures == before_audit.scope_captures);
    assert(after_audit.awg_output_mask == before_audit.awg_output_mask);
    assert(isequal(after_commands, before_commands));
    assert(isequal(after_awg, before_awg));
end
note = ['IIII DIV1/DIV2/DIV4 rejected at 593280 samples/channel; ', ...
    'EXT, 16G, fallback, aligned unequal lengths, and zero-write guards passed'];
clear cleanup;
end

function note = test_mock_traditional_sdel_settings()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();
msiq.instruments.io_audit('set_mock_awg_state', struct( ...
    'sample_clock_delay_samples', [10 11 12 13], ...
    'amplitude_vpp', [0.18 0.19 0.20 0.21], ...
    'offset_v', [0.01 0.02 0.03 0.04]));
status = msiq.traditional_tx('awg_status', [], struct('cfg_override', cfg));
assert(strcmpi(status.status, 'ok'));
assert(isequal([status.state.traces.sample_clock_delay_samples], [10 11 12 13]));
set_mock_outputs(cfg, [1 3 4], true);
command_count = numel(audit_commands());
result = msiq.traditional_tx('awg_channel_settings', [], struct( ...
    'cfg_override', cfg, 'route', 'pair_b_ch3_ch4', ...
    'amplitude_vpp', [0.24 0.25], 'offset_v', [-0.01 0.015], ...
    'sample_clock_delay_samples', [7 15]));
assert(isequal([result.state.traces(3:4).sample_clock_delay_samples], [7 15]));
assert(isequal(logical(result.state.outputs), [true false true true]));
assert(result.state.traces(1).amplitude_vpp == 0.18 && ...
    result.state.traces(1).sample_clock_delay_samples == 10);
commands = audit_commands();
settings_commands = commands(command_count+1:end);
assert(~any(contains(settings_commands, ':ABOR', 'IgnoreCase', true)));
assert(~any(contains(settings_commands, ':TRACe', 'IgnoreCase', true)));
assert(~any(contains(settings_commands, ':ARM:SDELay1', 'IgnoreCase', true)));
assert(~any(contains(settings_commands, ':ARM:SDELay2', 'IgnoreCase', true)));
assert(any(contains(settings_commands, ':ARM:SDELay3 7', 'IgnoreCase', true)));
assert(any(contains(settings_commands, ':ARM:SDELay4 15', 'IgnoreCase', true)));

command_count = numel(audit_commands());
single = msiq.traditional_tx('awg_channel_settings', [], struct( ...
    'cfg_override', cfg, 'route', 'pair_b_ch3_ch4', ...
    'amplitude_vpp', [0.24 0.25], 'offset_v', [-0.01 0.025], ...
    'sample_clock_delay_samples', [7 15], ...
    'physical_channels', 4, 'setting_names', {{'offset_v'}}));
assert(single.state.traces(4).offset_v == 0.025);
single_commands = audit_commands();
single_commands = single_commands(command_count+1:end);
assert(nnz(contains(single_commands, ':VOLTage4:OFFSet ', ...
    'IgnoreCase', true)) == 1);
assert(~any(contains(single_commands, ':VOLTage3', 'IgnoreCase', true)));
assert(~any(contains(single_commands, ':VOLTage4:AMPLitude', 'IgnoreCase', true)));
assert(~any(contains(single_commands, ':ARM:SDELay', 'IgnoreCase', true)));
assert(~any(contains(single_commands, ':OUTPut3', 'IgnoreCase', true)));
assert(nnz(contains(single_commands, ':OUTPut4 OFF', 'IgnoreCase', true)) == 1);
assert(nnz(contains(single_commands, ':OUTPut4 ON', 'IgnoreCase', true)) == 1);

first = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'sample_clock_delay_samples', [0 0], ...
    'frame_repetitions', 1));
second = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'sample_clock_delay_samples', [0 1], ...
    'frame_repetitions', 1));
assert(all(strcmp(first.waveform_hashes, second.waveform_hashes)));
assert(~strcmp(first.parameter_hash, second.parameter_hash));

msiq.instruments.reset_audit();
msiq.instruments.io_audit('set_mock_awg_state', struct( ...
    'ignore_sdel_writes', [true true false false]));
set_mock_outputs(cfg, [1 2], true);
rejected = false;
try
    msiq.traditional_tx('awg_channel_settings', [], struct( ...
        'cfg_override', cfg, 'route', 'pair_a_ch1_ch2', ...
        'sample_clock_delay_samples', [3 5], ...
        'physical_channels', 1, ...
        'setting_names', {{'sample_clock_delay_samples'}}));
catch exception
    rejected = strcmp(exception.identifier, ...
        'msiq:traditionalTx:ChannelSettingsReadback');
end
assert(rejected);
audit = msiq.instruments.get_audit();
assert(bitand(uint8(audit.awg_output_mask), uint8(1)) == 0);
assert(bitand(uint8(audit.awg_output_mask), uint8(2)) == 2);
failure_commands = audit_commands();
assert(~any(contains(failure_commands, ':ARM:SDELay2 ', 'IgnoreCase', true)));
note = ['four SDEL values read back; single-channel/single-field writes contain ', ...
    'no ABOR/trace; readback mismatch closes only the selected output'];
clear cleanup;
end

function note = test_traditional_variable_rate_loopback()
cfg = msiq.build_config('v2_traditional_wz');
orders = [4 16 64];
msiq.instruments.reset_audit();
for order = orders
    plan = msiq.traditional_tx('preview_plan', [], struct( ...
        'cfg_override', cfg, 'route', 'pair_a_ch1_ch2', 'rdiv', 'DIV4', ...
        'modulation_order', order, 'symbol_rate_hz', 65e9/30.5, ...
        'rate_authority', 'symbol_rate', 'frame_repetitions', 3));
    assert(abs(plan.cfg.waveform.selected_up-30.5) < 1e-10);
    assert(strcmp(plan.cfg.waveform.rate_generation_mode, ...
        'fixed_rate_rational_resample'));
    assert(~isempty(plan.waveforms.awg_dac_data));
    assert(any(abs(plan.waveforms.awg_dac_data(:)) > 0));
    raw = msiq.simulate_capture(plan.waveforms, plan.cfg, 'A', struct( ...
        'snr_db', 50, 'channel_matrix', eye(2), ...
        'image_matrix', zeros(2), 'rng_seed', 7300+order));
    decoded = msiq.decode_capture(raw, plan.tx_ref, plan.cfg);
    assert(decoded.pass && decoded.sync_ok);
    assert(all([decoded.primary_streams.post_fec_ber] == 0));
    assert(strcmp(decoded.iq_orientation.selected, 'normal'));
    mirrored = raw;
    mirrored.samples(:,2) = -mirrored.samples(:,2);
    corrected = msiq.decode_capture(mirrored, plan.tx_ref, plan.cfg);
    assert(corrected.pass && corrected.sync_ok);
    assert(corrected.iq_orientation.conjugate_applied);
    assert(strcmp(corrected.iq_orientation.status_text, ...
        '检测到 IQ 镜像，已自动校正'));
    assert(corrected.iq_orientation.alternate_retry_count <= 1);
end
normal = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'modulation_order', 16, ...
    'frame_repetitions', 1, 'invert_i', false, 'invert_q', false));
inverted = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'modulation_order', 16, ...
    'frame_repetitions', 1, 'invert_i', true, 'invert_q', false));
assert(~strcmp(normal.waveform_signature, inverted.waveform_signature));
assert(max(abs(inverted.waveforms.awg_dac_data(:,1)+ ...
    normal.waveforms.awg_dac_data(:,1))) < 1e-12);
assert(max(abs(inverted.waveforms.awg_dac_data(:,2)- ...
    normal.waveforms.awg_dac_data(:,2))) < 1e-12);
polarity_audit = msiq.instruments.get_audit();
assert(polarity_audit.awg_connections == 0 && ...
    polarity_audit.awg_queries == 0 && polarity_audit.awg_writes == 0);
full_scale = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'modulation_order', 16, 'frame_repetitions', 3, ...
    'normalization_mode', 'pair_common_final_full_scale'));
peaks = max(abs(full_scale.waveforms.awg_dac_data), [], 1);
assert(abs(max(peaks(1:2))-1) < 1e-12 && ...
    abs(max(peaks(3:4))-1) < 1e-12);
assert(full_scale.waveforms.dac_scale_factors(1) == ...
    full_scale.waveforms.dac_scale_factors(2));
assert(full_scale.waveforms.dac_scale_factors(3) == ...
    full_scale.waveforms.dac_scale_factors(4));
assert(max(full_scale.waveforms.sample_range_overflow_fraction) == 0);
legacy_scale = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'modulation_order', 16, 'frame_repetitions', 1, ...
    'peak_scale', 0.73));
assert(strcmp(legacy_scale.waveforms.normalization.mode, 'legacy_peak_scale'));
assert(max(abs(legacy_scale.waveforms.master_dac_data), [], 'all') <= 0.73+1e-12);
base_raw = msiq.simulate_capture(full_scale.waveforms, full_scale.cfg, 'A', ...
    struct('snr_db', Inf, 'channel_matrix', eye(2), 'image_matrix', zeros(2)));
variants = {[-base_raw.samples(:,1), base_raw.samples(:,2)], ...
    -base_raw.samples, base_raw.samples(:,[2 1])};
expected_mirror = [true false true];
for index = 1:numel(variants)
    trial = base_raw;
    trial.samples = variants{index};
    decoded = msiq.decode_capture(trial, full_scale.tx_ref, full_scale.cfg);
    assert(decoded.pass && decoded.iq_orientation.conjugate_applied == ...
        expected_mirror(index));
end
noise = base_raw;
noise.samples = zeros(size(noise.samples));
failed = false;
try
    msiq.decode_capture(noise, full_scale.tx_ref, full_scale.cfg);
catch exception
    failed = strcmp(exception.identifier, 'msiq:decode:IQOrientationFailed') && ...
        contains(exception.message, '正常和镜像候选均无法同步');
end
assert(failed);
rx_audit = msiq.instruments.get_audit();
assert(rx_audit.awg_connections == 0 && rx_audit.awg_writes == 0 && ...
    rx_audit.awg_binary_writes == 0);
bandwidth_plan = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'occupied_bandwidth_hz', 2.5e9, ...
    'rate_authority', 'bandwidth', 'rolloff', 0.2, ...
    'frame_repetitions', 1));
assert(abs(bandwidth_plan.cfg.waveform.symbol_rate_hz-2.5e9/1.2) < 1);
for up = [29 30 31]
    legacy = msiq.traditional_tx('preview_plan', [], struct( ...
        'cfg_override', cfg, 'selected_up', up, 'frame_repetitions', 1));
    assert(abs(legacy.cfg.waveform.selected_up-up) < 1e-10);
    assert(strcmp(legacy.cfg.waveform.rate_generation_mode, ...
        'legacy_integer_up'));
end
note = ['QPSK/16QAM/64QAM normal and mirrored IQ decode with BER=0; ', ...
    'I/Q inversion and swap select a locked normal/conjugate candidate; ', ...
    '100% pair normalization, legacy peak scale, failure reporting, zero AWG I/O, ', ...
    'bandwidth authority, and legacy UP 29/30/31 verified'];
end

function note = test_mock_tx_workbench_gui()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
record_path = fullfile(temporary, 'must_not_be_created.mat');
initial = struct('route', 'pair_a_ch1_ch2', ...
    'frame_repetitions', 3, ...
    'symbol_rate_hz', 65e9/30.5, ...
    'occupied_bandwidth_hz', (65e9/30.5)*1.15, ...
    'amplitude_vpp', [0.2 0.2 0.3 0.31], ...
    'offset_v', [0 0 0.02 0.03], ...
    'sample_clock_delay_samples', [2 5 11 12]);
sizes = [1100 700; 1500 900];
for index = 1:size(sizes,1)
    msiq.instruments.reset_audit();
    msiq.instruments.io_audit('set_mock_awg_state', struct( ...
        'raster_hz', 64e9, ...
        'options_raw', '001,16G,0', ...
        'sample_clock_delay_samples', [1 0 0 0]));
    options = struct('visible', false, 'maximize', false, ...
        'synchronous_startup', true, ...
        'position', [20 20 sizes(index,:)], ...
        'backend_options', struct('cfg_override', cfg), ...
        'initial_params', initial, 'persist_parameters', false, ...
        'parameter_record_path', record_path, ...
        'hardware_apply_delay_s', 0.05);
    fig = msiq.tx_workbench_app(options);
    fig_cleanup = onCleanup(@() close_validation_figure(fig));
    state = wait_for_workbench(fig, ...
        @(candidate) candidate.connected && ...
        strcmp(candidate.hardware_sync_state, 'different'), ...
        3, 'initial read-only hardware comparison');
    assert(state.connected && state.plan_valid && ~state.waveform_stale);
    assert(state.params.frame_repetitions == initial.frame_repetitions);
    assert(state.plan.tx_ref.frame.frame_repetitions == initial.frame_repetitions);
    assert(isfield(state.ui,'frame_repetitions'));
    assert(strcmp(get(state.ui.frame_repetitions,'Enable'),'on'));
    startup_audit = msiq.instruments.get_audit();
    assert(startup_audit.awg_writes == 0 && ...
        startup_audit.awg_binary_writes == 0);
    assert(abs(str2double(get(state.ui.current_delay_ps(1), 'String'))-15.625) < 0.001);
    assert(abs(str2double(get(state.ui.target_delay_ps(1), 'String'))- ...
        2/65e9*1e12) < 0.001);
    assert(strcmp(state.params.normalization_mode, ...
        'pair_common_final_full_scale'));
    assert(~isfield(state.ui, 'invert_i') && ~isfield(state.ui, 'peak_scale') && ...
        ~isfield(state.ui, 'rrc_span') && ~isfield(state.ui, 'seed') && ...
        ~isfield(state.ui, 'sync_length') && ~isfield(state.ui, 'ldpc_blocks'));
    assert(strcmp(get(state.ui.reconnect, 'Visible'), 'off'));
    assert(strcmp(get(state.ui.retry_settings, 'Visible'), 'off'));
    assert(isempty(get(state.ui.download_hint, 'String')));
    assert(contains(get(state.ui.output_hint, 'String'), '没有匹配'));
    assert(~isfield(state.ui, 'instrument'));
    assert(strcmp(get(state.ui.plan_panel, 'Title'), 'AWG 与下载'));
    assert(strcmp(get(state.ui.phase, 'String'), ...
        '阶段：状态回读完成；未修改设备'));
    assert(strcmp(get(state.ui.hardware_summary, 'String'), ...
        '离开输入框后写入 AWG'));
    assert(strcmp(get(state.ui.dashboard_title, 'String'), '发射波形检测'));
    assert(strcmp(get(state.ui.plan_scroll, 'Visible'), 'off'));
    for axis_index = 1:4
        assert(~isempty(allchild(state.ui.axes(axis_index))));
    end
    assert(isempty(findall(fig, 'Type', 'text', ...
        'String', '图组生成失败')));
    assert_axes_do_not_overlap(state.ui.axes, ...
        state.ui.params_outer, state.ui.plan_panel);
    assert_plan_blocks_fit(state);
    assert(state.plan.memory_capacity.ok);
    assert(state.plan.memory_capacity.option_16g_detected);
    assert(all(state.plan.memory_capacity.available_samples_per_channel == ...
        4294967296));
    assert(isequal(state.plan.final_sample_counts, ...
        state.plan.memory_capacity.required_samples_per_channel));
    capacity_text = strjoin([ ...
        string(get(state.ui.plan_capacity_header, 'String')); ...
        string(get(state.ui.plan_capacity_labels, 'String')); ...
        string(get(state.ui.plan_capacity, 'String'))], ' ');
    assert(contains(capacity_text, '下载准备'));
    assert(contains(capacity_text, '目标内存'));
    assert(all(contains(capacity_text, ...
        {'CH1 使用','CH1 可用','CH2 使用','CH2 可用','GSa','%'})));
    assert(~contains(capacity_text, '合计'));
    assert(contains(capacity_text, '结果'));
    assert(contains(capacity_text, '通过'));
    awg_text = strjoin([ ...
        string(get(state.ui.plan_awg_header, 'String')); ...
        string(get(state.ui.plan_awg_labels, 'String')); ...
        string(get(state.ui.plan_awg, 'String'))], ' ');
    assert(all(contains(awg_text, {'AWG 当前','IDN','地址','参考时钟', ...
        'DAC 模式','RDIV','Raster','CH1 / CH2','CH3 / CH4'})));
    header_controls = findall(state.ui.header, 'Type', 'uicontrol');
    header_text = strjoin(graphics_text_strings(header_controls), ' ');
    assert(~any(contains(header_text, ...
        {'IDN','地址','参考时钟','Raster','CH1 OFF','CH2 OFF'})));
    right_text = strjoin([ ...
        string(get(state.ui.plan_awg_header, 'String')); ...
        string(get(state.ui.plan_awg_labels, 'String')); ...
        string(get(state.ui.plan_awg, 'String')); ...
        string(get(state.ui.plan_capacity_header, 'String')); ...
        string(get(state.ui.plan_capacity_labels, 'String')); ...
        string(get(state.ui.plan_capacity, 'String')); ...
        string(get(state.ui.plan_changes_header, 'String')); ...
        string(get(state.ui.plan_changes_labels, 'String')); ...
        string(get(state.ui.plan_changes, 'String')); ...
        string(get(state.ui.plan_fixed_header, 'String')); ...
        string(get(state.ui.plan_fixed_labels, 'String')); ...
        string(get(state.ui.plan_fixed, 'String'))], ' ');
    repeated_right_items = {'符号率','占用带宽','UP / RDIV', ...
        '存储采样率','PAPR','同步','训练 / 导频', ...
        '保护 / Seed','DAC raster'};
    assert(~any(contains(right_text, repeated_right_items)));
    central_text_handles = findall(state.ui.axes, 'Type', 'text');
    central_text = strjoin(graphics_text_strings(central_text_handles), ' ');
    assert(~any(contains(central_text, {'Vpp','Offset','AWG 采样率', ...
        '符号率','滚降系数','RRC 带宽边界','Nyquist','Rs '})));
    assert_tx_hardware_columns(state);
    assert_parameter_scroll(state, fig);
    path = fullfile(temporary, sprintf('tx_gui_%dx%d.png', ...
        sizes(index,1), sizes(index,2)));
    print(fig, path, '-dpng', '-r110');
    listing = dir(path);
    pixels = imread(path);
    assert(listing.bytes > 30000 && std(double(pixels(:))) > 5);
    if index == 1
        for frame_count = [1 3 1]
            set(state.ui.frame_repetitions,'String',num2str(frame_count));
            invoke_callback(state.ui.frame_repetitions);
            state = getappdata(fig,'tx_workbench_state');
            assert(state.params.frame_repetitions == frame_count);
            invoke_callback(state.ui.preview);
            state = getappdata(fig,'tx_workbench_state');
            assert(state.plan_valid && ...
                state.plan.tx_ref.frame.frame_repetitions == frame_count);
        end
        same_value_command_count = numel(audit_commands());
        set(state.ui.target_vpp(1), 'String', '0.2');
        invoke_callback(state.ui.target_vpp(1));
        drawnow; pause(0.08); drawnow;
        state = getappdata(fig, 'tx_workbench_state');
        assert(~state.hardware_dirty && ...
            numel(audit_commands()) == same_value_command_count);
        msiq.instruments.reset_audit();
        set_mock_outputs(cfg, [1 2], true);
        command_count = numel(audit_commands());
        set(state.ui.target_vpp(1), 'String', '0.23');
        invoke_callback(state.ui.target_vpp(1));
        state = getappdata(fig, 'tx_workbench_state');
        set(state.ui.target_offset(2), 'String', '0.015');
        invoke_callback(state.ui.target_offset(2));
        state = getappdata(fig, 'tx_workbench_state');
        set(state.ui.target_sdel(2), 'String', '7.6');
        invoke_callback(state.ui.target_sdel(2));
        changed = getappdata(fig, 'tx_workbench_state');
        assert(changed.hardware_dirty && changed.plan_valid && ...
            ~changed.waveform_stale);
        assert(changed.params.sample_clock_delay_samples(2) == 8);
        changed = wait_for_workbench(fig, ...
            @(candidate) ~candidate.busy && ~candidate.hardware_dirty && ...
            strcmp(candidate.hardware_sync_state, 'different'), ...
            3, 'debounced single-field synchronization');
        settings_commands = audit_commands();
        settings_commands = settings_commands(command_count+1:end);
        assert(nnz(contains(settings_commands, ':VOLTage1:AMPLitude ', ...
            'IgnoreCase', true)) == 1);
        assert(~any(contains(settings_commands, ':VOLTage2:AMPLitude ', ...
            'IgnoreCase', true)));
        assert(nnz(contains(settings_commands, ':VOLTage2:OFFSet ', ...
            'IgnoreCase', true)) == 1);
        assert(~any(contains(settings_commands, ':VOLTage1:OFFSet ', ...
            'IgnoreCase', true)));
        assert(any(contains(settings_commands, ':ARM:SDELay2 8', ...
            'IgnoreCase', true)));
        assert(~any(contains(settings_commands, ':ABOR', 'IgnoreCase', true)));
        assert(~any(contains(settings_commands, ':TRACe', 'IgnoreCase', true)));
        assert(~any(contains(settings_commands, ':VOLTage3', 'IgnoreCase', true)));
        assert(~any(contains(settings_commands, ':VOLTage4', 'IgnoreCase', true)));
        assert(nnz(contains(settings_commands, ':OUTPut1 OFF', ...
            'IgnoreCase', true)) == 1);
        assert(nnz(contains(settings_commands, ':OUTPut1 ON', ...
            'IgnoreCase', true)) == 1);

        commands_before_invalid = numel(audit_commands());
        set(changed.ui.target_vpp(1), 'String', 'not-a-number');
        invoke_callback(changed.ui.target_vpp(1));
        drawnow; pause(0.08); drawnow;
        rejected = getappdata(fig, 'tx_workbench_state');
        assert(rejected.params.amplitude_vpp(1) == 0.23);
        rejected_color = get(rejected.ui.target_vpp(1), 'BackgroundColor');
        assert(rejected_color(1) > 0.99 && rejected_color(2) < 0.95);
        assert(numel(audit_commands()) == commands_before_invalid);

        msiq.instruments.io_audit('set_mock_awg_state', struct( ...
            'ignore_sdel_writes', [true false false false]));
        set(rejected.ui.target_sdel(1), 'String', '9');
        invoke_callback(rejected.ui.target_sdel(1));
        failed_sync = wait_for_workbench(fig, ...
            @(candidate) strcmp(candidate.hardware_sync_state, 'failed'), ...
            3, 'channel synchronization failure');
        failed_audit = msiq.instruments.get_audit();
        assert(bitand(uint8(failed_audit.awg_output_mask), uint8(1)) == 0);
        assert(bitand(uint8(failed_audit.awg_output_mask), uint8(2)) == 2);
        assert(strcmp(get(failed_sync.ui.retry_settings, 'Visible'), 'on'));
        msiq.instruments.io_audit('set_mock_awg_state', struct( ...
            'ignore_sdel_writes', false(1,4)));
        invoke_callback(failed_sync.ui.retry_settings);
        changed = wait_for_workbench(fig, ...
            @(candidate) strcmp(candidate.hardware_sync_state, 'synced'), ...
            3, 'channel synchronization retry');

        set(changed.ui.bandwidth, 'String', '2.6');
        invoke_callback(changed.ui.bandwidth);
        changed = getappdata(fig, 'tx_workbench_state');
        assert(changed.waveform_stale && changed.plan_valid);
        assert(contains(get(changed.ui.dashboard_title, 'String'), '旧预览'));
        assert(abs(changed.params.symbol_rate_hz- ...
            2.6e9/(1+changed.params.rolloff)) < 1);

        invoke_callback(changed.ui.preview);
        changed = getappdata(fig, 'tx_workbench_state');
        assert(changed.plan_valid && ~changed.waveform_stale);
        changed.confirmation_handler = @(~) false;
        setappdata(fig, 'tx_workbench_state', changed);
        msiq.instruments.reset_audit();
        invoke_callback(changed.ui.download);
        cancelled = getappdata(fig, 'tx_workbench_state');
        cancelled_audit = msiq.instruments.get_audit();
        assert(~cancelled.output_running && isempty(cancelled.last_run_dir));
        assert(cancelled_audit.awg_writes == 0 && ...
            cancelled_audit.awg_binary_writes == 0);

        cancelled.confirmation_handler = @(~) true;
        setappdata(fig, 'tx_workbench_state', cancelled);
        invoke_callback(cancelled.ui.download);
        running = getappdata(fig, 'tx_workbench_state');
        running_audit = msiq.instruments.get_audit();
        assert(running.output_running && isfolder(running.last_run_dir));
        assert(bitand(uint8(running_audit.awg_output_mask), uint8(3)) == 3);
        assert(isequal(running.plan.hardware_targets.amplitude_vpp, ...
            running.params.amplitude_vpp));
        assert(isequal(running.plan.hardware_targets.offset_v, ...
            running.params.offset_v));
        assert(isequal(running.plan.hardware_targets.sample_clock_delay_samples, ...
            running.params.sample_clock_delay_samples));
        reference = load(running.plan.reference_bundle_path, 'bundle');
        assert(isequal(reference.bundle.awg_channel_settings.target_all_amplitude_vpp, ...
            running.params.amplitude_vpp));
        assert(numel(reference.bundle.awg_channel_settings.readback_amplitude_vpp) == 4);
        assert(strcmp(reference.bundle.waveform_normalization.mode, ...
            'pair_common_final_full_scale'));
        set_mock_outputs(cfg, 2, false);
        invoke_callback(running.ui.reconnect);
        running = getappdata(fig, 'tx_workbench_state');
        assert(running.output_running && strcmp(running.output_state, 'i_only'));
        assert(strcmp(get(running.ui.output, 'String'), '停止输出'));
        binary_writes = running_audit.awg_binary_writes;
        command_count = numel(audit_commands());
        invoke_callback(running.ui.output);
        stopped = getappdata(fig, 'tx_workbench_state');
        assert(~stopped.output_running && strcmp(get(stopped.ui.output, ...
            'String'), '开始输出'));
        stopped_audit = msiq.instruments.get_audit();
        assert(bitand(uint8(stopped_audit.awg_output_mask), uint8(3)) == 0);
        invoke_callback(stopped.ui.output);
        restarted = getappdata(fig, 'tx_workbench_state');
        restarted_audit = msiq.instruments.get_audit();
        assert(restarted.output_running && ...
            bitand(uint8(restarted_audit.awg_output_mask), uint8(3)) == 3);
        assert(restarted_audit.awg_binary_writes == binary_writes);
        reuse_commands = audit_commands();
        reuse_commands = reuse_commands(command_count+1:end);
        assert(~any(contains(reuse_commands, ':ABOR', 'IgnoreCase', true)));
        assert(~any(contains(reuse_commands, ':TRACe', 'IgnoreCase', true)));
        waveform_command_count = numel(audit_commands());
        set(restarted.ui.modulation, 'Value', 3);
        invoke_callback(restarted.ui.modulation);
        old_waveform = getappdata(fig, 'tx_workbench_state');
        assert(old_waveform.waveform_stale && old_waveform.output_running);
        assert(contains(get(old_waveform.ui.dashboard_title, 'String'), '旧预览'));
        assert(contains(get(old_waveform.ui.output_hint, 'String'), '旧波形'));
        assert(numel(audit_commands()) == waveform_command_count);
        set(old_waveform.ui.route, 'Value', 2);
        invoke_callback(old_waveform.ui.route);
        route_rejected = getappdata(fig, 'tx_workbench_state');
        assert(strcmp(route_rejected.params.route, 'pair_a_ch1_ch2'));
        assert(contains(get(route_rejected.ui.phase, 'String'), '先停止输出'));
        invoke_callback(route_rejected.ui.output);
        stopped_old = getappdata(fig, 'tx_workbench_state');
        assert(~stopped_old.output_running);
        set(stopped_old.ui.route, 'Value', 2);
        invoke_callback(stopped_old.ui.route);
        switched = getappdata(fig, 'tx_workbench_state');
        assert(strcmp(switched.params.route, 'pair_b_ch3_ch4'));
        assert(isempty(switched.loaded_route) && isempty(switched.loaded_signature));
        assert(abs(str2double(get(switched.ui.target_vpp(1), 'String'))-0.3) < 1e-12);
        assert(abs(str2double(get(switched.ui.target_vpp(2), 'String'))-0.31) < 1e-12);
        assert(abs(str2double(get(switched.ui.target_offset(1), 'String'))-0.02) < 1e-12);
        assert(abs(str2double(get(switched.ui.target_offset(2), 'String'))-0.03) < 1e-12);
        assert(str2double(get(switched.ui.target_sdel(1), 'String')) == 11);
        assert(str2double(get(switched.ui.target_sdel(2), 'String')) == 12);
    else
        blocked = state;
        blocked.plan.preflight.ok = false;
        blocked.plan.preflight.reason = '测试容量不足';
        blocked.plan.memory_capacity.ok = false;
        setappdata(fig, 'tx_workbench_state', blocked);
        audit_before_block = msiq.instruments.get_audit();
        commands_before_block = audit_commands();
        invoke_callback(blocked.ui.download);
        blocked = getappdata(fig, 'tx_workbench_state');
        audit_after_block = msiq.instruments.get_audit();
        assert(strcmp(get(blocked.ui.download, 'Enable'), 'off'));
        assert(contains(get(blocked.ui.phase, 'String'), '禁止下载'));
        assert(audit_after_block.awg_writes == audit_before_block.awg_writes);
        assert(audit_after_block.awg_binary_writes == ...
            audit_before_block.awg_binary_writes);
        assert(isequal(audit_commands(), commands_before_block));
        blocked.awg_status.state.outputs = [false false true false];
        setappdata(fig, 'tx_workbench_state', blocked);
        set(blocked.ui.route, 'Value', 2);
        invoke_callback(blocked.ui.route);
        occupied = getappdata(fig, 'tx_workbench_state');
        assert(strcmp(occupied.params.route, 'pair_a_ch1_ch2'));
        assert(contains(get(occupied.ui.phase, 'String'), '目标路由'));
        occupied.awg_status.state.outputs = false(1,4);
        setappdata(fig, 'tx_workbench_state', occupied);
        set(occupied.ui.route, 'Value', 2);
        invoke_callback(occupied.ui.route);
        switched = getappdata(fig, 'tx_workbench_state');
        assert(strcmp(switched.params.route, 'pair_b_ch3_ch4'));
        assert(abs(str2double(get(switched.ui.target_vpp(1), 'String'))-0.3) < 1e-12);
        assert(abs(str2double(get(switched.ui.target_vpp(2), 'String'))-0.31) < 1e-12);
        assert(str2double(get(switched.ui.target_sdel(1), 'String')) == 11);
        assert(str2double(get(switched.ui.target_sdel(2), 'String')) == 12);
        restore_command_count = numel(audit_commands());
        invoke_callback(switched.ui.restore_defaults);
        restored = getappdata(fig, 'tx_workbench_state');
        assert(strcmp(restored.params.route, 'pair_a_ch1_ch2'));
        assert(numel(audit_commands()) == restore_command_count);
    end
    assert(~isfile(record_path));
    clear fig_cleanup;
end

legacy_record = fullfile(temporary, 'legacy_tx_targets.mat');
params = struct('route', 'pair_b_ch3_ch4', ...
    'amplitude_vpp', [0.33 0.34], 'offset_v', [-0.02 0.025], ...
    'sample_clock_delay_samples', [13 14]);
save(legacy_record, 'params', '-v7');
legacy_fig = msiq.tx_workbench_app(struct('visible', false, 'maximize', false, ...
    'synchronous_startup', true, 'startup_preview', false, ...
    'auto_connect', false, 'position', [20 20 1100 700], ...
    'persist_parameters', true, 'parameter_record_path', legacy_record));
legacy_cleanup = onCleanup(@() close_validation_figure(legacy_fig));
legacy = getappdata(legacy_fig, 'tx_workbench_state');
assert(isequal(legacy.params.amplitude_vpp, [0.2 0.2 0.33 0.34]));
assert(isequal(legacy.params.offset_v, [0 0 -0.02 0.025]));
assert(isequal(legacy.params.sample_clock_delay_samples, [0 0 13 14]));
clear legacy_cleanup;

failed_cfg = cfg;
failed_cfg.instrument.awg.fail_stage = 'connect_awg';
failed = msiq.tx_workbench_app(struct('visible', false, 'maximize', false, ...
    'synchronous_startup', true, 'position', [20 20 1100 700], ...
    'backend_options', struct('cfg_override', failed_cfg), ...
    'initial_params', initial, 'persist_parameters', false, ...
    'parameter_record_path', record_path, 'hardware_apply_delay_s', 0.05));
failed_cleanup = onCleanup(@() close_validation_figure(failed));
failed_state = getappdata(failed, 'tx_workbench_state');
assert(~failed_state.connected && failed_state.plan_valid);
assert(strcmp(get(failed_state.ui.reconnect, 'Visible'), 'on'));
assert(contains(get(failed_state.ui.phase, 'String'), 'connect_awg', ...
    'IgnoreCase', true));
commands_before_offline_edit = numel(audit_commands());
set(failed_state.ui.target_vpp(1), 'String', '0.27');
invoke_callback(failed_state.ui.target_vpp(1));
drawnow; pause(0.08); drawnow;
offline = getappdata(failed, 'tx_workbench_state');
assert(~offline.connected && offline.hardware_dirty);
assert(numel(audit_commands()) == commands_before_offline_edit);
offline.backend_options = struct('cfg_override', cfg);
setappdata(failed, 'tx_workbench_state', offline);
reconnect_command_count = numel(audit_commands());
invoke_callback(offline.ui.reconnect);
    reconnected = wait_for_workbench(failed, ...
        @(candidate) candidate.connected && ~candidate.busy && ...
        ~candidate.hardware_dirty && ...
        strcmp(candidate.hardware_sync_state, 'different'), ...
        6, 'reconnect single-field synchronization');
assert(reconnected.params.amplitude_vpp(1) == 0.27);
mock_state = msiq.instruments.io_audit('get_mock_awg_state', []);
assert(mock_state.amplitude_vpp(1) == 0.27);
reconnect_commands = audit_commands();
reconnect_commands = reconnect_commands(reconnect_command_count+1:end);
assert(nnz(contains(reconnect_commands, ':VOLTage1:AMPLitude ', ...
    'IgnoreCase', true)) == 1);
assert(~any(contains(reconnect_commands, ':VOLTage2', 'IgnoreCase', true)));
assert(~any(contains(reconnect_commands, ':VOLTage3', 'IgnoreCase', true)));
assert(~any(contains(reconnect_commands, ':VOLTage4', 'IgnoreCase', true)));
assert(~any(contains(reconnect_commands, ':ARM:SDELay', 'IgnoreCase', true)));
assert(~any(contains(reconnect_commands, ':ABOR', 'IgnoreCase', true)));
assert(~any(contains(reconnect_commands, ':TRACe', 'IgnoreCase', true)));
assert(~isfile(record_path));
note = ['mock GUI renders four plots at two sizes with aligned hardware ', ...
    'columns; edits debounce into one selected-channel write; invalid input ', ...
    'writes nothing; failure shuts outputs down and retries; reconnect ', ...
    'synchronizes offline edits; persistence is isolated; download/output ', ...
    'and waveform reuse remain safe'];
clear failed_cleanup cleanup;
end

function state = wait_for_workbench(fig, predicate, timeout_s, label)
started = tic;
while toc(started) < timeout_s
    drawnow; pause(0.02);
    state = getappdata(fig, 'tx_workbench_state');
    if predicate(state), return; end
end
state = getappdata(fig, 'tx_workbench_state');
error('msiq:validation:TxWorkbenchTimeout', ...
    ['Timed out waiting for %s (state=%s, connected=%d, busy=%d, ', ...
    'dirty=%d).'], label, state.hardware_sync_state, state.connected, ...
    state.busy, state.hardware_dirty);
end

function assert_tx_hardware_columns(state)
for index = 1:4
    position = get(state.ui.hardware_caption(index), 'Position');
    expected_x = [8 96 175 252];
    assert(position(1) == expected_x(index));
end
for channel = 1:2
    current_controls = [state.ui.current_vpp(channel), ...
        state.ui.current_offset(channel), state.ui.current_sdel(channel), ...
        state.ui.current_delay_ps(channel)];
    target_controls = [state.ui.target_vpp(channel), ...
        state.ui.target_offset(channel), state.ui.target_sdel(channel), ...
        state.ui.target_delay_ps(channel)];
    for row = 1:numel(current_controls)
        current_position = get(current_controls(row), 'Position');
        target_position = get(target_controls(row), 'Position');
        assert(current_position(1) == 96 && target_position(1) == 175);
        assert(current_position(3) == target_position(3));
        assert(current_position(1)+current_position(3) < target_position(1));
    end
end
children = allchild(state.ui.param_content);
for index = 1:numel(children)
    position = get(children(index), 'Position');
    assert(position(2) >= 0);
    assert(position(2)+position(4) <= state.ui.param_content_height);
end
end

function assert_parameter_scroll(state, fig)
maximum = get(state.ui.scroll, 'Max');
assert(maximum > 88);
assert(abs(get(state.ui.scroll, 'Value')-maximum) < 1e-9);
viewport = get(state.ui.params_view, 'Position');
content = get(state.ui.param_content, 'Position');
assert(abs(content(2)-(viewport(4)-content(4))) < 1e-9);
set(state.ui.scroll, 'Value', maximum/2);
callback = get(fig, 'WindowScrollWheelFcn');
panel = get(state.ui.params_outer, 'Position');
inside = [panel(1)+20 panel(2)+20];
    callback(fig, struct('VerticalScrollCount', 1, ...
        'PointerPosition', inside));
    after_inside = get(state.ui.scroll, 'Value');
    assert(after_inside < maximum/2);
    callback(fig, struct('VerticalScrollCount', -1, ...
        'PointerPosition', inside));
    after_up = get(state.ui.scroll, 'Value');
    assert(after_up > after_inside);
outside = [panel(1)+panel(3)+20 panel(2)+20];
callback(fig, struct('VerticalScrollCount', 1, ...
    'PointerPosition', outside));
assert(get(state.ui.scroll, 'Value') == after_up);
set(state.ui.scroll, 'Value', 0);
callback = get(state.ui.scroll, 'Callback'); callback(state.ui.scroll, []);
end

function invoke_callback(control)
callback = get(control, 'Callback');
callback(control, []);
end

function values = graphics_text_strings(handles)
values = strings(0,1);
for index = 1:numel(handles)
    raw = string(get(handles(index), 'String'));
    values = [values; raw(:)]; %#ok<AGROW>
end
end

function close_validation_figure(fig)
if ishghandle(fig)
    close(fig);
end
end

function assert_axes_do_not_overlap(handles, left_panel, right_panel)
positions = cell(size(handles));
for index = 1:numel(handles)
    inner = get(handles(index), 'Position');
    inset = get(handles(index), 'TightInset');
    positions{index} = [inner(1)-inset(1), inner(2)-inset(2), ...
        inner(3)+inset(1)+inset(3), inner(4)+inset(2)+inset(4)];
end

for first = 1:numel(handles)
    for second = first+1:numel(handles)
        a = positions{first}; b = positions{second};
        separated = a(1)+a(3) <= b(1) || b(1)+b(3) <= a(1) || ...
            a(2)+a(4) <= b(2) || b(2)+b(4) <= a(2);
        assert(separated);
    end
end
left = get(left_panel, 'Position');
right = get(right_panel, 'Position');
for index = 1:numel(positions)
    extent = positions{index};
    assert(extent(1) >= left(1)+left(3), ...
        'Axis %d crosses left panel: %.3f < %.3f.', index, ...
        extent(1), left(1)+left(3));
    assert(extent(1)+extent(3) <= right(1), ...
        'Axis %d crosses right panel: %.3f > %.3f.', index, ...
        extent(1)+extent(3), right(1));
end
end

function assert_plan_blocks_fit(state)
handles = [state.ui.plan_awg_header state.ui.plan_awg_labels ...
    state.ui.plan_awg state.ui.plan_capacity_header state.ui.plan_capacity_labels ...
    state.ui.plan_capacity state.ui.plan_changes_header ...
    state.ui.plan_changes_labels state.ui.plan_changes state.ui.plan_fixed_header ...
    state.ui.plan_fixed_labels state.ui.plan_fixed];
panel = get(state.ui.plan_content, 'Position');
positions = cell(1, numel(handles));
for index = 1:numel(handles)
    positions{index} = get(handles(index), 'Position');
    position = positions{index};
    extent = get(handles(index), 'Extent');
    assert(position(1) >= 0 && position(2) >= 0);
    assert(position(1)+position(3) <= panel(3));
    assert(position(2)+position(4) <= panel(4));
    assert(extent(3) <= position(3)+2);
    assert(extent(4) <= position(4)+2);
end
viewport = get(state.ui.plan_view, 'Position');
maximum = max(0, panel(4)-viewport(4));
assert(abs(get(state.ui.plan_scroll, 'Max')-max(1,maximum)) < 1e-9);
if maximum > 0
    set(state.ui.plan_scroll, 'Value', 0);
    invoke_callback(state.ui.plan_scroll);
    bottom_position = get(state.ui.plan_content, 'Position');
    assert(abs(bottom_position(2)) < 1e-9);
    set(state.ui.plan_scroll, 'Value', maximum);
    invoke_callback(state.ui.plan_scroll);
    top_position = get(state.ui.plan_content, 'Position');
    assert(abs(top_position(2)-(viewport(4)-panel(4))) < 1e-9);
end
for first = 1:numel(handles)
    for second = first+1:numel(handles)
        a = positions{first};
        b = positions{second};
        separated = a(1)+a(3) <= b(1) || b(1)+b(3) <= a(1) || ...
            a(2)+a(4) <= b(2) || b(2)+b(4) <= a(2);
        assert(separated);
    end
end
end

function note = test_mock_traditional_pair_b_extended_memory()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();
initial = msiq.instruments.io_audit('get_mock_awg_state', '');
initial.rdiv = 'DIV1';
initial.raster_hz = 55e9;
for channel = 1:4
    initial.traces(channel).memory_mode = 'INT';
end
msiq.instruments.set_mock_awg_state(initial);
plan = msiq.traditional_tx('awg_plan', [], struct( ...
    'cfg_override', cfg, 'route', 'pair_b_ch3_ch4', ...
    'rdiv', 'DIV4', 'frame_repetitions', 1));
assert(plan.waveform_sample_count == 148297);
assert(plan.padded_sample_count == 148352);
assert(plan.memory_capacity.ok);
assert(all(plan.memory_capacity.available_samples_per_channel == 536870912));
assert(strcmpi(plan.desired.memory_mode, 'EXT'));
assert(isequal(plan.desired.channel_memory_modes, ...
    {'EXT','EXT','EXT','EXT'}));
applied = apply_traditional_plan(plan);
assert(isequal(applied.output_mask, [false false true true]));
assert(isequal({applied.final_state.traces.memory_mode}, ...
    {'EXT','EXT','EXT','EXT'}));
commands = audit_commands();
rdiv_command = find(contains(commands, ':INST:MEM:EXT:RDIV DIV4', ...
    'IgnoreCase', true), 1);
first_ext_command = find(contains(commands, ':TRACe1:MMOD EXT', ...
    'IgnoreCase', true), 1);
assert(~isempty(rdiv_command) && ~isempty(first_ext_command) && ...
    rdiv_command < first_ext_command);
assert(any(contains(commands, ':TRACe3:DEFine', 'IgnoreCase', true)));
assert(any(contains(commands, ':TRACe4:DEFine', 'IgnoreCase', true)));
assert(~any(contains(commands, ':TRACe1:DEFine', 'IgnoreCase', true)));
assert(~any(contains(commands, ':TRACe2:DEFine', 'IgnoreCase', true)));
three_frame = msiq.traditional_tx('preview_plan', [], struct( ...
    'cfg_override', cfg, 'route', 'pair_b_ch3_ch4', ...
    'rdiv', 'DIV4', 'frame_repetitions', 3, ...
    'hardware_sro_injection_ppm', 200));
assert(three_frame.waveform_sample_count == 444889);
assert(strcmpi(three_frame.desired.memory_mode, 'EXT'));
assert(three_frame.memory_capacity.ok);
assert(three_frame.hardware_sro_injection_ppm == 200);
assert(abs(three_frame.awg_raster_hz-65e9/1.0002) < 1);
assert(abs(three_frame.actual_waveform_sample_rate_hz- ...
    three_frame.awg_raster_hz/4) < 1);

msiq.traditional_tx('awg_stop', [], struct('cfg_override', cfg, ...
    'route', 'pair_b_ch3_ch4'));
for route = {'pair_a_ch1_ch2','pair_b_ch3_ch4'}
    rejected = false;
    try
        msiq.traditional_tx('preview_plan', [], struct( ...
            'cfg_override', cfg, 'route', route{1}, 'rdiv', 'DIV1'));
    catch exception
        rejected = strcmp(exception.identifier, ...
            'msiq:traditionalTx:Div1Unsupported');
    end
    assert(rejected);
end
note = ['CH3/CH4 FOUR/EXT/DIV4 writes and enables only CH3/CH4; ', ...
    'DIV1 is rejected because real M8195A hardware reports the ', ...
    'FOUR/EXT/DIV1 combination as illegal'];
clear cleanup;
end

function note = test_mock_traditional_div2()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();
plan = msiq.traditional_tx('awg_plan', [], struct( ...
    'cfg_override', cfg, 'rdiv', 'DIV2'));
assert(plan.cfg.waveform.frame_repetitions == 1);
assert(plan.waveform_sample_count == 296593);
assert(plan.padded_sample_count == 296704);
assert(plan.memory_capacity.ok);
assert(all(plan.memory_capacity.available_samples_per_channel == 1073741824));
assert(abs(plan.waveform_sample_rate_hz-32.5e9) < 1);
assert(strcmpi(plan.desired.rdiv, 'DIV2'));
assert(isequal(plan.desired.channel_memory_modes, ...
    {'EXT','EXT','INT','INT'}));
assert(plan.public_parameter_changes);
assert(contains(plan.required_confirmation, 'FORCE PUBLIC CHANGE'));
applied = apply_traditional_plan(plan);
assert(isequal(applied.output_mask, [true true false false]));
assert(strcmpi(applied.final_state.rdiv, 'DIV2'));
assert(isequal({applied.final_state.traces.memory_mode}, ...
    {'EXT','EXT','INT','INT'}));
commands = audit_commands();
assert(any(contains(commands, ':TRACe3:MMOD INT', 'IgnoreCase', true)));
assert(any(contains(commands, ':TRACe4:MMOD INT', 'IgnoreCase', true)));
assert(~any(contains(commands, ':TRACe3:DEFine', 'IgnoreCase', true)));
assert(~any(contains(commands, ':TRACe4:DEFine', 'IgnoreCase', true)));

rejected = false;
try
    msiq.traditional_tx('awg_plan', [], struct( ...
        'cfg_override', cfg, 'rdiv', 'DIV2', 'route', 'all_four'));
catch exception
    rejected = strcmp(exception.identifier, 'msiq:traditionalTx:Div2Route');
end
assert(rejected);
note = ['DIV2 uses one EXT I/Q pair at 32.5 GSa/s, leaves CH3/CH4 INT, ', ...
    'and rejects all-four routing'];
clear cleanup;
end

function note = test_mock_traditional_plan_guards()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();
plan = msiq.traditional_tx('awg_plan', [], struct('cfg_override',cfg));
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
write_cleanup = onCleanup(@() msiq.instruments.close_session(session));
msiq.instruments.write_scpi(session, ':OUTPut3 ON');
clear write_cleanup;
blocked = false;
try
    apply_traditional_plan(plan);
catch exception
    blocked = strcmp(exception.identifier, 'msiq:traditionalTx:PlanDrift');
end
assert(blocked);

msiq.instruments.reset_audit();
msiq.instruments.set_mock_awg_state(struct('dac_mode', 'TWO'));
strong_plan = msiq.traditional_tx('awg_plan', [], struct('cfg_override',cfg));
assert(contains(strong_plan.required_confirmation, 'FORCE PUBLIC CHANGE'));
blocked = false;
try
    msiq.traditional_tx('awg_apply', [], struct('plan', strong_plan, ...
        'confirmation_phrase', 'incorrect'));
catch exception
    blocked = strcmp(exception.identifier, 'msiq:traditionalTx:Confirmation');
end
assert(blocked);
applied = apply_traditional_plan(strong_plan);
assert(applied.public_parameter_changes && applied.global_abort_used);
note = 'plan drift blocks apply and shared public changes require the dynamic force phrase';
clear cleanup;
end

function note = test_mock_traditional_other_channel_policy()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();
set_mock_outputs(cfg, [3 4], true);
plan = msiq.traditional_tx('awg_plan', [], struct('cfg_override',cfg));
assert(plan.public_parameter_changes);
applied = apply_traditional_plan(plan);
assert(~applied.other_outputs_restored && isequal(applied.other_outputs_disabled,[3 4]));
assert(~any(applied.final_state.outputs(3:4)));

msiq.instruments.reset_audit();
msiq.instruments.set_mock_awg_state(struct('dac_mode', 'TWO'));
set_mock_outputs(cfg, [3 4], true);
changed = msiq.traditional_tx('awg_plan', [], struct('cfg_override',cfg));
applied = apply_traditional_plan(changed);
assert(isequal(applied.other_outputs_disabled, [3 4]));
assert(~any(applied.final_state.outputs(3:4)));
note = 'other outputs restart only after unchanged route verification; public change leaves CH3/CH4 off';
clear cleanup;
end

function note = test_mock_traditional_scope_capture()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, short_raw_capture());
cfg.instrument.scope.mock_horizontal_sample_rate_hz = 80e9;
cfg.instrument.scope.mock_scope_preprocessing = struct( ...
    'C1', struct('interpolation', 'Linear', 'average_sweeps', 1, ...
        'enhance_resolution', 'None', 'optimize_group_delay', 'PulseResponse'), ...
    'C2', struct('interpolation', 'Linear', 'average_sweeps', 1, ...
        'enhance_resolution', 'None', 'optimize_group_delay', 'PulseResponse'));
msiq.instruments.reset_audit();
status = msiq.traditional_rx('scope_status', [], struct('cfg_override',cfg));
assert(strcmp(status.status, 'ok'));
audit = msiq.instruments.get_audit();
assert(audit.scope_writes == 0 && audit.driver_initializations == 0);
assert(abs(status.scope.sample_rate_hz/80e9 - 1) < 1e-12);
assert(contains(status.scope.sample_rate_source, ...
    'app.Acquisition.Horizontal.SampleRate'));
assert(strcmp(status.scope.preprocessing.status, 'ok'));
assert(strcmp(status.scope.preprocessing.interpolation, 'Linear'));
assert(status.scope.preprocessing.average_sweeps == 1);
assert(strcmp(status.scope.preprocessing.enhance_resolution, 'None'));
assert(strcmp(status.scope.preprocessing.optimize_group_delay, 'PulseResponse'));
assert(all(strcmp({status.scope.preprocessing.channels.channel}, {'C1','C2'})));

plan = msiq.traditional_tx('awg_plan', [], struct('cfg_override',cfg));
apply_traditional_plan(plan);
inbox = fullfile(temporary, 'receiver_inbox');
mkdir(inbox);
portable_path = fullfile(inbox, 'tx_reference_bundle.mat');
copyfile(plan.reference_bundle_path, portable_path);
rx_dir = fullfile(temporary, 'receiver_run');
capture = msiq.traditional_rx('capture', [], struct( ...
    'run_dir', rx_dir, 'tx_reference_bundle', portable_path, ...
    'cfg_override', cfg));
assert(~capture.demod_ready && strcmp(capture.status, 'captured_not_ready_for_demod'));
demod = msiq.traditional_rx('demod_capture', rx_dir, struct('cfg_override', cfg));
assert(strcmp(demod.status, 'blocked'));
assert(~strcmp(demod.run_dir, rx_dir));
assert(contains(demod.run_dir, [filesep 'analysis' filesep]));
assert(isfile(fullfile(demod.run_dir, 'summary.csv')));
diagnostics_dir = fullfile(rx_dir, 'data');
assert(strcmp(capture.diagnostics_dir, diagnostics_dir));
saved_reference = msiq.artifact_path(rx_dir, 'tx_reference_bundle.mat');
assert(isfile(saved_reference) && startsWith(saved_reference, diagnostics_dir));
assert(isfile(fullfile(diagnostics_dir, 'raw_capture.mat')));
assert(isfile(fullfile(diagnostics_dir, 'capture_preparation.mat')));
assert(isfile(fullfile(diagnostics_dir, 'capture_metadata.json')));
assert(isfile(fullfile(rx_dir, 'fig_rx_dashboard.png')));
assert(~isfile(fullfile(rx_dir, 'capture_time_spectrum.png')));
assert(~isfile(fullfile(rx_dir, 'demod_constellation.png')));
assert_nonblank_dashboard(fullfile(rx_dir, 'fig_rx_dashboard.png'), 'rx');
root_entries = dir(rx_dir);
root_files = root_entries(~[root_entries.isdir]);
assert(isequal(sort({root_files.name}), sort({'fig_rx_dashboard.png','overview.png','summary.csv'})));
saved = load(fullfile(diagnostics_dir, 'raw_capture.mat'), 'raw');
assert(abs(saved.raw.channels(1).samples(1) + 0.1) < 1e-7);
assert(abs(saved.raw.channels(1).sample_rate_hz/16.25e9 - 1) < 1e-6);
assert(abs(saved.raw.channels(1).time_axis_s(1) + 1e-9) < 1e-15);

% A longer synthetic capture exercises the portable bundle through demodulation.
cfg.instrument.scope.mock_raw_capture = repeated_scope_capture(plan);
decoded_rx_dir = fullfile(temporary, 'receiver_decoded_run');
decoded_capture = msiq.traditional_rx('capture', [], struct( ...
    'run_dir', decoded_rx_dir, 'tx_reference_bundle', portable_path, ...
    'cfg_override', cfg));
assert(decoded_capture.demod_ready && ...
    strcmp(decoded_capture.status, 'captured_ready_for_demod'));
decoded_output = msiq.traditional_rx('demod_capture', decoded_rx_dir, ...
    struct('cfg_override', cfg));
assert(strcmp(decoded_output.status, 'decoded'));
assert(decoded_output.pairs(1).decoded.payload_reference_used_for_processing == false);
assert_nonblank_dashboard(decoded_output.dashboard_path, 'rx');
assert(~strcmp(decoded_output.run_dir, decoded_rx_dir));
demod_path = msiq.artifact_path(decoded_output.run_dir, 'demod_result.mat');
stored = load(demod_path);
assert(~isfield(stored, 'validation'));
prepared = msiq.load_capture_validation(decoded_rx_dir);
linked = msiq.load_capture_validation(decoded_output.run_dir);
assert(isequaln(linked.validation, prepared.validation));
stored.validation = prepared.validation;
legacy_demod_path = msiq.artifact_path(decoded_rx_dir, 'demod_result.mat', 'write');
save(legacy_demod_path, '-struct', 'stored', '-v7.3');
delete(msiq.artifact_path(decoded_rx_dir, 'capture_preparation.mat'));
compacted = msiq.load_capture_validation(decoded_rx_dir);
assert(isequaln(compacted.validation, prepared.validation));
source_hash = compute_file_sha256(legacy_demod_path);
replayed = msiq.traditional_rx('demod_capture', decoded_rx_dir, ...
    struct('cfg_override', cfg));
assert(strcmp(replayed.status, 'decoded'));
assert(~strcmp(replayed.run_dir, decoded_output.run_dir));
assert(strcmp(compute_file_sha256(legacy_demod_path), source_hash));
compacted = msiq.load_capture_validation(decoded_rx_dir);
assert(isequaln(compacted.validation, prepared.validation));

% Bundles written before configurable modulation/rates omit the new fields.
legacy_bundle_path = fullfile(inbox, 'legacy_tx_reference_bundle.mat');
loaded_bundle = load(portable_path, 'bundle');
bundle = strip_configurable_reference_fields(loaded_bundle.bundle);
save(legacy_bundle_path, 'bundle', '-v7.3');
legacy_bundle_rx_dir = fullfile(temporary, 'receiver_legacy_bundle_run');
legacy_bundle_capture = msiq.traditional_rx('capture', [], struct( ...
    'run_dir', legacy_bundle_rx_dir, ...
    'tx_reference_bundle', legacy_bundle_path, 'cfg_override', cfg));
assert(legacy_bundle_capture.demod_ready);
legacy_bundle_output = msiq.traditional_rx('demod_capture', ...
    legacy_bundle_rx_dir, struct('cfg_override', cfg));
assert(strcmp(legacy_bundle_output.status, 'decoded'));
legacy_stream = legacy_bundle_output.pairs(1).decoded.primary_streams(1);
assert(legacy_stream.post_fec_ber == 0 && legacy_stream.bler == 0);

% Legacy run directories remain readable through the resolver.
legacy_dir = fullfile(temporary, 'legacy_manual_loopback');
mkdir(legacy_dir);
tx_diagnostics_dir = fullfile(plan.run_dir, 'data');
legacy_waveform = msiq.load_tx_waveform(plan.run_dir);
save(fullfile(legacy_dir, 'tx_waveform.mat'), '-struct', 'legacy_waveform', '-v7.3');
tx_legacy_files = {'tx_reference.mat','execution_receipt.json', ...
    'tx_manifest.mat'};
for k = 1:numel(tx_legacy_files)
    copyfile(fullfile(tx_diagnostics_dir, tx_legacy_files{k}), ...
        fullfile(legacy_dir, tx_legacy_files{k}));
end
copyfile(fullfile(diagnostics_dir, 'raw_capture.mat'), ...
    fullfile(legacy_dir, 'raw_capture.mat'));
cfg.instrument.scope.mock_raw_capture = short_raw_capture();
legacy_capture = msiq.traditional_rx('capture', [], struct( ...
    'run_dir', legacy_dir, 'cfg_override', cfg));
assert(strcmp(legacy_capture.status, 'captured_not_ready_for_demod'));
legacy_reuse = msiq.traditional_tx('awg_reuse', legacy_dir, ...
    struct('cfg_override', cfg));
assert(strcmp(legacy_reuse.status, 'reused'));
legacy_demod = msiq.traditional_rx('demod_capture', legacy_dir, struct());
assert(strcmp(legacy_demod.status, 'blocked'));
assert(~strcmp(legacy_demod.run_dir, legacy_dir));
assert(isfile(msiq.artifact_path(legacy_demod.run_dir, 'demod_result.mat')));

msiq.instruments.reset_audit();
cfg.instrument.scope.fail_stage = 'raw_read';
failed = false;
try
    msiq.traditional_rx('capture', [], struct( ...
        'run_dir', fullfile(temporary, 'failed_receiver_run'), 'tx_reference_bundle', portable_path, ...
        'cfg_override', cfg));
catch exception
    failed = strcmp(exception.identifier, 'msiq:instrument:MockRawReadFailure');
end
assert(failed);
assert(any(contains(audit_commands(), 'TRMD AUTO', 'IgnoreCase', true)));
assert(isfile(fullfile(rx_dir, 'fig_rx_dashboard.png')));
failed_info = Result_Update_Run_Info(fullfile(temporary, 'failed_receiver_run'), struct());
assert(strcmp(failed_info.status, 'failed'));
assert(isfile(fullfile(temporary, 'failed_receiver_run', 'summary.csv')));
note = 'raw VISA capture stays driver-free, restores TRMD AUTO, and blocks insufficient physical windows';
clear cleanup;
end

function note = test_mock_traditional_rdiv_comparison()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = traditional_mock_cfg(temporary, []);
msiq.instruments.reset_audit();

plan = msiq.traditional_rdiv_compare('rdiv_compare_plan', [], struct( ...
    'cfg_override', cfg, 'route', 'pair_a_ch1_ch2', ...
    'repeats_per_rdiv', 5, 'seed', 26072701, ...
    'amplitude_vpp', [0.2 0.2], 'offset_v', [0 0]));
assert(numel(plan.sequence) == 10);
assert(all(strcmpi({plan.sequence.rdiv}, ...
    {'DIV2','DIV4','DIV2','DIV4','DIV2','DIV4','DIV2','DIV4','DIV2','DIV4'})));
assert(plan.frame_repetitions == 1);
assert(plan.conditions(1).waveform_sample_count == 296593);
assert(plan.conditions(1).padded_sample_count == 296704);
assert(plan.conditions(2).waveform_sample_count == 148297);
assert(plan.conditions(2).padded_sample_count == 148352);
assert(all([plan.conditions.awg_raster_hz] == 65e9));
assert(strcmpi(plan.conditions(1).desired.dac_mode, 'FOUR'));
assert(strcmpi(plan.conditions(2).desired.dac_mode, 'FOUR'));
assert(isequal(plan.conditions(1).desired.channel_memory_modes, ...
    {'EXT','EXT','INT','INT'}));
assert(isequal(plan.conditions(2).desired.channel_memory_modes, ...
    {'EXT','EXT','INT','INT'}));
assert(contains(plan.required_confirmation, 'FORCE RDIV COMPARISON'));


result = msiq.traditional_rdiv_compare('rdiv_compare_apply', [], struct( ...
    'plan', plan, 'confirmation_phrase', plan.required_confirmation, ...
    'mock_hook', @comparison_mock_capture_hook));
assert(strcmpi(result.status, 'completed'));
assert(all(strcmpi({result.trials.status}, 'decoded')));
assert(all(strcmpi({result.trials.rdiv}, ...
    {'DIV2','DIV4','DIV2','DIV4','DIV2','DIV4','DIV2','DIV4','DIV2','DIV4'})));
assert(all(arrayfun(@(trial) trial.metrics.sync_ok, result.trials)));
assert(all(arrayfun(@(trial) isfinite(trial.metrics.pre_fec_bit_error_count), ...
    result.trials)));
assert(all(arrayfun(@(trial) isfinite(trial.metrics.post_fec_bit_error_count), ...
    result.trials)));
assert(isfile(result.dashboard_path));
assert_nonblank_dashboard(result.dashboard_path, 'rdiv');
assert(isfile(fullfile(result.diagnostics_dir, 'comparison_plan.json')));
assert(isfile(fullfile(result.diagnostics_dir, 'comparison_result.json')));
assert(isfile(fullfile(result.diagnostics_dir, 'comparison_metrics.csv')));
observations = Result_Read_Summary(plan.run_dir);
assert(size(observations,1) == numel(result.trials) + 2);
assert(isfile(fullfile(plan.run_dir,'summary.csv')));
for index = 1:numel(result.trials)
    trial = result.trials(index);
    tx_context = struct('run_dir', trial.tx_run_dir, ...
        'artifact_prefix', sprintf('%03d_%s_TX', trial.trial_index, trial.rdiv));
    rx_context = struct('run_dir', trial.rx_run_dir, ...
        'artifact_prefix', sprintf('%03d_%s_RX', trial.trial_index, trial.rdiv));
    assert(isfile(msiq.artifact_path(tx_context, 'fig_tx_dashboard.png')));
    assert(isfile(msiq.artifact_path(rx_context, 'fig_rx_dashboard.png')));
    assert(isequal(trial.awg_after_apply.outputs, [true true false false]));
end
history = audit_commands();
assert(nnz(contains(history, ':ABOR', 'IgnoreCase', true)) == 10);
assert(~any(contains(history, ':OUTPut3', 'IgnoreCase', true)));
assert(~any(contains(history, ':OUTPut4', 'IgnoreCase', true)));
final_state = result.final_stop.state;
assert(isequal(final_state.outputs, [false false false false]));
note = 'ten fixed DIV2/DIV4 mock trials decoded; one batch phrase, ten ABORs, and no CH3/CH4 output writes';
clear cleanup;
end

function cfg = comparison_mock_capture_hook(phase, index, cfg, plan)
if ~strcmpi(char(string(phase)), 'before_capture')
    return;
end
trial = plan.sequence(index);
trial_cfg = cfg;
divider = str2double(extractAfter(trial.rdiv, 'DIV'));
trial_cfg.awg.requested_rdiv = trial.rdiv;
trial_cfg.waveform.awg_sample_rate_hz = ...
    trial_cfg.waveform.master_sample_rate_hz / divider;
trial_cfg.waveform.awg_samples_per_symbol = ...
    trial_cfg.waveform.awg_sample_rate_hz / trial_cfg.waveform.symbol_rate_hz;
trial_cfg.waveform.decimation = divider;
trial_cfg.waveform.frame_repetitions = plan.frame_repetitions;
[waveforms, ~] = msiq.generate_waveforms(trial_cfg, plan.seed);
playback = awg_playback_waveforms(waveforms);
simulated = msiq.simulate_capture(playback, trial_cfg, 'A', struct( ...
    'snr_db', 42, 'prepend_samples', 2048, 'capture_repetitions',6, ...
    'rng_seed', 811 + index));
samples = simulated.samples;
sample_rate = simulated.sample_rate_hz;
time_axis = (0:size(samples,1)-1).'/sample_rate;
cfg.instrument.scope.mock_raw_capture = struct('channels', [ ...
    struct('channel', 'C1', 'samples', samples(:,1), ...
        'time_axis_s', time_axis, 'sample_rate_hz', sample_rate), ...
    struct('channel', 'C2', 'samples', samples(:,2), ...
        'time_axis_s', time_axis, 'sample_rate_hz', sample_rate)]);
end

function cfg = traditional_mock_cfg(project_root, raw_capture)
cfg = msiq.build_config('v2_traditional_wz');
cfg.project_root = project_root;
cfg.results_root = fullfile(project_root, 'results', 'manual_loopback');
cfg = attach_mock_instruments(cfg, []);
if nargin >= 2 && ~isempty(raw_capture)
    cfg.instrument.scope.mock_raw_capture = raw_capture;
end
end

function outcome = apply_traditional_plan(plan)
outcome = msiq.traditional_tx('awg_apply', [], struct('plan', plan, ...
    'confirmation_phrase', plan.required_confirmation));
end

function set_mock_outputs(cfg, channels, enabled)
session = msiq.instruments.open_session('awg', cfg.instrument.awg, 'query_only');
cleanup = onCleanup(@() msiq.instruments.close_session(session));
for channel = channels
    token = 'OFF';
    if enabled, token = 'ON'; end
    msiq.instruments.write_scpi(session, sprintf(':OUTPut%d %s', channel, token));
end
clear cleanup;
end

function commands = audit_commands()
history = msiq.instruments.get_command_history();
if isempty(history)
    commands = strings(0,1);
    return;
end
commands = string(cellfun(@(entry) entry.command, history, 'UniformOutput', false));
end

function raw = short_raw_capture()
codes = int8([0; 1; -2; 3; -4; 5; -6; 7]);
raw = struct('payloads', {{ ...
    synthetic_wavedesc_payload(codes, 0.02, 0.1, 1/16.25e9, -1e-9), ...
    synthetic_wavedesc_payload(-codes, 0.02, -0.05, 1/16.25e9, -0.5e-9)}});
end

function raw = repeated_scope_capture(plan)
simulated = msiq.simulate_capture(plan.waveforms, plan.cfg, 'A', struct( ...
    'snr_db', 42, 'prepend_samples', 2048, 'rng_seed', 811));
samples = [simulated.samples; simulated.samples];
sample_rate = simulated.sample_rate_hz;
time_axis = (0:size(samples,1)-1).'/sample_rate;
raw = struct('channels', [ ...
    struct('channel', 'C1', 'samples', samples(:,1), ...
        'time_axis_s', time_axis, 'sample_rate_hz', sample_rate), ...
    struct('channel', 'C2', 'samples', samples(:,2), ...
        'time_axis_s', time_axis, 'sample_rate_hz', sample_rate)]);
end

function yes = has_forbidden_bundle_fields(value)
forbidden = {'instrument','visa','resource','address','local_config'};
yes = false;
if isstruct(value)
    names = fieldnames(value);
    name_matches = contains(lower(string(names)), string(forbidden));
    if any(name_matches(:))
        yes = true;
        return;
    end
    for index = 1:numel(value)
        for field_index = 1:numel(names)
            if has_forbidden_bundle_fields(value(index).(names{field_index}))
                yes = true;
                return;
            end
        end
    end
elseif iscell(value)
    for index = 1:numel(value)
        if has_forbidden_bundle_fields(value{index})
            yes = true;
            return;
        end
    end
elseif ischar(value) || (isstring(value) && isscalar(value))
    text = lower(char(string(value)));
    yes = any(cellfun(@(item) contains(text, item), forbidden));
end
end

function note = test_traditional_dashboard_rendering()
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
cfg = msiq.build_config('v2_traditional_wz');
[waveforms, tx_ref] = msiq.generate_waveforms(cfg, 707);
playback = awg_playback_waveforms(waveforms);
raw = msiq.simulate_capture(playback, cfg, 'A', struct( ...
    'snr_db', 42, 'prepend_samples', 777, 'capture_repetitions',6, ...
    'rng_seed', 7071));
decoded = msiq.decode_capture(raw, tx_ref, cfg);
assert(decoded.pass && ~decoded.payload_reference_used_for_processing);
assert(~isempty(decoded.primary_equalizer.training_symbols_equalized));
assert(~isempty(decoded.primary_equalizer.service_symbols_before_tracking));
assert(~isempty(decoded.primary_equalizer.service_symbols_after_tracking));
assert(~isempty(decoded.primary_equalizer.tracking.phase_log));
assert(~isempty(decoded.primary_equalizer.tracking.amplitude_log));
assert(~isempty(decoded.primary_equalizer.tracking.error_log));
assert(~isempty(decoded.primary_streams(1).pre_tracking_symbols));
assert(~isempty(decoded.primary_streams(1).constellation_symbols));
overlap = raw.time_axes(end,1)-raw.time_axes(1,1);
validation = struct('ok', true, 'reason', '', ...
    'summary', struct('required_duration_s', 0.9*overlap, ...
    'pair_summaries', {{struct('overlap_duration_s', overlap)}}));
context = struct('route', struct('name', 'pair_a_ch1_ch2'), ...
    'desired', struct('dac_mode', 'FOUR', 'rdiv', 'DIV4', ...
    'raster_hz', 65e9, 'memory_mode', 'EXT'), ...
    'tx_ref', tx_ref, 'scope_status', struct('sample_rate_hz', 80e9));
path = fullfile(temporary, 'fig_rx_dashboard.png');

capture_only = struct('status', 'captured_ready_for_demod', ...
    'reason', '', 'pairs', struct([]));
details = msiq.plotting.rx_dashboard(path, raw, validation, context, capture_only);
assert(strcmp(details.status, 'captured_ready_for_demod') && ...
    details.decoded_pair_count == 0 && details.panel_count == 11);
assert_rx_unavailable_panels(details);
assert_nonblank_dashboard(path, 'rx');

blocked_validation = validation;
blocked_validation.ok = false;
blocked_validation.reason = 'insufficient_physical_time_window';
blocked = struct('status', 'blocked', ...
    'reason', blocked_validation.reason, 'pairs', struct([]));
details = msiq.plotting.rx_dashboard(path, raw, blocked_validation, context, blocked);
assert(strcmp(details.status, 'blocked') && details.decoded_pair_count == 0);
assert_rx_unavailable_panels(details);
assert_nonblank_dashboard(path, 'rx');

decoded_result = struct('status', 'decoded', 'pairs', ...
    struct('name', 'pair_a', 'status', 'decoded', 'decoded', decoded));
details = msiq.plotting.rx_dashboard(path, raw, validation, context, decoded_result);
assert(strcmp(details.status, 'decoded') && details.decoded_pair_count == 1);
assert(details.panel_count == 11 && details.axis_count == 13);
assert(isempty(details.layout.issues),strjoin(string(details.layout.issues),'; '));
assert_nonblank_dashboard(path, 'rx');

sync_failed = struct('status', 'failed', ...
    'reason', 'msiq:dsp:WzSyncFailed', 'pairs', struct([]));
details = msiq.plotting.rx_dashboard(path, raw, validation, context, sync_failed);
assert(strcmp(details.status, 'failed') && details.decoded_pair_count == 0);
assert_rx_unavailable_panels(details);
assert_nonblank_dashboard(path, 'rx');

capture_failed = struct('status', 'failed', ...
    'reason', 'capture_failed: mock scope failure', 'pairs', struct([]));
details = msiq.plotting.rx_dashboard(path, struct('channels', struct([])), ...
    struct('ok', false, 'reason', 'capture_failed', 'summary', struct()), ...
    context, capture_failed);
assert(strcmp(details.status, 'failed') && details.decoded_pair_count == 0);
assert_rx_unavailable_panels(details);
assert_nonblank_dashboard(path, 'rx');
note = 'RX eleven-panel dashboard covers capture-only, blocked, decoded, sync-failed, and capture-failed states';
clear cleanup;
end

function assert_rx_unavailable_panels(details)
assert(details.panel_count == 11 && details.axis_count == 13);
assert(isempty(details.layout.issues),strjoin(string(details.layout.issues),'; '));
assert(~any(details.stage_available) && all(details.constellation_counts == 0));
for panel_index = 3:11
    assert(~isempty(strtrim(strjoin(string(details.panel_texts{panel_index}(:)),' '))));
end
end

function payload = synthetic_wavedesc_payload(codes, gain, offset, interval, time_offset)
descriptor_length = uint32(346);
payload = zeros(double(descriptor_length) + numel(codes), 1, 'uint8');
payload = put_wavedesc_value(payload, 32, int16(0));
payload = put_wavedesc_value(payload, 34, int16(1));
payload = put_wavedesc_value(payload, 36, descriptor_length);
payload = put_wavedesc_value(payload, 60, uint32(numel(codes)));
payload = put_wavedesc_value(payload, 156, single(gain));
payload = put_wavedesc_value(payload, 160, single(offset));
payload = put_wavedesc_value(payload, 176, single(interval));
payload = put_wavedesc_value(payload, 180, double(time_offset));
payload(double(descriptor_length)+(1:numel(codes))) = typecast(codes(:), 'uint8');
end

function bytes = put_wavedesc_value(bytes, zero_offset, value)
encoded = typecast(value, 'uint8');
first = zero_offset + 1;
bytes(first:first+numel(encoded)-1) = encoded(:);
end

function bundle = strip_configurable_reference_fields(bundle)
bundle = remove_existing_fields(bundle, {'modulation_order', ...
    'frame_structure','rates','iq_calibration','dsp_config','parameter_hash'});
bundle.tx_ref = remove_existing_fields(bundle.tx_ref, ...
    {'modulation_order','modulation_label','configuration'});
bundle.tx_ref.frame = remove_existing_fields(bundle.tx_ref.frame, ...
    {'modulation_order','master_sample_rate_hz', ...
    'master_samples_per_symbol','awg_sample_rate_hz', ...
    'q_relative_delay_samples','invert_i','invert_q'});
end

function value = remove_existing_fields(value, names)
present = intersect(fieldnames(value), names);
if ~isempty(present)
    value = rmfield(value, present);
end
end

function note = test_mock_smoke_failure(cfg, failure_stage)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
[test_cfg, condition] = bench_test_config(cfg, temporary);
if strcmp(failure_stage,'capture')
    test_cfg.instrument.scope.fail_stage = 'capture';
else
    test_cfg.instrument.awg.fail_stage = failure_stage;
end
msiq.instruments.reset_audit();
failed = false;
try
    msiq.run_condition(test_cfg,condition,'single_dac_smoke');
catch
    failed = true;
end
assert(failed);
audit = msiq.instruments.get_audit();
assert(audit.shutdown_calls == 1 && audit.awg_output_mask == 0);
assert(audit.closes == 2 && audit.source_connections == 0 && ...
    audit.source_queries == 0 && audit.source_writes == 0 && ...
    audit.source_closes == 0);
runs = dir(fullfile(temporary,'measurement','*'));
runs = runs([runs.isdir] & ~ismember({runs.name},{'.','..'}));
assert(numel(runs) == 1);
    run_dir = fullfile(runs(1).folder,runs(1).name);
    info = jsondecode(fileread(msiq.artifact_path(run_dir,'run_info.json')));
    assert(strcmp(info.status,'failed'));
    assert(isfile(fullfile(run_dir,'overview.png')));
assert(numel(info.instruments) == 2 && ...
    ~any(strcmp({info.instruments.role},'signal_generator')));
assert(audit.max_awg_outputs_enabled <= 1);
note = sprintf('%s failure retained and closed AWG/scope with source untouched', ...
    failure_stage);
clear cleanup;
end

function note = test_mock_success_and_replay(cfg)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
test_cfg = cfg;
test_cfg.results_root = temporary;
test_cfg.waveform.frame_repetitions = 3;
test_cfg.safety.hardware_enabled = true;
test_cfg.safety.require_power_unit = false;
test_cfg.safety.test_mode = true;
test_cfg.safety.confirmation_granted = true;
test_cfg.experiment.minimum_passing_repeats = 1;

matrix = msiq.build_experiment_matrix(test_cfg);
condition = matrix.qualification(1);
condition.repetitions = 1;
condition.repeat_plan = condition.repeat_plan(1);
condition.power_unit_dbm = 0;
condition_cfg = msiq.apply_condition(test_cfg, condition);
[waveforms, ~] = msiq.generate_waveforms( ...
    condition_cfg, condition.repeat_plan.seed);
pair = condition.awg_slot_map(1).payload_pair;
if strcmp(pair, 'A')
    columns = 1:2;
else
    columns = 3:4;
end
samples = waveforms.master_dac_data(:,columns);
time_axis = (0:size(samples,1)-1).' / ...
    condition_cfg.waveform.master_sample_rate_hz;
mock_capture = struct('samples', samples, ...
    'time_axes', repmat(time_axis,1,size(samples,2)), ...
    'sample_rate_hz', condition_cfg.waveform.master_sample_rate_hz, ...
    'full_scale', 1);
test_cfg = attach_mock_instruments(test_cfg, mock_capture);

msiq.instruments.reset_audit();
outcome = msiq.run_condition(test_cfg, condition, 'hardware');
audit = msiq.instruments.get_audit();
assert(strcmp(outcome.status,'completed') && outcome.acceptance_pass);
assert(outcome.passing_repeats == 1 && all(outcome.repeat_pass));
assert(audit.driver_initializations == 1 && audit.shutdown_calls == 1);
info = jsondecode(fileread(msiq.artifact_path(outcome.run_dir,'run_info.json')));
assert(info.counts.executed == audit.captures);
assert(info.counts.succeeded == audit.captures && info.counts.failed == 0);

source_files = dir(fullfile(outcome.run_dir, 'data', '*.mat'));
source_names = string({source_files.name});
before = file_hashes(outcome.run_dir, source_names);
replay = msiq.replay_run(outcome.run_dir);
after = file_hashes(outcome.run_dir, source_names);
assert(isequal(before, after));
assert(replay.raw_files_modified == false);
assert(numel(replay.records) == 2);
assert(all([replay.records.post_ber] == 0));
assert(all([replay.records.bler] == 0));
assert(all([replay.records.parity]));
assert(all(cellfun(@isfile, struct2cell(replay.paths))));
note = sprintf(['UP%d mock run passed; replay kept %d MAT SHA256 values ', ...
    'unchanged'], condition.up, numel(source_names));
clear cleanup;
end

function note = test_mock_failure(cfg, failure_stage)
temporary = tempname;
mkdir(temporary);
cleanup = onCleanup(@() remove_temp(temporary));
test_cfg = cfg;
test_cfg.results_root = temporary;
test_cfg.waveform.frame_repetitions = 1;
test_cfg.safety.hardware_enabled = true;
test_cfg.safety.require_power_unit = false;
test_cfg.safety.test_mode = true;
test_cfg.safety.confirmation_granted = true;
test_cfg.experiment.minimum_passing_repeats = 1;
dummy_time = (0:127).'/test_cfg.waveform.master_sample_rate_hz;
dummy_capture = struct('samples',zeros(128,2), ...
    'time_axes',[dummy_time,dummy_time], ...
    'sample_rate_hz',test_cfg.waveform.master_sample_rate_hz);
test_cfg = attach_mock_instruments(test_cfg, dummy_capture);
if strcmp(failure_stage,'connect_scope')
    test_cfg.instrument.scope.fail_stage = 'connect_scope';
elseif strcmp(failure_stage,'capture')
    test_cfg.instrument.scope.fail_stage = 'capture';
else
    test_cfg.instrument.scope.fail_stage = 'dsp';
end
matrix = msiq.build_experiment_matrix(test_cfg);
condition = matrix.conditions(1);
condition.repetitions = 1;
condition.repeat_plan = condition.repeat_plan(1);
condition.power_unit_dbm = 0;
msiq.instruments.reset_audit();
try
    msiq.run_condition(test_cfg,condition,'hardware');
catch
end
audit = msiq.instruments.get_audit();
assert(audit.shutdown_calls == 1);
assert(audit.closes >= 1);
if ~strcmp(failure_stage,'connect_scope')
    assert(audit.captures >= 1);
end
note = sprintf('%s failure retained and triggered one safe shutdown',failure_stage);
records = dir(fullfile(temporary,'measurement','*','data','run_info.json'));
assert(numel(records) == 1);
info = jsondecode(fileread(fullfile(records(1).folder,records(1).name)));
if strcmp(failure_stage,'connect_scope')
    assert(strcmp(info.status,'failed'));
else
    assert(strcmp(info.status,'completed_with_failures'));
end
assert(info.counts.executed == audit.captures);
assert(info.counts.succeeded + info.counts.failed == info.counts.executed);
clear cleanup;
end

function cfg = attach_mock_instruments(cfg, mock_capture)
cfg.instrument.awg = struct('mock',true, ...
    'mock_idn','MOCK,M8195A,0,2.0','idn_contains','M8195A');
cfg.instrument.scope = struct('mock',true, ...
    'mock_idn','MOCK,LECROY,0,2.0','idn_contains','LECROY', ...
    'channels',{{'C1','C2'}},'mock_vertical_scale_v_per_div',0.1);
if nargin >= 2 && ~isempty(mock_capture)
    cfg.instrument.scope.mock_capture = mock_capture;
end
cfg.instrument.signal_generator = struct('mock',true, ...
    'mock_idn','MOCK,E8257D,0,2.0','idn_contains','E8257D');
end

function [cfg, condition] = bench_test_config(cfg, results_root)
cfg.results_root = results_root;
cfg.waveform.frame_repetitions = 1;
cfg.safety.hardware_enabled = true;
cfg.safety.require_power_unit = false;
cfg.safety.test_mode = true;
cfg.safety.confirmation_granted = true;
sample_count = 4096;
sample_rate = cfg.waveform.master_sample_rate_hz;
time_axis = (0:sample_count-1).'/sample_rate;
samples = 0.05*sin(2*pi*cfg.waveform.if_center_hz*time_axis);
mock_capture = struct('samples',samples,'time_axes',time_axis, ...
    'sample_rate_hz',sample_rate,'full_scale',1);
cfg = attach_mock_instruments(cfg,mock_capture);
cfg.instrument.awg.smoke_amplitude_vpp = 0.02;
cfg.instrument.scope.channels = {'C1'};
cfg.instrument.scope.smoke_channel = 'C1';
cfg.instrument.scope.mock_vertical_scale_v_per_div = 0.1;
cfg.instrument.manual_setup = struct( ...
    'direct_electrical_output_only',true,'wiring_verified',true, ...
    'protection_attenuation_db',20, ...
    'scope_vertical_scale_v_per_div',0.1,'notes','mock validation');
matrix = msiq.build_experiment_matrix(cfg);
condition = first_dual_condition(matrix);
condition.repetitions = 1;
condition.repeat_plan = condition.repeat_plan(1);
condition.power_unit_dbm = 0;
end

function condition = first_dual_condition(matrix)
index = find(strcmp({matrix.conditions.architecture},'dual_iq_mimo'),1);
assert(~isempty(index));
condition = matrix.conditions(index);
end

function condition = first_scalar_condition(matrix)
index = find(strcmp({matrix.conditions.architecture}, ...
    'single_complex_stream'),1);
assert(~isempty(index));
condition = matrix.conditions(index);
end

function count = summary_data_rows(path)
lines = readlines(path);
lines = lines(strlength(lines) > 0);
count = max(0,numel(lines)-2);
end

function header = summary_header(path)
fid = fopen(path,'r','n','UTF-8');
assert(fid >= 0);
cleanup = onCleanup(@() fclose(fid));
header = fgetl(fid);
clear cleanup;
end

function hashes = file_hashes(directory, names)
hashes = strings(size(names));
for k = 1:numel(names)
    hashes(k) = string(compute_file_sha256( ...
        msiq.artifact_path(directory, char(names(k)))));
end
end

function assert_nonblank_dashboard(path, layout)
if nargin < 2 || isempty(layout)
    layout = 'standard';
end
listing = dir(path);
assert(numel(listing) == 1 && listing.bytes > 50000);
metadata = imfinfo(path);
if strcmpi(char(string(layout)),'rx')
    assert(metadata.Width >= 1440 && metadata.Height >= 810);
else
    assert(metadata.Width >= 2000 && metadata.Height >= 1000);
end
ratio = double(metadata.Width)/double(metadata.Height);
switch lower(char(string(layout)))
    case 'tx'
        assert(abs(ratio-1) < 0.01);
    case 'rx'
        assert(abs(ratio-16/9) < 0.01);
    case 'rdiv'
        assert(abs(ratio-2100/1400) < 0.01);
    otherwise
        assert(ratio >= 1.60 && ratio <= 1.90);
end
pixels = imread(path);
intensity = mean(double(pixels),3);
assert(mean(intensity(:) < 248) > 0.01);
artifact_dir = getenv('MSIQ_VALIDATION_ARTIFACTS');
if ~isempty(artifact_dir)
    if ~isfolder(artifact_dir), mkdir(artifact_dir); end
    existing = dir(fullfile(artifact_dir,[char(layout),'_*.png']));
    copyfile(path,fullfile(artifact_dir, ...
        sprintf('%s_%02d.png',char(layout),numel(existing)+1)));
end
end

function note = test_v1_golden()
path = ['D:\BaiduSyncdisk\Program\100Gbps1km\experiments\20260610_bench\', ...
    '221328_rx_LDPC_r0p90__rx_IQMIMO_', ...
    '16QAM_12.5GBd_IF7.5GHz_115GHz_1km_16QAM_IQMIMO'];
if ~isfile(fullfile(path, 'rx_record.mat'))
    error('validation:skip', ...
        'V1 golden record is unavailable locally: %s', path);
end
audit = msiq.audit_v1_golden(path);
assert(audit.all_streams_pass && audit.stream_count == 2);
assert(all([audit.streams.block_count] == 5));
assert(all([audit.streams.block_error_count] == 0));
assert(all([audit.streams.bler] == 0));
assert(all([audit.streams.parity_converged]));
assert(all([audit.streams.post_fec_ber] == 0));
note = sprintf('V1 1 km: pre-BER %.4g/%.4g, 5 blocks/stream, BLER 0', ...
    audit.streams(1).pre_fec_ber,audit.streams(2).pre_fec_ber);
end

function note = test_equal_rate_comparison()
% Keep the comparison under the same temporary-result and zero-I/O gate.
audit_before = msiq.instruments.reset_audit(); %#ok<NASGU>
result = msiq.run_equal_rate_comparison('validate');
audit = msiq.instruments.get_audit();
assert(result.pass);
assert(all(struct2array(audit) == 0));
rate = result.matched.fairness.iqmimo_unique_net_information_rate_bps;
assert(abs(rate - 3.9852649904752288e9) < 1e3);
note = sprintf('equal-rate SC/IQ-MIMO; unique net rate %.9f Gbit/s; zero instrument I/O', ...
    rate/1e9);
end

function entry = run_case(name, callback)
start = tic;
msiq.validation_artifacts('begin',name);
try
    note = callback();
    entry = pass_entry(name,toc(start));
    entry.Note = string(note);
catch exception
    if strcmp(exception.identifier, 'validation:skip')
        entry = skip_entry(name, exception.message);
    else
        entry = fail_entry(name,exception);
    end
    entry.Seconds = toc(start);
end
retained = msiq.validation_artifacts('finish',entry.Status == "FAIL",char(entry.Note));
if ~isempty(retained)
    entry.Note = entry.Note + " | retained: " + strjoin(string(retained),", ");
end
fprintf('[%s] %s (%.2fs) %s\n',entry.Status,entry.Name,entry.Seconds,entry.Note);
end

function entry = pass_entry(name, seconds)
entry = empty_entry();
entry.Name = string(name);
entry.Status = "PASS";
entry.Seconds = seconds;
entry.Note = "";
end

function entry = fail_entry(name, exception)
entry = empty_entry();
entry.Name = string(name);
entry.Status = "FAIL";
entry.Seconds = 0;
location = '';
if ~isempty(exception.stack)
    location = sprintf(' at %s:%d', exception.stack(1).name, ...
        exception.stack(1).line);
end
entry.Note = string(sprintf('%s: %s%s', exception.identifier, ...
    exception.message, location));
end

function entry = skip_entry(name, note)
entry = empty_entry();
entry.Name = string(name);
entry.Status = "SKIP";
entry.Note = string(note);
end

function entry = empty_entry()
entry = struct('Name',"",'Status',"",'Seconds',0,'Note',"");
end

function remove_temp(path)
if isfolder(path) && startsWith(path,tempdir)
    if msiq.validation_artifacts('defer',path), return; end
    rmdir(path,'s');
end
end

function note=if_validation_note(callback)
result=callback();
if ischar(result)||isstring(result), note=char(result); return; end
assert(result.ok,'IF component validation failed.');
note='IF component offline checks passed';
end
