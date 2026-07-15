function file_name = Result_Build_Point_Filename(name_parts, repeat_index, ...
        attempt_index, extension, failed)
%RESULT_BUILD_POINT_FILENAME Build a flat parameter-point file name.

if nargin < 5 || isempty(failed)
    failed = false;
end
parts = normalize_name_parts(name_parts);
validateattributes(repeat_index, {'numeric'}, ...
    {'real', 'finite', 'scalar', 'integer', 'positive'});
validateattributes(attempt_index, {'numeric'}, ...
    {'real', 'finite', 'scalar', 'integer', 'positive'});
validateattributes(failed, {'logical', 'numeric'}, {'scalar'});

extension = char(string(extension));
if isempty(extension)
    error('Result_Build_Point_Filename:MissingExtension', ...
        'A file extension is required.');
end
if extension(1) ~= '.'
    extension = ['.', extension];
end
if contains(extension, {'/', '\'}) || count(extension, '.') ~= 1
    error('Result_Build_Point_Filename:BadExtension', ...
        'Extension must contain one leading period and no path separator.');
end

base_name = sprintf('%s_repeat%02d_attempt%02d%s', ...
    strjoin(parts, '_'), repeat_index, attempt_index, extension);
if logical(failed)
    file_name = ['FAILED_', base_name];
else
    file_name = base_name;
end

end

function parts = normalize_name_parts(value)
if ischar(value) || (isstring(value) && isscalar(value))
    parts = {char(value)};
elseif isstring(value)
    parts = cellstr(value(:).');
elseif iscell(value)
    parts = cellfun(@char, value, 'UniformOutput', false);
else
    error('Result_Build_Point_Filename:BadNameParts', ...
        'Name parts must be text or a cell array of text.');
end
if isempty(parts)
    error('Result_Build_Point_Filename:MissingNameParts', ...
        'At least one name part is required.');
end
for k = 1:numel(parts)
    parts{k} = strtrim(parts{k});
    if isempty(parts{k}) || ~isempty(regexp(parts{k}, '\s', 'once')) || ...
            ~isempty(regexp(parts{k}, '[<>:"/\\|?*\x00-\x1F]', 'once'))
        error('Result_Build_Point_Filename:UnsafeNamePart', ...
            'Name part %d is empty or unsafe.', k);
    end
end
end
