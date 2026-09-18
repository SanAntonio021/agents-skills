function run = rx_daily_journal(action,cfg,task,run,response)
%RX_DAILY_JOURNAL Small durable task ledger; never stores display/raw arrays.
% begin(cfg,task) allocates one task run. update/finalize append an event and
% preserve attempt/source relationships without changing capture source runs.
if nargin<4, run=[]; end
if nargin<5, response=struct(); end
if strcmp(action,'begin')
    category='measurement';
    if strcmp(task.profile.mode,'mock'), category='checks'; end
    if isfield(task.options,'source_mode') && strcmp(task.options.source_mode,'simulation') && ...
            ~field(task.options,'test_fixture',false), category='simulation'; end
    if msiq.validation_artifacts('active'), category='checks'; end
    name='RX_重复测量'; if task.balance, name='RX_自动配平'; end
    run=msiq.create_output_run(cfg,category,name);
    state=struct('schema_version',1,'task_id',task.id,'events',{{}},'rows',{{}});
    msiq.atomic_save(fullfile(run.DataDir,'task_state.mat'),struct('state',state));
    msiq.atomic_save(fullfile(run.DataDir,'task_config.mat'), ...
        struct('profile',task.profile,'cfg',cfg,'channels',{task.channels}, ...
        'options',pick(task.options,{'capture_then_demod','enable_ldpc','tx_reference_bundle','scope_channels','source_mode','measurement_context'})));
    Result_Summary_Initialize(run, ...
        {'序号','角色','状态','纠错前错误数','统计比特数','纠错前BER','MER','源记录','测量位置','子带','实际通道'}, ...
        {'-','-','-','bit','bit','-','dB','-','-','-','-'});
elseif isempty(run)
    return;
end
loaded=load(fullfile(run.DataDir,'task_state.mat'),'state'); state=loaded.state;
event=struct('at',char(datetime('now','Format','yyyy-MM-dd HH:mm:ss.SSS')), ...
    'phase',task.phase,'active',task.active,'stopped',task.stopped,'reason',task.reason);
for key={'action','ok','error','error_id','snapshot','board_history','elapsed_s','cleanup','range_report'}
    if isfield(response,key{1}), event.(key{1})=response.(key{1}); end
end
if isfield(response,'values'), event.range_request=pick(response,{'channels','values','expected_status','precheck'}); end
if isfield(response,'status') && isfield(response,'range_skipped')
    event.range_readback=response.status; event.range_skipped=response.range_skipped;
end
if isfield(response,'payload')
    % The caller may log a write request before dispatch; omit transport callbacks.
    event.request=pick(response.payload,{'kind','subband','value','settings'});
end
if isfield(response,'capture'), event.capture=pick(response.capture, ...
        {'run_dir','raw_path','metadata_path','reference_bundle_path','status','reason','measurement_context'}); end
if isfield(response,'result'), event.analysis=pick(response.result,{'run_dir','status'}); end
state.events{end+1}=event;
new_rows=cell(1,numel(task.rows));
for k=1:numel(task.rows)
    original=task.rows{k};
    row=struct('role',original.role,'capture',pick(original.capture, ...
        {'run_dir','raw_path','metadata_path','reference_bundle_path','status','reason','measurement_context','actual_scope_channels','requested_scope_channels'}), ...
        'observation',pick(original.observation, ...
        {'metrics','power_dbv2','scale_vdiv','clipped','sample_rates_hz','windows_s','attempt_reason','range_decision','range_reports','status_before','status_after'}));
    if isfield(original.observation,'result')
        row.analysis=pick(original.observation.result,{'run_dir','status'});
    end
    new_rows{k}=row;
    if k>numel(state.rows)
        m=field(row.observation,'metrics',struct());
        status='已保存'; if ismember(row.role,{'failed','cancelled'}), status=row.role; end
        measurement=msiq.rx_measurement_context(field(row.capture,'measurement_context',struct()));
        band=''; if isfield(measurement,'subband'), band=num2str(measurement.subband); end
        Result_Summary_Append(run,{k,row.role,status,field(m,'pre_error_count',NaN), ...
            field(m,'pre_bit_count',NaN),field(m,'pre_ber',NaN), ...
            field(m,'mer_db',NaN),field(row.capture,'run_dir',''),measurement.label,band, ...
            strjoin(cellstr(string(field(row.capture,'actual_scope_channels',{}))),' / ')});
    end
end
state.rows=new_rows; state.completed_formal=task.completed;
state.reference_provenance=pick(task.options,{'source_reference_path','source_reference_hash','source_reference_association'});
state.planned_formal=task.count*double(~task.balance);
state.board=task.board; state.phase=task.phase; state.reason=task.reason;
state.stopped=task.stopped; state.active=task.active; state.elapsed_s=toc(task.started);
state.source_mode=field(task.options,'source_mode',field(cfg,'source_mode','measurement'));
msiq.atomic_save(fullfile(run.DataDir,'task_state.mat'),struct('state',state));
Result_Log_Stage(run,'INFO','task','%s | %s',task.phase,task.reason);
attempts=sum(cellfun(@(e)isfield(e,'action') && strcmp(e.action,'formal_capture') && ...
    isfield(e,'ok'),state.events));
failures=sum(cellfun(@(e)isfield(e,'ok') && ~e.ok,state.events));
Result_Update_Run_Info(run,struct('counts',struct('planned',state.planned_formal, ...
    'executed',attempts,'succeeded',task.completed,'failed',failures,'invalid',0), ...
    'task',struct('id',task.id,'balance',task.balance,'phase',task.phase, ...
    'formal_completed',task.completed,'saved_records',numel(state.rows),'reason',task.reason)));
if strcmp(action,'finalize')
    status='completed'; reason='normal_completion';
    if task.stopped, status='stopped'; reason='user_stop';
    elseif failures>0 || ~ismember(task.reason,{'测量完成','配平完成，已达到容差', ...
            '配平停止：达到调整次数上限','配平停止：达到批准边界', ...
            '通信质量确认变差，已恢复此前设置','功率差不再改善，已恢复此前设置'})
        status='failed'; reason='processing_failed';
    end
    Result_Finalize_Run(run,status,reason,[],task.reason);
end
end

function out=pick(in,keys)
out=struct();
if ~isstruct(in), return; end
for k=1:numel(keys), if isfield(in,keys{k}), out.(keys{k})=in.(keys{k}); end; end
end
function value=field(in,key,fallback)
if isstruct(in) && isfield(in,key), value=in.(key); else, value=fallback; end
end
