function policy = output_policy(options)
%OUTPUT_POLICY Resolve storage options without changing computation or I/O gates.
if nargin < 1, options = struct(); end
if isfield(options, 'results'), options = options.results; end
level = 'compact';
if isfield(options, 'retention_mode') && ~isempty(options.retention_mode)
    level = validatestring(options.retention_mode, {'compact','full'});
end
if isfield(options, 'output_level') && ~isempty(options.output_level)
    level = validatestring(options.output_level, {'compact','full'});
end
if isfield(options, 'save_raw') && ~isempty(options.save_raw)
    validateattributes(options.save_raw, {'logical','numeric'}, {'scalar','binary'});
    if options.save_raw, level = 'full'; else, level = 'compact'; end
end
write = true;
if isfield(options, 'write_results')
    validateattributes(options.write_results, {'logical','numeric'}, {'scalar','binary'});
    write = logical(options.write_results);
end
policy = struct('output_level',level,'save_raw',strcmp(level,'full'), ...
    'write_results',write);
end
