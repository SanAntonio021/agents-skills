function note=validate_rx_real_if_workflow(output_dir)
%VALIDATE_RX_REAL_IF_WORKFLOW Real asynchronous GUI path, native simulation only.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
[~,location]=fileattrib(output_dir); output_dir=location.Name;
msiq.instruments.io_audit('reset','');
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false,'use_timer',false, ...
    'auto_connect',false,'preferences_path','','results_root',output_dir, ...
    'simulation',struct('cache_dir',fullfile(output_dir,'cache'),'test_fixture',true)));
guard=onCleanup(@()finish(fig));
s=state(); select(s.home.position_group,s.home.position_buttons(2)); s=state();
select(s.home.subband_group,s.home.subband_buttons(6)); s=state();
invoke(s.home.h_play); await(@(q)q.first_capture_complete,240); s=state();
invoke(s.home.h_pause); await(@(q)~q.busy && ~q.reference_busy,120); s=state();
assert(numel(s.raw.channels)==1 && strcmp(s.raw.channels.channel,'C2'));
assert(isfield(s.raw,'real_if_analysis') && s.raw.real_if_analysis.valid, ...
    'Real observation must include valid digital I/Q spectra, not only titles.');
assert(s.scope_status.sample_rate_hz>2*37.2e9,'High band mock aliased');
assert(contains(get(s.home.h_wave_title(2),'String'),'数字 I'));
assert(contains(get(s.home.h_spectrum_title(2),'String'),'数字 Q'));
assert(strcmp(get(s.home.h_balance,'Enable'),'off'));
for shape={[1280 720],[1920 1080]}
    sz=shape{1}; set(fig,'Position',[20 20 sz],'Visible','on'); drawnow;
    resize=get(fig,'SizeChangedFcn'); resize(fig,[]); drawnow;
    frame=getframe(fig); imwrite(frame.cdata,fullfile(output_dir,sprintf('rx_real_if_observed_%dx%d.png',sz)));
end
set(fig,'Visible','off');

assert(strcmp(get(s.home.h_single,'Enable'),'on'),get(s.home.h_single,'TooltipString'));
invoke(s.home.h_single); await(@(q)~isempty(q.task) && ~q.task.active && ~q.task_waiting,900); s=state();
assert(s.task.completed==1,s.task.reason);
formal=s.task.rows(cellfun(@(r)ismember(r.role,{'formal','正式'}),s.task.rows)); assert(numel(formal)==1);
r=formal{1}; assert(r.observation.metrics.valid,r.observation.metrics.reason);
assert(r.observation.metrics.pre_bit_count>0);
meta=jsondecode(fileread(r.capture.metadata_path));
assert(strcmp(meta.measurement_context.position,'tx_if') && meta.measurement_context.subband==6);
raw=load(r.capture.raw_path,'raw'); assert(numel(raw.raw.channels)==1);
assert(numel(raw.raw.channels.samples)>numel(r.capture.display_raw.channels.samples));
saved_hash=compute_file_sha256(r.capture.raw_path);
% A changed context can start a raw-only task directly, without an observation.
select(s.home.position_group,s.home.position_buttons(3)); s=state();
select(s.home.subband_group,s.home.subband_buttons(1)); s=state();
set(s.home.h_demod,'Value',0); invoke(s.home.h_demod); invoke(s.home.h_single);
await(@(q)~q.task.active && ~q.task_waiting,300); s=state(); assert(s.task.completed==1,s.task.reason);
select(s.home.position_group,s.home.position_buttons(4)); s=state(); assert(s.second_enabled && isequal(s.channels,{'C3','C4'}));
assert(strcmp(saved_hash,compute_file_sha256(r.capture.raw_path)),'Source capture changed');
audit=msiq.instruments.io_audit('get',''); assert(audit.connections==0 && audit.queries==0 && audit.writes==0,'Real instrument access occurred');
note='PASS: async single IF band 6 observation and demodulation; actual high Fs; digital PSDs; immediate changed context raw capture; IQ return; raw preservation';
finish(fig); clear guard;
    function s=state(), s=getappdata(fig,'rx_workbench_state'); end
    function await(predicate,limit)
        started=tic;
        while ~predicate(state())
            s=state(); assert(toc(started)<limit,'RX_Workbench:WorkflowTimeout','%s',get(s.home.h_status,'String'));
            tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
        end
    end
end
function select(group,button)
set(group,'SelectedObject',button); callback=get(group,'SelectionChangedFcn'); callback(group,struct('NewValue',button));
end
function invoke(h), callback=get(h,'Callback'); callback(h,[]); end
function finish(fig)
if ~isgraphics(fig), return; end
close(fig); started=tic;
while isgraphics(fig) && toc(started)<60
    tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
end
assert(~isgraphics(fig),'RX_Workbench:ReleaseTimeout','模拟后台未完成释放。');
end
