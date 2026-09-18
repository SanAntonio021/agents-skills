function note=validate_rx_input_queue(output_dir)
% Exercise GUI queues while a deterministic mock write is in flight.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
logpath=fullfile(output_dir,'input_queue_io.log');
fid=Result_Open_File_Retry(logpath,'w'); fclose(fid);
io=msiq.instruments.mock_rx_scope_io(struct('capture_delay_s',0,'record_count',2001, ...
    'log_path',logpath,'failure_path',fullfile(output_dir,'no_failure.txt')));
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false,'synchronous_startup',true, ...
    'use_timer',false,'find_reference',false,'io',io,'config',msiq.rx_mock_config()));
guard=onCleanup(@() close(fig)); %#ok<NASGU>
s=getappdata(fig,'rx_workbench_state'); invoke(s.home.h_pause);
h=s.home.h_off1;
% The actual queue is blocked by an older write; restoring old actual=0 must
% enqueue a second write, rather than accepting the stale pre-write readback.
flight(h,'setting',100,.01);
set(h,'String','.01'); key(h,'backspace'); set(h,'String','0'); key(h,'return');
s=getappdata(fig,'rx_workbench_state');
assert(numel(s.pending)==1 && s.pending.value==0,'Restore was dropped while older numeric write was in flight.');
key(h,'return'); s=getappdata(fig,'rx_workbench_state'); assert(numel(s.pending)==1,'Duplicate Enter queued another write.');
assert_blocked(s);
io.write(s.session,'C1:OFST 0.01'); release();
s=getappdata(fig,'rx_workbench_state'); assert(isempty(s.pending)&&s.scope_status.channels(1).offset_v==0);
log=fileread(logpath); assert(contains(log,'WRITE C1:OFST 0.01')&&contains(log,'WRITE C1:OFST 0'));
% Enum changes in flight follow the same rule, while duplicate same-value
% submissions are collapsed into one pending request.
h=[];
for item=s.home.extended_edits
    d=get(item,'UserData'); if strcmp(d.key,'BWL')&&d.index==1, h=item; break; end
end
assert(~isempty(h)); d=get(h,'UserData');
flight(h,'control',200,'ON');
set(h,'Value',find(strcmp(d.choices,'OFF'),1)); invoke(h);
s=getappdata(fig,'rx_workbench_state'); assert(numel(s.control_pending)==1&&strcmp(s.control_pending.value,'OFF'));
invoke(h); s=getappdata(fig,'rx_workbench_state'); assert(numel(s.control_pending)==1);
assert_blocked(s);
io.write(s.session,'BWL C1,ON'); release();
s=getappdata(fig,'rx_workbench_state'); assert(isempty(s.control_pending));
d=get(h,'UserData'); assert(strcmp(d.actual,'OFF'));
% Task gate must also inspect transport queues even if an input widget's
% visual state has been cleared (for example after a separate UI refresh).
s.busy=true; s.worker_request=struct('action','setting','handle',s.home.h_off1);
setappdata(fig,'rx_workbench_state',s); assert_blocked(s);
s=getappdata(fig,'rx_workbench_state'); s.busy=false; s.worker_request=struct(); setappdata(fig,'rx_workbench_state',s);
note='RX input queues passed: restore during numeric/enum flight, duplicate suppression and task transport gates; mock only.';
    function flight(item,action,revision,value)
        state=getappdata(fig,'rx_workbench_state'); state.busy=true;
        state.worker_request=struct('action',action,'handle',item,'revision',revision,'value',value);
        setappdata(fig,'rx_workbench_state',state); msiq.rx_input_state('pending',item,revision);
    end
    function release()
        state=getappdata(fig,'rx_workbench_state'); state.busy=false; state.worker_request=struct();
        setappdata(fig,'rx_workbench_state',state); callback=getappdata(fig,'rx_workbench_tick'); callback([],[]);
    end
    function assert_blocked(state)
        before=fileread(logpath); invoke(state.home.h_single);
        now=getappdata(fig,'rx_workbench_state');
        assert(isempty(now.task)||~now.task.active,'Task started with unresolved instrument control.');
        assert(contains(get(now.home.h_status,'String'),'示波器设置'), ...
            'Task was rejected by an unrelated gate instead of pending scope settings.');
        assert(strcmp(before,fileread(logpath)),'Blocked task performed instrument I/O.');
    end
end
function invoke(h)
callback=get(h,'Callback'); callback(h,[]); drawnow;
end
function key(h,name)
callback=get(h,'KeyPressFcn'); callback(h,struct('Key',name)); drawnow;
end
