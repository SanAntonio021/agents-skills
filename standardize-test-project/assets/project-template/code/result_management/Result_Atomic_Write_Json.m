function Result_Atomic_Write_Json(path, value)
%RESULT_ATOMIC_WRITE_JSON Write JSON, then replace with bounded retries.

text = jsonencode(value, 'PrettyPrint', true);
jsondecode(text);
temp_path = tempname(fileparts(path));
cleanup = onCleanup(@() delete_if_present(temp_path));

fid = fopen(temp_path, 'w', 'n', 'UTF-8');
if fid < 0
    error('Result_Atomic_Write_Json:OpenFailed', ...
        'Cannot open temporary JSON file: %s', temp_path);
end
file_cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', text);
clear file_cleanup;

max_attempts = 12;
initial_delay_seconds = 0.1;
last_message = '';
last_identifier = '';
for attempt = 1:max_attempts
    [ok, last_message, last_identifier] = movefile(temp_path, path, 'f');
    if ok
        return;
    end
    if attempt < max_attempts
        pause(min(1, initial_delay_seconds * 2^(attempt - 1)));
    end
end

error('Result_Atomic_Write_Json:MoveFailed', ...
    'Cannot replace JSON after %d attempts: %s (%s)', ...
    max_attempts, last_message, last_identifier);

end

function delete_if_present(path)
if exist(path, 'file')
    delete(path);
end
end
