function channel = scope_channel(scope_spec)
%SCOPE_CHANNEL Resolve the one LeCroy channel used for V212/V213.

if isfield(scope_spec, 'smoke_channel') && ~isempty(scope_spec.smoke_channel)
    channel = upper(char(string(scope_spec.smoke_channel)));
elseif isfield(scope_spec, 'channels') && ~isempty(scope_spec.channels)
    channels = cellstr(string(scope_spec.channels));
    channel = upper(channels{1});
else
    channel = 'C1';
end
if isempty(regexp(channel, '^C[1-4]$', 'once'))
    error('msiq:instrument:SmokeScopeChannel', ...
        'Scope smoke_channel must be C1, C2, C3, or C4.');
end
end
