function note=validate_if_scope_restore()
%VALIDATE_IF_SCOPE_RESTORE Scan origin survives range changes, cancel and resume.
msiq.instruments.io_audit('reset','');
p=msiq.if_workbench('config');
p.scan=struct('pre_start_db',20,'pre_stop_db',20,'pre_step_db',1, ...
 'post_start_db',20,'post_stop_db',19,'post_step_db',-1);
p.scope.vdiv=[.5 .5];
a=msiq.if_workbench('scan',struct('profile',p));
assert(strcmp(a.status,'completed'));
assert(a.shutdown.scope_restored&&isequal(a.scope_start.vdiv,[.5 .5]));
assert(~isequal(a.baseline{1}.scale_vdiv,a.scope_start.vdiv),'Expected fixture to exercise range change.');
assert(isequal(a.shutdown.scope_restore.status.vdiv,a.scope_start.vdiv));
saved=load(fullfile(a.run_dir,'data','if_checkpoint.mat'),'out');assert(isequal(saved.out.scope_start,a.scope_start));
newPreference=a.scope_start;newPreference.vdiv=[1 1];
b=msiq.if_workbench('resume',struct('profile',p,'run_dir',a.run_dir,'scope_settings',newPreference));
assert(strcmp(b.status,'completed')&&isequal(b.scope_start,a.scope_start));
assert(sum(cellfun(@(x)strcmp(x.role,'recovery_baseline'),b.observations))==3);
for failure={'cancel_capture','fail_capture','fail_save'}
 q=p;q.mock.(failure{1})=3;
 c=msiq.if_workbench('scan',struct('profile',q));
 assert(ismember(c.status,{'cancelled','paused'})&&c.shutdown.awg_off_verified&&c.shutdown.scope_restored);
 assert(isequal(c.shutdown.scope_restore.status.vdiv,c.scope_start.vdiv)&&c.shutdown.board_closed);
end
% Historical raw data still exists; missing origin blocks resume before sessions.
legacy=fullfile(a.run_dir,'legacy_scope_test');mkdir(fullfile(legacy,'data'));
out=rmfield(saved.out,'scope_start');save(fullfile(legacy,'data','if_checkpoint.mat'),'out');
c=msiq.if_workbench('resume',struct('profile',p,'run_dir',legacy));
assert(strcmp(c.status,'paused')&&strcmp(c.errors{1}.identifier,'msiq:if:ResumeScope'));
assert(isfile(a.observations{1}.raw_path));
live=p;live.mode='live';
c=msiq.if_workbench('scan',struct('profile',live));
assert(strcmp(c.status,'paused')&&strcmp(c.errors{1}.identifier,'msiq:if:ScopeSource'));
% Ordinary measurement retains no scan origin and follows previous cleanup.
c=msiq.if_workbench('manual_capture',struct('profile',p));
assert(strcmp(c.status,'completed')&&~isfield(c,'scope_start'));
q=p;q.mock.fail_scope_restore=true;q.mock.fail_capture=2;
c=msiq.if_workbench('scan',struct('profile',q));
assert(strcmp(c.status,'shutdown_failed')&&c.shutdown.awg_off_verified&&~c.shutdown.scope_restored&&c.shutdown.board_closed);
assert(any(contains(string(c.shutdown.errors),'Injected scope cleanup')));
audit=msiq.instruments.get_audit();
assert(audit.connections==0&&audit.queries==0&&audit.writes==0&&audit.captures==0);
note='IF scan start, bounded cleanup, cancellation, resume and legacy gates passed with zero instrument I/O.';
end
