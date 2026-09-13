function [corrected, info] = pilot_track(symbols, known, cfg)
%PILOT_TRACK Correct phase/amplitude using distributed pilots only.

frame = known.frame;
positions = frame.pilot_positions_frame(:);
references = known.pilot_symbols(:);
valid = positions >= 1 & positions <= numel(symbols) & ...
    isfinite(symbols(positions));
positions = positions(valid);
references = references(valid);
received = symbols(positions);
if numel(positions) < 2
    error('msiq:dsp:PilotCount', ...
        'At least two valid distributed pilots are required.');
end

phasor = received(:).*conj(references(:));
phase = unwrap(angle(phasor));
amplitude = abs(received(:))./max(abs(references(:)), eps);
smooth_length = cfg.receiver.pilot_phase_smoothing;
if smooth_length > 1 && numel(phase) >= smooth_length
    phase = movmedian(phase, smooth_length);
    amplitude = movmedian(amplitude, smooth_length);
end
axis_value = (1:numel(symbols)).';
phase_track = interp1(positions, phase, axis_value, 'linear', 'extrap');
amplitude_track = interp1(positions, amplitude, axis_value, ...
    'linear', 'extrap');
median_amplitude = median(amplitude);
amplitude_track = min(max(amplitude_track, 0.35*median_amplitude), ...
    2.5*median_amplitude);
corrected = symbols(:)./max(amplitude_track, eps).*exp(-1j*phase_track);
pilot_error = corrected(positions)-references;
noise_variance = mean(abs(pilot_error).^2);

info = struct('pilot_count', numel(positions), ...
    'pilot_positions', positions, 'phase_track', phase_track, ...
    'amplitude_track', amplitude_track, ...
    'noise_variance', max(noise_variance, 1e-10), ...
    'pilot_evm', sqrt(noise_variance/mean(abs(references).^2)), ...
    'payload_reference_used', false);
end
