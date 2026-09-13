function path = Result_Artifact_Path(run_or_dir, name)
%RESULT_ARTIFACT_PATH Resolve v2 data records with legacy root fallback.
name = char(name);
if isempty(name) || ~isempty(regexp(name, '[<>:"/\\|?*\x00-\x1F]', 'once')) || ismember(name, {'.', '..'})
    error('Result_Artifact_Path:Name', 'Name must be a single safe file name.');
end
if isstruct(run_or_dir)
    root = run_or_dir.OutputDir;
else
    root = char(run_or_dir);
end
path = fullfile(root, 'data', name);
legacy = fullfile(root, name);
if ~isfile(path) && (isfile(legacy) || ~isfolder(fullfile(root, 'data')))
    path = legacy;
end
end
