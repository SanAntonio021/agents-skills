function reason = classify_stop_reason(exception)
%CLASSIFY_STOP_REASON Map staged bench errors to result-contract reasons.

id = lower(exception.identifier);
if contains(id, 'connection') || contains(id, 'missingresource')
    reason = 'instrument_connection_failed';
elseif contains(id, 'readback') || contains(id, 'query') || ...
        contains(id, 'identity')
    reason = 'instrument_read_failed';
elseif contains(id, 'capture') || contains(id, 'acquisition')
    reason = 'acquisition_failed';
elseif contains(id, 'write') || contains(id, 'download')
    reason = 'instrument_write_failed';
elseif contains(id, 'safety') || contains(id, 'clip')
    reason = 'safety_stop';
else
    reason = 'unhandled_exception';
end
end
