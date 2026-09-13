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
sizes={[1100 700],[1500 900]}; report=struct('execution_mode','mock','output_dir',output_dir);
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
    io=msiq.instruments.mock_rx_scope_io(struct('log_path',fullfile(output_dir,sprintf('rx_mock_%d.log',k)), ...
        'capture_delay_s',0,'record_count',100000,'timebase_s',125e-9,'observation_mode',true, ...
        'failure_path',fullfile(output_dir,'unused_failure.txt')));
    fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false, ...
        'position',[20 20 dim],'synchronous_startup',true,'auto_connect',true, ...
        'use_timer',false,'asynchronous',false,'find_reference',false, ...
        'preferences_path','','config',msiq.rx_mock_config(),'io',io));
    cleanup=onCleanup(@() close(fig));
    tick=getappdata(fig,'rx_workbench_tick'); tick([],[]); drawnow;
    state=getappdata(fig,'rx_workbench_state');
    if isfield(state,'last_exception'), rethrow(state.last_exception); end
    assert(state.connected && isfield(state.raw,'channels') && numel(state.raw.channels)==2, ...
        char(string(get(state.home.h_status,'String'))));
    assert(~state.raw_stale);
    snapshot(fig,fullfile(output_dir,sprintf('RX_GUI_%dx%d.png',dim)),dim);
    clear cleanup;
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
