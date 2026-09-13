function [value,spectrum] = if_capture_observation(raw,p,cfg,scale)
%IF_CAPTURE_OBSERVATION Validate actual records without changing or aligning them.
assert(isfield(raw,'fresh_confirmed') && isequal(raw.fresh_confirmed,true), ...
    'msiq:if:StaleCapture','Fresh acquisition was not confirmed.');
count=numel(raw.channels);
assert(count==numel(p.scope.channels),'msiq:if:Channels','Capture channel count changed.');
assert(numel(scale)>=count && all(isfinite(scale)) && all(scale>0), ...
    'msiq:if:Scale','Actual vertical scales must be positive and finite.');
rates=zeros(1,count); windows=rates; power=rates; peaks=rates; clips=rates;
spectrum=cell(1,count); centers=zeros(1,count);
for k=1:count
    record=raw.channels(k);
    assert(strcmpi(record.channel,p.scope.channels{k}), ...
        'msiq:if:Channels','Capture channel order changed.');
    x=double(record.samples(:)); ts=double(record.time_axis_s(:));
    assert(isreal(x)&&all(isfinite(x))&&numel(x)>1&&numel(x)==numel(ts)&& ...
        all(isfinite(ts))&&all(diff(ts)>0),'msiq:if:Waveform','Invalid waveform or time axis.');
    dt=diff(ts); fs=1/median(dt);
    assert(max(abs(dt-1/fs))<=max(1e-6/fs,16*eps(max(abs(ts)))), ...
        'msiq:if:TimeAxis','Nonuniform sampling is not accepted.');
    assert(isscalar(record.sample_rate_hz)&&isfinite(record.sample_rate_hz)&& ...
        abs(record.sample_rate_hz/fs-1)<1e-5, ...
        'msiq:if:SampleRate','Descriptor rate and time axis disagree.');
    rates(k)=fs; windows(k)=numel(x)/fs;
    d=record.descriptor;
    if all(isfield(d,{'vertical_gain','vertical_offset','comm_type'}))
        assert(isfinite(d.vertical_gain)&&d.vertical_gain>0&&isfinite(d.vertical_offset)&& ...
            ismember(d.comm_type,[0 1]),'msiq:if:Descriptor','Invalid vertical descriptor.');
        bits=8+8*d.comm_type;
        codes=(x+d.vertical_offset)/d.vertical_gain;
        clips(k)=mean(codes<=-2^(bits-1)+.5 | codes>=2^(bits-1)-1-.5);
        centers(k)=-d.vertical_offset;
        peaks(k)=max(abs(x-centers(k))); % Do not remove DC before clipping/ranging.
    elseif strcmp(p.mode,'mock')
        peaks(k)=max(abs(x)); clips(k)=mean(abs(x)>=4*scale(k));
    else
        error('msiq:if:Descriptor','Calibrated vertical descriptor is required for clipping checks.');
    end
    ac=x-mean(x);
    bins=(-floor(numel(x)/2):ceil(numel(x)/2)-1)'*fs/numel(x);
    ps=abs(fftshift(fft(ac))).^2/numel(x)^2;
    bw=cfg.waveform.symbol_rate_hz*(1+cfg.waveform.rolloff)/2;
    mask=abs(bins)<=bw;
    if strcmp(p.stage,'tx_if'), mask=abs(abs(bins)-6.2e9)<=bw; end
    power(k)=sum(ps(mask));
    spectrum{k}=struct('frequency_hz',bins,'power_v2_bin',ps, ...
        'processing','mean_removed_rectangular_two_sided_fft');
end
assert(isfinite(p.scope.sample_rate_tolerance)&&p.scope.sample_rate_tolerance>=0&& ...
    isfinite(p.scope.window_tolerance)&&p.scope.window_tolerance>=0, ...
    'msiq:if:CaptureTolerance','Confirm sample-rate and window tolerances first.');
assert(all(abs(rates/p.scope.sample_rate_hz-1)<=p.scope.sample_rate_tolerance), ...
    'msiq:if:SampleRate','Actual sample rate differs from approved profile.');
% Mock carries a shorter transport fixture; never claim its record spans the live window.
if ~strcmp(p.mode,'mock')
    assert(all(abs(windows/p.scope.window_s-1)<=p.scope.window_tolerance), ...
        'msiq:if:Window','Actual record window differs from approved profile.');
end
assert(all(abs(rates/rates(1)-1)<1e-5), ...
    'msiq:if:SampleRate','I/Q rates differ.');
value=struct('power_v2',power,'power_dbv2',10*log10(max(realmin,power)), ...
    'peaks_v',peaks,'clipped',any(clips>0),'clip_fraction',clips, ...
    'sample_rates_hz',rates,'windows_s',windows,'vertical_centers_v',centers);
end
