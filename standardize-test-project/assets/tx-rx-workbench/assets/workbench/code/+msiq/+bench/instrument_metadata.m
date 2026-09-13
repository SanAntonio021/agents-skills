function metadata = instrument_metadata(specs)
%INSTRUMENT_METADATA Build run metadata without a signal-generator role.

names = {'awg','scope'};
roles = {'waveform_generator','oscilloscope'};
metadata = repmat(struct('role','','resource',''), 1, 2);
for k = 1:2
    metadata(k).role = roles{k};
    if isfield(specs.(names{k}), 'resource')
        metadata(k).resource = char(string(specs.(names{k}).resource));
    elseif isfield(specs.(names{k}), 'mock') && specs.(names{k}).mock
        metadata(k).resource = 'MOCK';
    end
end
end
