function result = equalize_single_wl(received, pair_ref, cfg)
%EQUALIZE_SINGLE_WL Train one symbol-spaced widely-linear FSE.

if size(received,2) < 2
    input = received(:,1);
else
    input = received(:,1) + 1j*received(:,2);
end
frame = pair_ref.receiver_known(1).frame;
desired = pair_ref.receiver_known(1).training_symbols(:);
training_index = frame.training_start + (0:frame.training_length-1);
taps = cfg.receiver.wl_taps;
if mod(taps,2) == 0
    error('msiq:dsp:WlTaps', 'WL-FSE tap count must be odd.');
end
half = (taps-1)/2;
valid = training_index(training_index > half & ...
    training_index <= numel(input)-half);
desired_offset = valid - frame.training_start + 1;
features = feature_matrix(input, valid, half);
lambda = cfg.receiver.rzf_regularization;
coefficients = (features*features' + lambda*eye(2*taps)) \ ...
    (features*conj(desired(desired_offset)));

all_index = (half+1:numel(input)-half).';
all_features = feature_matrix(input, all_index, half);
output = nan(size(input));
output(all_index) = coefficients' * all_features;
result = struct('name', 'wl_fse', 'coefficients', coefficients, ...
    'symbols', output, 'output_dimension', 1, ...
    'training_only', true, 'payload_reference_used', false);
end

function features = feature_matrix(input, centers, half)
taps = 2*half+1;
features = zeros(2*taps, numel(centers));
for k = 1:numel(centers)
    value = input(centers(k)+half:-1:centers(k)-half);
    features(:,k) = [value(:); conj(value(:))];
end
end
