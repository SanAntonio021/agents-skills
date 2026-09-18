function out = real_if_frontend(samples, time_axes, Fs, fc, tx_params, options)
%REAL_IF_FRONTEND Full-rate real IF conversion, before any baseband resampling.
% This pure function never accesses instruments or normalizes I/Q separately.
if nargin<6, options=struct(); end
if ~isvector(samples) || ~isreal(samples) || numel(samples)<3 || ...
        any(~isfinite(samples(:)))
    error('msiq:real_if:Samples','中频输入必须是有限的单路实数完整波形。');
end
x=double(samples(:)); t=double(time_axes(:));
if ~isscalar(Fs) || ~isfinite(Fs) || Fs<=0 || ~isscalar(fc) || ~isfinite(fc) || fc<=0
    error('msiq:real_if:Frequency','中频中心频率和采样率必须为正数。');
end
if ~isvector(time_axes) || numel(t)~=numel(x) || any(~isfinite(t)) || ...
        any(abs(diff(t)*Fs-1)>1e-4)
    error('msiq:real_if:TimeAxis','完整时间轴必须与波形及实际采样率一致。');
end
if ~isstruct(tx_params) || ~isfield(tx_params,'symbol_rate_hz') || ~isfield(tx_params,'rolloff')
    error('msiq:real_if:Reference','缺少发送参考的符号率或滚降系数。');
end
Rs=double(tx_params.symbol_rate_hz); rolloff=double(tx_params.rolloff);
if ~isscalar(Rs) || ~isfinite(Rs) || Rs<=0 || ~isscalar(rolloff) || ...
        ~isfinite(rolloff) || rolloff<0 || rolloff>1
    error('msiq:real_if:Reference','发送参考的符号率或滚降系数无效。');
end
fp=Rs*(1+rolloff)/2; fs=fp+0.1*Rs;
if fc<=fs || fc+fs>=Fs/2
    error('msiq:real_if:Nyquist','目标中频及滤波过渡带超出可用采样频带。');
end
if min(2*fc,Fs-2*fc)<=fp+fs
    error('msiq:real_if:Image','下变频镜像与目标滤波频带重叠。');
end
if isfield(options,'analog_bandwidth_hz') && isfinite(options.analog_bandwidth_hz) && ...
        options.analog_bandwidth_hz<fc+fp
    error('msiq:real_if:AnalogBandwidth','已确认的模拟带宽不足以覆盖目标中频。');
end
if isfield(options,'clip_fraction') && options.clip_fraction>0
    error('msiq:real_if:Clipped','原始中频采集存在削顶，解调指标无效。');
end
[b,spec]=design_filter(Fs,Rs,rolloff,fp,fs);
order=numel(b)-1; delay=order/2;
if numel(x)<=order+1
    error('msiq:real_if:Window','采集窗口不足以去除中频滤波瞬态。');
end
d=max(1,floor(Fs/max(4*Rs,2.02*fs)));
mixed=2*x.*exp(-1i*2*pi*fc*(t-t(1)));
filtered=fftfilt(b,mixed);
% Causal output at order+1:N uses only original samples; map back by delay.
indices=(order+1:d:numel(x)).';
y=filtered(indices); tout=t(indices-delay);
dc=0;
if isfield(options,'remove_dc') && options.remove_dc
    dc=median(real(y))+1i*median(imag(y)); y=y-dc;
end
log=spec;
log.version=1; log.source_sample_rate_hz=Fs; log.center_freq_hz=fc;
log.filter_coefficients=b; log.filter_delay_samples=delay;
log.crop_left_samples=delay; log.crop_right_samples=numel(x)-(indices(end)-delay);
log.retained_source_first_index=indices(1)-delay;
log.retained_source_last_index=indices(end)-delay;
log.decimation=d; log.output_sample_rate_hz=Fs/d;
log.source_sample_count=numel(x); log.output_sample_count=numel(y);
log.dc_removed=struct('real',real(dc),'imag',imag(dc)); log.voltage_scale=2;
out=struct('samples',y,'time_axes',tout,'sample_rate_hz',Fs/d, ...
    'already_baseband',true,'processing_log',log);
end

function [b,spec]=design_filter(Fs,Rs,rolloff,fp,fs)
persistent cache_key cache_b cache_spec
key=[Fs Rs rolloff];
if isequal(key,cache_key), b=cache_b; spec=cache_spec; return; end
% Design with margin, then measure the actual response against the contract.
[n,wn,beta,kind]=kaiserord([fp fs],[1 0],[0.0002 10^(-90/20)],Fs);
n=2*ceil(n/2);
while n<=8192
    b=fir1(n,wn,kind,kaiser(n+1,beta),'noscale');
    b=b/sum(b);
    [h,f]=freqz(b,1,max(65536,16*(n+1)),Fs);
    pass=abs(h(f<=fp)); stop=abs(h(f>=fs));
    ripple=20*log10(max(pass)/min(pass)); rejection=-20*log10(max(stop));
    if ripple<=0.05 && rejection>=80, break; end
    n=n+2*max(1,ceil(0.025*n));
end
if n>8192
    error('msiq:real_if:Filter','8193 taps 内无法满足中频滤波指标。');
end
spec=struct('passband_hz',fp,'stopband_hz',fs,'passband_ripple_db',ripple, ...
    'stopband_attenuation_db',rejection,'filter_type','Kaiser linear-phase FIR');
cache_key=key; cache_b=b; cache_spec=spec;
end
