function note=validate_rx_capture_setup_gui(output_dir)
%VALIDATE_RX_CAPTURE_SETUP_GUI Capture editor/summary controls without sampling.
if nargin<1,output_dir=msiq.validation_artifacts('directory');end
if ~isfolder(output_dir),mkdir(output_dir);end
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false,'use_timer',false, ...
    'source_mode','simulation','auto_connect',false,'preferences_path','','capture_settings_path',''));
guard=onCleanup(@()finish(fig)); %#ok<NASGU>
s=state();assertNoIO(s);
assert(isempty(s.capture_settings_path));
assert(strcmp(s.if_profile.scope.range_strategy,'computed'));
assert(strcmp(get(s.home.h_profile,'String'),'采集设置'));
assert(strcmp(get(s.home.h_view_result,'String'),'详细结果'));
% A button opens editable controls, not a file picker. Saving invalidates data.
s.raw=struct('marker','old');set(s.home.h_metrics,'String','OLD-METRIC');setappdata(fig,'rx_workbench_state',s);
oldRevision=s.measurement_revision;invoke(s.home.h_profile);
dlg=getappdata(fig,'rx_capture_settings_window');assert(isgraphics(dlg));
c=getappdata(dlg,'rx_capture_settings_controls');assert(isgraphics(c.auto_range));
set(c.auto_range,'Value',0);invoke(c.save);
s=state();assert(~s.if_profile.scope.auto_range_enabled&&s.measurement_revision>oldRevision);
assert(strcmp(s.if_profile.scope.range_strategy,'computed'));
assert(isempty(fieldnames(s.raw))&&~contains(string(get(s.home.h_metrics,'String')),'OLD-METRIC'));
assertNoIO(s);
before=s.if_profile;invoke(s.home.h_profile);dlg=getappdata(fig,'rx_capture_settings_window');
c=getappdata(dlg,'rx_capture_settings_controls');set(c.auto_range,'Value',1);invoke(c.cancel);
s=state();assert(isequaln(before,s.if_profile));
% Simulation owns its paired reference; real reference selection is tested below.
assert(strcmp(get(s.home.h_reference,'Visible'),'off'));
assert(strcmp(get(s.home.h_reference_auto,'Visible'),'off'));
assert(isempty(s.worker)&&~s.connected,'Settings opened instruments');
for size={[1280 720],[1920 1080]}
    wh=size{1};set(fig,'Position',[10 10 wh]);drawnow;
    s=state();stop=getpixelposition(s.home.h_stop,true);
    assert(stop(1)>=0&&stop(2)>=0&&stop(1)+stop(3)<=wh(1)&&stop(2)+stop(4)<=wh(2),'停止按钮不在窗口内');
    handles=[s.home.h_profile s.home.h_range_hint s.home.h_metrics];
    for h=handles,assert(isgraphics(h)&&strcmp(get(h,'Visible'),'on'));end
    print(fig,fullfile(output_dir,sprintf('capture_setup_%dx%d.png',wh(1),wh(2))),'-dpng','-r100');
end
referenceNote=msiq.validate_rx_reference_auto_gui(fullfile(output_dir,'reference_gui'));
note=['capture editor/save/cancel, explicit restore-auto, cleared metrics, two-size controls and zero instrument sessions; ' referenceNote];
    function s=state(),s=getappdata(fig,'rx_workbench_state');end
end
function invoke(h),cb=get(h,'Callback');cb(h,[]);end
function assertNoIO(s)
assert(isempty(s.worker)&&isempty(s.reference_worker)&&~s.connected,'UI-only flow created an instrument/reference worker');
end
function finish(fig)
if isgraphics(fig)
    dlg=getappdata(fig,'rx_capture_settings_window');if ~isempty(dlg)&&isgraphics(dlg),delete(dlg);end
    close(fig);started=tic;while isgraphics(fig)&&toc(started)<30,pause(.05);drawnow;end
end
end
