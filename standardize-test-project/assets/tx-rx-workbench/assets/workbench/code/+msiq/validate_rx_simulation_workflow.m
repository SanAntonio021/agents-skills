function note=validate_rx_simulation_workflow()
%VALIDATE_RX_SIMULATION_WORKFLOW Exercise daily controls with coded simulated data.
folder=msiq.validation_artifacts('directory');
options=struct('visible',false,'maximize',false,'use_timer',false,'auto_connect',false, ...
    'preferences_path','','simulation',struct('cache_dir',fullfile(folder,'cache'),'test_fixture',true));
fig=RX_Workbench('gui',options); cleanup=onCleanup(@()finish(fig));
s=state(); invoke(s.home.h_play);
await(@(q)q.first_capture_complete,240); s=state(); invoke(s.home.h_pause);
await(@(q)~q.busy,60); s=state(); s.cfg.results_root=folder; put(s);
s=state(); selection=get(s.home.position_group,'SelectionChangedFcn'); set(s.home.position_group,'SelectedObject',s.home.position_buttons(4)); selection(s.home.position_group,struct('NewValue',s.home.position_buttons(4)));
s=state(); invoke(s.home.board.controls.connect);
await(@(q)q.home.board.getSnapshot().is_open && ~q.busy && isempty(q.board_pending),90);

s=state(); invoke(s.home.board.controls.down);
await(@(q)q.home.board.getSnapshot().state_known && ~q.busy && isempty(q.board_pending),90);
s=state(); assert(strcmp(get(s.home.h_balance,'Enable'),'on'),get(s.home.h_balance,'TooltipString'));
invoke(s.home.h_balance);
await(@(q)~isempty(q.task) && ~q.task.active && ~q.task_waiting,900);
s=state(); assert(s.task.balance && s.task.completed==0);
assert(ismember(s.task.reason,{'配平完成，已达到容差','配平停止：达到调整次数上限', ...
    '配平停止：达到批准边界','通信质量确认变差，已恢复此前设置', ...
    '功率差不再改善，已恢复此前设置'}),s.task.reason);
assert(~s.running && ~isempty(s.task.rows),'Balance must finish before formal measurement.');
assert(all(cellfun(@(r)~ismember(r.role,{'formal','正式'}),s.task.rows)));
balance_reason=s.task.reason;
set(s.home.h_count,'String','3'); invoke(s.home.h_repeat);
await(@(q)~q.task.active && ~q.task_waiting,900); s=state();
assert(~s.task.balance && s.task.completed==3 && strcmp(s.task.reason,'测量完成'),s.task.reason);
formal=s.task.rows(cellfun(@(r)ismember(r.role,{'formal','正式'}),s.task.rows));
assert(numel(formal)==3);
boards=cell(1,3); hashes=cell(1,3);
for k=1:3
    row=formal{k}; metadata=jsondecode(fileread(row.capture.metadata_path));
    assert(strcmp(metadata.source_mode,'simulation'));
    assert(row.observation.metrics.valid && row.observation.metrics.pre_bit_count==194400);
    boards{k}=metadata.board_state; hashes{k}=compute_file_sha256(row.capture.raw_path);
    raw=load(row.capture.raw_path,'raw');
    assert(numel(raw.raw.channels(1).samples)>numel(row.capture.display_raw.channels(1).samples));
end
assert(isequaln(boards{1},boards{2}) && isequaln(boards{2},boards{3}),'Formal board settings changed.');
% Stop a new repeated task through the visible action, then keep prior raw intact.
invoke(s.home.h_repeat); s=state(); invoke(s.home.h_stop);
await(@(q)~q.task.active && ~q.task_waiting,120); s=state();
assert(s.task.stopped && s.task.completed==0 && ~s.running);
for k=1:3, assert(strcmp(hashes{k},compute_file_sha256(formal{k}.capture.raw_path))); end
note=['实际模拟GUI：连接/完整下发、配平终态（' balance_reason '）、三次严格纠错前解调、固定设置、停止及历史保护通过。'];
% Verify release explicitly: onCleanup alone turns cleanup failures into warnings.
finish(fig);
clear cleanup;
    function s=state(), s=getappdata(fig,'rx_workbench_state'); end
    function put(s), setappdata(fig,'rx_workbench_state',s); end
    function await(predicate,limit)
        started=tic;
        while ~predicate(state())
            s=state(); assert(toc(started)<limit,'RX_Workbench:WorkflowTimeout','%s',get(s.home.h_status,'String'));
            tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
        end
    end
end
function invoke(h), callback=get(h,'Callback'); callback(h,[]); end
function finish(fig)
if ~isgraphics(fig), return; end
close(fig); started=tic;
while isgraphics(fig) && toc(started)<60
    tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
end
assert(~isgraphics(fig),'RX_Workbench:ReleaseTimeout','模拟工作台后台未完成释放。');
end
