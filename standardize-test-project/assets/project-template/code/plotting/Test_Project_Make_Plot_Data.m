function plotData = Test_Project_Make_Plot_Data(analysis, profile, panels, source, view)
%TEST_PROJECT_MAKE_PLOT_DATA Compose reusable panels without re-running analysis.
if nargin<3, panels=struct([]); end
if nargin<4, source=struct(); end
if nargin<5, view=struct(); end
base=struct('id','','kind','','title','','status','ok','reason','', ...
    'depends_on',{{}},'data_ref',struct(),'data',struct(),'options',struct());
allPanels=repmat(base,1,0);
for k=1:numel(analysis.channels)
    c=analysis.channels(k); kinds={'waveform','spectrum'}; labels={'波形','频谱'};
    for j=1:2
        p=base; p.id=[c.id '_' kinds{j}]; p.kind=kinds{j};
        if strcmp(c.role,'signal'), p.title=[c.id ' ' labels{j}];
        else, p.title=[c.id ' / ' c.role ' ' labels{j}]; end
        p.data_ref=struct('channel_id',c.id,'field',kinds{j});
        p.options.color=Test_Project_Plot_Util('color',c.role);
        if j==1, p.options.stats=c.stats; end
        allPanels(end+1)=p; %#ok<AGROW>
    end
end
for k=1:numel(panels)
    p=base; fields=fieldnames(panels(k));
    for j=1:numel(fields), p.(fields{j})=panels(k).(fields{j}); end
    allPanels(end+1)=p; %#ok<AGROW>
end
plotData=struct('schema_name','test_project_plot_data','schema_version',1, ...
    'profile',char(profile),'source',source,'analysis',analysis,'panels',allPanels,'view',view);
plotData=Test_Project_Validate_Plot_Data(plotData);
end
