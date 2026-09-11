function record = load_reference_bundle(path)
record = load(path,'bundle');
if isfield(record.bundle,'shared_data')
    data = msiq.shared_tx_data('load',fileparts(path),record.bundle.shared_data);
    record.bundle.tx_ref = data.tx_ref;
end
end
