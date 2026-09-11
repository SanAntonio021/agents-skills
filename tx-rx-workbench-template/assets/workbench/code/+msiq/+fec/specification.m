function spec = specification(cfg)
%SPECIFICATION Supported code identities, independent of local matrix paths.
f = cfg.fec;
frame_type = 'normal';
if isfield(f, 'frame_type'), frame_type = lower(char(string(f.frame_type))); end
rate = f.rate_numerator / f.rate_denominator;
normal = strcmp(frame_type, 'normal') && abs(rate-9/10) < 1e-12;
short = strcmp(frame_type, 'short') && abs(rate-8/9) < 1e-12;
if ~strcmpi(f.family, 'DVB-S2') || ~(normal || short)
    error('msiq:config:FecLocked', ...
        'Supported DVB-S2 codes are normal 9/10 and opt-in short 8/9.');
end
spec = struct('family', 'DVB-S2', 'frame_type', frame_type, ...
    'rate_numerator', f.rate_numerator, 'rate_denominator', f.rate_denominator, ...
    'codeword_length', 64800, 'info_length', 58320);
if short
    spec.codeword_length = 16200;
    spec.info_length = 14400;
end
end
