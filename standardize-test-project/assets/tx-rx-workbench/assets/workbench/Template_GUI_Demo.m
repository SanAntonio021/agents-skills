function report = Template_GUI_Demo(output_dir)
%TEMPLATE_GUI_DEMO Test actual TX/RX controls with mock devices only.
guard=Template_NoHardware(); %#ok<NASGU>
root=fileparts(mfilename('fullpath'));
if nargin<1, output_dir=fullfile(root,'analysis',['template_gui_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]); end
assert(~isfolder(output_dir),'Choose a new output directory.'); mkdir(output_dir);
cfg=msiq.build_config('v2_traditional_wz');
cfg.instrument.awg.mock=true; cfg.instrument.scope.mock=true;
cfg.instrument.awg.mock_idn='KEYSIGHT,M8195A,TEMPLATE,1.0';
cfg.instrument.scope.mock_idn='LECROY,SDA845ZI-A,TEMPLATE,1.0';
cfg.instrument.signal_generator.mock=true; cfg.safety.hardware_enabled=false;
sizes={[1280 720],[1920 1080]}; report=struct('execution_mode','mock','output_dir',output_dir);
for k=1:2
    dim=sizes{k}; msiq.instruments.reset_audit();
    fig=msiq.tx_workbench_app(struct('visible',false,'maximize',false, ...
        'position',[20 20 dim],'synchronous_startup',true,'auto_connect',true, ...
        'persist_parameters',false,'backend_options',struct('cfg_override',cfg), ...
        'parameter_record_path',fullfile(output_dir,'unused_parameters.mat'), ...
        'initial_params',struct('route','pair_a_ch1_ch2','rdiv','DIV4','frame_repetitions',1)));
    cleanup=onCleanup(@() close(fig)); drawnow;
    state=getappdata(fig,'tx_workbench_state');
    if ~state.connected || ~state.plan_valid
        disp(state.awg_status); disp(get(state.ui.normalization,'String'));
        error('template:TxStartup','TX startup failed: connected=%d plan_valid=%d',state.connected,state.plan_valid);
    end
    audit=msiq.instruments.get_audit(); assert(audit.awg_writes==0 && audit.awg_binary_writes==0);
    snapshot(fig,fullfile(output_dir,sprintf('TX_GUI_%dx%d.png',dim)),dim);
    report.tx_mock_audit(k)=audit; clear cleanup;
    fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false, ...
        'position',[20 20 dim],'auto_connect',false,'source_mode','simulation', ...
        'use_timer',false,'preferences_path','','results_root',fullfile(output_dir,sprintf('rx_%d',k)), ...
        'simulation',struct('cache_dir',fullfile(output_dir,'simulation_cache'),'test_fixture',true)));
    cleanup=onCleanup(@() cleanup_rx(fig));
    state=getappdata(fig,'rx_workbench_state');
    select=get(state.home.position_group,'SelectionChangedFcn');
    set(state.home.position_group,'SelectedObject',state.home.position_buttons(1));
    select(state.home.position_group,struct('NewValue',state.home.position_buttons(1)));
    callback=get(state.home.h_play,'Callback'); callback(state.home.h_play,[]);
    started=tic;
    while true
        tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
        state=getappdata(fig,'rx_workbench_state');
        if state.first_capture_complete, break; end
        assert(toc(started)<240,'template:RxStartup','%s',get(state.home.h_status,'String'));
    end
    pause_and_drain(fig); state=getappdata(fig,'rx_workbench_state');
    assert(state.connected && numel(state.raw.channels)==2 && ~state.raw_stale);

    snapshot(fig,fullfile(output_dir,sprintf('RX_GUI_%dx%d.png',dim)),dim);
    report.rx_worker_audits{k}=finish_rx(fig); clear cleanup state callback select tick;
end
assert(getappdata(0,'TemplateHardwareAttempts')==0);
report.hardware_attempts=getappdata(0,'TemplateHardwareAttempts');
save(fullfile(output_dir,'validation.mat'),'report');
fprintf('TEMPLATE_GUI_PASS %s\n',output_dir);
end

function snapshot(fig,p,dim)
% Native capture avoids print's UI scaling and clipped panel captions.
% Keep the figure hidden so the desktop does not shrink oversized windows.
set(fig,'Visible','off','Position',[20 -200 dim]); drawnow;
position=getpixelposition(fig);
assert(isequal(round(position(3:4)),dim),'template:GuiSize', ...
    'Requested %dx%d, actual %gx%g.',dim(1),dim(2),position(3),position(4));
frame=getframe(fig); pixels=frame.cdata;
% Windows HiDPI captures physical pixels; export the tested logical size.
if ~isequal([size(pixels,2) size(pixels,1)],dim)
    [x,y]=meshgrid(linspace(1,size(pixels,2),dim(1)),linspace(1,size(pixels,1),dim(2)));
    scaled=zeros(dim(2),dim(1),3,'uint8');
    for channel=1:3
        scaled(:,:,channel)=uint8(interp2(double(pixels(:,:,channel)),x,y,'linear'));
    end
    pixels=scaled;
end
imwrite(pixels,p);
set(fig,'Visible','off');
info=imfinfo(p); assert(isequal([info.Width info.Height],dim));
pixels=imread(p); assert(std(double(pixels(:)))>10);
end

function audits=finish_rx(fig)
audits={}; if ~isgraphics(fig), return; end
pause_and_drain(fig);
state=getappdata(fig,'rx_workbench_state'); workers={state.worker,state.reference_worker};
close(fig); started=tic;
while isgraphics(fig) && toc(started)<60
    drawnow; pause(.05);
end
assert(~isgraphics(fig),'template:ReleaseTimeout','Simulation worker did not release.');
for k=1:numel(workers)
    worker=workers{k}; if isempty(worker), continue; end
    assert(worker.process.HasExited,'template:WorkerExit','Worker is still running.');
    worker.process.WaitForExit();
    assert(worker.process.ExitCode==0,'template:WorkerExit','Worker exited with code %d.',worker.process.ExitCode);
    p=fullfile(worker.folder,'template_hardware_audit.json');
    assert(isfile(p),'template:WorkerAudit','Missing child-process hardware audit: %s',p);
    evidence=jsondecode(fileread(p)); a=evidence.instrument_audit;
    assert(evidence.guard_active && evidence.hardware_attempts==0 && ...
        a.connections==0 && a.writes==0 && a.queries==0 && a.binary_writes==0, ...
        'template:WorkerHardware','Child process attempted instrument access.');
    evidence.exit_code=worker.process.ExitCode; audits{end+1}=evidence; %#ok<AGROW>
end
assert(numel(audits)==2,'template:WorkerAudit','Both scope and file workers need evidence.');
end
function pause_and_drain(fig)
if ~isgraphics(fig), return; end
s=getappdata(fig,'rx_workbench_state');
if s.close_requested, return; end
callback=get(s.home.h_pause,'Callback'); callback(s.home.h_pause,[]);
started=tic;
while isgraphics(fig)
    s=getappdata(fig,'rx_workbench_state');
    if ~s.busy && ~s.reference_busy && ~s.simulation_preparing, return; end
    assert(toc(started)<120,'template:DrainTimeout','%s',get(s.home.h_status,'String'));
    tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow; pause(.05);
end
end
function cleanup_rx(fig)
% Keep dependencies available if another cleanup has already restored path.
root=fileparts(mfilename('fullpath')); previous=path;
addpath(root,fullfile(root,'code'),fullfile(root,'code','result_management'),fullfile(root,'code','plotting'));
restore=onCleanup(@()path(previous)); %#ok<NASGU>
if isgraphics(fig), finish_rx(fig); end
end