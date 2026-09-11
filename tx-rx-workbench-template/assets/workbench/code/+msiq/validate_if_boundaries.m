function note=validate_if_boundaries()
%VALIDATE_IF_BOUNDARIES Offline fixed-setting, recovery and board boundaries.
msiq.instruments.io_audit('reset','');
p=msiq.if_workbench_config(); p.mock.gain_db=[0 0];
p.scan=struct('pre_start_db',20,'pre_stop_db',20,'pre_step_db',-1, ...
    'post_start_db',20,'post_stop_db',17,'post_step_db',-1);
swapped=p; swapped.mock.gain_db=[1 0];
swapped.board.mapping=struct('i_channel','C4','q_channel','C3');
balanced=msiq.if_workbench('balance',struct('profile',swapped));
assert(strcmp(balanced.status,'completed')&&balanced.final_setting.i_db>p.initial.i_db&& ...
    balanced.final_setting.q_db==p.initial.q_db);
% A fixed-board adjacent-range diagnostic is separate from formal counts.
direct=p; direct.stage='direct'; runner=msiq.IfRun(direct,struct());
r=runner.execute('manual_capture'); assert(strcmp(r.status,'completed'));
oldSetting=runner.setting; oldScale=runner.scale; n=numel(runner.out.observations);
runner.rangeDiagnostic(runner.out.observations{end},0,0);
assert(isequal(runner.setting,oldSetting)&&isequal(runner.scale,oldScale));
assert(numel(runner.out.observations)==n+2);
assert(all(cellfun(@(o)strcmp(o.role,'range_diagnostic'),runner.out.observations(end-1:end))));
runner.p.mock.fail_capture=runner.captureCount+2;
mustFail(@()runner.rangeDiagnostic(runner.out.observations{end},0,0),'msiq:if:InjectedCapture');
assert(isequal(runner.setting,oldSetting)&&isequal(runner.scale,oldScale));
% An interrupted point is not completed; resumption retains parent attempts.
broken=p; broken.mock.fail_capture=10;
old=msiq.if_workbench('scan',struct('profile',broken));
assert(strcmp(old.status,'paused')&&size(old.completed_points,1)==2);
resumed=msiq.if_workbench('resume',struct('profile',p,'run_dir',old.run_dir));
if ~strcmp(resumed.status,'completed'), disp(resumed.errors); end
assert(strcmp(resumed.status,'completed')&&size(resumed.completed_points,1)==4);
assert(numel(resumed.prior_observations)==numel(old.observations));
assert(sum(cellfun(@(o)strcmp(o.role,'recovery_baseline'),resumed.observations))==3);
assert(sum(cellfun(@(o)strcmp(o.role,'formal'),resumed.observations))==2);
assert(isfile(old.observations{end}.raw_path));
% Failure and cancellation close mock board and invalidate its cached state.
for cause={'write','cancel'}
    f=p;
    if strcmp(cause{1},'write'), f.board.fail_on_write=1;
    else, f.mock.cancel_capture=7; end
    runner=msiq.IfRun(f,struct()); out=runner.execute('scan');
    assert(ismember(out.status,{'paused','cancelled'}));
    assert(~isempty(runner.board)&&~runner.board.IsOpen&&~runner.board.StateKnown);
    assert(out.shutdown.awg_off_verified&&~out.shutdown.process_kill_protection);
end
audit=msiq.instruments.get_audit();
assert(audit.connections==0&&audit.queries==0&&audit.writes==0&&audit.captures==0);
note='IF fixed-setting range diagnostics, interrupted-point recovery and board cleanup passed.';
end
function mustFail(fn,id)
try
    fn();
catch ex
    assert(strcmp(ex.identifier,id),'Unexpected error: %s',ex.identifier); return;
end
error('msiq:if:Validation','Expected failure %s.',id);
end
