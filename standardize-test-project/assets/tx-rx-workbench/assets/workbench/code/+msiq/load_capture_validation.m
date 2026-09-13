function saved = load_capture_validation(run_dir)
%LOAD_CAPTURE_VALIDATION Support preparation files and compacted old runs.
path = msiq.artifact_path(run_dir, 'capture_preparation.mat', 'read');
pointer = msiq.artifact_path(run_dir, 'capture_source.json', 'read');
if ~isfile(path) && isfile(pointer)
    source = jsondecode(fileread(pointer));
    path = source.validation_path;
    if ~isfile(path) || ~strcmpi(compute_file_sha256(path), source.validation_sha256)
        error('msiq:captureArtifact:SourceChanged', 'Capture source is missing or changed: %s.', path);
    end
end
if ~isfile(path)
    path = msiq.artifact_path(run_dir, 'demod_result.mat', 'read');
end
if ~isfile(path)
    error('msiq:captureArtifact:Missing', 'Missing capture validation in %s.', run_dir);
end
saved = load(path, 'validation');
if ~isfield(saved, 'validation')
    error('msiq:captureArtifact:Invalid', 'Missing validation variable in %s.', path);
end
end
