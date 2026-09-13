function report=validate_if_awg(matrix_file)
%VALIDATE_IF_AWG Offline AWG previews and mutated-contract rejection tests.
% Supply the licensed matrix path explicitly or through MSIQ_DVBS2_MATRIX_FILE.
if nargin<1, matrix_file=getenv('MSIQ_DVBS2_MATRIX_FILE'); end
before=msiq.instruments.get_audit();
p=msiq.if_workbench_config();
p.tx_options=struct('amplitude_vpp',[.2 .2],'offset_v',[0 0], ...
    'memory_mode','EXT','route','pair_b_ch3_ch4','seed',123);
p.matrix_file=[tempname '.missing.mat'];
reject(@() msiq.if_awg_action('tx_plan',struct('profile',p)), 'msiq:fec:ShortMatrixMissing');
assert(isequal(before,msiq.instruments.get_audit()));
assert(isfile(matrix_file),'msiq:if:MatrixTestDependency','Provide the licensed matrix for preview validation.');
p.matrix_file=matrix_file;
a=msiq.if_awg_action('tx_plan',struct('profile',p));
p.tx_options.memory_mode='INT';
b=msiq.if_awg_action('tx_plan',struct('profile',p));
summary=msiq.if_compare_contract({a.plan,b.plan});
assert(summary.valid&&abs(summary.playback_rates_hz(2)/summary.playback_rates_hz(1)-4)<1e-12);
assert(abs(summary.symbol_rate_hz-65e9/15)<1);
assert(a.plan.cfg.waveform.rolloff==.15&&b.plan.cfg.waveform.rolloff==.15);
changed=b.plan; changed.cfg.waveform.symbol_rate_hz=4e9;
reject(@() msiq.if_compare_contract({a.plan,changed}),'msiq:if:Baud');
changed=b.plan;
bits=changed.tx_ref.pairs(1).metrics_only(1).fec.coded_bits;
bits(1)=~bits(1);
changed.tx_ref.pairs(1).metrics_only(1).fec.coded_bits=bits;
reject(@() msiq.if_compare_contract({a.plan,changed}),'msiq:if:FrameMismatch');
changed=b.plan; changed.memory_capacity.ok=false;
reject(@() msiq.if_compare_contract({a.plan,changed}),'msiq:if:Capacity');
p.tx_options.symbol_rate_hz=4e9;
reject(@() msiq.if_awg_action('tx_plan',struct('profile',p)),'msiq:if:WaveformContract');
p.mode='live'; p.authorized_devices={'awg'};
reject(@() msiq.if_awg_action('tx_level',struct('profile',p,'hardware_confirmed',true)), ...
    'msiq:if:MockProfile');
assert(isequal(before,msiq.instruments.get_audit()),'Offline AWG tests accessed an instrument.');
cancel_checks=validate_cancel_boundaries(matrix_file);
report=struct('ok',true,'status','passed','checks',{{'missing_matrix_no_io','ext_int_same_frame', ...
    'playback_rate_ratio','fixed_baud_rolloff','baud_mismatch','reference_mismatch', ...
    'capacity_rejection','fixed_waveform_options','mock_live_rejection','no_io'}}, ...
    'comparison',summary,'mock_cancel_boundaries',{cancel_checks});
end
function results=validate_cancel_boundaries(matrix_file)
% Explicit test transport: exercise the real apply cleanup, never real VISA.
cleanup=onCleanup(@()msiq.instruments.reset_audit()); %#ok<NASGU>
cfg=msiq.short_frame_config(matrix_file);
cfg.instrument.awg=struct('mock',true,'mock_idn','MOCK,M8195A,0,2.0','idn_contains','M8195A');
opts=struct('cfg_override',cfg,'route','pair_b_ch3_ch4','memory_mode','EXT','rdiv','DIV4', ...
    'amplitude_vpp',[.2 .2],'offset_v',[0 0],'seed',1);
results=cell(1,4); call_count=0; cancel_at=0;
for boundary=1:4
    msiq.instruments.reset_audit();
    opts.artifact_prefix=sprintf('if_cancel_boundary_%d',boundary);
    plan=msiq.traditional_tx('awg_plan',[],opts);
    call_count=0; cancel_at=boundary;
    reject(@()msiq.traditional_tx('awg_apply',[],struct('plan',plan, ...
        'confirmation_phrase',plan.required_confirmation,'enable_output',true, ...
        'cancel_check',@cancelCheck)),'msiq:if:Cancelled');
    assert(call_count==boundary);
    failure=jsondecode(fileread(msiq.artifact_path(plan,'execution_failure.json')));
    assert(failure.shutdown_verified&&isequal(failure.shutdown_channels(:)',1:4));
    commands=msiq.instruments.get_command_history();
    assert(~any(cellfun(@(c)~isempty(regexp(c.command,':OUTPut[1-4] ON','once')),commands)));
    audit=msiq.instruments.get_audit();
    assert(audit.scope_connections==0&&audit.source_connections==0);
    results{boundary}=struct('boundary',boundary,'shutdown_verified',true, ...
        'output_on_sent',false,'run_dir',plan.run_dir,'transport','mock','audit',audit);
end
    function cancelCheck()
        call_count=call_count+1;
        if call_count==cancel_at, error('msiq:if:Cancelled','Injected cancellation at apply boundary.'); end
    end
end
function reject(f,id)
try
    f();
catch err
    assert(strcmp(err.identifier,id),'Expected %s, got %s: %s',id,err.identifier,err.message);
    return;
end
error('msiq:if:TestExpectedFailure','Expected rejection %s.',id);
end
