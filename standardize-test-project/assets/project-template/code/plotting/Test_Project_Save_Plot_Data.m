function path = Test_Project_Save_Plot_Data(path, plotData)
%TEST_PROJECT_SAVE_PLOT_DATA Persist numerical v1 data, never display caches.
plotData=Test_Project_Validate_Plot_Data(plotData);
path=char(path); [folder,name,ext]=fileparts(path);
if ~strcmpi(ext,'.mat'), error('TestProject:Plot:MatRequired','A MAT path is required.'); end
if ~isempty(folder)&&~isfolder(folder), mkdir(folder); end
if isfile(path)
    vars=whos('-file',path);
    if strcmp(name,'plot_data') && ~any(strcmp({vars.name},'test_plot_data'))
        test_plot_data=plotData; %#ok<NASGU>
        save(path,'test_plot_data','-append'); % preserve every existing outer variable
        return;
    end
    error('TestProject:Plot:OutputExists','Plot data exists; use a new run.');
end
save(path,'plotData','-v7.3');
end
