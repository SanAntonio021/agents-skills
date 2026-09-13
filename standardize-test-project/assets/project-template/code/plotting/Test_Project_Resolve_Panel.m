function data = Test_Project_Resolve_Panel(analysis, panel)
%TEST_PROJECT_RESOLVE_PANEL Resolve one immutable numerical source.
if isstruct(panel.data_ref) && ~isempty(fieldnames(panel.data_ref))
    if ~isempty(fieldnames(panel.data)), error('TestProject:Plot:PanelSource','Provide data OR data_ref.'); end
    r=panel.data_ref; k=find(strcmp({analysis.channels.id},r.channel_id),1);
    if isempty(k)||~ismember(r.field,{'waveform','spectrum'})
        error('TestProject:Plot:MissingReference','面板引用的数据不存在');
    end
    data=analysis.channels(k).(r.field);
else
    data=panel.data;
end
end
