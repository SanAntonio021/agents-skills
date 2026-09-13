function state = Test_Project_Draw_Curve(ax, data, options)
%TEST_PROJECT_DRAW_CURVE Display provided diagnostic samples, retaining gaps.
if nargin<3, options=struct(); end
Test_Project_Plot_Util('decorate',ax,options);
y=data.y; if isvector(y), y=y(:); end
x=data.x; if isvector(x), x=x(:); end
if size(x,1)~=size(y,1)||~ismember(size(x,2),[1 size(y,2)])
    error('TestProject:Plot:CurveSize','Curve size mismatch.');
end
count=size(y,2); h=gobjects(1,count);
colors=[0 114 178;213 85 0;0 158 115;204 121 167]/255;
labels=Test_Project_Plot_Util('option',data,'series_labels',{});
if ~isempty(labels)&&numel(labels)~=count, error('TestProject:Plot:CurveLabels','Curve label count mismatch.'); end
styles=Test_Project_Plot_Util('option',options,'series_styles',struct([]));
if ~isstruct(styles)||numel(styles)>count, error('TestProject:Plot:CurveStyles','Invalid curve series styles.'); end
old=findobj(ax,'Type','line');
for k=1:numel(old)
    if startsWith(old(k).Tag,'test_curve'), set(old(k),'Visible','off'); end
end
for k=1:count
    tag='test_curve'; if k>1, tag=sprintf('test_curve_%d',k); end
    h(k)=Test_Project_Plot_Util('line',ax,tag,x(:,min(k,size(x,2))),y(:,k));
    color=colors(mod(k-1,size(colors,1))+1,:);
    if count==1, color=Test_Project_Plot_Util('option',options,'color',color); end
    style=struct(); if numel(styles)>=k, style=styles(k); end
    color=Test_Project_Plot_Util('option',style,'color',color);
    marker=Test_Project_Plot_Util('option',style,'marker','none');
    lineStyle=Test_Project_Plot_Util('option',style,'line_style','-');
    markerFace=Test_Project_Plot_Util('option',style,'marker_face_color','none');
    set(h(k),'Color',color,'LineWidth',1,'Visible','on','Marker',marker,'LineStyle',lineStyle, ...
        'MarkerFaceColor',markerFace);
    if ~isempty(labels), set(h(k),'DisplayName',char(string(labels(k)))); end
end
if ~isempty(labels), legend(ax,h,'Location','best','Interpreter','none'); else, legend(ax,'off'); end
xlabel(ax,Test_Project_Plot_Util('option',data,'x_unit',''),'Interpreter','none');
ylabel(ax,Test_Project_Plot_Util('option',data,'y_unit',''),'Interpreter','none');
xLimits=Test_Project_Plot_Util('option',options,'x_limits',[]);
yLimits=Test_Project_Plot_Util('option',options,'y_limits',[]);
if ~isempty(xLimits), xlim(ax,xLimits); end
if ~isempty(yLimits), ylim(ax,yLimits); end
state=struct('handle',h);
end
