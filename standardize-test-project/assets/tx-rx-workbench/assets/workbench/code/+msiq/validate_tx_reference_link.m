function note=validate_tx_reference_link()
folder=msiq.validation_artifacts('directory');
msiq.instruments.reset_audit();
cfg=msiq.build_config('v2_traditional_wz'); cfg.project_root=folder;
cfg.waveform.ldpc_blocks_per_frame=1; cfg.instrument.awg.mock=true; cfg.instrument.awg.resource='MOCK_REFERENCE_AWG'; cfg.instrument.awg.mock_idn='MOCK,M8195A,0,2.0'; cfg.instrument.awg.idn_contains='M8195A';
cfg.reference_link_store_path=fullfile(folder,'links');
opts=struct('cfg_override',cfg,'symbol_rate_hz',2e9,'rate_authority','symbol_rate', ...
    'rdiv','DIV4','memory_mode','EXT','frame_repetitions',1,'route','pair_b_ch3_ch4');
lookup=struct('source','simulation','store_path',cfg.reference_link_store_path, ...
    'device',cfg.instrument.awg.resource);
plan=msiq.traditional_tx('awg_plan',[],opts);
r=msiq.tx_reference_link('read',folder,lookup); assert(~r.valid);
apply=struct('plan',plan,'confirmation_phrase',plan.required_confirmation,'enable_output',false);
msiq.traditional_tx('awg_apply',[],apply);
r=msiq.tx_reference_link('read',folder,lookup); assert(~r.valid);
msiq.traditional_tx('awg_reuse',plan.run_dir,opts);
r=msiq.tx_reference_link('read',folder,lookup); assert(r.valid,r.reason);
m=msiq.rx_measurement_context(struct('position','awg_direct'));
info=msiq.rx_reference_band(folder,{'C1','C2'},'',true,m,lookup); assert(strcmp(info.path,r.path),jsonencode(info));
real=lookup; real.source='real'; assert(~msiq.tx_reference_link('read',folder,real).valid);
% Invalid confirmation is read-only and must not invalidate a published reference.
try, bad=apply; bad.confirmation_phrase='wrong'; msiq.traditional_tx('awg_apply',[],bad); catch, end
assert(msiq.tx_reference_link('read',folder,lookup).valid);
% Explicit reference remains usable after stopping; automatic association does not.
msiq.traditional_tx('awg_stop',[],opts); assert(~msiq.tx_reference_link('read',folder,lookup).valid);
info=msiq.rx_reference_band(folder,{'C1','C2'},r.path,false,m,lookup); assert(~isempty(info.path));
% Re-enable publishes a fresh successful receipt, also for already-applied manifests.
msiq.traditional_tx('awg_reuse',plan.run_dir,opts); assert(msiq.tx_reference_link('read',folder,lookup).valid);
msiq.traditional_tx('awg_stop',[],opts);
plan2=msiq.traditional_tx('awg_plan',[],opts); plan2.cfg.instrument.awg.fail_stage='download';
pub=lookup; pub.reference_path=r.path; pub.execution_id='previous'; msiq.tx_reference_link('publish',folder,pub);
failed=false;
try, msiq.traditional_tx('awg_apply',[],struct('plan',plan2,'confirmation_phrase',plan2.required_confirmation)); catch exception, failed=strcmp(exception.identifier,'msiq:traditionalTx:MockDownloadFailure'); end
assert(failed);
assert(~msiq.tx_reference_link('read',folder,lookup).valid);
% File-only publication validation, hash tamper and device ambiguity.
pub=lookup; pub.reference_path=r.path; pub.execution_id='test'; msiq.tx_reference_link('publish',folder,pub);
pub.device='another_awg'; msiq.tx_reference_link('publish',folder,pub);
all=rmfield(lookup,'device'); assert(~msiq.tx_reference_link('read',folder,all).valid);
msiq.tx_reference_link('read_metadata',folder,lookup);
fid=fopen(r.path,'a'); fwrite(fid,uint8(1)); fclose(fid);
assert(~msiq.tx_reference_link('read',folder,lookup).valid);
audit=msiq.instruments.get_audit(); assert(audit.scope_connections==0 && audit.source_connections==0);
note='成功发送关联、暂存不发布、停用失效、重启发布、读取拒绝不失效、跨通道、来源隔离、哈希与歧义验证；仅 mock AWG。';
end
