function note=validate_rx_auto_range(output_dir)
%VALIDATE_RX_AUTO_RANGE Pure occupancy and daily task accounting without I/O.
if nargin<1, output_dir=tempdir; end %#ok<NASGU>
p=msiq.if_workbench_config(struct('mode','mock'));
p.scope.ranges_vdiv=[.01 .02 .05 .1 .2 .5 1]; p.scope.max_adjustments=3;
p.scope.fresh=struct('verified',true,'timeout_s',1,'poll_s',.01);
p.policy.settle_s=0;p.scope.target_divisions=7;p.scope.edge_margin_divisions=.5;
p.scope.auto_range_enabled=true;
status=struct('vertical_divisions',8,'channels',struct('channel','C1', ...
    'offset_v',0,'vertical_scale_v_per_div',.1));
raw=struct('mock',true,'channels',struct('channel','C1','samples',[-.3;.3]));
d=msiq.rx_range_decision(raw,status,p.scope); assert(d.valid&&~d.needs_adjustment);
raw.channels.samples=[.7;.8];status.channels.offset_v=-.75;
d=msiq.rx_range_decision(raw,status,p.scope);assert(d.valid&&d.target_vdiv==.02);
% Descriptor coefficient is intentionally unrelated to display offset.
raw.channels.descriptor=struct('vertical_gain',.01,'vertical_offset',1,'comm_type',1);
d=msiq.rx_range_decision(raw,status,p.scope);assert(d.valid&&d.target_vdiv==.02);
raw.channels.samples=[0;326.67]; d=msiq.rx_range_decision(raw,status,p.scope);
assert(d.valid&&d.per_channel.adc_clipped&&d.target_vdiv==.2);
raw.channels.samples=[0;0];d=msiq.rx_range_decision(raw,status,p.scope);assert(~d.valid);
raw.channels.samples=[0;NaN];d=msiq.rx_range_decision(raw,status,p.scope);assert(~d.valid);
raw=struct('mock',true,'channels',struct('channel','C1','samples',[-.3;.3]));status.channels.offset_v=0;
d=msiq.rx_range_decision(raw,status,p.scope);
options=struct('capture_then_demod',false); task=msiq.RxDailyTask(1,options,p,{'C1'},3,false);
r=struct('ok',true,'capture',struct('demod_ready',false),'status',status,'raw',struct(), ...
    'observation',struct('range_decision',d,'scale_vdiv',.1,'clipped',false));
for k=1:3,assert(strcmp(task.next().action,'formal_capture'));task.accept(r);end
assert(task.completed==3&&~task.active&&numel(task.rows)==3&&all(cellfun(@(v)strcmp(v.role,'正式'),task.rows)));
% A range check is retained but not demodulated or counted.
raw.channels.samples=[-.03;.03];small=msiq.rx_range_decision(raw,status,p.scope);
task=msiq.RxDailyTask(2,options,p,{'C1'},1,false);r.observation.range_decision=small;
task.accept(r);assert(task.completed==0&&strcmp(task.next().action,'formal_range'));
newstatus=status;newstatus.channels.vertical_scale_v_per_div=.01;
task.accept(struct('ok',true,'status',newstatus));
r.status=newstatus;r.observation.scale_vdiv=.01;r.observation.range_decision=msiq.rx_range_decision(raw,newstatus,p.scope);
task.accept(r);assert(task.completed==1&&numel(task.rows)==2&&strcmp(task.rows{1}.role,'量程检查'));
p.scope.auto_range_enabled=false;task=msiq.RxDailyTask(3,options,p,{'C1'},1,false);
r.status=status;r.observation.scale_vdiv=.1;r.observation.range_decision=small;
failed=false;try task.accept(r);catch e,failed=strcmp(e.identifier,'RX_Workbench:AutoRangeDisabled');end
assert(failed&&task.completed==0);
% Fresh matching observation can pre-adjust; stale/revised observations cannot.
p.scope.auto_range_enabled=true;
cache=struct('decision',small,'status',status,'observed_datenum',now, ...
    'measurement_revision',2,'channels',{{'C1'}},'refresh_period_s',.2);
options.measurement_revision=2;options.observation_cache=cache;
task=msiq.RxDailyTask(4,options,p,{'C1'},1,false);assert(strcmp(task.next().action,'formal_range'));
task.accept(struct('ok',true,'status',status,'range_skipped',true));
assert(task.range_adjustments==0&&isempty(fieldnames(task.frozen_status))&&strcmp(task.next().action,'formal_capture'));
options.observation_cache.observed_datenum=now-10/86400;
task=msiq.RxDailyTask(5,options,p,{'C1'},1,false);assert(strcmp(task.next().action,'formal_capture'));
options.observation_cache=cache; options.measurement_revision=3;
task=msiq.RxDailyTask(6,options,p,{'C1'},1,false);assert(strcmp(task.next().action,'formal_capture'));
% Two channels choose separate legal ranges and the full-frame spike counts.
raw.channels(2)=raw.channels(1);raw.channels(2).channel='C2';raw.channels(2).samples=[-.03;.03;.32];
status.channels(2)=status.channels(1);status.channels(2).channel='C2';
d=msiq.rx_range_decision(raw,status,p.scope);assert(d.valid&&isequal(d.target_vdiv,[.01 .1]));
note='PASS: occupancy, offset, ADC clipping, zero/nonfinite data, minimal legal range, 1/N formal captures, conditional range checks, disabled automatic range';
end
