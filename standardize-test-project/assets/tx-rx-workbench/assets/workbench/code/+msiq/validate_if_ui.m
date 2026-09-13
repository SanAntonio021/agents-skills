function report = validate_if_ui()
%VALIDATE_IF_UI Hidden window, no instrument access, retained profile and mock.
before = msiq.instruments.get_audit();
input = struct('stage','rx_iq','mode','mock', ...
    'wiring',struct('id','UI_OFFLINE_TEST','notes','preserve this'), ...
    'custom_retained',struct('value',42));
f = msiq.if_workbench_app(struct('Visible','off','profile',input));
guard = onCleanup(@() deleteIfValid(f));
assert(strcmp(f.Visible,'off'));
d = f.UserData;
assert(isa(d.wiring,'matlab.ui.control.Label')&&isa(d.confirmed,'matlab.ui.control.Label'));
assert(isequal(d.left.RowHeight([5 7 9]),{0,0,0}));
p = d.getProfile();
assert(strcmp(p.mode,'mock'));
assert(p.custom_retained.value==42 && strcmp(p.wiring.notes,'preserve this'));
assert(isequal(p.scope.channels,{'C3','C4'}));
d.confirmWiring();
p=d.getProfile(); stamp=p.wiring.confirmed_at; id=p.wiring.id;
assert(~isempty(stamp));
d.confirmWiring(); p=d.getProfile();
assert(strcmp(p.wiring.id,id),'Reconfirmation must preserve wiring identity for resume.');
d.awgPair.Value='pair_b_ch3_ch4';
d.scopeOne.Value='C1'; d.scopeTwo.Value='C2'; d.wiringChanged();
p=d.getProfile();
assert(isempty(p.wiring.confirmed_at)&&isempty(p.wiring.id));
assert(strcmp(p.tx_options.route,'pair_b_ch3_ch4')&&isequal(p.scope.channels,{'C1','C2'}));
d.confirmWiring(); p=d.getProfile();
assert(~isempty(p.wiring.id)&&~isempty(p.wiring.confirmed_at));
d.scopeTwo.Value='C1'; d.wiringChanged();
rejected=false;
try, d.getProfile(); catch err, rejected=strcmp(err.identifier,'msiq:if:Wiring'); end
assert(rejected,'Duplicate scope inputs must be rejected.');
d.scopeTwo.Value='C2'; d.wiringChanged(); d.confirmWiring();
d.runAction('plan');
out = f.UserData.lastResult;
assert(isstruct(out) && isfield(out,'blockers'));
afterPlan = msiq.instruments.get_audit();
assert(isequal(before,afterPlan),'UI startup/plan accessed instruments.');
d.mode.Value='live';
d.runAction('manual_capture'); % Mock fixture must not become a live profile.
assert(isequal(out,f.UserData.lastResult));
assert(isequal(before,msiq.instruments.get_audit()));
d.mode.Value='mock';
d.scanFields{1,1}.Value='bad scan input';
d.refreshReadiness();
assert(strcmp(d.captureButton.Enable,'on'),'Single capture must not require scan inputs.');
d.showAwgPlan(struct('levels',struct('amplitude_vpp',[.2 .2])));
awgBefore=d.awgPlanBox.Value;
d.refreshReadiness();
assert(isequal(awgBefore,d.awgPlanBox.Value),'Scan readiness replaced AWG plan.');
d.ampI.Value='0.2'; d.txChanged();
assert(~isequal(awgBefore,d.awgPlanBox.Value),'AWG draft edit must invalidate plan display.');
d.ampI.Value='invalid draft';
d.refreshReadiness();
assert(strcmp(d.captureButton.Enable,'on'),'Capture must not depend on an unsent AWG draft.');
d.runAction('manual_capture');
out = f.UserData.lastResult;
assert(strcmp(out.status,'completed'),strjoin(cellfun(@(e)e.message,out.errors,'UniformOutput',false),'; '));
assert(numel(out.observations)==1);
assert(strcmp(out.profile.mode,'mock'));
assert(isequal(out.profile.scope.channels,{'C1','C2'}));
shown=msiq.if_ui_present(out);
assert(numel(shown.metrics)==4&&contains(shown.metrics{2},'统计比特数'));
invalid=out; invalid.observations{1}.metrics.pre_bit_count=0;
shown=msiq.if_ui_present(invalid);
assert(any(contains(shown.metrics,'无效')));
tx=out; tx.profile.stage='tx_if'; shown=msiq.if_ui_present(tx);
assert(any(contains(shown.metrics,'本阶段不计算解调指标')));
shown=msiq.if_ui_present(struct('status','stopped','state',struct('outputs',[0 0 0 1])));
assert(contains(shown.state,'关闭状态未确认'));
probe=msiq.if_workbench('manual_capture',struct('profile',out.profile, ...
    'progress_callback',@(~) error('msiq:if:UITest','Injected display failure')));
assert(strcmp(probe.status,'completed')&&probe.shutdown.awg_off_verified);
statusBefore=d.status.Text; d.refreshReadiness();
assert(strcmp(statusBefore,d.status.Text),'Readiness replaced completed status.');
d.pre.Value='22'; d.boardEdited();
assert(contains(d.boardState.Text,'尚未下发'));
boardBefore=d.boardState.Text;
% Invalid current drafts must not prevent loading a saved run.
d.runPath.Value=out.run_dir;
d.scopeTwo.Value=d.scopeOne.Value; d.ampI.Value='invalid amplitude';
d.runAction('replay');
replayed=f.UserData.lastResult;
assert(isfield(replayed,'replay')&&replayed.replay,'Replay depends on unrelated current fields.');
assert(strcmp(boardBefore,d.boardState.Text),'Historical board state replaced current board state.');
d.scopeTwo.Value='C2'; d.ampI.Value='0.2'; d.scanFields{1,1}.Value='';
% Selection changes metrics without changing the saved observations.
mock=out; o=mock.observations{1}; o.attempt=2; o.power_dbv2=[-10 -12];
mock.observations{2}=o;
data=f.UserData; data.lastResult=mock; f.UserData=data; d.present(mock);
assert(d.recordPicker.Value==2);
d.recordPicker.Value=1; d.recordPicker.ValueChangedFcn([],[]);
first=d.metricsBox.Value;
d.recordPicker.Value=2; d.recordPicker.ValueChangedFcn([],[]);
assert(~isequal(first,d.metricsBox.Value));
selectedMetrics=d.metricsBox.Value;
d.present(struct('status','awaiting_apply'));
assert(d.recordPicker.Value==2&&isequal(selectedMetrics,d.metricsBox.Value), ...
    'Control plans must preserve the displayed measurement.');
bad=out.profile; bad.scope.channels={'C1','C1'};
rejected=false;
try, msiq.if_workbench_validate_profile(bad,'manual_capture');
catch err, rejected=strcmp(err.identifier,'msiq:if:Wiring'); end
assert(rejected,'Backend must reject duplicate inputs independently of the UI.');
bad=out.profile;
bad.board.mapping=struct('i_channel','C3','q_channel','C4');
rejected=false;
try, msiq.if_workbench_validate_profile(bad,'balance');
catch err, rejected=strcmp(err.identifier,'msiq:if:BoardMapping'); end
assert(rejected,'Selecting scope channels must not infer the physical board mapping.');
d.stage.Value='tx_if'; d.stage.ValueChangedFcn([],[]);
p=d.getProfile();
assert(isequal(p.scope.channels,{'C2'})&&strcmp(p.scope.side,'lower'));
assert(strcmp(d.scopeOne.Enable,'off')&&strcmp(d.scopeTwo.Enable,'off'));
assert(strcmp(d.scopeTwo.Visible,'off'));
assert(isempty(p.wiring.confirmed_at));
afterMock = msiq.instruments.get_audit();
assert(isequal(before,afterMock),'UI mock accessed instruments.');
report = struct('ok',true,'status','passed','checks',{{'hidden_startup','plan_no_io', ...
    'profile_preserved','mock_to_live_blocked','mock_manual_capture','mock_no_io', ...
    'fixed_channel_options','duplicate_rejected','wiring_confirmation_invalidated', ...
    'stable_reconfirmation_id','alternate_scope_capture','tx_lower_ch2_fixed', ...
    'readonly_labels','collapsed_optional_sections','capture_without_scan', ...
    'awg_plan_isolation','plan_edit_invalidation','status_preserved','draft_state', ...
    'replay_independent','record_selection','compact_metrics','invalid_denominator', ...
    'tx_no_demodulation','shutdown_unknown','progress_failure_isolation'}},'run_dir',out.run_dir);
% Keep visual evidence with the same verification run; no native device access.
preview=msiq.if_workbench_app(struct('Visible','off'));
previewGuard=onCleanup(@() deleteIfValid(preview));
pd=preview.UserData; pd.runPath.Value=out.run_dir; pd.runAction('replay');
sizes={[20 40 1240 660],[10 10 1880 980],[10 10 900 520]};
names={'ui_rx_1280.png','ui_rx_1920.png','ui_compact.png'};
for k=1:numel(sizes)
    preview.Position=sizes{k}; preview.SizeChangedFcn([],[]); drawnow;
    scroll(pd.scrollHost,'top'); drawnow; pause(.1);
    exportapp(preview,fullfile(out.run_dir,names{k}));
    assert(strcmp(pd.offButton.Visible,'on')&&strcmp(pd.stopButton.Visible,'on'));
end
preview.Position=sizes{1}; preview.SizeChangedFcn([],[]);
pd.stage.Value='tx_if'; pd.stage.ValueChangedFcn([],[]); pd.runAction('manual_capture');
pd.view.Value='spectrum'; pd.view.ValueChangedFcn([],[]); drawnow; pause(.1);
exportapp(preview,fullfile(out.run_dir,'ui_tx_if.png'));
pd.stage.Value='direct'; pd.stage.ValueChangedFcn([],[]); drawnow; pause(.1);
exportapp(preview,fullfile(out.run_dir,'ui_direct.png'));
pd.toggleSection(7,180); pd.toggleSection(9,330); drawnow;
scroll(pd.scrollHost,'bottom'); drawnow; pause(.1);
exportapp(preview,fullfile(out.run_dir,'ui_record_details.png'));
report.screen_pixels_per_inch=get(groot,'ScreenPixelsPerInch');
report.scaling_check='Compact effective workspace checked; Windows DPI setting unchanged.';
assert(isequal(before,msiq.instruments.get_audit()),'Visual checks accessed instruments.');
save(fullfile(out.run_dir,'data','ui_validation.mat'),'report');
clear previewGuard;
clear guard;
end
function deleteIfValid(f)
if isvalid(f), delete(f); end
end
