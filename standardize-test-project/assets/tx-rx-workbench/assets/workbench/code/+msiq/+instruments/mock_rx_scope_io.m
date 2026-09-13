function io = mock_rx_scope_io(options)
%MOCK_RX_SCOPE_IO Process-local deterministic scope with controllable blocking I/O.
scale=[.015 .015 .03 .04]; offset=zeros(1,4); timebase=5e-6; drift_done=false;
trigger_delay=0;
capture_id=0;
values=containers.Map('KeyType','char','ValueType','any');
ranges=containers.Map('KeyType','char','ValueType','any');
for c=1:4
    prefix=sprintf('app.Acquisition.C%d.',c);
    define([prefix 'Coupling'],'D50',{'D50','GND'});
    define([prefix 'BandwidthLimit'],'OFF',{'OFF','16GHZ','13GHZ','8GHZ','6GHZ','4GHZ','3GHZ','1GHZ','200MHZ','ON'});
    define([prefix 'AverageSweeps'],1,[1 1e6 1]);
    define([prefix 'InterpolateType'],'LINEAR',{'LINEAR','SINXX'});
    define([prefix 'EnhanceResType'],'NONE',{'NONE','0.5BITS','1BITS','1.5BITS','2BITS','2.5BITS','3BITS'});
    define([prefix 'OptimizeGroupDelay'],'FLATNESS',{'PULSERESPONSE','EYEDIAGRAM','FLATNESS'});
end
define('app.Acquisition.TriggerMode','AUTO',{'AUTO','NORM','SINGLE','STOP'});
define('app.Acquisition.Trigger.Type','EDGE',{'EDGE','WIDTH'});
define('app.Acquisition.Trigger.Edge.Source','C1',{'C1','C2','C3','C4','EXT','LINE','FE'});
define('app.Acquisition.Trigger.Edge.Slope','POS',{'POS','NEG','EITHER'});
define('app.Acquisition.Trigger.Edge.Level',0,[-.075 .075 .001]);
define('app.Acquisition.Trigger.Edge.HoldoffType','OFF',{'OFF','TI','EV'});
define('app.Acquisition.Trigger.Edge.HoldoffTime',1e-9,[1e-9 20 .5e-9]);
define('app.Acquisition.Horizontal.MaxSamples',4e6,[500 32e6 25000]);
define('app.Acquisition.Horizontal.SampleMode','REALTIME',{'REALTIME','SEQUENCE','RIS'});
if isfield(options,'sample_mode'), values('app.Acquisition.Horizontal.SampleMode')=options.sample_mode; end
trace_states=repmat({'ON'},1,4);
if isfield(options,'timebase_s'), timebase=options.timebase_s; end
if isfield(options,'trace_states') && numel(options.trace_states)==4
    trace_states=cellstr(string(options.trace_states));
end
io=struct('open',@open_mock,'query',@query_mock,'write',@write_mock, ...
    'capture',@capture_mock,'close',@close_mock,'reference',@reference_mock);

    function info=reference_mock(request)
        record('REFERENCE BEGIN');
        if isfield(options,'reference_release_path')
            started=tic;
            while ~isfile(options.reference_release_path)
                assert(toc(started)<60,'mock:ReferenceGateTimeout', ...
                    'Reference release was not received within 60 seconds.');
                java.lang.Thread.sleep(20);
            end
        elseif isfield(options,'reference_delay_s')
            java.lang.Thread.sleep(round(options.reference_delay_s*1000));
        end
        fail('REFERENCE');
        info=msiq.rx_reference_band(request.project_root,request.channels,request.path,request.search);
        record('REFERENCE END');
    end

    function session=open_mock(~)
        record('OPEN'); fail('OPEN');
        if isfield(options,'startup_warning') && options.startup_warning
            warning('mock:InstrumentStartup','Instrument startup warning on stderr.');
        end
        session=struct('mock',true);
    end
    function reply=query_mock(~,command)
        record(['QUERY ' command]); fail(command);
        switch command
            case '*IDN?', reply='LECROY,SDA845ZI-A,MOCK,8.1'; return;
            case 'TDIV?', reply=sprintf('%.15g',timebase); return;
            case 'TRDL?', reply=sprintf('TRDL %.15g S',trigger_delay); return;
            case 'MSIZ?', reply=num2str(values('app.Acquisition.Horizontal.MaxSamples')); return;
            case 'TRMD?', reply=values('app.Acquisition.TriggerMode'); return;
            case 'BWL?'
                parts=cell(1,4);
                for b=1:4, parts{b}=sprintf('C%d,%s',b,values(sprintf('app.Acquisition.C%d.BandwidthLimit',b))); end
                reply=strjoin(parts,','); return;
        end
        vb=regexp(command,'^VBS\? ''return=(app\.[^'']+)''$','tokens','once');
        if ~isempty(vb)
            path=vb{1}; method=regexp(path,'\.(Get\w+)$','tokens','once');
            if ~isempty(method), path=extractBefore(path,strlength(path)-strlength(method{1})); end
            path=char(path);
            if isfield(options,'unsupported_setting') && contains(path,options.unsupported_setting)
                reply='ERROR unsupported property'; return;
            end
            if isKey(values,path)
                if isempty(method)
                    reply=char(string(values(path)));
                    if endsWith(path,'.BandwidthLimit') && strcmp(reply,'OFF'), reply='Full'; end
                    return;
                end
                limits=ranges(path);
                if strcmp(path,'app.Acquisition.Trigger.Edge.Level')
                    src=values('app.Acquisition.Trigger.Edge.Source');
                    if ~isempty(regexp(src,'^C[1-4]$','once')), span=5*scale(str2double(src(2))); else, span=1; end
                    limits=[-span span .001];
                end
                switch method{1}
                    case {'GetRangeStringRemote','GetRangeStringScreen'}, reply=strjoin(limits,',');
                    case {'GetMin','GetMinValue'}, reply=num2str(limits(1),17);
                    case {'GetMax','GetMaxValue'}, reply=num2str(limits(2),17);
                    case {'GetGrain','GetGrainValue'}, reply=num2str(limits(3),17);
                    otherwise, error('mock:Command','Unexpected metadata %s',command);
                end
                return;
            end
        end
        token=regexp(command,'^C([1-4]):(VDIV|OFST|TRA|CPL)\?$','tokens','once');
        if ~isempty(token)
            ch=str2double(token{1});
            switch token{2}
                case 'VDIV', reply=sprintf('%.15g',scale(ch));
                case 'OFST', reply=sprintf('%.15g',offset(ch));
                case 'TRA'
                    current_states=read_trace_states();
                    reply=current_states{ch};
                case 'CPL', reply=values(sprintf('app.Acquisition.C%d.Coupling',ch));
            end
        elseif contains(command,'SampleRate'), reply='80000000000';
        elseif contains(command,'InterpolateType'), reply='Linear';
        elseif contains(command,'AverageSweeps'), reply='1';
        elseif contains(command,'EnhanceResType'), reply='None';
        elseif contains(command,'OptimizeGroupDelay'), reply='Flatness';
        else, error('mock:Command','Unexpected query %s',command);
        end
    end
    function write_mock(~,command)
        record(['WRITE ' command]); fail(command);
        vb=regexp(command,'^VBS ''(app\.[^=]+)\.Value=(.+)''$','tokens','once');
        if ~isempty(vb) && isKey(values,vb{1})
            token=vb{2};
            if startsWith(token,'"'), values(vb{1})=strrep(token,'"','');
            else, values(vb{1})=str2double(token); end
            return;
        end
        token=regexp(command,'^C([1-4]):(TRA|CPL) (\S+)$','tokens','once');
        if ~isempty(token)
            target_channel=str2double(token{1});
            if strcmp(token{2},'TRA'), trace_states{target_channel}=token{3};
            else, values(sprintf('app.Acquisition.C%d.Coupling',target_channel))=token{3}; end
            return;
        end
        token=regexp(command,'^BWL C([1-4]),(\S+)$','tokens','once');
        if ~isempty(token), values(sprintf('app.Acquisition.C%s.BandwidthLimit',token{1}))=token{2}; return; end
        if startsWith(command,'TRMD '), values('app.Acquisition.TriggerMode')=command(6:end); return; end
        value=str2double(regexp(command,'[^ ]+$','match','once'));
        if startsWith(command,'TDIV '), timebase=value;
        elseif startsWith(command,'TRDL '), trigger_delay=value;
        elseif contains(command,':VDIV '), scale(str2double(command(2)))=round(value/.005)*.005;
        elseif contains(command,':OFST '), offset(str2double(command(2)))=value;
        else, error('mock:Command','Unexpected write %s',command);
        end
    end
    function raw=capture_mock(~,channels)
        record('CAPTURE BEGIN');
        cleanup_label='CAPTURE RESTORE AUTO';
        if isfield(options,'observation_mode') && options.observation_mode, cleanup_label='CAPTURE RELEASE'; end
        guard=onCleanup(@() record(cleanup_label));
        % Sleep blocks this MATLAB process without serving any GUI callbacks.
        java.lang.Thread.sleep(round(options.capture_delay_s*1000));
        fail('CAPTURE');
        count=options.record_count;
        if ~isfield(options,'no_new_frame') || ~options.no_new_frame || capture_id==0, capture_id=capture_id+1; end
        t=(-count/2+(0:count-1)')/80e9-trigger_delay;
        for k=1:numel(channels)
            samples=.04*cos(2*pi*1e9*t+k*.3)+.003*cos(2*pi*11e9*t);
            samples(round(count*.713))=.055;
            records(k)=struct('channel',channels{k},'samples',samples, ...
                'time_axis_s',t,'sample_rate_hz',80e9, ...
                'descriptor',struct('trigger_time_bytes',[typecast(double(capture_id),'uint8') zeros(1,8,'uint8')], ...
                'sweeps_per_acq',capture_id,'result_update_id',capture_id)); %#ok<AGROW>
        end
        if isfield(options,'calibration_offset_v')
            for k=1:numel(records)
                ch=str2double(channels{k}(2));
                records(k).descriptor.vertical_offset=offset(ch)+options.calibration_offset_v;
                records(k).descriptor.horizontal_offset_s=t(1);
            end
        end
        raw=struct('channels',records);
        mode='';
        if isfile(options.failure_path), mode=strtrim(fileread(options.failure_path)); end
        if (strcmp(mode,'DRIFT') && ~drift_done) || strcmp(mode,'DRIFT_ALWAYS')
            offset(1)=offset(1)+.001; drift_done=true;
            record('CAPTURE SETTING DRIFT');
        end
        record('CAPTURE END');
    end
    function close_mock(~)
        record('CLOSE');
    end
    function define(path,value,range)
        values(path)=value; ranges(path)=range;
    end
    function states=read_trace_states()
        states=trace_states;
        if ~isfield(options,'trace_state_path') || ~isfile(options.trace_state_path), return; end
        value=strtrim(fileread(options.trace_state_path));
        tokens=regexp(upper(value),'(ON|OFF)','match');
        if numel(tokens)==4, states=tokens; end
    end
    function fail(command)
        if isfile(options.failure_path)
            target=strtrim(fileread(options.failure_path));
            if ~isempty(target) && startsWith(command,target)
                error('mock:Timeout','Injected timeout at %s',command);
            end
        end
    end
    function record(message)
        path=options.log_path;
        if startsWith(message,'REFERENCE ') && isfield(options,'reference_log_path')
            path=options.reference_log_path;
        end
        fid=fopen(path,'a');
        if fid<0, error('mock:Log','Cannot open mock audit.'); end
        guard=onCleanup(@() fclose(fid));
        fprintf(fid,'%s\n',message);
    end
end
