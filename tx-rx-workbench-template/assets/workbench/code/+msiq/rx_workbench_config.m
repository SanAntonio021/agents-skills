function cfg = rx_workbench_config(options)
%RX_WORKBENCH_CONFIG Keep injected RX tests independent of local instruments.
if isfield(options,'config') && ~isempty(options.config)
    synchronous_mock = ~options.asynchronous && options.injected_io;
    asynchronous_mock = options.asynchronous && ~isempty(options.worker_factory);
    if ~(synchronous_mock || asynchronous_mock)
        error('RX_Workbench:TestConfig', ...
            'Configuration injection requires complete mock I/O or a mock worker factory.');
    end
    profile = options.config;
    if ~isstruct(profile) || ~isscalar(profile) || ~isfield(profile,'instrument') || ...
            ~isstruct(profile.instrument) || ~isscalar(profile.instrument)
        error('RX_Workbench:TestConfig','Injected configuration must be a scalar profile structure.');
    end
    % Clear before build_config: replacing the scope afterward still reads local JSON.
    profile.instrument.local_config = '';
    cfg = msiq.build_config(profile);
else
    cfg = msiq.build_config('v2_traditional_wz');
end
if ~isfield(cfg.instrument,'scope') || ~isstruct(cfg.instrument.scope) || ...
        ~isscalar(cfg.instrument.scope) || isempty(fieldnames(cfg.instrument.scope))
    error('RX_Workbench:ScopeConfig', ...
        ['Missing scope configuration. Configure config/instruments.local.json ' ...
        'using instruments.local.example.json before opening the hardware workbench.']);
end
end
