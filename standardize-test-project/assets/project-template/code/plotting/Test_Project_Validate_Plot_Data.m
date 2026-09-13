function plotData = Test_Project_Validate_Plot_Data(plotData)
%TEST_PROJECT_VALIDATE_PLOT_DATA Validate v1 and propagate ordered stage failure.
required={'schema_name','schema_version','profile','source','analysis','panels','view'};
if ~isstruct(plotData)||~isscalar(plotData)||~all(isfield(plotData,required))
    error('TestProject:Plot:InvalidSchema','Incomplete test plot data package.');
end
if ~strcmp(plotData.schema_name,'test_project_plot_data')||~isequal(plotData.schema_version,1)
    error('TestProject:Plot:UnsupportedVersion','Unsupported plot data schema/version.');
end
if ~ismember(plotData.profile,{'single_channel','iq_observation','demodulation'}) || ...
        ~isstruct(plotData.analysis)||~isfield(plotData.analysis,'channels')||~isstruct(plotData.panels)||~isstruct(plotData.view)
    error('TestProject:Plot:InvalidSchema','Invalid profile/analysis/panels/view.');
end
if ~isstruct(plotData.source), error('TestProject:Plot:InvalidSource','source must be a struct.'); end
reject_graphics(plotData);
channels=plotData.analysis.channels;
if strcmp(plotData.profile,'single_channel') && numel(channels)~=1
    error('TestProject:Plot:ProfileChannels','single_channel requires one physical channel.');
elseif strcmp(plotData.profile,'iq_observation') && (numel(channels)~=2 || ~all(ismember({'I','Q'},{channels.role})))
    error('TestProject:Plot:ProfileChannels','iq_observation requires one I and one Q channel.');
end
p=plotData.panels;
if isempty(p), error('TestProject:Plot:EmptyPanels','No panels to display.'); end
required={'id','kind','title','status','reason','depends_on','data_ref','data','options'};
if ~all(isfield(p,required)), error('TestProject:Plot:InvalidPanels','Incomplete panel contract.'); end
ids={p.id};
if any(cellfun(@isempty,ids)) || numel(unique(ids))~=numel(ids)
    error('TestProject:Plot:PanelIds','Panel IDs must be nonempty and unique.');
end
for k=1:numel(p)
    if ~ismember(p(k).status,{'ok','failed','skipped'})
        error('TestProject:Plot:PanelStatus','Invalid panel status.');
    end
    deps=cellstr(string(p(k).depends_on));
    for j=1:numel(deps)
        index=find(strcmp(ids,deps{j}),1);
        if isempty(index)||index>=k
            p(k).status='failed'; p(k).reason='依赖缺失或阶段顺序无效'; break;
        elseif ~strcmp(p(index).status,'ok')
            p(k).status='skipped'; p(k).reason=['上游阶段不可用：' deps{j}]; break;
        end
    end
    if ~strcmp(p(k).status,'ok'), continue; end
    try
        data=Test_Project_Resolve_Panel(plotData.analysis,p(k));
        if isfield(data,'status') && ~strcmp(data.status,'ok')
            p(k).status=data.status; p(k).reason=data.reason;
            continue;
        end
        switch p(k).kind
            case 'waveform', need={'time_s','samples_v'};
            case 'spectrum', need={'frequency_hz'};
            case 'constellation', need={'symbols'};
            case 'curve', need={'x','y','x_unit','y_unit'};
            otherwise, error('TestProject:Plot:PanelKind','Unknown panel kind.');
        end
        if ~all(isfield(data,need)), error('TestProject:Plot:PanelData','缺少必要面板数据'); end
        switch p(k).kind
            case 'waveform'
                check_pair(data.time_s,data.samples_v,false);
            case 'curve'
                check_pair(data.x,data.y,true);
            case 'constellation'
                if ~isnumeric(data.symbols)||~isvector(data.symbols)||~any(isfinite(data.symbols))
                    error('TestProject:Plot:Symbols','星座缺少有效数值样点');
                end
            case 'spectrum'
                if isfield(data,'density_v2_hz'), values=data.density_v2_hz;
                elseif isfield(data,'density_linear'), values=data.density_linear;
                else, error('TestProject:Plot:Density','缺少线性谱密度'); end
                check_pair(data.frequency_hz,values,false);
                if any(values<0)||~all(isfield(data,{'fs_hz','df_hz'}))
                    error('TestProject:Plot:Density','谱密度或采样参数无效');
                end
        end
        if strcmp(p(k).kind,'spectrum') && isfield(data,'density_linear') && ~isfield(data,'density_v2_hz')
            if ~isfield(data,'alignment_basis')||~ismember(data.alignment_basis,{'capture_verified','dsp_aligned'})||~isfield(data,'stage_id')||isempty(data.stage_id)
                error('TestProject:Plot:IQSync','复频谱缺少同步依据或阶段来源');
            end
        end
    catch err
        p(k).status='failed'; p(k).reason=err.message;
    end
end
plotData.panels=p;
end
function check_pair(x,y,allowGaps)
if ~isnumeric(x)||~isnumeric(y)||~isreal(x)||~isreal(y)||~isvector(x)||~isvector(y)||isempty(x)||numel(x)~=numel(y)
    error('TestProject:Plot:CurveSize','曲线需要等长的实数向量');
end
if ~allowGaps && (any(~isfinite(x))||any(~isfinite(y)))
    error('TestProject:Plot:CurveFinite','曲线含有无效采样值');
end
end
function reject_graphics(value)
if isa(value,'handle')||isa(value,'function_handle')
    error('TestProject:Plot:DisplayCache','Do not archive graphics handles or callbacks.');
elseif isstruct(value)
    names=fieldnames(value);
    for k=1:numel(value), for j=1:numel(names), reject_graphics(value(k).(names{j})); end, end
elseif iscell(value)
    for k=1:numel(value), reject_graphics(value{k}); end
end
end
