function [baseband, info] = prepare_capture(raw, cfg)
%PREPARE_CAPTURE Align time axes, resample, DDC, and matched-filter capture.

if ~isstruct(raw) || ~isfield(raw, 'samples')
    error('msiq:dsp:RawFormat', 'raw.samples is required.');
end
samples = double(raw.samples);
if isvector(samples)
    samples = samples(:);
end
if size(samples, 1) < size(samples, 2)
    samples = samples.';
end
if ~isfield(raw, 'sample_rate_hz') || isempty(raw.sample_rate_hz)
    error('msiq:dsp:SampleRate', 'raw.sample_rate_hz is required.');
end
source_rate = double(raw.sample_rate_hz);
architecture = lower(char(string(cfg.waveform.architecture)));
is_single = strcmp(architecture, 'single_complex_stream');
wz_single = is_single && isfield(cfg.receiver, 'single_equalizer') && ...
    strcmpi(cfg.receiver.single_equalizer, 'wz_wl_fse_nlms');

alignment = struct('applied', false, 'offset_samples', zeros(1, size(samples,2)));
if isfield(raw, 'time_axes') && ~isempty(raw.time_axes)
    time_axes = double(raw.time_axes);
    if size(time_axes, 1) < size(time_axes, 2)
        time_axes = time_axes.';
    end
    if ~isequal(size(time_axes), size(samples))
        error('msiq:dsp:TimeAxisSize', ...
            'raw.time_axes must match raw.samples.');
    end
    [samples, alignment] = align_axes(samples, time_axes, source_rate);
end

if wz_single
    target_rate = cfg.receiver.single_samples_per_symbol * ...
        cfg.waveform.symbol_rate_hz;
else
    target_rate = cfg.waveform.master_sample_rate_hz;
end
if abs(source_rate-target_rate) > max(1, target_rate*1e-12)
    % LeCroy WAVEDESC HORIZ_INTERVAL is single precision. Its nominal-rate
    % quantization must not turn an exact practical ratio into a huge filter.
    [p, q] = rat(target_rate/source_rate, 1e-7);
    if p > 5000 || q > 5000
        error('msiq:dsp:ResampleRatio', ...
            'Capture resampling ratio is too large: %d/%d.', p, q);
    end
    resampled = cell(1, size(samples,2));
    for channel = 1:size(samples,2)
        resampled{channel} = resample(samples(:,channel), p, q);
    end
    count = min(cellfun(@numel, resampled));
    samples_out = zeros(count, size(samples,2));
    if ~isreal(samples)
        samples_out = complex(samples_out);
    end
    for channel = 1:size(samples,2)
        samples_out(:,channel) = resampled{channel}(1:count);
    end
    samples = samples_out;
else
    p = 1;
    q = 1;
end

already_baseband = isfield(raw, 'already_baseband') && ...
    logical(raw.already_baseband);
iq_preprocessing = struct('applied', false, 'dc_i', 0, 'dc_q', 0, ...
    'q_gain_factor', 1, 'combined_as_complex_pair', false);
if is_single
    if size(samples,2) >= 2 && isreal(samples)
        dc_i = median(samples(:,1));
        dc_q = median(samples(:,2));
        i_samples = samples(:,1)-dc_i;
        q_samples = samples(:,2)-dc_q;
        q_gain = 1;
        if ~isfield(cfg.receiver, 'iq_coarse_gain_balance') || ...
                logical(cfg.receiver.iq_coarse_gain_balance)
            q_gain = sqrt(mean(i_samples.^2)) / ...
                max(sqrt(mean(q_samples.^2)), eps);
            q_samples = q_gain*q_samples;
        end
        complex_baseband = complex(i_samples, q_samples);
        iq_preprocessing = struct('applied', true, 'dc_i', dc_i, ...
            'dc_q', dc_q, 'q_gain_factor', q_gain, ...
            'combined_as_complex_pair', true);
    elseif size(samples,2) == 1
        complex_baseband = complex(samples(:,1));
    else
        error('msiq:dsp:SingleIqPair', ...
            'Traditional complex reception requires one I/Q sample pair.');
    end
    if ~already_baseband && abs(cfg.waveform.if_center_hz) > 0
        n = (0:size(complex_baseband,1)-1).';
        complex_baseband = complex_baseband .* ...
            exp(-1j*2*pi*cfg.waveform.if_center_hz/target_rate*n);
        complex_baseband = lowpass_columns(complex_baseband, target_rate, cfg);
    end
    rms_value = sqrt(mean(abs(complex_baseband).^2));
    complex_baseband = complex_baseband/max(rms_value, eps);
elseif already_baseband || ~isreal(samples)
    complex_baseband = complex(samples);
else
    n = (0:size(samples,1)-1).';
    oscillator = exp(-1j*2*pi*cfg.waveform.if_center_hz/target_rate*n);
    complex_baseband = 2*samples.*oscillator;
    complex_baseband = lowpass_columns(complex_baseband, target_rate, cfg);
end

sps = target_rate/cfg.waveform.symbol_rate_hz;
if abs(sps-round(sps)) > 1e-9
    error('msiq:dsp:ProcessingSps', ...
        'Matched-filter processing rate must be an integer samples/symbol.');
end
sps = round(sps);
rrc = rcosdesign(cfg.waveform.rolloff, ...
    cfg.waveform.rrc_span_symbols, ...
    sps, 'sqrt').';
baseband = zeros(size(complex_baseband));
baseband = complex(baseband);
for channel = 1:size(complex_baseband,2)
    baseband(:,channel) = filter(rrc, 1, complex_baseband(:,channel));
end

info = struct();
info.source_sample_rate_hz = source_rate;
info.output_sample_rate_hz = target_rate;
info.resample_p = p;
info.resample_q = q;
info.alignment = alignment;
info.architecture = architecture;
info.processing_samples_per_symbol = sps;
info.iq_preprocessing = iq_preprocessing;
info.input_samples = size(raw.samples,1);
info.output_samples = size(baseband,1);
info.already_baseband = already_baseband;
preview_count = min(8000, size(baseband,1));
preview_index = unique(round(linspace(1, size(baseband,1), preview_count)));
info.baseband_preview_indices = preview_index(:);
info.baseband_preview = baseband(preview_index,:);
end

function value = lowpass_columns(value, sample_rate, cfg)
cutoff_hz = 0.62*cfg.waveform.symbol_rate_hz*(1+cfg.waveform.rolloff);
cutoff_hz = min(cutoff_hz, 0.48*sample_rate);
order = 192;
lowpass = fir1(order, cutoff_hz/(sample_rate/2), ...
    'low', kaiser(order+1, 7)).';
for channel = 1:size(value,2)
    if size(value,1) > 3*numel(lowpass)
        value(:,channel) = filtfilt(lowpass, 1, value(:,channel));
    else
        value(:,channel) = filter(lowpass, 1, value(:,channel));
    end
end
end

function [aligned, info] = align_axes(samples, time_axes, sample_rate)
start_time = max(time_axes(1,:));
stop_time = min(time_axes(end,:));
reference_time = time_axes(:,1);
keep = reference_time >= start_time & reference_time <= stop_time;
common_time = reference_time(keep);
aligned = zeros(numel(common_time), size(samples,2));
for channel = 1:size(samples,2)
    aligned(:,channel) = interp1(time_axes(:,channel), ...
        samples(:,channel), common_time, 'pchip');
end
finite_rows = all(isfinite(aligned),2);
aligned = aligned(finite_rows,:);
common_time = common_time(finite_rows);
offset = zeros(1, size(samples,2));
for channel = 1:size(samples,2)
    count = min(size(time_axes,1), size(time_axes,1));
    offset(channel) = median(time_axes(1:count,channel) - ...
        time_axes(1:count,1))*sample_rate;
end
info = struct('applied', true, 'offset_samples', offset, ...
    'output_samples', numel(common_time));
end
