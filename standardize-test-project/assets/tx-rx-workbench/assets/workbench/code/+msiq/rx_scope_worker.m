function rx_scope_worker(folder)
%RX_SCOPE_WORKER Serial process-local instrument owner with cooperative shutdown.
% Template-only child-process guard: workers do not inherit the parent's path.
template_guard=[]; template_audit=[]; %#ok<NASGU>
marker=getenv('MSIQ_TEMPLATE_NO_HARDWARE_ROOT');
if ~isempty(marker)
    template_root=fileparts(fileparts(fileparts(mfilename('fullpath'))));
    assert(strcmpi(char(java.io.File(marker).getCanonicalPath()), ...
        char(java.io.File(template_root).getCanonicalPath())), ...
        'template:WorkerRoot','Template guard root does not match this worker.');
    addpath(template_root); template_guard=Template_NoHardware();
    msiq.instruments.reset_audit();
    template_audit=onCleanup(@() template_worker_audit(folder));
end
data = load(fullfile(folder,'bootstrap.mat'));
file_only=isfield(data,'worker_kind') && strcmp(data.worker_kind,'reference');
board_only=isfield(data,'worker_kind') && strcmp(data.worker_kind,'board');
if ~isempty(marker) && ~file_only && ~board_only
    assert(~isempty(data.factory),'template:WorkerFactory', ...
        'Template scope workers require an explicit simulation factory.');
end
if (file_only || board_only) && isempty(data.factory)
    io=struct('close',@(~) []);
elseif isempty(data.factory)
    io = struct('open',@(s) msiq.instruments.open_session('scope',s,'raw'), ...
        'query',@msiq.instruments.query_scpi,'write',@msiq.instruments.write_scpi, ...
        'capture',@(s,c) msiq.instruments.capture_scope_raw(s,c,struct('mode','observation')), ...
        'close',@msiq.instruments.close_session);
else
    if ~file_only, data.factory_options.observation_mode=true; end
    io = feval(data.factory,data.factory_options);
end
session = []; status = struct(); full_read = []; last_calibration = []; range_cache=struct();
settings=struct(); previous_raw=struct(); previous_analysis=struct(); previous_live_options=struct();
owner=containers.Map({'session','board','request','cleanup','release_errors'}, ...
    {[],[],struct(),struct(),{}});
guard=onCleanup(@() close_all(owner,io,folder));
query_fn=@(s,c) progress_query(io,s,c,folder);
while ~isfile(fullfile(folder,'close.flag')) && parent_alive(data.parent_pid)
    path = fullfile(folder,'request.mat');
    if ~isfile(path), pause(.02); continue; end
    packet = load(path,'request'); delete(path);
    request = packet.request; owner('request')=request;
    fprintf('%s #%d %s begin\n',char(datetime('now','Format','HH:mm:ss.SSS')), ...
        request.sequence,request.action);
    response = struct('sequence',request.sequence,'action',request.action, ...
        'ok',false,'status',struct(),'raw',struct(),'accepted',NaN,'error','', ...
        'analysis_s',NaN,'read_s',NaN,'error_id','');
    if isfield(request,'source_epoch'), response.source_epoch=request.source_epoch; end
    if isfield(request,'measurement_revision'), response.measurement_revision=request.measurement_revision; end
    if isfield(request,'origin'), response.origin=request.origin; end
    if isfield(request,'revision'), response.revision=request.revision; end
    started = tic;
    phase = request.action; command = '';
    try
        if file_only && ~ismember(request.action,{'reference','demod','prepare_reference','prepare_simulation'})
            error('RX_Workbench:FileOnly','File worker rejects all instrument actions.');
        end
        if board_only && ~startsWith(request.action,'board_'), error('RX_Workbench:BoardOnly','Board worker rejects scope actions.'); end
        if ~isfield(request,'payload'), request.payload=request; end
        check_task(folder,request);
        if field_or_worker(request,'rx_position_guard',false)
            revision=field_or_worker(request,'measurement_revision',-1);
            prior=-1; if isKey(owner,'measurement_revision'), prior=owner('measurement_revision'); end
            assert(revision>=prior,'RX_Workbench:StaleMeasurement','测量选择已变化，拒绝旧请求');
            owner('measurement_revision')=revision;
            if startsWith(request.action,'board_')
                measurement=field_or_worker(request,'measurement_context',struct());
                assert(ismember(field_or_worker(measurement,'position',''),{'rx_if','rx_if_thz'}), ...
                    'RX_Workbench:BoardPosition','当前测量位置不能操作 RX 中频板卡');
            end
        end
        live_options=worker_live_options(request);
        if isfield(io,'set_measurement') && isfield(live_options,'measurement_context')
            io.set_measurement(live_options.measurement_context);
        end
        if ismember(request.action,{'connect','release','setting','control','restore_settings','board_adjust','board_initialize','board_connect','board_close'}), range_cache=struct(); end
        switch request.action
            case 'prepare_simulation'
                assert(file_only,'RX_Workbench:SimulationPreparation', ...
                    '通信模拟波形必须由文件后台准备。');
                progress(folder,'准备编码通信波形和发送参考');
                response.simulation_source=msiq.rx_simulation_source( ...
                    field_or_worker(request,'simulation',struct()));
                check_task(folder,request);
            case 'connect'
                close_owner(owner,io);
                command = 'VISA open';
                progress(folder,['连接 | ' command]);
                session = io.open(data.specification);
                owner('session')=session;
                status = msiq.instruments.rx_scope_state(session,query_fn);
                settings=msiq.instruments.rx_scope_settings(session,query_fn,struct(),true);
                status.settings=settings;
                previous_raw=struct(); previous_analysis=struct();
                last_calibration = [];
                full_read = tic;
            case 'status'
                status = msiq.instruments.rx_scope_state(session,query_fn);
                if isfield(request,'extended_status') && request.extended_status
                    settings=msiq.instruments.rx_scope_settings(session,query_fn,settings,false);
                end
                settings=sync_sample_mode(settings,read_sample_mode(session,query_fn));
                status.settings=settings;
                full_read = tic;
            case 'scope_snapshot'
                status=msiq.instruments.rx_scope_state(session,query_fn);
                settings=msiq.instruments.rx_scope_settings(session,query_fn,struct(),true);
                status.settings=settings;
                response.snapshot=msiq.rx_scope_snapshot(status,request.channels);
            case 'restore_settings'
                assert(~isempty(session),'RX_Workbench:Disconnected','请先连接示波器');
                restore_io=struct('query',query_fn,'write',io.write);
                response.report=msiq.rx_scope_restore(session,request.target,request.channels, ...
                    restore_io,struct('check',@()check_task(folder,request)));
                if ~isempty(fieldnames(response.report.status)), status=response.report.status; end
                if isfield(status,'settings'), settings=status.settings; end
                previous_raw=struct(); previous_analysis=struct(); full_read=tic;
                if ~response.report.ok && isfield(response.report,'error_id') && ...
                        should_disconnect(struct('identifier',response.report.error_id))
                    error(response.report.error_id,'%s',strjoin(response.report.errors,'；'));
                end
                assert(response.report.ok,'RX_Workbench:RestoreIncomplete', ...
                    '恢复未完成：%s',strjoin(response.report.errors,'；'));
            case 'capture'
                if isempty(full_read) || toc(full_read)>=5
                    status = msiq.instruments.rx_scope_state(session,query_fn);
                    settings=msiq.instruments.rx_scope_settings(session,query_fn,settings,false);
                    full_read = tic;
                else
                    status = msiq.instruments.rx_scope_state(session,query_fn,status,request.channels);
                end
                settings=sync_sample_mode(settings,read_sample_mode(session,query_fn));
                status.settings=settings;
                if isfield(settings,'sample_mode') && ...
                        any(strcmpi(settings.sample_mode,{'SEQUENCE','SEQUENCE_MODE','RIS','RIS_MODE'}))
                    response.raw=struct('channels',struct([]),'new_data',false, ...
                        'capture_valid',false,'capture_reason','不支持当前采集模式，请选择实时模式', ...
                        'unsupported_mode',true,'observation_status','不支持当前采集模式');
                    response.read_s=toc(started);
                    response.ok=true; response.status=status;
                else
                active = status.channels(strcmp({status.channels.trace_state},'ON'));
                requested = request.channels(ismember(request.channels,{active.channel}));
                raw = struct('channels',struct([]));
                if ~isempty(requested)
                    command = strjoin(strcat(requested,':WAVEFORM? ALL'),' / ');
                    progress(folder,['采集 | ' command]);
                    raw = io.capture(session,requested);
                end
                after=msiq.instruments.rx_scope_state(session,query_fn,status,request.channels);
                before=status; status=after;
                status.settings=settings;
                raw.capture_consistency=msiq.rx_capture_consistency(raw,before,after,request.channels);
                if ~isequaln(raw.capture_consistency,last_calibration)
                    for item=raw.capture_consistency
                        fprintf('CALIBRATION %s OFST=%.17g V WAVEDESC=%.17g V delta=%.17g V\n', ...
                            item.channel,item.scope_offset_v,item.waveform_offset_v,item.offset_delta_v);
                    end
                    last_calibration=raw.capture_consistency;
                end
                raw = complete_channels(raw,request.channels);
                raw=msiq.rx_observation_freshness(raw,previous_raw,status);
                response.read_s=toc(started);
                phase = '频谱分析';
                progress(folder,phase);
                analysis_started=tic;
                if ~raw.new_data && isequaln(live_options,previous_live_options) && isfield(previous_analysis,'channels') && ...
                        any(arrayfun(@(r) ~isempty(r.samples),raw.channels)) && ...
                        isequal({raw.channels.channel},{previous_analysis.channels.channel}) && ...
                        isequal(arrayfun(@(r) ~isempty(r.samples),raw.channels), ...
                            arrayfun(@(r) ~isempty(r.samples),previous_analysis.channels))
                    response.raw=previous_analysis;
                    for name={'new_data','freshness_known','observation_status','observed_at'}
                        if isfield(raw,name{1}), response.raw.(name{1})=raw.(name{1}); end
                    end
                    for n=1:numel(raw.channels)
                        response.raw.channels(n).fresh=raw.channels(n).fresh;
                    end
                else
                    response.raw = msiq.plotting.rx_live_analysis(raw,status,live_options);
                end
                response.raw.capture_valid = any([response.raw.channels.wave_valid]);
                if response.raw.capture_valid
                    response.raw.capture_reason = '';
                elseif isempty(requested)
                    response.raw.capture_reason = ['所选通道未开启：' strjoin(request.channels, '、')];
                else
                    response.raw.capture_reason = ['未收到有效波形：' strjoin(requested, '、')];
                end
                if isfield(request,'range_policy')
                    if isfield(io,'source_mode') && strcmp(io.source_mode,'simulation'), raw.mock=true; end
                    if strcmp(field_or_worker(request.range_policy,'range_strategy',''),'computed'), status=read_range_context(status,session,query_fn); end
                    [response.range_decision,range_cache]=cached_range_decision(raw,status,request.range_policy,request,range_cache);
                    response.observed_datenum=now;
                end
                response.analysis_s=toc(analysis_started);
                previous_raw=raw; previous_analysis=response.raw; previous_live_options=live_options;
                end
            case 'formal_capture'
                assert(~isempty(session),'RX_Workbench:Disconnected','请先连接示波器');
                check=@() check_task(folder,request);
                check(); wait_checked(request.settle_s,check);
                owner('cleanup')=struct();
                cleanup_capture=onCleanup(@() restore_auto(io,session,owner));
                evidence=msiq.if_confirm_fresh(request.fresh,@(c)io.write(session,c), ...
                    @(c)query_fn(session,c),check,@(t)wait_checked(t,check));
                status=msiq.instruments.rx_scope_state(session,query_fn);
                if strcmp(field_or_worker(request.profile.scope,'range_strategy',''),'computed'), status=read_range_context(status,session,query_fn); end
                before=status; check(); raw=io.capture(session,request.channels);
                if strcmp(request.profile.mode,'mock'), raw.mock=true; end
                % Preserve a completed read even when cancellation arrived during I/O.
                request.options.scope_status=before; request.options.fresh_capture=evidence;
                request.options.requested_scope_channels=request.channels;
                if isfield(io,'source_mode'), request.options.source_mode=io.source_mode; end
                request.options.requires_capture_validation=true;
                if strcmp(field_or_worker(request.options,'sampling_baseline_source',''), 'front_panel')
                    request.profile.scope.sample_rate_hz=before.sample_rate_hz;
                    request.profile.scope.window_s=10*before.timebase;
                    request.options.sampling_baseline=struct('source','front_panel_readback', ...
                        'sample_rate_hz',before.sample_rate_hz,'window_s',10*before.timebase, ...
                        'status',before);
                end
                if isKey(owner,'board') && ~isempty(owner('board'))
                    current_board=owner('board'); request.options.board_state=current_board.snapshot();
                end
                response.capture=msiq.traditional_rx('save_capture',raw,request.options);
                check();
                if isfield(request,'frozen_board') && isfield(request.frozen_board,'state_known') && request.frozen_board.state_known
                    assert(isfield(request.options,'board_state') && request.options.board_state.state_known && ...
                        isequaln(request.options.board_state.state,request.frozen_board.state), ...
                        'RX_Workbench:BoardDrift','测量期间已下发板卡状态发生变化');
                end
                after=msiq.instruments.rx_scope_state(session,query_fn,status,request.channels); status=after;
                if strcmp(field_or_worker(request.profile.scope,'range_strategy',''),'computed')
                    after=read_range_context(after,session,query_fn);
                    assert(isequaln(before.range_context,after.range_context),'RX_Workbench:CaptureChanged','采集期间触发或采样模式发生变化');
                end
                raw.capture_consistency=msiq.rx_capture_consistency(raw,before,after,request.channels);
                if isfield(request,'frozen_status') && ~isempty(fieldnames(request.frozen_status))
                    msiq.rx_capture_consistency(raw,request.frozen_status,after,request.channels);
                    if isfield(request.frozen_status,'range_context') && isfield(after,'range_context')
                        assert(isequaln(request.frozen_status.range_context,after.range_context), ...
                            'RX_Workbench:CaptureChanged','正式任务触发或采样模式发生变化');
                    end
                end
                assert(all(arrayfun(@(c) ~isempty(c.samples),raw.channels)) && ...
                    numel(raw.channels)==numel(request.channels),'RX_Workbench:EmptyCapture','采集不完整');
                status=after;
                raw.fresh_confirmed=true;
                scale=zeros(1,numel(request.channels));
                for k=1:numel(scale)
                    ch=status.channels(strcmp({status.channels.channel},request.channels{k}));
                    scale(k)=ch.vertical_scale_v_per_div;
                end
                [response.observation,~]=msiq.if_capture_observation(raw,request.profile,request.options.cfg_override,scale);
                response.observation.scale_vdiv=scale;
                [response.observation.range_decision,range_cache]=cached_range_decision(raw,status,request.profile.scope,request,range_cache);
                response.observation.status_before=before; response.observation.status_after=after;
                Result_Atomic_Write_Json(fullfile(response.capture.run_dir,'data','range_decision.json'), ...
                    response.observation.range_decision);
                response.raw=msiq.plotting.rx_live_analysis(raw,status,live_options);
                response.raw.capture_valid=true; response.raw.capture_reason='';
                response.fresh_capture=evidence;
                capture_validation(response.capture,true,'',status,evidence);
                clear cleanup_capture; response.cleanup=owner('cleanup');
                settings=msiq.instruments.rx_scope_settings(session,query_fn,settings,false); status.settings=settings;
            case 'formal_range'
                assert(~isempty(session),'RX_Workbench:Disconnected','请先连接示波器');
                status=msiq.instruments.rx_scope_state(session,query_fn);
                computed=strcmp(field_or_worker(request,'range_strategy',''),'computed');
                if computed, status=read_range_context(status,session,query_fn); end
                expected=field_or_worker(request,'expected_status',struct());
                response.range_skipped=false;
                if field_or_worker(request,'precheck',false)
                    cache=field_or_worker(request,'observation_cache',struct());
                    if ~all(isfield(cache,{'observed_datenum','refresh_period_s'})) || ...
                            (now-cache.observed_datenum)*86400>max(2,3*cache.refresh_period_s)
                        response.range_skipped=true;
                    end
                end
                if ~isempty(fieldnames(expected))
                    try
                        msiq.rx_capture_consistency(struct('channels',struct([])),expected,status,request.channels);
                        if computed && isfield(expected,'range_context')
                            assert(isequaln(expected.range_context,status.range_context),'RX_Workbench:CaptureChanged','触发或采样模式发生变化');
                        end
                    catch ex
                        if field_or_worker(request,'precheck',false)
                            response.range_skipped=true;
                        else, rethrow(ex); end
                    end
                end
                response.range_report=struct('strategy',field_or_worker(request,'range_strategy','legacy'), ...
                    'requested_values',request.values,'actual_values',nan(size(request.values)), ...
                    'channels',{request.channels},'written_channels',{{}},'ok',false,'error','');
                assert(isnumeric(request.values) && isreal(request.values) && ...
                    numel(request.values)==numel(request.channels) && ...
                    all(isfinite(request.values(:)) & request.values(:)>0), ...
                    'RX_Workbench:RangeValue','量程请求必须是每通道有限正数');
                assert(numel(unique(request.channels))==numel(request.channels) && ...
                    all(ismember(request.channels,{status.channels.channel})), ...
                    'RX_Workbench:RangeChannel','量程通道无效或重复');
                if ~response.range_skipped
                    baseline=status;
                    for k=1:numel(request.channels)
                        check_task(folder,request);
                        c=baseline.channels(strcmp({baseline.channels.channel},request.channels{k}));
                        response.range_report.actual_values(k)=c.vertical_scale_v_per_div;
                        if abs(c.vertical_scale_v_per_div-request.values(k))<=max(1e-12,request.values(k)*1e-8), continue; end
                        if ~computed && isfield(request,'allowed_ranges')
                            assert(any(abs(request.allowed_ranges-request.values(k))<=max(1e-12,request.values(k)*1e-8)), ...
                                'RX_Workbench:RangeBoundary','请求量程不在批准档位中');
                        end
                        command=sprintf('%s:VDIV %.15g',request.channels{k},request.values(k));
                        io.write(session,command);
                        response.range_report.written_channels{end+1}=request.channels{k};
                        response.range_report.actual_values(k)=NaN;
                        check_task(folder,request);
                        reply=char(string(query_fn(session,[request.channels{k} ':VDIV?'])));
                        token=regexp(reply,'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?:[a-zA-Z/]+)?\s*$','tokens','once');
                        actual=NaN;
                        if ~isempty(token) && isempty(regexpi(reply,'error|failed|invalid|unknown','once')), actual=str2double(token{1}); end
                        assert(isfinite(actual)&&actual>0,'RX_Workbench:RangeReadback','量程回读无效');
                        response.range_report.actual_values(k)=actual;
                        assert(computed || abs(actual-request.values(k))<max(1e-12,request.values(k)*1e-6), ...
                            'RX_Workbench:RangeReadback','量程回读不一致');
                        index=strcmp({baseline.channels.channel},request.channels{k});
                        baseline.channels(index).vertical_scale_v_per_div=actual;
                        check_task(folder,request);
                        status=msiq.instruments.rx_scope_state(session,query_fn);
                        if computed
                            status=read_range_context(status,session,query_fn);
                            assert(isequaln(baseline.range_context,status.range_context),'RX_Workbench:CaptureChanged','调节期间触发或采样模式发生变化');
                        end
                        msiq.rx_capture_consistency(struct('channels',struct([])),baseline,status,request.channels);
                        check_task(folder,request);
                    end
                    if computed
                        range_cache=struct('key',range_cache_key(status,request), ...
                            'channels',{request.channels},'requested',request.values, ...
                            'actual',response.range_report.actual_values, ...
                            'needed',nan(size(request.values)),'pending',true(size(request.values)));
                    end
                    response.range_report.ok=true;
                end
            case 'prepare_reference'
                opts=request.options;
                if isfield(opts,'reference_association') && ~isempty(fieldnames(opts.reference_association))
                    a=opts.reference_association;
                    linked=msiq.tx_reference_link('read',opts.cfg_override.project_root,a.options);
                    assert(linked.valid && strcmp(linked.path,opts.tx_reference_bundle) && ...
                        strcmp(linked.hash,a.expected_hash),'RX_Workbench:ReferenceChanged', ...
                        '发送关联已经变化，请重新取得关联后测试');
                    opts.source_reference_association=linked.record;
                end
                original_hash=msiq.file_sha256(opts.tx_reference_bundle);
                ref=msiq.load_reference_bundle(opts.tx_reference_bundle); bundle=ref.bundle;
                assert(strcmp(original_hash,msiq.file_sha256(opts.tx_reference_bundle)), ...
                    'RX_Workbench:ReferenceChanged','读取期间发送参考发生变化');
                opts.source_reference_hash=original_hash;
                assert(isfield(bundle,'execution') && strcmp(bundle.execution.status,'applied'), ...
                    'RX_Workbench:Reference','发送参考未经有效下发');
                assert(msiq.rx_reference_channels_compatible(bundle,request.channels, ...
                    field_or_worker(opts,'measurement_context',struct()),true), ...
                    'RX_Workbench:Reference','发送参考与本次逻辑信号或采集通道不兼容');
                assert(strcmp(bundle.reference_payload_policy,'metrics_only') && ...
                    strcmp(bundle.tx_ref.frame.reference_payload_policy,'metrics_only'), ...
                    'RX_Workbench:Reference','发送参考策略不符合要求');
                snapshot=fullfile(folder,sprintf('task_reference_%d.mat',request.task_id));
                assert(~isfile(snapshot),'RX_Workbench:ReferenceSnapshot','任务参考快照已存在，不能覆盖');
                save(snapshot,'bundle','-v7.3');
                opts.source_reference_path=opts.tx_reference_bundle; opts.tx_reference_bundle=snapshot;
                opts.cfg_override.waveform=bundle.dsp_config.waveform;
                response.options=opts;
            case 'demod'
                progress(folder,'解调已保存的完整波形');
                response.result=msiq.traditional_rx('demod_capture',request.run_dir,request.options);
            case {'board_connect','board_initialize','board_adjust','board_close','board_ready'}
                if strcmp(request.action,'board_connect')
                    if ~isempty(owner('board')), previous_board=owner('board'); previous_board.close(); end
                    request.payload.cfg.initial_state_confirmed=false;
                    request.payload.cfg.cancel_check=@() task_cancelled(folder,owner('request'));
                    owner('board')=msiq.instruments.IfBoard(request.payload.cfg);
                    board=owner('board'); board.open();
                else
                    board=owner('board');
                    assert(~isempty(board),'RX_Workbench:BoardDisconnected','请先连接中频板卡');
                    switch request.action
                        case 'board_initialize', board.initialize(request.payload.settings);
                        case 'board_adjust'
                            board.setAttenuation(request.payload.kind,request.payload.subband,request.payload.value);
                        case 'board_close', board.close();
                        case 'board_ready', board.assertAutomaticReady();
                    end
                end
                board=owner('board'); response.snapshot=board.snapshot(); response.board_history=board.History;
                if isfield(io,'set_board'), io.set_board(response.snapshot); end
                if isfield(request,'task_id') && isfile(fullfile(folder,sprintf('cancel_%d.flag',request.task_id)))
                    board=owner('board'); board.cancel(); response.snapshot=board.snapshot();
                    error('RX_Workbench:Cancelled','已停止；写入期间收到停止请求，板卡状态未确认');
                end
            case 'setting'
                command = sprintf('%s %.15g',request.command,request.value);
                progress(folder,['写入 | ' command]);
                io.write(session,command);
                phase = '回读'; command = [request.command '?'];
                reply = strtrim(char(string(query_fn(session,command))));
                token = regexp(reply,'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?:[a-zA-Z/]+)?\s*$','tokens','once');
                accepted = NaN;
                if ~isempty(token) && isempty(regexpi(reply,'error|failed|invalid|unknown','once'))
                    accepted = str2double(token{1});
                end
                if ~isfinite(accepted) || ...
                        (~endsWith(request.command,'OFST') && ~endsWith(request.command,'TRDL') && accepted<=0)
                    error('RX_Workbench:Readback','无效回读：%s',reply);
                end
                response.accepted = accepted;
                status = msiq.instruments.rx_scope_state(session,query_fn);
                settings=msiq.instruments.rx_scope_settings(session,query_fn,settings,false);
                status.settings=settings;
                previous_raw=struct(); previous_analysis=struct();
                full_read=tic;
            case 'control'
                command=request.key;
                progress(folder,['写入 | ' command]);
                response.accepted=msiq.instruments.apply_rx_scope_setting( ...
                    session,request,query_fn,io.write);
                status=msiq.instruments.rx_scope_state(session,query_fn);
                settings=msiq.instruments.rx_scope_settings(session,query_fn,settings,false);
                status.settings=settings;
                previous_raw=struct(); previous_analysis=struct();
                full_read=tic;
            case 'release'
                close_owner(owner,io); session=[];
            case 'reference'
                progress(folder,'查找统计频段参考');
                if isfield(io,'reference')
                    response.reference=io.reference(request);
                else
                    response.reference=msiq.rx_reference_band(request.project_root, ...
                        request.channels,request.path,request.search,field_or_worker(request,'measurement_context',struct()), ...
                        field_or_worker(request,'reference_options',struct()));
                end
            otherwise
                error('RX_Workbench:WorkerAction','Unknown worker action.');
        end
        response.ok = true;
        if isfield(response,'cleanup') && isfield(response.cleanup,'auto_restored') && ~response.cleanup.auto_restored
            response.ok=false; response.error_id='RX_Workbench:Cleanup';
            response.error=['波形已保存，但示波器 AUTO 恢复未确认：' response.cleanup.error];
        end
        response.status = status;
    catch exception
        range_cache=struct();
        if isfield(response,'range_report'), response.range_report.error=exception.message; end
        if exist('cleanup_capture','var'), clear cleanup_capture; response.cleanup=owner('cleanup'); end
        if isKey(owner,'board') && ~isempty(owner('board'))
            board=owner('board'); response.snapshot=board.snapshot(); response.board_history=board.History;
            if isfield(io,'set_board'), io.set_board(response.snapshot); end
        end
        if strcmp(request.action,'formal_capture') && isfield(response,'capture')
            try capture_validation(response.capture,false,exception.message,status,field_or_worker(response,'fresh_capture',struct()));
            catch evidence_error, response.validation_save_error=evidence_error.message; end
        end
        response.error_id = exception.identifier;
        response.error = sprintf('%s | %s | %s',phase,command,exception.message);
        response.status=status;
        fprintf(2,'%s\n',getReport(exception,'extended','hyperlinks','off'));
        if ~strcmp(request.action,'reference') && should_disconnect(exception)
            close_owner(owner,io); session=[];
        end
    end
    response.elapsed_s = toc(started);
    fprintf('%s #%d %s ok=%d elapsed=%.3fs %s\n', ...
        char(datetime('now','Format','HH:mm:ss.SSS')),request.sequence, ...
        request.action,response.ok,response.elapsed_s,response.error);
    temporary = fullfile(folder,'response.tmp.mat');
    save(temporary,'response','-v7');
    movefile(temporary,fullfile(folder,'response.mat'),'f');
end

end

function mode=read_sample_mode(session,query_fn)
reply=strtrim(char(string(query_fn(session, ...
    'VBS? ''return=app.Acquisition.Horizontal.SampleMode'''))));
mode=regexp(upper(reply),'REALTIME|SEQUENCE|RIS','match','once');
if isempty(mode)
    error('RX_Workbench:Readback','无法确认采集模式：%s',reply);
end
end

function settings=sync_sample_mode(settings,mode)
settings.sample_mode=mode;
if isfield(settings,'fields')
    index=find(strcmp({settings.fields.key},'SAMPLEMODE'),1);
    if ~isempty(index)
        settings.fields(index).value=mode;
        settings.fields(index).available=true;
        settings.fields(index).error='';
    end
end
end

function yes=should_disconnect(exception)
identifier=lower(char(string(exception.identifier)));
yes=strcmp(identifier,'rx_workbench:readback') || ...
    strcmp(identifier,'rx_workbench:transport') || ...
    any(contains(identifier,{'visa','timeout','transport','readfailure','block','instrument:'}));
end

function close_owner(owner,io,finalizing)
if nargin<3, finalizing=false; end
if ~isKey(owner,'session'), return; end
session=owner('session');
if ~isempty(session)
    try
        io.close(session); remove(owner,'session');
    catch exception
        owner('release_errors')=[owner('release_errors'),{['scope: ' exception.message]}];
        if ~finalizing
            error('RX_Workbench:ReleaseFailed','示波器会话释放未确认：%s',exception.message);
        end
    end
end
end

function reply=progress_query(io,session,command,folder)
progress(folder,['回读 | ' command]);
reply=io.query(session,command);
end

function progress(folder,message)
fid=fopen(fullfile(folder,'progress.txt'),'w','n','UTF-8');
if fid<0, return; end
guard=onCleanup(@() fclose(fid));
fprintf(fid,'%s',message);
end

function yes = parent_alive(pid)
try
    process = System.Diagnostics.Process.GetProcessById(pid);
    cleanup = onCleanup(@() process.Dispose());
    yes = ~process.HasExited;
catch
    yes = false;
end
end

function raw = complete_channels(raw,channels)
records = raw.channels;
if isempty(records)
    records = struct('channel','','samples',[],'time_axis_s',[],'sample_rate_hz',NaN);
end
for k=1:numel(channels)
    index = find(strcmp({records.channel},channels{k}),1);
    if isempty(index)
        record = records(1); record.channel = channels{k};
        record.samples=[]; record.time_axis_s=[]; record.sample_rate_hz=NaN;
    else
        record = records(index);
    end
    ordered(k)=record; %#ok<AGROW>
end
raw.channels=ordered;
end

function check_task(folder,request)
if isfile(fullfile(folder,'close.flag')) || ...
    (isfield(request,'task_id') && isfile(fullfile(folder,sprintf('cancel_%d.flag',request.task_id))))
    error('RX_Workbench:Cancelled','已请求停止');
end
end
function wait_checked(seconds,check)
validateattributes(seconds,{'numeric'},{'scalar','nonnegative','finite'});
started=tic; while toc(started)<seconds, check(); pause(min(.05,seconds-toc(started))); end
check();
end
function restore_auto(io,session,owner)
try
    io.write(session,'TRMD AUTO');
    reply=upper(strtrim(char(string(io.query(session,'TRMD?')))));
    ok=contains(reply,'AUTO');
    owner('cleanup')=struct('auto_restored',ok,'error','');
    if ~ok, owner('cleanup')=struct('auto_restored',false,'error',['回读：' reply]); end
catch exception, owner('cleanup')=struct('auto_restored',false,'error',exception.message); end
end
function close_all(owner,io,folder)
if isKey(owner,'board') && ~isempty(owner('board'))
    try board=owner('board'); board.close();
    catch exception, owner('release_errors')=[owner('release_errors'),{['board: ' exception.message]}]; end
end
close_owner(owner,io,true);
errors=owner('release_errors');
released=struct('ok',isempty(errors),'errors',{errors}, ...
    'recorded_at',char(datetime('now','Format','yyyy-MM-dd HH:mm:ss.SSS')));
try msiq.atomic_save(fullfile(folder,'released.mat'),struct('released',released));
catch exception, fprintf(2,'Release evidence save failed: %s\n',exception.message); end
end

function yes=task_cancelled(folder,request)
yes=isfile(fullfile(folder,'close.flag')) || (isfield(request,'task_id') && isfile(fullfile(folder,sprintf('cancel_%d.flag',request.task_id))));
end

function capture_validation(capture,valid,reason,status,evidence)
msiq.rx_capture_validation(capture.run_dir,struct('valid',valid,'reason',reason,'status_after',status,'fresh_capture',evidence));
end
function value=field_or_worker(s,name,fallback)
value=fallback; if isfield(s,name), value=s.(name); end
end

function options=worker_live_options(request)
persistent cached_path cached_stamp cached_reference
options=field_or_worker(request,'options',struct());
for key={'measurement_context','real_if_reference','measurement_revision'}
    if isfield(request,key{1}), options.(key{1})=request.(key{1}); end
end
path=field_or_worker(request,'reference_bundle',field_or_worker(options,'tx_reference_bundle',''));
if ismember(request.action,{'capture','formal_capture'}) && ...
        (~isfield(options,'real_if_reference') || ...
        isempty(fieldnames(options.real_if_reference))) && ~isempty(path) && isfile(path)
    info=dir(path); stamp=[info.datenum info.bytes];
    if isempty(cached_path) || ~strcmp(cached_path,path) || ~isequal(cached_stamp,stamp)
        try
            value=msiq.load_reference_bundle(path);
            assert(strcmp(value.bundle.execution.status,'applied') && ...
                strcmp(value.bundle.reference_payload_policy,'metrics_only') && ...
                strcmp(value.bundle.tx_ref.frame.reference_payload_policy,'metrics_only'), ...
                'RX_Workbench:Reference','发送参考未通过有效性检查');
            cached_reference=value.bundle.dsp_config.waveform;
            cached_reference.reference_identity=msiq.file_sha256(path);
            cached_path=path; cached_stamp=stamp;
        catch
            cached_reference=struct(); cached_path=''; cached_stamp=[];
        end
    end
    options.real_if_reference=cached_reference;
end
end

function [decision,cache]=cached_range_decision(raw,status,policy,request,cache)
decision=msiq.rx_range_decision(raw,status,policy);
if ~strcmp(field_or_worker(policy,'range_strategy',''),'computed'), return; end
if isempty(fieldnames(cache)), return; end
if ~isequaln(cache.key,range_cache_key(status,request)), cache=struct(); return; end
accept={};
for k=1:numel(decision.per_channel)
    item=decision.per_channel(k); j=find(strcmp(cache.channels,item.channel),1);
    if isempty(j), continue; end
    fresh=field_or_worker(raw,'fresh_confirmed',field_or_worker(raw,'new_data',false));
    if cache.pending(j) && fresh && item.safe
        cache.needed(j)=item.needed_vdiv; cache.pending(j)=false;
    end
    if ~cache.pending(j) && abs(item.needed_vdiv-cache.needed(j))<=max(1e-12,abs(cache.needed(j))*1e-8)
        accept{end+1}=item.channel; %#ok<AGROW>
    end
end
policy.accept_actual_channels=unique([field_or_worker(policy,'accept_actual_channels',{}),accept]);
decision=msiq.rx_range_decision(raw,status,policy);
end

function key=range_cache_key(status,request)
% Only trusted sample/channel state; timestamps and query diagnostics are not identity.
key=struct();
for name={'idn','timebase','trigger_delay_s','sample_rate_hz','memory_depth','channels','range_context'}
    if isfield(status,name{1}), key.(name{1})=status.(name{1}); end
end
for name={'source_epoch','measurement_revision','measurement_context'}
    key.(name{1})=field_or_worker(request,name{1},[]);
end
key.selected=field_or_worker(request,'channels',{});
options=field_or_worker(request,'options',struct());
key.reference=field_or_worker(request,'range_reference_identity', ...
    field_or_worker(options,'source_reference_hash',field_or_worker(request,'reference_bundle','')));
end

function status=read_range_context(status,session,query_fn)
requested=struct('requested_keys',{{'SAMPLEMODE','TRSOURCE','TRLEVEL','TRSLOPE','HTYPE','HTIME'}});
values=msiq.instruments.rx_scope_settings(session,query_fn,requested,false);
status.range_context=struct('key',{values.fields.key},'value',{values.fields.value},'known',num2cell([values.fields.available]));
end

function template_worker_audit(folder)
audit=msiq.instruments.get_audit();
attempts=getappdata(0,'TemplateHardwareAttempts');
record=struct('hardware_attempts',attempts,'instrument_audit',audit, ...
    'guard_active',true,'pid',feature('getpid'),'worker_folder',folder);
p=fullfile(folder,'template_hardware_audit.json');
fid=fopen(p,'w','n','UTF-8'); assert(fid>=0,'template:AuditSave','Cannot save worker audit.');
cleanup=onCleanup(@()fclose(fid)); fwrite(fid,jsonencode(record),'char'); clear cleanup;
archive=getenv('TEMPLATE_AUDIT_DIR');
if ~isempty(archive)
    if ~isfolder(archive), mkdir(archive); end
    target=fullfile(archive,sprintf('worker_%d_%s.json',feature('getpid'), ...
        char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))));
    copyfile(p,target);
end
end