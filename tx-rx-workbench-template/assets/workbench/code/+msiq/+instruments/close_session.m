function close_session(session)
%CLOSE_SESSION Close only resources owned by this V2 session.

if isempty(session)
    return;
end
msiq.instruments.io_audit('record_close', session.kind);
if isfield(session, 'mock') && session.mock
    return;
end
if isfield(session, 'device') && ~isempty(session.device)
    try disconnect(session.device); catch, end
    try delete(session.device); catch, end
end
if isfield(session, 'interface') && ~isempty(session.interface)
    try fclose(session.interface); catch, end
    try delete(session.interface); catch, end
end
end
