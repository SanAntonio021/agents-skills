function note = validate_rx_workbench(output_dir)
%VALIDATE_RX_WORKBENCH Exercise the complete GUI with an in-memory scope.
visual_guard = visual_test_lock(); %#ok<NASGU>
if nargin < 1
    if msiq.validation_artifacts('active')
        output_dir = msiq.validation_artifacts('directory');
    else
        root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
        output_dir = fullfile(root,'results','analysis', ...
            ['RX_GUI_' char(datetime('now','Format','yyyyMMdd_HHmmss'))]);
    end
end
if ~isfolder(output_dir), mkdir(output_dir); end
msiq.validate_rx_mock_config(output_dir);
msiq.validate_rx_scope_settings(fullfile(output_dir,'settings_backend'));
msiq.validate_rx_observation();
existing_figures=findall(0,'Type','figure');
figure_guard=onCleanup(@() close_new_figures(existing_figures));
note=validate_with_mock(output_dir);
msiq.validate_rx_settings_gui(fullfile(output_dir,'settings_extended'));
msiq.validate_rx_consistency(output_dir);
msiq.validate_rx_preferences(output_dir);
msiq.validate_rx_async(output_dir);
msiq.validate_rx_observation_worker();
end

function note=validate_with_mock(output_dir)
writes = {}; queries = {}; connections = 0; captures = 0;
scale = [.1 .2 .3 .4]; offset = [0 .01 .02 .03]; timebase = 2e-9; trigger_delay = 0;
enabled = true(1,4); limit = Inf(1,4);
query_failure = ''; write_failure = ''; invalid_reply = ''; connect_failure = false;
capture_failure = false; nested_edit = false; capture_drift = false; gui = [];
acquisition_rate=40e9; memory_depth=2500000;
io = struct('open',@open_mock,'query',@query_mock,'write',@write_mock, ...
    'capture',@capture_mock,'close',@close_mock);
options = struct('visible',false,'maximize',false,'position',[40 40 1500 900], ...
    'synchronous_startup',true,'use_timer',false,'find_reference',false,'io',io, ...
    'config',msiq.rx_mock_config());
fig = msiq.rx_workbench_app(options); gui = fig;
cleanup = onCleanup(@() close_if_valid(fig));
state = get_state();
assert(state.connected && state.running && numel(state.scope_status.channels)==4);
assert(isempty(writes) && connections==1,'Startup must be read-only.');
for k=1:4
    assert(any(strcmp(queries,sprintf('C%d:VDIV?',k))));
    assert(any(strcmp(queries,sprintf('C%d:OFST?',k))));
end
tick(); tick();
state = get_state();
if isfield(state,'last_exception'), rethrow(state.last_exception); end
assert(connections==1 && isfield(state.raw,'channels'),'Refresh must not reconnect or discard data.');
assert(abs(state.plot_state.frequency_limit_hz-20e9)<1e3, ...
    'Frequency limit %.12g, ADC %.12g; reasons: %s / %s', ...
    state.plot_state.frequency_limit_hz,state.scope_status.sample_rate_hz, ...
    state.plot_state.spectra{1}.reason,state.plot_state.spectra{2}.reason);
assert(state.plot_state.last_sample_count(1)==8001 && state.plot_state.last_sample_count(2)==801);
axes_list = live_axes(state);
assert(all(cellfun(@(x) strcmp(x,'on'),get(axes_list,'Visible'))));
wave1 = findobj(axes_list(1),'Tag','rx_waveform');
wave2 = findobj(axes_list(3),'Tag','rx_waveform');
assert(abs(wave1.XData(1)+10)<1e-8 && abs(wave2.XData(1)+9.5)<1e-8, ...
    'Do not independently zero the two time axes.');
saved_raw=state.raw; saved_limits=get(axes_list(1),'YLim');
capture_drift=true; tick(); capture_drift=false; state=get_state();
assert(state.connected && state.running && state.raw_stale);
assert(isequaln(saved_raw,state.raw) && isequal(saved_limits,get(axes_list(1),'YLim')));
assert(contains(state.stale_reason,'offset_v'));
tick(); state=get_state(); assert(~state.raw_stale);
assert(state.capture_rejections==0);
saved_raw=state.raw; captures_before=captures; capture_drift=true;
tick(); tick(); tick(); state=get_state();
assert(state.connected && state.paused && ~state.running && state.capture_rejections==3);
assert(isequaln(saved_raw,state.raw) && captures==captures_before+3);
assert(contains(get(state.home.h_status,'String'),'已暂停'));
assert(contains(get(state.home.h_status,'TooltipString'),' -> '));
tick(); tick(); assert(captures==captures_before+3,'Synchronous rejection loop never stopped.');
capture_drift=false; invoke(state.home.h_play); tick(); state=get_state();
assert(state.running && ~state.raw_stale && state.capture_rejections==0 && connections==1);

invoke(state.home.h_pause);
write_before = numel(writes);
previous_upper = get(axes_list(2),'YLim'); previous_upper=previous_upper(2);
set(state.home.h_psd_min,'String','-135'); invoke(state.home.h_psd_min);
assert(isequal(get(axes_list(2),'YLim'),[-135 previous_upper]));
assert(numel(writes)==write_before,'Display edits must not write the scope.');
set(state.home.h_vdiv1,'String','.1234'); invoke(state.home.h_vdiv1);
assert(numel(writes)==write_before+1 && startsWith(writes{end},'C1:VDIV '));
assert(abs(str2double(get(state.home.h_vdiv1,'String'))-.125)<1e-12, ...
    'Accepted hardware normalization must be shown.');
state=get_state();
assert(abs(state.scope_status.channels(1).offset_v-offset(1))<1e-12);
assert(abs(str2double(get(state.home.h_off1,'String'))-offset(1))<1e-12, ...
    'Scale-dependent offset normalization was not read back.');
assert(scale(2)==.2 && offset(2)==.01);
set(state.home.h_off2,'String','-.023'); invoke(state.home.h_off2);
assert(startsWith(writes{end},'C2:OFST '));
set(state.home.h_tdiv,'String','5'); invoke(state.home.h_tdiv);
assert(startsWith(writes{end},'TDIV ') && abs(timebase-5e-9)<1e-18);
assert(get_state().scope_status.sample_rate_hz==acquisition_rate && ...
    get_state().scope_status.memory_depth==memory_depth);
set(state.home.h_trdl,'String','2.5'); invoke(state.home.h_trdl);
assert(startsWith(writes{end},'TRDL ') && abs(trigger_delay-2.5e-9)<1e-21, ...
    'Horizontal position was not written in seconds.');
set(state.home.h_trdl,'String','-3.5'); invoke(state.home.h_trdl);
assert(startsWith(writes{end},'TRDL ') && abs(trigger_delay+3.5e-9)<1e-21, ...
    'Negative horizontal position was rejected.');
state=get_state(); assert(abs(state.scope_status.trigger_delay_s+3.5e-9)<1e-21);
write_before = numel(writes);
set(state.home.h_vdiv1,'String','bad'); invoke(state.home.h_vdiv1);
assert(numel(writes)==write_before);
set(state.home.h_vdiv1,'String','.125'); invoke(state.home.h_vdiv1);

% Switching loads the actual new channel, never the prior channel's targets.
set(state.home.h_ch1,'Value',3); invoke(state.home.h_ch1);
state = get_state();
assert(strcmp(state.channels{1},'C3') && str2double(get(state.home.h_vdiv1,'String'))==.3);
assert(numel(writes)==write_before);
set(state.home.h_ch2,'Value',3); invoke(state.home.h_ch2);
state = get_state(); assert(isequal(state.channels,{'C3','C2'}));
assert(get(state.home.h_ch2,'Value')==2);
invoke(state.home.h_play); assert(numel(writes)==write_before);
tick();
scale(3)=.35; offset(3)=.04;
tick(); state=get_state();
assert(str2double(get(state.home.h_vdiv1,'String'))==.35);
set(state.home.h_off1,'String','.061'); % Uncommitted keyboard text must survive readback.
tick(); assert(strcmp(get(state.home.h_off1,'String'),'.061'));
invoke(state.home.h_off1); assert(startsWith(writes{end},'C3:OFST '));

% An edit delivered during capture is queued until the complete read finishes.
nested_edit=true; write_before=numel(writes);
tick(); nested_edit=false;
assert(numel(writes)==write_before+1 && startsWith(writes{end},'C2:OFST '));
enabled(2)=false; tick(); state=get_state();
assert(state.connected && isempty(state.raw.channels(2).samples));
assert(isempty(findall(state.home.axes.spectrum_bottom,'Tag','rx_spectrum_band')));
assert(isnan(getappdata(state.home.axes.spectrum_bottom,'rx_band_power_dbm')));
enabled(2)=true; tick();

% Failed field write preserves the typed value and offers an inline retry.
state=get_state(); write_failure='C3:VDIV';
set(state.home.h_vdiv1,'String','.4'); invoke(state.home.h_vdiv1);
state=get_state(); data=get(state.home.h_vdiv1,'UserData');
assert(~state.connected && ~state.running && strcmp(get(data.retry,'Visible'),'on'));
assert(strcmp(get(data.current,'String'),'--'));
assert(contains(get(data.error,'TooltipString'),'C3:VDIV'));
write_failure=''; invoke(data.retry);
state=get_state(); assert(state.connected && abs(scale(3)-.4)<1e-12);
invoke(state.home.h_play);

% A malformed readback cannot be reported as success.
invalid_reply='C3:OFST?'; set(state.home.h_off1,'String','.07'); invoke(state.home.h_off1);
state=get_state(); assert(~state.connected);
invalid_reply=''; invoke(state.home.h_play);

query_failure='C2:VDIV?'; tick(); state=get_state();
assert(~state.connected && ~state.running);
assert(contains(get(state.home.h_status,'String'),'C2:VDIV?'));
query_failure=''; before=connections; invoke(state.home.h_play); tick();
assert(get_state_connected() && connections==before+1);

capture_failure=true; tick(); state=get_state();
assert(~state.connected && ~state.running && isfield(state.raw,'channels'));
capture_failure=false; invoke(state.home.h_play); tick();

% A disabled/unimplemented page must not issue hidden hardware writes.
state=get_state(); write_before=numel(writes);
invoke(state.home.h_single);
assert(numel(writes)==write_before && get_state_page()=="single");
invoke(state.pages.h_single_start);
assert(numel(writes)==write_before && get_state_page()=="single");
original_position=get(fig,'Position');
set(fig,'Position',[original_position(1:3) original_position(4)-100]); drawnow;
invoke(state.pages.back_single); tick();
assert(numel(writes)==write_before && get_state_connected());
assert(isequal(getappdata(state.home.plot_panel,'rx_layout_size'), ...
    [original_position(3) original_position(4)-100]));
set(fig,'Position',original_position); drawnow;

state=get_state(); invoke(state.home.h_pause);
set(state.home.h_ch1,'Value',1); invoke(state.home.h_ch1);
invoke(state.home.h_play); tick();
limit(1)=5e9; tick(); state=get_state();
assert(getappdata(state.home.axes.spectrum_top,'rx_effective_limit_hz')==5e9);
assert(max(get(findobj(state.home.axes.spectrum_top,'Tag','rx_spectrum_line'),'XData'))<=5+1e-9);
limit(1)=Inf; tick();

% Both even and odd FFT lengths integrate to A^2/(2R) for an in-band tone.
state=get_state();
set(state.home.h_center,'String','1'); invoke(state.home.h_center);
set(state.home.h_bandwidth,'String','1');
invoke(state.home.h_bandwidth); state=get_state();
expected=10*log10(.04^2/2/50*1000);
assert(abs(getappdata(state.home.axes.spectrum_top,'rx_band_power_dbm')-expected)<.02);
for k=1:30, tick(); end
state=get_state();
for ax=live_axes(state)
    assert(strcmp(get(ax,'Visible'),'on') && strcmp(get(ax,'Box'),'on'));
    assert(~isempty(get(get(ax,'XLabel'),'String')) && ~isempty(get(ax,'XTickLabel')));
end
assert(numel(findall(state.home.axes.spectrum_top,'Tag','rx_spectrum_band'))==1);
assert(numel(findall(state.home.axes.spectrum_bottom,'Tag','rx_spectrum_band'))==1);

% Exercise Swing document/focus/action events without OS-wide key injection.
state=get_state(); set(fig,'Visible','on'); figure(fig);
set(state.home.scroll,'Value',get(state.home.scroll,'Max')); invoke(state.home.scroll);
write_before=numel(writes);
edit_and_commit(state.home.h_vdiv1,'0.175','focus',@tick);
assert(numel(writes)==write_before+1 && startsWith(writes{end},'C1:VDIV '), ...
    'Losing edit focus: expected %d writes, got %d; text=%s', ...
    write_before+1,numel(writes),get(state.home.h_vdiv1,'String'));
edit_and_commit(state.home.h_vdiv1,'0.18','enter');
assert(numel(writes)==write_before+2 && abs(scale(1)-.18)<1e-12, ...
    'Enter did not commit the focused field.');
invoke(state.home.h_vdiv1);
assert(numel(writes)==write_before+2,'An unchanged normalized value was written again.');
invoke(state.home.h_settings);
edit_and_commit(state.home.h_psd_min,'-130','focus',@tick);
state=get_state();
assert(state.plot_state.psd_ylim(1)==-130 && numel(writes)==write_before+2, ...
    'An in-progress display edit was overwritten or wrote hardware.');
invoke(state.home.h_auto_psd);
invoke(state.home.h_settings);
write_before=numel(writes);
edit_and_commit(state.home.h_trdl,'-1.25','focus',@tick);
assert(numel(writes)==write_before+1 && strcmp(writes{end},'TRDL -1.25e-09'));
state=get_state(); data=get(state.home.h_trdl,'UserData');
assert(abs(state.scope_status.trigger_delay_s+1.25e-9)<1e-21 && ...
    strcmp(get(data.current,'String'),'-1.25') && strcmp(get(data.unit,'String'),'ns'));
edit_and_commit(state.home.h_trdl,'0','enter');
assert(numel(writes)==write_before+2 && trigger_delay==0);
invoke(state.home.h_trdl); tick(); tick();
assert(numel(writes)==write_before+2,'Observation must not repeat TRDL writes.');
scale(1:2)=.015; offset(1:2)=0; timebase=2e-9;
tick();
for size_value = {[1500 900],[1100 700]}
    dim=size_value{1};
    set(fig,'Position',[40 40 dim]);
    resize=get(fig,'SizeChangedFcn'); resize(fig,[]);
    state=get_state(); set(state.home.scroll,'Value',get(state.home.scroll,'Max')); invoke(state.home.scroll);
    drawnow;
    check_layout(fig,state);
    snapshot(fig,fullfile(output_dir,sprintf('RX_%dx%d_home.png',dim)));
    invoke(state.home.h_settings); drawnow;
    check_scroll(state);
    snapshot(fig,fullfile(output_dir,sprintf('RX_%dx%d_settings.png',dim)));
    invoke(state.home.h_settings);
end
close(fig); clear cleanup;

connect_failure=true;
fig=msiq.rx_workbench_app(options); gui=fig;
cleanup=onCleanup(@() close_if_valid(fig));
state=get_state(); assert(~state.connected && ~state.busy);
assert(contains(get(state.home.h_status,'String'),'injected connect timeout'));
connect_failure=false;
set(state.home.h_vdiv1,'String','.225'); invoke(state.home.h_vdiv1);
write_before=numel(writes); invoke(state.home.h_play);
assert(numel(writes)==write_before,'Connecting must not itself commit pending edits.');
tick(); assert(numel(writes)==write_before+1 && startsWith(writes{end},'C1:VDIV '));
close(fig); clear cleanup;

query_failure='*IDN?';
fig=msiq.rx_workbench_app(options); gui=fig;
cleanup=onCleanup(@() close_if_valid(fig));
state=get_state(); assert(~state.connected && ~state.busy);
query_failure=''; close(fig); clear cleanup;

% Regression for missing record timing: do not substitute ADC rate silently.
fixture=make_records({'C1','C2'});
fixture.channels(2).sample_rate_hz=NaN;
fixture.channels(2).time_axis_s=[];
fig=msiq.rx_workbench_app(setfield(options,'auto_connect',false)); %#ok<SFLD>
cleanup=onCleanup(@() close_if_valid(fig));
state=getappdata(fig,'rx_workbench_state');
plot_state=msiq.plotting.rx_live_dashboard(state.home.axes,fixture, ...
    struct('sample_rate_hz',40e9),struct(),struct());
assert(isempty(plot_state.spectra{2}.frequency_hz));
assert(contains(plot_state.spectra{2}.reason,'间隔'));
close(fig); clear cleanup;

bundle=struct('route',struct('scope_channels',{{'C1','C2'}}), ...
    'desired',struct(),'tx_ref',struct('frame',struct('reference_payload_policy','metrics_only', ...
    'occupied_bandwidth_hz',3e9)),'execution',struct('status','applied'), ...
    'reference_payload_policy','metrics_only', ...
    'dsp_config',struct('waveform',struct('occupied_bandwidth_hz',3e9,'if_center_hz',.25e9)));
reference_path=fullfile(output_dir,'mock_reference_bundle.mat');
save(reference_path,'bundle');
reference_options=options; reference_options.reference_bundle=reference_path;
fig=msiq.rx_workbench_app(reference_options); gui=fig;
cleanup=onCleanup(@() close_if_valid(fig));
state=get_state();
assert(isempty(state.reference_bundle) && ~state.first_capture_complete);
tick(); state=get_state();
assert(state.first_capture_complete && isempty(state.reference_bundle), ...
    'Historical lookup must not precede the first displayed capture.');
await_reference(); state=get_state();
assert(state.plot_state.bandwidth_hz==3e9 && state.plot_state.center_hz==.25e9);
invoke(state.home.h_pause); set(state.home.h_ch1,'Value',3); invoke(state.home.h_ch1);
state=get_state(); assert(isempty(state.reference_bundle));
close(fig); clear cleanup;
bundle=rmfield(bundle,'dsp_config'); save(reference_path,'bundle');
fig=msiq.rx_workbench_app(reference_options); gui=fig;
cleanup=onCleanup(@() close_if_valid(fig)); tick(); await_reference(); state=get_state();
assert(state.plot_state.bandwidth_hz==3e9 && state.plot_state.center_hz==0);
close(fig); clear cleanup;

% Parseval power check includes the last bin for odd FFT lengths.
fig=msiq.rx_workbench_app(setfield(options,'auto_connect',false)); %#ok<SFLD>
cleanup=onCleanup(@() close_if_valid(fig)); state=getappdata(fig,'rx_workbench_state');
for count=[800 801]
    fixture=make_records({'C1','C2'});
    for fft_channel=1:2
        t=(0:count-1)'/40e9;
        fixture.channels(fft_channel).samples=cos(2*pi*.499*(0:count-1)');
        fixture.channels(fft_channel).time_axis_s=t;
        fixture.channels(fft_channel).sample_rate_hz=40e9;
    end
    plot_state=msiq.plotting.rx_live_dashboard(state.home.axes,fixture, ...
        msiq.instruments.rx_scope_state([],io.query), ...
        struct('center_hz',10e9,'bandwidth_hz',20e9),struct());
    spec=plot_state.spectra{1};
    window=.5-.5*cos(2*pi*(0:count-1)'/count);
    expected_power=sum((fixture.channels(1).samples.*window).^2)/sum(window.^2)/50;
    actual_power=sum(10.^(spec.power_dbm_hz/10))*1e-3*spec.delta_f_hz;
    assert(abs(actual_power/expected_power-1)<1e-8);
end
close(fig); clear cleanup;

timer_options=options; timer_options.use_timer=true;
timer_options.synchronous_startup=false; timer_options.refresh_period_s=.15;
before_connections=connections; before_captures=captures;
fig=msiq.rx_workbench_app(timer_options); gui=fig;
cleanup=onCleanup(@() close_if_valid(fig));
deadline=tic;
while captures<before_captures+3 && toc(deadline)<5
    pause(.05); drawnow;
end
state=get_state();
assert(captures>=before_captures+3 && connections==before_connections+1, ...
    'The live timer must capture repeatedly without reconnecting.');
invoke(state.home.h_pause); before_captures=captures;
pause(.4); drawnow;
assert(captures==before_captures);
close(fig); clear cleanup;
note=sprintf('RX GUI mock assertions passed; full-window screenshots: %s',output_dir);
fprintf('%s\n',note);

    function session=open_mock(~)
        connections=connections+1;
        if connect_failure, error('mock:Connect','injected connect timeout'); end
        session=struct('mock',true,'kind','scope');
    end
    function response=query_mock(~,command)
        queries{end+1}=command;
        if strcmp(command,query_failure), error('mock:Timeout','injected query timeout'); end
        if strcmp(command,invalid_reply), response='invalid value'; return; end
        switch command
            case '*IDN?', response='LECROY,SDA845ZI-A,MOCK,8.1.0'; return;
            case 'TDIV?', response=sprintf('TDIV %.15g S',timebase); return;
            case 'TRDL?', response=sprintf('TRDL %.15g S',trigger_delay); return;
            case 'MSIZ?', response=sprintf('MSIZ %.15g',memory_depth); return;
            case 'BWL?'
                response='BWL ';
                for channel_index=1:4
                    if isinf(limit(channel_index)), txt='OFF'; else, txt=sprintf('%gGHZ',limit(channel_index)/1e9); end
                    response=[response sprintf('C%d,%s,',channel_index,txt)]; %#ok<AGROW>
                end
                return;
        end
        if contains(command,'Horizontal.SampleRate'), response=sprintf('%.15g',acquisition_rate); return; end
        token=regexp(command,'^C([1-4]):(VDIV|OFST|TRA|CPL)\?$','tokens','once');
        if ~isempty(token)
            channel_index=str2double(token{1});
            switch token{2}
                case 'VDIV', response=sprintf('C%d:VDIV %.12g V',channel_index,scale(channel_index));
                case 'OFST', response=sprintf('C%d:OFST %.12g V',channel_index,offset(channel_index));
                case 'TRA'
                    if enabled(channel_index), response='ON'; else, response='OFF'; end
                case 'CPL', response='D50';
            end
            return;
        end
        if contains(command,'InterpolateType')
            if contains(command,'.C1.'), response='Sinxx'; else, response='Linear'; end
        elseif contains(command,'AverageSweeps'), response='1';
        elseif contains(command,'EnhanceResType'), response='None';
        elseif contains(command,'OptimizeGroupDelay'), response='Flatness';
        else
            response='Object does not support this property';
        end
    end
    function write_mock(~,command)
        writes{end+1}=command;
        if ~isempty(write_failure) && startsWith(command,write_failure), error('mock:Write','injected write timeout'); end
        token=regexp(command,'^(C([1-4]):)?(VDIV|OFST|TDIV|TRDL) (.*)$','tokens','once');
        assert(~isempty(token),'Unexpected instrument write.');
        value=str2double(token{end});
        if startsWith(command,'TDIV')
            timebase=value; acquisition_rate=80e9; memory_depth=4000000;
        elseif startsWith(command,'TRDL')
            trigger_delay=value;
        else
            ch=str2double(command(2));
            if contains(command,':VDIV')
                scale(ch)=round(value/.005)*.005; offset(ch)=.025;
            else
                offset(ch)=value;
            end
        end
    end
    function raw=capture_mock(~,channels)
        captures=captures+1;
        if capture_failure, error('mock:Transport','injected C2:WAVEFORM? ALL timeout'); end
        if nested_edit
            n=numel(writes); s=get_state();
            set(s.home.h_off2,'String','.081'); invoke(s.home.h_off2);
            assert(numel(writes)==n,'Field write interleaved with an active capture.');
        end
        raw=make_records(channels);
        if capture_drift, offset(1)=offset(1)+.01; end
    end
    function raw=make_records(channels)
        records=repmat(struct('channel','','samples',[],'time_axis_s',[], ...
            'sample_rate_hz',NaN),1,numel(channels));
        for j=1:numel(channels)
            if strcmp(channels{j},'C1'), rate=400e9; else, rate=40e9; end
            n=round(timebase*10*rate)+1;
            start=-10e-9;
            if strcmp(channels{j},'C2'), start=start+.5e-9; end
            t=start+(0:n-1)'/rate;
            records(j)=struct('channel',channels{j},'samples',.04*cos(2*pi*1e9*t), ...
                'time_axis_s',t,'sample_rate_hz',rate);
        end
        raw=struct('channels',records);
    end
    function close_mock(~)
    end
    function state=get_state()
        state=getappdata(gui,'rx_workbench_state');
    end
    function yes=get_state_connected()
        s=get_state(); yes=s.connected;
    end
    function page=get_state_page()
        s=get_state(); page=s.page;
    end
    function tick()
        cb=getappdata(gui,'rx_workbench_tick'); cb([],[]);
    end
    function await_reference()
        started=tic;
        while toc(started)<60
            tick(); s=get_state();
            if ~s.reference_pending && ~s.reference_busy, return; end
            pause(.02);
        end
        error('msiq:validation:ReferenceTimeout','File-only reference lookup did not finish.');
    end
end

function invoke(handle)
callback=get(handle,'Callback'); callback(handle,[]);
end

function axes_list=live_axes(state)
axes_list=[state.home.axes.wave_top state.home.axes.spectrum_top ...
    state.home.axes.wave_bottom state.home.axes.spectrum_bottom];
end

function check_layout(fig,state)
axes_list=live_axes(state);
rectangles=zeros(4,4);
for k=1:4
    ax=axes_list(k); rectangles(k,:)=getpixelposition(state.home.plot_frames(k),true);
    position=get(ax,'Position'); inset=get(ax,'TightInset');
    bounds=[position(1:2)-inset(1:2),position(3:4)+inset(1:2)+inset(3:4)];
    outer=[0 0 rectangles(k,3:4)];
    assert(all(bounds(1:2)>=outer(1:2)-2) && all(bounds(1:2)+bounds(3:4)<=outer(1:2)+outer(3:4)+2), ...
        'Axes decorations escaped their allocated cell.');
    assert(position(3)>300 && position(4)>130,'Plots were squeezed too far.');
    title_rect=get(state.home.plot_titles(k),'Position');
    metric_rect=get(state.home.plot_metrics(k),'Position');
    assert(~overlap(title_rect,metric_rect) && bounds(2)+bounds(4)<=title_rect(2)+2, ...
        'Plot header overlaps the curve area or axes decorations.');
    for label=[state.home.plot_titles(k) state.home.plot_metrics(k)]
        extent=get(label,'Extent'); rect=get(label,'Position');
        assert(extent(3)<=rect(3)+2 && extent(4)<=rect(4)+2, ...
            'Header text does not fit: %s',get(label,'String'));
    end
end
for k=1:4
    for j=k+1:4, assert(~overlap(rectangles(k,:),rectangles(j,:))); end
end
assert(abs(rectangles(1,4)-rectangles(3,4))<1);
for handle=state.home.hardware_edits
    data=get(handle,'UserData'); a=get(handle,'Position'); b=get(data.current,'Position');
    assert(a(1)==178 && b(1)==92 && strcmp(get(handle,'HorizontalAlignment'),'right'));
    parent=getpixelposition(get(handle,'Parent'),true);
    assert(a(1)+a(3)<parent(3),'Input clipped by its channel group.');
end
pos=get(fig,'Position'); assert(rectangles(2,1)+rectangles(2,3)<pos(3));
end

function yes=overlap(a,b)
yes=min(a(1)+a(3),b(1)+b(3))>max(a(1),b(1))+1 && ...
    min(a(2)+a(4),b(2)+b(4))>max(a(2),b(2))+1;
end

function check_scroll(state)
content=get(state.home.content,'Position'); viewport=get(state.home.settings_panel,'Position');
slider=state.home.scroll;
if state.home.content_height>viewport(4)
    assert(strcmp(get(slider,'Visible'),'on'),'Long settings must remain reachable.');
    assert(abs(content(2)+content(4)-viewport(4))<3,'Top slider must show top content.');
    set(slider,'Value',get(slider,'Min')); invoke(slider);
    bottom=get(state.home.content,'Position');
    assert(abs(bottom(2))<3,'Bottom slider must show bottom content.');
    set(slider,'Value',get(slider,'Max')); invoke(slider);
else
    assert(content(2)>=-2 && content(2)+content(4)<=viewport(4)+2);
    assert(strcmp(get(slider,'Visible'),'off'));
end
end

function snapshot(fig,path)
set(fig,'Visible','on'); drawnow;
frame=getframe(fig); imwrite(frame.cdata,path);
assert(size(frame.cdata,1)>600 && size(frame.cdata,2)>1000);
assert(std(double(frame.cdata(:)))>10);
state=getappdata(fig,'rx_workbench_state');
if state.page=="settings", return; end
size_fig=get(fig,'Position'); sx=size(frame.cdata,2)/size_fig(3); sy=size(frame.cdata,1)/size_fig(4);
for ax=live_axes(state)
    rect=getpixelposition(ax,true);
    left=max(1,ceil(rect(1)*sx)); right=min(size(frame.cdata,2),floor((rect(1)+rect(3))*sx));
    bottom=max(1,ceil(size(frame.cdata,1)-(rect(2)+rect(4))*sy));
    top=min(size(frame.cdata,1),floor(size(frame.cdata,1)-rect(2)*sy));
    pixels=double(frame.cdata(bottom:top,left:right,:));
    chroma=max(pixels,[],3)-min(pixels,[],3);
    assert(nnz(chroma>40)>50,'One plot has no colored waveform/spectrum pixels.');
    header=getappdata(ax,'rx_embedded_header'); outer=getpixelposition(header,true);
    title_left=max(1,ceil(outer(1)*sx));
    title_right=min(size(frame.cdata,2),floor((outer(1)+outer(3))*sx));
    title_top=max(1,ceil(size(frame.cdata,1)-(outer(2)+outer(4))*sy));
    title_bottom=min(size(frame.cdata,1),floor(size(frame.cdata,1)-outer(2)*sy));
    pixels=double(frame.cdata(title_top:title_bottom,title_left:title_right,:));
    assert(nnz(max(pixels,[],3)<110)>25, ...
        'An axes title is missing from the rendered pixels.');
end
end

function edit_and_commit(handle,text_value,commit,during_edit)
uicontrol(handle); drawnow; pause(.15);
manager=java.awt.KeyboardFocusManager.getCurrentKeyboardFocusManager();
owner=manager.getFocusOwner();
assert(~isempty(owner) && strcmp(char(owner.getText()),get(handle,'String')), ...
    'The test edit did not own keyboard focus.');
javaMethodEDT('selectAll',owner);
javaMethodEDT('replaceSelection',owner,text_value);
assert(strcmp(char(owner.getText()),text_value), ...
    'The Swing document did not accept the test edit.');
if nargin>=4
    during_edit();
    assert(strcmp(char(owner.getText()),text_value), ...
        'A capture refresh overwrote the uncommitted edit.');
end
if strcmp(commit,'focus')
    javaMethodEDT('transferFocus',owner);
else
    javaMethodEDT('postActionEvent',owner);
end
deadline=tic;
while toc(deadline)<3
    pause(.05); drawnow;
    data=get(handle,'UserData');
    if isstruct(data)
        complete=abs(data.actual-str2double(text_value)*data.multiplier)<1e-12 && ...
            strcmp(get(handle,'String'),data.displayed);
    else
        complete=strcmp(data,text_value);
    end
    if complete
        return;
    end
end
end

function guard=visual_test_lock()
file=java.io.RandomAccessFile(fullfile(tempdir,'msiq_rx_gui_visual.lock'),'rw');
channel=file.getChannel();
deadline=tic; lock=[];
while isempty(lock) && toc(deadline)<120
    lock=channel.tryLock();
    if isempty(lock), pause(.1); end
end
if isempty(lock)
    channel.close(); file.close();
    error('msiq:validation:VisualLock','Another RX GUI validation still owns keyboard focus.');
end
guard=onCleanup(@() release_visual_lock(lock,channel,file));
end

function release_visual_lock(lock,channel,file)
lock.release(); channel.close(); file.close();
end

function close_if_valid(fig)
if isgraphics(fig), close(fig); end
end

function close_new_figures(existing)
created=setdiff(findall(0,'Type','figure'),existing);
for fig=reshape(created,1,[]), close_if_valid(fig); end
end
