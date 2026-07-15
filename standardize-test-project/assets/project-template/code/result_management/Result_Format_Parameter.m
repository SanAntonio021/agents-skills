function text = Result_Format_Parameter(name, value, precision, unit)
%RESULT_FORMAT_PARAMETER Format one scalar or range for a file name.

name = validate_name_part(name, 'name');
unit = validate_name_part(unit, 'unit');
validateattributes(value, {'numeric'}, {'real', 'finite', 'vector', 'nonempty'});
if numel(value) > 2
    error('Result_Format_Parameter:BadValueCount', ...
        'Parameter value must be a scalar or a two-element range.');
end

values = value(:).';
formatted = arrayfun(@(x) Result_Format_Value(x, precision), values, ...
    'UniformOutput', false);
separator = '-';
if numel(values) == 2 && any(values < 0)
    separator = '_to_';
end
text = [name, strjoin(formatted, separator), unit];

end

function text = validate_name_part(value, label)
if ~(ischar(value) || (isstring(value) && isscalar(value)))
    error('Result_Format_Parameter:BadNamePart', '%s must be text.', label);
end
text = strtrim(char(value));
if isempty(text)
    if strcmp(label, 'unit')
        return;
    end
    error('Result_Format_Parameter:EmptyNamePart', ...
        '%s cannot be empty.', label);
end
if ~isempty(regexp(text, '\s', 'once')) || ...
        ~isempty(regexp(text, '[<>:"/\\|?*\x00-\x1F]', 'once'))
    error('Result_Format_Parameter:UnsafeNamePart', ...
        '%s contains a character that is unsafe in a Windows file name.', label);
end
end
