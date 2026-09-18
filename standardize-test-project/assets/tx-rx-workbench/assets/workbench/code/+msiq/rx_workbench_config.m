function cfg = rx_workbench_config(options)
%RX_WORKBENCH_CONFIG Keep injected RX tests independent of local instruments.
if isfield(options,'native_simulation') && options.native_simulation
    assert(~isfield(options,'config') || isempty(options.config),'RX_Workbench:TestConfig', ...
        '模拟参数请使用 options.simulation；config 注入仅用于显式 mock 测试');
    cfg=msiq.rx_simulation_config(options.simulation);
    cfg=result_root(cfg,options); return;
end
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
    cfg.instrument.scope=struct(); % Opening the UI does not require a hardware address.
end
cfg=result_root(cfg,options);
end
function cfg=result_root(cfg,options)
if isfield(options,'results_root') && ~isempty(options.results_root)
    validateattributes(options.results_root,{'char','string'},{'nonempty'});
    cfg.results_root=char(options.results_root); cfg.results.root=cfg.results_root;
end
end
