function save_reference_bundle(path,bundle,source_path)
%SAVE_REFERENCE_BUNDLE Share references within a run; exported bundles stay portable.
if isfield(bundle,'shared_data')
    source_root = char(java.io.File(fullfile(fileparts(source_path), ...
        bundle.shared_data.scope)).getCanonicalPath());
    destination = char(java.io.File(fileparts(path)).getCanonicalPath());
    if strcmpi(source_root,destination) || startsWith(lower(destination),[lower(source_root),filesep])
        bundle.shared_data = msiq.shared_tx_data('relocate', ...
            fileparts(source_path),bundle.shared_data,fileparts(path));
        bundle = rmfield(bundle,'tx_ref');
    else
        bundle = rmfield(bundle,'shared_data');
    end
end
msiq.atomic_save(path,struct('bundle',bundle));
end
