function value = analysis_record(value)
%ANALYSIS_RECORD Retain derived metrics and source provenance, not DSP workspaces.
if isstruct(value)
    names = intersect(fieldnames(value), ...
        {'raw','tx_ref','waveforms','decoded','sync','synchronization'});
    value = rmfield(value,names);
    names = fieldnames(value);
    for k = 1:numel(value)
        for j = 1:numel(names)
            value(k).(names{j}) = msiq.analysis_record(value(k).(names{j}));
        end
        for name = {'source_path','bundle_path','raw_path'}
            if isfield(value,name{1}) && ischar(value(k).(name{1})) ...
                    && isfile(value(k).(name{1}))
                value(k).([name{1},'_sha256']) = msiq.file_sha256(value(k).(name{1}));
            end
        end
    end
elseif iscell(value)
    for k = 1:numel(value), value{k} = msiq.analysis_record(value{k}); end
end
end
