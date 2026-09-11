function output = Multistream_Workbench(action, profile, selector, varargin)
%MULTISTREAM_WORKBENCH Human entry point for isolated single-carrier V2.
%
% Multistream_Workbench()                         dry-run first condition
% Multistream_Workbench('matrix')                inspect experiment matrix
% Multistream_Workbench('generate',[],1,seed)    generate one waveform
% Multistream_Workbench('simulation')            persistent dual-stream simulation
% Multistream_Workbench('traditional_simulation') WZ traditional simulation
% Multistream_Workbench('preflight',[],1)        read-only instrument IDN
% Multistream_Workbench('awg_off_check_dry_run') plan V212 without I/O
% Multistream_Workbench('awg_off_check')         execute AWG/scope-only V212
% Multistream_Workbench('single_dac_smoke_dry_run') plan V213 without I/O
% Multistream_Workbench('single_dac_smoke')      execute AWG/scope-only V213
% Multistream_Workbench('hardware',[],1)         confirmed formal hardware
% Multistream_Workbench('replay',[],run_dir)     offline replay

root = fileparts(mfilename('fullpath'));
addpath(fullfile(root, 'code'));
addpath(fullfile(root, 'code', 'result_management'));
addpath(fullfile(root, 'code', 'plotting'));
if nargin < 1 || isempty(action), action = 'dry_run'; end
action = lower(char(string(action)));
if nargin < 2 || isempty(profile)
    if ismember(action, {'traditional_simulation','simulation_traditional'})
        profile = 'v2_traditional_wz';
    else
        profile = 'v2_default';
    end
end
cfg = msiq.build_config(profile);

if strcmp(action,'rerun')
    if nargin < 3 || isempty(selector)
        error('Multistream_Workbench:RerunPath','rerun requires a source simulation directory.');
    end
    options = struct();
    if ~isempty(varargin), options = varargin{1}; end
    output = msiq.rerun_simulation(selector,options);
    return;
end
if strcmp(action, 'replot')
    if nargin < 3 || isempty(selector)
        error('Multistream_Workbench:ReplotPath','replot requires a source run directory.');
    end
    output = msiq.replot_run(selector);
    return;
end
if strcmp(action, 'replay')
    if nargin < 3 || isempty(selector)
        error('Multistream_Workbench:ReplayPath', ...
            'Replay requires a source run directory.');
    end
    overrides = struct();
    if ~isempty(varargin), overrides = varargin{1}; end
    output = msiq.replay_run(selector, overrides);
    return;
end

if ismember(action,{'simulation','traditional_simulation','simulation_traditional','dry_run'}) ...
        && ~isempty(varargin)
    options = varargin{1};
    effective_options = cfg.results;
    names = fieldnames(options);
    for k = 1:numel(names), effective_options.(names{k}) = options.(names{k}); end
    policy = msiq.output_policy(effective_options);
    cfg.results.output_level = policy.output_level;
    cfg.results.write_results = policy.write_results;
    if isfield(options,'results_root'), cfg.results_root = options.results_root; end
    if isfield(options,'source_run'), cfg.results.source_run = options.source_run; end
end
matrix = msiq.build_experiment_matrix(cfg);
if strcmp(action, 'matrix')
    output = matrix;
    fprintf('Formal conditions: %d (indoor %d, 1 km N=1 %d, 1 km N=2-4 %d)\n', ...
        matrix.counts.formal_total, matrix.counts.indoor_formal, ...
        matrix.counts.one_km_single, matrix.counts.one_km_multichannel);
    return;
end
if nargin < 3 || isempty(selector)
    if ismember(action, {'traditional_simulation','simulation_traditional'})
        selector = find(strcmp({matrix.conditions.architecture}, ...
            'single_complex_stream'), 1);
    elseif ismember(action, {'simulation', 'single_dac_smoke', ...
            'single_dac_smoke_dry_run','v213','v213_dry_run'})
        selector = find(strcmp({matrix.conditions.architecture}, ...
            'dual_iq_mimo'), 1);
    else
        selector = 1;
    end
end
condition = select_condition(matrix.conditions, selector);

switch action
    case 'dry_run'
        output = msiq.run_condition(cfg, condition, 'dry_run');
    case 'simulation'
        output = msiq.run_condition(cfg, condition, 'simulation');
    case {'traditional_simulation','simulation_traditional'}
        output = msiq.run_condition(cfg, condition, 'simulation');
    case {'preflight','instrument_preflight'}
        output = msiq.run_condition(cfg, condition, 'hardware_query');
    case {'awg_off_check','v212'}
        output = msiq.run_condition(cfg, condition, 'awg_off_check');
    case {'awg_off_check_dry_run','v212_dry_run'}
        output = msiq.run_condition(cfg, condition, 'awg_off_check_dry_run');
    case {'single_dac_smoke','v213'}
        output = msiq.run_condition(cfg, condition, 'single_dac_smoke');
    case {'single_dac_smoke_dry_run','v213_dry_run'}
        output = msiq.run_condition(cfg, condition, 'single_dac_smoke_dry_run');
    case 'hardware'
        output = msiq.run_condition(cfg, condition, 'hardware');
    case 'generate'
        if isempty(varargin)
            seed = condition.repeat_plan(1).seed;
        else
            seed = varargin{1};
        end
        cfg.waveform.architecture = condition.architecture;
        [waveforms, tx_ref] = msiq.generate_waveforms(cfg, seed);
        output = struct('waveforms',waveforms,'tx_ref',tx_ref, ...
            'preflight',msiq.preflight_waveform(waveforms,cfg,cfg.awg.model));
    otherwise
        error('Multistream_Workbench:Action', ...
            'Unknown action: %s', action);
end
end

function condition = select_condition(conditions, selector)
if isnumeric(selector)
    validateattributes(selector, {'numeric'}, ...
        {'scalar','integer','positive','<=',numel(conditions)});
    condition = conditions(selector);
else
    index = find(strcmpi({conditions.condition_id}, char(string(selector))), 1);
    if isempty(index)
        error('Multistream_Workbench:Condition', ...
            'Unknown condition: %s', char(string(selector)));
    end
    condition = conditions(index);
end
end
