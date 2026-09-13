function states = read_awg_output_state(session)
%READ_AWG_OUTPUT_STATE Read all four M8195A output-enable states.

states = false(1,4);
for channel = 1:4
    response = strtrim(msiq.instruments.query_scpi(session, ...
        sprintf(':OUTPut%d?', channel)));
    numeric = str2double(response);
    if isfinite(numeric)
        states(channel) = numeric ~= 0;
    elseif strcmpi(response, 'ON')
        states(channel) = true;
    elseif strcmpi(response, 'OFF')
        states(channel) = false;
    else
        error('msiq:instrument:AwgReadbackParse', ...
            'Cannot parse DAC%d output readback: %s.', channel, response);
    end
end
end
