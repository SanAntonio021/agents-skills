function write_scpi(session, command)
%WRITE_SCPI Send one command and record the side effect.

msiq.instruments.io_audit('record_write', session.kind);
msiq.instruments.io_audit('record_command', struct( ...
    'role', session.kind, 'command', char(string(command))));
if session.mock
    fail_if_requested(session, 'write');
else
    fprintf(session.interface, char(string(command)));
end
if strcmpi(session.kind, 'awg')
    msiq.instruments.io_audit('apply_awg_command', command);
end
end

function fail_if_requested(session, stage)
specification = session.specification;
if isfield(specification, 'fail_stage') && ...
        strcmpi(char(string(specification.fail_stage)), stage)
    error('msiq:instrument:MockFailure', ...
        'Injected mock failure at %s.', stage);
end
end
