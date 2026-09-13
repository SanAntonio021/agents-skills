function set_awg_channel_output(session, channel, enabled)
%SET_AWG_CHANNEL_OUTPUT Enable one DAC only, or force all four DACs off.

validateattributes(channel, {'numeric'}, ...
    {'scalar','integer','>=',1,'<=',4});
if ~enabled
    msiq.instruments.set_awg_output(session, false);
    return;
end

msiq.instruments.set_awg_output(session, false);
try
    msiq.instruments.write_scpi(session, sprintf(':OUTPut%d ON', channel));
    msiq.instruments.write_scpi(session, ...
        ':FUNCtion:MODE ARBitrary;:INIT:IMM');
catch exception
    try msiq.instruments.set_awg_output(session, false); catch, end
    rethrow(exception);
end
end
