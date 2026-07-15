function summary_path = Result_Summary_Initialize(run_or_path, columns, units)
%RESULT_SUMMARY_INITIALIZE Write metric names and units as two CSV rows.

summary_path = resolve_summary_path(run_or_path);
columns = normalize_row(columns, 'columns');
units = normalize_row(units, 'units');
if numel(columns) ~= numel(units)
    error('Result_Summary_Initialize:SizeMismatch', ...
        'Columns and units must have the same number of entries.');
end
if exist(summary_path, 'file')
    error('Result_Summary_Initialize:SummaryExists', ...
        'Summary file already exists and will not be overwritten: %s', summary_path);
end

fid = fopen(summary_path, 'w', 'n', 'UTF-8');
if fid < 0
    error('Result_Summary_Initialize:OpenFailed', ...
        'Cannot create summary file: %s', summary_path);
end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, uint8([239, 187, 191]), 'uint8');
write_csv_row(fid, columns);
write_csv_row(fid, units);

run_info_path = fullfile(fileparts(summary_path), 'run_info.json');
if exist(run_info_path, 'file')
    info = Result_Update_Run_Info(run_info_path, struct());
    artifacts = merge_artifacts(normalize_artifacts(info), ...
        artifact_record('summary.csv', 'detail_table'));
    Result_Update_Run_Info(run_info_path, struct('artifacts', {artifacts}));
end

end

function path = resolve_summary_path(value)
if isstruct(value) && isfield(value, 'SummaryPath')
    path = value.SummaryPath;
elseif ischar(value) || (isstring(value) && isscalar(value))
    path = char(value);
    if isfolder(path)
        path = fullfile(path, 'summary.csv');
    end
else
    error('Result_Summary_Initialize:BadTarget', ...
        'Target must be a run struct, run directory, or summary path.');
end
end

function values = normalize_row(value, label)
if isstring(value)
    values = cellstr(value(:).');
elseif iscell(value)
    values = value(:).';
else
    error('Result_Summary_Initialize:BadRow', ...
        '%s must be a string array or cell array.', label);
end
values = cellfun(@(x) char(string(x)), values, 'UniformOutput', false);
if isempty(values) || any(cellfun(@isempty, values))
    error('Result_Summary_Initialize:EmptyEntry', ...
        '%s cannot contain empty entries.', label);
end
end

function write_csv_row(fid, values)
encoded = cellfun(@csv_text, values, 'UniformOutput', false);
fprintf(fid, '%s\n', strjoin(encoded, ','));
end

function text = csv_text(value)
text = char(string(value));
if contains(text, {'"', ',', newline, char(13)})
    text = ['"', strrep(text, '"', '""'), '"'];
end
end

function artifacts = normalize_artifacts(info)
if ~isfield(info, 'artifacts') || isempty(info.artifacts)
    artifacts = struct('file', {}, 'role', {}, 'sha256', {});
elseif isstruct(info.artifacts)
    artifacts = info.artifacts(:).';
else
    error('Result_Summary_Initialize:BadArtifacts', ...
        'run_info.json artifacts must be an object array.');
end
end

function record = artifact_record(file, role)
record = struct('file', file, 'role', role, 'sha256', string(missing));
end

function out = merge_artifacts(first, second)
out = [first, second];
[~, keep] = unique({out.file}, 'stable');
out = out(sort(keep));
end
