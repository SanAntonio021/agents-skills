function plotData = Test_Project_Load_Plot_Data(path)
%TEST_PROJECT_LOAD_PLOT_DATA Read v1; legacy formats retain their original readers.
path=char(path);
if isfolder(path)
    candidates={fullfile(path,'data','test_plot_data.mat'),fullfile(path,'data','plot_data.mat'),fullfile(path,'plot_data.mat')};
    found=find(cellfun(@isfile,candidates),1);
    if isempty(found), error('TestProject:Plot:MissingArchive','No numerical plot package.'); end
    path=candidates{found};
end
vars=whos('-file',path); names={vars.name};
if ismember('plotData',names), value=load(path,'plotData'); plotData=value.plotData;
elseif ismember('test_plot_data',names), value=load(path,'test_plot_data'); plotData=value.test_plot_data;
else
    error('TestProject:Plot:LegacyArchive','旧记录请沿用项目原读取器；缺少数值的独立图不可补造。');
end
plotData=Test_Project_Validate_Plot_Data(plotData);
end
