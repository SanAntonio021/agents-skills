function import_summary(run, writer, header_rows, display_columns)
%IMPORT_SUMMARY Adapt legacy row encoders to full and presentation tables.
if nargin < 3, header_rows = 2; end
if nargin < 4, display_columns = {}; end
temporary = [tempname(run.DataDir) '.csv'];
cleanup = onCleanup(@() remove_owned_file(temporary));
writer(temporary);
cells = readcell(temporary,'Delimiter',',','Encoding','UTF-8');
columns = cellstr(string(cells(1,:)));
if header_rows == 2
    units = cellstr(string(cells(2,:)));
else
    units = repmat({'-'},size(columns));
end
rows = cells(header_rows+1:end,:);
for k = 1:numel(rows)
    if isa(rows{k},'missing') || (isstring(rows{k}) && ismissing(rows{k}))
        rows{k} = '';
    end
end
options = struct('DisplayColumns',{display_columns});
Result_Summary_Initialize(run,columns,units,options);
if ~isempty(rows), Result_Summary_Append(run,rows); end
end

function remove_owned_file(path)
if isfile(path), delete(path); end
end
