function note=validate_rx_detail_gui(output_dir)
%VALIDATE_RX_DETAIL_GUI Exercise position applicability and persisted routes.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
path=fullfile(output_dir,'detail_preferences.mat');
msiq.rx_view_preferences('save',path,struct('channels',{{'C1','C2'}},'second_enabled',false));
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false,'use_timer',false, ...
    'source_mode','simulation','auto_connect',false,'preferences_path',path));
guard=onCleanup(@()finish(fig)); %#ok<NASGU>
s=state(); assert(s.channel_selection_explicit && ~s.second_enabled);
assert_disabled();
select(2); s=state(); assert(strcmp(s.channels{1},'C1') && ~s.second_enabled,'Explicit existing channel was replaced');
select(1); s=state(); assert(~s.second_enabled && strcmp(s.channels{1},'C1'));
assert(strcmp(get(s.home.subband_group,'Visible'),'off'));
assert(~isfield(msiq.rx_measurement_context('awg_direct',6),'subband'));
assert_hidden_subband_rejected();
assert_disabled();
for pos=2:3
    select(pos); s=state(); assert(strcmp(get(s.home.subband_group,'Visible'),'on')); assert_disabled();
end
select(4); s=state(); assert(s.home.board.isApplicable());
channel(1,3); channel(2,4); s=state(); assert(s.second_enabled);
channel(2,5); s=state(); assert(~s.second_enabled);
revision=s.measurement_revision; channel(2,3); s=state();
assert(~s.second_enabled && get(s.home.h_ch2,'Value')==5 && s.measurement_revision==revision,'Rejected duplicate enabled/displayed a disabled second channel');
select(5); channel(1,2); channel(2,4);
select(4); s=state(); assert(isequal(s.channels,{'C3','C4'}) && ~s.second_enabled,'Position second-channel state not restored');
select(5); s=state(); assert(isequal(s.channels,{'C2','C4'}) && s.second_enabled);
% A no-op must not clear an existing display or advance the revision.
s.raw=struct('marker','same-selection'); set(s.home.h_metrics,'String','TEST-METRIC'); setappdata(fig,'rx_workbench_state',s);
rev=s.measurement_revision; select(5); s=state();
assert(s.measurement_revision==rev && isfield(s.raw,'marker') && strcmp(get(s.home.h_metrics,'String'),'TEST-METRIC'));
select(4); s=state(); assert(isempty(fieldnames(s.raw)) && ~contains(get(s.home.h_metrics,'String'),'TEST-METRIC'));
% Pending command rejects and restores the actual selected radio.
s.control_pending=struct('handle',s.home.h_ch1,'key','fixture','value',1,'revision',0); setappdata(fig,'rx_workbench_state',s);
assert_hidden_subband_rejected();
select(1); s=state(); assert(strcmp(s.measurement_position,'rx_if') && get(s.home.position_group,'SelectedObject')==s.home.position_buttons(4));
s.control_pending=struct('handle',{},'key',{},'value',{},'revision',{}); setappdata(fig,'rx_workbench_state',s);
select(1); s=state(); assert(strcmp(s.measurement_position,'awg_direct')); assert_disabled();
assert(isempty(s.worker) && isempty(s.reference_worker) && ~s.connected,'Selection opened an instrument worker');
p=msiq.rx_view_preferences('load',path);
assert(p.version==3 && p.channel_selection_explicit && ~p.measurement_second_enabled.rx_if && p.measurement_second_enabled.rx_if_thz);
old=msiq.rx_view_preferences('save','',struct('channels',{{'C3','C4'}}));
assert(old.channel_selection_explicit && old.second_enabled && isempty(old.measurement_position));
implicit=msiq.rx_view_preferences('save','',struct('channels',{{'C3','C4'}},'channel_selection_explicit',false));
assert(~implicit.channel_selection_explicit);
invalid=msiq.rx_view_preferences('save','',struct('second_enabled',nan,'measurement_second_enabled',struct('rx_if',2)));
assert(invalid.second_enabled && ~isfield(invalid.measurement_second_enabled,'rx_if'));
note='PASS: disabled actual controls/callbacks; AWG no subband; explicit first channel; per-position second enable; no-op; stale metrics; queued switch rejection; preference migration; zero sessions';
    function s=state(), s=getappdata(fig,'rx_workbench_state'); end
    function select(index)
        s=state(); set(s.home.position_group,'SelectedObject',s.home.position_buttons(index));
        cb=get(s.home.position_group,'SelectionChangedFcn'); cb(s.home.position_group,struct('NewValue',s.home.position_buttons(index)));
    end
    function channel(index,value)
        s=state(); hs=[s.home.h_ch1 s.home.h_ch2]; h=hs(index); set(h,'Value',value); cb=get(h,'Callback'); cb(h,[]);
    end
    function assert_hidden_subband_rejected()
        before=state(); h=before.home.board.controls.selection; set(h,'Value',mod(before.measurement_subband,6)+1);
        cb=get(h,'Callback'); cb(h,[]); after=state();
        assert(after.measurement_subband==before.measurement_subband && after.measurement_revision==before.measurement_revision && ...
            get(h,'Value')==before.measurement_subband,'Hidden board selector bypassed applicability/task gate');
    end
    function assert_disabled()
        s=state(); c=s.home.board.controls;
        handles=[c.port c.refresh_ports c.config c.connect c.down c.edits(:)' c.plus(:)' c.minus(:)'];
        for h=handles, assert(strcmp(get(h,'Enable'),'off'),'Board control is actionable outside RX IF'); end
        before=s.home.board.getSnapshot(); cb=get(c.connect,'Callback'); cb(c.connect,[]);
        after=s.home.board.getSnapshot(); assert(isequaln(before,after),'Direct disabled callback performed board I/O');
        assert(~s.home.board.isApplicable());
    end
end
function finish(fig)
if isgraphics(fig), close(fig); end
end
