function record = load_tx_manifest(path)
record = load(path);
if isfield(record.plan,'shared_data')
    data = msiq.shared_tx_data('load',fileparts(path),record.plan.shared_data);
    for name = {'waveforms','download','tx_ref'}
        record.plan.(name{1}) = data.(name{1});
    end
    record.plan.storage_run_root = char(java.io.File(fullfile( ...
        fileparts(path),record.plan.shared_data.scope)).getCanonicalPath());
    record.plan.run_dir = fileparts(fileparts(path));
    record.plan.diagnostics_dir = fileparts(path);
    record.plan.reference_bundle_path = msiq.artifact_path(record.plan,'tx_reference_bundle.mat');
    record.plan.tx_dashboard_path = msiq.artifact_path(record.plan,'fig_tx_dashboard.png');
end
end
