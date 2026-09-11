function cfg = short_frame_config(matrix_file)
%SHORT_FRAME_CONFIG Opt-in three-block short code; keep the long-code default.
% matrix_file is machine-local licensed data, not a distributable dependency.
cfg = msiq.build_config('v2_traditional_wz');
cfg.fec.frame_type = 'short';
cfg.fec.rate_numerator = 8;
cfg.fec.rate_denominator = 9;
if nargin > 0 && ~isempty(matrix_file), cfg.fec.matrix_file = char(matrix_file); end
cfg.waveform.ldpc_blocks_per_frame = 3;
cfg.waveform.frame_repetitions = 1;
cfg = msiq.build_config(cfg);
end
