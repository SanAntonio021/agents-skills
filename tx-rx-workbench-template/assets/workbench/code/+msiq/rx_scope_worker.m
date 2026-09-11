function rx_scope_worker(folder)
%RX_SCOPE_WORKER Serial process-local instrument owner with cooperative shutdown.
data = load(fullfile(folder,'bootstrap.mat'));
file_only=isfield(data,'worker_kind') && strcmp(data.worker_kind,'reference');
if file_only && isempty(data.factory)
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
session = []; status = struct(); full_read = []; last_calibration = [];
settings=struct(); previous_raw=struct(); previous_analysis=struct();
owner=containers.Map({'session'},{[]});
guard=onCleanup(@() close_owner(owner,io));
query_fn=@(s,c) progress_query(io,s,c,folder);
while ~isfile(fullfile(folder,'close.flag')) && parent_alive(data.parent_pid)
    path = fullfile(folder,'request.mat');
    if ~isfile(path), pause(.02); continue; end
    packet = load(path,'request'); delete(path);
    request = packet.request;
    fprintf('%s #%d %s begin\n',char(datetime('now','Format','HH:mm:ss.SSS')), ...
        request.sequence,request.action);
    response = struct('sequence',request.sequence,'action',request.action, ...
        'ok',false,'status',struct(),'raw',struct(),'accepted',NaN,'error','', ...
        'analysis_s',NaN,'read_s',NaN,'error_id','');
    started = tic;
    phase = request.action; command = '';
    try
        if file_only && ~strcmp(request.action,'reference')
            error('RX_Workbench:FileOnly','File worker rejects all instrument actions.');
        end
        switch request.action
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
                if ~raw.new_data && isfield(previous_analysis,'channels') && ...
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
                    response.raw = msiq.plotting.rx_live_analysis(raw,status);
                end
                response.raw.capture_valid = any([response.raw.channels.wave_valid]);
                if response.raw.capture_valid
                    response.raw.capture_reason = '';
                elseif isempty(requested)
                    response.raw.capture_reason = ['所选通道未开启：' strjoin(request.channels, '、')];
                else
                    response.raw.capture_reason = ['未收到有效波形：' strjoin(requested, '、')];
                end
                response.analysis_s=toc(analysis_started);
                previous_raw=raw; previous_analysis=response.raw;
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
                        request.channels,request.path,request.search);
                end
            otherwise
                error('RX_Workbench:WorkerAction','Unknown worker action.');
        end
        response.ok = true;
        response.status = status;
    catch exception
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

function close_owner(owner,io)
if ~isKey(owner,'session'), return; end
session=owner('session');
if ~isempty(session)
    try io.close(session); catch, end
    remove(owner,'session');
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
    cleanup = onCleanup(@() process.Dispose()); %#ok<NASGU>
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
for k=1:2
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
