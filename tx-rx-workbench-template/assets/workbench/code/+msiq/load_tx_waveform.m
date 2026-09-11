function saved = load_tx_waveform(run_dir)
%LOAD_TX_WAVEFORM Read legacy waveforms or the canonical TX manifest.
path = msiq.artifact_path(run_dir, 'tx_waveform.mat', 'read');
if isfile(path)
    saved = load(path);
    return;
end
path = msiq.artifact_path(run_dir, 'tx_manifest.mat', 'read');
if ~isfile(path)
    path = msiq.artifact_path(run_dir, 'awg_plan.mat', 'read');
end
if ~isfile(path)
    error('msiq:txArtifact:Missing', 'Missing TX waveform or plan in %s.', run_dir);
end
source = msiq.load_tx_manifest(path);
required = {'waveforms','route','desired','cfg'};
if ~isfield(source, 'plan') || ~all(isfield(source.plan, required))
    error('msiq:txArtifact:Invalid', 'Incomplete TX plan in %s.', path);
end
saved = struct();
for k = 1:numel(required)
    saved.(required{k}) = source.plan.(required{k});
end
end
