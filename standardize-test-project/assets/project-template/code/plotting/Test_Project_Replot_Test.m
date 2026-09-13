function details = Test_Project_Replot_Test(sourcePath, projectRoot, options)
%TEST_PROJECT_REPLOT_TEST New analysis run from saved figures, no DSP calls.
if nargin<3, options=struct(); end
plotData=Test_Project_Load_Plot_Data(sourcePath);
sourcePath=char(java.io.File(char(sourcePath)).getCanonicalPath());
sourceRun=sourcePath;
if isfile(sourcePath)
    sourceRun=fileparts(sourcePath);
    [~,last]=fileparts(sourceRun);
    if strcmp(last,'data'), sourceRun=fileparts(sourceRun); end
end
run=Result_Create_Run(struct('ProjectRoot',char(projectRoot),'RunType','analysis', ...
    'NameParts',{{'绘图重绘'}},'RunPurpose','validation','ExecutionMode','offline_analysis'));
try
    Result_Write_Sources(run,{sourceRun});
    Result_Update_Run_Info(run,struct('plot_source',struct('path',sourcePath, ...
        'frame_source',plotData.source)));
    details=Test_Project_Plot_Test(fullfile(run.OutputDir,'overview.png'),plotData,options);
    Result_Update_Run_Info(run,struct('status','completed','finished_at',char(datetime('now'))));
    Result_Log_Stage(run,'INFO','replot','Numerical plot archive rendered; no DSP or instrument I/O.');
catch err
    Result_Update_Run_Info(run,struct('status','failed','stop_reason',err.identifier,'stop_detail',err.message));
    rethrow(err);
end
details.Run=run;
end
