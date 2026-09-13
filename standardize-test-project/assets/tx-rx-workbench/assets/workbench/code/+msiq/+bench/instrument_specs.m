function specs = instrument_specs(cfg)
%INSTRUMENT_SPECS Return the AWG/scope-only V212/V213 specifications.

required = {'awg','scope'};
for k = 1:numel(required)
    if ~isfield(cfg.instrument, required{k})
        error('msiq:instrument:LocalConfigRequired', ...
            ['Missing cfg.instrument.%s. Create config/instruments.local.json ', ...
            'from the example before V212/V213 instrument access.'], required{k});
    end
end
specs = struct('awg', cfg.instrument.awg, 'scope', cfg.instrument.scope);
end
