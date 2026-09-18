function report = Template_Demo(mode,output_dir)
%TEMPLATE_DEMO Standalone long-frame IQ/real-IF save and demodulation demo.
% Template_Demo() / Template_Demo('iq'|'real_if',output_dir).
% The original Template_Demo(output_dir) form remains supported.
guard=Template_NoHardware(); %#ok<NASGU>
root=fileparts(mfilename('fullpath'));
if nargin<1 || isempty(mode), mode='iq'; end
if ~ismember(char(string(mode)),{'iq','real_if'})
    assert(nargin==1,'template:DemoArguments','Unknown signal mode.');
    output_dir=char(string(mode)); mode='iq';
end
if ~exist('output_dir','var') || isempty(output_dir)
    output_dir=fullfile(root,'analysis',['template_' mode '_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
end
assert(~isfolder(output_dir),'Choose a new output directory.');
mkdir(output_dir); mkdir(fullfile(output_dir,'data'));
cfg=msiq.build_config('v2_traditional_wz');
cfg.fec.frame_type='normal'; cfg.fec.rate_numerator=9; cfg.fec.rate_denominator=10;
cfg.waveform.ldpc_blocks_per_frame=1;
cfg.instrument.awg.mock=true; cfg.instrument.scope.mock=true;
cfg.instrument.signal_generator.mock=true; cfg.safety.hardware_enabled=false;
msiq.instruments.reset_audit();
plan=TX_Workbench('preview_plan',[],struct('cfg_override',cfg, ...
    'symbol_rate_hz',2e9,'rate_authority','symbol_rate', ...
    'route','pair_b_ch3_ch4','rdiv','DIV4','memory_mode','EXT', ...
    'frame_repetitions',1,'seed',26072701));
assert(plan.memory_capacity.ok); cfg=plan.cfg;
bundle=struct('route',plan.route,'desired',plan.desired,'tx_ref',plan.tx_ref, ...
    'reference_payload_policy','metrics_only','source_mode','simulation', ...
    'execution',struct('status','applied','simulated',true,'hardware_executed',false), ...
    'dsp_config',struct('waveform',cfg.waveform,'receiver',cfg.receiver));
reference=fullfile(output_dir,'data','tx_reference_bundle.mat'); save(reference,'bundle');
% Three intact periods permit synchronization and FIR edge removal without
% pretending the raw acquisition must itself have an exact frame boundary.
columns=plan.route.waveform_columns;
assert(numel(columns)==2,'template:Route','The demo requires one logical IQ pair.');
base=repmat(complex(plan.waveforms.master_dac_data(:,columns(1)),plan.waveforms.master_dac_data(:,columns(2))),3,1);
Fs=plan.waveforms.master_sample_rate_hz; t=(0:numel(base)-1)'/Fs;
if strcmp(mode,'real_if')
    measurement=msiq.rx_measurement_context('tx_if',1);
    samples=real(base.*exp(1i*2*pi*measurement.center_freq_hz*t)); channels={'C2'};
else
    measurement=msiq.rx_measurement_context('awg_direct',1);
    samples=[real(base) imag(base)]; channels={'C3','C4'};
end
raw=struct('mock',true);
for k=1:numel(channels)
    raw.channels(k)=struct('channel',channels{k},'samples',samples(:,k), ...
        'time_axis_s',t,'sample_rate_hz',Fs);
end
options=struct('cfg_override',cfg,'results_root',output_dir, ...
    'tx_reference_bundle',reference,'measurement_context',measurement,'enable_ldpc',false);
capture=msiq.traditional_rx('save_capture',raw,options);
assert(capture.demod_ready,'template:Capture','%s',char(capture.reason));
stored=load(capture.raw_path,'raw'); assert(isequaln(stored.raw,raw),'Full raw capture was changed.');
original_hash=compute_file_sha256(capture.raw_path);
options.cfg_override.project_root=output_dir;
result=msiq.traditional_rx('demod_capture',capture.run_dir,options);
metrics=msiq.rx_pre_fec_metrics(result);
assert(metrics.valid && metrics.pre_error_count==0,'template:Metrics','valid=%d errors=%g bits=%g; %s',metrics.valid,metrics.pre_error_count,metrics.pre_bit_count,char(metrics.reason));
options.enable_ldpc=true;
with_ldpc=msiq.traditional_rx('demod_capture',capture.run_dir,options);
ldpc_metrics=msiq.rx_pre_fec_metrics(with_ldpc);
assert(ldpc_metrics.valid && metrics.pre_bit_count==ldpc_metrics.pre_bit_count && ...
    metrics.pre_error_count==ldpc_metrics.pre_error_count);
assert(strcmp(original_hash,compute_file_sha256(capture.raw_path)),'Reanalysis modified raw capture.');
assert(~strcmp(result.run_dir,with_ldpc.run_dir),'Reanalysis must create a new result.');
report=struct('execution_mode','simulation','signal_mode',mode,'decoded_pass',true, ...
    'output_dir',output_dir,'capture',capture,'metrics',metrics,'ldpc_metrics',ldpc_metrics, ...
    'analysis_dir',result.run_dir,'ldpc_analysis_dir',with_ldpc.run_dir);
context=struct('cfg',cfg,'tx_ref',plan.tx_ref,'scope_status',struct(),'measurement_context',measurement);
validation=struct('ok',true,'reason','','summary',struct());
for dim={[1280 720],[1920 1080]}
    size_px=dim{1}; context.plot_options.figure_size=size_px;
    rxpath=fullfile(output_dir,sprintf('RX_%dx%d.png',size_px));
    msiq.plotting.rx_dashboard(rxpath,raw,validation,context,result); check_image(rxpath,size_px);
    fig=figure('Visible','off','Color','w','Position',[10 10 size_px]);
    cleanup=onCleanup(@()close(fig));
    positions=[.055 .58 .61 .34;.73 .60 .22 .30;.065 .315 .9 .20;.065 .065 .9 .18];
    ax=gobjects(4,1); for k=1:4, ax(k)=axes('Parent',fig,'Position',positions(k,:)); end
    tx=msiq.plotting.tx_dashboard('',plan,struct('target_axes',ax)); assert(tx.panel_count==4);
    set(fig,'PaperUnits','inches','PaperPosition',[0 0 size_px/96],'PaperSize',size_px/96);
    txpath=fullfile(output_dir,sprintf('TX_%dx%d.png',size_px)); print(fig,txpath,'-dpng','-r96');
    check_image(txpath,size_px); clear cleanup;
end
audit=msiq.instruments.get_audit();
assert(audit.connections==0 && audit.writes==0 && audit.queries==0);
assert(getappdata(0,'TemplateHardwareAttempts')==0);
report.instrument_audit=audit; report.hardware_attempts=getappdata(0,'TemplateHardwareAttempts');
save(fullfile(output_dir,'data','validation.mat'),'report');
fprintf('TEMPLATE_DEMO_PASS %s %s\n',mode,output_dir);
end
function check_image(p,dim)
info=imfinfo(p); assert(isequal([info.Width info.Height],dim));
pixels=imread(p); assert(std(double(pixels(:)))>10);
end