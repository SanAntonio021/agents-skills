function note = validate_rx_capture_metrics()
%VALIDATE_RX_CAPTURE_METRICS Full raw persistence and opt-in metric population.
msiq.instruments.io_audit('reset','');
if ~msiq.validation_artifacts('active')
    error('msiq:validation:Scope','Run this case through the validation case scope.');
end
folder = msiq.validation_artifacts('directory');
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.ldpc_blocks_per_frame = 3;
options = struct('cfg_override',cfg,'symbol_rate_hz',65e9/15, ...
    'rate_authority','symbol_rate','rdiv','DIV4','frame_repetitions',1,'memory_mode','EXT');
plan = msiq.traditional_tx('preview_plan',[],options);
cfg = plan.cfg;
ref = plan.tx_ref.pairs(1).metrics_only(1).fec;
llr = 10*(1-2*double(ref.coded_bits(:)));
llr([1,ref.codeword_length+7]) = -llr([1,ref.codeword_length+7]);
cfg.receiver.strict_reference_blocks = true;
cfg.receiver.debug_pre_fec_only = true;
pre = msiq.fec.decode_soft(llr,ref,cfg);
cfg.receiver.debug_pre_fec_only = false;
post = msiq.fec.decode_soft(llr,ref,cfg);
assert(pre.valid && post.valid && ~pre.decoder_executed && post.decoder_executed);
assert(pre.pre_fec_bit_count == post.pre_fec_bit_count && ...
    pre.pre_fec_bit_error_count == post.pre_fec_bit_error_count && ...
    pre.pre_fec_ber == post.pre_fec_ber && pre.pre_fec_bit_error_count == 2);
assert(isnan(pre.post_fec_ber) && isnan(pre.post_fec_bit_count));
for enabled = [false true]
    cfg.receiver.debug_pre_fec_only = ~enabled;
    poison = cfg; poison.fec.matrix_file = 'MUST_NOT_OPEN_FOR_INVALID_METRICS.mat';
    short = msiq.fec.decode_soft(llr(1:end-ref.codeword_length),ref,poison);
    assert(~short.valid && isnan(short.pre_fec_ber) && short.pre_fec_bit_count == 0);
    nonfinite = llr; nonfinite(2) = NaN;
    bad = msiq.fec.decode_soft(nonfinite,ref,poison);
    assert(~bad.valid && isnan(bad.pre_fec_ber));
    wrong = ref; wrong.block_count = wrong.block_count-1;
    bad = msiq.fec.decode_soft(llr,wrong,poison);
    assert(~bad.valid && isnan(bad.pre_fec_ber));
end
legacy = cfg; legacy.receiver.debug_pre_fec_only = false;
legacy.receiver.strict_reference_blocks = false;
partial = msiq.fec.decode_soft(llr(1:end-ref.codeword_length),ref,legacy);
assert(partial.valid && partial.pre_fec_bit_count == 2*ref.codeword_length);

t = (0:12002)'/40e9;
record = struct('channel','C3','samples',.03*cos(2*pi*1e9*t), ...
    'time_axis_s',t,'sample_rate_hz',40e9);
raw = struct('channels',record,'mock',true);
save_options = struct('cfg_override',cfg,'results_root',folder, ...
    'fresh_capture',struct('confirmed',true),'measurement_role','formal');
one = msiq.traditional_rx('save_capture',raw,save_options);
saved = load(one.raw_path,'raw');
assert(isequaln(saved.raw,raw) && numel(saved.raw.channels.samples)==12003);
assert(~one.demod_ready && isempty(one.reference_bundle_path) && strcmp(one.status,'captured'));
assert(numel(one.display_raw.channels.samples)<numel(record.samples));
spec = load(one.spectrum_path,'spectrum');
assert(numel(spec.spectrum)==1 && spec.spectrum{1}.n==numel(record.samples));
assert(isfile(one.dashboard_path));
hash = compute_file_sha256(one.raw_path);
expect_error(@() msiq.traditional_rx('save_capture',one.display_raw,save_options), ...
    'msiq:traditionalRx:DisplayCapture');
collision = save_options; collision.run_dir = one.run_dir;
expect_error(@() msiq.traditional_rx('save_capture',raw,collision), ...
    'Result_Create_Run:OutputExists');
assert(strcmp(hash,compute_file_sha256(one.raw_path)));
bad_reference = save_options; bad_reference.tx_reference_bundle = fullfile(folder,'missing.mat');
unassociated = msiq.traditional_rx('save_capture',raw,bad_reference);
assert(strcmp(unassociated.status,'captured') && ~unassociated.demod_ready);

bundle = struct('route',plan.route,'desired',plan.desired,'tx_ref',plan.tx_ref, ...
    'reference_payload_policy','metrics_only','execution',struct('status','applied','simulated',true), ...
    'dsp_config',struct('waveform',plan.cfg.waveform,'receiver',plan.cfg.receiver));
bundle.dsp_config.receiver.debug_pre_fec_only = false;
bundle_path = fullfile(folder,'reference.mat'); save(bundle_path,'bundle');
raw.channels(2) = record; raw.channels(2).channel = 'C4';
raw.channels(2).samples = .025*sin(2*pi*1e9*t);
save_options.tx_reference_bundle = bundle_path;
two = msiq.traditional_rx('save_capture',raw,save_options);
saved = load(two.raw_path,'raw'); assert(isequaln(saved.raw,raw));
assert(~two.demod_ready && isfile(two.reference_bundle_path)); % Deliberately short window.
before = compute_file_sha256(two.raw_path);
decode_options = struct('cfg_override',cfg,'enable_ldpc',false);
decode_options.cfg_override.project_root = folder;
decode_options.cfg_override.results_root = folder;
decoded = msiq.traditional_rx('demod_capture',two.run_dir,decode_options);
effective = load(fullfile(decoded.diagnostics_dir,'effective_config.mat'),'cfg');
assert(effective.cfg.receiver.debug_pre_fec_only && effective.cfg.receiver.strict_reference_blocks);
assert(~strcmp(two.run_dir,decoded.run_dir) && strcmp(decoded.status,'blocked'));
assert(strcmp(before,compute_file_sha256(two.raw_path)));
decode_options.enable_ldpc = true;
second = msiq.traditional_rx('demod_capture',two.run_dir,decode_options);
effective = load(fullfile(second.diagnostics_dir,'effective_config.mat'),'cfg');
assert(~effective.cfg.receiver.debug_pre_fec_only && effective.cfg.receiver.strict_reference_blocks);
assert(~strcmp(second.run_dir,decoded.run_dir));
assert(strcmp(before,compute_file_sha256(two.raw_path)));

% Positive end-to-end path: one immutable full capture, two decoder choices.
% This uses the transmitted frame and the actual synchronizer/tracker/FEC.
simulation = struct('snr_db',35,'cfo_hz',0,'sro_ppm',0, ...
    'channel_matrix',eye(2),'image_matrix',zeros(2),'capture_repetitions',3);
sampled = msiq.simulate_capture(plan.waveforms,plan.cfg,'A',simulation);
full_raw = struct('mock',true,'channels',[ ...
    struct('channel','C3','samples',sampled.samples(:,1), ...
        'time_axis_s',sampled.time_axes(:,1),'sample_rate_hz',sampled.sample_rate_hz), ...
    struct('channel','C4','samples',sampled.samples(:,2), ...
        'time_axis_s',sampled.time_axes(:,2),'sample_rate_hz',sampled.sample_rate_hz)]);
bundle.dsp_config.receiver.debug_pre_fec_only = true;
positive_reference_path = fullfile(folder,'positive_reference.mat');
save(positive_reference_path,'bundle');
save_options.tx_reference_bundle = positive_reference_path;
full_raw.captured_at = 'mock'; % Legacy native mock marker must survive reanalysis.
save_options.requires_capture_validation = true;
positive = msiq.traditional_rx('save_capture',full_raw,save_options);
assert(positive.demod_ready && strcmp(positive.status,'captured'));
assert(isfile(fullfile(positive.diagnostics_dir,'capture_validation.json')) && ...
    ~isfile(fullfile(positive.run_dir,'capture_validation.json')));
pending_hash=compute_file_sha256(positive.raw_path);
expect_error(@() msiq.traditional_rx('demod_capture',positive.run_dir,decode_options), ...
    'msiq:traditionalRx:CaptureValidation'); % Includes worker-crash-before-postcheck case.
msiq.rx_capture_validation(positive.run_dir,struct('valid',true,'reason','', ...
    'status_after',struct('fixture',true),'fresh_capture',struct('fresh_confirmed',true)));
assert(strcmp(pending_hash,compute_file_sha256(positive.raw_path)));
immutable = {positive.raw_path,positive.reference_bundle_path,positive.metadata_path, ...
    fullfile(positive.run_dir,'summary.csv'),fullfile(positive.diagnostics_dir,'run_info.json'), ...
    fullfile(positive.diagnostics_dir,'capture_validation.json')};
hashes = cellfun(@compute_file_sha256,immutable,'UniformOutput',false);
assert(all(cellfun(@isfile,immutable)) && all(cellfun(@(h)numel(h)==64,hashes)));
outputs = cell(1,2); streams = cell(1,2);
for enabled = [false true]
    index = 1+double(enabled);
    decode_options.enable_ldpc = enabled;
    outputs{index} = msiq.traditional_rx('demod_capture',positive.run_dir,decode_options);
    current = outputs{index};
    assert(strcmp(current.status,'decoded') && current.pairs(1).decoded.sync_ok);
    assert(~current.pairs(1).decoded.clipped);
    streams{index} = current.pairs(1).decoded.primary_streams;
    assert(all([streams{index}.valid]) && ...
        all([streams{index}.pre_fec_bit_count] == numel(ref.coded_bits)));
    for k = 1:numel(streams{index})
        fec_result = streams{index}(k).fec;
        assert(fec_result.decoder_executed == enabled);
        assert(fec_result.expected_block_count == ref.block_count);
        if enabled
            assert(strcmp(fec_result.decoder_status,'EXECUTED') && ...
                fec_result.post_fec_bit_count == numel(ref.info_bits));
        else
            assert(strcmp(fec_result.decoder_status,'NOT_RUN_DEBUG_PRE_FEC_ONLY') && ...
                isnan(fec_result.post_fec_bit_count) && isnan(fec_result.post_fec_ber));
        end
    end
    archived = load(fullfile(current.diagnostics_dir,'demod_result.mat'),'output');
    assert(isequaln(archived.output.pairs(1).decoded.primary_streams,streams{index}));
    metadata = jsondecode(fileread(fullfile(current.diagnostics_dir,'demod_result.json')));
    assert(strcmp(metadata.source_mode,'simulation'));
    provenance=jsondecode(fileread(fullfile(current.diagnostics_dir,'capture_source.json')));
    assert(strcmp(provenance.source_mode,'simulation'));
    json_stream = metadata.pairs(1).streams(1);
    assert(json_stream.pre_fec_bit_count == numel(ref.coded_bits));
    assert(json_stream.decoder_executed == enabled && json_stream.valid);
    assert(isequal(hashes,cellfun(@compute_file_sha256,immutable,'UniformOutput',false)));
end
assert(isequal([streams{1}.pre_fec_bit_count],[streams{2}.pre_fec_bit_count]) && ...
    isequal([streams{1}.pre_fec_bit_error_count],[streams{2}.pre_fec_bit_error_count]) && ...
    isequal([streams{1}.pre_fec_ber],[streams{2}.pre_fec_ber]));
assert(~strcmp(outputs{1}.run_dir,outputs{2}.run_dir) && ...
    ~strcmp(outputs{1}.run_dir,positive.run_dir));
expect_error(@() msiq.rx_capture_validation(positive.run_dir, ...
    struct('valid',false,'reason','不能重写已完成校验')), ...
    'msiq:traditionalRx:ValidationFinal');
rejected=msiq.traditional_rx('save_capture',raw,save_options);
rejected_hash=compute_file_sha256(rejected.raw_path);
msiq.rx_capture_validation(rejected.run_dir,struct('valid',false, ...
    'reason','采集前后量程发生变化','status_after',struct('fixture',true)));
expect_error(@() msiq.traditional_rx('demod_capture',rejected.run_dir,decode_options), ...
    'msiq:traditionalRx:CaptureValidation');
assert(strcmp(rejected_hash,compute_file_sha256(rejected.raw_path)));
audit = msiq.instruments.get_audit();
assert(audit.connections==0 && audit.queries==0 && audit.writes==0 && audit.captures==0);
note = '完整 raw/PSD 保存、单通道无参考、LDPC 开关统计一致、缺块拒绝、参考覆盖及历史保护通过；仪器 I/O 为零。';
end

function expect_error(action, identifier)
try
    action();
catch exception
    assert(strcmp(exception.identifier,identifier),'Unexpected error: %s',exception.message);
    return;
end
error('msiq:validation:ExpectedFailure','Expected %s.',identifier);
end
