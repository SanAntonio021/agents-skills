function note=validate_if_workbench()
%VALIDATE_IF_WORKBENCH State-machine regression through the public entry point.
msiq.instruments.io_audit('reset','');
p=msiq.if_workbench('config');
p.scan=struct('pre_start_db',20,'pre_stop_db',19,'pre_step_db',-1, ...
    'post_start_db',20,'post_stop_db',18,'post_step_db',-1);
plan=msiq.if_workbench('plan',struct('profile',p));
assert(plan.automatic_ready&&isequal(plan.points,[20 20;20 19;20 18;19 20;19 19;19 18]));
r=run('scan',p); must_complete(r);
assert(size(r.completed_points,1)==6);
assert(count(r,'formal')==6&&count(r,'baseline')==3);
baseline=r.baseline; assert(isequal(baseline{1}.setting,baseline{3}.setting));
assert(isequal(baseline{1}.scale_vdiv,baseline{3}.scale_vdiv));
assert(baseline{1}.setting.i_db>=p.initial.i_db&&baseline{1}.setting.q_db==p.initial.q_db);
saved=load(fullfile(r.run_dir,'data','if_checkpoint.mat'),'out');
replay=msiq.if_workbench('replay',struct('run_dir',r.run_dir));
assert(numel(replay.observations)==numel(saved.out.observations));
resumed=msiq.if_workbench('resume',struct('profile',p,'run_dir',r.run_dir)); must_complete(resumed);
assert(count(resumed,'formal')==0&&count(resumed,'recovery_baseline')==3);
assert(~strcmp(resumed.run_dir,r.run_dir));
bad=p; bad.scan.post_stop_db=17; mismatch=msiq.if_workbench('resume',struct('profile',bad,'run_dir',r.run_dir));
assert(strcmp(mismatch.status,'paused'));
% Three distinct degraded points stop only this pre group; the next is visited.
d=p; d.scan.post_stop_db=14; d.mock.degrade_below_post_db=19;
deg=run('scan',d); must_complete(deg);
assert(numel(deg.stopped_groups)==2&&size(deg.completed_points,1)==10);
assert(count(deg,'formal')==22); % per group: two normal + three sets of three
for name={'fail_capture','fail_save','cancel_capture','invalid_capture'}
    f=p; f.mock.(name{1})=7;
    failed=run('scan',f);
    assert(ismember(failed.status,{'paused','cancelled'}));
    assert(failed.shutdown.awg_off_verified&&failed.shutdown.scope_auto);
    assert(size(failed.completed_points,1)<6);
    assert(isfile(fullfile(failed.run_dir,'data','if_checkpoint.mat')));
end
stale=p; stale.mock.stale_capture=true; failed=run('manual_capture',stale);
assert(strcmp(failed.status,'paused')&&isempty(failed.observations));
off=p; off.mock.fail_shutdown=true; failed=run('manual_capture',off);
assert(strcmp(failed.status,'shutdown_failed')&&~failed.shutdown.awg_off_verified&&~isempty(failed.shutdown.errors));
tx=p; tx.stage='tx_if'; one=run('manual_capture',tx); must_complete(one);
raw=load(one.observations{1}.raw_path,'raw','spectrum');
assert(numel(raw.raw.channels)==1&&isreal(raw.raw.channels.samples)&&~isempty(raw.spectrum));
c=p; c.stage='direct'; comparison=run('mode_compare',c); must_complete(comparison);
assert(count(comparison,'mode_formal')==6);
assert(strcmp(comparison.comparison.decision,'tolerance_not_confirmed'));
c.scope.vdiv=[.001 .001]; clipped=run('mode_compare',c);
assert(strcmp(clipped.status,'paused')&&count(clipped,'mode_formal')==0);
live=p; live.mode='live'; live.authorized_devices={};
blocked=run('manual_capture',live); assert(strcmp(blocked.status,'paused'));
forced=msiq.if_workbench('mock',struct('profile',live,'hardware_confirmed',true));
must_complete(forced); assert(strcmp(forced.profile.mode,'mock'));
audit=msiq.instruments.get_audit();
assert(audit.connections==0&&audit.queries==0&&audit.writes==0&&audit.captures==0);
note=sprintf('IF grid/counts/local stop/balance/replay/resume/failure/clip/fresh gates passed; %s',r.run_dir);
end
function r=run(action,p)
r=msiq.if_workbench(action,struct('profile',p));
end
function must_complete(r)
if ~strcmp(r.status,'completed'), for k=1:numel(r.errors),disp(r.errors{k});end; end
assert(strcmp(r.status,'completed'),'msiq:if:Validation','IF operation failed.');
end
function n=count(r,role)
n=sum(cellfun(@(x)strcmp(x.role,role),r.observations));
end
