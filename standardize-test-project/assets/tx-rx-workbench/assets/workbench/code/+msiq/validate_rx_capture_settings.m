function note=validate_rx_capture_settings(output_dir)
%VALIDATE_RX_CAPTURE_SETTINGS Real controls, trust preservation and local files.
if nargin<1,output_dir=msiq.validation_artifacts('directory');end
if ~isfolder(output_dir),mkdir(output_dir);end
base=msiq.if_workbench_config(struct('mode','live'));opts=struct('source_mode','live');
assert(base.scope.auto_range_enabled&&base.scope.target_divisions==7&&base.scope.edge_margin_divisions==.5);
assert(isnan(base.scope.max_adjustments)&&isempty(base.scope.ranges_vdiv));
path=fullfile(output_dir,'capture_settings.mat');
assert(~strcmp(msiq.rx_capture_settings('path',base,output_dir,opts), ...
    msiq.rx_capture_settings('path',base,output_dir,struct('source_mode','simulation'))));
p=base;p.scope.auto_range_enabled=false;p.scope.ranges_vdiv=[.1 .02 .05];p.scope.max_adjustments=4;p.policy.settle_s=.1;
msiq.rx_capture_settings('save',p,path,opts);q=msiq.rx_capture_settings('load',base,path,opts);
assert(~q.scope.auto_range_enabled&&isequal(q.scope.ranges_vdiv,[.02 .05 .1]));
jsonPath=fullfile(output_dir,'settings.json');msiq.rx_capture_settings('export',p,jsonPath,opts);
q=msiq.rx_capture_settings('import',base,jsonPath,opts);assert(isnan(q.policy.balance_step_db));
profile=p;legacy=fullfile(output_dir,'legacy.mat');save(legacy,'profile');
q=msiq.rx_capture_settings('import',base,legacy,opts);assert(q.scope.max_adjustments==4);
fake=base;fake.scope.fresh.verified=true;
q=msiq.rx_capture_settings('normalize',base,fake,opts);assert(~q.scope.fresh.verified);
trusted=base;trusted.scope.ranges_vdiv=[.02 .05 .1];trusted.scope.headroom=1.25;trusted.scope.fresh.verified=true;trusted.scope.fresh.start_command='START';
q=msiq.rx_capture_settings('normalize',trusted,trusted,opts);assert(q.scope.fresh.verified);
changed=trusted;changed.scope.fresh.start_command='OTHER';
q=msiq.rx_capture_settings('normalize',trusted,changed,opts);assert(~q.scope.fresh.verified);
mock=msiq.if_workbench_config();rejected=false;
try,msiq.rx_capture_settings('normalize',base,mock,opts);catch,rejected=true;end
assert(rejected);
saved=[];
dlg=msiq.rx_capture_settings_dialog([],trusted,struct('visible','off','preferences_path',path,'onSave',@received));
guard=onCleanup(@()finish(dlg)); %#ok<NASGU>
c=getappdata(dlg,'rx_capture_settings_controls');
assert(strcmp(get(c.fresh_status,'Style'),'text'));
assert(~isfield(c.edits,'scope_sample_rate_hz')&&~isfield(c.edits,'scope_window_s'));
assert(strcmp(get(c.device_window,'Visible'),'off'));
assert(numel(get(c.tabs,'Children'))==3);
set(c.edits.policy_settle_s,'String','250');
assert(~isfield(c.edits,'scope_ranges_vdiv')&&~isfield(c.edits,'scope_headroom'));
set(c.edits.scope_sample_rate_tolerance,'String','2');
set(c.edits.scope_window_tolerance,'String','3');
set(c.edits.scope_fresh_poll_s,'String','50');
set(c.edits.scope_max_adjustments,'String','3');invoke(c.arrows.scope_max_adjustments(1));
assert(strcmp(get(c.edits.scope_max_adjustments,'String'),'4'));
invoke(c.device);assert(strcmp(get(c.device_window,'Visible'),'on'));

set(c.edits.scope_target_divisions,'String','8');invoke(c.save);
assert(isgraphics(dlg)&&isempty(saved),'Invalid margin accepted');
set(c.edits.scope_target_divisions,'String','7');
set(c.edits.scope_fresh_start_command,'String','ALTERED');set(c.auto_range,'Value',0);invoke(c.save);
assert(~isgraphics(dlg)&&~saved.scope.fresh.verified&&~saved.scope.auto_range_enabled);
assert(~isgraphics(c.device_window));
assert(saved.policy.settle_s==.25&&saved.scope.fresh.poll_s==.05);
assert(isequal(saved.scope.ranges_vdiv,[.02 .05 .1])&&saved.scope.headroom==1.25);
assert(saved.scope.sample_rate_tolerance==.02&&saved.scope.window_tolerance==.03);
assert(saved.scope.max_adjustments==4);
q=msiq.rx_capture_settings('load',trusted,path,opts);assert(~q.scope.fresh.verified);
dlg=msiq.rx_capture_settings_dialog([],base,struct('visible','off','preferences_path','','onSave',@received,'balance_applicable',false));
importer=getappdata(dlg,'rx_capture_settings_import');importer(jsonPath);
c=getappdata(dlg,'rx_capture_settings_controls');assert(get(c.auto_range,'Value')==0);
assert(strcmp(get(c.edits.scope_max_adjustments,'Enable'),'off'));
assert(strcmp(get(c.edits.scope_target_divisions,'Enable'),'on'));
assert(strcmp(get(c.edits.policy_balance_step_db,'Enable'),'off'));
assert(strcmp(get(c.edits.policy_settle_s,'Enable'),'off'));
setter=getappdata(dlg,'rx_capture_settings_applicability');setter(true);
assert(strcmp(get(c.edits.policy_balance_step_db,'Enable'),'on'));
assert(strcmp(get(c.edits.policy_settle_s,'Enable'),'on'));
exporter=getappdata(dlg,'rx_capture_settings_export');
exported=fullfile(output_dir,'legacy_hidden_roundtrip.mat');exporter(exported);
roundtrip=msiq.rx_capture_settings('load',base,exported,opts);
assert(isequal(roundtrip.scope.ranges_vdiv,[.02 .05 .1]));
assert(~isfield(c.edits,'scope_ranges_vdiv')&&~isfield(c.edits,'scope_headroom'));
invoke(c.cancel);assert(~isgraphics(dlg));
note='capture settings MAT/JSON persistence, source isolation, trust gate and real controls; zero instrument I/O';
    function received(p),saved=p;end
end
function invoke(h),cb=get(h,'Callback');cb(h,[]);end
function finish(h),if isgraphics(h),delete(h);end;end
