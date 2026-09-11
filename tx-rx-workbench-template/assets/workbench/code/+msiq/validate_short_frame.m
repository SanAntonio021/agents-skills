function note = validate_short_frame()
%VALIDATE_SHORT_FRAME Focused, hardware-free short-code integration checks.
root = msiq.project_root();
msiq.instruments.reset_audit();
cfg = msiq.short_frame_config();
contracts(cfg);
options = struct('cfg_override', cfg, 'symbol_rate_hz', 65e9/15, ...
    'rate_authority', 'symbol_rate', 'rdiv', 'DIV4', 'frame_repetitions', 1, ...
    'memory_mode','EXT','normalization_mode','legacy_peak_scale', ...
    'peak_scale',0.8,'q_relative_delay_samples',0,'invert_i',false,'invert_q',false);
plan = msiq.traditional_tx('preview_plan', [], options);
assert(plan.tx_ref.frame.symbol_count == 14958);
assert(plan.tx_ref.frame.training_length == 2048);
assert(numel(plan.tx_ref.frame.pilot_positions_service) == 380);
assert(numel(plan.tx_ref.frame.payload_positions_service) == 12150);
assert(size(plan.waveforms.master_dac_data, 1) == 224370);
assert(size(plan.waveforms.awg_dac_data, 1) == 56093);
assert(plan.tx_ref.frame.awg_padded_waveform_length == 56192);
reference = plan.tx_ref.pairs(1).metrics_only(1).fec;
assert(reference.block_count == 3 && numel(reference.info_bits) == 43200);
blocks = reshape(reference.coded_bits, 16200, 3);
assert(~isequal(blocks(:,1), blocks(:,2)) && ~isequal(blocks(:,2), blocks(:,3)));
assert(~isfield(plan.tx_ref.fec_config, 'matrix_file'));

% The old JSON and ordinary preview must still generate one normal codeword.
normal = msiq.build_config('v2_traditional_wz');
normal_options = options;
normal_options.cfg_override = normal;
normal_plan = msiq.traditional_tx('preview_plan', [], normal_options);
assert(normal_plan.tx_ref.frame.symbol_count == 19135);
assert(normal_plan.tx_ref.frame.awg_padded_waveform_length == 71808);
assert(strcmp(normal_plan.tx_ref.fec_config.frame_type, 'normal'));
assert(~isfield(normal_plan.tx_ref.waveform_config, 'fec'));

run = Result_Create_Run(struct('ProjectRoot', root, 'RunType', 'simulation', ...
    'NameParts', {{'int_reference_replay'}}, 'ExecutionMode', 'simulation', ...
    'EntryPoint', 'run_v2_validation(''short_frame'')', 'RetentionMode', 'full', ...
    'Counts', struct('planned',3)));
diary(fullfile(run.DataDir, 'matlab.log'));
log_cleanup = onCleanup(@() diary('off'));
headers = {'case_id','playback_GSa_s','injected_sro_ppm','estimated_sro_ppm', ...
    'evm_percent','pre_fec_ber','post_fec_ber','blocks','sync_ok', ...
    'padded_samples','padding_samples','period_us','pass'};
units = {'-','GSa/s','ppm','ppm','%','-','-','-','-','samples','samples','us','-'};
Result_Summary_Initialize(run, headers, units);
save(fullfile(run.DataDir, 'tx_plan.mat'), 'plan', '-v7.3');
copyfile(fullfile(root, 'code', '+msiq', 'validate_short_frame.m'), ...
    fullfile(run.DataDir, 'validate_short_frame.m'));
rates = [16.25e9, 16.25e9, 65e9];
offsets = [0, 10, 0];
scope_rate = 40e9;
capture_count = round(50e-6*scope_rate);
passed = false(1,3);
fig = figure('Visible','off','Color','w','Position',[80 80 1400 480]);
fig_cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig,1,3,'TileSpacing','compact','Padding','compact');
try
    for k = 1:3
        fprintf('CASE %d: playback %.2f GSa/s, SRO %+g ppm\n', k, rates(k)/1e9, offsets(k));
        case_options = options;
        if k == 3, case_options.memory_mode = 'INT'; end
        case_plan = msiq.traditional_tx('preview_plan',[],case_options);
        case_cfg = case_plan.cfg;
        tx_ref = case_plan.tx_ref;
        prepared = case_plan.download;
        assert(isequaln(case_plan.waveforms.master_dac_data,plan.waveforms.master_dac_data));
        samples = round(127*[prepared.channel_data{:}])/127;
        count = size(samples,1);
        period = count/rates(k);
        assert(abs(period-56192/16.25e9) < 1e-15);
        if k == 3, assert(count <= 262144 && count == 224768); end
        [p,q] = rat(scope_rate/rates(k),1e-12);
        playback = plan.waveforms;
        % Capture synthesis only; receiver resampling and SRO remain unchanged.
        [playback.master_dac_data, capture_filter] = resample( ...
            repmat(samples,ceil(50e-6/period)+2,1),p,q,40,10);
        capture_resampling = struct('p',p,'q',q,'n',40,'beta',10, ...
            'input_rate_hz',rates(k),'output_rate_hz',scope_rate, ...
            'filter_coefficients',capture_filter);
        playback.master_sample_rate_hz = scope_rate;
        simulation = struct('snr_db',Inf,'cfo_hz',0,'sro_ppm',offsets(k), ...
            'channel_matrix',eye(2),'image_matrix',zeros(2), ...
            'crop_start_samples',round(0.35*period*scope_rate));
        raw = msiq.simulate_capture(playback,case_cfg,'A',simulation);
        raw.samples = raw.samples(1:capture_count,:);
        raw.time_axes = raw.time_axes(1:capture_count,:);
        raw = rmfield(raw,'simulation_options');
        % Exercise receiver-side code restoration starting from the long default.
        receiver_cfg = case_cfg;
        receiver_cfg.fec = normal.fec;
        expect_error(@() msiq.decode_capture(raw,tx_ref,receiver_cfg), ...
            'msiq:decode:ConfigurationMismatch');
        receiver_cfg = msiq.fec.apply_reference(receiver_cfg,tx_ref);
        prefix = sprintf('case_%d',k);
        bundle = struct('route',case_plan.route,'desired',case_plan.desired, ...
            'tx_ref',tx_ref,'reference_payload_policy','metrics_only', ...
            'execution',struct('status','applied','simulated',true), ...
            'dsp_config',struct('waveform',case_cfg.waveform,'receiver',case_cfg.receiver));
        bundle_path = fullfile(run.DataDir,[prefix '_bundle.mat']);
        save(bundle_path,'bundle');
        simulated_raw = raw;
        raw = struct('simulation',true,'channels', [ ...
            struct('channel','C1','samples',simulated_raw.samples(:,1), ...
                'time_axis_s',simulated_raw.time_axes(:,1),'sample_rate_hz',scope_rate), ...
            struct('channel','C2','samples',simulated_raw.samples(:,2), ...
                'time_axis_s',simulated_raw.time_axes(:,2),'sample_rate_hz',scope_rate)]);
        save(fullfile(run.DataDir,[prefix '_raw_capture.mat']),'raw','-v7.3');
        replay = msiq.traditional_rx('demod_capture',run.OutputDir, ...
            struct('cfg_override',normal,'tx_reference_bundle',bundle_path,'artifact_prefix',prefix));
        assert(strcmp(replay.status,'decoded'));
        decoded = replay.pairs(1).decoded;
        stream = decoded.primary_streams(1);
        sync = decoded.synchronization;
        checks = [decoded.sync_ok, decoded.pass, stream.block_count == 3, ...
            stream.pre_fec_ber == 0, stream.post_fec_ber == 0, ...
            abs(sync.sro_ppm-offsets(k)) < 3, ...
            sync.sro_raw_correction.applied == (offsets(k) ~= 0), ...
            ~sync.sro_low_rate_resample_applied, ...
            ~decoded.payload_reference_used_for_processing];
        passed(k) = all(checks);
        Result_Update_Run_Info(run, struct('counts', struct('executed',k, ...
            'succeeded',nnz(passed(1:k)), 'failed',nnz(~passed(1:k)))));
        Result_Summary_Append(run, {k,rates(k)/1e9,offsets(k),sync.sro_ppm, ...
            100*stream.evm_rms,stream.pre_fec_ber,stream.post_fec_ber, ...
            stream.block_count,decoded.sync_ok,count, ...
            count-prepared.source_sample_counts(1),period*1e6,passed(k)});
        save(fullfile(run.DataDir,sprintf('case_%d.mat',k)), ...
            'case_plan','case_cfg','receiver_cfg','tx_ref','simulation', ...
            'capture_resampling','decoded','checks','-v7.3');
        points = stream.constellation_symbols(:);
        csv = fullfile(run.DataDir,sprintf('constellation_%d.csv',k));
        fid = Result_Open_File_Retry(csv,'w');
        file_cleanup = onCleanup(@() fclose(fid));
        fprintf(fid,'I,Q\n');
        fprintf(fid,'%.15g,%.15g\n',[real(points),imag(points)].');
        clear file_cleanup;
        points_table = readtable(csv);
        ax = nexttile(layout);
        scatter(ax,points_table.I,points_table.Q,3,'.');
        axis(ax,'equal'); xlim(ax,[-1.25 1.25]); ylim(ax,[-1.25 1.25]); grid(ax,'on');
        xlabel(ax,'I'); ylabel(ax,'Q');
        title(ax,sprintf('%.2f GSa/s, SRO %+g ppm\nEVM %.3f%%, BER %.2g / %.2g', ...
            rates(k)/1e9,offsets(k),100*stream.evm_rms,stream.pre_fec_ber,stream.post_fec_ber));
        fprintf('CASE %d: pass=%d, EVM=%.6f%%, SRO=%.6f ppm, blocks=%d\n', ...
            k,passed(k),100*stream.evm_rms,sync.sro_ppm,stream.block_count);
    end
    title(layout,'Short-frame software check: 16QAM, 4.333 GBd, 3 x short 8/9');
    exportgraphics(fig,fullfile(run.OutputDir,'constellations.png'),'Resolution',200);
    match_comparison_spectra(run);
    audit = msiq.instruments.get_audit();
    save(fullfile(run.DataDir,'audit.mat'),'audit');
    assert(all(struct2array(audit) == 0));
    assert(all(passed),'msiq:shortFrame:Failed','Inspect the saved short-frame results.');
    Result_Finalize_Run(run,'completed');
catch exception
    Result_Finalize_Run(run,'completed_with_failures');
    rethrow(exception);
end
note = sprintf('Contracts and 3/3 waveform cases passed; no hardware I/O. %s',run.OutputDir);
fprintf('%s\n',note);
end

function match_comparison_spectra(run)
% Freeze the same display scale across this three-case comparison only.
spectra = cell(2,3);
limits = [Inf,-Inf];
for k = 1:3
    path = fullfile(run.DataDir,sprintf('case_%d_fig_rx_dashboard.fig',k));
    fig = openfig(path,'invisible');
    aa = comparison_spectrum_axes(fig);
    captured = load(fullfile(run.DataDir,sprintf('case_%d_raw_capture.mat',k)),'raw');
    assert(numel(captured.raw.channels)==2);
    for ch = 1:2
        ln = findall(aa(ch),'Type','line');
        ln = ln(arrayfun(@(v) numel(v.XData)>100,ln));
        assert(numel(ln)==1);
        spectra{ch,k} = [ln.XData(:),ln.YData(:)];
        % Check both plotted channels against their saved physical samples.
        record=captured.raw.channels(ch);
        assert(strcmp(record.channel,sprintf('C%d',ch)));
        fs=1/median(diff(record.time_axis_s(:)));
        assert(abs(fs/40e9-1)<1e-6);
        values=double(record.samples(:));
        nfft=min(65536,2^floor(log2(numel(values))));
        [density,frequency]=pwelch(values,hann(nfft),floor(nfft/2),nfft,fs,'onesided');
        expected=10*log10(max(density/50*1000,realmin));
        assert(numel(ln.XData)==numel(frequency));
        assert(max(abs(ln.XData(:)-frequency/1e9))<1e-9);
        assert(max(abs(ln.YData(:)-expected))<1e-9);
        limits = [min(limits(1),min(ln.YData)),max(limits(2),max(ln.YData))];
    end
    close(fig);
end
limits = [floor(limits(1)/20)*20,ceil(limits(2)/20)*20];
for k = 1:3
    path = fullfile(run.DataDir,sprintf('case_%d_fig_rx_dashboard.fig',k));
    fig = openfig(path,'invisible');
    % Keep the dashboard's native canvas; its eleven panels use pixel layout.
    aa = comparison_spectrum_axes(fig);
    for ax = aa(:).'
        set(ax,'XLim',[0 20],'YLim',limits,'XTick',0:4:20,'YTick',limits(1):20:limits(2), ...
            'XTickLabelMode','auto','YTickLabelMode','auto');
    end
    savefig(fig,path);
    exportgraphics(fig,fullfile(run.OutputDir,sprintf('case_%d_fig_rx_dashboard.png',k)),'Resolution',200);
    close(fig);
    fig = openfig(path,'invisible');
    aa = comparison_spectrum_axes(fig);
    for ch = 1:2
        ax=aa(ch);
        assert(isequal(ax.XLim,[0 20]) && isequal(ax.YLim,limits));
        assert(isequal(ax.XTick,0:4:20)&&isequal(ax.YTick,limits(1):20:limits(2)));
        assert(strcmp(ax.XTickLabelMode,'auto')&&strcmp(ax.YTickLabelMode,'auto'));
        ln=findall(ax,'Type','line');
        ln=ln(arrayfun(@(v)numel(v.XData)>100,ln));
        assert(numel(ln)==1&&isequal([ln.XData(:),ln.YData(:)],spectra{ch,k}));
    end
    close(fig);
end
labels = {'DIV4, 0 ppm','DIV4, +10 ppm (regression)','INT, 0 ppm'};
fig = figure('Visible','off','Color','w','Position',[50 50 1350 640]);
tiledlayout(fig,2,3,'Padding','compact','TileSpacing','compact');
for ch = 1:2
    for k = 1:3
        data = spectra{ch,k};
        csv = fullfile(run.DataDir,sprintf('spectrum_%d_%d.csv',k,ch));
        fid = Result_Open_File_Retry(csv,'w');
        fprintf(fid,'frequency_GHz,PSD_dBm_per_Hz\n');
        fprintf(fid,'%.17g,%.17g\n',data.'); fclose(fid);
        data = readmatrix(csv);
        ax = nexttile;
        plot(ax,data(:,1),data(:,2),'LineWidth',0.65);
        set(ax,'XLim',[0 20],'YLim',limits,'XTick',0:4:20,'YTick',limits(1):20:limits(2));
        grid(ax,'on'); xlabel(ax,'Frequency (GHz)'); ylabel(ax,'PSD (dBm/Hz)');
        title(ax,sprintf('%s | %s',labels{k},char('I'+8*(ch-1))));
    end
end
savefig(fig,fullfile(run.DataDir,'comparison_spectra.fig'));
exportgraphics(fig,fullfile(run.OutputDir,'comparison_spectra.png'),'Resolution',300);
close(fig);
Result_Atomic_Write_Json(fullfile(run.DataDir,'spectrum_axes_check.json'), ...
    struct('xlim_GHz',[0 20],'ylim_dBm_Hz',limits,'ytick',limits(1):20:limits(2), ...
    'dashboard_readback_passed',true,'raw_spectrum_match_passed',true, ...
    'capture_channels',{{'C1','C2'}},'capture_rate_hz',40e9));
end

function aa=comparison_spectrum_axes(fig)
% Current RX labels use the physical unit directly, without a PSD prefix.
aa=findall(fig,'Type','axes');
aa=aa(arrayfun(@(ax) contains(string(ax.YLabel.String),'dBm/Hz'),aa));
assert(numel(aa)==2,'msiq:shortFrame:SpectrumAxes', ...
    'Expected exactly two channel spectra in dBm/Hz.');
[~,order]=sort(arrayfun(@(ax) ax.Position(2),aa),'descend');
aa=aa(order);
end

function contracts(cfg)
normal = msiq.build_config('v2_traditional_wz');
fec = msiq.fec.build(normal);
assert(isequal(fec.parity_check_matrix,dvbs2ldpc(9/10)));
assert(fec.codeword_length == 64800 && fec.info_length == 58320);
short = msiq.fec.build(cfg);
assert(short.codeword_length == 16200 && short.info_length == 14400);
bad = cfg;
bad.fec.rate_numerator = 9; bad.fec.rate_denominator = 10;
expect_error(@() msiq.build_config(bad),'msiq:config:FecLocked');
bad = cfg; bad.fec.matrix_file = fullfile(tempdir,'missing-msiq-matrix.mat');
expect_error(@() msiq.fec.build(bad),'msiq:fec:ShortMatrixMissing');
[bits,ref] = msiq.fec.encode_payload(cfg,6090901,3);
llr = (1-2*double(bits)).*(1-2*double(ref.scramble_bits))*20;
decoded = msiq.fec.decode_soft(llr,ref,cfg);
assert(decoded.block_count == 3 && decoded.post_fec_ber == 0 && decoded.parity_converged);
tail = msiq.fec.decode_soft(llr(1:end-1),ref,cfg);
assert(tail.block_count == 2 && tail.incomplete_tail_bits == 16199);
expect_error(@() msiq.fec.decode_soft(llr,ref,normal),'msiq:fec:ReferenceMismatch');
legacy = msiq.fec.apply_reference(normal,struct());
assert(isequal(legacy,normal));
end

function expect_error(action, identifier)
try
    action();
catch exception
    assert(strcmp(exception.identifier,identifier),exception.message);
    return;
end
error('msiq:shortFrame:MissingError','Expected %s.',identifier);
end
