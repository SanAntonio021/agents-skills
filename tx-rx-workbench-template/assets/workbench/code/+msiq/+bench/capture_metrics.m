function [metrics, raw] = capture_metrics(raw, cfg, center_hz, ...
        half_width_hz, vertical_scale_v_per_div)
%CAPTURE_METRICS Compute electrical power and clipping metrics.

samples = double(raw.samples);
if isempty(samples) || ~ismatrix(samples) || any(~isfinite(samples(:)))
    error('msiq:bench:InvalidCapture', ...
        'Smoke capture samples must be a finite nonempty matrix.');
end
if ~isfield(raw, 'sample_rate_hz') || ...
        ~isscalar(raw.sample_rate_hz) || ~isfinite(raw.sample_rate_hz) || ...
        raw.sample_rate_hz <= 0
    error('msiq:bench:InvalidSampleRate', ...
        'Smoke capture requires a positive finite sample rate.');
end

full_scale = NaN;
if isfield(raw, 'full_scale') && isscalar(raw.full_scale) && ...
        isfinite(raw.full_scale) && raw.full_scale > 0
    full_scale = double(raw.full_scale);
elseif isfinite(vertical_scale_v_per_div) && vertical_scale_v_per_div > 0
    full_scale = vertical_scale_v_per_div * cfg.scope.vertical_divisions / 2;
    raw.full_scale = full_scale;
end

count = size(samples,1);
rate = double(raw.sample_rate_hz);
frequency = (0:count-1).'/count*rate;
positive = abs(frequency-center_hz) <= half_width_hz;
negative = abs(frequency-(rate-center_hz)) <= half_width_hz;
mask = positive | negative;
power_w = zeros(1,size(samples,2));
for channel = 1:size(samples,2)
    spectrum = fft(samples(:,channel));
    band = ifft(spectrum.*mask);
    power_w(channel) = mean(abs(band).^2)/50;
end
clip_fraction = NaN;
if isfinite(full_scale)
    clip_fraction = nnz(abs(samples) >= 0.99*full_scale)/numel(samples);
end
metrics = struct( ...
    'inband_power_dbm', 10*log10(max(mean(power_w)*1000, realmin)), ...
    'rms_v', sqrt(mean(samples(:).^2)), ...
    'peak_v', max(abs(samples(:))), ...
    'clip_fraction', clip_fraction, ...
    'vertical_scale_v_per_div', vertical_scale_v_per_div, ...
    'full_scale_v', full_scale);
end
