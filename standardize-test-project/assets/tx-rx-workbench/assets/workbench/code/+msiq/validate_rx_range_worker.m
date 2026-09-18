function note=validate_rx_range_worker(folder)
%VALIDATE_RX_RANGE_WORKER Computed requests against the real worker and mock I/O.
if nargin==1 && isstruct(folder), note=msiq.instruments.mock_rx_scope_io(folder); note.source_mode='simulation'; return; end
if nargin<1,folder=msiq.validation_artifacts('directory');end
if ~isfolder(folder),mkdir(folder);end
[~,location]=fileattrib(folder);folder=location.Name;
opts=struct('log_path',fullfile(folder,'range_worker.log'),'failure_path',fullfile(folder,'failure.flag'), ...
    'capture_delay_s',0,'record_count',1024);
cfg=msiq.build_config(msiq.rx_mock_config());
w=msiq.RxScopeWorker(cfg.instrument.scope,'msiq.validate_rx_range_worker',opts);
guard=onCleanup(@()finish(w)); %#ok<NASGU>
w.submit(struct('action','connect'));r=await(w);assert(r.ok,r.error);
obs=struct('action','capture','channels',{{'C1','C2'}},'range_policy',struct('range_strategy','computed'));
w.submit(obs);r=await(w);assert(r.ok&&r.range_decision.valid,r.error);
q=struct('action','formal_range','channels',{{'C1','C2'}},'values',[.0183 .0212], ...
    'range_strategy','computed','allowed_ranges',.5);
w.submit(q);r=await(w);assert(r.ok,r.error);
assert(isequal(r.range_report.actual_values,[.02 .02]));
assert(isequal(r.range_report.requested_values,q.values));
assert(numel(r.range_report.written_channels)==2&&r.status.channels(1).vertical_scale_v_per_div==.02);
q.values=[.02 .02];prior=count(fileread(opts.log_path),'WRITE ');
w.submit(q);r=await(w);assert(r.ok&&isempty(r.range_report.written_channels));
assert(count(fileread(opts.log_path),'WRITE ')==prior);
obs.range_reference_identity='paired-A';
w.submit(obs);r=await(w);assert(r.ok&&r.range_decision.valid,r.error);
q.range_reference_identity='paired-A';q.values=r.range_decision.target_vdiv;
w.submit(q);r=await(w);assert(r.ok,r.error);
% Mock rounds below the required edge margin; cache must not accept unsafe data.
w.submit(obs);r=await(w);assert(r.ok&&r.range_decision.needs_adjustment);
obs.range_policy.edge_margin_divisions=0; obs.range_policy.target_divisions=6;
w.submit(obs);r=await(w);q.values=r.range_decision.target_vdiv;
w.submit(q);r=await(w);assert(r.ok,r.error);
w.submit(obs);r=await(w);assert(r.ok&&r.range_decision.valid&&~r.range_decision.needs_adjustment);
q.values=[.04 .04];w.submit(q);r=await(w);assert(r.ok,r.error);
% Safety expansion may exceed the optimal request: accept its first safe frame.
w.submit(obs);r=await(w);assert(r.ok&&~r.range_decision.needs_adjustment);
w.submit(obs);r=await(w);assert(r.ok&&~r.range_decision.needs_adjustment);
obs.range_reference_identity='paired-B';
w.submit(obs);r=await(w);assert(r.ok&&r.range_decision.needs_adjustment);
prior=count(fileread(opts.log_path),'WRITE ');
q.values=[NaN .01];w.submit(q);r=await(w);assert(~r.ok&&strcmp(r.error_id,'RX_Workbench:RangeValue'));
assert(count(fileread(opts.log_path),'WRITE ')==prior);
q.values=[.023 .025];q.range_strategy='legacy';q.allowed_ranges=[.023 .025];
w.submit(q);r=await(w);assert(~r.ok&&strcmp(r.error_id,'RX_Workbench:RangeReadback'));
assert(isequal(r.range_report.written_channels,{'C1'}));
q.range_strategy='computed';q.values=[.029 .035];
fid=fopen(opts.failure_path,'w');fprintf(fid,'C2:VDIV 0.');fclose(fid);
w.submit(q);r=await(w);assert(~r.ok&&strcmp(r.error_id,'mock:Timeout'));
assert(isequal(r.range_report.written_channels,{'C1'})&&r.range_report.actual_values(1)==.03);
assert(contains(r.range_report.error,'mock')||~isempty(r.range_report.error));
delete(opts.failure_path);
w.submit(struct('action','connect'));r=await(w);assert(r.ok,r.error);
q.task_id=501;w.cancel(q.task_id);prior=count(fileread(opts.log_path),'WRITE ');
w.submit(q);r=await(w);assert(~r.ok&&strcmp(r.error_id,'RX_Workbench:Cancelled'));
assert(count(fileread(opts.log_path),'WRITE ')==prior);
note='PASS: computed upward/downward readback, no-op, invalid values, cache safe confirmation/reference invalidation, unchanged legacy mismatch, partial failure and cancellation';
end
function r=await(w)
t=tic;while true,[ready,r]=w.poll();if ready,return;end;assert(toc(t)<150);pause(.05);end
end
function finish(w)
w.close();t=tic;while ~w.process.HasExited&&toc(t)<40,pause(.05);end
assert(w.process.HasExited);delete(w);
end
