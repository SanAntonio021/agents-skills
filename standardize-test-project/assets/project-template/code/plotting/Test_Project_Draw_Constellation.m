function state = Test_Project_Draw_Constellation(ax, data, options)
%TEST_PROJECT_DRAW_CONSTELLATION All finite symbols, no display normalization.
if nargin<3, options=struct(); end
Test_Project_Plot_Util('decorate',ax,options);
rx=data.symbols(:); ideal=opt(data,'ideal_symbols',[]); ideal=ideal(:);
valid=isfinite(real(rx))&isfinite(imag(rx)); rx=rx(valid);
ideal=ideal(isfinite(real(ideal))&isfinite(imag(ideal)));
state=struct('handle',[],'ideal_handle',[],'valid_count',numel(rx),'outside_count',0);
if isempty(rx), Test_Project_Plot_Util('placeholder',ax,'星座数据不可用'); return; end
h=Test_Project_Plot_Util('line',ax,'test_symbols',real(rx),imag(rx));
set(h,'LineStyle','none','Marker','.','MarkerSize',4,'Color',opt(options,'color',[0 114 178]/255),'DisplayName','接收符号');
hi=Test_Project_Plot_Util('line',ax,'test_ideal',real(ideal),imag(ideal));
set(hi,'LineStyle','none','Marker','s','MarkerSize',5,'Color',[0 0 0],'DisplayName','理想符号');
lims=opt(options,'axis_limits',[]);
if isempty(lims), extent=max([1;abs(real(rx));abs(imag(rx));abs(real(ideal));abs(imag(ideal))])*1.08; lims=[-extent extent -extent extent]; end
axis(ax,'equal'); xlim(ax,lims(1:2)); ylim(ax,lims(3:4));
xlabel(ax,'同相分量 I'); ylabel(ax,'正交分量 Q');
outside=nnz(real(rx)<lims(1)|real(rx)>lims(2)|imag(rx)<lims(3)|imag(rx)>lims(4));
note={sprintf('N = %d',numel(rx))}; metrics=opt(data,'metrics',struct());
names=fieldnames(metrics);
for k=1:numel(names)
    v=metrics.(names{k}); if isnumeric(v)&&isscalar(v)&&isfinite(v), note{end+1}=sprintf('%s %.4g',names{k},v); end %#ok<AGROW>
end
if outside>0, note{end+1}=sprintf('超范围 %d',outside); end
if ~opt(options,'suppress_note',false), Test_Project_Plot_Util('note',ax,note); end
state=struct('handle',h,'ideal_handle',hi,'valid_count',numel(rx),'outside_count',outside);
end
function v=opt(s,k,d), v=Test_Project_Plot_Util('option',s,k,d); end
