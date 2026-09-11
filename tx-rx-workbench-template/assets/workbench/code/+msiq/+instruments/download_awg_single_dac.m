function report = download_awg_single_dac(session, samples, sample_rate_hz, ...
        channel, amplitude_vpp, offset_v, cfg)
%DOWNLOAD_AWG_SINGLE_DAC Load one trace while all four outputs remain off.

validateattributes(channel, {'numeric'}, ...
    {'scalar','integer','>=',1,'<=',4});
validateattributes(samples, {'numeric'}, {'vector','real','finite','nonempty'});
validateattributes(sample_rate_hz, {'numeric'}, {'scalar','real','finite','positive'});
validateattributes(amplitude_vpp, {'numeric'}, {'scalar','real','finite','positive'});
validateattributes(offset_v, {'numeric'}, {'scalar','real','finite'});
samples = double(samples(:));
original_samples = samples;
original_count = numel(samples);
if max(abs(samples)) > 1 + 1e-12
    error('msiq:instrument:SingleDacRange', ...
        'Single-DAC waveform must stay inside normalized range [-1,1].');
end
if ~strcmpi(cfg.awg.model, 'M8195A_4ch') || ...
        abs(sample_rate_hz-cfg.waveform.awg_sample_rate_hz) > 1
    error('msiq:instrument:SingleDacMode', ...
        'Single-DAC smoke requires M8195A four-DAC EXT DIV4 mode.');
end

msiq.instruments.set_awg_output(session, false);
granularity = 128;
padded_count = ceil(numel(samples)/granularity)*granularity;
if padded_count > numel(samples)
    samples(end+1:padded_count,1) = 0;
end

msiq.instruments.write_scpi(session, [ ...
    ':INST:DACM FOUR;:TRAC1:MMOD EXT;:TRAC2:MMOD EXT;', ...
    ':TRAC3:MMOD EXT;:TRAC4:MMOD EXT;:INST:MEM:EXT:RDIV DIV4']);
msiq.instruments.write_scpi(session, sprintf( ...
    ':FREQuency:RASTer %.15g', sample_rate_hz*4));
msiq.instruments.write_scpi(session, sprintf(':TRACe%d:DELete 1', channel));
msiq.instruments.write_scpi(session, sprintf( ...
    ':TRACe%d:DEFine 1,%d', channel, padded_count));
binary = int8(round(127*max(min(samples,1),-1)));
msiq.instruments.io_audit('record_binary_write', 'awg');
fail_if_requested(session, 'download');
if ~session.mock
    header = sprintf(':TRACe%d:DATA 1,0,', channel);
    binblockwrite(session.interface, binary, 'int8', header);
    fprintf(session.interface, '');
    msiq.instruments.query_scpi(session, '*OPC?');
end
msiq.instruments.write_scpi(session, sprintf(':TRACe%d:SELect 1', channel));
msiq.instruments.write_scpi(session, sprintf( ...
    ':VOLTage%d:AMPLitude %.15g', channel, amplitude_vpp));
msiq.instruments.write_scpi(session, sprintf( ...
    ':VOLTage%d:OFFSet %.15g', channel, offset_v));
msiq.instruments.write_scpi(session, sprintf(':OUTPut%d OFF', channel));

report = struct('dac', channel, 'sample_count', original_count, ...
    'padded_sample_count', padded_count, 'sample_rate_hz', sample_rate_hz, ...
    'amplitude_vpp', amplitude_vpp, 'offset_v', offset_v, ...
    'waveform_sha256', msiq.sha256_bytes(original_samples), ...
    'downloaded_sha256', msiq.sha256_bytes(samples), ...
    'outputs_enabled', false);
end

function fail_if_requested(session, stage)
specification = session.specification;
if isfield(specification, 'fail_stage') && ...
        strcmpi(char(string(specification.fail_stage)), stage)
    error('msiq:instrument:MockDownloadFailure', ...
        'Injected mock failure at %s.', stage);
end
end
