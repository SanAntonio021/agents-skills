function Result_Log_Stage(run_or_path, level, stage, message, varargin)
%RESULT_LOG_STAGE Append one staged UTF-8 log record.

path = resolve_log_path(run_or_path);
level = upper(strtrim(char(string(level))));
if ~ismember(level, {'DEBUG', 'INFO', 'WARNING', 'ERROR'})
    error('Result_Log_Stage:BadLevel', ...
        'Level must be DEBUG, INFO, WARNING, or ERROR.');
end
stage = lower(strtrim(char(string(stage))));
if isempty(regexp(stage, '^[a-z][a-z0-9_]*$', 'once'))
    error('Result_Log_Stage:BadStage', ...
        'Stage must use lowercase letters, digits, and underscores.');
end
message = sprintf(char(string(message)), varargin{:});
message = regexprep(message, '\r?\n', ' | ');

fid = fopen(path, 'a', 'n', 'UTF-8');
if fid < 0
    error('Result_Log_Stage:OpenFailed', 'Cannot open log file: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
timestamp = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSSXXX'));
fprintf(fid, '%s | %s | %s | %s\n', timestamp, level, stage, message);

end

function path = resolve_log_path(value)
if isstruct(value) && isfield(value, 'LogPath')
    path = value.LogPath;
elseif ischar(value) || (isstring(value) && isscalar(value))
    path = char(value);
    if isfolder(path)
        path = fullfile(path, 'run_log.txt');
    else
        [parent, ~, extension] = fileparts(path);
        if strcmpi(extension, '.json')
            path = fullfile(parent, 'run_log.txt');
        end
    end
else
    error('Result_Log_Stage:BadTarget', ...
        'Target must be a run struct, run directory, or log path.');
end
end
