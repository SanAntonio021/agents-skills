function note=validate_rx_reference_auto_gui(folder)
%VALIDATE_RX_REFERENCE_AUTO_GUI Actual file-worker linking, no instrument sessions.
if nargin<1, folder=msiq.validation_artifacts('directory'); end
if ~isfolder(folder), mkdir(folder); end
[~,location]=fileattrib(folder);folder=location.Name;
cfg=msiq.rx_mock_config(); cfg.project_root=msiq.project_root(); cfg.results.root=folder;
io=struct('open',@forbidden,'query',@forbidden,'write',@forbidden,'capture',@forbidden,'close',@(~)[]);
link=struct('source','simulation','store_path',fullfile(folder,'links'),'device','mock_awg');
bundle=struct('route',struct('scope_channels',{{'C3','C4'}},'awg_channels',[3 4],'waveform_columns',[3 4]), ...
    'desired',struct(),'tx_ref',struct('frame',struct('reference_payload_policy','metrics_only','occupied_bandwidth_hz',3e9)), ...
    'execution',struct('status','applied'),'reference_payload_policy','metrics_only', ...
    'dsp_config',struct('waveform',struct('architecture','single_complex_stream','occupied_bandwidth_hz',3e9,'symbol_rate_hz',2e9,'if_center_hz',0)));
first=fullfile(folder,'first.mat'); save(first,'bundle'); link.reference_path=first;
msiq.tx_reference_link('publish',cfg.project_root,link);
f=msiq.rx_workbench_app(struct('config',cfg,'io',io,'visible',false,'auto_connect',false, ...
    'use_timer',false,'preferences_path','','capture_settings_path','','reference_link_store_path',link.store_path));
g=onCleanup(@()finish(f)); %#ok<NASGU>
s=state(); s.channels={'C1','C2'};s.measurement_position='awg_direct';setappdata(f,'rx_workbench_state',s);
await(@(s)strcmp(s.reference_bundle,first)); s=state(); assert(~s.reference_manual&&isempty(s.worker)&&~s.connected);
% New successful TX follows automatically and invalidates current metrics.
s.raw=struct('old',true);set(s.home.h_metrics,'String','OLD');setappdata(f,'rx_workbench_state',s);
bundle.dsp_config.waveform.symbol_rate_hz=1e9; second=fullfile(folder,'second.mat');save(second,'bundle');link.reference_path=second;
msiq.tx_reference_link('publish',cfg.project_root,link); await(@(s)strcmp(s.reference_bundle,second));s=state();
assert(isempty(fieldnames(s.raw))&&~contains(string(get(s.home.h_metrics,'String')),'OLD'));
% Manual pin stays despite TX changes; explicit reset follows latest.
s.reference_manual=true;s.reference_path=first;s.reference_bundle=first;setappdata(f,'rx_workbench_state',s);
for k=1:3,tick();end;s=state();assert(strcmp(s.reference_bundle,first));
cb=get(s.home.h_reference_auto,'Callback');cb(s.home.h_reference_auto,[]);await(@(s)strcmp(s.reference_bundle,second));
msiq.tx_reference_link('invalidate',cfg.project_root,link);await(@(s)isempty(s.reference_bundle)&&~s.reference_pending);
s=state();assert(~isempty(s.reference_info.error)&&isempty(s.worker)&&~s.connected);
finish(f);clear g; % A release failure must fail this test, not become an onCleanup warning.
note='自动关联/跟随新发送/手动锁定/恢复自动/发送失效清空，真实文件后台且零仪器会话';
    function s=state(),s=getappdata(f,'rx_workbench_state');end
    function tick()
        s=state();s.reference_checked_at=-Inf;setappdata(f,'rx_workbench_state',s);
        cb=getappdata(f,'rx_workbench_tick');cb([],[]);drawnow;
    end
    function await(test)
        t=tic;while true,tick();if test(state()),return;end;q=state();assert(toc(t)<90,'Reference GUI timeout: root=%s path=%s info=%s',q.cfg.project_root,q.reference_bundle,jsonencode(q.reference_info));pause(.05);end
    end
end
function forbidden(varargin),error('validation:HardwareAccess','Instrument access forbidden');end
function finish(f)
if ~isgraphics(f),return;end
close(f);t=tic;while isgraphics(f)&&toc(t)<60,cb=getappdata(f,'rx_workbench_tick');cb([],[]);pause(.05);drawnow;end
assert(~isgraphics(f),'File worker failed to close');
end
