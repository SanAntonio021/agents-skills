function run = create_output_run(cfg, category, name, requested)
%CREATE_OUTPUT_RUN Share automatic names and collision protection with V2.
if nargin < 4, requested = ''; end
addpath(fullfile(cfg.code_root, 'result_management'));
root = cfg.results_root;
[~,leaf] = fileparts(root);
if ismember(leaf,{'simulation','measurement','analysis','checks'})
    root = fileparts(root);
end
mode = 'hardware';
kind = 'single_point';
if strcmp(category,'analysis'), mode = 'offline_analysis'; kind = 'analysis'; end
if strcmp(category,'simulation'), mode = 'simulation'; kind = 'simulation'; end
if strcmp(category,'checks'), mode = 'dry_run'; kind = 'dry_run'; end
settings = struct('ProjectRoot',cfg.project_root,'ResultsRoot',root, ...
    'OutputCategory',category,'RunType',kind,'ExecutionMode',mode, ...
    'NameParts',{{name}},'ProjectName','multistream_iq_SC', ...
    'Parameters',struct('waveform',cfg.waveform,'receiver',cfg.receiver));
if strcmp(mode,'dry_run'), settings.PlannedRunKind='single_point'; end
if ~isempty(requested), settings.OutputDir = requested; end
run = Result_Create_Run(settings);
end
