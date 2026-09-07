function summary_path = Result_Summary_Initialize(run_or_path, columns, units, options)
%RESULT_SUMMARY_INITIALIZE Write metric names and units as two CSV rows.

summary_path = resolve_summary_path(run_or_path);
if nargin < 4, options = struct(); end
if isstruct(run_or_path)
    if ~isfield(options, 'DisplayColumns') && isfield(run_or_path, 'DisplayColumns'), options.DisplayColumns = run_or_path.DisplayColumns; end
    if ~isfield(options, 'Formats') && isfield(run_or_path, 'SummaryFormats'), options.Formats = run_or_path.SummaryFormats; end
end
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

root = fileparts(summary_path);
run_info_path = Result_Artifact_Path(root, 'run_info.json');
has_info = isfile(run_info_path);
full_path = Result_Artifact_Path(root, 'observations.csv');
if isfile(full_path), error('Result_Summary_Initialize:SummaryExists', 'Full observations already exist.'); end
selected = 1:numel(columns);
if isfield(options, 'DisplayColumns') && ~isempty(options.DisplayColumns)
    requested = cellstr(string(options.DisplayColumns));
    [found, selected] = ismember(requested, columns);
    if ~all(found), error('Result_Summary_Initialize:Columns', 'Unknown display column.'); end
else
    hidden = {'repeat', 'attempt', char([37319 38598 26102 38388]), char([21407 22987 25968 25454 25991 20214]), char([21333 27425 22270 29255 25991 20214]), char([38169 35823 20195 30721]), char([38169 35823 20449 24687])};
    selected = find(~ismember(columns, hidden));
end
if isempty(selected), error('Result_Summary_Initialize:Columns', 'At least one display column is required.'); end
if has_info
fid_full = fopen(full_path, 'w', 'n', 'UTF-8');
if fid_full < 0, error('Result_Summary_Initialize:OpenFailed', 'Cannot create full observations.'); end
close_full = onCleanup(@() fclose(fid_full));
fwrite(fid_full, uint8([239, 187, 191]), 'uint8');
write_csv_row(fid_full, columns);
write_csv_row(fid_full, units);
clear close_full;
else
    selected = 1:numel(columns);
end
fid = fopen(summary_path, 'w', 'n', 'UTF-8');
if fid < 0
    error('Result_Summary_Initialize:OpenFailed', ...
        'Cannot create summary file: %s', summary_path);
end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, uint8([239, 187, 191]), 'uint8');
write_csv_row(fid, columns(selected));
write_csv_row(fid, units(selected));

if exist(run_info_path, 'file')
    spec = struct('headers', {columns}, 'display_indices', selected, 'formats', struct());
    if isfield(options, 'Formats'), spec.formats = options.Formats; end
    Result_Update_Run_Info(run_info_path, struct('summary', spec));
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
