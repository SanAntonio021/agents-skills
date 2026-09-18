function note=validate_rx_scope_restore_worker(folder)
%VALIDATE_RX_SCOPE_RESTORE_WORKER Exercise the actual process-owned mock path.
if nargin<1,folder=msiq.validation_artifacts('directory');end
if ~isfolder(folder),mkdir(folder);end
[~,location]=fileattrib(folder);folder=location.Name;
opts=struct('log_path',fullfile(folder,'restore_worker.log'),'failure_path',fullfile(folder,'failure.flag'),'capture_delay_s',0,'record_count',1024);
cfg=msiq.build_config(msiq.rx_mock_config());
w=msiq.RxScopeWorker(cfg.instrument.scope,'msiq.instruments.mock_rx_scope_io',opts);
guard=onCleanup(@()finish(w));
w.submit(struct('action','connect'));r=await(w);assert(r.ok,r.error);
q=struct('action','scope_snapshot','channels',{{'C1','C2'}},'source_epoch',3,'measurement_revision',7);
w.submit(q);r=await(w);assert(r.ok,r.error);target=r.snapshot;
assert(r.source_epoch==3&&r.measurement_revision==7);
w.submit(struct('action','setting','command','C1:VDIV','value',.04));r=await(w);assert(r.ok,r.error);
q.action='restore_settings';q.target=target;
w.submit(q);r=await(w);assert(r.ok,r.error);assert(r.report.ok&&r.source_epoch==3&&r.measurement_revision==7);
assert(r.status.channels(1).vertical_scale_v_per_div==.015);
prior=count(fileread(opts.log_path),'WRITE ');
w.submit(q);r=await(w);assert(r.ok&&isempty(r.report.applied));
assert(count(fileread(opts.log_path),'WRITE ')==prior);
w.submit(struct('action','setting','command','C1:VDIV','value',.04));r=await(w);assert(r.ok,r.error);
fid=fopen(opts.failure_path,'w');fprintf(fid,'C1:VDIV 0.');fclose(fid);
w.submit(q);r=await(w);assert(~r.ok&&~r.report.ok&&strcmp(r.error_id,'mock:Timeout'));
assert(ismember('TRMD STOP',r.report.applied)&&~ismember('TRMD',r.report.applied));
delete(opts.failure_path);
assert(contains(fileread(opts.log_path),'CLOSE'),'Transport failure must release the unusable session');
w.submit(q);r=await(w);assert(~r.ok&&strcmp(r.error_id,'RX_Workbench:Disconnected'));
% Only an explicit reconnect may establish another session.
w.submit(struct('action','connect'));r=await(w);assert(r.ok,r.error);
w.submit(q);r=await(w);assert(r.ok,r.error);
w.close();t=tic;while ~w.process.HasExited&&toc(t)<40,pause(.05);end
assert(w.process.HasExited);assert(contains(fileread(opts.log_path),'CLOSE'));
note='PASS: mock process snapshot, ordered restore, zero-write no-op, partial failure, epoch/revision and session release';
end
function r=await(w)
t=tic;while true,[ready,r]=w.poll();if ready,return;end;assert(toc(t)<150);pause(.05);end
end
function finish(w)
w.close();t=tic;while ~w.process.HasExited&&toc(t)<40,pause(.05);end
assert(w.process.HasExited);delete(w);
end
