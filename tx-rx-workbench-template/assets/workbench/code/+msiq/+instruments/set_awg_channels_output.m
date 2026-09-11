function states = set_awg_channels_output(session, channels, enabled)
%SET_AWG_CHANNELS_OUTPUT Change only selected outputs and verify readback.

channels = unique(double(channels(:).'), 'stable');
validateattributes(channels, {'numeric'}, ...
    {'vector','integer','>=',1,'<=',4,'nonempty'});
validateattributes(enabled, {'logical','numeric'}, {'scalar'});
token = 'OFF';
if logical(enabled), token = 'ON'; end
for channel = channels
    msiq.instruments.write_scpi(session, ...
        sprintf(':OUTPut%d %s', channel, token));
end
states = msiq.instruments.read_awg_output_state(session);
if any(states(channels) ~= logical(enabled))
    error('msiq:instrument:SelectedOutputReadback', ...
        'Selected output readback mismatch for channels %s: %s.', ...
        mat2str(channels), mat2str(states));
end
end
