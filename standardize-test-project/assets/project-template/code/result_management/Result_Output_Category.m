function category = Result_Output_Category(mode, requested)
%RESULT_OUTPUT_CATEGORY Keep execution semantics separate from output grouping.
if nargin < 2, requested = ''; end
switch char(mode)
    case {'hardware', 'hardware_query'}, expected = 'measurement';
    case 'dry_run', expected = 'checks';
    case 'simulation', expected = 'simulation';
    case {'offline_replay', 'offline_analysis'}, expected = 'analysis';
    otherwise, error('Result_Output_Category:Mode', 'Unsupported execution mode.');
end
category = char(requested);
if isempty(category), category = expected; end
if ~ismember(category, {'simulation', 'measurement', 'analysis', 'checks'}) || ...
        (~strcmp(category, expected) && ~(strcmp(mode, 'simulation') && strcmp(category, 'checks')))
    error('Result_Output_Category:Category', 'Output category disagrees with execution mode.');
end
end
