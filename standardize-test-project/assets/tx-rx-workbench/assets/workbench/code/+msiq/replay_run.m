function replay = replay_run(run_dir, overrides)
%REPLAY_RUN Reprocess one V2 run without changing raw capture files.

if nargin < 2 || isempty(overrides), overrides = struct(); end
run_dir = char(string(run_dir));
info_path = msiq.artifact_path(run_dir, 'run_info.json');
if ~isfile(info_path)
    error('msiq:replay:RunInfoMissing', ...
        'V2 replay requires run_info.json: %s', run_dir);
end
source_info = jsondecode(fileread(info_path));
if strcmp(source_info.execution_mode,'simulation') && ...
        ~isfile(msiq.artifact_path(run_dir,'raw_capture.mat'))
    error('msiq:replay:RerunSimulation', ...
        'Compact simulation has no raw capture. Use replot for figures, or rerun simulation with the saved configuration and seeds to change DSP.');
end
cfg = msiq.build_config('v2_default');
saved_cfg = msiq.artifact_path(run_dir,'effective_config.mat');
if isfile(saved_cfg)
    saved = load(saved_cfg,'effective_cfg');
    cfg = saved.effective_cfg;
end
cfg = merge_recursive(cfg, overrides);
condition = source_info.parameters.condition;
cfg = msiq.apply_condition(cfg, condition);

raw_files = dir(fullfile(run_dir, 'ON_batch*_repeat*_attempt*.mat'));
new_files = dir(fullfile(run_dir, 'data', 'ON_batch*_repeat*_attempt*.mat'));
if ~isempty(new_files), raw_files = new_files; end
if isempty(raw_files)
    error('msiq:replay:NoRawCapture', ...
        'No V2 ON capture files found in %s.', run_dir);
end
addpath(fullfile(cfg.code_root, 'result_management'));
run = Result_Create_Run(struct('ProjectRoot',cfg.project_root, ...
    'ResultsRoot',cfg.results_root,'RunType','analysis', ...
    'NameParts',{{'V2_replay'}},'ExecutionMode','offline_replay', ...
    'SourceRuns',{{run_dir}},'Parameters',struct('overrides',overrides)));
Result_Write_Sources(run,{run_dir});
paths = struct( ...
    'info', msiq.output_path(run, 'replay_info.json'), ...
    'summary', run.SummaryPath, ...
    'overview', fullfile(run.OutputDir, 'overview.png'));

records = repmat(struct('sequence',0,'repeat',0,'batch',0,'physical','','stream',0, ...
    'evm',NaN,'mer',NaN,'pre_ber',NaN,'post_ber',NaN, ...
    'bler',NaN,'parity',false,'blocks',0,'source_file',''), 0, 1);
for file_index = 1:numel(raw_files)
    tokens = regexp(raw_files(file_index).name, ...
        'ON_batch(\d+)_repeat(\d+)_attempt(\d+)\.mat', 'tokens', 'once');
    batch_index = str2double(tokens{1});
    repeat_index = str2double(tokens{2});
    seed = condition.repeat_plan(repeat_index).seed;
    reference_path = msiq.artifact_path(run_dir, sprintf('tx_reference_seed%d.mat', seed));
    if ~isfile(reference_path)
        error('msiq:replay:ReferenceMissing', ...
            'Missing TX reference for seed %d.', seed);
    end
    source = load(fullfile(raw_files(file_index).folder, raw_files(file_index).name), 'raw_on');
    reference = load(reference_path, 'tx_ref');
    batch = condition.receive_batches(batch_index);
    for local_index = 1:numel(batch.physical_subbands)
        physical = batch.physical_subbands{local_index};
        mapping = condition.awg_slot_map(strcmp( ...
            {condition.awg_slot_map.physical_subband}, physical));
        raw = source.raw_on;
        columns = 2*local_index-1:2*local_index;
        raw.samples = raw.samples(:,columns);
        if isfield(raw, 'time_axes') && ~isempty(raw.time_axes)
            raw.time_axes = raw.time_axes(:,columns);
        end
        raw.payload_pair = mapping.payload_pair;
        decoded = msiq.decode_capture(raw, reference.tx_ref, cfg);
        for stream = 1:numel(decoded.primary_streams)
            value = decoded.primary_streams(stream);
            records(end+1) = struct('sequence',file_index,'repeat',repeat_index, ...
                'batch',batch_index,'physical',physical,'stream',stream, ...
                'evm',value.evm_rms,'mer',value.mer_db, ...
                'pre_ber',value.pre_fec_ber,'post_ber',value.post_fec_ber, ...
                'bler',value.bler,'parity',value.parity_converged, ...
                'blocks',value.block_count, ...
                'source_file',fullfile(raw_files(file_index).folder, ...
                raw_files(file_index).name)); %#ok<AGROW>
        end
    end
end

Result_Summary_Initialize(run,{'序号','物理子带','Channel','EVM','MER', ...
    'pre-FEC BER','post-FEC BER','BLER','状态','来源文件'}, ...
    {'-','-','-','%','dB','-','-','-','-','-'});
for k = 1:numel(records)
    value = records(k);
    status = '成功';
    if ~isfinite(value.evm), status = '失败'; end
    Result_Summary_Append(run,{value.sequence,value.physical,value.stream, ...
        100*value.evm,value.mer,value.pre_ber,value.post_ber,value.bler, ...
        status,value.source_file});
end
save(msiq.output_path(run, 'replay_records.mat'), 'records', '-v7.3');
addpath(fullfile(cfg.code_root, 'plotting'));
metrics(1) = struct('Name','EVM','Unit','%', ...
    'Values',100*[records.evm].');
metrics(2) = struct('Name','MER','Unit','dB', ...
    'Values',[records.mer].');
streams_per_subband = 2;
if strcmpi(condition.architecture, 'single_complex_stream')
    streams_per_subband = 1;
end
planned_observations = condition.repetitions * ...
    condition.num_active * streams_per_subband;
planned_observations = max(planned_observations, numel(records));
plot_records(paths.overview,records);

replay_info = struct('schema_version','3.0', ...
    'run_id',run.RunName, ...
    'source_run_id',source_info.run_id,'source_run_dir',run_dir, ...
    'execution_mode','offline_replay','started_at', ...
    char(datetime('now','TimeZone','local', ...
    'Format','yyyy-MM-dd''T''HH:mm:ssXXX')), ...
    'overrides',overrides,'source_files',{unique({records.source_file})}, ...
    'artifacts',{{paths.summary,paths.overview}}, ...
    'raw_files_modified',false);
addpath(fullfile(cfg.code_root, 'result_management'));
Result_Atomic_Write_Json(paths.info, replay_info);
Result_Finalize_Run(run, 'completed', 'normal_completion', [], '');
replay = struct('source_run',run_dir,'run_dir',run.OutputDir,'records',records,'paths',paths, ...
    'raw_files_modified',false);
end

function plot_records(path, records)
fig = figure('Visible','off','Color','w');
cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig,2,1);
labels = arrayfun(@(r) sprintf('%s_Channel%d',r.physical,r.stream), ...
    records,'UniformOutput',false);
groups = unique(labels,'stable');
fields = {'evm','mer'};
for metric = 1:2
    ax = nexttile(layout,metric); hold(ax,'on');
    for group = 1:numel(groups)
        values = records(strcmp(labels,groups{group}));
        x = [values.sequence]; y = [values.(fields{metric})];
        if metric == 1, y = 100*y; end
        plot(ax,x,y,'o-','DisplayName',groups{group});
    end
    xlabel(ax,'序号'); grid(ax,'on'); legend(ax,'Location','best');
    if metric == 1, ylabel(ax,'EVM (%)'); else, ylabel(ax,'MER (dB)'); end
end
Test_Project_Export_PNG(fig,path);
end

function write_replay_summary(path, records)
fid = fopen(path, 'w', 'n', 'UTF-8');
if fid < 0, error('msiq:replay:SummaryOpen','Cannot create %s.',path); end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, uint8([239 187 191]), 'uint8');
fprintf(fid, ['repeat,batch,physical_subband,stream,EVM,MER,pre_FEC_BER,', ...
    'post_FEC_BER,BLER,parity_converged,block_count,source_file\n']);
fprintf(fid, '-,-,-,-,-,dB,-,-,-,-,block,-\n');
for k = 1:numel(records)
    value = records(k);
    fprintf(fid, '%d,%d,%s,%d,%.15g,%.15g,%.15g,%.15g,%.15g,%d,%d,%s\n', ...
        value.repeat,value.batch,value.physical,value.stream,value.evm, ...
        value.mer,value.pre_ber,value.post_ber,value.bler,value.parity, ...
        value.blocks,value.source_file);
end
end

function out = merge_recursive(base, extra)
out = base;
names = fieldnames(extra);
for k = 1:numel(names)
    name = names{k};
    if isfield(out,name) && isstruct(out.(name)) && isstruct(extra.(name))
        out.(name) = merge_recursive(out.(name), extra.(name));
    else
        out.(name) = extra.(name);
    end
end
end
