function tests=Test_Test_Project_Plot_Contract
%TEST_TEST_PROJECT_PLOT_CONTRACT Hardware-free v1 persistence/render tests.
tests=functiontests(localfunctions);
end

function setupOnce(testCase)
projectRoot=fileparts(fileparts(fileparts(mfilename('fullpath'))));
testCase.TestData.OriginalPath=path;
addpath(fullfile(projectRoot,'code','plotting'),fullfile(projectRoot,'code','result_management'));
requestedRoot=getenv('TEST_PROJECT_PLOT_TEST_OUTPUT');
if isempty(requestedRoot), outputRoot=[tempname '_plot_contract'];
else, outputRoot=tempname(requestedRoot); end
mkdir(outputRoot); testCase.TestData.OutputDir=outputRoot;
fprintf('PLOT_CONTRACT_OUTPUT=%s\n',outputRoot);
end

function teardownOnce(testCase)
path(testCase.TestData.OriginalPath);
% Retain only this test's isolated evidence; no source/raw/archive cleanup.
end

function testRoundTripAndDisplayedFrame(testCase)
[pd,channels]=fixture(2048,2); original=pd;
file=fullfile(testCase.TestData.OutputDir,'roundtrip','data','test_plot_data.mat');
Test_Project_Save_Plot_Data(file,pd);
loaded=Test_Project_Load_Plot_Data(file);
verifyTrue(testCase,isequaln(loaded,original));
verifyEqual(testCase,loaded.analysis.channels(1).waveform.samples_v,channels(1).samples);
verifyEqual(testCase,loaded.source.frame_id,'synthetic-frame-001');
verifyError(testCase,@() Test_Project_Save_Plot_Data(file,pd),'TestProject:Plot:OutputExists');
next=pd; next.source.frame_id='synthetic-frame-002';
verifyError(testCase,@() Test_Project_Plot_Test(fullfile(fileparts(fileparts(file)),'wrong_frame.png'),next), ...
    'TestProject:Plot:FrameMismatch');
verifyFalse(testCase,isfile(fullfile(fileparts(fileparts(file)),'wrong_frame.png')));
end

function testOverviewIndependentAndGeometry(testCase)
[pd,~]=fixture(4096,2); original=pd;
folder=fullfile(testCase.TestData.OutputDir,'exports');
normal=Test_Project_Plot_Test(fullfile(folder,'overview.png'),pd,struct('target_size_px',[1920 1080]));
archiveHash=sha256(normal.ArchivePath);
compact=Test_Project_Plot_Test(fullfile(folder,'compact.png'),pd,struct('target_size_px',[1440 810]));
single=Test_Project_Plot_Test(fullfile(folder,'CH1_spectrum.png'),pd, ...
    struct('panel_ids',{{'CH1_spectrum'}},'target_size_px',[1440 810], ...
    'frequency_limits_hz',[0 1e9]));
verifyImage(testCase,normal.OutputPaths{1},[1920 1080]);
verifyImage(testCase,compact.OutputPaths{1},[1440 810]);
verifyImage(testCase,single.OutputPaths{1},[1440 810]);
verifyEqual(testCase,numel(single.PanelStatus),1);
verifyEqual(testCase,single.PanelStatus{1}.id,'CH1_spectrum');
verifyTrue(testCase,isequaln(pd,original));
verifyTrue(testCase,isequaln(Test_Project_Load_Plot_Data(normal.ArchivePath),original));
verifyEqual(testCase,sha256(normal.ArchivePath),archiveHash);
end

function testRealTimeHandlesReuseFullFrame(testCase)
[pd,channels]=fixture(65536,1); original=pd;
fig=figure('Visible','off','Position',[50 50 1440 810]); clean=onCleanup(@() close(fig)); %#ok<NASGU>
layout=tiledlayout(fig,1,2); ax1=nexttile(layout); ax2=nexttile(layout);
c=pd.analysis.channels(1);
a=Test_Project_Draw_Waveform(ax1,c.waveform,struct('stats',c.stats));
b=Test_Project_Draw_Spectrum(ax2,c.spectrum);
drawnow;
a2=Test_Project_Draw_Waveform(ax1,c.waveform,struct('stats',c.stats));
b2=Test_Project_Draw_Spectrum(ax2,c.spectrum);
verifyEqual(testCase,a2.handle,a.handle);
verifyEqual(testCase,b2.handle,b.handle);
verifyLessThan(testCase,numel(a.display_indices),numel(channels.samples));
visibleTime=c.waveform.time_s(a.display_indices);
verifyGreaterThanOrEqual(testCase,nnz(visibleTime>=0 & visibleTime<=10e-9),75, ...
    'A zoomed 10 ns window must retain its waveform cycles before display thinning.');
verifyEqual(testCase,pd.analysis.channels.waveform.samples_v,channels.samples);
verifyTrue(testCase,isequaln(pd,original));
file=fullfile(testCase.TestData.OutputDir,'displayed','data','test_plot_data.mat');
Test_Project_Save_Plot_Data(file,pd);
saved=Test_Project_Load_Plot_Data(file);
verifyEqual(testCase,numel(saved.analysis.channels.waveform.samples_v),65536);
verifyEqual(testCase,saved.source.frame_id,pd.source.frame_id);
end

function testFailuresPropagateAndVersionBoundary(testCase)
[pd,~]=fixture(1024,1);
p=struct('id','sync','kind','curve','title','合成失败','status','failed', ...
    'reason','injected failure','depends_on',{{}},'data_ref',struct(),'data',struct(),'options',struct());
q=p; q.id='equalized'; q.kind='constellation'; q.title='依赖阶段'; q.status='ok'; q.reason=''; q.depends_on={'sync'};
value=Test_Project_Make_Plot_Data(pd.analysis,'demodulation',[p q],pd.source,pd.view);
verifyEqual(testCase,value.panels(end-1).status,'failed');
verifyEqual(testCase,value.panels(end).status,'skipped');
verifyNotEmpty(testCase,value.panels(end).reason);
unknown=pd; unknown.schema_version=2;
verifyError(testCase,@() Test_Project_Validate_Plot_Data(unknown),'TestProject:Plot:UnsupportedVersion');
plotData=unknown; %#ok<NASGU>
file=fullfile(testCase.TestData.OutputDir,'unknown.mat'); save(file,'plotData');
verifyError(testCase,@() Test_Project_Load_Plot_Data(file),'TestProject:Plot:UnsupportedVersion');
end

function testLegacyBoundaryAndEmbeddedArchive(testCase)
[pd,~]=fixture(1024,1);
folder=fullfile(testCase.TestData.OutputDir,'legacy'); mkdir(folder);
legacy_scalar=pi; legacy_payload=struct('note','preserved','values',[1 3 5]); %#ok<NASGU>
file=fullfile(folder,'plot_data.mat'); save(file,'legacy_scalar','legacy_payload');
verifyError(testCase,@() Test_Project_Load_Plot_Data(file),'TestProject:Plot:LegacyArchive');
try
    Test_Project_Load_Plot_Data(file);
catch err
    verifyTrue(testCase,contains(err.message,'原读取器'));
end
Test_Project_Save_Plot_Data(file,pd);
raw=load(file);
verifyEqual(testCase,raw.legacy_scalar,pi);
verifyEqual(testCase,raw.legacy_payload,legacy_payload);
verifyTrue(testCase,isfield(raw,'test_plot_data'));
verifyTrue(testCase,isequaln(Test_Project_Load_Plot_Data(file),pd));
verifyError(testCase,@() Test_Project_Save_Plot_Data(file,pd),'TestProject:Plot:OutputExists');
end

function testPaginationAndQpskStages(testCase)
[pd,~]=fixture(1024,1);
p=struct('id','','kind','curve','title','','status','ok','reason','', ...
    'depends_on',{{}},'data_ref',struct(),'data',struct(),'options',struct());
panels=repmat(p,1,11);
for k=1:10
    panels(k).id=sprintf('diagnostic_%02d',k);
    panels(k).title=sprintf('合成诊断阶段 %d',k);
    panels(k).data=struct('x',(1:16)','y',sin((1:16)'/k), ...
        'x_unit','符号序号','y_unit','归一化输入 / 1');
end
panels(11).id='qpsk'; panels(11).kind='constellation'; panels(11).title='合成 QPSK 阶段';
qpsk=[1+1i;1-1i;-1+1i;-1-1i]/sqrt(2);
panels(11).data=struct('symbols',repmat(qpsk,16,1),'ideal_symbols',qpsk);
value=Test_Project_Make_Plot_Data(pd.analysis,'demodulation',panels,pd.source,pd.view);
verifyEqual(testCase,numel(value.panels),13);
details=Test_Project_Plot_Test(fullfile(testCase.TestData.OutputDir,'pagination','overview.png'),value, ...
    struct('target_size_px',[1440 810]));
verifyEqual(testCase,numel(details.OutputPaths),2);
verifyTrue(testCase,contains(details.OutputPaths{1},'_p01.png'));
verifyTrue(testCase,contains(details.OutputPaths{2},'_p02.png'));
verifyImage(testCase,details.OutputPaths{2},[1440 810]);
end

function testReplotNewRunsSourceUnchanged(testCase)
[pd,~]=fixture(2048,1);
source=fullfile(testCase.TestData.OutputDir,'source','data','test_plot_data.mat');
Test_Project_Save_Plot_Data(source,pd); before=sha256(source);
project=fullfile(testCase.TestData.OutputDir,'replot_project');
mkdir(project);
a=Test_Project_Replot_Test(source,project,struct('target_size_px',[1440 810]));
b=Test_Project_Replot_Test(source,project,struct('target_size_px',[1440 810]));
verifyNotEqual(testCase,a.Run.OutputDir,b.Run.OutputDir);
verifyTrue(testCase,isfile(fullfile(a.Run.OutputDir,'data','sources.txt')));
sourceRun=fileparts(fileparts(source));
verifyTrue(testCase,contains(fileread(fullfile(a.Run.OutputDir,'data','sources.txt')),sourceRun));
info=jsondecode(fileread(fullfile(a.Run.OutputDir,'data','run_info.json')));
verifyEqual(testCase,info.plot_source.path,char(java.io.File(source).getCanonicalPath()));
verifyEqual(testCase,info.plot_source.frame_source.frame_id,pd.source.frame_id);
verifyEqual(testCase,sha256(source),before);
verifyTrue(testCase,isequaln(Test_Project_Load_Plot_Data(a.ArchivePath),pd));
verifyTrue(testCase,isequaln(Test_Project_Load_Plot_Data(b.ArchivePath),pd));
end

function testPerformanceRecordsNoFrameRateClaim(testCase)
sizes=[1920 1080;1440 810]; lengths=[65536 1048576];
records=struct('sample_count',{},'channel_count',{},'target_size_px',{}, ...
    'analysis_seconds',{},'draw_seconds',{});
for n=lengths
    for count=1:2
        channels=makeChannels(n,count);
        start=tic; analysis=Test_Project_Analyze_Capture(channels); analysisSeconds=toc(start);
        for sizeIndex=1:2
            fig=figure('Visible','off','Position',[50 50 sizes(sizeIndex,:)]);
            clean=onCleanup(@() close(fig));
            layout=tiledlayout(fig,count,2); axesHandles=gobjects(count,2);
            for k=1:count
                axesHandles(k,1)=nexttile(layout); axesHandles(k,2)=nexttile(layout);
            end
            start=tic;
            for k=1:count
                Test_Project_Draw_Waveform(axesHandles(k,1),analysis.channels(k).waveform);
                Test_Project_Draw_Spectrum(axesHandles(k,2),analysis.channels(k).spectrum);
            end
            drawnow; drawSeconds=toc(start);
            records(end+1)=struct('sample_count',n,'channel_count',count, ...
                'target_size_px',sizes(sizeIndex,:),'analysis_seconds',analysisSeconds, ...
                'draw_seconds',drawSeconds); %#ok<AGROW>
            clear clean;
        end
    end
end
verifyEqual(testCase,numel(records),8);
verifyTrue(testCase,all(isfinite([records.analysis_seconds]))&&all([records.analysis_seconds]>0));
verifyTrue(testCase,all(isfinite([records.draw_seconds]))&&all([records.draw_seconds]>0));
report=struct('kind','synthetic_software_timing','not_instrument_fps',true,'records',records);
file=fullfile(testCase.TestData.OutputDir,'plot_performance.json');
fid=fopen(file,'w','n','UTF-8'); clean=onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid,'%s\n',jsonencode(report));
end

function [pd,channels]=fixture(n,count)
channels=makeChannels(n,count);
analysis=Test_Project_Analyze_Capture(channels,struct('power_band_hz',[.2e9 .8e9]));
profile='single_channel'; if count==2, profile='iq_observation'; end
pd=Test_Project_Make_Plot_Data(analysis,profile,struct([]), ...
    struct('kind','synthetic','frame_id','synthetic-frame-001'),struct('title','合成契约测试'));
end

function channels=makeChannels(n,count)
fs=8e9; time=(0:n-1)'/fs;
c=struct('id','CH1','role','signal','samples',.15*cos(2*pi*.5e9*time)+.01, ...
    'time_s',time,'impedance_ohm',50,'impedance_source','synthetic fixture', ...
    'sync_verified',false,'voltage_limits_v',[-.5 .5],'time_limits_s',[0 10e-9]);
channels=repmat(c,1,count);
if count==2
    channels(1).role='I'; channels(2).role='Q'; channels(2).id='CH2';
    channels(2).samples=.12*sin(2*pi*.5e9*time);
end
end

function verifyImage(testCase,file,expectedSize)
verifyTrue(testCase,isfile(file)); info=imfinfo(file);
verifyEqual(testCase,[info.Width info.Height],expectedSize);
pixels=imread(file); verifyGreaterThan(testCase,std(double(pixels(:))),2);
end

function value=sha256(file)
fid=fopen(file,'rb'); clean=onCleanup(@() fclose(fid)); %#ok<NASGU>
bytes=fread(fid,Inf,'*uint8'); digest=java.security.MessageDigest.getInstance('SHA-256');
digest.update(bytes); value=lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
end
