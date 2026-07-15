function info = Result_Finalize_Run(run_or_path, status, stop_reason, artifacts, stop_detail)
%RESULT_FINALIZE_RUN Record final status, reason, time, and artifact objects.

if nargin < 3 || isempty(stop_reason)
    stop_reason = '';
end
if nargin < 5
    stop_detail = '';
end
output_dir = resolve_output_dir(run_or_path);
current_info = Result_Update_Run_Info(run_or_path, struct());
existing_artifacts = artifact_records(current_info.artifacts, 'run_artifact');
if nargin < 4 || isempty(artifacts)
    listing = dir(output_dir);
    listing = listing(~[listing.isdir]);
    artifacts = artifact_records({listing.name}, 'run_artifact');
else
    artifacts = artifact_records(artifacts, 'run_artifact');
end
artifacts = merge_artifacts(existing_artifacts, artifacts);
status = normalize_status(status);
[stop_reason, stop_detail] = normalize_stop(stop_reason, stop_detail, status);
if strcmp(status, 'running')
    error('Result_Finalize_Run:RunningIsNotFinal', ...
        'Finalize status cannot remain running.');
end

updates = struct();
updates.status = status;
updates.finished_at = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
updates.stop_reason = stop_reason;
updates.stop_detail = stop_detail;
updates.artifacts = artifacts;
info = Result_Update_Run_Info(run_or_path, updates);
Result_Log_Stage(run_or_path, 'INFO', 'finish', ...
    'Run finalized with status %s.', status);

end

function output_dir = resolve_output_dir(value)
if isstruct(value) && isfield(value, 'OutputDir')
    output_dir = value.OutputDir;
elseif ischar(value) || (isstring(value) && isscalar(value))
    path = char(value);
    if isfolder(path)
        output_dir = path;
    else
        output_dir = fileparts(path);
    end
else
    error('Result_Finalize_Run:BadTarget', ...
        'Target must be a run struct, run directory, or run_info.json path.');
end
end

function status = normalize_status(value)
status = lower(strtrim(char(string(value))));
aliases = struct('dry_run', 'completed', 'preflight_ok', 'completed', ...
    'simulated', 'completed', ...
    'analyzed', 'completed', 'stopped_by_user', 'stopped');
if isfield(aliases, status)
    status = aliases.(status);
end
valid = {'running', 'completed', 'completed_with_failures', 'failed', 'stopped'};
if ~ismember(status, valid)
    error('Result_Finalize_Run:BadStatus', ...
        'Status is not part of the run-info contract.');
end
end

function [reason, detail] = normalize_stop(reason, detail, status)
reason = lower(strtrim(char(string(reason))));
detail = char(string(detail));
valid = {'normal_completion', 'user_stop', 'preflight_failed', ...
    'instrument_connection_failed', 'instrument_read_failed', ...
    'instrument_write_failed', 'acquisition_failed', ...
    'processing_failed', 'safety_stop', 'unhandled_exception'};
if ~isempty(reason) && ~ismember(reason, valid)
    if isempty(detail)
        detail = reason;
    end
    reason = '';
end
if isempty(reason)
    if ismember(status, {'completed', 'completed_with_failures'})
        reason = 'normal_completion';
    elseif strcmp(status, 'stopped')
        reason = 'user_stop';
    else
        reason = 'unhandled_exception';
    end
end
end

function records = artifact_records(value, default_role)
if isstruct(value)
    records = repmat(struct('file', '', 'role', '', ...
        'sha256', string(missing)), 1, numel(value));
    for k = 1:numel(value)
        if ~isfield(value, 'file')
            error('Result_Finalize_Run:BadArtifacts', ...
                'Each artifact record must contain file.');
        end
        records(k).file = char(string(value(k).file));
        records(k).role = default_role;
        if isfield(value, 'role') && ~isempty(value(k).role)
            records(k).role = char(string(value(k).role));
        end
        if isfield(value, 'sha256') && ~isempty(value(k).sha256)
            records(k).sha256 = char(string(value(k).sha256));
        end
    end
else
    if ischar(value) || (isstring(value) && isscalar(value))
        files = {char(value)};
    elseif isstring(value)
        files = cellstr(value(:).');
    elseif iscell(value)
        files = cellfun(@char, value(:).', 'UniformOutput', false);
    else
        error('Result_Finalize_Run:BadArtifacts', ...
            'Artifacts must be an object array or list of file names.');
    end
    records = repmat(struct('file', '', 'role', default_role, ...
        'sha256', string(missing)), 1, numel(files));
    for k = 1:numel(files)
        records(k).file = files{k};
    end
end
end

function out = merge_artifacts(first, second)
out = [first(:).', second(:).'];
[~, keep] = unique({out.file}, 'stable');
out = out(sort(keep));
end
