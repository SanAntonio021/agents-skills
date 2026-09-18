classdef RxDailyTask < handle
    %RXDAILYTASK One bounded command at a time; owns no hardware or graphics.
    properties
        active=true
        stopped=false
        reason=''
        phase='capture'
        id
        options
        profile
        channels
        count
        completed=0
        rows={}
        capture=struct()
        observation=struct()
        reference=struct()
        board=struct()
        balance=false
        adjustments=0
        confirmations={}
        role='trial'
        ranges=[]
        range_adjustments=0
        frozen_status=struct()
        pending_range=[]
        pending_write=struct()
        started
        range_history={}
        range_precheck=false
        range_accept_pending=false
        balance_range_diagnostic=false
        range_reports={}
        range_match_needed=[]
        range_match_actual=[]
    end
    methods
        function obj=RxDailyTask(id,options,profile,channels,count,balance,board)
            if nargin<7, board=struct(); end
            profile.scope.range_strategy='computed';
            obj.id=id; obj.options=options; obj.profile=profile;
            obj.channels=channels; obj.count=count; obj.balance=balance; obj.board=board; obj.started=tic;
            if isfield(options,'measurement_context') && ~isempty(fieldnames(options.measurement_context))
                m=options.measurement_context;
                m=msiq.rx_measurement_context(m);
                obj.options.measurement_context=m;
                obj.profile.measurement_context=m;
                if isfield(m,'subband'), obj.profile.subband=m.subband;
                elseif isfield(obj.profile,'subband'), obj.profile=rmfield(obj.profile,'subband'); end
                if m.is_real_if
                    assert(numel(channels)==1,'RX_Workbench:RealIFChannels','单路中频需要一个采集通道');
                    obj.profile.stage='tx_if';
                end
                if balance
                    assert(ismember(m.position,{'rx_if','rx_if_thz'}), ...
                        'RX_Workbench:BalancePosition','自动配平仅适用于中频下变频后的物理 I/Q');
                end
            end
            validateattributes(count,{'numeric'},{'scalar','integer','>=',1,'<=',100});
            f=profile.scope.fresh;
            assert(f.verified && all(isfinite([f.timeout_s f.poll_s])) && f.timeout_s>0 && f.poll_s>0, ...
                'RX_Workbench:FreshGate','尚未确认新采集完成判据');
            assert(isfinite(profile.policy.settle_s) && profile.policy.settle_s>=0, ...
                'RX_Workbench:Settle','尚未配置稳定等待时间');
            p=profile.scope;
            assert(isfinite(p.max_adjustments) && p.max_adjustments>=0 && p.max_adjustments==fix(p.max_adjustments), ...
                'RX_Workbench:RangeGate','请配置量程调整次数');
            assert(isfinite(p.target_divisions) && p.target_divisions>0 && ...
                isfinite(p.edge_margin_divisions) && p.edge_margin_divisions>=0 && ...
                p.target_divisions+2*p.edge_margin_divisions<=8, ...
                'RX_Workbench:RangeGate','目标占格与上下余量合计不能超过 8 格');
            if ~balance, obj.role='formal'; end
            if options.capture_then_demod || balance, obj.phase='prepare_reference'; end
            if ~balance && isfield(options,'observation_cache')
                c=options.observation_cache;
                if all(isfield(c,{'decision','status','observed_datenum','measurement_revision','channels','refresh_period_s'})) && ...
                        isfield(options,'measurement_revision') && c.measurement_revision==options.measurement_revision && ...
                        isequal(c.channels,channels) && (now-c.observed_datenum)*86400>=0 && ...
                        (now-c.observed_datenum)*86400<=max(2,3*c.refresh_period_s) && c.decision.valid && ...
                        c.decision.needs_adjustment && obj.auto_range() && profile.scope.max_adjustments>0
                    obj.pending_range=c.decision.target_vdiv; obj.frozen_status=c.status;
                    obj.range_precheck=true; obj.range_history={c.decision.current_vdiv};
                    if strcmp(obj.phase,'capture'), obj.phase='range'; end
                end
            end
            if balance
                assert(numel(channels)==2 && isfield(board,'state_known') && board.state_known, ...
                    'RX_Workbench:BalanceGate','自动配平需要两路通道及完整已下发设置');
                assert(isfield(profile.board,'runtime') && all(isfield(profile.board.runtime, ...
                    {'protocol_verified','mapping_verified','response_verified'})) && ...
                    isequal(profile.board.runtime.protocol_verified,true) && ...
                    isequal(profile.board.runtime.mapping_verified,true) && ...
                    isequal(profile.board.runtime.response_verified,true), ...
                    'RX_Workbench:BalanceGate','请确认协议、物理映射和板卡控制响应');
                assert(isfield(board.state,'agc') && numel(board.state.agc)==6 && all(board.state.agc==0), ...
                    'RX_Workbench:BalanceGate','请先下发完整设置，关闭六路 AGC');
                q=profile.policy;
                assert(all(isfinite([q.balance_tolerance_db q.balance_step_db q.max_balance_adjustments ...
                    q.ber_degradation q.mer_degradation_db])) && q.balance_step_db>0 && ...
                    q.balance_tolerance_db>=0 && q.ber_degradation>=0 && q.mer_degradation_db>=0 && ...
                    q.max_balance_adjustments>=0 && q.max_balance_adjustments==fix(q.max_balance_adjustments), ...
                    'RX_Workbench:BalanceGate','请确认配平和通信质量容差及次数上限');
                assert(isfield(profile.board,'mapping') && ...
                    ismember(profile.board.mapping.i_channel,channels) && ...
                    ismember(profile.board.mapping.q_channel,channels) && ...
                    ~strcmp(profile.board.mapping.i_channel,profile.board.mapping.q_channel), ...
                    'RX_Workbench:Mapping','请确认板卡 I/Q 与示波器物理通道对应关系');
                obj.phase='prepare_reference'; obj.options.enable_ldpc=false;
            end
        end
        function request=next(obj)
            request=[]; if ~obj.active || obj.stopped, return; end
            request=struct('action',obj.phase,'task_id',obj.id,'timeout_s',90);
            request.range_reference_identity=field(obj.options,'range_reference_identity',field(obj.options,'tx_reference_bundle',''));
            request.measurement_revision=field(obj.options,'measurement_revision',0);
            if obj.balance, request.origin='balance'; else, request.origin='daily_test'; end
            switch obj.phase
                case 'capture'
                    request.action='formal_capture'; request.channels=obj.channels;
                    request.options=obj.options; request.options.measurement_role=obj.role;
                    request.fresh=obj.profile.scope.fresh; request.settle_s=obj.profile.policy.settle_s;
                    request.timeout_s=max(90,request.fresh.timeout_s+request.settle_s+60);
                    request.profile=obj.profile; request.profile.scope.channels=obj.channels;
                    request.frozen_ranges=obj.ranges; request.frozen_status=obj.frozen_status;
                    request.frozen_board=obj.board;
                case 'prepare_reference'
                    request.options=obj.options; request.channels=obj.channels;
                case 'demod'
                    request.run_dir=obj.capture.run_dir; request.options=obj.options; request.timeout_s=900;
                    if isfield(obj.capture,'reference_bundle_path'), request.options.tx_reference_bundle=obj.capture.reference_bundle_path; end
                case 'range'
                    request.action='formal_range'; request.channels=obj.channels;
                    request.values=obj.pending_range; request.expected_status=obj.frozen_status;
                    request.precheck=obj.range_precheck; request.range_strategy='computed';
                    request.measurement_revision=field(obj.options,'measurement_revision',0);
                    request.reference_bundle=field(obj.options,'tx_reference_bundle','');
                    if obj.range_precheck, request.observation_cache=obj.options.observation_cache; end
                case 'write'
                    request.action='board_adjust'; request.payload=obj.pending_write;
                case 'board_ready'
                    request.payload=struct();
            end
        end
        function accept(obj,response)
            if isfield(response,'range_report'), obj.range_reports{end+1}=response.range_report; end
            if ~response.ok || obj.stopped
                obj.range_accept_pending=false;
                has_capture=isfield(response,'capture') || strcmp(obj.phase,'demod');
                if isfield(response,'capture'), obj.capture=response.capture; end
                if isfield(response,'observation'), obj.observation=response.observation; end
                if isfield(response,'raw') && isfield(response.raw,'channels')
                    obj.observation.display_raw=response.raw; obj.observation.scope_status=response.status;
                end
                if isfield(response,'result'), obj.observation.result=response.result; end
                obj.reason='已停止任务'; if ~response.ok, obj.reason=response.error; end
                if has_capture && isfield(obj.capture,'run_dir')
                    label='failed'; if obj.stopped, label='cancelled'; end
                    obj.record(label);
                end
                obj.active=false; obj.reason='已停止任务';
                if ~response.ok, obj.reason=response.error; end
                return;
            end
            switch obj.phase
                case 'prepare_reference'
                    obj.options=response.options; obj.phase='capture';
                    if obj.balance, obj.phase='board_ready';
                    elseif obj.range_precheck, obj.phase='range'; end
                case 'board_ready'
                    if isfield(response,'snapshot'), obj.board=response.snapshot; end
                    obj.phase='capture';
                case 'range'
                    if ~isfield(response,'range_skipped') || ~response.range_skipped
                        obj.range_adjustments=obj.range_adjustments+1;
                        actual=zeros(1,numel(obj.channels));
                        for k=1:numel(actual)
                            c=response.status.channels(strcmp({response.status.channels.channel},obj.channels{k}));
                            actual(k)=c.vertical_scale_v_per_div;
                        end
                        assert(all(isfinite(actual)&actual>0),'RX_Workbench:RangeReadback','量程回读无效');
                        obj.ranges=actual; obj.frozen_status=response.status;
                        obj.range_history{end+1}=actual; obj.range_accept_pending=true;
                    elseif obj.range_precheck
                        obj.frozen_status=struct();
                    end
                    obj.range_precheck=false;
                    if obj.balance, obj.role='range_trial'; else, obj.role='formal'; end
                    obj.phase='capture';
                case 'write'
                    obj.board=response.snapshot;
                    if strcmp(obj.role,'revert')
                        obj.active=false;
                    else, obj.phase='capture'; end
                case 'capture'
                    obj.capture=response.capture; obj.observation=response.observation; obj.observation.scope_status=response.status;
                    obj.observation.display_raw=response.raw;
                    d=obj.observation.range_decision;
                    safe=field(d,'safe',d.valid && ~d.needs_adjustment);
                    needed=[];
                    if isfield(d,'per_channel') && ~isempty(d.per_channel)
                        needed=[d.per_channel.needed_vdiv];
                    end
                    % A repeated task freezes its accepted scale. Noise alone must
                    % not start another shrink cycle; every frame still checks safety.
                    if safe && ~isempty(obj.range_match_actual) && ...
                            range_equal(d.current_vdiv,obj.range_match_actual)
                        d.needs_adjustment=false;
                    end
                    % A fresh frame after our write decides acceptance, not request equality.
                    if obj.range_accept_pending && safe
                        d.needs_adjustment=false;
                        obj.range_match_needed=needed; obj.range_match_actual=d.current_vdiv;
                    end
                    % Once balance has a reference, do not chase a new optimum on every
                    % attenuation step. Only unsafe acquisition triggers a diagnostic.
                    if obj.balance && ~isempty(fieldnames(obj.reference)) && safe
                        d.needs_adjustment=false;
                    end
                    if safe && ~d.needs_adjustment
                        d.reason='实际回读量程满足边缘余量';
                        if isfield(d,'target_vdiv'),d.target_vdiv=d.current_vdiv;end
                        if isfield(d,'per_channel')
                            for k=1:numel(d.per_channel)
                                d.per_channel(k).needs_adjustment=false;
                                d.per_channel(k).reason=d.reason;
                            end
                        end
                    end
                    obj.range_accept_pending=false;
                    if ~d.valid || d.needs_adjustment
                        obj.reason=d.reason;
                        if obj.balance && ~isempty(fieldnames(obj.reference)), obj.record('排查');
                        else, obj.record('量程检查'); end
                        assert(d.valid,'RX_Workbench:RangeData','%s',d.reason);
                        assert(~strcmp(obj.role,'balance_confirmation'), ...
                            'RX_Workbench:RangeConfirmation','退化确认期间量程条件失效，已暂停，未混算');
                        assert(obj.auto_range(),'RX_Workbench:AutoRangeDisabled','量程不合适，请调整后重新测试');
                        assert(obj.range_adjustments<obj.profile.scope.max_adjustments, ...
                            'RX_Workbench:RangeBudget','量程调整已达到次数上限');
                        if ~safe && numel(obj.range_history)>1
                            previous=obj.range_history(1:end-1);
                            for k=1:numel(d.current_vdiv)
                                unsafe=~isfield(d,'per_channel') || ~d.per_channel(k).safe;
                                if unsafe
                                    assert(~any(cellfun(@(v)range_equal(v(k),d.current_vdiv(k)),previous)), ...
                                        'RX_Workbench:RangeOscillation','%s 实际量程未推进或反复切换，已停止',obj.channels{k});
                                end
                            end
                        end
                        if isempty(obj.range_history),obj.range_history={d.current_vdiv};end
                        obj.pending_range=d.target_vdiv;
                        if ~safe && obj.range_adjustments>0 && isfield(d,'per_channel')
                            for k=1:numel(obj.channels)
                                if ~d.per_channel(k).safe
                                    obj.pending_range(k)=max(d.target_vdiv(k),2*d.current_vdiv(k));
                                else,obj.pending_range(k)=d.current_vdiv(k);end
                            end
                        end
                        if obj.balance && ~isempty(fieldnames(obj.reference))
                            obj.balance_range_diagnostic=true;
                        end
                        obj.frozen_status=response.status;obj.phase='range';return;
                    end
                    obj.reason=''; obj.ranges=d.current_vdiv; obj.frozen_status=response.status;
                    obj.range_match_actual=d.current_vdiv;obj.range_match_needed=needed;
                    obj.observation.range_decision=d;
                    assert(~obj.observation.clipped,'RX_Workbench:Clipping','检测到削顶，已保留波形并停止');
                    if ~isempty(obj.ranges)
                        assert(isequal(obj.ranges,obj.observation.scale_vdiv), ...
                            'RX_Workbench:RangeDrift','固定测量期间量程发生变化');
                    end
                    if obj.balance || obj.options.capture_then_demod
                        assert(obj.capture.demod_ready,'RX_Workbench:Reference','波形已保存；参考不符合解调要求');
                        obj.phase='demod';
                    else
                        obj.observation.metrics=struct('valid',false,'reason','本次未解调'); obj.finish_observation();
                    end
                case 'demod'
                    obj.observation.result=response.result;
                    obj.observation.metrics=msiq.rx_pre_fec_metrics(response.result);
                    assert(obj.observation.metrics.valid,'RX_Workbench:InvalidMetrics', ...
                        '纠错前指标无效：%s',obj.observation.metrics.reason);
                    obj.finish_observation();
            end
        end
        function fail(obj,exception)
            obj.reason=exception.message; obj.active=false;
            if isfield(obj.capture,'run_dir'), obj.record('failed'); end
        end
        function stop(obj)
            obj.stopped=true; obj.reason='已请求停止';
        end
    end
    methods (Access=private)
        function yes=auto_range(obj)
            yes=true; if isfield(obj.profile.scope,'auto_range_enabled'), yes=obj.profile.scope.auto_range_enabled; end
        end
        function record(obj,label)
            observation=obj.observation; observation.attempt_reason=obj.reason;
            observation.range_reports=obj.range_reports;
            if isfield(obj.capture,'run_dir') && isfolder(obj.capture.run_dir)
                details=struct('task_id',obj.id,'role',label,'completed_formal',obj.completed+strcmp(label,'正式'), ...
                    'stop_requested',obj.stopped,'reason',obj.reason,'elapsed_s',toc(obj.started));
                Result_Atomic_Write_Json(fullfile(obj.capture.run_dir,'data','task_outcome.json'),details);
            end
            obj.rows{end+1}=struct('role',label,'capture',obj.capture,'observation',observation);
        end
        function finish_observation(obj)
            if ~obj.balance
                obj.record('正式'); obj.completed=obj.completed+1;
                obj.range_adjustments=0; obj.range_history={};
                if obj.completed>=obj.count, obj.active=false; obj.reason='测量完成';
                else, obj.phase='capture'; end
                return;
            end
            if obj.balance_range_diagnostic
                obj.reason='固定板卡完成量程排查，原质量参考的量程已改变；请重新开始配平';
                obj.record('排查');obj.active=false;return;
            end
            obj.record(obj.role);
            if strcmp(obj.role,'balance_confirmation')
                obj.confirmations{end+1}=obj.observation;
                if numel(obj.confirmations)<3, obj.phase='capture'; return; end
                bad=cellfun(@(x)obj.worse(x,obj.reference),obj.confirmations);
                if all(bad), obj.rollback('通信质量确认变差，已恢复此前设置'); return; end
                obj.observation=obj.confirmations{find(~bad,1,'last')};
            elseif strcmp(obj.role,'balance') && obj.worse(obj.observation,obj.reference)
                obj.confirmations={obj.observation}; obj.role='balance_confirmation'; obj.phase='capture'; return;
            end
            difference=abs(diff(obj.observation.power_dbv2));
            if ~isempty(fieldnames(obj.reference)) && difference>=abs(diff(obj.reference.power_dbv2))
                obj.rollback('功率差不再改善，已恢复此前设置'); return;
            end
            if difference<=obj.profile.policy.balance_tolerance_db
                obj.active=false; obj.reason='配平完成，已达到容差'; return;
            end
            if obj.adjustments>=obj.profile.policy.max_balance_adjustments
                obj.active=false; obj.reason='配平停止：达到调整次数上限'; return;
            end
            stronger=1+(obj.observation.power_dbv2(1)<obj.observation.power_dbv2(2));
            kind='q'; if strcmp(obj.channels{stronger},obj.profile.board.mapping.i_channel), kind='i'; end
            subband=obj.profile.subband; old=obj.board.state.(kind)(subband);
            value=old+obj.profile.policy.balance_step_db;
            if value>min(31.5,obj.profile.board.limits.(kind)(subband,2))
                obj.active=false; obj.reason='配平停止：达到批准边界'; return;
            end
            obj.reference=obj.observation; obj.reference.board=obj.board;
            obj.pending_write=struct('kind',kind,'subband',subband,'value',value);
            obj.role='balance'; obj.phase='write'; obj.adjustments=obj.adjustments+1;
            obj.ranges=obj.observation.scale_vdiv; obj.frozen_status=obj.observation.scope_status;
        end
        function bad=worse(obj,a,b)
            x=a.metrics; y=b.metrics;
            assert(x.valid && y.valid && x.pre_bit_count==y.pre_bit_count, ...
                'RX_Workbench:Denominator','配平比较的统计块不一致');
            if x.pre_error_count>0 || y.pre_error_count>0
                bad=x.pre_ber>y.pre_ber+obj.profile.policy.ber_degradation;
            else, bad=x.mer_db<y.mer_db-obj.profile.policy.mer_degradation_db; end
        end
        function rollback(obj,reason)
            obj.pending_write.value=obj.reference.board.state.(obj.pending_write.kind)(obj.profile.subband);
            obj.role='revert'; obj.phase='write'; obj.reason=reason;
        end
    end
end

function value=field(s,key,fallback)
value=fallback;if isfield(s,key)&&~isempty(s.(key)),value=s.(key);end
end
function yes=range_equal(a,b)
yes=isequal(size(a),size(b))&&all(abs(a-b)<=max(1e-12,abs(b)*1e-8));
end
