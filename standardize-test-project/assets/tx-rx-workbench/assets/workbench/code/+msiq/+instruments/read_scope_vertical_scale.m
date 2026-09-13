function value = read_scope_vertical_scale(session, channel)
%READ_SCOPE_VERTICAL_SCALE Read LeCroy V/div without changing acquisition.

channel = upper(char(string(channel)));
command = sprintf('VBS? ''return=app.Acquisition.%s.VerScale''', channel);
response = strtrim(msiq.instruments.query_scpi(session, command));
response = regexprep(response, '^.*return=', '');
response = strrep(response, '"', '');
value = str2double(response);
if ~isfinite(value) || value <= 0
    error('msiq:instrument:ScopeScaleReadback', ...
        'Invalid LeCroy V/div readback on %s: %s.', channel, response);
end
end
