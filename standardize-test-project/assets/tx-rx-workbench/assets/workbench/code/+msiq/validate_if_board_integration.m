function note=validate_if_board_integration()
%VALIDATE_IF_BOARD_INTEGRATION No serial constructor is reached by mock tests.
limits=struct('rf',repmat([1 30],6,1),'i',repmat([1 30],6,1),'q',repmat([1 30],6,1));
settings=struct('rf',2:7,'i',8:13,'q',14:19);
cfg=struct('mode','mock','role','tx','limits',struct('rf',limits.rf));
tx=msiq.instruments.IfBoard(cfg); cleanup=onCleanup(@()tx.close());
assert(~tx.IsOpen && isempty(tx.History)); tx.open(); assert(~tx.StateKnown);
tx.initialize(struct('rf',settings.rf));
assert(numel(tx.History)==1 && tx.History(1).frame(3)==1);
tx.setAttenuation('rf',3,4.5);
assert(isequal(tx.History(end).frame(4:9),uint8([4 6 9 10 12 14])));
assert(all(isnan(tx.Readback.rf)) && strcmp(tx.History(end).outcome,'sent_not_readback'));
failed=false; try tx.setIQ(1,2,3); catch, failed=true; end; assert(failed);
cfg.role='rx'; cfg.limits=limits;
rx=msiq.instruments.IfBoard(cfg); cleanup2=onCleanup(@()rx.close()); rx.open(); rx.initialize(settings);
assert(isequal(arrayfun(@(x)double(x.frame(3)),rx.History),[2 1 4 6]));
assert(isequal(rx.History(1).frame(4:9),zeros(1,6,'uint8')));
rx.setIQ(1,7.5,14.5);
assert(isequal(arrayfun(@(x)double(x.frame(3)),rx.History(end-1:end)),[6 4]));
rx.cancel(); assert(~rx.StateKnown); rx.initialize(settings); assert(rx.StateKnown);
cfg.fail_on_write=3;
broken=msiq.instruments.IfBoard(cfg); cleanup3=onCleanup(@()broken.close()); broken.open();
failed=false; try broken.initialize(settings); catch, failed=true; end
assert(failed && ~broken.StateKnown && numel(broken.History)==3);
assert(strcmp(broken.History(end).outcome,'unknown_after_failure'));
failed=false; try broken.setAttenuation('rf',1,3); catch, failed=true; end
assert(failed && numel(broken.History)==3);
broken.initialize(settings); assert(broken.StateKnown && numel(broken.History)==7);
assert(msiq.if_board_quantize(10.25,[0 31.5])==10.5);
assert(msiq.if_board_quantize(-100,[2.2 10.7])==2.5);
assert(msiq.if_board_quantize(100,[2.2 10.7])==10.5);
failed=false; try msiq.if_board_quantize('',[0 31.5]); catch, failed=true; end; assert(failed);
f=figure('Visible','off','Position',[1 1 450 720]); cleanup4=onCleanup(@()delete(f));
options=struct('offline_test',true,'persist',false,'initial_settings',settings);
p=msiq.if_board_panel(f,'rx',options); panelCleanup=onCleanup(@()p.close());
assert(~p.getSnapshot().is_open);
feval(get(p.controls.connect,'Callback'),[],[]);
assert(p.getSnapshot().is_open && ~p.getSnapshot().state_known);
feval(get(p.controls.down,'Callback'),[],[]);
assert(p.getSnapshot().state_known);
feval(get(p.controls.plus(1,2),'Callback'),[],[]);
assert(p.getSnapshot().sent.i(1)==8.5);
feval(get(p.controls.edits(1,2),'Callback'),p.controls.edits(1,2),[]);
assert(p.getSnapshot().sent.i(1)==8.5);
p.setBusy(true); assert(strcmp(get(p.controls.plus(1),'Enable'),'off'));
% A failed multi-frame group must not replace the last complete saved setup.
folder=tempname; mkdir(folder); deferred=msiq.validation_artifacts('defer',folder);
record=fullfile(folder,'rx_last.mat'); msiq.atomic_save(record,struct('settings',settings,'source_mode','mock'));
options.persist=true; options.record_path=record; options.config=cfg;
options.initial_settings=struct('rf',10*ones(1,6),'i',11*ones(1,6),'q',12*ones(1,6));
p2=msiq.if_board_panel(f,'rx',options); cleanup5=onCleanup(@()p2.close());
feval(get(p2.controls.connect,'Callback'),[],[]); feval(get(p2.controls.down,'Callback'),[],[]);
saved=load(record); assert(isequal(saved.settings,settings) && ~p2.getSnapshot().state_known);
feval(get(p2.controls.down,'Callback'),[],[]);
saved=load(record); assert(isequal(saved.settings.rf,10*ones(1,6)));
feval(get(p2.controls.connect,'Callback'),[],[]); assert(~p2.getSnapshot().is_open);
assert(contains(get(p2.controls.status,'String'),'已断开'));
if ~deferred, delete(record); rmdir(folder); end
% A real-labelled panel must never fall through to the adapter's mock default.
p3=msiq.if_board_panel(f,'rx',struct('persist',false,'config',struct(),'port_list_fn',@()strings(0)));
cleanup6=onCleanup(@()p3.close());
assert(strcmp(p3.getConfig().mode,'live') && ~p3.getSnapshot().is_open);
assert(strcmp(get(p3.controls.connect,'Enable'),'off'));
failed=false;
try msiq.if_board_panel(f,'rx',struct('persist',false,'config',struct('mode','mock')));
catch err, failed=strcmp(err.identifier,'msiq:ifboard:modeMismatch'); end
assert(failed);
valid=struct('limits',limits,'initial_state',settings);
p3.loadConfig(valid); assert(strcmp(p3.getConfig().mode,'live'));
beforeConfig=p3.getConfig(); beforeDraft=p3.getDraft();
invalid=valid; invalid.mode='mock';
failed=false; try p3.loadConfig(invalid); catch, failed=true; end
assert(failed && isequaln(p3.getConfig(),beforeConfig) && isequaln(p3.getDraft(),beforeDraft));
invalid=valid; invalid.limits.i=[1 2]; invalid.initial_state.rf=10*ones(1,6);
failed=false; try p3.loadConfig(invalid); catch, failed=true; end
assert(failed && isequaln(p3.getConfig(),beforeConfig) && isequaln(p3.getDraft(),beforeDraft));
mockOptions=struct('persist',false,'offline_test',true,'config',struct('mode','live'));
p4=msiq.if_board_panel(f,'tx',mockOptions); cleanup7=onCleanup(@()p4.close());
assert(strcmp(p4.getConfig().mode,'mock'));
note='TX/RX role initialization, six-value frames, ordering, partial recovery, quantization and real mock controls passed.';
end
