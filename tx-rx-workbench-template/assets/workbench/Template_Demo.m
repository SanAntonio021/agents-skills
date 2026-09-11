function report = Template_Demo(output_dir)
%TEMPLATE_DEMO Deterministic waveform generation, real RX DSP, and plots; no I/O.
guard=Template_NoHardware(); %#ok<NASGU>
root=fileparts(mfilename('fullpath'));
if nargin<1, output_dir=fullfile(root,'analysis',['template_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]); end
assert(~isfolder(output_dir),'Choose a new output directory.');
mkdir(output_dir); mkdir(fullfile(output_dir,'data'));
cfg=msiq.build_config('v2_traditional_wz');
cfg.instrument.awg.mock=true; cfg.instrument.scope.mock=true;
cfg.instrument.signal_generator.mock=true;
cfg.safety.hardware_enabled=false;
msiq.instruments.reset_audit();
plan=TX_Workbench('preview_plan',[],struct('cfg_override',cfg, ...
    'route','pair_b_ch3_ch4','rdiv','DIV4','frame_repetitions',1,'seed',26072701));
assert(plan.memory_capacity.ok);
cfg=plan.cfg;
prepared=msiq.instruments.prepare_awg_download(plan.waveforms.awg_dac_data,1:4,1:4,128);
playback=plan.waveforms;
playback.master_dac_data=round(127*[prepared.channel_data{:}])/127;
playback.master_sample_rate_hz=playback.awg_sample_rate_hz;
sim=msiq.simulate_capture(playback,cfg,'A',struct('snr_db',42, ...
    'cfo_hz',0,'sro_ppm',0,'prepend_samples',777,'capture_repetitions',6,'rng_seed',7071));
decoded=msiq.decode_capture(sim,plan.tx_ref,cfg);
assert(decoded.pass,'The deterministic reference simulation must decode.');
raw=struct();
for k=1:2
    raw.channels(k)=struct('channel',sprintf('C%d',k+2), ...
        'samples',sim.samples(:,k),'time_axis_s',sim.time_axes(:,k), ...
        'sample_rate_hz',sim.sample_rate_hz);
end
context=struct('cfg',cfg,'tx_ref',plan.tx_ref,'scope_status',struct());
for k=1:2
    context.scope_status.channels(k)=struct('name',sprintf('C%d',k+2), ...
        'impedance_ohm',50,'vertical_scale_v_per_div',.25,'offset_v',0, ...
        'bandwidth_limit_hz',Inf);
end
result=struct('status','decoded','pairs',struct('name','pair_b','status','decoded','decoded',decoded));
validation=struct('ok',true,'reason','','summary',struct());
sizes={[1920 1080],[1440 810]};
report=struct('execution_mode','simulation','decoded_pass',decoded.pass,'output_dir',output_dir);
for k=1:2
    dim=sizes{k}; context.plot_options.figure_size=dim;
    rxpath=fullfile(output_dir,sprintf('RX_%dx%d.png',dim));
    details=msiq.plotting.rx_dashboard(rxpath,raw,validation,context,result);
    assert(details.panel_count==11 && isempty(details.layout.issues));
    check_image(rxpath,dim);
    report.rx(k)=details;
    fig=figure('Visible','off','Color','w','Position',[10 10 dim], ...
        'DefaultAxesFontName','Microsoft YaHei UI','DefaultTextFontName','Microsoft YaHei UI', ...
        'DefaultAxesFontSize',9,'DefaultTextFontSize',9);
    fig_guard=onCleanup(@() close(fig));
    positions=[.055 .58 .61 .34;.73 .60 .22 .30;.065 .315 .9 .20;.065 .065 .9 .18];
    ax=gobjects(4,1);
    for n=1:4, ax(n)=axes('Parent',fig,'Position',positions(n,:)); end
    tx=msiq.plotting.tx_dashboard('',plan,struct('target_axes',ax));
    assert(tx.panel_count==4);
    sgtitle(fig,'发射处理总览（合成示例）','FontName','Microsoft YaHei UI');
    set(fig,'PaperUnits','inches','PaperPosition',[0 0 dim/96],'PaperSize',dim/96);
    txpath=fullfile(output_dir,sprintf('TX_%dx%d.png',dim));
    print(fig,txpath,'-dpng','-r96'); check_image(txpath,dim);
    clear fig_guard;
end
audit=msiq.instruments.get_audit();
assert(audit.connections==0 && audit.writes==0 && audit.queries==0);
assert(getappdata(0,'TemplateHardwareAttempts')==0);
report.instrument_audit=audit;
report.hardware_attempts=getappdata(0,'TemplateHardwareAttempts');
% Store compact plotting inputs, not a multi-frame waveform archive.
save(fullfile(output_dir,'data','demo_inputs.mat'),'raw','validation','context','result','-v7.3');
save(fullfile(output_dir,'data','validation.mat'),'report');
fprintf('TEMPLATE_DEMO_PASS %s\n',output_dir);
end

function check_image(p,dim)
info=imfinfo(p); assert(isequal([info.Width info.Height],dim));
pixels=imread(p); assert(std(double(pixels(:)))>10);
end
