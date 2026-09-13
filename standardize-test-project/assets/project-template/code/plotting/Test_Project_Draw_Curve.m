function state = Test_Project_Draw_Curve(ax, data, options)
%TEST_PROJECT_DRAW_CURVE Display provided diagnostic samples, retaining gaps.
if nargin<3, options=struct(); end
Test_Project_Plot_Util('decorate',ax,options);
if numel(data.x)~=numel(data.y), error('TestProject:Plot:CurveSize','Curve size mismatch.'); end
h=Test_Project_Plot_Util('line',ax,'test_curve',data.x(:),data.y(:));
set(h,'Color',Test_Project_Plot_Util('option',options,'color',[0 114 178]/255),'LineWidth',1);
xlabel(ax,Test_Project_Plot_Util('option',data,'x_unit',''),'Interpreter','none');
ylabel(ax,Test_Project_Plot_Util('option',data,'y_unit',''),'Interpreter','none');
state=struct('handle',h);
end
