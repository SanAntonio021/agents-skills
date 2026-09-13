function delta = audit_delta(before, after)
%AUDIT_DELTA Subtract scalar instrument audit counters.

names = fieldnames(before);
delta = struct();
for k = 1:numel(names)
    delta.(names{k}) = after.(names{k})-before.(names{k});
end
end
