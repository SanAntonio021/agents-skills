function note=validate_rx_real_if_backend()
%VALIDATE_RX_REAL_IF_BACKEND Full single-channel saves and immutable reanalysis.
folder=msiq.validation_artifacts('directory');
msiq.instruments.io_audit('reset','');
cfg=msiq.build_config('v2_traditional_wz');
cfg.waveform.ldpc_blocks_per_frame=1;
plan=msiq.traditional_tx('preview_plan',[],struct('cfg_override',cfg, ...
    'symbol_rate_hz',2e9,'rate_authority','symbol_rate','rdiv','DIV4', ...
    'memory_mode','EXT','frame_repetitions',1));
cfg=plan.cfg;
bundle=struct('route',plan.route,'desired',plan.desired,'tx_ref',plan.tx_ref, ...
    'reference_payload_policy','metrics_only','execution',struct('status','applied','simulated',true), ...
    'dsp_config',struct('waveform',cfg.waveform,'receiver',cfg.receiver));
bundle_path=fullfile(folder,'reference.mat'); save(bundle_path,'bundle');
base=complex(plan.waveforms.master_dac_data(:,1),plan.waveforms.master_dac_data(:,2));
base=repmat(base,3,1); Fs=plan.waveforms.master_sample_rate_hz;
t=(0:numel(base)-1)'/Fs;
m=msiq.rx_measurement_context('tx_if',1);
associated=msiq.rx_reference_band(folder,{'C2'},bundle_path,false,m);
assert(strcmp(associated.path,bundle_path) && associated.center_hz==m.center_freq_hz);
legacy=msiq.rx_reference_band(folder,{'C2'},bundle_path,false); assert(isempty(legacy.path));
x=real(base.*exp(1i*2*pi*m.center_freq_hz*t));
raw=struct('mock',true,'channels',struct('channel','C2','samples',x, ...
    'time_axis_s',t,'sample_rate_hz',Fs));
opts=struct('cfg_override',cfg,'results_root',folder,'tx_reference_bundle',bundle_path, ...
    'measurement_context',m,'enable_ldpc',false);
saved=msiq.traditional_rx('save_capture',raw,opts);
assert(saved.demod_ready,saved.reason);
full=load(saved.raw_path,'raw'); assert(isequaln(full.raw,raw));
assert(numel(saved.display_raw.channels)==1 && saved.display_raw.real_if_analysis.valid);
meta=jsondecode(fileread(saved.metadata_path)); assert(isequaln(meta.measurement_context,m));
original={saved.raw_path,saved.metadata_path,saved.reference_bundle_path};
hashes=cellfun(@compute_file_sha256,original,'UniformOutput',false);
opts.cfg_override.project_root=folder;
a=msiq.traditional_rx('demod_capture',saved.run_dir,opts);
assert(strcmp(a.status,'decoded'),a.status);
metrics=msiq.rx_pre_fec_metrics(a); assert(metrics.valid,metrics.reason);
assert(a.pairs(1).decoded.sync_ok && metrics.pre_ber==0);
opts.enable_ldpc=true;
b=msiq.traditional_rx('demod_capture',saved.run_dir,opts);
second=msiq.rx_pre_fec_metrics(b); assert(second.valid,second.reason);
assert(metrics.pre_bit_count==second.pre_bit_count && metrics.pre_error_count==second.pre_error_count);
assert(~strcmp(a.run_dir,b.run_dir) && ~strcmp(a.run_dir,saved.run_dir));
% The same noise-free transmitted frame through both frontends has the same population.
iqraw=raw; iqraw.channels(1).channel='C3'; iqraw.channels(1).samples=real(base);
iqraw.channels(2)=iqraw.channels(1); iqraw.channels(2).channel='C4'; iqraw.channels(2).samples=imag(base);
iqopts=opts; iqopts.enable_ldpc=false; iqopts.measurement_context=msiq.rx_measurement_context('awg_direct',1);
iqsaved=msiq.traditional_rx('save_capture',iqraw,iqopts);
iqdecoded=msiq.traditional_rx('demod_capture',iqsaved.run_dir,iqopts);
iqmetrics=msiq.rx_pre_fec_metrics(iqdecoded);
assert(iqmetrics.valid && iqmetrics.pre_error_count==0 && iqmetrics.pre_bit_count==metrics.pre_bit_count);
thzopts=opts; thzopts.enable_ldpc=false; thzopts.measurement_context=msiq.rx_measurement_context('thz_if',1);
thzsaved=msiq.traditional_rx('save_capture',raw,thzopts);
thzdecoded=msiq.traditional_rx('demod_capture',thzsaved.run_dir,thzopts);
thzmetrics=msiq.rx_pre_fec_metrics(thzdecoded);
assert(thzmetrics.valid && thzmetrics.pre_error_count==metrics.pre_error_count && ...
    thzmetrics.pre_bit_count==metrics.pre_bit_count && abs(thzmetrics.mer_db-metrics.mer_db)<1e-8);
limited=opts; limited.scope_status=struct('channels',struct('channel','C2', ...
    'analog_bandwidth_hz',5e9));
limited_save=msiq.traditional_rx('save_capture',raw,limited);
assert(~limited_save.demod_ready && contains(limited_save.reason,'AnalogBandwidth'));
assert(isfile(limited_save.raw_path));

assert(isequal(hashes,cellfun(@compute_file_sha256,original,'UniformOutput',false)));
wrong=opts; wrong.measurement_context=msiq.rx_measurement_context('thz_if',1);
expect(@()msiq.traditional_rx('demod_capture',saved.run_dir,wrong),'msiq:traditionalRx:MeasurementMismatch');
missing=rmfield(opts,'tx_reference_bundle');
unassociated=msiq.traditional_rx('save_capture',raw,missing);
assert(~unassociated.demod_ready && isfile(unassociated.raw_path));
assert(~unassociated.display_raw.real_if_analysis.valid);
% An invalid acquisition still persists in full, with an explicit reason.
bad=raw; bad.channels.samples(8)=NaN;
invalid=msiq.traditional_rx('save_capture',bad,opts);
assert(~invalid.demod_ready && isfile(invalid.raw_path));
short=raw; short.channels.samples=x(1:30); short.channels.time_axis_s=t(1:30);
invalid=msiq.traditional_rx('save_capture',short,opts);
assert(~invalid.demod_ready && contains(invalid.reason,'Window'));
% Single IF cannot enter physical board balancing, even with a complete board.
p=msiq.if_workbench_config(struct('mode','mock')); opts.capture_then_demod=true;
p.scope.fresh=struct('verified',true,'timeout_s',1,'poll_s',.01,'reset_command','RESET', ...
    'start_command','START','completion_query','DONE?','pending_response','0','complete_response','1');
expect(@()msiq.RxDailyTask(1,opts,p,{'C2'},1,true,struct()),'RX_Workbench:BalancePosition');
task=msiq.RxDailyTask(2,opts,p,{'C2'},1,false,struct());
opts.measurement_context=msiq.rx_measurement_context('thz_if',2);
request=task.next(); assert(strcmp(request.options.measurement_context.position,'tx_if'));
audit=msiq.instruments.get_audit();
assert(audit.connections==0 && audit.queries==0 && audit.writes==0 && audit.captures==0);
note='单路中频全量保存、实际通道与参考分离、严格解调及 LDPC 前统计一致、缺参考/坏数据、不可变历史和任务冻结，零仪器 I/O。';
end
function expect(action,id)
try, action(); catch e, assert(strcmp(e.identifier,id),e.message); return; end
error('msiq:validation:ExpectedFailure','Expected %s',id);
end
