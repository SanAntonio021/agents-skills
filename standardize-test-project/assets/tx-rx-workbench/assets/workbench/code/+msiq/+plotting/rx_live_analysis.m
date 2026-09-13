function compact = rx_live_analysis(raw,status)
%RX_LIVE_ANALYSIS Analyze once per capture, separately from graphics callbacks.
% Returned samples are a display envelope, not a uniformly sampled DSP record.
compact = raw;
records = field_or(raw,'channels',struct([]));
spectra = cell(1,numel(records));
for k = 1:numel(records)
    record = records(k);
    channel = channel_status(status,record.channel);
    spectra{k} = real_psd(record,status,channel);
    samples = double(record.samples(:));
    time = double(field_or(record,'time_axis_s',[])); time=time(:);
    valid = numel(time)==numel(samples) && numel(samples)>=2 && ...
        all(isfinite(samples)) && all(isfinite(time)) && all(diff(time)>0) && ...
        ~strcmp(field_or(channel,'trace_state',''),'OFF');
    compact.channels(k).original_count = numel(samples);
    compact.channels(k).wave_valid = valid;
    compact.channels(k).wave_info = '数据不可用';
    if strcmp(field_or(channel,'trace_state',''),'OFF')
        compact.channels(k).wave_info = '通道已关闭';
    elseif isempty(samples)
        compact.channels(k).wave_info = '未收到波形';
    elseif ~valid
        compact.channels(k).wave_info = '波形或时间轴无效';
    end
    compact.channels(k).peak_v = NaN;
    compact.channels(k).rms_v = NaN;
    compact.channels(k).vpp_v = NaN;
    if valid
        index = msiq.plotting.rx_envelope_indices(samples,6000);
        compact.channels(k).samples = samples(index);
        compact.channels(k).time_axis_s = time(index);
        compact.channels(k).peak_v = max(abs(samples));
        compact.channels(k).rms_v = sqrt(mean(samples.^2));
        compact.channels(k).vpp_v = max(samples)-min(samples);
        compact.channels(k).wave_info = sprintf('RMS %s | Vpp %s', ...
            voltage(compact.channels(k).rms_v),voltage(compact.channels(k).vpp_v));
    else
        compact.channels(k).samples = [];
        compact.channels(k).time_axis_s = [];
    end
end
compact.live_spectra = spectra;
end

function label = voltage(value)
if abs(value)<1, label=sprintf('%.3g mV',value*1e3);
else, label=sprintf('%.3g V',value); end
end

function spectrum = real_psd(record,status,channel)
spectrum = struct('channel',record.channel,'frequency_hz',[],'power_dbm_hz',[], ...
    'sample_rate_hz',NaN,'effective_limit_hz',NaN,'n',numel(record.samples), ...
    'delta_f_hz',NaN,'reason','','details','','impedance_note','', ...
    'impedance_known',false,'voltage_dbv2_hz',[],'limit_confirmed',false);
samples = double(record.samples(:)); n = numel(samples);
if strcmp(field_or(channel,'trace_state',''),'OFF')
    spectrum.reason = '通道已关闭'; return;
end
if n < 4
    spectrum.reason = '未收到足够采样点'; return;
end
if any(~isfinite(samples))
    spectrum.reason = '采样值包含 NaN 或 Inf'; return;
end
[rate,source] = record_rate(record);
if ~isfinite(rate) || rate <= 0
    spectrum.reason = '缺少可信的回传样点间隔'; return;
end
impedance = field_or(channel,'impedance_ohm',NaN);
if ~isfinite(impedance) || impedance <= 0
    spectrum.impedance_note = '阻抗未确认，功率不可用';
else
    spectrum.impedance_known = true;
    spectrum.impedance_note = sprintf('%.4g Ohm',impedance);
end
% Bounded live estimate: no raw decimation, at most eight full-rate windows.
segment_n = min(n,65536);
starts = unique(round(linspace(1,n-segment_n+1,min(8,ceil(n/segment_n)))));
window = .5-.5*cos(2*pi*(0:segment_n-1)'/segment_n);
take = (1:floor(segment_n/2)+1)';
density = zeros(numel(take),1);
for first = starts
    values = fft(samples(first:first+segment_n-1).*window,segment_n);
    density = density+abs(values(take)).^2;
end
density = density/(numel(starts)*rate*sum(window.^2));
if mod(segment_n,2) == 0
    density(2:end-1) = density(2:end-1)*2;
else
    density(2:end) = density(2:end)*2;
end
frequency = (take-1)*rate/segment_n;
acquisition_rate = field_or(status,'sample_rate_hz',NaN);
bw = field_or(channel,'bandwidth_limit_hz',NaN);
analog = field_or(channel,'analog_bandwidth_hz',field_or(status,'analog_bandwidth_hz',NaN));
bounds = [rate/2 acquisition_rate/2 bw analog];
bounds = bounds(isfinite(bounds) & bounds>0);
limit = min(bounds);
spectrum.limit_confirmed = isfinite(analog) || isfinite(bw);
spectrum.details = sprintf('分段 Hann 单边 PSD | 回传 %.6g GSa/s | 采集 %.6g GSa/s\nN %d | df %.6g MHz | %s | %s', ...
    rate/1e9,acquisition_rate/1e9,n,rate/segment_n/1e6,source,spectrum.impedance_note);
if ~isfinite(analog) && (~isfinite(bw) || isnan(bw))
    spectrum.details = sprintf('%s\n模拟带宽未回读；当前按采样上限显示',spectrum.details);
end
valid = frequency <= limit*(1+1e-12);
spectrum.frequency_hz = frequency(valid);
spectrum.voltage_dbv2_hz = 10*log10(max(density(valid),realmin));
if spectrum.impedance_known
    spectrum.power_dbm_hz = 10*log10(max(density(valid)/impedance*1000,realmin));
else
    spectrum.power_dbm_hz = nan(nnz(valid),1);
end
spectrum.sample_rate_hz = rate;
spectrum.effective_limit_hz = limit;
spectrum.delta_f_hz = rate/segment_n;
spectrum.segment_count = numel(starts);
spectrum.segment_length = segment_n;
end

function [rate,source] = record_rate(record)
rate = NaN; source = '';
time = double(field_or(record,'time_axis_s',[])); time = time(:);
if numel(time) >= 2
    delta = diff(time);
    if any(~isfinite(delta)) || any(delta <= 0), return; end
    interval = median(delta);
    if max(abs(delta-interval)) > max(1e-18,interval*1e-4), return; end
    rate = 1/interval; source = '回传时间轴';
    return;
end
descriptor = field_or(record,'descriptor',struct());
interval = field_or(descriptor,'horizontal_interval_s',NaN);
if isfinite(interval) && interval > 0
    rate = 1/interval; source = 'WAVEDESC';
    return;
end
rate = field_or(record,'sample_rate_hz',NaN);
source = '通道记录采样率';
end

function channel = channel_status(status,name)
channel = struct();
channels = field_or(status,'channels',struct([]));
if isempty(channels), return; end
index = find(strcmpi({channels.channel},name),1);
if ~isempty(index), channel = channels(index); end
end

function value = field_or(object,name,fallback)
if isstruct(object) && isfield(object,name) && ~isempty(object.(name))
    value = object.(name);
else
    value = fallback;
end
end
