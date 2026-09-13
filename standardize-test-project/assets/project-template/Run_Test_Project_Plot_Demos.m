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
    struct('title','合成示例：单通道原始电压与频谱'));
outputs.single_channel=renderPair(outputRoot,'single_channel',pd);

iq=repmat(base,1,2); iq(1).role='I'; iq(2).role='Q'; iq(2).id='CH2';
iq(1).samples=.24*cos(2*pi*.5e9*time)+.02*randn(n,1);
iq(2).samples=.19*sin(2*pi*.5e9*time)+.01+.02*randn(n,1);
% Raw observation deliberately does not assert instrument synchronization.
analysis=Test_Project_Analyze_Capture(iq,struct('power_band_hz',[.35e9 .65e9]));
source.frame_id='synthetic-iq-001';
pd=Test_Project_Make_Plot_Data(analysis,'iq_observation',struct([]),source, ...
    struct('title','合成示例：I/Q 原始观察（未声明采集同步）'));
outputs.iq_observation=renderPair(outputRoot,'iq_observation',pd);

% This fixture explicitly supplies DSP-aligned stage data; no DSP is hidden
% in a renderer. Both constellations contain the same synthetic payload set.
levels=[-3 -1 1 3]; [re,im]=meshgrid(levels,levels);
ideal=(re(:)+1i*im(:))/sqrt(10); tx=ideal(randi(16,4096,1));
before=tx.*exp(1i*.15)+.11*(randn(size(tx))+1i*randn(size(tx)));
after=tx+.035*(randn(size(tx))+1i*randn(size(tx)));
dsp=struct('samples',repelem(after,4),'fs_hz',fs, ...
    'alignment_basis','dsp_aligned','stage_id','synthetic_equalized', ...
    'amplitude_unit','dimensionless');
spectrum=Test_Project_Complex_Spectrum(dsp);
panels=repmat(panelTemplate(),1,6);
panels(1)=panel('complex_psd','spectrum','合成示例：均衡后复基带频谱',spectrum,{});
lags=(-128:128)'; corr=.03+.95*exp(-.5*((lags-17)/3).^2);
panels(2)=panel('synchronization','curve','合成示例：同步相关曲线', ...
    struct('x',lags,'y',corr,'x_unit','候选延迟 / 样点','y_unit','相关幅度 / 1'),{});
panels(3)=panel('before_equalization','constellation','合成示例：均衡前业务符号', ...
    struct('symbols',before,'ideal_symbols',ideal,'symbol_set_id','payload-001'),{'synchronization'});
panels(4)=panel('after_equalization','constellation','合成示例：均衡后业务符号', ...
    struct('symbols',after,'ideal_symbols',ideal,'symbol_set_id','payload-001'),{'before_equalization'});
panels(3).options.comparison_group='payload';
panels(4).options.comparison_group='payload';
panels(5)=panel('failed_tracking','curve','合成示例：跟踪失败',struct(),{'after_equalization'});
panels(5).status='failed'; panels(5).reason='人为注入的离线示例失败';
panels(6)=panel('dependent_stage','constellation','合成示例：后续结果跳过',struct(),{'failed_tracking'});
source.frame_id='synthetic-demod-001';
pd=Test_Project_Make_Plot_Data(analysis,'demodulation',panels,source, ...
    struct('title','合成示例：实际阶段数据驱动的解调诊断'));
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
