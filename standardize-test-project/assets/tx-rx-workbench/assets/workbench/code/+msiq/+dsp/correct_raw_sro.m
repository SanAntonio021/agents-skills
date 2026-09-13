function [corrected, info] = correct_raw_sro(raw, sro_ppm)
%CORRECT_RAW_SRO Inverse-resample an acquired waveform before RX filtering.

if ~isstruct(raw) || ~isfield(raw, 'samples') || isempty(raw.samples)
    error('msiq:dsp:RawSroFormat', 'raw.samples is required.');
end
if ~isnumeric(raw.samples) || ~all(isfinite(raw.samples(:)))
    error('msiq:dsp:RawSroSamples', ...
        'raw.samples must be finite numeric samples.');
end
if ~isfield(raw, 'sample_rate_hz') || isempty(raw.sample_rate_hz) || ...
        ~isscalar(raw.sample_rate_hz) || ~isfinite(raw.sample_rate_hz) || ...
        raw.sample_rate_hz <= 0
    error('msiq:dsp:RawSroSampleRate', ...
        'raw.sample_rate_hz must be a positive finite scalar.');
end
if ~isscalar(sro_ppm) || ~isfinite(sro_ppm)
    error('msiq:dsp:RawSroEstimate', ...
        'SRO estimate must be a finite scalar ppm value.');
end

samples = double(raw.samples);
if isvector(samples)
    samples = samples(:);
elseif size(samples,1) < size(samples,2)
    samples = samples.';
end
input_count = size(samples,1);
channel_count = size(samples,2);
sample_rate = double(raw.sample_rate_hz);
scale = 1/(1 + double(sro_ppm)*1e-6);
if ~isfinite(scale) || scale <= 0
    error('msiq:dsp:RawSroScale', ...
        'SRO estimate produces an invalid inverse-resampling scale.');
end

if sro_ppm == 0
    corrected = raw;
    info = correction_info(false, sro_ppm, scale, input_count, input_count, ...
        false, zeros(1,channel_count));
    return;
end

output_count = floor((input_count-1)*scale)+1;
source_axis = 1+(0:output_count-1).'/scale;
source_index = (1:input_count).';
resampled = zeros(output_count, channel_count);
if ~isreal(samples)
    resampled = complex(resampled);
end
for channel = 1:channel_count
    resampled(:,channel) = interp1(source_index, samples(:,channel), ...
        source_axis, 'pchip');
end

corrected = raw;
corrected.samples = resampled;
time_axes_rebuilt = false;
offset_samples = zeros(1,channel_count);
if isfield(raw, 'time_axes') && ~isempty(raw.time_axes)
    time_axes = raw.time_axes;
    if isvector(time_axes)
        time_axes = time_axes(:);
    elseif size(time_axes,1) < size(time_axes,2)
        time_axes = time_axes.';
    end
    if ~isequal(size(time_axes), size(samples)) || ...
            ~isnumeric(time_axes) || ~all(isfinite(time_axes(:)))
        error('msiq:dsp:RawSroTimeAxes', ...
            'raw.time_axes must be finite and match raw.samples.');
    end
    time_axes = double(time_axes);
    corrected_axes = zeros(output_count, channel_count);
    index = (0:output_count-1).'/sample_rate;
    for channel = 1:channel_count
        corrected_axes(:,channel) = time_axes(1,channel)+index;
    end
    corrected.time_axes = corrected_axes;
    offset_samples = (time_axes(1,:)-time_axes(1,1))*sample_rate;
    time_axes_rebuilt = true;
end

info = correction_info(true, sro_ppm, scale, input_count, output_count, ...
    time_axes_rebuilt, offset_samples);
end

function info = correction_info(applied, sro_ppm, scale, input_count, ...
        output_count, time_axes_rebuilt, offset_samples)
info = struct('applied', logical(applied), 'stage', ...
    ternary(applied, 'raw_input', 'not_applied'), 'sro_ppm', double(sro_ppm), ...
    'inverse_resample_scale', double(scale), 'input_samples', input_count, ...
    'output_samples', output_count, 'time_axes_rebuilt', ...
    logical(time_axes_rebuilt), 'channel_time_offsets_samples', ...
    double(offset_samples));
end

function value = ternary(condition, when_true, when_false)
if condition
    value = when_true;
else
    value = when_false;
end
end
