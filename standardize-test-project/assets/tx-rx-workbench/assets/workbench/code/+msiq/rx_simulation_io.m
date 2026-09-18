function io=rx_simulation_io(options)
%RX_SIMULATION_IO Communication provider: fixed receiver noise, live sent settings.
assert(isfield(options,'simulation_source'),'RX_Workbench:SimulationSource', ...
    '请先由后台准备通信模拟波形。');
source=options.simulation_source; simulation=source.simulation;
assert(strcmp(source.source_mode,'simulation'),'RX_Workbench:SimulationSource','模拟来源无效。');
assert(strcmp(msiq.file_sha256(source.waveform_path),source.waveform_sha256), ...
    'RX_Workbench:SimulationSource','通信模拟波形缓存已变化。');
loaded=load(source.waveform_path,'signal','master_rate_hz');
signal=loaded.signal; master_rate=loaded.master_rate_hz;
base_options=options;
defaults=struct('capture_delay_s',0,'record_count',1024, ...
    'log_path',[tempname '.log'], ...
    'failure_path',[tempname '.flag'], ...
    'timebase_s',simulation.timebase_s,'observation_mode',true);
for name=fieldnames(defaults)'
    if ~isfield(base_options,name{1}), base_options.(name{1})=defaults.(name{1}); end
end
base=msiq.instruments.mock_rx_scope_io(base_options);
ready=false; capture_id=0; requested_rate=simulation.sample_rate_hz; control_state_known=false;
v=repmat(simulation.baseline_attenuation_db,1,6);
sent=struct('rf',v,'i',v,'q',v,'agc',zeros(1,6));
io=base; io.query=@query; io.write=@write; io.capture=@capture; io.open=@open;
io.set_board=@set_board;
context=msiq.rx_measurement_context('',simulation.subband);
io.set_measurement=@set_measurement;
io.source_mode='simulation';
    function set_measurement(value)
        context=msiq.rx_measurement_context(value);
    end
    function session=open(specification)
        session=base.open(specification);
        for channel={'C1','C2','C3','C4'}
            base.write(session,[channel{1} ':VDIV 0.05']);
        end
    end
    function value=query(session,command)
        if strcmp(command,'MOCK:DONE?'), value=num2str(ready);
        elseif strcmp(command,'*IDN?'), value='SIMULATION,COMMUNICATION_RX,NO_HARDWARE,1.0';
        elseif contains(command,'BandwidthLimit')
            % Native communication simulation has no measured instrument bandwidth inventory.
            value='OFF';
        elseif contains(command,'Horizontal.SampleRate'), value=num2str(actual_rate(session),17);
        else, value=base.query(session,command); end
    end
    function write(session,command)
        switch command
            case 'MOCK:RESET', ready=false;
            case 'MOCK:START', ready=true;
            otherwise
                if contains(command,'Horizontal.SampleRate')
                    token=regexp(command,'=([0-9.eE+-]+)','tokens','once');
                    assert(~isempty(token),'RX_Workbench:SimulationRate','模拟采样率无效。');
                    value=str2double(token{1});
                    validateattributes(value,{'numeric'},{'scalar','positive','finite'});
                    requested_rate=value;
                else, base.write(session,command); end
        end
    end
    function set_board(snapshot)
        % Only driver-confirmed complete sent state affects the physical model.
        control_state_known=isfield(snapshot,'state_known') && snapshot.state_known;
        if ~isfield(snapshot,'sent'), return; end
        next=snapshot.sent;
        for key={'rf','i','q'}
            values=next.(key{1});
            if any(~isfinite(values)), continue; end
            validateattributes(values,{'numeric'},{'numel',6,'finite','>=',0,'<=',31.5});
            sent.(key{1})=values;
        end
    end
    function fs=actual_rate(session)
        duration=10*str2double(base.query(session,'TDIV?'));
        capacity=str2double(base.query(session,'MSIZ?'));
        target=requested_rate;
        if context.is_real_if
            stop=simulation.symbol_rate_hz*((1+source.cfg.waveform.rolloff)/2+.1);
            target=max(target,ceil(2.1*(context.center_freq_hz+stop)/1e9)*1e9);
        end
        fs=min(target,capacity/duration);
    end
    function raw=capture(session,channels)
        capture_id=capture_id+1;
        fs=actual_rate(session); duration=10*str2double(base.query(session,'TDIV?'));
        count=max(2,floor(duration*fs));
        delay_text=base.query(session,'TRDL?');
        token=regexp(delay_text,'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?','match');
        delay=str2double(token{end});
        t=((0:count-1)'-count/2)/fs-delay;
        index=mod(t*master_rate,numel(signal))+1;
        transmitted=interp1((1:numel(signal)+1)',[signal;signal(1)],index,'linear');
        band=simulation.subband;
        if isfield(context,'subband'), band=context.subband; end
        baseline=simulation.baseline_attenuation_db;
        gain_rf=10^(-(sent.rf(band)-baseline)/20);
        gains=gain_rf*[10^((simulation.iq_imbalance_db-(sent.i(band)-baseline))/20), ...
            10^(-(sent.q(band)-baseline)/20)];
        baseline_power=simulation.base_q_rms_v^2*(1+10^(simulation.iq_imbalance_db/10));
        noise_sigma=sqrt(baseline_power/10^(simulation.baseline_snr_db/10)/2);
        rng_stream=RandStream('mt19937ar','Seed',mod(simulation.seed+capture_id-1,2^32));
        clean=[real(transmitted)*gains(1),imag(transmitted)*gains(2)];
        if strcmp(context.position,'awg_direct') || context.is_real_if
            gains=[1 1];
            clean=[real(transmitted),imag(transmitted)];
        end
        noise=noise_sigma*randn(rng_stream,count,2);
        values=clean+noise;
        if context.is_real_if
            % Real modulation at the selected physical IF; no aliasing shortcut.
            stop=simulation.symbol_rate_hz*((1+source.cfg.waveform.rolloff)/2+.1);
            assert(fs/2>context.center_freq_hz+stop,'RX_Workbench:SimulationRate', ...
                '模拟记录点数上限不足以采集所选中频，请增加记录点数或缩短窗口。');
            carrier=context.center_freq_hz+option('frequency_offset_hz',0);
            baseband=transmitted;
            if option('conjugate',false), baseband=conj(baseband); end
            real_if=real(baseband.*exp(1j*2*pi*carrier*t));
            lo_frequency=max(.1e9,context.center_freq_hz-2*stop);
            real_if=real_if+option('lo_amplitude_v',.008)*cos(2*pi*lo_frequency*t);
            real_if=real_if+noise(:,1);
        end
        records=repmat(struct('channel','','samples',[],'time_axis_s',[], ...
            'sample_rate_hz',NaN,'descriptor',struct()),1,numel(channels));
        for k=1:numel(channels)
            channel=channels{k}; mapped=find(strcmp(simulation.channels,channel),1);
            if context.is_real_if, samples=real_if;
            elseif isempty(mapped), samples=noise_sigma*randn(rng_stream,count,1);
            else, samples=values(:,mapped); end
            scale=str2double(base.query(session,[channel ':VDIV?']));
            offset=str2double(base.query(session,[channel ':OFST?']));
            gain=8*scale/65536;
            codes=round((samples+offset)/gain);
            codes=min(max(codes,-32768),32767);
            samples=codes*gain-offset;
            descriptor=struct('vertical_gain',gain,'vertical_offset',offset,'comm_type',1, ...
                'horizontal_interval_s',1/fs,'horizontal_offset_s',t(1), ...
                'trigger_time_bytes',[typecast(double(capture_id),'uint8') zeros(1,8,'uint8')], ...
                'sweeps_per_acq',capture_id,'result_update_id',capture_id);
            records(k)=struct('channel',channel,'samples',samples,'time_axis_s',t, ...
                'sample_rate_hz',fs,'descriptor',descriptor); %#ok<AGROW>
        end
        raw=struct('channels',records,'source_mode','simulation','simulation', ...
            struct('cache_key',source.cache_key,'capture_sequence',capture_id, ...
            'seed',simulation.seed,'noise_sigma_v',noise_sigma,'baseline_snr_db',simulation.baseline_snr_db, ...
            'iq_imbalance_db',simulation.iq_imbalance_db,'subband',band, ...
            'sent_state',sent,'control_state_known',control_state_known, ...
            'signal_gains',gains,'noise_policy','fixed_receiver_floor'), ...
            'captured_at',datetime('now'));
        if ~isempty(context.position), raw.measurement_context=context; end
        if ~isfield(context,'subband'), raw.simulation=rmfield(raw.simulation,'subband'); end
        if simulation.test_fixture, raw.mock=true; end
    end
    function value=option(name,fallback)
        value=fallback;
        if isfield(options,'real_if') && isfield(options.real_if,name)
            value=options.real_if.(name);
        end
    end
end
