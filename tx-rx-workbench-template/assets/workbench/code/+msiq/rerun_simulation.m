function output = rerun_simulation(source_run, options)
%RERUN_SIMULATION Start a new simulation from recorded effective configuration.
if nargin < 2, options = struct(); end
info = jsondecode(fileread(msiq.artifact_path(source_run,'run_info.json')));
if ~strcmp(info.execution_mode,'simulation') || ~isfield(info.parameters,'effective_config')
    error('msiq:rerun:Configuration','This run has no complete saved simulation configuration.');
end
cfg = info.parameters.effective_config;
condition = info.parameters.condition;
archive_path = msiq.artifact_path(source_run,'plot_data.mat');
if isfile(archive_path)
    stored = load(archive_path);
    if isfield(stored,'effective_config'), cfg = stored.effective_config; end
    if isfield(stored,'condition'), condition = stored.condition; end
end
current = msiq.build_config('v2_default');
cfg.project_root = current.project_root;
cfg.code_root = current.code_root;
cfg.results_root = current.results_root;
for name = {'receiver','simulation'}
    if isfield(options,name{1})
        fields = fieldnames(options.(name{1}));
        for k = 1:numel(fields)
            cfg.(name{1}).(fields{k}) = options.(name{1}).(fields{k});
        end
    end
end
policy = msiq.output_policy(options);
if isfield(cfg.results,'save_raw'), cfg.results = rmfield(cfg.results,'save_raw'); end
cfg.results.output_level = policy.output_level;
cfg.results.write_results = policy.write_results;
cfg.results.source_run = char(java.io.File(source_run).getCanonicalPath());
if isfield(options,'results_root'), cfg.results_root = options.results_root; end
output = msiq.run_condition(cfg,condition,'simulation');
end
