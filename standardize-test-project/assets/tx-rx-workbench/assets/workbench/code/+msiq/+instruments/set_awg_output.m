function set_awg_output(session, enabled)
%SET_AWG_OUTPUT Enable all DACs or force all DACs off with best effort.

if ~enabled
    first_exception = [];
    for channel = 1:4
        try
            msiq.instruments.write_scpi(session, ...
                sprintf(':OUTPut%d OFF', channel));
        catch exception
            if isempty(first_exception), first_exception = exception; end
        end
    end
    try
        msiq.instruments.write_scpi(session, ':ABOR');
    catch exception
        if isempty(first_exception), first_exception = exception; end
    end
    if ~isempty(first_exception), rethrow(first_exception); end
    return;
end

try
    for channel = 1:4
        msiq.instruments.write_scpi(session, ...
            sprintf(':OUTPut%d ON', channel));
    end
    msiq.instruments.write_scpi(session, ...
        ':FUNCtion:MODE ARBitrary;:INIT:IMM');
catch exception
    try msiq.instruments.set_awg_output(session, false); catch, end
    rethrow(exception);
end
end
