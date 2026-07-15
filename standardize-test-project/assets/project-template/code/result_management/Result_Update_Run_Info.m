function info = Result_Update_Run_Info(run_or_path, updates)
%RESULT_UPDATE_RUN_INFO Merge updates into run_info.json atomically.

if nargin < 2 || ~isstruct(updates) || ~isscalar(updates)
    error('Result_Update_Run_Info:BadUpdates', ...
        'Updates must be a scalar struct.');
end
path = resolve_info_path(run_or_path);
if ~exist(path, 'file')
    error('Result_Update_Run_Info:MissingRunInfo', ...
        'run_info.json does not exist: %s', path);
end

fid = fopen(path, 'r', 'n', 'UTF-8');
if fid < 0
    error('Result_Update_Run_Info:ReadFailed', ...
        'Cannot read run_info.json: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
text = fread(fid, '*char').';
clear cleanup;
info = jsondecode(text);
updates = normalize_updates(updates);
info = merge_recursive(info, updates);
info = remove_legacy_fields(info);
Result_Atomic_Write_Json(path, info);

end

function updates = normalize_updates(updates)
if isfield(updates, 'status')
    status = lower(strtrim(char(string(updates.status))));
    aliases = struct('dry_run', 'completed', 'preflight_ok', 'completed', ...
        'simulated', 'completed', 'analyzed', 'completed', ...
        'stopped_by_user', 'stopped');
    if isfield(aliases, status)
        status = aliases.(status);
    end
    if ~ismember(status, ...
            {'running', 'completed', 'completed_with_failures', 'failed', 'stopped'})
        error('Result_Update_Run_Info:BadStatus', ...
            'Status is not part of the run-info contract.');
    end
    updates.status = status;
end
end

function info = remove_legacy_fields(info)
legacy = {'run_type', 'run_purpose', 'start_time', 'end_time', ...
    'code_version', 'sources'};
present = intersect(legacy, fieldnames(info));
if ~isempty(present)
    info = rmfield(info, present);
end
end

function path = resolve_info_path(value)
if isstruct(value) && isfield(value, 'RunInfoPath')
    path = value.RunInfoPath;
elseif ischar(value) || (isstring(value) && isscalar(value))
    path = char(value);
    if isfolder(path)
        path = fullfile(path, 'run_info.json');
    end
else
    error('Result_Update_Run_Info:BadTarget', ...
        'Target must be a run struct, run directory, or JSON path.');
end
end

function out = merge_recursive(base, extra)
out = base;
names = fieldnames(extra);
for k = 1:numel(names)
    name = names{k};
    if isfield(out, name) && isstruct(out.(name)) && isscalar(out.(name)) && ...
            isstruct(extra.(name)) && isscalar(extra.(name))
        out.(name) = merge_recursive(out.(name), extra.(name));
    else
        out.(name) = extra.(name);
    end
end
end
