function out = if_awg_action(action,options)
%IF_AWG_ACTION AWG-only manual actions; preview never opens instruments.
action=lower(char(action));
p=options.profile;
allowed={'tx_plan','tx_prepare','tx_apply','tx_level','awg_stop'};
assert(ismember(action,allowed),'msiq:if:Action','Unknown AWG action.');
live=strcmp(p.mode,'live');
if ~strcmp(action,'tx_plan')
    assert(live,'msiq:if:LiveOnly','AWG control needs a local live profile; use tx_plan for offline preview.');
    assert(isfield(options,'hardware_confirmed')&&isequal(options.hardware_confirmed,true), ...
        'msiq:if:Authorization','Confirm the explicit AWG action.');
    assert(ismember('awg',p.authorized_devices),'msiq:if:Authorization','AWG is not authorized.');
end
tx=p.tx_options;
if isfield(tx,'cfg_override'), tx=rmfield(tx,'cfg_override'); end
if strcmp(action,'awg_stop')
    % Stop never depends on waveform files, power limits or successful planning.
    tx.awg_channels=1:4; tx.waveform_columns=1:4;
    tx.scope_channels={'C1','C2','C3','C4'};
    tx.labels={'CH1','CH2','CH3','CH4'};
    out=msiq.traditional_tx('awg_stop',[],tx); return;
end
if live && isfield(p,'mock_fixture_applied')
    assert(~p.mock_fixture_applied,'msiq:if:MockProfile','Synthetic defaults cannot authorize a live AWG action.');
end
assert(isfield(tx,'amplitude_vpp')&&numel(tx.amplitude_vpp)==2&& ...
    all(isfinite(tx.amplitude_vpp))&&all(tx.amplitude_vpp>0), ...
    'msiq:if:Amplitude','Specify both AWG amplitudes.');
assert(isfield(tx,'offset_v')&&all(tx.offset_v==0), ...
    'msiq:if:Offset','The first IF experiment uses zero offsets.');
if ~strcmp(action,'tx_plan')
    assert(isfield(tx,'route')&&~isempty(tx.route),'msiq:if:Route','Specify the approved AWG channel pair in the local profile.');
    limits=p.comparison.amplitude_bounds_vpp;
    assert(numel(limits)==2&&all(isfinite(limits))&&limits(1)>0&&limits(2)>=limits(1)&& ...
        all(tx.amplitude_vpp>=limits(1)&tx.amplitude_vpp<=limits(2)), ...
        'msiq:if:AmplitudeLimit','Both amplitudes must be within approved local limits.');
    assert(~isempty(p.wiring.id)&&~isempty(p.wiring.confirmed_at),'msiq:if:Wiring','Confirm wiring first.');
end
assert(isfield(tx,'memory_mode')&&ismember(upper(tx.memory_mode),{'EXT','INT'}), ...
    'msiq:if:MemoryMode','Select EXT/DIV4 or INT.');
tx.rdiv='DIV4';
fixed=struct('symbol_rate_hz',65e9/15,'master_sample_rate_hz',65e9, ...
    'rolloff',.15,'modulation_order',16,'ldpc_blocks_per_frame',3,'frame_repetitions',1, ...
    'hardware_sro_injection_ppm',0);
names=fieldnames(fixed);
for k=1:numel(names)
    name=names{k};
    if isfield(tx,name)&&~isempty(tx.(name))
        assert(isequal(tx.(name),fixed.(name)),'msiq:if:WaveformContract', ...
            'The IF experiment keeps the approved short frame, rate and shaping.');
    end
    tx.(name)=fixed.(name);
end
tx.rate_authority='symbol_rate';
if strcmp(action,'tx_level')
    out=msiq.traditional_tx('awg_level',[],tx); return;
end
matrix=''; if isfield(p,'matrix_file'), matrix=p.matrix_file; end
cfg=msiq.short_frame_config(matrix);
cfg.waveform.master_sample_rate_hz=65e9;
cfg.waveform.symbol_rate_hz=65e9/15;
cfg.waveform.selected_up=15;
cfg.waveform.rolloff=.15;
cfg.waveform.modulation_order=16;
tx.cfg_override=cfg;
switch action
    case 'tx_plan'
        plan=msiq.traditional_tx('preview_plan',[],tx);
        out=struct('status','offline_preview','plan',plan);
    case 'tx_prepare'
        plan=msiq.traditional_tx('awg_plan',[],tx);
        plan.if_requested_tx=p.tx_options;
        plan.if_wiring=p.wiring;
        out=struct('status','awaiting_apply','plan',plan,'run_dir',plan.run_dir);
    case 'tx_apply'
        assert(isfield(options,'plan')&&isstruct(options.plan),'msiq:if:Plan','Prepare and review an execution plan first.');
        plan=options.plan;
        assert(isfield(plan,'if_requested_tx')&&isequaln(plan.if_requested_tx,p.tx_options)&& ...
            isequaln(plan.if_wiring,p.wiring),'msiq:if:PlanDrift','Settings/wiring changed; prepare a new plan.');
        assert(isequal(plan.levels.amplitude_vpp,tx.amplitude_vpp)&&all(plan.levels.offset_v==0)&& ...
            abs(plan.cfg.waveform.symbol_rate_hz-65e9/15)<1&& ...
            strcmpi(plan.desired.memory_mode,tx.memory_mode), ...
            'msiq:if:PlanDrift','Execution plan does not match the approved amplitudes and playback mode.');
        assert(isfield(options,'confirmation_phrase')&&strcmp(options.confirmation_phrase,plan.required_confirmation), ...
            'msiq:if:PlanConfirmation','Confirm the displayed execution plan.');
        tx.plan=plan; tx.confirmation_phrase=options.confirmation_phrase;
        tx.enable_output=true;
        tx.cancel_check=@check_cancel;
        out=msiq.traditional_tx('awg_apply',[],tx);
end
end
function check_cancel()
drawnow;
if msiq.if_workbench('cancelled')
    error('msiq:if:Cancelled','Stop requested; AWG output will remain disabled.');
end
end
