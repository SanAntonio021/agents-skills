function report = download_awg(session, waveforms, cfg)
%DOWNLOAD_AWG Preload four DACs in external-memory DIV4 mode, outputs off.

preflight = msiq.preflight_waveform(waveforms, cfg, cfg.awg.model);
if ~preflight.ok
    error('msiq:instrument:AwgPreflight', ...
        'AWG waveform rejected: %s.', preflight.reason);
end
if ~strcmpi(cfg.awg.model, 'M8195A_4ch')
    error('msiq:instrument:AwgMode', ...
        'Formal V2 download requires M8195A_4ch.');
end

prepared = msiq.instruments.prepare_awg_download( ...
    waveforms.awg_dac_data, 1:4, 1:4, 128);
awg_state = msiq.instruments.read_awg_public_state(session);
capacity = msiq.instruments.awg_memory_capacity(struct( ...
    'dac_mode', 'FOUR', 'channel_memory_modes', {{'EXT','EXT','EXT','EXT'}}, ...
    'rdiv', 'DIV4', 'selected_channels', prepared.channels, ...
    'required_samples_per_channel', prepared.final_sample_counts, ...
    'option_raw', awg_state.options_raw));
if ~capacity.ok
    error('msiq:instrument:AwgMemoryCapacity', '%s', capacity.message);
end

msiq.instruments.write_scpi(session, ':ABOR');
msiq.instruments.write_scpi(session, [ ...
    ':INST:DACM FOUR;:TRAC1:MMOD EXT;:TRAC2:MMOD EXT;', ...
    ':TRAC3:MMOD EXT;:TRAC4:MMOD EXT;:INST:MEM:EXT:RDIV DIV4']);
msiq.instruments.write_scpi(session, sprintf( ...
    ':FREQuency:RASTer %.15g', waveforms.awg_sample_rate_hz*4));
for channel = 1:4
    msiq.instruments.write_scpi(session, sprintf(':OUTPut%d OFF', channel));
    msiq.instruments.write_scpi(session, sprintf(':TRACe%d:DELete 1', channel));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':TRACe%d:DEFine 1,%d', channel, prepared.final_sample_counts(channel)));
    binary = int8(round(127*prepared.channel_data{channel}));
    if session.mock
        msiq.instruments.io_audit('record_binary_write', 'awg');
        fail_if_requested(session, 'download');
    else
        msiq.instruments.io_audit('record_binary_write', 'awg');
        header = sprintf(':TRACe%d:DATA 1,0,', channel);
        binblockwrite(session.interface, binary, 'int8', header);
        fprintf(session.interface, '');
        msiq.instruments.query_scpi(session, '*OPC?');
    end
    msiq.instruments.write_scpi(session, sprintf(':TRACe%d:SELect 1', channel));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':VOLTage%d:AMPLitude %.15g', channel, cfg.awg.amplitude_vpp(channel)));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':VOLTage%d:OFFSet %.15g', channel, cfg.awg.offset_v(channel)));
    msiq.instruments.write_scpi(session, sprintf(':OUTPut%d OFF', channel));
end
report = struct('sample_count', size(waveforms.awg_dac_data,1), ...
    'padded_sample_count', max(prepared.final_sample_counts), ...
    'final_sample_counts', prepared.final_sample_counts, ...
    'memory_capacity', capacity, 'outputs_enabled', false, ...
    'dac_mapping', {cfg.awg.dac_mapping});
end

function fail_if_requested(session, stage)
specification = session.specification;
if isfield(specification, 'fail_stage') && ...
        strcmpi(char(string(specification.fail_stage)), stage)
    error('msiq:instrument:MockFailure', ...
        'Injected mock failure at %s.', stage);
end
end
