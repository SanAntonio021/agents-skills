function note=validate_rx_context_records()
%VALIDATE_RX_CONTEXT_RECORDS Wiring-independent single-stream records.
folder=msiq.validation_artifacts('directory');
msiq.instruments.io_audit('reset','');
legacy=struct('schema_version',1,'position','awg_direct','subband',6);
m=msiq.rx_measurement_context(legacy);
assert(m.schema_version==2 && ~isfield(m,'subband') && m.center_freq_hz==0);
assert(~isfield(msiq.rx_measurement_context(),'subband'));
cfg=msiq.build_config('v2_traditional_wz'); cfg.waveform.ldpc_blocks_per_frame=1;
plan=msiq.traditional_tx('preview_plan',[],struct('cfg_override',cfg, ...
    'symbol_rate_hz',2e9,'rate_authority','symbol_rate','rdiv','DIV4', ...
    'memory_mode','EXT','frame_repetitions',1,'route','pair_b_ch3_ch4'));
cfg=plan.cfg;
bundle=struct('route',plan.route,'desired',plan.desired,'tx_ref',plan.tx_ref, ...
    'reference_payload_policy','metrics_only','execution',struct('status','applied'), ...
    'dsp_config',struct('waveform',cfg.waveform,'receiver',cfg.receiver));
bundle.route.scope_channels={'C3','C4'};
path=fullfile(folder,'reference.mat'); save(path,'bundle'); original=msiq.file_sha256(path);
assert(msiq.rx_reference_channels_compatible(bundle,{'C1','C2'},m,true));
assert(~msiq.rx_reference_channels_compatible(bundle,{'C1','C2'},m,false));
assert(~msiq.rx_reference_channels_compatible(bundle,{'C1','C2'},struct(),true));
assert(~msiq.rx_reference_channels_compatible(bundle,{'C1','C1'},m,true));
dual=bundle; dual.dsp_config.waveform.architecture='dual_independent_iq';
assert(~msiq.rx_reference_channels_compatible(dual,{'C1','C2'},m,true));
info=msiq.rx_reference_band(folder,{'C1','C2'},path,false,m); assert(strcmp(info.path,path));
base=repmat(plan.waveforms.master_dac_data(:,3:4),3,1); fs=plan.waveforms.master_sample_rate_hz;
t=(0:size(base,1)-1)'/fs;
record=struct('channel','C1','samples',base(:,1),'time_axis_s',t,'sample_rate_hz',fs);
raw=struct('mock',true,'channels',record); raw.channels(2)=record;
raw.channels(2).channel='C2'; raw.channels(2).samples=base(:,2);
opts=struct('cfg_override',cfg,'results_root',folder,'tx_reference_bundle',path, ...
    'measurement_context',m,'enable_ldpc',false,'requested_scope_channels',{{'C1','C2'}});
saved=msiq.traditional_rx('save_capture',raw,opts); assert(saved.demod_ready,saved.reason);
meta=jsondecode(fileread(saved.metadata_path));
assert(~isfield(meta.measurement_context,'subband'));
assert(isequal(string(meta.actual_scope_channels(:)),["C1";"C2"]));
assert(isequal(string(meta.requested_scope_channels(:)),["C1";"C2"]));
assert(isequal(string(meta.reference_provenance.historical_scope_channels(:)),["C3";"C4"]));
raw_hash=msiq.file_sha256(saved.raw_path); meta_hash=msiq.file_sha256(saved.metadata_path);
opts.cfg_override.project_root=folder;
decoded=msiq.traditional_rx('demod_capture',saved.run_dir,opts);
metrics=msiq.rx_pre_fec_metrics(decoded); assert(metrics.valid && metrics.pre_error_count==0);
assert(strcmp(raw_hash,msiq.file_sha256(saved.raw_path)) && strcmp(meta_hash,msiq.file_sha256(saved.metadata_path)));
assert(strcmp(original,msiq.file_sha256(path)));
audit=msiq.instruments.get_audit(); assert(audit.connections==0 && audit.writes==0 && audit.captures==0);
note='上下文 v2 无虚构子带；显式参考允许 C3/C4→C1/C2，自动及旧调用保留匹配；全量保存、零误码解调、来源与历史不变，零仪器访问。';
end
