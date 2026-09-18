function note=validate_rx_real_if_simulation()
% Exercise the actual communication provider, isolated from real instruments.
folder=msiq.validation_artifacts('directory');
msiq.instruments.io_audit('reset','');
source=msiq.rx_simulation_source(struct('cache_dir',fullfile(folder,'cache'), ...
    'test_fixture',true,'timebase_s',50e-9));
opts=struct('simulation_source',source,'log_path',fullfile(folder,'provider.log'), ...
    'failure_path',fullfile(folder,'failure.txt'));
base=source.simulation.baseline_attenuation_db*ones(1,6);
snapshot=struct('state_known',true,'sent',struct('rf',base+6,'i',base+3,'q',base+1));
params=struct('symbol_rate_hz',source.symbol_rate_hz,'rolloff',source.cfg.waveform.rolloff);
for position=1:5
    for band=1:6
        context=msiq.rx_measurement_context(position,band);
        a=msiq.rx_simulation_io(opts); b=msiq.rx_simulation_io(opts);
        sa=a.open(source.cfg.instrument.scope); sb=b.open(source.cfg.instrument.scope);
        guard=onCleanup(@()close_pair(a,sa,b,sb));
        a.set_measurement(context); b.set_measurement(context);
        b.set_board(snapshot);
        channels=source.channels;
        if context.is_real_if, channels={'C2'}; end
        % Use ample vertical range so equality measures routing, not saturation.
        for k=1:numel(channels)
            a.write(sa,[channels{k} ':VDIV 0.05']); b.write(sb,[channels{k} ':VDIV 0.05']);
        end
        raw=a.capture(sa,channels); altered=b.capture(sb,channels);
        assert(isequal(raw.measurement_context,context));
        assert(numel(raw.channels)==numel(channels));
        for k=1:numel(channels)
            if position<=3
                assert(isequal(raw.channels(k).samples,altered.channels(k).samples), ...
                    'RX board incorrectly affects upstream measurement.');
            else
                assert(~isequal(raw.channels(k).samples,altered.channels(k).samples));
                assert(mean(altered.channels(k).samples.^2)<mean(raw.channels(k).samples.^2));
            end
        end
        if context.is_real_if
            r=raw.channels(1); stop=params.symbol_rate_hz*((1+params.rolloff)/2+.1);
            assert(r.sample_rate_hz/2>context.center_freq_hz+stop);
            out=msiq.dsp.real_if_frontend(r.samples,r.time_axis_s,r.sample_rate_hz, ...
                context.center_freq_hz,params);
            assert(all(isfinite(out.samples)) && numel(out.samples)>100);
        end
        clear guard
    end
end
% Capacity limitation must refuse IF generation, never silently alias it.
io=msiq.rx_simulation_io(opts); session=io.open(source.cfg.instrument.scope);
guard=onCleanup(@()io.close(session));
io.set_measurement(msiq.rx_measurement_context('tx_if',6));
io.write(session,'VBS ''app.Acquisition.Horizontal.MaxSamples.Value=500''');
try
    io.capture(session,{'C2'});
    error('validation:ExpectedFailure','Expected insufficient rate refusal.');
catch ex
    assert(strcmp(ex.identifier,'RX_Workbench:SimulationRate'),'%s',ex.message);
end
io.write(session,'VBS ''app.Acquisition.Horizontal.MaxSamples.Value=4000000''');
io.write(session,'C2:VDIV 0.005');
raw=io.capture(session,{'C2'}); r=raw.channels(1);
codes=(r.samples+r.descriptor.vertical_offset)/r.descriptor.vertical_gain;
clip=mean(codes<=-32767.5 | codes>=32766.5);
assert(clip>0);
try
    msiq.dsp.real_if_frontend(r.samples,r.time_axis_s,r.sample_rate_hz,37.2e9,params, ...
        struct('clip_fraction',clip));
    error('validation:ExpectedFailure','Expected clipped capture refusal.');
catch ex
    assert(strcmp(ex.identifier,'msiq:real_if:Clipped'),'%s',ex.message);
end
clear guard
audit=msiq.instruments.get_audit();
assert(audit.connections==0 && audit.queries==0 && audit.writes==0 && audit.captures==0);
note='five positions / six bands: real provider rate and DDC, RX board isolation, capacity and clipping refusal; zero instrument I/O';
end

function close_pair(a,sa,b,sb)
a.close(sa); b.close(sb);
end
