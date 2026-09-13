function cfg = apply_reference(cfg, tx_ref)
%APPLY_REFERENCE Restore code identity, never a sender's private file path.
if ~isfield(tx_ref, 'fec_config'), return; end
source = tx_ref.fec_config;
names = {'family','frame_type','rate_numerator','rate_denominator'};
for k = 1:numel(names)
    cfg.fec.(names{k}) = source.(names{k});
end
cfg.fec.rate = cfg.fec.rate_numerator / cfg.fec.rate_denominator;
msiq.fec.specification(cfg);
end
