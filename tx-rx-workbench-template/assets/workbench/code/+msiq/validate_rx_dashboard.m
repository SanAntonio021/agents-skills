function note = validate_rx_dashboard()
%VALIDATE_RX_DASHBOARD Hardware-free RX panel data, states, and geometry.
own_scope = ~msiq.validation_artifacts('active');
if own_scope, msiq.validation_artifacts('begin','rx_eleven_panel_data_and_layout'); end
try
    output_dir = msiq.validation_artifacts('directory');
    mkdir(fullfile(output_dir,'data'));
    msiq.instruments.reset_audit();
    validate_tracking_statistics();
    validate_payload_stages();
    orders = [4 16 64];
    dimensions = {[1440 810],[1920 1080],[1440 810]};
    for index = 1:numel(orders)
        [raw,validation,context,result] = fixture(orders(index));
        context.plot_options.figure_size = dimensions{index};
        if orders(index) == 16
            raw.channels(1).channel = 'C3';
            raw.channels(2).channel = 'C4';
            context.scope_status.channels(1).name = 'C3';
            context.scope_status.channels(2).name = 'C4';
            context.scope_status.channels(1).impedance_ohm = NaN;
            context.scope_status.channels(2).impedance_ohm = NaN;
            context.scope_status.channels(2).bandwidth_limit_hz = NaN;
        end
        path = fullfile(output_dir,sprintf('rx_%dqam.png',orders(index)));
        details = msiq.plotting.rx_dashboard(path,raw,validation,context,result);
        assert_export(path,details,dimensions{index});
        assert(strcmp(details.status,'decoded') && details.decoded_pair_count == 1);
        assert(details.modulation_order == orders(index));
        assert(details.reference_point_count == orders(index));
        if orders(index) == 4
            assert(contains(details.figure_title,'QPSK'));
        else
            assert(contains(details.figure_title,sprintf('%dQAM',orders(index))));
        end
        assert(all(details.stage_available));
        payload_count = numel(context.tx_ref.frame.payload_positions_service);
        assert(isequal(details.constellation_counts,repmat(payload_count,1,4)));
        assert(all([details.channels.sample_count] == [8192 12288]));
        assert(max(abs([details.channels.sample_rate_hz]-[8e9 12e9])) < 1e3);
        assert(abs(details.channels(1).frequency_limit_hz-1e9) < 1);
        assert(max(abs(details.channels(1).voltage_limits-[-0.48 0.32])) < 1e-12);
        for channel_index = 1:2
            assert(strcmp(details.channels(channel_index).name,raw.channels(channel_index).channel));
            channel = details.channels(channel_index);
            assert(numel(channel.voltage_ticks) >= 2 && numel(channel.voltage_ticks) <= 3);
            span = diff(channel.voltage_limits);
            assert(all(diff(channel.voltage_ticks) >= span/2-1e-10*span));
        end
        if orders(index) == 16
            assert(all([details.channels.impedance_ohm] == 50));
            assert(all(isfinite([details.channels.power_dbm])));
            assert(all([details.channels.inband_power_available]));
            assert(all(isfinite([details.channels.inband_power_dbm])));
            assert(contains(panel_text(details,2),'带内功率'));
            assert(abs(details.channels(2).frequency_limit_hz-6e9) < 1e3);
            assert(~details.channels(2).bandwidth_known);
        else
            assert(all([details.channels.impedance_ohm] == 50));
            assert(all(isfinite([details.channels.power_dbm])));
            assert(all([details.channels.inband_power_available]));
            assert(all(isfinite([details.channels.inband_power_dbm])));
            assert(contains(panel_text(details,2),'带内功率'));
            expected_power=10*log10(mean(raw.channels(1).samples.^2)/50*1000);
            assert(abs(details.channels(1).inband_power_dbm-expected_power)<.2);
            assert(max(abs(details.channels(1).inband_frequency_limits_hz-[0 1e9]))<1e3);
            assert(abs(details.channels(2).frequency_limit_hz-4e9) < 1);
        end
        error_text = panel_text(details,11);
        assert(~details.tracking_error.rejection_visible);
        assert(~contains(error_text,'拒绝更新'));
        assert(~contains(error_text,'参与更新'));
    end

    [raw,validation,context,result] = fixture(16);
    context.plot_options.figure_size = [1440 810];
    eq = result.pairs.decoded.primary_equalizer;
    eq = rmfield(eq,'service_symbols_before_equalization');
    result.pairs.decoded.primary_equalizer = eq;
    path = fullfile(output_dir,'rx_missing_stage.png');
    details = msiq.plotting.rx_dashboard(path,raw,validation,context,result);
    assert_export(path,details,[1440 810]);
    assert(isequal(logical(details.stage_available),[false true true true]));
    assert(details.constellation_counts(1) == 0);
    assert(~isempty(details.stages_info.stage_reasons{1}));
    assert(~isempty(strtrim(panel_text(details,7))));

    [raw,validation,context,result] = fixture(16);
    context.plot_options.figure_size = [1440 810];
    tracking = result.pairs.decoded.primary_equalizer.tracking;
    tracking.error_log(101) = NaN;
    tracking.update_count = tracking.update_count-1;
    tracking.rejected_count = 1;
    result.pairs.decoded.primary_equalizer.tracking = tracking;
    path = fullfile(output_dir,'rx_rejected_update.png');
    details = msiq.plotting.rx_dashboard(path,raw,validation,context,result);
    assert_export(path,details,[1440 810]);
    assert(details.tracking_error.rejection_visible);
    assert(details.tracking_error.rejected_count == 1);
    assert(contains(panel_text(details,11),'拒绝更新'));
    assert(details.tracking_error.rejected_fraction > 0);

    [raw,validation,context,result] = fixture(16);
    context.plot_options.figure_size = [1440 810];
    context.cfg.waveform.if_center_hz = 2.5e9;
    context.scope_status.channels(2).impedance_ohm = 75;
    path = fullfile(output_dir,'rx_nonzero_if_power.png');
    details = msiq.plotting.rx_dashboard(path,raw,validation,context,result);
    assert_export(path,details,[1440 810]);
    assert(~details.channels(1).inband_power_available);
    assert(strcmp(details.channels(1).inband_power_reason,'理论频段不在采集范围内'));
    assert(details.channels(2).inband_power_available);
    assert(max(abs(details.channels(2).inband_frequency_limits_hz-[1.4e9 3.6e9])) < 1e3);
    assert(details.channels(2).impedance_ohm == 75);
    assert(isfinite(details.channels(2).inband_power_dbm));
    expected_power=10*log10(details.channels(2).inband_rms_v^2/75*1000);
    assert(abs(details.channels(2).inband_power_dbm-expected_power)<1e-10);
    [raw,validation,context,~] = fixture(16);
    context.plot_options.figure_size = [1440 810];
    raw.channels(1).time_axis_s = [];
    raw.channels(2).time_axis_s(end) = [];
    capture_only = struct('status','captured_ready_for_demod','pairs',struct([]));
    path = fullfile(output_dir,'rx_invalid_time_axes.png');
    details = msiq.plotting.rx_dashboard(path,raw,validation,context,capture_only);
    assert_export(path,details,[1440 810]);
    assert(strcmp(details.status,'captured_ready_for_demod'));
    assert(~any(details.stage_available));
    audit = msiq.instruments.get_audit();
    assert(all(struct2array(audit) == 0),'RX plotting accessed instrument I/O.');
    note = ['RX11/13 axes; 1440x810 and 1920x1080; dynamic channels, rates, ' ...
        'bandwidth, QAM order, missing stages, shared payload and tracking statistics; zero instrument I/O'];
catch exception
    if own_scope, msiq.validation_artifacts('finish',true,exception.message); end
    rethrow(exception);
end
if own_scope, msiq.validation_artifacts('finish',false,note); end
end

function validate_payload_stages()
[raw,~,context,result] = fixture(16);
decoded = result.pairs.decoded;
[stages,info] = msiq.plotting.rx_constellation_stages(raw,context,decoded);
positions = context.tx_ref.frame.payload_positions_service;
assert(all(info.stage_available));
assert(~info.time_available && ~isempty(info.time_reason));
assert(isequal(info.payload_positions_service(:),positions(:)));
assert(isempty(intersect(positions,context.tx_ref.frame.pilot_positions_service)));
eq = decoded.primary_equalizer;
fields = {'service_symbols_before_equalization','service_symbols_before_tracking', ...
    'service_symbols_after_tracking'};
for index = 1:3
    values = eq.(fields{index});
    assert(isequaln(stages{index}(:),values(positions)));
end
assert(isequaln(stages{4}(:),decoded.primary_streams.constellation_symbols(:)));
decoded.primary_equalizer.service_symbols_before_tracking(end) = [];
[stages,info] = msiq.plotting.rx_constellation_stages(raw,context,decoded);
assert(~info.stage_available(2) && isempty(stages{2}));
assert(~isempty(info.stage_reasons{2}));
assert(info.stage_available(3) && info.stage_available(4));
end

function validate_tracking_statistics()
frame = struct('service_length',24,'pilot_positions_service',[1 9 17], ...
    'symbol_rate_hz',2e9);
cfg = struct('receiver',struct('track_pilot_acquire_count',2));
errors = (1:24).'/100;
errors(2:8) = NaN;
errors(12) = NaN;
errors(19) = .9;
tracking = struct('enabled',true,'error_log',errors, ...
    'phase_log',zeros(24,1),'update_count',16,'rejected_count',1);
stats = msiq.plotting.rx_tracking_error_stats(tracking,frame,cfg,5);
assert(stats.available);
assert(stats.updated_count == 16 && stats.initial_wait_count == 7);
assert(stats.eligible_count == 14 && stats.rejected_count == 1);
assert(abs(stats.rejected_fraction-1/14) < 1e-12);
assert(stats.rejection_visible && stats.window_size_symbols == 5);
assert(sum(stats.window_counts) == nnz(isfinite(errors)));
expected_energy = sum(errors(isfinite(errors)).^2);
assert(abs(stats.error_energy-expected_energy) < 1e-12);
assert(abs(sum(stats.window_counts(:).*stats.window_rms(:).^2)-expected_energy) < 1e-12);
for index = 1:numel(stats.window_counts)
    positions = ((index-1)*5+1:min(index*5,24)).';
    positions = positions(isfinite(errors(positions)));
    if isempty(positions)
        assert(isnan(stats.window_rms(index)) && isnan(stats.window_peak(index)));
        continue;
    end
    [peak,local] = max(errors(positions));
    assert(abs(stats.window_peak(index)-peak) < 1e-12);
    assert(abs(stats.window_peak_time_us(index)-(positions(local)-1)/2e9*1e6) < 1e-12);
end
tracking.error_log(12) = .12;
tracking.update_count = 17;
tracking.rejected_count = 0;
stats = msiq.plotting.rx_tracking_error_stats(tracking,frame,cfg,5);
assert(stats.available && ~stats.rejection_visible && stats.rejected_count == 0);
tracking.error_log(24) = NaN;
tracking.phase_log(24) = NaN;
tracking.update_count = tracking.update_count-1;
stats = msiq.plotting.rx_tracking_error_stats(tracking,frame,cfg,5);
assert(stats.count_consistent && stats.eligible_count == 13);
assert(stats.rejected_count == 0 && stats.rejected_fraction == 0);
tracking.rejected_count = 2;
stats = msiq.plotting.rx_tracking_error_stats(tracking,frame,struct(),5);
assert(stats.rejection_visible && isnan(stats.rejected_fraction));
tracking.error_log(:) = NaN;
tracking.update_count = 0;
stats = msiq.plotting.rx_tracking_error_stats(tracking,frame,cfg,5);
assert(~stats.available && all(isnan(stats.window_rms)));
end

function [raw,validation,context,result] = fixture(order)
cfg = struct('waveform',struct('modulation_order',order,'if_center_hz',0), ...
    'receiver',struct('track_pilot_acquire_count',2));
service_count = 1056;
pilots = (1:33:service_count).';
positions = setdiff((1:service_count).',pilots);
ideal = qammod((0:order-1).',order,'UnitAveragePower',true);
symbols = ideal(mod((0:service_count-1).',order)+1);
symbols(pilots) = 7+8i;
frame = struct('service_length',service_count,'service_start',193, ...
    'training_start',65,'training_length',128,'symbol_count',1248, ...
    'payload_positions_service',positions,'pilot_positions_service',pilots, ...
    'symbol_rate_hz',2e9,'rrc_rolloff',.1,'modulation_order',order);
errors = .02+.01*sin((1:service_count).'/13).^2;
errors(2:33) = NaN;
errors(612) = .2;
tracking = struct('enabled',true,'phase_log',.05*sin((1:service_count).'/81), ...
    'error_log',errors,'update_count',nnz(isfinite(errors)), ...
    'rejected_count',0);
eq = struct('name','synthetic_plot_fixture','training_symbols_equalized', ...
    repmat(pskmod((0:3).',4,pi/4),32,1)*.998, ...
    'training_nmse',1e-3,'training_timing_offsets_samples',-6:6, ...
    'training_timing_nmse',1e-3*(1+((-6:6)+2).^2/200), ...
    'training_timing_offset_samples',-2,'processing_samples_per_symbol',2, ...
    'service_symbols_before_equalization',1.3*symbols+.08i, ...
    'service_symbols_before_tracking',1.03*symbols+.01i, ...
    'service_symbols_after_tracking',1.01*symbols,'tracking',tracking);
stream = struct('pre_tracking_symbols',eq.service_symbols_after_tracking(positions), ...
    'constellation_symbols',symbols(positions),'evm_rms',.02, ...
    'pre_fec_ber',1e-3,'post_fec_ber',0,'block_count',3,'block_error_count',0, ...
    'fec',struct('pre_fec_bit_error_count',4,'pre_fec_bit_count',4000, ...
    'post_fec_bit_error_count',0,'post_fec_bit_count',3000));
sync = struct('repeat_metric_trace',zeros(2048,1),'repeat_peak_locations',[257 1257], ...
    'sync_start_sample',257);
sync.repeat_metric_trace([257 1257]) = [.99 .98];
decoded = struct('pass',true,'primary_equalizer',eq,'primary_streams',stream, ...
    'synchronization',sync,'preparation',struct('output_sample_rate_hz',4e9));
result = struct('status','decoded','pairs',struct('name','pair_a', ...
    'status','decoded','decoded',decoded));
records = repmat(struct('channel','','sample_rate_hz',NaN, ...
    'time_axis_s',[],'samples',[]),1,2);
for index = 1:2
    rate = [8e9 12e9]; count = [8192 12288];
    records(index).channel = sprintf('C%d',index);
    records(index).sample_rate_hz = 250e6;
    records(index).time_axis_s = (0:count(index)-1).'/rate(index)-.5e-6;
    records(index).samples = .12*sin(2*pi*.3e9*records(index).time_axis_s)+.02;
end
raw = struct('channels',records);
channels = struct('name',{'C1','C2'},'impedance_ohm',{50,50}, ...
    'vertical_scale_v_per_div',{.1,.05},'offset_v',{.08,0}, ...
    'bandwidth_limit_hz',{1e9,4e9});
context = struct('cfg',cfg,'tx_ref',struct('frame',frame,'modulation_order',order), ...
    'scope_status',struct('channels',channels,'sample_rate_hz',250e6));
validation = struct('ok',true,'reason','','summary',struct());
end

function assert_export(path,details,dimensions)
assert(isfile(path));
[folder,name] = fileparts(path);
assert(isfile(msiq.artifact_path(folder,[name '.fig'])));
packet = load(msiq.artifact_path(folder,'plot_data.mat'));
assert(nnz(cellfun(@(p) strcmp(p.file,[name '.png']),packet.plots)) == 1);
info = imfinfo(path);
assert(info.Width == dimensions(1) && info.Height == dimensions(2));
pixels = imread(path);
assert(range(double(pixels(:))) > 100);
assert(nnz(any(pixels < 235,3)) > .005*info.Width*info.Height);
assert(details.panel_count == 11 && details.axis_count == 13);
assert(isempty(details.layout.issues),strjoin(string(details.layout.issues),'; '));
assert(numel(details.panel_texts) == 11);
end

function text = panel_text(details,index)
text = strjoin(string(details.panel_texts{index}(:)),' ');
end
