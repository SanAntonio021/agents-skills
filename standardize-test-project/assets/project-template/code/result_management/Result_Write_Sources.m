function path = Result_Write_Sources(run_or_path, sources)
%RESULT_WRITE_SOURCES Write source run directories for cross-run analysis.

output_dir = resolve_output_dir(run_or_path);
path = Result_Artifact_Path(output_dir, 'sources.txt');
if exist(path, 'file')
    error('Result_Write_Sources:SourcesExist', ...
        'sources.txt already exists and will not be overwritten: %s', path);
end
sources = normalize_sources(sources);
if isempty(sources)
    error('Result_Write_Sources:TooFewSources', ...
        'Analysis requires at least one source run directory.');
end
for k = 1:numel(sources)
    if strcmpi(char(java.io.File(sources{k}).getCanonicalPath()), char(java.io.File(output_dir).getCanonicalPath()))
        error('Result_Write_Sources:SameRun', 'Analysis must use a new output directory.');
    end
    if ~isfolder(sources{k})
        error('Result_Write_Sources:MissingSource', ...
            'Source directory does not exist: %s', sources{k});
    end
end
display_sources = relative_sources(run_or_path, output_dir, sources);

fid = fopen(path, 'w', 'n', 'UTF-8');
if fid < 0
    error('Result_Write_Sources:OpenFailed', ...
        'Cannot create sources.txt: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
for k = 1:numel(display_sources)
    fprintf(fid, '%s\n', display_sources{k});
end

run_info_path = Result_Artifact_Path(output_dir, 'run_info.json');
if exist(run_info_path, 'file')
    info = Result_Update_Run_Info(run_info_path, struct());
    artifacts = normalize_artifacts(info);
    artifacts = merge_artifacts(artifacts, ...
        artifact_record(strrep(erase(path, [output_dir, filesep]), '\', '/'), 'source_list'));
    source_runs = build_source_runs(sources, display_sources);
    updates = struct();
    updates.source_runs = source_runs;
    updates.artifacts = artifacts;
    Result_Update_Run_Info(run_info_path, updates);
end
end

function values = relative_sources(run_or_path, output_dir, sources)
if isstruct(run_or_path) && isfield(run_or_path, 'ProjectRoot')
    project_root = char(run_or_path.ProjectRoot);
else
    project_root = fileparts(fileparts(fileparts(output_dir)));
end
prefix = [char(java.io.File(project_root).getCanonicalPath()), filesep];
values = sources;
for k = 1:numel(sources)
    source_path = char(java.io.File(sources{k}).getCanonicalPath());
    if startsWith(lower(source_path), lower(prefix))
        values{k} = strrep(source_path(numel(prefix) + 1:end), '\', '/');
    end
end
end

function output_dir = resolve_output_dir(value)
if isstruct(value) && isfield(value, 'OutputDir')
    output_dir = value.OutputDir;
elseif ischar(value) || (isstring(value) && isscalar(value))
    output_dir = char(value);
    if ~isfolder(output_dir)
        output_dir = fileparts(output_dir);
    end
else
    error('Result_Write_Sources:BadTarget', ...
        'Target must be a run struct, run directory, or file path.');
end
end

function values = normalize_sources(value)
if ischar(value) || (isstring(value) && isscalar(value))
    values = {char(value)};
elseif isstring(value)
    values = cellstr(value(:).');
elseif iscell(value)
    values = cellfun(@char, value(:).', 'UniformOutput', false);
else
    error('Result_Write_Sources:BadSources', ...
        'Sources must be text or a cell array of text.');
end
if isempty(values)
    error('Result_Write_Sources:MissingSources', ...
        'At least one source directory is required.');
end
end

function artifacts = normalize_artifacts(info)
if ~isfield(info, 'artifacts') || isempty(info.artifacts)
    artifacts = struct('file', {}, 'role', {}, 'sha256', {});
elseif isstruct(info.artifacts)
    artifacts = info.artifacts(:).';
else
    error('Result_Write_Sources:BadArtifacts', ...
        'run_info.json artifacts must be an object array.');
end
end

function records = build_source_runs(sources, display_sources)
records = repmat(struct('run_id', '', 'path', ''), 1, numel(sources));
for k = 1:numel(sources)
    [~, base, suffix] = fileparts(sources{k});
    records(k).run_id = [base, suffix];
    records(k).path = display_sources{k};
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
