function fec = build(cfg)
%BUILD Construct DVB-S2 LDPC encoder and decoder configurations.

spec = msiq.fec.specification(cfg);
rate = spec.rate_numerator / spec.rate_denominator;
if strcmp(spec.frame_type, 'short')
    H = msiq.fec.short_parity_check(cfg);
else
    H = dvbs2ldpc(rate);
end
fec = struct();
fec.family = cfg.fec.family;
fec.rate = rate;
fec.frame_type = spec.frame_type;
fec.parity_check_matrix = H;
fec.encoder = ldpcEncoderConfig(H);
fec.decoder = ldpcDecoderConfig(H);
fec.codeword_length = fec.encoder.BlockLength;
fec.info_length = fec.encoder.NumInformationBits;
fec.parity_check_count = size(H, 1);
fec.max_iterations = cfg.fec.decoder_max_iterations;
fec.llr_clip = cfg.fec.llr_clip;
end
