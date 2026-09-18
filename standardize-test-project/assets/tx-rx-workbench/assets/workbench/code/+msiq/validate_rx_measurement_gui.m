function note=validate_rx_measurement_gui(output_dir)
%VALIDATE_RX_MEASUREMENT_GUI Real controls, zero instrument sessions.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
path=fullfile(output_dir,'measurement_preferences.mat');
if isfile(path), delete(path); end
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false,'use_timer',false, ...
    'auto_connect',false,'preferences_path',path)); guard=onCleanup(@()finish(fig));
s=getappdata(fig,'rx_workbench_state');
assert(isempty(s.measurement_position) && isempty(get(s.home.position_group,'SelectedObject')));
assert(isempty(s.worker) && isempty(s.reference_worker) && ~s.connected);
assert(strcmp(get(s.home.board.controls.selection,'Visible'),'off'));
original_channels=s.channels;
for position=1:5
    select_position(position); s=getappdata(fig,'rx_workbench_state');
    assert(sum(arrayfun(@(h)get(h,'Value'),s.home.position_buttons))==1);
    assert(isempty(s.worker) && isempty(s.reference_worker) && ~s.connected,'Selection performed I/O');
    is_if=ismember(position,[2 3]);
    assert(s.second_enabled==~is_if);
    if is_if, assert(strcmp(s.channels{1},'C2') && strcmp(get(s.home.h_ch2,'Enable'),'off')); end
    assert(strcmp(get(s.home.h_if_center,'Visible'),onoff(is_if)));
    if position==1, assert(strcmp(get(s.home.subband_group,'Visible'),'off')); continue; end
    for band=1:6
        cb=get(s.home.subband_group,'SelectionChangedFcn'); set(s.home.subband_group,'SelectedObject',s.home.subband_buttons(band));
        cb(s.home.subband_group,struct('NewValue',s.home.subband_buttons(band))); s=getappdata(fig,'rx_workbench_state');
        assert(s.measurement_subband==band && s.home.board.getSelection()==band);
        assert(sum(arrayfun(@(h)get(h,'Value'),s.home.subband_buttons))==1);
        assert(isequal(get(s.home.board.controls.edits(band,1),'BackgroundColor'),[.86 .94 1]));
    end
end
select_position(1); s=getappdata(fig,'rx_workbench_state'); assert(isequal(s.channels,original_channels));
select_position(2); s=getappdata(fig,'rx_workbench_state');
for shape={[1280 720],[1920 1080]}
    sz=shape{1}; set(fig,'Position',[20 20 sz],'Visible','on'); drawnow;
    cb=get(fig,'SizeChangedFcn'); cb(fig,[]); s=getappdata(fig,'rx_workbench_state');
    for h=[s.home.h_stop s.home.h_single s.home.h_repeat]
        box=getpixelposition(h,true); assert(all(box(1:2)>=0)&&box(1)+box(3)<=sz(1)&&box(2)+box(4)<=sz(2));
    end
    for h=s.home.position_buttons
        extent=get(h,'Extent'); box=get(h,'Position'); assert(extent(3)<box(3),'Position label truncated');
    end
    plotbox=getpixelposition(s.home.plot_panel,true); slider=s.home.scroll;
    set(slider,'Value',get(slider,'Max')); cb=get(slider,'Callback'); cb(slider,[]); drawnow;
    imwrite(getframe(fig).cdata,fullfile(output_dir,sprintf('rx_measurement_top_%dx%d.png',sz)));
    set(slider,'Value',get(slider,'Min')); cb(slider,[]);
    assert(isequal(plotbox,getpixelposition(s.home.plot_panel,true)),'Scroll resized plots');
end
% A historical record without a cached preview must never retain another plot.
s=getappdata(fig,'rx_workbench_state'); s.raw=struct('marker','unrelated record'); setappdata(fig,'rx_workbench_state',s);
saved=struct('role','正式','capture',struct('run_dir',output_dir,'source_mode','simulation', ...
    'measurement_context',msiq.rx_measurement_context('thz_if',2)),'observation',struct());
setappdata(s.home.h_history,'records',{saved}); set(s.home.h_history,'String',{'历史记录'},'Value',1);
cb=get(s.home.h_history,'Callback'); cb(s.home.h_history,[]); s=getappdata(fig,'rx_workbench_state');
assert(isempty(fieldnames(s.raw)) && contains(get(s.home.h_wave_info(1),'String'),'详细结果'));
assert(contains(get(s.home.h_history,'TooltipString'),'太赫兹下变频') && contains(get(s.home.h_metrics,'TooltipString'),'子带 2'));
record=msiq.rx_view_preferences('load',path);
assert(strcmp(record.measurement_position,'tx_if') && record.measurement_subband==6);
assert(isequal(record.measurement_routes.awg_direct,original_channels));
old=msiq.rx_view_preferences('save','',struct('channels',{{'C3','C4'}}));
assert(isempty(old.measurement_position),'Old preferences must not invent measurement position');
note='PASS: five positions and six subbands; single physical channel; shared row highlight; zero sessions; preferences; 1280/1920 layout';
    function select_position(index)
        s=getappdata(fig,'rx_workbench_state'); cb=get(s.home.position_group,'SelectionChangedFcn');
        set(s.home.position_group,'SelectedObject',s.home.position_buttons(index));
        cb(s.home.position_group,struct('NewValue',s.home.position_buttons(index)));
    end
end
function value=onoff(flag)
value='off'; if flag, value='on'; end
end
function finish(fig)
if isgraphics(fig), close(fig); end
end
