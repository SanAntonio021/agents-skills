function outputs = Run_Test_Project_Plot_Demos(outputRoot)
%RUN_TEST_PROJECT_PLOT_DEMOS Synthetic examples; never acquire or control devices.
% outputs contains image/archive paths for single-channel, IQ and DSP stages.
if nargin~=1 || isempty(outputRoot)
    error('TestProject:Demo:OutputRoot','Provide a new outputRoot explicitly.');
end
outputRoot=char(outputRoot);
if isfolder(outputRoot) || isfile(outputRoot)
    error('TestProject:Demo:OutputExists','Use a new outputRoot; existing data is preserved.');
end
root=fileparts(mfilename('fullpath')); oldPath=path;
cleanupPath=onCleanup(@() path(oldPath)); %#ok<NASGU>
addpath(fullfile(root,'code','plotting'),fullfile(root,'code','result_management'));
previousRng=rng; cleanupRng=onCleanup(@() rng(previousRng)); %#ok<NASGU>
rng(20260913,'twister');
mkdir(outputRoot);
fs=8e9; n=32768; time=(0:n-1)'/fs;
base=struct('id','CH1','role','signal','samples',[], 'time_s',time, ...
    'impedance_ohm',50,'impedance_source','synthetic 50 ohm fixture', ...
    'sync_verified',false,'voltage_limits_v',[-.5 .5], ...
    'time_limits_s',[0 10e-9]);
single=base;
single.samples=.06+.2*cos(2*pi*.65e9*time)+.015*randn(n,1);
analysis=Test_Project_Analyze_Capture(single,struct('power_band_hz',[.5e9 .8e9]));
source=struct('kind','synthetic','frame_id','synthetic-single-001','seed',20260913);
pd=Test_Project_Make_Plot_Data(analysis,'single_channel',struct([]),source, ...
    struct('title','单通道观察（仿真）'));
outputs.single_channel=renderPair(outputRoot,'single_channel',pd);

iq=repmat(base,1,2); iq(1).role='I'; iq(2).role='Q'; iq(2).id='CH2';
iq(1).samples=.24*cos(2*pi*.5e9*time)+.02*randn(n,1);
iq(2).samples=.19*sin(2*pi*.5e9*time)+.01+.02*randn(n,1);
% Raw observation deliberately does not assert instrument synchronization.
analysis=Test_Project_Analyze_Capture(iq,struct('power_band_hz',[.35e9 .65e9]));
source.frame_id='synthetic-iq-001';
pd=Test_Project_Make_Plot_Data(analysis,'iq_observation',struct([]),source, ...
    struct('title','IQ 观察（仿真）'));
outputs.iq_observation=renderPair(outputRoot,'iq_observation',pd);

% Each stage below is an explicit synthetic fixture, not a demodulator.
% The same payload symbols are retained across all four displayed stages.
levels=[-3 -1 1 3]; [re,im]=meshgrid(levels,levels);
ideal=(re(:)+1i*im(:))/sqrt(10); tx=ideal(randi(16,12288,1));
phase=.22+.35*sin(linspace(0,2*pi,numel(tx))');
noise=(randn(size(tx))+1i*randn(size(tx)));
before=1.1*tx.*exp(1i*phase)+.15*noise;
fixed=tx.*exp(1i*phase)+.075*noise;
joint=tx.*exp(1i*.025)+.038*noise;
final=tx+.025*noise;
trainingIdeal=exp(1i*(pi/4+(0:3)'*pi/2));
training=trainingIdeal(randi(4,2048,1))+.025*(randn(2048,1)+1i*randn(2048,1));
demodIq=iq;
demodRaw=repelem(before,2); demodTime=(0:numel(demodRaw)-1)'/fs;
for k=1:2
    demodIq(k).time_s=demodTime;
    demodIq(k).time_limits_s=[0 demodTime(end)];
    demodIq(k).voltage_limits_v=[-.4 .4];
end
demodIq(1).samples=.18*real(demodRaw); demodIq(2).samples=.18*imag(demodRaw);
analysis=Test_Project_Analyze_Capture(demodIq,struct('power_band_hz',[0 2.3e9]));
panels=repmat(panelTemplate(),1,9);
syncTime=linspace(0,demodTime(end)*1e6,4096)'; syncMetric=.012*rand(4096,1);
syncPeaks=[];
for center=[.15 .92 1.69 2.46]
    syncMetric=syncMetric+.97*exp(-.5*((syncTime-center)/.012).^2);
    [~,peak]=min(abs(syncTime-center)); syncPeaks(end+1)=peak; %#ok<AGROW>
end
peakTrace=nan(size(syncMetric)); peakTrace(syncPeaks)=syncMetric(syncPeaks);
selectedTrace=nan(size(syncMetric)); selectedTrace(syncPeaks(1))=syncMetric(syncPeaks(1));
panels(1)=panel('synchronization','curve','重复 ZC 同步', ...
    struct('x',syncTime,'y',[syncMetric peakTrace selectedTrace],'x_unit','采集时间（μs）','y_unit','相关度'),{});
panels(1).options.series_styles=styles({'none','o','o'},{'-','none','none'},[0 114 178;213 85 0;190 25 35]/255);
panels(1).options.series_styles(3).marker_face_color=[190 25 35]/255;
panels(1).options.x_limits=[0 demodTime(end)*1e6];
panels(1).options.y_limits=[0 1.2];
offsets=(-8:8)'; nmseDb=-31+.11*(offsets-2).^2;
selectedNmse=nan(size(nmseDb)); selectedNmse(offsets==2)=nmseDb(offsets==2);
panels(2)=panel('training_search','curve','训练窗口对齐搜索', ...
    struct('x',offsets,'y',[nmseDb selectedNmse],'x_unit','训练位置偏移（样点）','y_unit','训练 NMSE（dB）'),{'synchronization'});
panels(2).options.series_styles=styles({'o','o'},{'none','none'},[0 114 178;190 25 35]/255);
panels(2).options.series_styles(2).marker_face_color=[190 25 35]/255;
panels(3)=panel('training','constellation','均衡后训练星座', ...
    struct('symbols',training,'ideal_symbols',trainingIdeal,'symbol_set_id','training-fixture'),{'training_search'});
panels(3).options.color=[213 85 0]/255;
serviceTime=(0:numel(tx)-1)'/(fs/2)*1e6;
panels(4)=panel('phase_tracking','curve','业务区相位跟踪', ...
    struct('x',serviceTime,'y',phase*180/pi,'x_unit','业务区时间（μs）','y_unit','相位补偿（°）'),{'training'});
error=abs(.038*noise); windows=ceil(numel(error)/512);
windowTime=zeros(windows,1); windowRms=windowTime; windowPeak=windowTime; peakTime=windowTime;
for k=1:windows
    indices=(k-1)*512+1:min(k*512,numel(error));
    windowTime(k)=mean(serviceTime(indices)); windowRms(k)=sqrt(mean(error(indices).^2));
    [windowPeak(k),j]=max(error(indices)); peakTime(k)=serviceTime(indices(j));
end
panels(5)=panel('tracking_error','curve','业务区联合跟踪误差', ...
    struct('x',[windowTime peakTime],'y',[windowRms windowPeak], ...
    'series_labels',{{'窗内均方根误差','窗内最大误差'}}, ...
    'x_unit','业务区时间（μs）','y_unit','误差幅度'),{'phase_tracking'});
panels(5).options.series_styles=styles({'none','^'},{'-','none'},[0 114 178;213 85 0]/255);
panels(5).options.series_styles(2).marker_face_color=[213 85 0]/255;
panels(4).options.x_limits=[0 numel(tx)/(fs/2)*1e6];
panels(5).options.x_limits=panels(4).options.x_limits;
panels(5).options.y_limits=[0 max(windowPeak)*1.3];
ids={'before_equalization','fixed_equalization','joint_tracking','final_pilot'};
titles={'均衡前业务星座','固定均衡后业务星座','联合跟踪后业务星座','最终导频校正后业务星座'};
stages={before,fixed,joint,final};
for k=1:4
    panels(k+5)=panel(ids{k},'constellation',titles{k}, ...
        struct('symbols',stages{k},'ideal_symbols',ideal,'symbol_set_id','payload-fixture'),{});
    panels(k+5).options.comparison_group='payload';
end
panels(9).data.metrics=struct('EVM_percent',100*sqrt(mean(abs(final-tx).^2)/mean(abs(tx).^2)));
source.frame_id='synthetic-demod-001';
source.stage_data_origin='Explicitly constructed synthetic stage fixtures; no receiver DSP executed.';
view=demodView('CH1','CH2'); view.title='16QAM 接收处理总览（仿真）';
view.signal_band_hz=[0 2.3e9];
pd=Test_Project_Make_Plot_Data(analysis,'demodulation',panels,source,view);
outputs.demodulation=renderPair(outputRoot,'demodulation',pd);
outputs.output_root=outputRoot;
disp(outputs);
end

function output=renderPair(root,name,pd)
folder=fullfile(root,name);
normal=Test_Project_Plot_Test(fullfile(folder,'overview.png'),pd, ...
    struct('target_size_px',[1920 1080]));
compact=Test_Project_Plot_Test(fullfile(folder,'overview_compact.png'),pd, ...
    struct('target_size_px',[1440 810]));
output=struct('normal',{normal.OutputPaths},'compact',{compact.OutputPaths}, ...
    'archive',normal.ArchivePath);
end

function p=panelTemplate()
p=struct('id','','kind','','title','','status','ok','reason','', ...
    'depends_on',{{}},'data_ref',struct(),'data',struct(),'options',struct());
end
function p=panel(id,kind,title,data,dependencies)
p=panelTemplate(); p.id=id; p.kind=kind; p.title=title;
p.data=data; p.depends_on=dependencies;
end

function view=demodView(i,q)
titles={'1 原始采集波形','2 通道信号频谱','3 重复 ZC 同步','4 训练窗口对齐搜索', ...
    '5 均衡后训练星座','6 业务区相位跟踪','11 业务区联合跟踪误差', ...
    '7 业务星座：均衡前','8 业务星座：固定均衡后', ...
    '9 业务星座：联合跟踪后','10 业务星座：最终导频校正后'};
ids={{[i '_waveform'],[q '_waveform']},{[i '_spectrum'],[q '_spectrum']}, ...
    {'synchronization'},{'training_search'},{'training'},{'phase_tracking'}, ...
    {'tracking_error'},{'before_equalization'},{'fixed_equalization'},{'joint_tracking'},{'final_pilot'}};
positions=[1 1 1 1;1 2 1 1;1 3 1 1;1 4 1 1;2 1 1 1;2 2 1 1;2 3 1 2; ...
    3 1 1 1;3 2 1 1;3 3 1 1;3 4 1 1];
groups=repmat(struct('id','','title','','panel_ids',{{}},'position',[]),1,11);
for k=1:11
    groups(k)=struct('id',sprintf('group_%d',k),'title',titles{k},'panel_ids',{ids{k}},'position',positions(k,:));
end
view=struct('grid_size',[3 4],'groups',groups);
end
function result=styles(markers,lines,colors)
result=repmat(struct('marker','','line_style','','color',[]),1,numel(markers));
for k=1:numel(markers)
    result(k)=struct('marker',markers{k},'line_style',lines{k},'color',colors(k,:));
end
end