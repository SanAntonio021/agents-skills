function idn = query_idn(session)
%QUERY_IDN Read and validate instrument identity.

idn = msiq.instruments.query_scpi(session, '*IDN?');
if isfield(session.specification, 'idn_contains') && ...
        ~isempty(session.specification.idn_contains)
    expected = upper(char(string(session.specification.idn_contains)));
    if ~contains(upper(idn), expected)
        error('msiq:instrument:IdentityMismatch', ...
            '%s identity does not contain %s: %s', ...
            session.kind, expected, idn);
    end
end
end
