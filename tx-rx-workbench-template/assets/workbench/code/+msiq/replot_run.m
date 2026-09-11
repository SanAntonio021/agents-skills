function output = replot_run(source_run, options)
%REPLOT_RUN Export saved figures into a new analysis run without decoding.
if nargin < 2, options = struct(); end
source_run = char(string(source_run));
files = dir(fullfile(source_run,'data','*.fig'));
if isempty(files), files = dir(fullfile(source_run,'*.fig')); end
cfg = msiq.build_config('v2_default');
if isfield(options,'results_root'), cfg.results_root = options.results_root; end
addpath(fullfile(cfg.code_root,'plotting'));
run = msiq.create_output_run(cfg,'analysis','重绘图片','');
Result_Write_Sources(run,{source_run});
Result_Summary_Initialize(run,{'序号','图片','状态','来源文件'}, ...
    {'-','-','-','-'},struct('DisplayColumns',{{'序号','图片','状态'}}));
archive = msiq.artifact_path(source_run,'plot_data.mat','read');
if isfile(archive) || isempty(files)
    result = replot_saved_data(source_run,run.OutputDir,archive);
    images = result.paths;
    for k = 1:numel(images)
        [~,name,ext] = fileparts(images{k});
        Result_Summary_Append(run,{k,[name ext],'成功',source_run});
    end
    Result_Update_Run_Info(run,struct('counts',struct('planned',numel(images), ...
        'executed',numel(images),'succeeded',numel(images),'failed',0,'invalid',0)));
    Result_Finalize_Run(run,'completed','normal_completion',[], '');
    output = result;
    output.run_dir = run.OutputDir;
    output.images = images;
    output.source_unchanged = true;
    return;
end
images = cell(1,numel(files));
for k = 1:numel(files)
    fig = openfig(fullfile(files(k).folder,files(k).name),'invisible');
    cleanup = onCleanup(@() close(fig));
    properties = struct();
    if isappdata(fig,'TestProjectOriginalGeometry')
        properties = getappdata(fig,'TestProjectOriginalGeometry');
    else
        stored = load(fullfile(files(k).folder,files(k).name),'-mat');
        keys = fieldnames(stored);
        keys = keys(startsWith(keys,'hgS_'));
        for key_index = 1:numel(keys)
            value = stored.(keys{key_index});
            if isstruct(value) && isscalar(value) && isfield(value,'properties')
                properties = value.properties;
                break;
            end
        end
        if isempty(fieldnames(properties))
            keys = fieldnames(stored);
            keys = keys(startsWith(keys,'hgM_'));
            for key_index = 1:numel(keys)
                value = stored.(keys{key_index});
                if ~isfield(value,'GraphicsObjects') || ...
                        ~isprop(value.GraphicsObjects,'Format3Data'), continue; end
                original = value.GraphicsObjects.Format3Data;
                if ~isscalar(original) || ~isgraphics(original,'figure'), continue; end
                properties = struct('Units',original.Units,'Position',original.Position, ...
                    'PaperUnits',original.PaperUnits,'PaperPosition',original.PaperPosition, ...
                    'PaperPositionMode',original.PaperPositionMode);
                if ~isequal(original,fig), close(original); end
                break;
            end
        end
    end
    if ~all(isfield(properties,{'Units','Position'}))
        warning('msiq:replot:FigureGeometry', ...
            'Saved geometry unavailable; retaining loaded size for %s.',files(k).name);
    end
    geometry = {'Units','Position','PaperUnits','PaperPosition','PaperPositionMode'};
    for property = 1:numel(geometry)
        key = geometry{property};
        if isfield(properties,key), set(fig,key,properties.(key)); end
    end
    [~,name] = fileparts(files(k).name);
    images{k} = fullfile(run.OutputDir,[name '.png']);
    if isappdata(fig,'msiq_export')
        rendering = getappdata(fig,'msiq_export');
        savefig(fig,fullfile(run.DataDir,files(k).name),'compact');
        print(fig,images{k},'-dpng',sprintf('-r%d',rendering.resolution));
    else
        Test_Project_Export_PNG(fig,images{k});
    end
    Result_Summary_Append(run,{k,[name '.png'],'成功', ...
        fullfile(files(k).folder,files(k).name)});
    clear cleanup;
end
Result_Update_Run_Info(run,struct('counts',struct('planned',numel(files), ...
    'executed',numel(files),'succeeded',numel(files),'failed',0,'invalid',0)));
Result_Finalize_Run(run,'completed','normal_completion',[], '');
output = struct('run_dir',run.OutputDir,'images',{images}, ...
    'source_run',source_run,'source_unchanged',true,'paths',{images},'dsp_executed',false);
end

function output = replot_saved_data(run_dir,destination,archive)
%REPLOT_RUN Render saved plots; legacy RX may replay verified observations.
run_dir = char(string(run_dir));
code_root = fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(code_root,'plotting'),fullfile(code_root,'result_management'));
if ~isfile(archive)
    output = legacy_replot(run_dir,destination);
    return;
end
record = load(archive);
if ~isfield(record,'schema_version') || ~ismember(record.schema_version,{'1.0','2.0'})
    error('msiq:replot:Schema', 'Unsupported plot archive: %s', archive);
end
prefix = '';
paths = cell(size(record.plots));
for k = 1:numel(record.plots)
    entry = record.plots{k};
    [~,name,ext] = fileparts(entry.file);
    if ~strcmp(entry.file,[name,ext]) || ~strcmpi(ext,'.png')
        error('msiq:replot:Path','Invalid plot filename in %s.',archive);
    end
    paths{k} = fullfile(destination,[prefix,entry.file]);
    msiq.plot_archive('render',entry,paths{k});
    % Preserve the independently editable FIG alongside the lossless archive.
    source_figure = msiq.artifact_path(run_dir,[name '.fig'],'read');
    destination_figure = fullfile(destination,'data',[name '.fig']);
    if isfile(source_figure) && ~isfile(destination_figure)
        copyfile(source_figure,destination_figure);
    end
end
output = struct('source_run',run_dir,'source_archive',archive, ...
    'paths',{paths},'dsp_executed',false);
addpath(fullfile(fileparts(fileparts(mfilename('fullpath'))),'result_management'));

end


function output = legacy_replot(root,destination)
raw_path = msiq.artifact_path(root,'raw_capture.mat','read');
decoded_path = msiq.artifact_path(root,'decoded_result.mat','read');
info_path = msiq.artifact_path(root,'run_info.json','read');
if isfile(raw_path) && isfile(decoded_path) && isfile(info_path)
    raw = load(raw_path,'raw'); decoded = load(decoded_path,'decoded');
    info = jsondecode(fileread(info_path));
    condition = info.parameters.condition;
    profile = 'v2_default';
    if strcmp(condition.architecture,'single_complex_stream'), profile = 'v2_traditional_wz'; end
    cfg = msiq.apply_condition(msiq.build_config(profile),condition);
    if isfield(info.parameters,'effective_config'), cfg = info.parameters.effective_config; end
    prefix = '';
    msiq.plotting.simulation_plots(struct('OutputDir',destination),raw.raw,decoded.decoded,cfg,condition,prefix);
    names = {'metrics_overview.png','constellation.png'};
    for stream_index = 1:numel(decoded.decoded.primary_streams)
        names{end+1} = sprintf('001_Channel%d_星座图.png',stream_index); %#ok<AGROW>
    end
    names{end+1} = 'overview.png';
    paths = cellfun(@(name) fullfile(destination,[prefix,name]),names,'UniformOutput',false);
    output = struct('source_run',root,'paths',{paths},'dsp_executed',false);
    return;
end
paths = {};
dsp_executed = false;
observation_replay = struct('attempted',false,'ok',false,'reason','');
prefix = '';
manifest = msiq.artifact_path(root,'tx_manifest.mat','read');
if ~isfile(manifest), manifest = msiq.artifact_path(root,'awg_plan.mat','read'); end
if isfile(manifest)
    tx = msiq.load_tx_manifest(manifest);
    receipt = struct();
    if isfield(tx,'receipt'), receipt = tx.receipt; end
    path = fullfile(destination,[prefix,'fig_tx_dashboard.png']);
    msiq.plotting.tx_dashboard(path,tx.plan,receipt);
    paths{end+1} = path;
end
raw_path = msiq.artifact_path(root,'raw_capture.mat','read');
bundle_path = msiq.artifact_path(root,'tx_reference_bundle.mat','read');
demod_path = msiq.artifact_path(root,'demod_result.mat','read');
if isfile(raw_path) && isfile(bundle_path)
    raw = load(raw_path,'raw'); reference = msiq.load_reference_bundle(bundle_path);
    validation = msiq.load_capture_validation(root);
    bundle = reference.bundle;
    cfg = msiq.build_config('v2_traditional_wz');
    if isfield(bundle,'dsp_config')
        cfg.waveform = bundle.dsp_config.waveform; cfg.receiver = bundle.dsp_config.receiver;
    end
    context = struct('cfg',cfg,'route',bundle.route,'desired',bundle.desired,'tx_ref',bundle.tx_ref);
    metadata_path = msiq.artifact_path(root,'capture_metadata.json','read');
    if isfile(metadata_path)
        metadata = jsondecode(fileread(metadata_path));
        if isfield(metadata,'scope_status_before'), context.scope_status = metadata.scope_status_before; end
    end
    result = struct();
    if isfile(demod_path)
        stored = load(demod_path,'output');
        if isfield(stored,'output'), result = stored.output; end
    end
    path = fullfile(destination,[prefix,'fig_rx_dashboard.png']);
    dashboard = msiq.plotting.rx_dashboard(path,raw.raw,validation.validation,context,result);
    if isfield(dashboard,'stages_info') && isfield(dashboard.stages_info,'replay')
        observation_replay = dashboard.stages_info.replay;
        dsp_executed = logical(observation_replay.attempted);
    end
    paths{end+1} = path;
end
if ~isempty(paths)
    output = struct('source_run',root,'paths',{paths},'dsp_executed',dsp_executed, ...
        'observation_replay',observation_replay);
    return;
end
error('msiq:replot:LegacyData', ...
    'No plot archive or supported legacy simulation data in %s. Original records remain readable by their existing entry points.',root);
end
