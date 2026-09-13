classdef IfRun < handle
    %IFRUN One owned operation, with durable attempts and bounded adjustment.
    properties
        p; options; cfg; out; board=[]; scope=[]; awg=[];
        setting; scale; captureCount=0; clock; bundle=struct();
        amplitude; memoryMode='EXT'; lastRangeChange=false;
        comparisonPlans={};
        shutdownDone=false;
        referencePath=''; modeSwitchCount=0;
    end
    properties (Access=private)
        progressCallback=[]; progressLast=-Inf; progressPhase='preparing';
    end
    methods
        function self=IfRun(p,options)
            self.p=p; self.options=options;
            % UI callbacks are session-only, never part of saved run metadata.
            if isfield(self.options,'progress_callback')
                if isa(self.options.progress_callback,'function_handle')
                    self.progressCallback=self.options.progress_callback;
                end
                self.options=rmfield(self.options,'progress_callback');
            end
            self.cfg=msiq.build_config('v2_traditional_wz');
            if isfield(options,'cfg_override'), self.cfg=options.cfg_override; end
            self.cfg.receiver.debug_pre_fec_only=true;
            self.setting=p.initial; self.scale=p.scope.vdiv;
            self.amplitude=p.comparison.initial_vpp;
            self.clock=tic;
            self.out=struct('status','preparing','run_dir','','profile',p, ...
                'plan',msiq.if_workbench_plan(p),'observations',{{}},'events',{{}}, ...
                'errors',{{}},'completed_points',zeros(0,2),'stopped_groups',[], ...
                'baseline',{{}},'parent_run','','shutdown',struct(), ...
                'elapsed_s',0,'estimated_remaining_s',NaN);
        end
        function result=execute(self,action)
            emergency=onCleanup(@()self.emergencyShutdown()); %#ok<NASGU>
            self.progress('preparing',true);
            try
                self.preflight(action);
                category='measurement'; if strcmp(self.p.mode,'mock'), category='checks'; end
                run=msiq.create_output_run(self.cfg,category,['IF_' action]);
                self.out.run_dir=run.OutputDir; self.checkpoint();
                self.open();
                self.out.status='running';
                self.progress(action,true);
                switch action
                    case 'board_set'
                        self.setPoint(self.options.setting); self.event('manual_board_set',self.setting);
                    case 'manual_capture'
                        self.capture('manual',0,0);
                    case 'balance'
                        self.prepare(0,0,true);
                    case 'final_capture'
                        if isfield(self.options,'setting'), self.setPoint(self.options.setting); end
                        self.prepare(0,0,true); self.out.baseline=self.repeat('baseline',0,0,3);
                    case {'scan','mock'}
                        self.scan();
                    case 'resume'
                        self.resume();
                    case 'mode_compare'
                        self.compareModes();
                    otherwise
                        error('msiq:if:Action','Unknown IF operation: %s',action);
                end
                self.out.status='completed';
            catch ex
                self.out.status='paused';
                if strcmp(ex.identifier,'msiq:if:Cancelled')||msiq.if_workbench('cancelled'), self.out.status='cancelled'; end
                self.out.errors{end+1}=struct('identifier',ex.identifier,'message',ex.message,'stack',{ex.stack});
            end
            self.shutdown();
            if numel(self.out.baseline)==3
                ber=cellfun(@(x)x.metrics.pre_ber,self.out.baseline);
                mer=cellfun(@(x)x.metrics.mer_db,self.out.baseline);
                powers=cellfun(@(x)x.power_dbv2,self.out.baseline,'UniformOutput',false);
                self.out.baseline_summary=struct('count',3,'ber_mean',mean(ber),'ber_std',std(ber), ...
                    'mer_mean_db',mean(mer),'mer_std_db',std(mer),'mer_range_db',max(mer)-min(mer), ...
                    'power_dbv2',vertcat(powers{:}),'thresholds_auto_selected',false);
            end
            self.out.elapsed_s=toc(self.clock);
            self.out.final_setting=self.setting;
            self.out.candidates=self.candidates();
            try
                self.checkpoint();
                if ~isempty(self.out.run_dir), msiq.if_write_summary(self.out); end
            catch ex
                self.out.status='save_failed';
                self.out.errors{end+1}=struct('identifier',ex.identifier,'message',ex.message);
            end
            self.progress(self.out.status,true);
            result=self.out;
        end
        function preflight(self,action)
            [self.p,devices]=msiq.if_workbench_validate_profile(self.p,action);
            self.options.needed_devices=devices;
            self.options.board_automatic=ismember(action,{'balance','scan','mock','resume','final_capture'})&&strcmp(self.p.stage,'rx_iq');
            self.out.profile=self.p;
            self.out.plan=msiq.if_workbench_plan(self.p);
            p=self.p;
            assert(ismember(p.mode,{'mock','live'}),'msiq:if:Mode','mode must be mock or live.');
            assert(ismember(p.stage,{'direct','tx_if','rx_iq'}),'msiq:if:Stage','Unknown stage.');
            automatic=ismember(action,{'scan','mock','resume'});
            if automatic && ~self.out.plan.automatic_ready
                error('msiq:if:NotReady','%s',strjoin(self.out.plan.blockers,'; '));
            end
            if strcmp(p.mode,'mock'), return; end
            assert(~p.mock_fixture_applied,'msiq:if:MockProfile','Mock defaults cannot be reused for a live run. Load an explicit live profile.');
            assert(isfield(self.options,'hardware_confirmed')&&isequal(self.options.hardware_confirmed,true), ...
                'msiq:if:Authorization','Explicit hardware action confirmation is required.');
            assert(~isempty(p.wiring.id)&&~isempty(p.wiring.confirmed_at),'msiq:if:Wiring','Confirm physical wiring first.');
            if strcmp(p.stage,'tx_if')
                assert(strcmp(p.scope.side,'lower')&&isequal(p.scope.channels,{'C2'}),'msiq:if:Wiring','TX IF requires lower C2.');
            elseif strcmp(p.stage,'rx_iq')
                assert(strcmp(p.scope.side,'upper')&&numel(p.scope.channels)==2&& ...
                    numel(unique(p.scope.channels))==2&&all(ismember(p.scope.channels,{'C1','C2','C3','C4'})), ...
                    'msiq:if:Wiring','RX requires two distinct upper channels C1 through C4.');
            end
            for k=1:numel(devices)
                assert(ismember(devices{k},p.authorized_devices),'msiq:if:DeviceAuthorization','Device not authorized: %s',devices{k});
                if ~strcmp(devices{k},'board')
                    spec=self.cfg.instrument.(devices{k});
                    assert(~isfield(spec,'mock')||~spec.mock,'msiq:if:Transport','Live action cannot use a mock instrument specification.');
                end
            end
            if strcmp(action,'mode_compare')
                assert(isfield(p.tx_options,'route')&&~isempty(p.tx_options.route), ...
                    'msiq:if:Route','Specify the approved physical AWG channel pair.');
                c=p.comparison; bounds=c.amplitude_bounds_vpp;
                assert(numel(bounds)==2&&all(isfinite(bounds))&&bounds(1)>0&&bounds(2)>=bounds(1)&& ...
                    numel(self.amplitude)==2&&all(isfinite(self.amplitude))&&all(self.amplitude>=bounds(1)&self.amplitude<=bounds(2)), ...
                    'msiq:if:Amplitude','Initial amplitudes must lie in the approved range before opening instruments.');
                assert(isscalar(c.max_adjustments)&&isfinite(c.max_adjustments)&&c.max_adjustments>=0&& ...
                    c.max_adjustments==round(c.max_adjustments)&&isscalar(c.power_tolerance_db)&& ...
                    isfinite(c.power_tolerance_db)&&c.power_tolerance_db>=0, ...
                    'msiq:if:PowerPolicy','Confirmed power matching tolerance and integer adjustment budget required.');
                assert(numel(self.scale)==2&&all(isfinite(self.scale))&&all(self.scale>0), ...
                    'msiq:if:Scale','Fixed positive per-channel comparison ranges required.');
            end
            if ismember('scope',devices)
                f=p.scope.fresh;
                assert(f.verified&&all(isfinite([f.timeout_s f.poll_s p.policy.settle_s]))&&f.timeout_s>0&&f.poll_s>0, ...
                    'msiq:if:FreshGate','Verified fresh-acquisition profile and finite time bounds are required.');
                names={'reset_command','start_command','completion_query','pending_response','complete_response'};
                for k=1:numel(names), assert(~isempty(f.(names{k})),'msiq:if:FreshGate','Missing fresh capture field: %s',names{k}); end
                assert(~strcmp(f.pending_response,f.complete_response),'msiq:if:FreshGate','Pending and complete responses must differ.');
                if strcmp(action,'mode_compare')
                    base=self.p;
                    base.tx_options.amplitude_vpp=self.amplitude; base.tx_options.offset_v=[0 0];
                    for mode={'EXT','INT'}
                        base.tx_options.memory_mode=mode{1}; base.tx_options.seed=1;
                        preview=msiq.if_awg_action('tx_plan',struct('profile',base));
                        self.comparisonPlans{end+1}=preview.plan;
                    end
                    self.out.mode_contract=msiq.if_compare_contract(self.comparisonPlans);
                    plan=self.comparisonPlans{1};
                    self.bundle=struct('tx_ref',plan.tx_ref,'dsp_config',struct('waveform',plan.cfg.waveform,'receiver',plan.cfg.receiver));
                    self.cfg=plan.cfg;
                else
                    assert(isfile(p.reference_bundle),'msiq:if:Reference','Saved TX reference bundle is required.');
                    loaded=msiq.load_reference_bundle(p.reference_bundle); self.bundle=loaded.bundle;
                end
                assert(isfield(self.bundle,'tx_ref')&&isfield(self.bundle,'dsp_config'), ...
                    'msiq:if:Reference','Bundle must contain tx_ref and dsp_config.');
                self.cfg.waveform=self.bundle.dsp_config.waveform;
                self.cfg.receiver=self.bundle.dsp_config.receiver;
                self.cfg=msiq.fec.apply_reference(self.cfg,self.bundle.tx_ref);
                self.cfg.receiver.debug_pre_fec_only=true;
            end
            self.options.needed_devices=devices;
        end
        function open(self)
            if strcmp(self.p.mode,'mock')
                if ismember('board',self.options.needed_devices)
                    boardCfg=self.p.board; boardCfg.cancel_check=@()msiq.if_workbench('cancelled');
                    self.board=msiq.instruments.IfBoard(boardCfg); self.board.open();
                    if self.options.board_automatic, self.board.assertAutomaticReady(); end
                end
                self.event('mock_only',struct('real_instrument_access',false)); return;
            end
            d=self.options.needed_devices;
            % Open AWG first, so every subsequent failure has an owned OFF path.
            self.awg=msiq.instruments.open_session('awg',self.cfg.instrument.awg,'query_only');
            if ismember('scope',d)
                self.scope=msiq.instruments.open_session('scope',self.cfg.instrument.scope,'raw');
            end
            if ismember('board',d)
                boardCfg=self.p.board; boardCfg.cancel_check=@()msiq.if_workbench('cancelled');
                    self.board=msiq.instruments.IfBoard(boardCfg); self.board.open();
                if self.options.board_automatic, self.board.assertAutomaticReady(); end
            end
            if ~isempty(fieldnames(self.bundle))
                self.saveReference(self.path('tx_reference_bundle.mat'),self.p.reference_bundle);
                self.out.reference_hash=msiq.sha256_bytes(jsonencode(self.bundle));
            end
        end
        function check(self)
            drawnow;
            self.progress('',false);
            if msiq.if_workbench('cancelled'), error('msiq:if:Cancelled','Stop requested; no further control is permitted.'); end
        end
        function wait(self,seconds)
            t=tic;
            while toc(t)<seconds, self.check(); pause(min(.05,seconds-toc(t))); end
            self.check();
        end
        function event(self,name,value)
            self.out.events{end+1}=struct('name',name,'value',value,'elapsed_s',toc(self.clock));
            phase=name;
            if strcmp(name,'attempt_started'), phase=['capture_' value.role]; end
            self.progress(phase,false);
        end
        function setPoint(self,target)
            self.check();
            v=[target.pre_db target.i_db target.q_db];
            assert(all(isfinite(v))&&all(v>=0&v<=31.5)&&all(abs(2*v-round(2*v))<1e-9), ...
                'msiq:if:Setting','Settings must be on the 0:0.5:31.5 dB grid.');
            assert(~isempty(self.board),'msiq:if:Board','Board control is unavailable.');
            snapshot=self.board.snapshot();
            assert(snapshot.state_known,'msiq:if:BoardState','Board state unconfirmed; no retry.');
            % Only the selected board is controlled. Caller restores post start
            % before pre changes; the adapter checks every intermediate state.
            if target.pre_db~=snapshot.state.rf(self.p.subband)
                self.board.setAttenuation('rf',self.p.subband,target.pre_db);
            end
            self.board.setIQ(self.p.subband,target.i_db,target.q_db);
            self.setting=target;
            self.event('board_setting',self.boardState()); self.checkpoint();
        end
        function s=boardState(self)
            if isempty(self.board)
                s=struct('requested',self.setting,'sent',[], 'trusted_readback',[], ...
                    'provenance','manual_unverified','state_known',false);
                if strcmp(self.p.stage,'direct'), s.provenance='no_board_in_direct_path'; end
            else
                s=self.board.snapshot(); s.history=self.board.History;
                if strcmp(self.p.mode,'mock'), s.provenance='synthetic_mock_board';
                else, s.provenance='manual_confirmation_and_sent_commands'; end
            end
        end
        function raw=fresh(self)
            self.check(); self.wait(self.p.policy.settle_s);
            if strcmp(self.p.mode,'mock')
                assert(~self.p.mock.stale_capture,'msiq:if:StaleCapture','Fresh acquisition was not confirmed.');
                n=4096; fs=self.p.scope.sample_rate_hz; t=(0:n-1)'/fs;
                % Test transport: voltage depends on attenuation; quality is synthetic.
                gain=10.^((self.p.mock.gain_db-[self.setting.i_db self.setting.q_db]+20)/20);
                amp=.15*gain.*(self.amplitude/.2);
                x=[amp(1)*sin(2*pi*1e9*t),amp(2)*cos(2*pi*1e9*t)];
                channels=self.p.scope.channels;
                if isfield(self.p.board,'mapping')&&numel(channels)==2
                    mapped=zeros(size(x));
                    mapped(:,strcmp(channels,self.p.board.mapping.i_channel))=x(:,1);
                    mapped(:,strcmp(channels,self.p.board.mapping.q_channel))=x(:,2);
                    x=mapped;
                end
                if strcmp(self.p.stage,'tx_if'), x=.1*cos(2*pi*6.2e9*t); end
                records=cell(1,numel(channels));
                for k=1:numel(channels)
                    records{k}=struct('channel',channels{k},'samples',x(:,k), ...
                        'time_axis_s',t,'sample_rate_hz',fs,'descriptor',struct('source','IF mock fixture'));
                end
                raw=struct('channels',[records{:}],'captured_at',char(datetime('now')), ...
                    'fresh_confirmed',true,'mock',true,'model_window_s',self.p.scope.window_s);
                return;
            end
            f=self.p.scope.fresh;
            evidence=msiq.if_confirm_fresh(f,@(c)msiq.instruments.write_scpi(self.scope,c), ...
                @(c)msiq.instruments.query_scpi(self.scope,c),@()self.check(),@(s)self.wait(s));
            raw=msiq.instruments.capture_scope_raw(self.scope,self.p.scope.channels);
            raw.fresh_confirmed=true; raw.fresh_evidence=evidence;
        end
        function obs=capture(self,role,group,point)
            self.check(); self.captureCount=self.captureCount+1; attempt=self.captureCount;
            self.event('attempt_started',struct('attempt',attempt,'role',role,'group',group,'point',point));
            self.checkpoint();
            if strcmp(self.p.mode,'mock')
                if attempt==self.p.mock.cancel_capture, msiq.if_workbench('stop'); self.check(); end
                assert(attempt~=self.p.mock.fail_capture,'msiq:if:InjectedCapture','Injected capture failure.');
            end
            t=tic; raw=self.fresh();
            raw_path=self.path(sprintf('capture_%05d.mat',attempt));
            % Raw first: invalid axes, readback failures and DSP errors remain recoverable.
            capture_context=struct('attempt',attempt,'role',role,'group',group, ...
                'point',point,'setting',self.setting,'scale_requested_vdiv',self.scale);
            save(raw_path,'raw','capture_context','-v7.3');
            if ~isempty(self.scope)
                for k=1:numel(self.p.scope.channels)
                    self.scale(k)=msiq.instruments.read_scope_vertical_scale(self.scope,self.p.scope.channels{k});
                end
            end
            try
                [measurement,spectrum]=msiq.if_capture_observation(raw,self.p,self.cfg,self.scale);
            catch ex
                validation_error=struct('identifier',ex.identifier,'message',ex.message);
                save(raw_path,'validation_error','-append');
                self.event('capture_invalid',struct('attempt',attempt,'raw_path',raw_path,'error',validation_error));
                rethrow(ex);
            end
            obs=struct('attempt',attempt,'role',role,'group',group,'point',point, ...
                'nominal',[group point],'setting',self.setting,'board',self.boardState(), ...
                'scale_vdiv',self.scale,'power_v2',measurement.power_v2, ...
                'power_dbv2',measurement.power_dbv2,'peaks_v',measurement.peaks_v, ...
                'clipped',measurement.clipped,'clip_fraction',measurement.clip_fraction, ...
                'sample_rates_hz',measurement.sample_rates_hz,'windows_s',measurement.windows_s, ...
                'fresh_confirmed',true,'memory_mode',self.memoryMode, ...
                'reference_path',self.referencePath,'awg_level_requested_vpp',self.amplitude, ...
                'awg_level_is_measured',false, ...
                'metrics',self.invalidMetrics('not_demodulated'),'raw_path',raw_path, ...
                'seconds',toc(t),'range_changed',self.lastRangeChange);
            if strcmp(self.p.mode,'mock')
                assert(attempt~=self.p.mock.fail_save,'msiq:if:InjectedSave','Injected save failure.');
            end
            save(obs.raw_path,'raw','spectrum','obs','-v7.3'); % preserve before DSP
            if ~strcmp(self.p.stage,'tx_if')
                try
                    obs.metrics=self.metrics(raw,obs);
                catch ex
                    obs.metrics=self.invalidMetrics(ex.message);
                end
            end
            self.out.observations{end+1}=obs;
            self.checkpoint();
        end
        function m=invalidMetrics(~,why)
            m=struct('valid',false,'pre_error_count',NaN,'pre_bit_count',NaN, ...
                'pre_ber',NaN,'mer_db',NaN,'evm_rms',NaN,'reason',why);
        end
        function m=metrics(self,raw,obs)
            m=self.invalidMetrics('');
            if strcmp(self.p.mode,'mock')
                loss=max(0,self.p.mock.degrade_below_post_db-min(self.setting.i_db,self.setting.q_db));
                errors=round(loss*200); m.pre_bit_count=100000; m.pre_error_count=errors;
                m.pre_ber=errors/m.pre_bit_count; m.mer_db=30-3*loss;
                if self.lastRangeChange, m.mer_db=m.mer_db+self.p.mock.range_jump_db; end
                m.evm_rms=10^(-m.mer_db/20); m.valid=~obs.clipped&&self.captureCount~=self.p.mock.invalid_capture;
                m.reason='synthetic_test_transport';
                if ~m.valid, m.pre_ber=NaN; end
                return;
            end
            records=raw.channels;
            assert(numel(records)==2,'msiq:if:Channels','I/Q decoding requires two records.');
            lengths=arrayfun(@(r)numel(r.samples),records);
            assert(all(lengths==lengths(1)),'msiq:if:Waveform','I/Q record lengths differ; no silent truncation.');
            n=lengths(1);
            data=zeros(n,2); times=data;
            for k=1:2, data(:,k)=records(k).samples(1:n); times(:,k)=records(k).time_axis_s(1:n); end
            input=struct('samples',data,'time_axes',times,'sample_rate_hz',records(1).sample_rate_hz, ...
                'already_baseband',strcmp(self.p.stage,'rx_iq'),'iq_pair',true, ...
                'clip_fraction',obs.clip_fraction,'payload_pair','A');
            decoded=msiq.decode_capture(input,self.bundle.tx_ref,self.cfg);
            streams=decoded.primary_streams;
            m.valid=decoded.valid&&~obs.clipped;
            m.pre_error_count=sum([streams.pre_fec_bit_error_count]); m.pre_bit_count=sum([streams.pre_fec_bit_count]);
            m.pre_ber=m.pre_error_count/m.pre_bit_count;
            m.valid=m.valid && m.pre_bit_count>0 && isfinite(m.pre_ber);
            m.mer_db=mean([streams.mer_db]); m.evm_rms=mean([streams.evm_rms]);
            if ~m.valid, m.pre_ber=NaN; end
            save(self.path(sprintf('decode_%05d.mat',obs.attempt)),'decoded','-v7.3');
        end
        function obs=prepare(self,group,point,balance)
            self.lastRangeChange=false;
            obs=self.capture('trial',group,point);
            for k=0:self.p.scope.max_adjustments
                target=self.scale; changed=false;
                for c=1:numel(obs.peaks_v)
                    if obs.peaks_v(c)>=4*self.scale(c)*self.p.scope.headroom || ...
                            obs.peaks_v(c)<4*self.scale(c)*self.p.scope.headroom/4
                        candidates=self.p.scope.ranges_vdiv;
                        ix=find(4*candidates*self.p.scope.headroom>obs.peaks_v(c),1);
                        assert(~isempty(ix),'msiq:if:RangeBoundary','No approved nonclipping range.');
                        target(c)=candidates(ix); changed=changed||target(c)~=self.scale(c);
                    end
                end
                if ~changed, break; end
                assert(k<self.p.scope.max_adjustments,'msiq:if:RangeBudget','Scope adjustment limit reached.');
                self.setScale(target); self.lastRangeChange=true; obs=self.capture('range_trial',group,point);
            end
            assert(~obs.clipped,'msiq:if:Clipped','Clipping persists after range preparation.');
            if balance&&strcmp(self.p.stage,'rx_iq')
                assert(~isempty(self.board),'msiq:if:Board','Automatic balance requires a confirmed board.');
                self.board.assertAutomaticReady();
                assert(all(isfinite([self.p.policy.balance_tolerance_db self.p.policy.balance_step_db ...
                    self.p.policy.max_balance_adjustments]))&&self.p.policy.balance_step_db>0, ...
                    'msiq:if:BalancePolicy','Bounded balance policy is required.');
                stopReason='adjustment_budget';
                for k=1:self.p.policy.max_balance_adjustments
                    self.valid(obs);
                    difference=obs.power_dbv2(1)-obs.power_dbv2(2);
                    if abs(difference)<=self.p.policy.balance_tolerance_db, stopReason='within_tolerance'; break; end
                    old=self.setting; target=old; reference=obs;
                    stronger=1+(difference<0);
                    if strcmp(self.p.scope.channels{stronger},self.p.board.mapping.i_channel)
                        key='i'; target.i_db=old.i_db+self.p.policy.balance_step_db; value=target.i_db;
                    else
                        key='q'; target.q_db=old.q_db+self.p.policy.balance_step_db; value=target.q_db;
                    end
                    limit=self.p.board.limits.(key)(self.p.subband,2);
                    if value>min(31.5,limit), stopReason='approved_boundary'; break; end
                    self.setPoint(target); candidate=self.capture('balance',group,point); self.valid(candidate);
                    confirmedBad=false;
                    if self.worse(candidate,reference,false)
                        extra=self.repeat('balance_confirmation',group,point,2);
                        allResults=[{candidate},extra];
                        bad=cellfun(@(x)self.worse(x,reference,false),allResults);
                        confirmedBad=all(bad);
                        if ~confirmedBad, candidate=allResults{find(~bad,1,'last')}; end
                    end
                    noImprovement=abs(diff(candidate.power_dbv2))>=abs(difference);
                    if confirmedBad||noImprovement
                        self.setPoint(old); obs=reference;
                        if confirmedBad, stopReason='quality_degradation_confirmed'; else, stopReason='no_amplitude_improvement'; end
                        self.event('balance_reverted',struct('setting',old,'reason',stopReason)); break;
                    end
                    obs=candidate;
                end
                self.event('balance_stopped',struct('reason',stopReason, ...
                    'residual_difference_db',abs(diff(obs.power_dbv2))));
            end
        end
        function setScale(self,target)
            self.check();
            assert(all(ismember(target,self.p.scope.ranges_vdiv)),'msiq:if:Scale','Scale is outside approved list.');
            if ~isempty(self.scope)
                for k=1:numel(self.p.scope.channels)
                    self.check(); msiq.instruments.write_scpi(self.scope,sprintf('%s:VDIV %.15g',self.p.scope.channels{k},target(k)));
                    actual=msiq.instruments.read_scope_vertical_scale(self.scope,self.p.scope.channels{k});
                    assert(abs(actual-target(k))<max(1e-12,target(k)*1e-6),'msiq:if:ScaleReadback','Scope range readback differs.');
                end
            end
            self.scale=target; self.event('range_setting',target);
        end
        function valid(~,obs)
            assert(obs.metrics.valid&&isfinite(obs.metrics.pre_ber)&&obs.metrics.pre_bit_count>0, ...
                'msiq:if:InvalidMetrics','Invalid complete pre-FEC statistics: %s',obs.metrics.reason);
        end
        function yes=worse(self,a,b,recovery)
            self.valid(a); self.valid(b);
            assert(a.metrics.pre_bit_count==b.metrics.pre_bit_count,'msiq:if:Denominator','Statistical blocks differ.');
            ber=self.p.policy.ber_degradation; mer=self.p.policy.mer_degradation_db;
            if recovery, ber=self.p.policy.ber_recovery; mer=self.p.policy.mer_recovery_db; end
            assert(all(isfinite([ber mer])),'msiq:if:Tolerance','Comparison tolerances have not been confirmed.');
            if a.metrics.pre_error_count>0||b.metrics.pre_error_count>0
                yes=a.metrics.pre_ber>b.metrics.pre_ber+ber;
            else, yes=a.metrics.mer_db<b.metrics.mer_db-mer; end
        end
        function yes=better(self,a,b)
            self.valid(a); self.valid(b);
            assert(a.metrics.pre_bit_count==b.metrics.pre_bit_count,'msiq:if:Denominator','Statistical blocks differ.');
            if a.metrics.pre_error_count>0||b.metrics.pre_error_count>0
                yes=a.metrics.pre_ber<b.metrics.pre_ber;
            else, yes=a.metrics.mer_db>b.metrics.mer_db; end
        end
        function observations=repeat(self,role,group,point,count)
            frozen=struct('setting',self.setting,'scale',self.scale,'board',[]);
            if ~isempty(self.board), frozen.board=self.board.snapshot(); end
            observations=cell(1,count);
            for k=1:count
                assert(isequal(frozen.setting,self.setting)&&isequal(frozen.scale,self.scale),'msiq:if:RepeatDrift','Repeat settings drifted.');
                if ~isempty(self.board)
                    current=self.board.snapshot();
                    assert(current.state_known&&isequaln(current.state,frozen.board.state), ...
                        'msiq:if:RepeatDrift','Board state became unknown or changed during fixed repeats.');
                end
                observations{k}=self.capture(role,group,point);
                if ~strcmp(self.p.stage,'tx_if'), self.valid(observations{k}); end
                assert(isequal(frozen.scale,self.scale)&&isequal(frozen.setting,self.setting),'msiq:if:RepeatDrift','Settings changed during fixed repeats.');
            end
        end
        function scan(self)
            assert(~strcmp(self.p.stage,'tx_if'),'msiq:if:Stage','2D scanning requires RX I/Q metrics.');
            self.prepare(0,0,true); self.out.baseline=self.repeat('baseline',0,0,3);
            self.scanPoints();
        end
        function scanPoints(self)
            points=self.out.plan.points; groups=unique(points(:,1),'stable');
            for g=groups'
                best=[]; consecutive=0;
                if ismember(g,self.out.stopped_groups), continue; end
                rows=find(points(:,1)==g);
                if all(ismember(points(rows,:),self.out.completed_points,'rows')), continue; end
                % Reuse completed observations across recovery, never an unfinished point.
                history=self.out.observations;
                if isfield(self.out,'prior_observations'), history=[self.out.prior_observations,history]; end
                seen=zeros(0,2);
                for h=1:numel(history)
                    prior=history{h}; nominal=[prior.group prior.point];
                    if strcmp(prior.role,'formal')&&prior.group==g&& ...
                            ismember(nominal,self.out.completed_points,'rows')&&~ismember(nominal,seen,'rows')
                        seen(end+1,:)=nominal;
                        if isempty(best)||self.better(prior,best), best=prior; end
                    end
                end
                % Restore post attenuation before changing the pre setting.
                target=self.setting; target.i_db=self.p.scan.post_start_db; target.q_db=target.i_db;
                self.setPoint(target); target.pre_db=g; self.setPoint(target);
                for row=rows'
                    nominal=points(row,:);
                    if ismember(nominal,self.out.completed_points,'rows'), continue; end
                    target=self.setting; target.i_db=nominal(2); target.q_db=nominal(2); self.setPoint(target);
                    self.prepare(g,nominal(2),true);
                    a=self.repeat('formal',g,nominal(2),1); candidate=a{1};
                    reference=best; degraded=false;
                    if ~isempty(reference)&&self.worse(candidate,reference,false)
                        extra=self.repeat('formal',g,nominal(2),2); a=[a extra];
                        degraded=all(cellfun(@(x)self.worse(x,reference,false),a));
                    end
                    differentRange=~isempty(reference)&&~isequal(candidate.scale_vdiv,reference.scale_vdiv);
                    if ~isempty(reference)&&(self.lastRangeChange||differentRange)&& ...
                            (abs(candidate.metrics.mer_db-reference.metrics.mer_db)>self.p.policy.range_jump_db || (degraded&&consecutive>=2))
                        self.rangeDiagnostic(candidate,g,nominal(2));
                    end
                    if degraded, consecutive=consecutive+1; else, consecutive=0; end
                    if isempty(best)||self.better(candidate,best), best=candidate; end
                    self.out.completed_points(end+1,:)=nominal;
                    self.out.estimated_remaining_s=(size(points,1)-size(self.out.completed_points,1))*toc(self.clock)/max(1,size(self.out.completed_points,1));
                    self.event('point_completed',struct('nominal',nominal,'formal_count',numel(a),'degraded',degraded,'consecutive',consecutive));
                    self.checkpoint();
                    if consecutive>=3
                        self.out.stopped_groups(end+1)=g; self.event('local_direction_stop',g); self.checkpoint(); break;
                    end
                end
            end
        end
        function rangeDiagnostic(self,reference,group,point)
            original=self.scale; adjacent=original; candidates=self.p.scope.ranges_vdiv;
            for c=1:numel(original)
                ix=find(candidates>original(c),1);
                assert(~isempty(ix),'msiq:if:RangeAmbiguous','No adjacent wider approved range; paused.');
                adjacent(c)=candidates(ix);
            end
            boardSetting=self.setting;
            try
                a=self.repeat('range_diagnostic',group,point,1);
                self.setScale(adjacent);
                b=self.repeat('range_diagnostic',group,point,1);
                self.setScale(original);
            catch ex
                % Restore measurement configuration when possible; cancellation
                % prevents further normal control and is handled by shutdown.
                try, self.setScale(original); catch restoreEx, self.event('range_restore_failed',restoreEx.message); end
                rethrow(ex);
            end
            assert(isequal(boardSetting,self.setting),'msiq:if:RangeAmbiguous','Board changed during range comparison.');
            assert(~a{1}.clipped&&~b{1}.clipped&& ...
                abs(a{1}.metrics.mer_db-b{1}.metrics.mer_db)<=self.p.policy.mer_recovery_db&& ...
                abs(a{1}.metrics.pre_ber-b{1}.metrics.pre_ber)<=self.p.policy.ber_recovery, ...
                'msiq:if:RangeAmbiguous','Range influence cannot be excluded; board held and scan paused.');
            self.event('range_influence_excluded',reference.attempt);
        end
        function resume(self)
            loaded=load(fullfile(self.options.run_dir,'data','if_checkpoint.mat'),'out'); old=loaded.out;
            assert(strcmp(old.plan.signature,self.out.plan.signature),'msiq:if:ResumeIdentity','Plan/profile differs; start a new run.');
            self.out.parent_run=old.run_dir;
            self.out.prior_observations=old.observations;
            if isfield(old,'prior_observations'), self.out.prior_observations=[old.prior_observations,old.observations]; end
            self.out.prior_events=old.events;
            if isfield(old,'prior_events'), self.out.prior_events=[old.prior_events,old.events]; end
            self.checkpoint();
            if strcmp(self.p.mode,'live')
                assert(~strcmp(old.profile.wiring.confirmed_at,self.p.wiring.confirmed_at),'msiq:if:ResumeWiring','A new wiring confirmation is required.');
                assert(isfield(old,'reference_hash')&&strcmp(old.reference_hash,self.out.reference_hash),'msiq:if:ResumeReference','Reference differs.');
            end
            assert(numel(old.baseline)==3,'msiq:if:ResumeBaseline','Saved complete baseline is required.');
            % Recover in the same safe two-step path as a fresh scan group.
            target=self.setting; target.i_db=self.p.scan.post_start_db; target.q_db=target.i_db;
            self.setPoint(target); target.pre_db=old.baseline{1}.setting.pre_db; self.setPoint(target);
            self.setPoint(old.baseline{1}.setting); self.setScale(old.baseline{1}.scale_vdiv);
            baseline=self.repeat('recovery_baseline',0,0,3);
            for k=1:3
                assert(~self.worse(baseline{k},old.baseline{k},true)&&~self.worse(old.baseline{k},baseline{k},true), ...
                    'msiq:if:Recovery','Recovery tolerance failed; start a new run.');
            end
            self.out.baseline=baseline;
            self.out.completed_points=old.completed_points; self.out.stopped_groups=old.stopped_groups;
            self.event('recovery_passed',struct('history_retained',old.run_dir,'degradation_count',0));
            self.scanPoints();
        end
        function compareModes(self)
            assert(strcmp(self.p.stage,'direct'),'msiq:if:Stage','Mode comparison requires direct wiring.');
            p=self.p.comparison;
            assert(isfinite(p.power_tolerance_db)&&p.power_tolerance_db>=0&&isfinite(p.max_adjustments)&& ...
                all(isfinite(p.amplitude_bounds_vpp)),'msiq:if:PowerPolicy','Power matching bounds and tolerance are required.');
            fixed=self.scale; target=[];
            for k=1:6
                self.memoryMode=self.out.plan.mode_order{k}; self.switchMode();
                trial=self.capture('mode_trial',k,0);
                assert(~trial.clipped&&isequal(self.scale,fixed),'msiq:if:ComparisonRange','Clipping or range drift invalidates this comparison group.');
                if isempty(target), target=trial.power_dbv2; end
                for attempt=0:p.max_adjustments
                    delta=target-trial.power_dbv2;
                    if all(abs(delta)<=p.power_tolerance_db), break; end
                    assert(attempt<p.max_adjustments,'msiq:if:PowerMismatch','Power matching failed; start another group after preparation.');
                    self.amplitude=self.amplitude.*10.^(delta/20);
                    assert(all(self.amplitude>=p.amplitude_bounds_vpp(1)&self.amplitude<=p.amplitude_bounds_vpp(2)), ...
                        'msiq:if:Amplitude','Matching would exceed approved amplitude bounds.');
                    if strcmp(self.p.mode,'live')
                        o=self.p.tx_options; o.cfg_override=self.cfg; o.amplitude_vpp=self.amplitude;
                        self.check(); msiq.traditional_tx('awg_level',[],o);
                    end
                    trial=self.capture('power_match',k,0);
                    assert(~trial.clipped&&isequal(self.scale,fixed),'msiq:if:ComparisonRange','Clipping/range drift during matching.');
                end
                measured=self.repeat('mode_formal',k,0,1);
                assert(all(abs(measured{1}.power_dbv2-target)<=p.power_tolerance_db), ...
                    'msiq:if:PowerMismatch','Formal power drift invalidates this comparison group.');
            end
            self.out.comparison=self.comparisonSummary();
        end
        function switchMode(self)
            if strcmp(self.p.mode,'mock')
                self.event('awg_off_verified',true); self.event('mode_switch',self.memoryMode); return;
            end
            self.check(); msiq.instruments.set_awg_output(self.awg,false);
            assert(~any(msiq.instruments.read_awg_output_state(self.awg)),'msiq:if:AWGOff','AWG OFF readback failed.');
            o=self.p.tx_options; o.cfg_override=self.cfg; o.memory_mode=self.memoryMode; o.rdiv='DIV4'; o.seed=1;
            o.amplitude_vpp=self.amplitude; o.offset_v=[0 0];
            self.check(); plan=msiq.traditional_tx('awg_plan',[],o);
            assert(abs(plan.cfg.waveform.symbol_rate_hz-self.cfg.waveform.symbol_rate_hz)<1, ...
                'msiq:if:Baud','Mode has a different symbol rate.');
            expected=self.comparisonPlans{1+strcmp(self.memoryMode,'INT')};
            assert(isequal(plan.tx_ref.pairs(1).metrics_only(1).fec.coded_bits, ...
                expected.tx_ref.pairs(1).metrics_only(1).fec.coded_bits), ...
                'msiq:if:FrameMismatch','Execution frame differs from the compared preview.');
            assert(abs(plan.actual_waveform_sample_rate_hz-expected.actual_waveform_sample_rate_hz)<1, ...
                'msiq:if:Rates','Actual playback rate differs from preview.');
            self.check(); o.plan=plan; o.confirmation_phrase=plan.required_confirmation; o.enable_output=true;
            applied=msiq.traditional_tx('awg_apply',[],o);
            loaded=msiq.load_reference_bundle(applied.reference_bundle_path); self.bundle=loaded.bundle;
            self.modeSwitchCount=self.modeSwitchCount+1;
            self.saveReference(self.path(sprintf('reference_%s_%02d.mat',self.memoryMode,self.modeSwitchCount)), ...
                applied.reference_bundle_path);
            self.event('awg_applied',struct('reference_path',self.referencePath,'source_reference_path',applied.reference_bundle_path, ...
                'requested_amplitude_vpp',self.amplitude));
        end
        function saveReference(self,destination,source)
            % Materialize references when leaving the source run tree.
            msiq.save_reference_bundle(destination,self.bundle,source);
            stored=msiq.load_reference_bundle(destination);
            self.bundle=stored.bundle;
            self.referencePath=destination;
        end
        function summary=comparisonSummary(self)
            summary=struct('preferred','EXT','decision','tolerance_not_confirmed','modes',struct([]));
            allobs=self.out.observations;
            for k=1:2
                mode={'EXT','INT'}; selected=allobs(cellfun(@(x)strcmp(x.role,'mode_formal')&&strcmp(x.memory_mode,mode{k}),allobs));
                ber=cellfun(@(x)x.metrics.pre_ber,selected); mer=cellfun(@(x)x.metrics.mer_db,selected);
                powers=cellfun(@(x)x.power_dbv2,selected,'UniformOutput',false);
                entry=struct('mode',mode{k},'count',numel(ber),'ber_mean',mean(ber), ...
                    'ber_std',std(ber),'mer_mean',mean(mer),'mer_std',std(mer),'power_dbv2',vertcat(powers{:}));
                summary.modes=[summary.modes entry];
            end
            p=self.p.comparison;
            if isfinite(p.ber_advantage)&&isfinite(p.mer_advantage_db)
                a=summary.modes(1); b=summary.modes(2); summary.decision='no_clear_advantage';
                if (max(a.ber_mean,b.ber_mean)>0&&a.ber_mean-b.ber_mean>p.ber_advantage)|| ...
                        (a.ber_mean==0&&b.ber_mean==0&&b.mer_mean-a.mer_mean>p.mer_advantage_db)
                    summary.preferred='INT'; summary.decision='configured_advantage';
                end
            end
        end
        function path=path(self,name)
            path=msiq.artifact_path(self.out.run_dir,name,'write');
        end
        function result=candidates(self)
            result={}; history=self.out.observations;
            if isfield(self.out,'prior_observations'), history=[self.out.prior_observations history]; end
            for k=1:size(self.out.completed_points,1)
                nominal=self.out.completed_points(k,:);
                items=history(cellfun(@(x)strcmp(x.role,'formal')&&x.group==nominal(1)&&x.point==nominal(2),history));
                if isempty(items), continue; end
                result{end+1}=struct('nominal',nominal,'actual_setting',items{end}.setting, ...
                    'formal_count',numel(items),'worst_pre_ber',max(cellfun(@(x)x.metrics.pre_ber,items)), ...
                    'minimum_mer_db',min(cellfun(@(x)x.metrics.mer_db,items)), ...
                    'group_has_observed_boundary',ismember(nominal(1),self.out.stopped_groups));
            end
        end
        function checkpoint(self)
            if isempty(self.out.run_dir), return; end
            self.out.elapsed_s=toc(self.clock); out=self.out;
            path=self.path('if_checkpoint.mat'); temporary=[path '.tmp'];
            save(temporary,'out','-v7.3');
            [ok,message]=movefile(temporary,path,'f'); assert(ok,'msiq:if:Checkpoint','%s',message);
            state=rmfield(out,'observations');
            Result_Atomic_Write_Json(self.path('if_state.json'),state);
            if ~isempty(out.observations)
                rows=cell(1,numel(out.observations));
                for k=1:numel(rows)
                    o=out.observations{k};
                    rows{k}=struct('attempt',o.attempt,'role',o.role,'group',o.group,'point',o.point, ...
                        'pre_db',o.setting.pre_db,'i_db',o.setting.i_db,'q_db',o.setting.q_db, ...
                        'valid',o.metrics.valid,'pre_error_count',o.metrics.pre_error_count, ...
                        'pre_bit_count',o.metrics.pre_bit_count,'pre_ber',o.metrics.pre_ber,'mer_db',o.metrics.mer_db);
                end
                Result_Atomic_Write_Json(self.path('observations.json'),[rows{:}]);
            end
            self.progress('',false);
        end
        function shutdown(self)
            if self.shutdownDone, return; end
            self.progress('shutting_down',true);
            report=struct('awg_off_verified',false,'scope_auto',false,'errors',{{}});
            if strcmp(self.p.mode,'mock')
                report.awg_off_verified=true; report.scope_auto=true; report.mock=true;
                if self.p.mock.fail_shutdown
                    report.awg_off_verified=false; report.errors{end+1}='Injected AWG OFF verification failure.';
                end
            else
                if ~isempty(self.awg)
                    try
                        msiq.instruments.set_awg_output(self.awg,false);
                        report.awg_off_verified=~any(msiq.instruments.read_awg_output_state(self.awg));
                        assert(report.awg_off_verified,'msiq:if:Shutdown','AWG shutdown verification failed.');
                    catch ex, report.errors{end+1}=ex.message; end
                end
                if ~isempty(self.scope)
                    try, msiq.instruments.write_scpi(self.scope,'TRMD AUTO'); report.scope_auto=true;
                    catch ex, report.errors{end+1}=ex.message; end
                end
                for session={self.scope,self.awg}
                    if ~isempty(session{1})
                        try, msiq.instruments.close_session(session{1}); catch ex, report.errors{end+1}=ex.message; end
                    end
                end
            end
            if ~isempty(self.board)
                self.out.board_final=self.boardState();
                try, self.board.close(); catch ex, report.errors{end+1}=ex.message; end
            end
            report.process_kill_protection=false;
            self.out.shutdown=report;
            self.shutdownDone=true;
            if ~isempty(report.errors), self.out.status='shutdown_failed'; end
            self.progress('shutdown_complete',true);
        end
        function emergencyShutdown(self)
            if self.shutdownDone, return; end
            self.out.status='interrupted';
            self.shutdown();
            try, self.checkpoint(); catch, end
        end
    end
    methods (Access=private)
        function progress(self,phase,force)
            % Presentation failures must never interrupt acquisition or cleanup.
            if ~isempty(phase), self.progressPhase=phase; end
            if isempty(self.progressCallback), return; end
            elapsed=toc(self.clock);
            if ~force && elapsed-self.progressLast<.25, return; end
            self.progressLast=elapsed;
            try
                observations=self.out.observations;
                formal=sum(cellfun(@(o)ismember(o.role, ...
                    {'formal','mode_formal','baseline','recovery_baseline'}),observations));
                update=struct('phase',self.progressPhase,'status',self.out.status, ...
                    'elapsed_s',elapsed,'formal_count',formal, ...
                    'observation_count',numel(observations));
                if isfinite(self.out.estimated_remaining_s)
                    update.estimated_remaining_s=self.out.estimated_remaining_s;
                end
                if ~isempty(fieldnames(self.out.shutdown)), update.shutdown=self.out.shutdown; end
                self.progressCallback(update);
            catch
                % Disable a failed callback for this session; preserve run results.
                self.progressCallback=[];
            end
        end
    end
end
