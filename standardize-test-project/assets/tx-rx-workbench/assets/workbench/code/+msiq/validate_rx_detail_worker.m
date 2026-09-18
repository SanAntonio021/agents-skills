function note=validate_rx_detail_worker()
% Real process boundary with a mock scope; rejection precedes board creation.
folder=msiq.validation_artifacts('directory');
cfg=msiq.build_config(msiq.rx_mock_config());
worker=msiq.RxScopeWorker(cfg.instrument.scope,'msiq.rx_daily_mock_io', ...
    struct('log_path',fullfile(folder,'audit.log'),'failure_path',fullfile(folder,'failure.txt'),'record_count',32000,'capture_delay_s',0));
guard=onCleanup(@()finish(worker)); %#ok<NASGU>
request=struct('action','board_connect','rx_position_guard',true, ...
    'measurement_revision',3,'measurement_context',msiq.rx_measurement_context('awg_direct'), ...
    'payload',struct());
worker.submit(request); r=await(worker);
assert(~r.ok && strcmp(r.error_id,'RX_Workbench:BoardPosition'));
request.measurement_context=msiq.rx_measurement_context('rx_if',1); request.measurement_revision=2;
worker.submit(request); r=await(worker);
assert(~r.ok && strcmp(r.error_id,'RX_Workbench:StaleMeasurement'));
% The rejected requests did not create a board; scope lifecycle is independent.
worker.submit(struct('action','connect')); r=await(worker); assert(r.ok,r.error);
worker.submit(struct('action','release')); r=await(worker); assert(r.ok,r.error);
save(fullfile(folder,'worker_guard_evidence.mat'),'request','r');
note='PASS: real worker rejects inapplicable and stale board request before construction; scope release remains available; mock only';
end
function r=await(worker)
t=tic;
while true
    [ready,r]=worker.poll(); if ready, return; end
    assert(toc(t)<90,'Worker timeout'); pause(.05);
end
end
function finish(worker)
worker.close(); t=tic;
while ~worker.process.HasExited && toc(t)<30, pause(.05); end
assert(worker.process.HasExited,'Worker failed to close'); delete(worker);
end
