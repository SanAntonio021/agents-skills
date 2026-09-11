function state = set_awg_channel_levels(session, channels, amplitude_vpp, offset_v)
%SET_AWG_CHANNEL_LEVELS Update only selected DAC amplitude and offset.

channels = unique(double(channels(:).'), 'stable');
validateattributes(channels, {'numeric'}, ...
    {'vector','integer','>=',1,'<=',4,'nonempty'});
amplitude_vpp = expand(amplitude_vpp, numel(channels), 'amplitude_vpp', true);
offset_v = expand(offset_v, numel(channels), 'offset_v', false);
for k = 1:numel(channels)
    channel = channels(k);
    msiq.instruments.write_scpi(session, sprintf( ...
        ':VOLTage%d:AMPLitude %.15g', channel, amplitude_vpp(k)));
    msiq.instruments.write_scpi(session, sprintf( ...
        ':VOLTage%d:OFFSet %.15g', channel, offset_v(k)));
end
state = msiq.instruments.read_awg_public_state(session);
for k = 1:numel(channels)
    trace = state.traces(channels(k));
    if ~isfinite(trace.amplitude_vpp) || ...
            abs(trace.amplitude_vpp-amplitude_vpp(k)) > 1e-9 || ...
            ~isfinite(trace.offset_v) || abs(trace.offset_v-offset_v(k)) > 1e-9
        error('msiq:instrument:AwgLevelReadback', ...
            'DAC%d level readback does not match the requested value.', channels(k));
    end
end
end

function value = expand(value, count, name, positive)
value = double(value(:).');
if isscalar(value), value = repmat(value, 1, count); end
if numel(value) ~= count || any(~isfinite(value)) || (positive && any(value <= 0))
    error('msiq:instrument:AwgLevelInput', ...
        '%s must be finite and scalar or match selected channels.', name);
end
end
