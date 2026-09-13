function report = run_wz_sro_case_examples(options)
%RUN_WZ_SRO_CASE_EXAMPLES Draw understandable B/C/D WZ SRO examples.
% This is an offline analysis helper. It does not change production code.

if nargin < 1 || isempty(options)
    options = struct();
end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:sroExamples:Options', 'options must be a scalar struct.');
end
repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo, 'code', 'result_management'));
defaults = struct('trial','02_DIV4','results_root',repo, ...
    'write_results',true,'output_dir','');
options = merge_options(defaults, options);
policy = msiq.output_policy(options);
options.output_level = policy.output_level;
options.write_results = policy.write_results;

trial_dir = fullfile(repo,'results','manual_loopback', ...
    'rdiv_compare_20260821_091514','trials',options.trial);
rx_path = fullfile(trial_dir,'rx','diagnostics','raw_capture.mat');
tx_path = fullfile(trial_dir,'tx','diagnostics','tx_reference_bundle.mat');
if ~isfile(rx_path) || ~isfile(tx_path)
    error('msiq:sroExamples:InputMissing', ...
        'Missing raw capture or TX reference for %s.',options.trial);
end
loaded_rx = load(rx_path,'raw');
loaded_tx = msiq.load_reference_bundle(tx_path);
cfg = msiq.build_config('v2_traditional_wz');
cfg.waveform = loaded_tx.bundle.dsp_config.waveform;
cfg.receiver = loaded_tx.bundle.dsp_config.receiver;
cfg.waveform.architecture = 'single_complex_stream';
tx_ref = loaded_tx.bundle.tx_ref;
raw = normalize_pair(loaded_rx.raw);

cases = { ...
    struct('label','fixed_sro_200ppm', 'title', ...
    '固定 SRO：200 ppm', ...
    'kind','global','sro_ppm',200,'echo_amp',NaN,'echo_delay_symbols',NaN), ...
    struct('label','varying_sro_100_to_300ppm', 'title', ...
    '时变 SRO：100 ppm -> 300 ppm', ...
    'kind','varying','start_ppm',100,'end_ppm',300,'echo_amp',NaN, ...
    'echo_delay_symbols',NaN)};

if isempty(options.output_dir)
    output_dir = '';
else
    output_dir = char(string(options.output_dir));
end
run = [];
artifacts = {'overview.png','varying_sro_100_to_300ppm.png', ...
    'summary.csv','data/plot_data.mat','data/source_info.json','data/sources.txt'};
if options.write_results
    parameters = struct('trial',options.trial, ...
        'fixed_sro_ppm',200,'varying_sro_ppm',[100 300], ...
        'comparison','B_no_correction_C_production_D_known_injection');
    run_cfg = struct('ProjectRoot',repo,'ResultsRoot',options.results_root, ...
        'RunType','analysis','NameParts',{{'WZ_SRO_case_examples'}}, ...
        'RunPurpose','validation','ExecutionMode','offline_analysis', ...
        'EntryPoint','msiq.run_wz_sro_case_examples', ...
        'Parameters',parameters,'Counts',struct('planned',2, ...
        'executed',0,'succeeded',0,'failed',0,'invalid',0), ...
        'SourceRuns',{{rx_path,tx_path}},'Artifacts',{artifacts});
    if ~isempty(output_dir), run_cfg.OutputDir = output_dir; end
    run = Result_Create_Run(run_cfg);
    output_dir = run.OutputDir;
    plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
    Result_Log_Stage(run,'INFO','setup', ...
        'Two offline SRO constellation examples started for %s.', ...
        options.trial);
end

examples = repmat(empty_example(),1,numel(cases));
try
    for k = 1:numel(cases)
        stressed = inject_case(raw,cfg,cases{k});
        no_sro_cfg = cfg;
        no_sro_cfg.receiver.max_abs_sro_ppm = 0;
        b = decode_case(stressed,tx_ref,no_sro_cfg);
        c = decode_case(stressed,tx_ref,cfg);
        if strcmp(cases{k}.kind,'varying')
            oracle = undo_variable_sro(stressed,cases{k}.start_ppm, ...
                cases{k}.end_ppm,size(raw.samples,1));
        else
            [oracle,~] = msiq.dsp.correct_raw_sro( ...
                stressed,cases{k}.sro_ppm);
        end
        d = decode_case(oracle,tx_ref,no_sro_cfg);
        examples(k).label = cases{k}.label;
        examples(k).title = cases{k}.title;
        examples(k).b = b;
        examples(k).c = c;
        examples(k).d = d;
        examples(k).output_path = '';
        if options.write_results
            image_name = [cases{k}.label '.png'];
            if k == 1, image_name = 'overview.png'; end
            examples(k).output_path = fullfile(output_dir,image_name);
            draw_example(examples(k),examples(k).output_path);
            if ~isempty(run)
                Result_Log_Stage(run,'INFO','example', ...
                    '%s completed: C_applied=%d, C_reason=%s.', ...
                    cases{k}.label,logical_field(c.sync,'sro_applied',false), ...
                    c.reason);
            end
        end
    end
    if options.write_results
        msiq.import_summary(run,@(path) write_csv(path,examples));
        Result_Atomic_Write_Json(msiq.output_path(run,'source_info.json'),struct( ...
            'raw_path',rx_path,'raw_sha256',msiq.file_sha256(rx_path), ...
            'reference_path',tx_path,'reference_sha256',msiq.file_sha256(tx_path), ...
            'options',options,'effective_config',cfg));
        write_sources(msiq.output_path(run,'sources.txt'), ...
            {rx_path,tx_path},repo);
        if ~isempty(run)
            Result_Update_Run_Info(run,struct('counts',struct( ...
                'planned',2,'executed',2,'succeeded',2, ...
                'failed',0,'invalid',0),'safety',struct( ...
                'preflight','not_applicable', ...
                'initial_outputs','not_applicable', ...
                'shutdown','not_applicable', ...
                'shutdown_readback','not_applicable')));
            Result_Finalize_Run(run,'completed','normal_completion', ...
                artifacts,'Two representative constellation examples completed.');
        end
    end
catch exception
    if options.write_results && ~isempty(output_dir)
        msiq.save_failure(output_dir,msiq.analysis_record(struct( ...
            'options',options,'cfg',cfg,'raw_path',rx_path, ...
            'bundle_path',tx_path,'examples',examples)));
    end
    if options.write_results && ~isempty(run)
        Result_Log_Stage(run,'ERROR','failure','%s',exception.message);
        Result_Finalize_Run(run,'failed','processing_failed',{}, ...
            exception.message);
    end
    rethrow(exception);
end
report = struct('ok',true,'offline_only',true,'trial',options.trial, ...
    'examples',examples,'output_dir',output_dir);
end

function raw = normalize_pair(capture)
% Match traditional_rx's offline I/Q alignment before replay.
if ~isstruct(capture) || ~isfield(capture,'channels') || ...
        numel(capture.channels) < 2
    error('msiq:sroExamples:CaptureFormat', ...
        'Capture must contain at least two channels.');
end
records = capture.channels(1:2);
times = cell(1,2);
samples = cell(1,2);
rates = nan(1,2);
for k = 1:2
    times{k} = double(records(k).time_axis_s(:));
    samples{k} = double(records(k).samples(:));
    if numel(times{k}) < 2 || numel(samples{k}) ~= numel(times{k}) || ...
            any(~isfinite(times{k})) || any(~isfinite(samples{k})) || ...
            any(diff(times{k}) <= 0)
        error('msiq:sroExamples:CaptureTimeAxis', ...
            'Capture channel %d has an invalid time axis.', k);
    end
    rates(k) = 1/median(diff(times{k}));
end
same_grid = numel(times{1}) == numel(times{2}) && ...
    max(abs(times{1}-times{2})) <= 0.05/min(rates);
if same_grid
    common_time = times{1};
    data = [samples{1},samples{2}];
else
    start_time = max(cellfun(@(x)x(1),times));
    end_time = min(cellfun(@(x)x(end),times));
    common_rate = min(rates);
    count = floor((end_time-start_time)*common_rate)+1;
    common_time = start_time+(0:count-1).'/common_rate;
    data = [interp1(times{1},samples{1},common_time,'linear'), ...
        interp1(times{2},samples{2},common_time,'linear')];
end
if any(~isfinite(data(:)))
    error('msiq:sroExamples:CaptureInterpolation', ...
        'I/Q alignment produced non-finite samples.');
end
raw = struct('samples',data,'time_axes',repmat(common_time,1,2), ...
    'sample_rate_hz',1/median(diff(common_time)), ...
    'payload_pair','A','full_scale',NaN);
end

function output = decode_case(raw,tx_ref,cfg)
output = struct('decoded',false,'metrics',empty_metrics(),'sync',struct(), ...
    'symbols',complex([]),'reason','');
try
    decoded = msiq.decode_capture(raw,tx_ref,cfg);
    stream = decoded.primary_streams(1);
    output.decoded = decoded.pass && stream.pass;
    output.metrics = struct('mer_db',stream.mer_db,'evm_rms',stream.evm_rms, ...
        'pre_fec_ber',stream.pre_fec_ber,'post_fec_ber',stream.post_fec_ber, ...
        'bler',stream.bler,'pass',stream.pass);
    output.sync = decoded.synchronization;
    output.symbols = stream.constellation_symbols(:);
    output.reason = decoded.synchronization.sro_reason;
catch exception
    output.reason = exception.identifier;
end
end

function draw_example(example,path)
labels = {'未补偿','按估计值补偿','按真实值补偿（参考）'};
cases = {example.b,example.c,example.d};
fig = figure('Visible','off','Color','w','Position',[50 50 1800 760]);
set(fig,'DefaultAxesFontName','Microsoft YaHei UI', ...
    'DefaultTextFontName','Microsoft YaHei UI','DefaultAxesFontSize',9);
annotation(fig,'textbox',[0.03 0.945 0.94 0.040],'String', ...
    example.title,'EdgeColor','none','HorizontalAlignment','center', ...
    'FontSize',16,'FontWeight','bold','Interpreter','none');

% Final constellations use identical axes across B/C/D.
all_symbols = [];
for k = 1:3
    symbols = cases{k}.symbols;
    all_symbols = [all_symbols; symbols(isfinite(real(symbols)) & ...
        isfinite(imag(symbols)))]; %#ok<AGROW>
end
ideal = qammod((0:15).',16,'UnitAveragePower',true);
if isempty(all_symbols)
    constellation_lim = 1.2;
else
    constellation_lim = max(1.1,max(abs([real(all_symbols);imag(all_symbols)])));
    constellation_lim = min(max(constellation_lim,1.1),3);
end
for k = 1:3
    ax = subplot(1,3,k); hold(ax,'on');
    set(ax,'Position',[0.06+0.31*(k-1),0.16,0.27,0.70]);
    symbols = cases{k}.symbols;
    symbols = symbols(isfinite(real(symbols)) & isfinite(imag(symbols)));
    total_symbols = numel(symbols);
    if numel(symbols) > 4000
        symbols = symbols(round(linspace(1,numel(symbols),4000)));
    end
    if isempty(symbols)
        text(ax,0.5,0.5,'无星座数据','HorizontalAlignment','center');
    else
        plot(ax,real(symbols),imag(symbols),'.','MarkerSize',4);
    end
    plot(ax,real(ideal),imag(ideal),'ks','MarkerSize',7,'LineWidth',1.1);
    axis(ax,'equal'); xlim(ax,[-constellation_lim constellation_lim]);
    ylim(ax,[-constellation_lim constellation_lim]); grid(ax,'on'); box(ax,'on');
    status = panel_status(cases{k},k);
    title(ax, sprintf('%s\nMER %.2f dB | %s | N %d/%d',labels{k}, ...
        cases{k}.metrics.mer_db,status,numel(symbols),total_symbols), ...
        'Interpreter','none');
    xlabel(ax,'I'); ylabel(ax,'Q');
end
if ~msiq.plot_archive('export',fig,path,'print',300)
    print(fig,path,'-dpng','-r300');
end
close(fig);
end

function text_value = panel_status(value,index)
if index == 1
    text_value = '基线';
elseif index == 3
    text_value = '参考';
else
    s = value.sync;
    applied = isfield(s,'sro_applied') && logical(s.sro_applied);
    if applied
        text_value = '已执行';
    else
        reason = '';
        if isfield(s,'sro_reason')
            reason = char(string(s.sro_reason));
        end
        text_value = ['未执行：' reason_text(reason)];
    end
end
end

function text_value = reason_text(reason)
switch reason
    case 'estimate_out_of_range'
        text_value = '估计值超出范围';
    case 'internal_interval_scatter'
        text_value = '同步峰间隔不一致';
    case 'ambiguous_awg_boundary_phase'
        text_value = '帧边界位置不明确';
    case 'applied'
        text_value = '已执行';
    otherwise
        if isempty(reason), text_value = '判据未通过'; else, text_value = reason; end
end
end

function value = observation_sync(sync)
value = sync;
if isstruct(sync) && isfield(sync,'sro_observation')
    value = sync.sro_observation;
end
end

function value = numeric_field(source,name,fallback)
field_name = name;
if isstruct(source) && ~isfield(source,field_name) && ...
        isfield(source,['sro_' name])
    field_name = ['sro_' name];
end
if isstruct(source) && isfield(source,field_name) && ...
        ~isempty(source.(field_name))
    value = double(source.(field_name)(:));
else
    value = double(fallback(:));
end
value = value(isfinite(value));
end

function value = empty_metrics()
value = struct('mer_db',NaN,'evm_rms',NaN,'pre_fec_ber',NaN, ...
    'post_fec_ber',NaN,'bler',NaN,'pass',false);
end

function value = empty_example()
value = struct('label','','title','','b',empty_case(), ...
    'c',empty_case(),'d',empty_case(),'output_path','');
end

function value = empty_case()
value = struct('decoded',false,'metrics',empty_metrics(),'sync',struct(), ...
    'symbols',complex([]),'reason','');
end

function value = inject_case(raw,cfg,case_spec)
if strcmp(case_spec.kind,'varying')
    value = inject_variable_sro(raw,case_spec.start_ppm,case_spec.end_ppm);
else
    value = inject_global_sro(raw,case_spec.sro_ppm);
    if isfinite(case_spec.echo_amp)
        samples_per_symbol = raw.sample_rate_hz/cfg.waveform.symbol_rate_hz;
        value = add_echo(value,case_spec.echo_amp, ...
            round(case_spec.echo_delay_symbols*samples_per_symbol));
    end
end
end

function value = inject_global_sro(raw,ppm)
scale = 1+ppm*1e-6;
count = floor((size(raw.samples,1)-1)*scale)+1;
source_axis = (0:count-1).'/scale;
value = raw; value.samples = zeros(count,size(raw.samples,2));
for k = 1:size(raw.samples,2)
    value.samples(:,k) = interp1((0:size(raw.samples,1)-1).', ...
        raw.samples(:,k),source_axis,'pchip');
end
value.time_axes = rebuild_time_axes(raw,count);
end

function value = inject_variable_sro(raw,start_ppm,end_ppm)
[~,~,source_axis] = variable_map(size(raw.samples,1),start_ppm,end_ppm);
value = raw; value.samples = zeros(numel(source_axis),size(raw.samples,2));
for k = 1:size(raw.samples,2)
    value.samples(:,k) = interp1((0:size(raw.samples,1)-1).', ...
        raw.samples(:,k),source_axis,'pchip');
end
value.time_axes = rebuild_time_axes(raw,numel(source_axis));
end

function value = undo_variable_sro(raw,start_ppm,end_ppm,original_count)
[mapping,~,~] = variable_map(original_count,start_ppm,end_ppm);
target = min(mapping(:),size(raw.samples,1)-1);
value = raw; value.samples = zeros(original_count,size(raw.samples,2));
for k = 1:size(raw.samples,2)
    value.samples(:,k) = interp1((0:size(raw.samples,1)-1).', ...
        raw.samples(:,k),target,'pchip','extrap');
end
value.time_axes = rebuild_time_axes(raw,original_count);
end

function [mapping,output_axis,source_axis] = variable_map(count,start_ppm,end_ppm)
axis_value = (0:count-1).';
scale = 1+(start_ppm+(end_ppm-start_ppm)*axis_value/max(count-1,1))*1e-6;
mapping = cumtrapz(axis_value,scale);
output_axis = (0:floor(mapping(end))).';
source_axis = interp1(mapping,axis_value,output_axis,'pchip');
end

function value = add_echo(raw,amplitude,delay_samples)
z = complex(raw.samples(:,1),raw.samples(:,2));
delayed = zeros(size(z)); delayed(delay_samples+1:end) = z(1:end-delay_samples);
z = z+amplitude*delayed; value = raw; value.samples = [real(z),imag(z)];
end

function value = rebuild_time_axes(raw,count)
start_time = raw.time_axes(1,1);
axis_value = start_time+(0:count-1).'/raw.sample_rate_hz;
value = repmat(axis_value,1,size(raw.samples,2));
end

function write_csv(path,examples)
fid = Result_Open_File_Retry(path,'w','n','UTF-8'); cleanup = onCleanup(@()fclose(fid));
fprintf(fid,'%s',char(65279));
fprintf(fid,['case,mode,mer_db,evm_rms,pre_fec_ber,post_fec_ber,', ...
    'bler,decoded,reason,sro_ppm,sro_sigma_ppm,', ...
    'max_interval_deviation_samples,peak_count,applied,状态,repeat,', ...
    'attempt,采集时间,原始数据文件,单次图片文件,错误代码,错误信息\n']);
fprintf(fid,['-,-,dB,-,-,-,-,-,-,ppm,ppm,samples,count,-,', ...
    '-,-,-,-,-,-,-,-\n']);
for k = 1:numel(examples)
    for name = {'b','c','d'}
        mode = name{1}; value = examples(k).(mode); s = observation_sync(value.sync);
        [~,image_name,image_extension] = fileparts(examples(k).output_path);
        fprintf(fid,['%s,%s,%.17g,%.17g,%.17g,%.17g,%.17g,%d,', ...
            '%s,%.17g,%.17g,%.17g,%d,%d,%s,1,1,,,%s,,\n'], ...
            examples(k).label,mode,value.metrics.mer_db,value.metrics.evm_rms, ...
            value.metrics.pre_fec_ber,value.metrics.post_fec_ber,value.metrics.bler, ...
            value.decoded,csv_text(value.reason),numeric_field(s,'sro_ppm',NaN), ...
            numeric_field(s,'sro_sigma_ppm',NaN),numeric_field(s,'max_interval_deviation_samples',NaN), ...
            numel(numeric_field(s,'peak_samples',[])), ...
            logical_field(value.sync,'sro_applied',false),csv_text(case_status(value)), ...
            csv_text([image_name image_extension]));
    end
end
clear cleanup;
end

function value = case_status(example_case)
if isempty(example_case.symbols)
    value = '失败';
else
    value = '成功';
end
end


function write_sources(path,sources,repo)
fid = Result_Open_File_Retry(path,'w','n','UTF-8');
cleanup = onCleanup(@() fclose(fid));
for k = 1:numel(sources)
    value = sources{k};
    if startsWith(value,repo)
        value = strrep(value,[repo filesep],'');
    end
    fprintf(fid,'%s\n',value);
end
clear cleanup;
end

function value = logical_field(source,name,fallback)
if isstruct(source) && isfield(source,name), value = logical(source.(name)); else, value = fallback; end
end

function value = merge_options(base,override)
value = base; names = fieldnames(override);
for k = 1:numel(names), value.(names{k}) = override.(names{k}); end
end

function text = csv_text(value)
text = strrep(char(string(value)),',','/');
end
