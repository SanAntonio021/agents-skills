function state = Test_Project_Draw_Waveform(ax, waveform, options)
%TEST_PROJECT_DRAW_WAVEFORM Render raw volts; compressed indices are display-only.
if nargin<3, options=struct(); end
Test_Project_Plot_Util('decorate',ax,options);
state=struct('handle',[],'display_indices',[],'status','failed');
if ~strcmp(opt(waveform,'status','ok'),'ok') || ~isfield(waveform,'time_s') || isempty(waveform.time_s)
    Test_Project_Plot_Util('placeholder',ax,opt(waveform,'reason','波形不可用')); return;
end
x=waveform.time_s(:); y=waveform.samples_v(:);
if numel(x)~=numel(y) || any(~isfinite(x)) || any(~isfinite(y))
    Test_Project_Plot_Util('placeholder',ax,'波形数据无效'); return;
end
lim=opt(options,'time_limits_s',opt(waveform,'time_limits_s',[min(x) max(x)]));
scale=1e9; unit='ns'; if diff(lim)>=1e-6, scale=1e6; unit='μs'; end
if diff(lim)>=1e-3, scale=1e3; unit='ms'; end
if diff(lim)>=1, scale=1; unit='s'; end
% Select the visible interval BEFORE envelope reduction; retain border points.
visible=find(x>=lim(1)&x<=lim(2));
if ~isempty(visible), visible=(max(1,visible(1)-1):min(numel(x),visible(end)+1))'; end
px=getpixelposition(ax); reduced=Test_Project_Plot_Util('envelope',y(visible),max(300,2*px(3)));
idx=visible(reduced);
h=Test_Project_Plot_Util('line',ax,'test_waveform',x(idx)*scale,y(idx));
set(h,'Color',opt(options,'color',[0 114 178]/255),'LineWidth',.65);
xlim(ax,lim*scale); xticks(ax,linspace(lim(1),lim(2),11)*scale);
vl=opt(waveform,'voltage_limits_v',[]);
if isempty(vl), extent=max(1e-6,max(abs(y))*1.1); vl=[-extent extent]; end
ylim(ax,vl); yticks(ax,linspace(vl(1),vl(2),9));
xlabel(ax,['时间 / ' unit]); ylabel(ax,'电压 / V');
stats=opt(options,'stats',struct()); note={};
if isfield(stats,'rms_v'), note{end+1}=sprintf('有效值 %.4g V | 峰峰值 %.4g V',stats.rms_v,stats.vpp_v); end
if strcmp(opt(waveform,'voltage_limits_source','data_adapted'),'scope')
    note{end+1}='量程：已提供设置';
else, note{end+1}='量程：按数据适配'; end
Test_Project_Plot_Util('note',ax,note);
state=struct('handle',h,'display_indices',idx,'status','ok');
end
function v=opt(s,k,d), v=Test_Project_Plot_Util('option',s,k,d); end
