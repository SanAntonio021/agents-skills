function result = equalize_single_wz(frame_samples, pair_ref, cfg, training_only)
%EQUALIZE_SINGLE_WZ WZ-style training and pilot/DD widely-linear FSE.

if nargin < 4 || isempty(training_only)
    training_only = false;
end

if size(frame_samples,2) ~= 1
    error('msiq:dsp:WzEqualizerInput', ...
        'WZ traditional equalization requires one complex input stream.');
end
samples = frame_samples(:,1).';
known = pair_ref.receiver_known(1);
frame = known.frame;
sps = cfg.receiver.single_samples_per_symbol;
training_start = (frame.training_start-1)*sps+1;
service_start = (frame.service_start-1)*sps+1;

[main_taps, image_taps, training] = train_wl_nlms(samples, ...
    training_start, known.training_symbols, sps, cfg.receiver.wl_taps, ...
    cfg.receiver.wl_step_size, cfg.receiver.wl_passes, ...
    cfg.receiver.wl_mu_decay, cfg.receiver.wl_timing_offsets_samples);

training_output = apply_wl(samples, ...
    training_start+training.best_timing_offset_samples, ...
    frame.training_length, sps, main_taps, image_taps);
if training_only
    result = struct('name', 'wz_wl_fse_nlms', ...
        'training_symbols_equalized', training_output(:), ...
        'training_timing_offsets_samples', training.timing_offsets_samples, ...
        'training_timing_nmse', training.timing_nmse, ...
        'training_timing_offset_samples', ...
        training.best_timing_offset_samples, ...
        'training_timing_offset_symbols', ...
        training.best_timing_offset_samples/sps, ...
        'training_nmse', training.best_nmse, ...
        'processing_samples_per_symbol', sps, ...
        'training_only', true, 'payload_reference_used', false, ...
        'selection_policy', 'wz_training_only_no_payload_reference');
    return;
end
service_before_tracking = apply_wl(samples, ...
    service_start+training.best_timing_offset_samples, ...
    frame.service_length, sps, main_taps, image_taps);
if cfg.receiver.joint_track_enabled
    [service_output, final_main, final_image, tracking] = ...
        track_pilot_dd(samples, ...
        service_start+training.best_timing_offset_samples, ...
        frame.service_length, sps, main_taps, image_taps, ...
        cfg.waveform.modulation_order, frame.pilot_positions_service, ...
        known.pilot_symbols, cfg.receiver.joint_track_step_size, ...
        cfg.receiver.pll_alpha, cfg.receiver.pll_beta, ...
        cfg.receiver.track_max_error_fraction, ...
        cfg.receiver.track_pilot_acquire_count);
else
    service_output = apply_wl(samples, ...
        service_start+training.best_timing_offset_samples, ...
        frame.service_length, sps, main_taps, image_taps);
    final_main = main_taps;
    final_image = image_taps;
    tracking = struct('enabled',false,'update_count',0, ...
        'rejected_count',0,'phase_log',zeros(frame.service_length,1), ...
        'frequency_log',zeros(frame.service_length,1), ...
        'amplitude_log',abs(service_before_tracking(:)), ...
        'error_log',nan(frame.service_length,1));
end

symbols = nan(frame.symbol_count,1);
symbols(frame.training_start:frame.training_start+frame.training_length-1) = ...
    training_output(:);
symbols(frame.service_start:frame.service_start+frame.service_length-1) = ...
    service_output(:);

result = struct();
result.name = 'wz_wl_fse_nlms';
result.symbols = symbols;
result.output_dimension = 1;
result.main_taps = main_taps;
result.image_taps = image_taps;
result.final_main_taps = final_main;
result.final_image_taps = final_image;
result.training_symbols_equalized = training_output(:);
result.training_timing_offsets_samples = training.timing_offsets_samples;
result.training_timing_nmse = training.timing_nmse;
result.training_timing_offset_samples = ...
    training.best_timing_offset_samples;
result.training_timing_offset_symbols = ...
    training.best_timing_offset_samples/sps;
result.training_nmse = training.best_nmse;
result.processing_samples_per_symbol = sps;
result.tracking = tracking;
if isfield(cfg.receiver,'track_pilot_acquire_count')
    result.tracking.pilot_acquire_count = cfg.receiver.track_pilot_acquire_count;
end
% Observe the same window centers used by the fixed and adaptive equalizers.
service_centers = service_start+training.best_timing_offset_samples + ...
    (0:frame.service_length-1)*sps;
service_input = nan(frame.service_length,1);
valid_centers = service_centers >= 1 & service_centers <= numel(samples);
service_input(valid_centers) = samples(service_centers(valid_centers));
result.service_symbols_before_equalization = service_input;
result.service_symbols_before_tracking = service_before_tracking(:);
result.service_symbols_after_tracking = service_output(:);
result.training_only = false;
result.payload_reference_used = false;
result.selection_policy = 'wz_training_pilot_dd_no_payload_reference';
end

function [best_main, best_image, info] = train_wl_nlms( ...
        samples, start_sample, desired, sps, taps, step_size, passes, ...
        decay, timing_offsets)
desired = desired(:);
if mod(taps,2) == 0
    error('msiq:dsp:WzWlTaps', 'WZ WL-FSE tap count must be odd.');
end
timing_offsets = double(timing_offsets(:).');
timing_nmse = inf(size(timing_offsets));
main_store = cell(size(timing_offsets));
image_store = cell(size(timing_offsets));
half = (taps-1)/2;

for offset_index = 1:numel(timing_offsets)
    offset = timing_offsets(offset_index);
    main = zeros(taps,1);
    image = zeros(taps,1);
    main(half+1) = 1;
    for pass = 1:passes
        mu = step_size*decay^(pass-1);
        for symbol = 1:numel(desired)
            center = start_sample+offset+(symbol-1)*sps;
            if center-half < 1 || center+half > numel(samples)
                continue;
            end
            input = samples(center+half:-1:center-half).';
            output = main'*input+image'*conj(input);
            error_value = desired(symbol)-output;
            denominator = 2*sum(abs(input).^2)+1e-8;
            main = main+mu*input*conj(error_value)/denominator;
            image = image+mu*conj(input)*conj(error_value)/denominator;
        end
    end
    equalized = apply_wl(samples,start_sample+offset,numel(desired), ...
        sps,main,image);
    valid = isfinite(real(equalized)) & isfinite(imag(equalized));
    valid(1:floor(numel(valid)/4)) = false;
    if any(valid)
        timing_nmse(offset_index) = ...
            mean(abs(desired(valid)-equalized(valid).').^2)/ ...
            mean(abs(desired(valid)).^2);
    end
    main_store{offset_index} = main;
    image_store{offset_index} = image;
end
[best_nmse,best_index] = min(timing_nmse);
if ~isfinite(best_nmse)
    error('msiq:dsp:WzWlTraining', ...
        'WZ WL-FSE did not find a valid training timing.');
end
best_main = main_store{best_index};
best_image = image_store{best_index};
info = struct('timing_offsets_samples',timing_offsets, ...
    'timing_nmse',timing_nmse, ...
    'best_timing_offset_samples',timing_offsets(best_index), ...
    'best_nmse',best_nmse);
end

function output = apply_wl(samples,start_sample,count,sps,main,image)
main = main(:);
image = image(:);
half = (numel(main)-1)/2;
output = nan(1,count);
for symbol = 1:count
    center = start_sample+(symbol-1)*sps;
    if center-half < 1 || center+half > numel(samples)
        continue;
    end
    input = samples(center+half:-1:center-half).';
    output(symbol) = main'*input+image'*conj(input);
end
end

function [output,main,image,info] = track_pilot_dd( ...
        samples,start_sample,count,sps,main,image,order, ...
        pilot_positions,pilot_symbols,step_size,alpha,beta, ...
        maximum_error_fraction,minimum_pilot_count)
pilot_positions = pilot_positions(:);
pilot_symbols = pilot_symbols(:);
pilot_mask = false(1,count);
pilot_map = zeros(1,count);
valid_pilots = pilot_positions >= 1 & pilot_positions <= count;
pilot_mask(pilot_positions(valid_pilots)) = true;
pilot_map(pilot_positions(valid_pilots)) = pilot_symbols(valid_pilots);
constellation = qammod((0:order-1).',order,'UnitAveragePower',true);
distance = abs(constellation-constellation.');
distance(distance == 0) = inf;
maximum_error = maximum_error_fraction*min(distance(:));
half = (numel(main)-1)/2;
first_pilot = find(pilot_mask,1,'first');
if isempty(first_pilot)
    error('msiq:dsp:WzPilotCount', ...
        'WZ joint tracking requires at least one pilot.');
end
first_center = start_sample+(first_pilot-1)*sps;
first_input = samples(first_center+half:-1:first_center-half).';
first_output = main'*first_input+image'*conj(first_input);
phase_state = angle(first_output*conj(pilot_map(first_pilot)));
frequency_state = 0;
output = nan(1,count);
phase_log = nan(1,count);
frequency_log = nan(1,count);
amplitude_log = nan(1,count);
error_log = nan(1,count);
update_count = 0;
rejected_count = 0;
pilot_count = 0;

for symbol = 1:count
    center = start_sample+(symbol-1)*sps;
    if center-half < 1 || center+half > numel(samples)
        continue;
    end
    input = samples(center+half:-1:center-half).';
    raw_output = main'*input+image'*conj(input);
    rotated = raw_output*exp(-1j*phase_state);
    if pilot_mask(symbol)
        desired = pilot_map(symbol);
        reliable = true;
        pilot_count = pilot_count+1;
    else
        [decision_error,index] = min(abs(rotated-constellation).^2);
        desired = constellation(index);
        reliable = pilot_count >= minimum_pilot_count && ...
            sqrt(decision_error) <= maximum_error;
    end
    output(symbol) = rotated;
    phase_log(symbol) = phase_state;
    frequency_log(symbol) = frequency_state;
    amplitude_log(symbol) = abs(raw_output);
    phase_error = angle(rotated*conj(desired));
    if reliable
        desired_raw = desired*exp(1j*phase_state);
        equalizer_error = desired_raw-raw_output;
        error_log(symbol) = equalizer_error;
        denominator = 2*sum(abs(input).^2)+1e-8;
        main = main+step_size*input*conj(equalizer_error)/denominator;
        image = image+step_size*conj(input)*conj(equalizer_error)/denominator;
        frequency_state = frequency_state+beta*phase_error;
        phase_state = phase_state+frequency_state+alpha*phase_error;
        update_count = update_count+1;
    else
        phase_state = phase_state+frequency_state;
        if pilot_count >= minimum_pilot_count
            rejected_count = rejected_count+1;
        end
    end
end
info = struct('enabled',true,'update_count',update_count, ...
    'rejected_count',rejected_count,'phase_log',phase_log(:), ...
    'frequency_log',frequency_log(:),'amplitude_log',amplitude_log(:), ...
    'error_log',error_log(:),'payload_reference_used',false);
end
