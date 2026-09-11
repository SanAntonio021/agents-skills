function record = load_tx_reference(path)
record = load(path);
if isfield(record,'shared_data')
    data = msiq.shared_tx_data('load',fileparts(path),record.shared_data);
    record.tx_ref = data.tx_ref;
end
end
