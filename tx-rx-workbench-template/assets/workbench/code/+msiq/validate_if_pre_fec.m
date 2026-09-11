function report = validate_if_pre_fec()
%VALIDATE_IF_PRE_FEC Pure software checks: debug never constructs a decoder.
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform.ldpc_blocks_per_frame = 3;
options = struct('cfg_override',cfg,'symbol_rate_hz',65e9/15, ...
    'rate_authority','symbol_rate','rdiv','DIV4','frame_repetitions',1, ...
    'memory_mode','EXT');
plan = msiq.traditional_tx('preview_plan',[],options);
ref = plan.tx_ref.pairs(1).metrics_only(1).fec;
cfg = plan.cfg;
cfg.receiver.debug_pre_fec_only = true;
llr = 10*(1-2*double(ref.coded_bits(:)));
% Invalid matrix/decoder settings prove debug does not build or run LDPC.
poison = cfg;
poison.fec.matrix_file = 'THIS_FILE_MUST_NOT_BE_OPENED.mat';
poison.fec.decoder_max_iterations = -1;
good = msiq.fec.decode_soft(llr,ref,poison);
assert(good.valid && good.pre_fec_ber == 0);
assert(good.pre_fec_bit_count == numel(ref.coded_bits));
assert(~good.decoder_executed && isempty(good.decoded_bits));
assert(isnan(good.post_fec_ber) && isnan(good.post_fec_bit_count));
short_cfg = msiq.short_frame_config();
short_cfg.receiver.debug_pre_fec_only = true;
short_cfg.fec.matrix_file = 'THIS_FILE_MUST_NOT_BE_OPENED.mat';
short_ref = struct('block_count',3,'codeword_length',16200, ...
    'info_length',14400,'coded_bits',zeros(48600,1), ...
    'info_bits',zeros(43200,1));
short_good = msiq.fec.decode_soft(ones(48600,1),short_ref,short_cfg);
assert(short_good.valid && ~short_good.decoder_executed);
llr_bad = llr;
llr_bad([1, ref.codeword_length+1]) = -llr_bad([1,ref.codeword_length+1]);
bad = msiq.fec.decode_soft(llr_bad,ref,cfg);
assert(bad.valid && bad.pre_fec_bit_error_count == 2);
assert(bad.pre_fec_ber == 2/numel(ref.coded_bits));
short = msiq.fec.decode_soft(llr(1:end-ref.codeword_length),ref,cfg);
assert(~short.valid && isnan(short.pre_fec_ber));
partial = msiq.fec.decode_soft(llr(1:end-1),ref,cfg);
assert(~partial.valid && partial.pre_fec_bit_count == 0);
nan_llr = llr; nan_llr(7) = NaN;
invalid = msiq.fec.decode_soft(nan_llr,ref,cfg);
assert(~invalid.valid && isnan(invalid.pre_fec_ber));
wrong = ref; wrong.block_count = ref.block_count+1;
mismatch = msiq.fec.decode_soft(llr,wrong,cfg);
assert(~mismatch.valid);
reduced=ref; reduced.block_count=ref.block_count-1;
reduced.coded_bits=ref.coded_bits(1:reduced.block_count*ref.codeword_length);
reduced.info_bits=ref.info_bits(1:reduced.block_count*ref.info_length);
denominator_shortcut=msiq.fec.decode_soft(llr,reduced,cfg);
assert(~denominator_shortcut.valid&&isnan(denominator_shortcut.pre_fec_ber));
wrong = ref; wrong.codeword_length = ref.codeword_length+1;
mismatch = msiq.fec.decode_soft(llr,wrong,cfg);
assert(~mismatch.valid);
normal = cfg; normal.receiver.debug_pre_fec_only = false;
legacy = msiq.fec.decode_soft(llr_bad,ref,normal);
assert(legacy.pre_fec_bit_count == bad.pre_fec_bit_count && ...
    legacy.pre_fec_bit_error_count == bad.pre_fec_bit_error_count);
% Exercise existing synthesis, synchronization, tracking and stream reporting.
simulation = struct('snr_db',35,'cfo_hz',0,'sro_ppm',0, ...
    'channel_matrix',eye(2),'image_matrix',zeros(2), ...
    'capture_repetitions',3);
raw = msiq.simulate_capture(plan.waveforms,plan.cfg,'A',simulation);
decoded = msiq.decode_capture(raw,plan.tx_ref,cfg);
assert(decoded.sync_ok && decoded.valid && decoded.pass);
assert(all([decoded.primary_streams.valid]));
assert(all(isnan([decoded.primary_streams.post_fec_ber])));
assert(all([decoded.primary_streams.pre_fec_bit_count] == numel(ref.coded_bits)));
report = struct('ok',true,'details',struct( ...
    'strict_block_count',ref.block_count,'bit_count',good.pre_fec_bit_count, ...
    'injected_errors',bad.pre_fec_bit_error_count, ...
    'legacy_pre_ber_agrees',true,'synthetic_capture_valid',decoded.valid, ...
    'ldpc_debug_executed',false));
end
