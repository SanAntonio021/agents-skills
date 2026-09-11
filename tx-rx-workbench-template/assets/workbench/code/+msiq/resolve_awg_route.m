function route = resolve_awg_route(options)
%RESOLVE_AWG_ROUTE Load a tracked one-to-one waveform/AWG/scope route.

if nargin < 1 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:route:Options', 'Route options must be a scalar struct.');
end

root = msiq.project_root();
path = fullfile(root, 'config', 'awg_routes.json');
catalog = jsondecode(fileread(path));
name = char(string(catalog.default_route));
if isfield(options, 'route') && ~isempty(options.route)
    name = char(string(options.route));
end
index = find(strcmpi({catalog.routes.name}, name), 1);
if isempty(index)
    error('msiq:route:Unknown', 'Unknown AWG route: %s.', name);
end
route = catalog.routes(index);
route.name = char(string(route.name));
route.waveform_columns = double(route.waveform_columns(:).');
route.awg_channels = double(route.awg_channels(:).');
route.scope_channels = cellstr(string(route.scope_channels(:).'));
route.labels = cellstr(string(route.labels(:).'));

overrides = {'waveform_columns','awg_channels','scope_channels','labels'};
for k = 1:numel(overrides)
    field = overrides{k};
    if isfield(options, field) && ~isempty(options.(field))
        if ismember(field, {'scope_channels','labels'})
            route.(field) = cellstr(string(options.(field)(:).'));
        else
            route.(field) = double(options.(field)(:).');
        end
    end
end
count = numel(route.awg_channels);
if count < 1 || count > 4 || ...
        numel(route.waveform_columns) ~= count || ...
        numel(route.scope_channels) ~= count || numel(route.labels) ~= count
    error('msiq:route:Size', ...
        'A route needs equally sized waveform, AWG, scope, and label lists.');
end
validateattributes(route.awg_channels, {'numeric'}, ...
    {'integer','>=',1,'<=',4});
validateattributes(route.waveform_columns, {'numeric'}, ...
    {'integer','>=',1,'<=',4});
if numel(unique(route.awg_channels)) ~= count || ...
        numel(unique(route.waveform_columns)) ~= count
    error('msiq:route:OneToOne', ...
        'Version 1 routes must be one-to-one; duplication and mixing are unsupported.');
end
expected_scope = "C" + string(route.awg_channels);
actual_scope = upper(string(route.scope_channels));
if any(actual_scope ~= expected_scope)
    error('msiq:route:ScopeMapping', ...
        'Version 1 requires AWG CHn to map to LeCroy Cn.');
end
route.scope_channels = cellstr(actual_scope);
end
