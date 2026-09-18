function note=validate_rx_daily_gui(output_dir)
%VALIDATE_RX_DAILY_GUI Exercise actual callbacks and two asynchronous workers.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
[~,location]=fileattrib(output_dir); output_dir=location.Name;
cfg=msiq.rx_mock_config(); cfg.results.root=output_dir;
p=msiq.if_workbench_config(struct('mode','mock')); p.scope.sample_rate_hz=80e9;
p.scope.fresh=struct('verified',true,'timeout_s',2,'poll_s',.01,'reset_command','MOCK:RESET', ...
    'start_command','MOCK:START','completion_query','MOCK:DONE?','pending_response','0','complete_response','1');
opts=struct('config',cfg,'visible',false,'maximize',false,'auto_connect',true, ...
    'synchronous_startup',true,'use_timer',false,'find_reference',false,'asynchronous',true, ...
    'if_profile',p,'worker_factory','msiq.rx_daily_mock_io','worker_options',struct( ...
    'capture_delay_s',0,'timebase_s',40e-9,'record_count',32000,'log_path',fullfile(output_dir,'gui_io.log'), ...
    'failure_path',fullfile(output_dir,'failure.txt')));
fig=msiq.rx_workbench_app(opts); guard=onCleanup(@()finish(fig));
await(fig,@(s)s.connected,90); s=getappdata(fig,'rx_workbench_state');
invoke(s.home.h_pause); await(fig,@(s)~s.busy,30);
initial=getappdata(fig,'rx_workbench_state');
select=get(initial.home.position_group,'SelectionChangedFcn');
set(initial.home.position_group,'SelectedObject',initial.home.position_buttons(4));
select(initial.home.position_group,struct('NewValue',initial.home.position_buttons(4)));
s=getappdata(fig,'rx_workbench_state');
assert(isfield(initial.raw,'channels') && numel(initial.raw.channels)==2 && all([initial.raw.channels.wave_valid]), ...
    'Screenshot fixture requires a verified two-channel mock capture');
set(s.home.h_demod,'Value',0); invoke(s.home.h_demod);
set(s.home.h_ch2,'Value',5); invoke(s.home.h_ch2); await(fig,@(s)~s.busy,30);
s=getappdata(fig,'rx_workbench_state'); assert(~s.second_enabled);
% C1 starts at 15 mV/div and the mock rounds the required 15.7 mV/div
% back to 15: the computed strategy correctly stops that unsafe no-progress
% case. Use C3's 30 mV/div for this successful results-window workflow.
set(s.home.h_ch1,'Value',3); invoke(s.home.h_ch1); await(fig,@(s)~s.busy,30);
s=getappdata(fig,'rx_workbench_state');
set(s.home.h_count,'String','3'); invoke(s.home.h_repeat);
result=getappdata(fig,'rx_result_window'); assert(isgraphics(result),'Result window must open immediately');
assert(strcmp(get(result,'Visible'),'off'),'Hidden parent must not expose a test window');
rs=getappdata(result,'rx_result_window_state'); assert(contains(get(rs.status,'String'),'0 / 3'));
await(fig,@(s)s.task.completed>=1,180);
rs=getappdata(result,'rx_result_window_state'); selected=rs.selected;
set(rs.list,'Value',selected); invoke(rs.list);
await(fig,@(s)s.task.completed>=2,180);
rs=getappdata(result,'rx_result_window_state'); assert(rs.selected==selected && ~rs.follow,'Selection must survive next formal result');
close(result);
await(fig,@(s)~isempty(s.task) && ~s.task.active,180);
closed=getappdata(fig,'rx_result_window'); assert(isempty(closed)||~isgraphics(closed),'Closing results must not reopen or stop repeat');
s=getappdata(fig,'rx_workbench_state'); invoke(s.home.h_view_result);
result=getappdata(fig,'rx_result_window'); assert(isgraphics(result),'View results must reopen');
rs=getappdata(result,'rx_result_window_state'); assert(contains(get(rs.status,'String'),'3 / 3') && ~isempty(rs.image_path));
s=getappdata(fig,'rx_workbench_state'); assert(s.task.completed==3,s.task.reason);
roles=cellfun(@(r)r.role,s.task.rows,'UniformOutput',false); assert(sum(strcmp(roles,'正式'))==3);
formal=find(strcmp(roles,'正式'));
for k=1:3
    outcome=jsondecode(fileread(fullfile(s.task.rows{formal(k)}.capture.run_dir,'data','task_outcome.json')));
    assert(outcome.completed_formal==k,'Saved formal count must match 1/2/3');
end
assert(strcmp(get(s.home.h_vdiv1,'Enable'),'on'),'Controls must unlock after completion');
readback=get(s.home.h_vdiv1,'UserData');
channel_index=find(strcmp({s.scope_status.channels.channel},s.channels{1}),1);
assert(readback.actual==s.scope_status.channels(channel_index).vertical_scale_v_per_div);
fprintf('MATLAB screen DPI: %.0f; screenshot dimensions 1280x720 and 1920x1080\n',get(groot,'ScreenPixelsPerInch'));
assert(isempty(s.reference_worker),'Raw-only captures must not spawn a DSP worker');
rows=getappdata(s.home.h_history,'records'); assert(numel(rows)>=4);
for k=1:numel(rows)
    raw=load(rows{k}.capture.raw_path,'raw'); assert(numel(raw.raw.channels)==1 && numel(raw.raw.channels.samples)==32000);
    evidence=jsondecode(fileread(fullfile(rows{k}.capture.run_dir,'data','capture_validation.json'))); assert(evidence.valid);
end
set(s.home.h_history,'Value',1); invoke(s.home.h_history); before=getappdata(fig,'rx_workbench_state');
assert(isequaln(before.raw,rows{1}.observation.display_raw),'History selection must match exact display record');
% Representative screenshot uses actual mock capture and adapter-sent six-band values.
s=getappdata(fig,'rx_workbench_state'); s.raw=initial.raw; s.raw_scope_status=initial.scope_status;
s.second_enabled=true; set(s.home.h_ch2,'Value',str2double(s.channels{2}(2))); setappdata(fig,'rx_workbench_state',s);
boardcfg=struct('mode','mock','role','rx','limits',struct('rf',repmat([0 31.5],6,1), ...
    'i',repmat([0 31.5],6,1),'q',repmat([0 31.5],6,1)));
board=msiq.instruments.IfBoard(boardcfg); board.open(); board.initialize(struct('rf',20:.5:22.5,'i',18:.5:20.5,'q',18.5:.5:21));
s.home.board.update(board.snapshot());
for shape={[1280 720],[1920 1080]}
    sz=shape{1}; set(fig,'Position',[20 20 sz],'Visible','on'); drawnow;
    callback=get(fig,'SizeChangedFcn'); callback(fig,[]);
    s=getappdata(fig,'rx_workbench_state'); slider=s.home.scroll;
    repeatpos=get(s.home.h_repeat,'Position'); countpos=get(s.home.h_count,'Position'); stoppos=get(s.home.h_stop,'Position');
    assert(countpos(1)>sum(repeatpos([1 3])) && countpos(1)-sum(repeatpos([1 3]))<60);
    assert(abs(countpos(2)-repeatpos(2))<5 && stoppos(1)>=0 && sum(stoppos([1 3]))<=sz(1) && sum(stoppos([2 4]))<=sz(2));
    set(slider,'Value',get(slider,'Max')); invoke(slider); drawnow;
    frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,sprintf('rx_feedback_top_%dx%d.png',sz)));
    board_position=get(s.home.board.panel,'Position'); offset=s.home.content_height-sum(board_position([2 4])); set(slider,'Value',get(slider,'Max')-offset);
    callback=get(slider,'Callback'); callback(slider,[]); drawnow;
    frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,sprintf('rx_mock_board_%dx%d.png',sz)));
    for view={'display','trigger','acquisition'}
        switch view{1}
            case 'display', panel=s.home.display_panel;
            case 'trigger', panel=s.home.trigger_panel;
            otherwise, panel=s.home.settings_groups(end);
        end
        box=get(panel,'Position'); offset=min(get(slider,'Max'),s.home.content_height-sum(box([2 4])));
        set(slider,'Value',max(0,get(slider,'Max')-offset)); invoke(slider); drawnow;
        frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,sprintf('rx_feedback_%s_%dx%d.png',view{1},sz)));
    end
end
board.close();
note='PASS: result window immediate/progress/selection/close/reopen; top count and stop layout; actual GUI callback -> worker fresh raw-only single-channel repeated capture; exactly 3 formal; accepted actual ranges; durable full raw; history selection';
end
function invoke(h)
cb=get(h,'Callback'); cb(h,[]);
end
function await(fig,predicate,limit)
started=tic;
while true
    s=getappdata(fig,'rx_workbench_state'); if predicate(s), return; end
    assert(toc(started)<limit,'GUI test timeout: %s',get(s.home.h_status,'String'));
    tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
end
end
function finish(fig)
if ~isgraphics(fig), return; end
s=getappdata(fig,'rx_workbench_state'); workers={s.worker,s.reference_worker};
result=getappdata(fig,'rx_result_window'); if isgraphics(result), delete(result); end
close(fig); started=tic;
while isgraphics(fig) && toc(started)<40
    tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
end
for k=1:numel(workers), if ~isempty(workers{k}), assert(workers{k}.process.HasExited,'Worker still owns session'); end; end
end
