function report=validate_if_replay()
%VALIDATE_IF_REPLAY Saved fixture replay, with source immutability checks.
cfg=msiq.build_config('v2_traditional_wz');
run=msiq.create_output_run(cfg,'checks','IF_replay_fixture');
source_dir=run.OutputDir;
p=msiq.if_workbench_config();
raw=struct('channels',[],'fresh_confirmed',true,'mock',true);
raw_path=msiq.artifact_path(source_dir,'capture_00001.mat','write');
save(raw_path,'raw');
obs=struct('attempt',1,'memory_mode','EXT','raw_path',raw_path, ...
    'scale_vdiv',[.1 .1],'metrics',struct('valid',true,'pre_ber',0));
out=struct('run_dir',source_dir,'status','completed','profile',p,'observations',{{obs}});
checkpoint=msiq.artifact_path(source_dir,'if_checkpoint.mat','write');
save(checkpoint,'out');
before=hash_file(checkpoint); raw_before=hash_file(raw_path);
listing=dir(fullfile(source_dir,'data'));
read=msiq.if_workbench_replay(struct('run_dir',source_dir));
assert(read.replay&&strcmp(read.status,'offline_replay'));
assert(read.observations{1}.metrics.pre_ber==0);
assert(isequal({listing.name},{dir(fullfile(source_dir,'data')).name}));
recomputed=msiq.if_workbench_replay(struct('run_dir',source_dir,'redecode',true));
assert(~strcmp(recomputed.run_dir,source_dir));
assert(~recomputed.observations{1}.metrics.valid);
assert(isnan(recomputed.observations{1}.metrics.pre_ber));
assert(strcmp(before,hash_file(checkpoint))&&strcmp(raw_before,hash_file(raw_path)));
assert(isfile(msiq.artifact_path(recomputed.run_dir,'if_checkpoint.mat','read')));
shared_details=check_shared_reference(cfg);
report=struct('ok',true,'details',struct('read_only_default',true, ...
    'source_unchanged',true,'mock_no_fake_ber',true, ...
    'fixture_run',source_dir,'analysis_run',recomputed.run_dir, ...
    'shared_reference',shared_details));
end
function details=check_shared_reference(cfg)
% Compact TX references must load through the same path as portable bundles.
source=msiq.create_output_run(cfg,'checks','IF_shared_reference');
destination=msiq.create_output_run(cfg,'checks','IF_portable_reference');
second=msiq.create_output_run(cfg,'checks','IF_second_reference');
p=msiq.if_workbench_config(struct('stage','tx_if'));
tx_ref=struct('fec_config',msiq.fec.specification(cfg),'fixture_identity','shared-reference');
source_path=msiq.artifact_path(source.OutputDir,'tx_reference_bundle.mat','write');
owner=fileparts(source_path);
shared=msiq.shared_tx_data('save',owner,owner,struct('tx_ref',tx_ref));
bundle=struct('tx_ref',tx_ref,'dsp_config',struct('waveform',cfg.waveform, ...
    'receiver',cfg.receiver),'shared_data',shared);
msiq.save_reference_bundle(source_path,bundle,source_path);
compact=load(source_path,'bundle');
assert(~isfield(compact.bundle,'tx_ref')&&isfield(compact.bundle,'shared_data'));
before=hash_file(source_path);
shared_path=fullfile(owner,shared.file); shared_before=hash_file(shared_path);

% Exercise the actual IF persistence method, with no preflight or instruments.
worker=msiq.IfRun(p,struct());
resolved=msiq.load_reference_bundle(source_path); worker.bundle=resolved.bundle;
portable_path=msiq.artifact_path(destination.OutputDir,'tx_reference_bundle.mat','write');
worker.saveReference(portable_path,source_path);
portable=load(portable_path,'bundle');
assert(isequaln(portable.bundle.tx_ref,tx_ref)&&~isfield(portable.bundle,'shared_data'));
second_path=msiq.artifact_path(second.OutputDir,'tx_reference_bundle.mat','write');
worker.saveReference(second_path,portable_path);
carried=load(second_path,'bundle');
assert(isequaln(carried.bundle,portable.bundle));

t=(0:1023)'/p.scope.sample_rate_hz;
record=struct('channel','C2','samples',.01*cos(2*pi*6.2e9*t), ...
    'time_axis_s',t,'sample_rate_hz',p.scope.sample_rate_hz,'descriptor',struct());
raw=struct('channels',record,'fresh_confirmed',true,'mock',true);
raw_path=msiq.artifact_path(destination.OutputDir,'capture_00001.mat','write');
save(raw_path,'raw');
obs=struct('attempt',1,'memory_mode','EXT','raw_path',raw_path,'scale_vdiv',.1);
out=struct('run_dir',destination.OutputDir,'status','completed', ...
    'profile',p,'observations',{{obs}});
checkpoint=msiq.artifact_path(destination.OutputDir,'if_checkpoint.mat','write');
save(checkpoint,'out'); checkpoint_before=hash_file(checkpoint);
paths={source_path,portable_path,second_path};
for k=1:numel(paths)
    replay=msiq.if_workbench_replay(struct('run_dir',destination.OutputDir, ...
        'redecode',true,'reference_bundle',paths{k}));
    assert(isempty(replay.replay_errors));
    assert(strcmp(replay.observations{1}.replay_status,'spectrum_only'));
    assert(~replay.observations{1}.metrics.valid);
end
assert(strcmp(before,hash_file(source_path))&&strcmp(shared_before,hash_file(shared_path)));
assert(strcmp(checkpoint_before,hash_file(checkpoint)));
details=struct('compact_replay',true,'cross_run_portable',true, ...
    'second_run_replay',true,'sources_unchanged',true);
end
function h=hash_file(path)
fid=fopen(path,'rb'); cleaner=onCleanup(@()fclose(fid));
h=msiq.sha256_bytes(fread(fid,Inf,'*uint8'));
end
