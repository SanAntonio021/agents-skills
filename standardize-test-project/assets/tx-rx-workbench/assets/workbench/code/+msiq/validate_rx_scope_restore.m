function note=validate_rx_scope_restore(folder)
%VALIDATE_RX_SCOPE_RESTORE Mock-only snapshot, preset isolation and restore.
if nargin<1,folder=msiq.validation_artifacts('directory');end
if ~isfolder(folder),mkdir(folder);end
opts=struct('log_path',fullfile(folder,'io.log'),'failure_path',fullfile(folder,'fail.flag'),'capture_delay_s',0,'record_count',1024);
io=msiq.instruments.mock_rx_scope_io(opts);session=io.open([]);
io.write(session,'C1:OFST 0.002');
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','TI'),io.query,io.write);
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTIME','value',2e-9),io.query,io.write);
target=take();
io.write(session,'C1:VDIV 0.04');io.write(session,'C1:OFST -0.003');io.write(session,'TDIV 1e-6');io.write(session,'TRDL 2e-6');
io.write(session,'C3:VDIV 0.2');
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','OFF'),io.query,io.write);
r=msiq.rx_scope_restore(session,target,{'C1','C2'},io);assert(r.ok,strjoin(r.errors,';'));
assert(r.status.timebase==5e-6&&r.status.trigger_delay_s==0);
assert(r.status.channels(1).offset_v==.002&&r.status.channels(3).vertical_scale_v_per_div==.2);
assert(~any(startsWith(r.applied,'C3')));
r=msiq.rx_scope_restore(session,target,{'C1','C2'},io);assert(r.ok&&isempty(r.applied));
bad=target;bad.identity='DIFFERENT';r=msiq.rx_scope_restore(session,bad,{'C1','C2'},io);assert(~r.ok&&isempty(r.applied));
limited=io;limited.write=@fail_write;io.write(session,'C1:VDIV 0.04');
r=msiq.rx_scope_restore(session,target,{'C1','C2'},limited);assert(~r.ok&&strcmp(r.phase,'C1:VDIV')&&~any(strcmp(r.applied,'TRMD')));
r=msiq.rx_scope_restore(session,target,{'C1','C2'},io);assert(r.ok,strjoin(r.errors,';'));
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','OFF'),io.query,io.write);
off_target=take();
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','TI'),io.query,io.write);
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTIME','value',3e-9),io.query,io.write);
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','OFF'),io.query,io.write);
r=msiq.rx_scope_restore(session,off_target,{'C1','C2'},io);assert(r.ok,strjoin(r.errors,';'));
assert(ismember('HTYPE temporary TI',r.applied));
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','TI'),io.query,io.write);
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTIME','value',3e-9),io.query,io.write);
msiq.instruments.apply_rx_scope_setting(session,struct('key','HTYPE','value','OFF'),io.query,io.write);
failtime=io;failtime.write=@fail_time;
r=msiq.rx_scope_restore(session,off_target,{'C1','C2'},failtime);assert(~r.ok&&strcmp(r.phase,'HTIME'));
assert(~ismember('HTYPE restored',r.applied)&&~ismember('TRMD',r.applied));
r=msiq.rx_scope_restore(session,off_target,{'C1','C2'},io);assert(r.ok,strjoin(r.errors,';'));
r=msiq.rx_scope_restore(session,target,{'C1','C2'},io);assert(r.ok);
cancel=struct('check',@() error('mock:Cancelled','Cancelled'));
r=msiq.rx_scope_restore(session,target,{'C1','C2'},io,cancel);assert(~r.ok&&isempty(r.applied));
mismatch=io;mismatch.query=@wrong_readback;
r=msiq.rx_scope_restore(session,target,{'C1','C2'},mismatch);assert(~r.ok&&contains(r.errors{1},'不一致'));
r=msiq.rx_scope_restore(session,target,{'C1','C2'},io);assert(r.ok);
store=struct('store_path',fullfile(folder,'presets'));project=fileparts(folder);
msiq.rx_scope_presets('save',project,'simulation',target,store);
assert(isempty(msiq.rx_scope_presets('load',project,'measurement',target,store)));
other=target;other.identity='OTHER,SCOPE,SERIAL';assert(isempty(msiq.rx_scope_presets('load',project,'simulation',other,store)));
changed=target;changed.fields(strcmp({changed.fields.key},'TDIV')).value=7e-6;changed.fields(strcmp({changed.fields.key},'C1:OFST')).value=.02;
store.keys={'TDIV'};saved=msiq.rx_scope_presets('save',project,'simulation',changed,store);
assert(saved.fields(strcmp({saved.fields.key},'TDIV')).value==7e-6);
assert(saved.fields(strcmp({saved.fields.key},'C1:OFST')).value==.002);
assert(isempty(msiq.rx_scope_presets('save',project,'simulation',target,struct('store_path',''))));
% An unwritable location cannot destroy the last complete preset. A regular
% file used as a parent is deterministic on Windows without changing ACLs.
preset_path=msiq.rx_scope_presets('path',project,'simulation',target,store);
original_hash=msiq.file_sha256(preset_path);
blocked_parent=fullfile(folder,'preset_parent_is_file');
fid=fopen(blocked_parent,'w');assert(fid>=0);fprintf(fid,'regular file');fclose(fid);
failed=false;
try
 msiq.rx_scope_presets('save',project,'simulation',changed, ...
  struct('store_path',fullfile(blocked_parent,'cannot_create')));
catch
 failed=true;
end
assert(failed,'Blocked preset location unexpectedly succeeded');
assert(strcmp(original_hash,msiq.file_sha256(preset_path)));
retained=msiq.rx_scope_presets('load',project,'simulation',target,store);
assert(isequaln(retained,saved));

% First manual edit after moving to C3/C4 establishes those whole channels,
% without importing unrelated global or prior-channel changes.
status=msiq.instruments.rx_scope_state(session,io.query);
status.settings=msiq.instruments.rx_scope_settings(session,io.query);
third=msiq.rx_scope_snapshot(status,{'C3','C4'});
third.fields(strcmp({third.fields.key},'TDIV')).value=8e-6;
store.keys={'C3:VDIV'};
expanded=msiq.rx_scope_presets('save',project,'simulation',third,store);
for n=1:numel(saved.fields)
 f=saved.fields(n);k=find(strcmp({expanded.fields.key},f.key),1);
 assert(isequaln(expanded.fields(k).value,f.value));
end
assert(all(ismember({'C3:VDIV','C3:OFST','C3:TRA','C4:VDIV','C4:OFST','C4:TRA'},{expanded.fields.key})));
io.write(session,'C3:OFST 0.01');io.write(session,'C4:VDIV 0.08');
r=msiq.rx_scope_restore(session,expanded,{'C3','C4'},io);assert(r.ok,strjoin(r.errors,';'));
assert(r.status.channels(3).offset_v==0&&r.status.channels(4).vertical_scale_v_per_div==.04);
assert(~any(startsWith(r.applied,{'C1:','C2:'})));
malformed=expanded;malformed.fields(strcmp({malformed.fields.key},'C4:OFST'))=[];
r=msiq.rx_scope_restore(session,malformed,{'C3','C4'},io);assert(~r.ok&&isempty(r.attempted_commands));
io.close(session);note='PASS: scope snapshot and restore, identity/channel isolation, holdoff dependencies, failure stopping and preset save preservation';
fprintf('RX scope restore PASS: identity, selected channels, dependencies, readback, partial failure, preset isolation and failed-save preservation.\n');
 function s=take()
  status=msiq.instruments.rx_scope_state(session,io.query);status.settings=msiq.instruments.rx_scope_settings(session,io.query);s=msiq.rx_scope_snapshot(status,{'C1','C2'});
 end
 function reply=wrong_readback(s,c)
  reply=io.query(s,c);if strcmp(c,'C1:VDIV?'),reply='0.04';end
 end
 function fail_time(s,c)
  if contains(c,'HoldoffTime.Value='),error('mock:TimeFailure','Injected holdoff failure');end
  io.write(s,c);
 end
 function fail_write(s,c)
  if startsWith(c,'C1:VDIV '),error('mock:RestoreFailure','Injected write failure');end
  io.write(s,c);
 end
end
