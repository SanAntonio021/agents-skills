function note=validate_if_serial_selection()
%VALIDATE_IF_SERIAL_SELECTION Named ports, source-separated histories, no I/O.
folder=tempname; mkdir(folder); deferred=msiq.validation_artifacts('defer',folder);
fig=figure('Visible','off','Position',[20 20 450 720]); guard=onCleanup(@()delete(fig));
enumerations=0; connections=0; available={'COM3','COM5'};
limits=struct('rf',repmat([0 31.5],6,1),'i',repmat([0 31.5],6,1),'q',repmat([0 31.5],6,1));
serial=struct('port','COM9','baud_rate',115200,'data_bits',8,'parity','none','stop_bits',1, ...
    'flow_control','none','timeout',1,'protocol_version','vendor_v1');
cfg=struct('mode','live','serial',serial,'limits',limits,'runtime',struct('protocol_verified',true));
options=struct('source_mode','measurement','persist',false,'config',cfg,'port_list_fn',@listPorts,'dispatch',@dispatch);
p=msiq.if_board_panel(fig,'rx',options); pguard=onCleanup(@()p.close());
assert(enumerations==1 && connections==0 && strcmp(get(p.controls.port,'Style'),'popupmenu'));
assert(strcmp(p.getConfig().serial.port,'COM9'));
labels=get(p.controls.port,'String'); assert(contains(labels{get(p.controls.port,'Value')},'不可用'));
assert(strcmp(get(p.controls.connect,'Enable'),'off') && all(isnan(p.getDraft().rf)));
invoke(p.controls.connect); assert(connections==0,'Unavailable port was connected.');
available={'COM3','COM9'}; p.refreshPorts();
assert(enumerations==2 && strcmp(p.getConfig().serial.port,'COM9') && strcmp(get(p.controls.connect,'Enable'),'on'));
available={'COM3'}; p.refreshPorts(); assert(strcmp(p.getConfig().serial.port,'COM9'));
assert(strcmp(get(p.controls.connect,'Enable'),'off'),'Unplugged historical port was silently replaced.');
set(p.controls.port,'Value',2); invoke(p.controls.port);
assert(strcmp(p.getConfig().serial.port,'COM3')); invoke(p.controls.connect);
assert(connections==1 && strcmp(get(p.controls.port,'Enable'),'off'));
before=enumerations; p.refreshPorts(); assert(enumerations==before);
assert(strcmp(get(p.controls.refresh_ports,'Enable'),'off'));
invoke(p.controls.connect); assert(~p.getSnapshot().is_open);

% With no selected history, listing a single available port still does not select it.
options.config.serial.port=''; p0=msiq.if_board_panel(fig,'tx',options); g0=onCleanup(@()p0.close());
assert(isempty(p0.getConfig().serial.port) && get(p0.controls.port,'Value')==1);

paths=struct('live',fullfile(folder,'live.mat'),'mock',fullfile(folder,'mock.mat'));
before=enumerations;
mockOptions=struct('source_mode','simulation','persist',true,'record_paths',paths,'port_list_fn',@rejectEnumeration);
m=msiq.if_board_panel(fig,'rx',mockOptions); mg=onCleanup(@()m.close());
assert(enumerations==before && all(m.getDraft().rf==20) && all(m.getDraft().i==20) && all(m.getDraft().q==20));
assert(~m.getSnapshot().is_open && ~isfile(paths.mock));
assert(strcmp(get(m.controls.port,'String'),'模拟串口') || isequal(get(m.controls.port,'String'),{'模拟串口'}));
assert(strcmp(get(m.controls.refresh_ports,'Enable'),'off'));
m.refreshPorts(); invoke(m.controls.connect);
assert(~m.getSnapshot().state_known && ~isfile(paths.mock));
invoke(m.controls.down); saved=load(paths.mock);
assert(strcmp(saved.source_mode,'simulation') && all(saved.settings.rf==20) && ~isfile(paths.live));
invoke(m.controls.plus(1,1)); saved=load(paths.mock); assert(saved.settings.rf(1)==20.5);

legacy=struct('rf',7*ones(1,6),'i',8*ones(1,6),'q',9*ones(1,6));
legacyPath=fullfile(folder,'legacy.mat'); msiq.atomic_save(legacyPath,struct('settings',legacy,'port','COM8'));
liveOptions=options; liveOptions.persist=true; liveOptions.record_path=legacyPath;
liveOptions.config=rmfield(cfg,'serial');
l=msiq.if_board_panel(fig,'rx',liveOptions); lg=onCleanup(@()l.close());
assert(all(l.getDraft().rf==7) && strcmp(l.getConfig().serial.port,'COM8') && ~l.getSnapshot().state_known);
mockLegacy=mockOptions; mockLegacy=rmfield(mockLegacy,'record_paths'); mockLegacy.record_path=legacyPath;
ml=msiq.if_board_panel(fig,'rx',mockLegacy); mlg=onCleanup(@()ml.close());
assert(all(ml.getDraft().rf==20),'Unmarked historical values entered simulation.');
liveOptions.record_path=paths.mock;
blocked=msiq.if_board_panel(fig,'rx',liveOptions); bg=onCleanup(@()blocked.close());
assert(all(isnan(blocked.getDraft().rf)),'Mock history entered a live draft.');
taggedPath=fullfile(folder,'tagged_mock.mat');
msiq.atomic_save(taggedPath,struct('settings',legacy,'config',struct('mode','mock')));
[s,~,~]=msiq.if_board_history(taggedPath,'live','rx'); assert(isempty(fieldnames(s)));
assert(~strcmp(m.getRecordPath(),paths.live));
if ~deferred
    for item=dir(fullfile(folder,'*.mat')).', delete(fullfile(folder,item.name)); end
    rmdir(folder);
end
note='串口只枚举、不可用端口保留、连接锁定、模拟零枚举/20 dB 初值和来源历史隔离通过。';
    function names=listPorts(), enumerations=enumerations+1; names=available; end
    function names=rejectEnumeration(), error('validation:SerialEnumeration','模拟不应枚举本机串口。'); names={}; end %#ok<UNRCH>
    function dispatch(action,payload,completion)
        assert(strcmp(payloadMode(payload),'live'),'validation:Source','Live request lost source mode.');
        if strcmp(action,'board_connect')
            connections=connections+1; assert(strcmp(payload.cfg.serial.port,'COM3'));
            response=struct('ok',true,'snapshot',struct('is_open',true,'state_known',false));
        else
            assert(strcmp(action,'board_close')); response=struct('ok',true,'snapshot',struct('is_open',false,'state_known',false));
        end
        completion(response);
    end
end
function value=payloadMode(payload)
value='live'; if isfield(payload,'cfg'), value=payload.cfg.mode; end
end
function invoke(h)
callback=get(h,'Callback'); callback(h,[]);
end
