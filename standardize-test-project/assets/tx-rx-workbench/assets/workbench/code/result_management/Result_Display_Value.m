function value = Result_Display_Value(value, header, mode)
%RESULT_DISPLAY_VALUE Display formatting only; never use this for computation.
if nargin < 2, header = ''; end
if nargin < 3, mode = ''; end
if isempty(value), value = ''; return; end
if ~isnumeric(value), return; end
validateattributes(value, {'numeric'}, {'scalar', 'real'});
if ~isfinite(value), value = ''; return; end
if strcmp(mode, 'exact')
    value = sprintf('%.17g', value);
elseif startsWith(mode, 'fixed:')
    precision = str2double(extractAfter(mode, 'fixed:'));
    validateattributes(precision, {'numeric'}, {'integer', 'scalar', '>=', 0, '<=', 15});
    value = sprintf('%.*f', precision, value);
elseif strcmp(mode, 'integer') || isinteger(value) || ...
        any(strcmpi(header, {'Channel', 'Observation', 'Sequence', 'Count', '序号', '计数'})) || ...
        ~isempty(regexpi(header, '(^|_)(count|index)$|Count$|比特数|符号数|块数|次数|数量', 'once'))
    value = sprintf('%.0f', value);
elseif strcmp(mode, 'probability') || ~isempty(regexpi(header, 'BER|BLER|FER', 'once'))
    if value == 0, value = '0'; else, value = sprintf('%.2e', value); end
elseif value ~= 0 && abs(value) < 0.005
    value = sprintf('%.2e', value);
else
    value = sprintf('%.2f', value);
end
end
