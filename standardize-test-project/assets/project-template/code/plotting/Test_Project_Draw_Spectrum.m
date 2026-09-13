function state = Test_Project_Draw_Spectrum(ax, spectrum, options)
%TEST_PROJECT_DRAW_SPECTRUM Render saved densities; never calculate a PSD here.
if nargin<3, options=struct(); end
Test_Project_Plot_Util('decorate',ax,options);
state=struct('handle',[],'display_indices',[],'status','failed');
if ~strcmp(opt(spectrum,'status','ok'),'ok')
    Test_Project_Plot_Util('placeholder',ax,opt(spectrum,'reason','频谱不可用')); return;
end
% Legacy file-export wrappers supply already-scaled display quantities.
if isfield(spectrum,'display_x')
    x=spectrum.display_x(:); y=spectrum.display_y(:);
    xl=opt(options,'x_label',''); yl=opt(options,'y_label','');
else
    x=spectrum.frequency_hz(:)/1e9; xl='频率 / GHz';
    if isfield(spectrum,'bandwidth_known') && ~spectrum.bandwidth_known, xl='频率 / GHz（采样上限，模拟带宽未知）'; end
    if ~strcmp(opt(options,'unit','auto'),'voltage') && isfield(spectrum,'density_w_hz') && ~isempty(spectrum.density_w_hz) && all(isfinite(spectrum.density_w_hz))
        y=10*log10(max(spectrum.density_w_hz(:)*1000,realmin)); yl='功率谱密度 / (dBm/Hz)';
    elseif isfield(spectrum,'density_v2_hz')
        y=10*log10(max(spectrum.density_v2_hz(:),realmin)); yl='电压谱密度 / dB(V²/Hz)';
    else
        if ~isfield(spectrum,'alignment_basis') || ~ismember(spectrum.alignment_basis,{'capture_verified','dsp_aligned'}) || isempty(opt(spectrum,'stage_id',''))
            Test_Project_Plot_Util('placeholder',ax,'复频谱缺少对齐依据或阶段来源'); return;
        end
        y=10*log10(max(spectrum.density_linear(:),realmin));
        yl=['谱密度 / dB(' char(spectrum.density_unit) ')'];
    end
end
if isempty(x) || numel(x)~=numel(y) || any(~isfinite(x)) || any(~isfinite(y))
    Test_Project_Plot_Util('placeholder',ax,'频谱数据无效'); return;
end
idx=(1:numel(x))';
if ~opt(options,'full_points',false)
    px=getpixelposition(ax); idx=Test_Project_Plot_Util('envelope',y,max(300,2*px(3)));
end
tag=opt(options,'tag','test_spectrum'); h=Test_Project_Plot_Util('line',ax,tag,x(idx),y(idx));
set(h,'Color',opt(options,'color',[0 114 178]/255),'LineWidth',opt(options,'line_width',.9), ...
    'LineStyle',opt(options,'line_style','-'),'DisplayName',opt(options,'name','频谱'));
xlabel(ax,xl,'Interpreter','none'); ylabel(ax,yl,'Interpreter','none');
fl=opt(options,'frequency_limits_hz',[]);
if ~isempty(fl), xlim(ax,fl/1e9);
elseif isfield(spectrum,'density_v2_hz') && isfield(spectrum,'available_limit_hz')
    xlim(ax,[0 spectrum.available_limit_hz/1e9]);
elseif max(x)>min(x), xlim(ax,[min(x) max(x)]); end
ylimits=opt(options,'y_limits',[]); if ~isempty(ylimits), ylim(ax,ylimits); else, ylim(ax,'auto'); end
if ~isfield(spectrum,'display_x')
    note={sprintf('%.4g GSa/s | Δf %.4g MHz',spectrum.fs_hz/1e9,spectrum.df_hz/1e6)};
    if isfield(spectrum,'stage_id'), note{end+1}=char(spectrum.stage_id); end
    if isfield(spectrum,'band_power_w') && isfinite(spectrum.band_power_w)
        note{end+1}=sprintf('带内功率 %.3f dBm',10*log10(max(spectrum.band_power_w*1000,realmin)));
    elseif isfield(spectrum,'power_band_hz') && ~isempty(spectrum.power_band_hz) && ~strcmp(opt(spectrum,'power_status',''),'ok')
        note{end+1}='请求频段功率不可用';
    end
    Test_Project_Plot_Util('note',ax,note);
end
state=struct('handle',h,'display_indices',idx,'status','ok');
end
function v=opt(s,k,d), v=Test_Project_Plot_Util('option',s,k,d); end
