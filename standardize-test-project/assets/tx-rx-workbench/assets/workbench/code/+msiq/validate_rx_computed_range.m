function note=validate_rx_computed_range(output_dir)
%VALIDATE_RX_COMPUTED_RANGE Pure computed range and task accounting; no I/O.
if nargin<1, output_dir=tempdir; end %#ok<NASGU>
p=msiq.if_workbench_config(struct('mode','mock'));
p.scope.range_strategy='computed'; p.scope.ranges_vdiv=[]; p.scope.headroom=NaN;
p.scope.max_adjustments=3; p.scope.fresh=struct('verified',true,'timeout_s',1,'poll_s',.01);
p.policy.settle_s=0; p.scope.target_divisions=7; p.scope.edge_margin_divisions=.5;
options=struct('capture_then_demod',false);
for scale=[.0005 .001 .00314159]
    [raw,status]=frame([-3.5;3.5]*scale,scale,0);
    d=msiq.rx_range_decision(raw,status,p.scope);
    assert(d.valid && d.safe && ~d.needs_adjustment);
    assert(abs(d.target_vdiv-scale)<1e-12);
end
% Display offset, not ADC decoder offset, determines required screen room.
[raw,status]=frame([.007;.008],.01,-.0075);
raw.channels.descriptor=struct('vertical_gain',.001,'vertical_offset',1,'comm_type',1);
d=msiq.rx_range_decision(raw,status,p.scope);
assert(d.valid && abs(d.target_vdiv-.001/7)<1e-12);
raw.channels.samples=[0;0]; assert(~msiq.rx_range_decision(raw,status,p.scope).valid);
raw.channels.samples=[0;NaN]; assert(~msiq.rx_range_decision(raw,status,p.scope).valid);
% A spike only present in the full acquisition controls the computed request.
[raw,status]=frame([zeros(10000,1);.032],.1,0);
d=msiq.rx_range_decision(raw,status,p.scope);
assert(d.valid && abs(d.target_vdiv-.032/3.5)<1e-12);
raw.channels(2)=raw.channels; raw.channels(2).channel='C2';
raw.channels(2).samples=[-.0035;.0035];
status.channels(2)=status.channels; status.channels(2).channel='C2';
d=msiq.rx_range_decision(raw,status,p.scope);
assert(d.valid && abs(d.target_vdiv(2)-.001)<1e-12 && d.target_vdiv(1)>d.target_vdiv(2));
[raw,status]=frame([-.004;.004],.001,0);
d=msiq.rx_range_decision(raw,status,p.scope);
assert(d.valid && ~d.safe && d.per_channel.adc_clipped && d.target_vdiv==.002);
accepted=p.scope; accepted.accept_actual_channels={'C1'};
assert(msiq.rx_range_decision(raw,status,accepted).needs_adjustment,'Matching cannot suppress unsafe data');
% Suitable first frames are formal directly; no obligatory trial acquisition.
for count=[1 3]
    task=msiq.RxDailyTask(count,options,p,{'C1'},count,false);
    for k=1:count
        [raw,status]=frame([-.0035;.0035],.001,0);
        deliver(task,raw,status);
    end
    assert(task.completed==count && ~task.active && numel(task.rows)==count);
    assert(all(cellfun(@(r)strcmp(r.role,'正式'),task.rows)));
end
% A device may accept a different positive value. Use it as the frozen value.
for actual=[.001 .0009]
    task=msiq.RxDailyTask(10,options,p,{'C1'},1,false);
    [raw,status]=frame([-.003;.003],.01,0); deliver(task,raw,status);
    req=task.next(); assert(strcmp(req.action,'formal_range') && strcmp(req.range_strategy,'computed'));
    assert(abs(req.values-.006/7)<1e-12 && task.completed==0);
    status.channels.vertical_scale_v_per_div=actual;
    task.accept(struct('ok',true,'status',status));
    assert(isequal(task.ranges,actual) && isequal(task.next().frozen_ranges,actual));
    deliver(task,raw,status);
    assert(~task.active && task.completed==1 && numel(task.rows)==2);
    assert(strcmp(task.rows{1}.role,'量程检查') && strcmp(task.rows{2}.role,'正式'));
end
% A downward match that lacks margin must be enlarged before formal counting.
task=msiq.RxDailyTask(15,options,p,{'C1'},3,false);
[raw,status]=frame([-.003;.003],.01,0); deliver(task,raw,status);
status.channels.vertical_scale_v_per_div=.0008;
task.accept(struct('ok',true,'status',status)); deliver(task,raw,status);
req=task.next(); assert(strcmp(req.action,'formal_range') && abs(req.values-.0016)<1e-12);
assert(task.completed==0 && numel(task.rows)==2);
status.channels.vertical_scale_v_per_div=.0016;
task.accept(struct('ok',true,'status',status));
for k=1:3
    % Full-frame extrema vary naturally; safe repeated points retain the
    % accepted actual range rather than chasing tiny new target values.
    raw.channels.samples=[-.003;.003]*(1+(k-1)*.01);
    deliver(task,raw,status);
end
assert(task.completed==3 && ~task.active && numel(task.rows)==5);
% The acceptance is task-local: a new task evaluates the actual waveform.
newtask=msiq.RxDailyTask(18,options,p,{'C1'},1,false);
deliver(newtask,raw,status);
assert(strcmp(newtask.next().action,'formal_range') && newtask.completed==0);
% An unchanged unsafe readback cannot cause unbounded repeated writes.
task=msiq.RxDailyTask(11,options,p,{'C1'},1,false);
[raw,status]=frame([-.0038;.0038],.001,0); deliver(task,raw,status);
assert(strcmp(task.next().action,'formal_range'));
task.accept(struct('ok',true,'status',status));
failed=expect_rejection(@()deliver(task,raw,status));
assert(failed && task.completed==0 && task.range_adjustments<=p.scope.max_adjustments);
% Progress on C2 must not conceal the unchanged, still unsafe C1 readback.
task=msiq.RxDailyTask(16,options,p,{'C1','C2'},1,false);
[raw,status]=frame([-.0038;.0038],.001,0);
raw.channels(2)=raw.channels; raw.channels(2).channel='C2';
raw.channels(2).samples=[-.0035;.0035];
status.channels(2)=status.channels; status.channels(2).channel='C2';
status.channels(2).vertical_scale_v_per_div=.01;
deliver(task,raw,status); assert(strcmp(task.next().action,'formal_range'));
status.channels(2).vertical_scale_v_per_div=.002;
task.accept(struct('ok',true,'status',status));
assert(expect_rejection(@()deliver(task,raw,status)));
assert(task.completed==0 && task.range_adjustments==1 && ~strcmp(task.phase,'range'));
% Exhausted per-point budget and disabled auto range retain the check frame.
for automatic=[true false]
    q=p; q.scope.auto_range_enabled=automatic; if automatic, q.scope.max_adjustments=0; end
    task=msiq.RxDailyTask(12,options,q,{'C1'},1,false);
    [raw,status]=frame([-.003;.003],.01,0);
    assert(expect_rejection(@()deliver(task,raw,status)));
    assert(task.completed==0 && strcmp(task.rows{1}.role,'量程检查'));
end
% Observation preadjustment counts against the same formal point budget.
[raw,status]=frame([-.003;.003],.01,0);
c=struct('decision',msiq.rx_range_decision(raw,status,p.scope),'status',status, ...
    'observed_datenum',now,'measurement_revision',5,'channels',{{'C1'}},'refresh_period_s',.2);
o=options; o.measurement_revision=5; o.observation_cache=c;
task=msiq.RxDailyTask(13,o,p,{'C1'},1,false);
assert(strcmp(task.next().action,'formal_range'));
status.channels.vertical_scale_v_per_div=.001;
task.accept(struct('ok',true,'status',status)); assert(task.range_adjustments==1);
deliver(task,raw,status); assert(task.completed==1 && numel(task.rows)==1);
% Balance quality confirmations must not silently adjust or mix ranges.
q=p; q.board.runtime=struct('protocol_verified',true,'mapping_verified',true,'response_verified',true);
q.board.mapping=struct('i_channel','C1','q_channel','C2');
q.board.limits=struct('i',repmat([0 31.5],6,1),'q',repmat([0 31.5],6,1));
board=struct('state_known',true,'state',struct('agc',zeros(1,6),'i',ones(1,6)*10,'q',ones(1,6)*10));
task=msiq.RxDailyTask(14,options,q,{'C1','C2'},1,true,board);
task.phase='capture'; task.role='balance_confirmation'; task.ranges=[.001 .001];
[raw,status]=frame([-.0038;.0038],.001,0);
raw.channels(2)=raw.channels; raw.channels(2).channel='C2';
status.channels(2)=status.channels; status.channels(2).channel='C2';
assert(expect_rejection(@()deliver(task,raw,status)));
assert(~strcmp(task.phase,'range') && task.completed==0);
% Partial-write evidence survives compact journal persistence without raw arrays.
cfg=msiq.build_config('v2_traditional_wz'); cfg.results_root=output_dir;
task=msiq.RxDailyTask(17,options,p,{'C1'},1,false);
report=struct('strategy','computed','requested_values',[.001 .002], ...
    'actual_values',[.001 NaN],'channels',{{'C1','C2'}}, ...
    'written_channels',{{'C1'}},'ok',false,'error','mock partial write');
task.rows={struct('role','量程检查','capture',struct(), ...
    'observation',struct('range_reports',{{report}},'display_raw',ones(20,1)))};
run=msiq.rx_daily_journal('begin',cfg,task);
msiq.rx_daily_journal('update',cfg,task,run, ...
    struct('action','formal_range','ok',false,'error',report.error,'range_report',report));
saved=load(fullfile(run.DataDir,'task_state.mat'),'state');
assert(isequaln(saved.state.events{end}.range_report,report));
assert(isequaln(saved.state.rows{1}.observation.range_reports{1},report));
assert(~isfield(saved.state.rows{1}.observation,'display_raw'));
note='PASS: continuous computed scales; full-frame offset/spike/ADC checks; one/three formal counts; rounded actual freeze; bounded unsafe retries; preadjustment budget; balance confirmation range freeze';
end
function [raw,status]=frame(x,scale,offset)
raw=struct('mock',true,'channels',struct('channel','C1','samples',x));
status=struct('vertical_divisions',8,'channels',struct('channel','C1','offset_v',offset,'vertical_scale_v_per_div',scale));
end
function deliver(task,raw,status)
request=task.next(); assert(strcmp(request.action,'formal_capture'));
d=msiq.rx_range_decision(raw,status,request.profile.scope);
o=struct('range_decision',d,'scale_vdiv',[status.channels.vertical_scale_v_per_div], ...
    'clipped',any([d.per_channel.adc_clipped]),'power_dbv2',[0 -1]);
task.accept(struct('ok',true,'capture',struct('demod_ready',true), ...
    'status',status,'raw',raw,'observation',o));
end
function rejected=expect_rejection(fn)
rejected=false;
try fn(); catch ex
    assert(startsWith(ex.identifier,'RX_Workbench:'),'Unexpected error: %s',ex.message);
    rejected=true;
end
end
