function report = verify_historical_results()
%VERIFY_HISTORICAL_RESULTS Verify every path frozen before isolated V2 work.

root = msiq.project_root();
baseline_path = fullfile(root, 'docs', 'v2_baseline', ...
    'historical_results_baseline_v2.json');
baseline = read_json_utf8(baseline_path);
manifest_path = fullfile(root, strrep(baseline.manifest, '/', filesep));
if ~isfile(manifest_path)
    error('msiq:history:ManifestMissing', ...
        'Historical manifest is missing: %s', manifest_path);
end
manifest_hash = compute_file_sha256(manifest_path);
if ~strcmpi(manifest_hash, baseline.manifest_sha256)
    error('msiq:history:ManifestChanged', ...
        'Historical manifest SHA256 no longer matches its frozen baseline.');
end

manifest = readtable(manifest_path, 'TextType', 'string');
missing = strings(0,1);
changed = strings(0,1);
current_bytes = uint64(0);
for row = 1:height(manifest)
    relative = char(manifest.path(row));
    absolute = fullfile(root, strrep(relative, '/', filesep));
    if ~isfile(absolute)
        missing(end+1,1) = string(relative); %#ok<AGROW>
        continue;
    end
    details = dir(absolute);
    current_bytes = current_bytes + uint64(details.bytes);
    if details.bytes ~= manifest.bytes(row) || ...
            ~strcmpi(compute_file_sha256(absolute), manifest.sha256(row))
        changed(end+1,1) = string(relative); %#ok<AGROW>
    end
end
manifest_paths = string(manifest.path);
[legacy_paths, ignored_v2_count, ignored_post_baseline_count, ...
    ignored_post_baseline_roots] = current_legacy_result_paths( ...
    root, char(string(baseline.root)), manifest_paths, ...
    char(string(baseline.created_at)));
extra = legacy_paths(~ismember(lower(legacy_paths), lower(manifest_paths)));
metadata_ok = height(manifest) == double(baseline.file_count) && ...
    current_bytes == uint64(baseline.total_bytes);
report = struct('ok', metadata_ok && isempty(missing) && ...
    isempty(changed) && isempty(extra), ...
    'expected_file_count', baseline.file_count, ...
    'verified_file_count', height(manifest)-numel(missing), ...
    'legacy_file_count', numel(legacy_paths), ...
    'expected_total_bytes', uint64(baseline.total_bytes), ...
    'verified_total_bytes', current_bytes, ...
    'manifest_sha256', manifest_hash, ...
    'missing', missing, 'changed', changed, 'extra', extra, ...
    'ignored_v2_file_count', ignored_v2_count, ...
    'ignored_post_baseline_file_count', ignored_post_baseline_count, ...
    'ignored_post_baseline_roots', ignored_post_baseline_roots, ...
    'new_v2_files_ignored', true);
end

function [paths, ignored_count, ignored_post_baseline_count, ...
        ignored_post_baseline_roots] = current_legacy_result_paths( ...
        root, result_root, baseline_paths, baseline_created_at)
absolute_root = fullfile(root, strrep(result_root, '/', filesep));
items = dir(fullfile(absolute_root, '**', '*'));
items = items(~[items.isdir]);
paths = strings(numel(items), 1);
root_prefix = [root, filesep];
for k = 1:numel(items)
    absolute = fullfile(items(k).folder, items(k).name);
    relative = absolute((numel(root_prefix)+1):end);
    paths(k) = string(strrep(relative, filesep, '/'));
end
v2_roots = ["results/single_point/", "results/scan/", ...
    "results/dry_run/", "results/simulation/", "results/analysis/"];
ignored = false(size(paths));
for k = 1:numel(v2_roots)
    ignored = ignored | startsWith(lower(paths), lower(v2_roots(k)));
end
% New top-level run directories are valid post-baseline artifacts. Keep
% additions inside an existing frozen run visible as historical extras.
post_baseline = false(size(paths));
post_baseline_roots = strings(0, 1);
result_prefix = [char(string(result_root)), '/'];
for k = 1:numel(paths)
    if ignored(k)
        continue;
    end
    relative = char(paths(k));
    if ~startsWith(lower(relative), lower(result_prefix))
        continue;
    end
    remainder = relative((numel(result_prefix)+1):end);
    slash = strfind(remainder, '/');
    if isempty(slash)
        continue;
    end
    child = remainder(1:(slash(1)-1));
    child_prefix = [result_prefix, child, '/'];
    if ~any(startsWith(lower(baseline_paths), lower(child_prefix))) && ...
            is_post_baseline_timestamp(child, baseline_created_at)
        post_baseline(k) = true;
        post_baseline_roots(end+1, 1) = string(child); %#ok<AGROW>
    end
end
ignored_post_baseline_count = nnz(post_baseline);
ignored_post_baseline_roots = unique(post_baseline_roots, 'stable');
ignored_count = nnz(ignored);
paths = paths(~ignored & ~post_baseline);
end

function tf = is_post_baseline_timestamp(name, baseline_created_at)
% Only timestamped runs created after the frozen baseline are auto-classified.
tf = false;
baseline_token = char(string(baseline_created_at));
if numel(baseline_token) < 19
    return;
end
try
    baseline_time = datetime(baseline_token(1:19), ...
        'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss');
catch
    return;
end
tokens = regexp(name, '(\d{8}_\d{6})$', 'tokens', 'once');
if isempty(tokens)
    return;
end
try
    run_time = datetime(tokens{1}, 'InputFormat', 'yyyyMMdd_HHmmss');
    tf = run_time > baseline_time;
catch
    tf = false;
end
end

function value = read_json_utf8(path)
fid = fopen(path, 'r');
if fid < 0
    error('msiq:history:BaselineOpen', ...
        'Cannot open historical baseline: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
bytes = fread(fid, Inf, '*uint8').';
if numel(bytes) >= 3 && isequal(bytes(1:3), uint8([239 187 191]))
    bytes = bytes(4:end);
end
value = jsondecode(native2unicode(bytes, 'UTF-8'));
end
