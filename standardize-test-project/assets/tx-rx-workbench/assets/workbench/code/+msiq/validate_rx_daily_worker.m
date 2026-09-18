function note=validate_rx_daily_worker(output_dir)
%VALIDATE_RX_DAILY_WORKER Real background process, mock I/O, full raw persistence.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
[~,location]=fileattrib(output_dir); output_dir=location.Name;
log=fullfile(output_dir,'worker_audit.log');
cfg=msiq.build_config(msiq.rx_mock_config());
p=msiq.if_workbench_config(struct('mode','mock')); p.scope.sample_rate_hz=80e9;
p.scope.channels={'C1'};
p.scope.fresh=struct('verified',true,'timeout_s',2,'poll_s',.01,'reset_command','MOCK:RESET', ...
    'start_command','MOCK:START','completion_query','MOCK:DONE?','pending_response','0','complete_response','1');
worker=msiq.RxScopeWorker(cfg.instrument.scope,'msiq.rx_daily_mock_io', ...
    struct('capture_delay_s',.4,'record_count',32000,'log_path',log,'failure_path',fullfile(output_dir,'failure.txt')));
guard=onCleanup(@()finish(worker));
worker.submit(struct('action','connect')); r=await(worker); assert(r.ok,r.error);
options=struct('cfg_override',cfg,'scope_channels',{{'C1'}},'measurement_role','formal', ...
    'run_dir',fullfile(output_dir,'capture_one'),'tx_reference_bundle','');
request=struct('action','formal_capture','channels',{{'C1'}},'task_id',71,'timeout_s',120, ...
    'fresh',p.scope.fresh,'settle_s',0,'profile',p,'options',options,'frozen_status',struct());
worker.submit(request); r=await(worker); assert(r.ok,r.error);
assert(isfile(r.capture.raw_path) && r.fresh_capture.fresh_confirmed);
saved=load(r.capture.raw_path,'raw');
assert(numel(saved.raw.channels)==1 && numel(saved.raw.channels.samples)==32000);
assert(numel(r.raw.channels.samples)<=6000 && numel(r.raw.channels.samples)<numel(saved.raw.channels.samples));
assert(contains(fileread(log),'WRITE TRMD AUTO'));
% GUI sampling checks derive from trusted front-panel readings. Explicit
% backend requirements still reject a mismatching waveform after raw save.
request.profile.scope.sample_rate_hz=1e9;
request.options.run_dir=fullfile(output_dir,'explicit_rate_rejected');
worker.submit(request); r=await(worker);
assert(~r.ok && strcmp(r.error_id,'msiq:if:SampleRate') && isfile(r.capture.raw_path));
request.options.sampling_baseline_source='front_panel';
request.options.run_dir=fullfile(output_dir,'front_panel_baseline');
worker.submit(request); r=await(worker); assert(r.ok,r.error);
meta=jsondecode(fileread(r.capture.metadata_path));
assert(strcmp(meta.sampling_baseline.source,'front_panel_readback'));
assert(meta.sampling_baseline.sample_rate_hz==r.status.sample_rate_hz);
assert(meta.sampling_baseline.window_s==10*r.status.timebase);
assert(r.fresh_capture.fresh_confirmed);
% Existing task cancellation must reject a future request before acquisition.
worker.cancel(72); request.task_id=72; request.options.run_dir=fullfile(output_dir,'cancelled');
worker.submit(request); r=await(worker); assert(~r.ok && strcmp(r.error_id,'RX_Workbench:Cancelled'));
assert(~isfolder(request.options.run_dir));
% Cancellation during a bounded read retains the completed raw and rejects replay.
request.task_id=73; request.options.run_dir=fullfile(output_dir,'cancel_during_read');
prior=count(fileread(log),'CAPTURE BEGIN'); worker.submit(request); started=tic;
while count(fileread(log),'CAPTURE BEGIN')<=prior
    assert(toc(started)<20,'Capture did not start'); pause(.01);
end
worker.cancel(73); r=await(worker);
assert(~r.ok && isfield(r,'capture') && isfile(r.capture.raw_path));
evidence=jsondecode(fileread(fullfile(r.capture.run_dir,'data','capture_validation.json')));
assert(~evidence.valid && strcmp(evidence.status,'rejected'));
worker.close(); refused=false;
try worker.submit(struct('action','connect')); catch e, refused=strcmp(e.identifier,'RX_Workbench:WorkerClosing'); end
assert(refused,'Closing worker must reject new requests');
note='PASS: real process mock fresh capture; complete raw before compact; one channel; AUTO cleanup; cancellation before/during I/O; closing rejects requests';
end
function r=await(worker)
started=tic;
while true
    [ready,r]=worker.poll(); if ready, return; end
    assert(toc(started)<150,'Worker response timeout'); pause(.05);
end
end
function finish(worker)
worker.close(); started=tic;
while ~worker.process.HasExited && toc(started)<30, pause(.05); end
assert(worker.process.HasExited,'Worker did not release session'); delete(worker);
end
