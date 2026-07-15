function run = Result_Create_Run(user_cfg)
%RESULT_CREATE_RUN Create one flat run directory and initialize records.
%
% Required fields: ProjectRoot and RunType. Parameters, Precision and Units
% build the default directory name. OutputDir may override that path.

if nargin < 1 || ~isstruct(user_cfg) || ~isscalar(user_cfg)
    error('Result_Create_Run:BadConfig', 'Input must be a scalar struct.');
end
cfg = merge_struct(default_config(), user_cfg);
cfg.ProjectRoot = required_directory_text(cfg.ProjectRoot, 'ProjectRoot');
cfg.RunType = lower(strtrim(char(string(cfg.RunType))));
valid_types = {'single_point', 'scan', 'dry_run', 'simulation', 'analysis'};
if ~ismember(cfg.RunType, valid_types)
    error('Result_Create_Run:BadRunType', ...
        'RunType must be single_point, scan, dry_run, simulation, or analysis.');
end

timestamp = normalize_timestamp(cfg.RunTimestamp);
name_parts = parameter_name_parts(cfg);
name_parts = [name_parts, normalize_name_parts(cfg.NameParts)];
if isempty(name_parts)
    error('Result_Create_Run:MissingNameParts', ...
        'Parameters or NameParts must describe the run directory.');
end
run_name = [strjoin(name_parts, '_'), '_', timestamp];

if isempty(cfg.OutputDir)
    if isempty(cfg.ResultsRoot)
        results_root = fullfile(cfg.ProjectRoot, 'results');
    else
        results_root = path_text(cfg.ResultsRoot, 'ResultsRoot');
    end
    category_root = fullfile(results_root, cfg.RunType);
    output_dir = fullfile(category_root, run_name);
else
    output_dir = char(string(cfg.OutputDir));
    if isempty(cfg.ResultsRoot)
        results_root = fullfile(cfg.ProjectRoot, 'results');
    else
        results_root = path_text(cfg.ResultsRoot, 'ResultsRoot');
    end
    category_root = fileparts(output_dir);
    [~, run_name] = fileparts(output_dir);
end
if exist(output_dir, 'dir')
    error('Result_Create_Run:OutputExists', ...
        'Run directory already exists and will not be overwritten: %s', output_dir);
end
if exist(output_dir, 'file')
    error('Result_Create_Run:OutputIsFile', ...
        'OutputDir points to a file: %s', output_dir);
end
[ok, message] = mkdir(output_dir);
if ~ok
    error('Result_Create_Run:CreateFailed', ...
        'Cannot create run directory: %s (%s)', output_dir, message);
end
try

run = struct();
run.ProjectRoot = cfg.ProjectRoot;
run.ResultsRoot = results_root;
run.CategoryRoot = category_root;
run.RunType = cfg.RunType;
run.RunTimestamp = timestamp;
run.RunName = run_name;
run.OutputDir = output_dir;
run.RunInfoPath = fullfile(output_dir, 'run_info.json');
run.SummaryPath = fullfile(output_dir, 'summary.csv');
run.LogPath = fullfile(output_dir, 'run_log.txt');

info = cfg.RunInfo;
info.schema_version = '1.0';
info.run_id = run_name;
info.project_name = default_text(cfg.ProjectName, project_name(cfg.ProjectRoot));
info.test_name = default_text(cfg.TestName, info.project_name);
info.run_kind = cfg.RunType;
info.planned_run_kind = nullable_run_kind(cfg.PlannedRunKind);
info.purpose = normalize_purpose(cfg.RunPurpose);
info.execution_mode = normalize_execution_mode(cfg.ExecutionMode, cfg.RunType);
info.status = 'running';
info.stop_reason = '';
info.stop_detail = '';
info.started_at = current_time_text();
info.finished_at = string(missing);
info.entry_point = char(string(cfg.EntryPoint));
info.code = normalize_code(cfg.Code, cfg.CodeVersion);
info.runtime = merge_struct(default_runtime(), cfg.Runtime);
info.primary_variable = nullable_struct(cfg.PrimaryVariable, 'PrimaryVariable');
info.parameters = cfg.Parameters;
info.inputs = normalize_generic_array(cfg.Inputs);
info.instruments = normalize_struct_array(cfg.Instruments, 'Instruments');
info.counts = normalize_counts(cfg.Counts);
info.safety = merge_struct(default_safety(), cfg.Safety);
source_runs = cfg.SourceRuns;
if isempty(source_runs)
    source_runs = cfg.Sources;
end
info.source_runs = normalize_source_runs(source_runs);
initial_artifacts = artifact_records(cfg.Artifacts, 'run_artifact');
required_artifacts = artifact_records({'run_info.json', 'run_log.txt'}, 'run_record');
info.artifacts = merge_artifacts(required_artifacts, initial_artifacts);
info = remove_legacy_fields(info);
validate_run_contract(info);

Result_Atomic_Write_Json(run.RunInfoPath, info);
Result_Log_Stage(run, 'INFO', 'startup', 'Run initialized: %s', run.RunName);
if strcmp(info.run_kind, 'dry_run')
    Result_Log_Stage(run, 'INFO', 'safety', ...
        'dry-run: no instrument connection, query, or write was performed.');
end
catch exception
    remove_failed_run_directory(output_dir);
    rethrow(exception);
end

end

function cfg = default_config()
cfg = struct('ProjectRoot', '', 'RunType', '', 'RunTimestamp', '', ...
    'Parameters', struct(), 'Precision', 0, 'Units', struct(), ...
    'NameParts', {{}}, 'ProjectName', '', 'TestName', '', ...
    'PlannedRunKind', '', 'RunPurpose', 'validation', ...
    'ExecutionMode', '', 'EntryPoint', '', 'Code', struct(), ...
    'CodeVersion', '', 'Runtime', struct(), 'PrimaryVariable', [], ...
    'Counts', struct(), 'Safety', struct(), 'ResultsRoot', '', ...
    'OutputDir', '', 'Inputs', {{}}, 'Instruments', struct([]), ...
    'SourceRuns', struct([]), 'Sources', {{}}, 'Artifacts', struct([]), ...
    'RunInfo', struct());
end

function text = path_text(value, label)
if ~(ischar(value) || (isstring(value) && isscalar(value)))
    error('Result_Create_Run:BadPath', '%s must be text.', label);
end
text = strtrim(char(value));
if isempty(text)
    error('Result_Create_Run:BadPath', '%s cannot be empty.', label);
end
end

function text = required_directory_text(value, label)
if ~(ischar(value) || (isstring(value) && isscalar(value)))
    error('Result_Create_Run:BadPath', '%s must be text.', label);
end
text = char(value);
if isempty(strtrim(text)) || ~isfolder(text)
    error('Result_Create_Run:MissingProjectRoot', ...
        '%s must be an existing directory: %s', label, text);
end
end

function timestamp = normalize_timestamp(value)
if isempty(value)
    timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
else
    timestamp = char(string(value));
end
if isempty(regexp(timestamp, '^\d{8}_\d{6}$', 'once'))
    error('Result_Create_Run:BadTimestamp', ...
        'RunTimestamp must use YYYYMMDD_HHMMSS.');
end
end

function parts = parameter_name_parts(cfg)
% Explicit NameParts keep full Parameters in JSON without lengthening names.
if ~isempty(cfg.NameParts)
    parts = {};
    return;
end
parameters = cfg.Parameters;
if isempty(parameters)
    parts = {};
    return;
end
if ~isstruct(parameters) || ~isscalar(parameters)
    error('Result_Create_Run:BadParameters', 'Parameters must be a scalar struct.');
end
names = fieldnames(parameters);
parts = cell(1, numel(names));
for k = 1:numel(names)
    name = names{k};
    precision = field_value(cfg.Precision, name, 0);
    unit = field_value(cfg.Units, name, '');
    parts{k} = Result_Format_Parameter(name, parameters.(name), precision, unit);
end
end

function value = field_value(container, field_name, default_value)
if isstruct(container)
    if isfield(container, field_name)
        value = container.(field_name);
    else
        value = default_value;
    end
else
    value = container;
end
end

function parts = normalize_name_parts(value)
if isempty(value)
    parts = {};
elseif ischar(value) || (isstring(value) && isscalar(value))
    parts = {char(value)};
elseif isstring(value)
    parts = cellstr(value(:).');
elseif iscell(value)
    parts = cellfun(@char, value, 'UniformOutput', false);
else
    error('Result_Create_Run:BadNameParts', ...
        'NameParts must be text or a cell array of text.');
end
parts = cellfun(@strtrim, parts, 'UniformOutput', false);
for k = 1:numel(parts)
    if isempty(parts{k}) || ~isempty(regexp(parts{k}, '\s', 'once')) || ...
            ~isempty(regexp(parts{k}, '[<>:"/\\|?*\x00-\x1F]', 'once'))
        error('Result_Create_Run:UnsafeNamePart', ...
            'NameParts{%d} is empty or unsafe.', k);
    end
    if ismember(lower(parts{k}), ...
            {'single_point', 'scan', 'dry_run', 'simulation', 'analysis'})
        error('Result_Create_Run:ReservedNamePart', ...
            'NameParts{%d} repeats a result category.', k);
    end
end
end

function value = normalize_generic_array(value)
if isempty(value)
    value = {};
end
end

function out = merge_struct(base, extra)
out = base;
if isempty(extra)
    return;
end
names = fieldnames(extra);
for k = 1:numel(names)
    out.(names{k}) = extra.(names{k});
end
end

function text = current_time_text()
text = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
end

function text = project_name(project_root)
[~, text] = fileparts(project_root);
end

function text = default_text(value, default_value)
text = strtrim(char(string(value)));
if isempty(text)
    text = default_value;
end
end

function value = nullable_run_kind(value)
if isempty(value)
    value = string(missing);
    return;
end
value = lower(strtrim(char(string(value))));
valid = {'single_point', 'scan', 'dry_run', 'simulation', 'analysis'};
if ~ismember(value, valid)
    error('Result_Create_Run:BadPlannedRunKind', ...
        'PlannedRunKind must be empty or a supported run kind.');
end
end

function purpose = normalize_purpose(value)
purpose = lower(strtrim(char(string(value))));
if strcmp(purpose, 'unspecified') || isempty(purpose)
    purpose = 'validation';
end
if ~ismember(purpose, {'formal', 'validation', 'debug'})
    error('Result_Create_Run:BadPurpose', ...
        'RunPurpose must be formal, validation, or debug.');
end
end

function mode = normalize_execution_mode(value, run_kind)
mode = lower(strtrim(char(string(value))));
if isempty(mode) || strcmp(mode, 'unspecified')
    switch run_kind
        case 'dry_run'
            mode = 'dry_run';
        case 'simulation'
            mode = 'simulation';
        case 'analysis'
            mode = 'offline_analysis';
        otherwise
            mode = 'hardware';
    end
elseif strcmp(mode, 'live')
    mode = 'hardware';
end
valid = {'hardware', 'hardware_query', 'dry_run', 'simulation', ...
    'offline_replay', 'offline_analysis'};
if ~ismember(mode, valid)
    error('Result_Create_Run:BadExecutionMode', ...
        'ExecutionMode is not part of the run-info contract.');
end
end

function validate_run_contract(info)
if strcmp(info.run_kind, 'dry_run')
    if ~strcmp(info.execution_mode, 'dry_run') || ~isempty(info.instruments)
        error('Result_Create_Run:UnsafeDryRun', ...
            'dry_run requires dry_run execution mode and no instruments.');
    end
    if null_value(info.planned_run_kind) || ...
            ~ismember(char(info.planned_run_kind), {'single_point', 'scan'})
        error('Result_Create_Run:MissingPlannedRunKind', ...
            'dry_run requires PlannedRunKind single_point or scan.');
    end
elseif ~null_value(info.planned_run_kind)
    error('Result_Create_Run:UnexpectedPlannedRunKind', ...
        'PlannedRunKind is only used by dry_run.');
end
end

function tf = null_value(value)
tf = isempty(value);
if ~tf
    missing_flags = ismissing(value);
    tf = any(missing_flags(:));
end
end

function code = normalize_code(value, code_version)
base = struct('git_commit', string(missing), ...
    'git_dirty', string(missing), 'entry_file_sha256', string(missing));
if isempty(value)
    value = struct();
end
if ~isstruct(value) || ~isscalar(value)
    error('Result_Create_Run:BadCode', 'Code must be a scalar struct.');
end
code = merge_struct(base, value);
if ~isempty(code_version)
    code.version = char(string(code_version));
end
end

function runtime = default_runtime()
runtime = struct('name', 'MATLAB', ...
    'version', ['R', version('-release')], 'os', system_dependent('getos'));
end

function value = nullable_struct(value, label)
if isempty(value)
    value = string(missing);
elseif ~isstruct(value) || ~isscalar(value)
    error('Result_Create_Run:BadNullableStruct', ...
        '%s must be empty or a scalar struct.', label);
end
end

function values = normalize_struct_array(value, label)
if isempty(value)
    values = struct([]);
elseif isstruct(value)
    values = value;
else
    error('Result_Create_Run:BadStructArray', ...
        '%s must be a struct array.', label);
end
end

function counts = normalize_counts(value)
counts = merge_struct(struct('planned', 0, 'executed', 0, ...
    'succeeded', 0, 'failed', 0, 'invalid', 0), value);
names = {'planned', 'executed', 'succeeded', 'failed', 'invalid'};
for k = 1:numel(names)
    validateattributes(counts.(names{k}), {'numeric'}, ...
        {'real', 'finite', 'scalar', 'integer', 'nonnegative'});
end
end

function safety = default_safety()
safety = struct('preflight', 'pending', ...
    'initial_outputs', 'pending', 'shutdown', 'pending', ...
    'shutdown_readback', 'pending');
end

function records = normalize_source_runs(value)
if isempty(value)
    records = struct('run_id', {}, 'path', {});
elseif isstruct(value)
    records = value;
elseif ischar(value) || isstring(value) || iscell(value)
    if ischar(value) || (isstring(value) && isscalar(value))
        paths = {char(value)};
    elseif isstring(value)
        paths = cellstr(value(:).');
    else
        paths = cellfun(@char, value(:).', 'UniformOutput', false);
    end
    records = repmat(struct('run_id', '', 'path', ''), 1, numel(paths));
    for k = 1:numel(paths)
        [~, records(k).run_id] = fileparts(paths{k});
        records(k).path = paths{k};
    end
else
    error('Result_Create_Run:BadSourceRuns', ...
        'SourceRuns must be a struct array or list of paths.');
end
end

function records = artifact_records(value, default_role)
if isempty(value)
    records = struct('file', {}, 'role', {}, 'sha256', {});
    return;
end
if isstruct(value)
    records = repmat(struct('file', '', 'role', '', ...
        'sha256', string(missing)), 1, numel(value));
    for k = 1:numel(value)
        if ~isfield(value, 'file')
            error('Result_Create_Run:BadArtifacts', ...
                'Each artifact record must contain file.');
        end
        records(k).file = char(string(value(k).file));
        records(k).role = default_role;
        if isfield(value, 'role') && ~isempty(value(k).role)
            records(k).role = char(string(value(k).role));
        end
        if isfield(value, 'sha256') && ~isempty(value(k).sha256)
            records(k).sha256 = char(string(value(k).sha256));
        end
    end
else
    if ischar(value) || (isstring(value) && isscalar(value))
        files = {char(value)};
    elseif isstring(value)
        files = cellstr(value(:).');
    elseif iscell(value)
        files = cellfun(@char, value(:).', 'UniformOutput', false);
    else
        error('Result_Create_Run:BadArtifacts', ...
            'Artifacts must be a struct array or list of file names.');
    end
    records = repmat(struct('file', '', 'role', default_role, ...
        'sha256', string(missing)), 1, numel(files));
    for k = 1:numel(files)
        records(k).file = files{k};
    end
end
end

function out = merge_artifacts(first, second)
out = [first, second];
if isempty(out)
    return;
end
[~, keep] = unique({out.file}, 'stable');
out = out(sort(keep));
end

function info = remove_legacy_fields(info)
legacy = {'run_type', 'run_purpose', 'start_time', 'end_time', ...
    'code_version', 'sources'};
present = intersect(legacy, fieldnames(info));
if ~isempty(present)
    info = rmfield(info, present);
end
end

function remove_failed_run_directory(path)
if isfolder(path)
    [ok, message] = rmdir(path, 's');
    if ~ok
        warning('Result_Create_Run:CleanupFailed', ...
            'Could not remove failed run directory %s: %s', path, message);
    end
end
end
