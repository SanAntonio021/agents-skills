function raw = simulate_capture(waveforms, cfg, payload_pair, options)
%SIMULATE_CAPTURE Build a synthetic capture with controlled channel damage.

if nargin < 3 || isempty(payload_pair), payload_pair = 'A'; end
if nargin < 4 || isempty(options), options = struct(); end
options = defaults(options, struct( ...
    'snr_db', 40, 'cfo_hz', 0, 'sro_ppm', 0, ...
    'channel_matrix', [1 0.08; 0.06 0.95], ...
    'image_matrix', zeros(2), 'channel_skew_samples', 0, ...
    'time_axis_skew_samples', 0, 'prepend_samples', 0, ...
    'crop_start_samples', 0, 'clip_level', Inf, 'rng_seed', 9001, ...
    'capture_repetitions', 1, 'segment_padding_samples', 0));

if strcmpi(payload_pair, 'A')
    columns = 1:2;
else
    columns = 3:4;
end
passband = waveforms.master_dac_data(:,columns);
passband = repeat_capture_segments(passband, ...
    options.capture_repetitions, options.segment_padding_samples);
rate = waveforms.master_sample_rate_hz;
n = (0:size(passband,1)-1).';
architecture = lower(char(string(waveforms.architecture)));
is_single = strcmp(architecture, 'single_complex_stream');
H = double(options.channel_matrix);
G = double(options.image_matrix);
if is_single
    transmitted = complex(passband(:,1), passband(:,2));
    received = H(1,1)*transmitted + G(1,1)*conj(transmitted);
else
    baseband = zeros(size(passband));
    baseband = complex(baseband);
    for stream = 1:2
        baseband(:,stream) = hilbert(passband(:,stream)) .* ...
            exp(-1j*2*pi*cfg.waveform.if_center_hz/rate*n);
    end
    received = (H*baseband.' + G*conj(baseband.')).';
    if abs(options.channel_skew_samples) > 0
        axis_value = (1:size(received,1)).';
        received(:,2) = interp1(axis_value, received(:,2), ...
            axis_value-options.channel_skew_samples, 'pchip', 0);
    end
end
received = received .* exp(1j*2*pi*options.cfo_hz/rate*n);

if abs(options.sro_ppm) > 0
    scale = 1 + options.sro_ppm*1e-6;
    output_count = floor((size(received,1)-1)*scale)+1;
    source_axis = 1 + (0:output_count-1).'/scale;
    value = zeros(output_count, size(received,2));
    value = complex(value);
    for channel = 1:size(received,2)
        value(:,channel) = interp1((1:size(received,1)).', ...
            received(:,channel), source_axis, 'pchip');
    end
    received = value;
end

stream = RandStream('mt19937ar', 'Seed', options.rng_seed);
signal_power = mean(abs(received(:)).^2);
noise_power = signal_power/10^(options.snr_db/10);
noise = sqrt(noise_power/2)*(randn(stream,size(received)) + ...
    1j*randn(stream,size(received)));
received = received + noise;

if options.prepend_samples > 0
    received = [zeros(options.prepend_samples,size(received,2)); received];
end
if options.crop_start_samples > 0
    first = min(options.crop_start_samples+1, size(received,1));
    received = received(first:end,:);
end
if is_single
    samples = [real(received), imag(received)];
    if abs(options.channel_skew_samples) > 0
        axis_value = (1:size(samples,1)).';
        samples(:,2) = interp1(axis_value, samples(:,2), ...
            axis_value-options.channel_skew_samples, 'pchip', 0);
    end
else
    samples = received;
end
if isfinite(options.clip_level)
    if isreal(samples)
        samples = min(max(samples, -options.clip_level), options.clip_level);
    else
        magnitude = abs(samples);
        mask = magnitude > options.clip_level;
        samples(mask) = options.clip_level * ...
            samples(mask)./magnitude(mask);
    end
end

time = (0:size(samples,1)-1).'/rate;
time_axes = [time, time + options.time_axis_skew_samples/rate];
raw = struct('samples', samples, 'time_axes', time_axes, ...
    'sample_rate_hz', rate, 'already_baseband', ~is_single, ...
    'architecture', architecture, 'iq_pair', is_single, ...
    'payload_pair', upper(char(string(payload_pair))), ...
    'full_scale', options.clip_level, ...
    'simulation_options', options);
end

function out = defaults(value, base)
out = base;
names = fieldnames(value);
for k = 1:numel(names), out.(names{k}) = value.(names{k}); end
end

function value = repeat_capture_segments(value, repetitions, padding_samples)
repetitions = max(1,round(double(repetitions)));
padding_samples = max(0,round(double(padding_samples)));
if repetitions == 1
    return;
end
parts = cell(1,2*repetitions-1);
for index = 1:repetitions
    parts{2*index-1} = value;
    if index < repetitions
        parts{2*index} = zeros(padding_samples,size(value,2));
    end
end
value = vertcat(parts{:});
end
