function note = validate_rx_real_if(output_dir)
%VALIDATE_RX_REAL_IF Pure numerical tests; no instrument construction or I/O.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end %#ok<NASGU>
centers=msiq.if_subband_frequencies();
assert(isequal(centers,[6.2 12.4 18.6 24.8 31 37.2]*1e9));
assert(isempty(msiq.rx_measurement_context().position));
for p=1:5
    for band=1:6
        c=msiq.rx_measurement_context(p,band);
        assert(c.is_real_if==ismember(p,[2 3]));
        assert(c.through_thz==ismember(p,[3 5]));
        assert(isequal(c,msiq.rx_measurement_context(c)));
        if c.is_real_if, assert(c.center_freq_hz==centers(band));
        else, assert(c.center_freq_hz==0); end
    end
end
params=struct('symbol_rate_hz',1e9,'rolloff',0.2);
errors=zeros(1,6);
for band=1:6
    fc=centers(band); Fs=ceil(2*(fc+3e9)/1e9)*1e9;
    t=(0:65535)'/Fs; f1=0.17e9; f2=-0.31e9;
    z=0.2*exp(1i*(2*pi*f1*t+0.3))+0.12*exp(1i*(2*pi*f2*t-0.7));
    x=real(z.*exp(1i*2*pi*fc*t));
    out=msiq.dsp.real_if_frontend(x,t,Fs,fc,params);
    truth=0.2*exp(1i*(2*pi*f1*out.time_axes+0.3))+ ...
        0.12*exp(1i*(2*pi*f2*out.time_axes-0.7));
    errors(band)=norm(out.samples-truth)/norm(truth);
    assert(errors(band)<5e-4,'Real IF voltage/phase mismatch.');
    assert(out.already_baseband && size(out.samples,2)==1);
    assert(out.sample_rate_hz>=4e9);
    assert(out.processing_log.stopband_attenuation_db>=80);
    assert(out.processing_log.passband_ripple_db<=0.05);
    assert(numel(out.processing_log.filter_coefficients)<=8193);
    assert(all(abs(diff(out.time_axes)*out.sample_rate_hz-1)<1e-6));
end
% A large out-of-band tone must be rejected; an in-band LO remains visible.
fc=6.2e9; Fs=20e9; t=(0:131071)'/Fs;
x=cos(2*pi*(fc+0.9e9)*t);
out=msiq.dsp.real_if_frontend(x,t,Fs,fc,params);
assert(sqrt(mean(abs(out.samples).^2))<1e-4);
x=0.1*cos(2*pi*fc*t);
live=msiq.dsp.real_if_frontend(x,t,Fs,fc,params);
formal=msiq.dsp.real_if_frontend(x,t,Fs,fc,params,struct('remove_dc',true));
assert(abs(mean(live.samples)-0.1)<1e-5);
assert(abs(mean(formal.samples))<1e-5);
assert(abs(formal.processing_log.dc_removed.real-0.1)<1e-5);
assert(abs(formal.processing_log.dc_removed.imag)<1e-5);
assert(~isempty(jsonencode(formal.processing_log)));
must_fail(@()msiq.dsp.real_if_frontend(x,t,10e9,fc,params),'TimeAxis');
must_fail(@()msiq.dsp.real_if_frontend(x,t,Fs,9.5e9,params),'Nyquist');
bad=x; bad(2)=NaN;
must_fail(@()msiq.dsp.real_if_frontend(bad,t,Fs,fc,params),'Samples');
badtime=t; badtime(2)=badtime(3);
must_fail(@()msiq.dsp.real_if_frontend(x,badtime,Fs,fc,params),'TimeAxis');
must_fail(@()msiq.dsp.real_if_frontend(x(1:20),t(1:20),Fs,fc,params),'Window');
must_fail(@()msiq.dsp.real_if_frontend(x,t,Fs,fc,params,struct('clip_fraction',.01)),'Clipped');
must_fail(@()msiq.dsp.real_if_frontend(x,t,Fs,fc,params,struct('analog_bandwidth_hz',6.3e9)),'AnalogBandwidth');
must_fail(@()msiq.dsp.real_if_frontend(x,t,Fs,fc,struct('symbol_rate_hz',1e6,'rolloff',.2)),'Filter');
note=sprintf('six-band real IF frontend, phase/voltage error <= %.3g, rejection/crop/DC/invalid inputs; zero instrument I/O',max(errors));
end

function must_fail(action,suffix)
try
    action();
catch ex
    assert(strcmp(ex.identifier,['msiq:real_if:' suffix]),'%s',ex.message);
    return
end
error('validation:real_if:ExpectedFailure','Expected real_if error %s.',suffix);
end
