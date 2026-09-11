function [primary, diagnostic] = equalize_dual(received, pair_ref, cfg)
%EQUALIZE_DUAL Apply fixed 2x2 RZF and augmented 4x4 RZF outputs.

if size(received,2) ~= 2
    error('msiq:dsp:DualDimension', ...
        'Dual IQ-MIMO receiver requires exactly two received channels.');
end
frame = pair_ref.receiver_known(1).frame;
X = zeros(2, frame.training_length);
for stream = 1:2
    X(stream,:) = pair_ref.receiver_known(stream).training_symbols(:).';
end
lambda = cfg.receiver.rzf_regularization;
timing_candidates = -3:3;
timing_nmse = inf(size(timing_candidates));
channel_candidates = cell(size(timing_candidates));
for candidate = 1:numel(timing_candidates)
    offset = timing_candidates(candidate);
    index = frame.training_start + offset + (0:frame.training_length-1);
    if index(1) < 1 || index(end) > size(received,1)
        continue;
    end
    Ycandidate = received(index,:).';
    Hcandidate = (Ycandidate*X') / (X*X' + lambda*eye(2));
    timing_nmse(candidate) = norm(Ycandidate-Hcandidate*X,'fro')^2 / ...
        max(norm(Ycandidate,'fro')^2, eps);
    channel_candidates{candidate} = Hcandidate;
end
[~, timing_index] = min(timing_nmse);
timing_offset = timing_candidates(timing_index);
H = channel_candidates{timing_index};
if isempty(H)
    error('msiq:dsp:TrainingTiming', ...
        'No valid training timing candidate was found.');
end
aligned = align_to_reference(received, timing_offset);
index = frame.training_start + (0:frame.training_length-1);
Y = aligned(index,:).';
H = (Y*X') / (X*X' + lambda*eye(2));
W = (H'*H + lambda*eye(2)) \ H';
equalized = (W*aligned.').';
primary = struct('name', 'rzf_2x2', 'channel_matrix', H, ...
    'equalizer_matrix', W, 'symbols', equalized, ...
    'output_dimension', size(equalized,2), ...
    'training_timing_offset_symbols', timing_offset, ...
    'training_timing_nmse', timing_nmse);

Yaug = [Y; conj(Y)];
Xaug = [X; conj(X)];
G = (Yaug*Xaug') / (Xaug*Xaug' + lambda*eye(4));
Waug = (G'*G + lambda*eye(4)) \ G';
all_augmented = [aligned.'; conj(aligned.')];
equalized_augmented = Waug*all_augmented;
diagnostic = struct('name', 'augmented_rzf_4x4', ...
    'channel_matrix', G, 'equalizer_matrix', Waug, ...
    'symbols', equalized_augmented(1:2,:).', ...
    'full_output_dimension', size(equalized_augmented,1), ...
    'reported_output_dimension', 2, ...
    'selection_policy', 'fixed_diagnostic_output_no_payload_selection');
end

function aligned = align_to_reference(received, offset)
aligned = nan(size(received));
if offset >= 0
    count = size(received,1)-offset;
    aligned(1:count,:) = received(1+offset:end,:);
else
    shift = -offset;
    count = size(received,1)-shift;
    aligned(1+shift:end,:) = received(1:count,:);
end
end
