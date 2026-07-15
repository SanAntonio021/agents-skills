function Result_Summary_Append(run_or_path, rows)
%RESULT_SUMMARY_APPEND Append rows in the existing summary column order.

summary_path = resolve_summary_path(run_or_path);
if ~exist(summary_path, 'file')
    error('Result_Summary_Append:MissingSummary', ...
        'Initialize summary.csv before appending rows: %s', summary_path);
end
expected_count = header_column_count(summary_path);
rows = normalize_rows(rows);
if size(rows, 2) ~= expected_count
    error('Result_Summary_Append:ColumnCountMismatch', ...
        'Expected %d columns but received %d.', expected_count, size(rows, 2));
end

fid = fopen(summary_path, 'a', 'n', 'UTF-8');
if fid < 0
    error('Result_Summary_Append:OpenFailed', ...
        'Cannot open summary file: %s', summary_path);
end
cleanup = onCleanup(@() fclose(fid));
for row_index = 1:size(rows, 1)
    encoded = cellfun(@csv_text, rows(row_index, :), 'UniformOutput', false);
    fprintf(fid, '%s\n', strjoin(encoded, ','));
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
    error('Result_Summary_Append:BadTarget', ...
        'Target must be a run struct, run directory, or summary path.');
end
end

function rows = normalize_rows(value)
if istable(value)
    rows = table2cell(value);
elseif iscell(value)
    rows = value;
elseif isstring(value)
    rows = cellstr(value);
elseif isnumeric(value) || islogical(value)
    rows = num2cell(value);
else
    error('Result_Summary_Append:BadRows', ...
        'Rows must be a table, cell array, numeric array, logical array, or string array.');
end
if isvector(rows)
    rows = reshape(rows, 1, []);
end
end

function count_value = header_column_count(path)
fid = fopen(path, 'r', 'n', 'UTF-8');
if fid < 0
    error('Result_Summary_Append:ReadFailed', ...
        'Cannot read summary header: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
line = fgetl(fid);
if ~ischar(line)
    error('Result_Summary_Append:EmptySummary', 'summary.csv is empty.');
end
count_value = csv_column_count(line);
end

function count_value = csv_column_count(line)
inside_quotes = false;
count_value = 1;
index = 1;
while index <= numel(line)
    if line(index) == '"'
        if inside_quotes && index < numel(line) && line(index + 1) == '"'
            index = index + 1;
        else
            inside_quotes = ~inside_quotes;
        end
    elseif line(index) == ',' && ~inside_quotes
        count_value = count_value + 1;
    end
    index = index + 1;
end
if inside_quotes
    error('Result_Summary_Append:BadHeader', ...
        'summary.csv header contains an unmatched quote.');
end
end

function text = csv_text(value)
if isempty(value)
    text = '';
elseif isnumeric(value)
    validateattributes(value, {'numeric'}, {'scalar'});
    if ~isfinite(value)
        text = '';
    else
        text = sprintf('%.15g', value);
    end
elseif islogical(value)
    validateattributes(value, {'logical'}, {'scalar'});
    text = char(string(value));
elseif isdatetime(value)
    validateattributes(value, {'datetime'}, {'scalar'});
    text = char(value);
else
    text = char(string(value));
end
if contains(text, {'"', ',', newline, char(13)})
    text = ['"', strrep(text, '"', '""'), '"'];
end
end
