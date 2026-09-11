function fid = Result_Open_File_Retry(path, permission, machine_format, encoding)
%RESULT_OPEN_FILE_RETRY Open a result file through transient cloud locks.

if nargin < 3 || isempty(machine_format)
    machine_format = 'n';
end
if nargin < 4 || isempty(encoding)
    encoding = 'UTF-8';
end

% Cloud upload filters can retain a fresh CSV for more than ten seconds.
max_attempts = 32;
initial_delay_seconds = 0.1;
last_message = '';
for attempt = 1:max_attempts
    [fid, last_message] = fopen(path, permission, machine_format, encoding);
    if fid >= 0
        return;
    end
    if attempt < max_attempts
        pause(min(1, initial_delay_seconds*2^(attempt-1)));
    end
end

error('Result_Open_File_Retry:OpenFailed', ...
    'Cannot open result file after %d attempts: %s (%s)', ...
    max_attempts, path, last_message);
end
