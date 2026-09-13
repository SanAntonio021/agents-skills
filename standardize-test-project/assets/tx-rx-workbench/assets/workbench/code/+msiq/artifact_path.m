function path = artifact_path(run_dir, name, mode)
%ARTIFACT_PATH Resolve manual-loopback artifacts across old and new layouts.

if nargin < 3 || isempty(mode)
    mode = 'read';
end
prefix = '';
if isstruct(run_dir) && isscalar(run_dir) && isfield(run_dir, 'run_dir')
    if isfield(run_dir, 'artifact_prefix')
        prefix = char(string(run_dir.artifact_prefix));
    end
    run_dir = run_dir.run_dir;
end
if ~(ischar(run_dir) || (isstring(run_dir) && isscalar(run_dir)))
    error('msiq:artifactPath:RunDirectory', ...
        'run_dir must be a path string.');
end
if ~(ischar(name) || (isstring(name) && isscalar(name))) || isempty(name)
    error('msiq:artifactPath:Name', 'Artifact name must be a nonempty string.');
end

run_dir = char(string(run_dir));
name = char(string(name));
if ~isempty(prefix)
    if isempty(regexp(prefix, '^[A-Za-z0-9_-]+$', 'once'))
        error('msiq:artifactPath:Prefix', 'Invalid artifact prefix.');
    end
    name = [prefix, '_', name];
end
diagnostics_dir = fullfile(run_dir, 'data');
mode = lower(char(string(mode)));
[~,~,extension] = fileparts(name);
if ismember(lower(extension), {'.png','.jpg','.jpeg','.svg','.pdf','.tif','.tiff'})
    path = fullfile(run_dir, name);
    return;
end

switch mode
    case 'write'
        if ~isfolder(diagnostics_dir)
            [ok, message] = mkdir(diagnostics_dir);
            if ~ok
                error('msiq:artifactPath:CreateDirectory', ...
                    'Cannot create diagnostics directory %s: %s.', ...
                    diagnostics_dir, message);
            end
        end
        path = fullfile(diagnostics_dir, name);
    case 'read'
        candidate = fullfile(diagnostics_dir, name);
        if isfile(candidate)
            path = candidate;
            return;
        end
        candidate = fullfile(run_dir, 'diagnostics', name);
        if isfile(candidate)
            path = candidate;
            return;
        end
        if endsWith(name,'tx_reference_bundle.mat')
            pointer = fullfile(diagnostics_dir,strrep(name, ...
                'tx_reference_bundle.mat','tx_reference_source.json'));
            if isfile(pointer)
                reference = jsondecode(fileread(pointer));
                path = reference.source_path;
                if isfield(reference,'local_file')
                    path = fullfile(diagnostics_dir,reference.local_file);
                end
                if ~isfile(path) || ~strcmpi(reference.sha256,compute_file_sha256(path))
                    error('msiq:artifactPath:ReferenceChanged', ...
                        'Saved reference is missing or changed: %s.',path);
                end
                return;
            end
        end
        path = fullfile(run_dir, name);
    otherwise
        error('msiq:artifactPath:Mode', ...
            'Mode must be read or write, got %s.', mode);
end
end
