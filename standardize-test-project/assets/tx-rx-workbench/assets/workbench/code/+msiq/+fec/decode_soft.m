function out = decode_soft(llr_bits, reference, cfg)
%DECODE_SOFT Decode complete blocks and report BER, BLER, and parity state.

if isfield(cfg, 'receiver') && isfield(cfg.receiver, 'debug_pre_fec_only') && ...
        isequal(cfg.receiver.debug_pre_fec_only, true)
    out = pre_fec_only(llr_bits, reference, cfg);
    return;
end
fec = msiq.fec.build(cfg);
if (isfield(reference, 'codeword_length') && ...
        reference.codeword_length ~= fec.codeword_length) || ...
        (isfield(reference, 'info_length') && reference.info_length ~= fec.info_length)
    error('msiq:fec:ReferenceMismatch', ...
        'Reference code dimensions do not match the decoder.');
end
llr_bits = double(llr_bits(:));
reference.info_bits = double(reference.info_bits(:));
reference.coded_bits = double(reference.coded_bits(:));

available_blocks = floor(numel(llr_bits) / fec.codeword_length);
available_blocks = min(available_blocks, ...
    floor(numel(reference.coded_bits) / fec.codeword_length));
available_blocks = min(available_blocks, ...
    floor(numel(reference.info_bits) / fec.info_length));
if isfield(reference, 'block_count')
    available_blocks = min(available_blocks, reference.block_count);
end

out = empty_result();
out.incomplete_tail_bits = mod(numel(llr_bits), fec.codeword_length);
out.discarded_llr_bits = numel(llr_bits) - ...
    available_blocks * fec.codeword_length;
if available_blocks < 1
    out.status = 'NO_FULL_BLOCK';
    return;
end

coded_count = available_blocks * fec.codeword_length;
info_count = available_blocks * fec.info_length;
llr_blocks = llr_bits(1:coded_count);
if isfinite(fec.llr_clip) && fec.llr_clip > 0
    llr_blocks = max(min(llr_blocks, fec.llr_clip), -fec.llr_clip);
end

hard_pre = double(llr_blocks < 0);
coded_ref = reference.coded_bits(1:coded_count);
out.pre_fec_bit_error_count = nnz(hard_pre ~= coded_ref);
out.pre_fec_bit_count = coded_count;
out.pre_fec_ber = out.pre_fec_bit_error_count / coded_count;

decoded_bits = zeros(info_count, 1);
actual_iterations = zeros(1, available_blocks);
final_parity_checks = zeros(fec.parity_check_count, available_blocks);
info_errors = zeros(1, available_blocks);
parity_ok = false(1, available_blocks);
for block = 1:available_blocks
    coded_index = (block-1)*fec.codeword_length + (1:fec.codeword_length);
    info_index = (block-1)*fec.info_length + (1:fec.info_length);
    [decoded, iterations, checks] = ldpcDecode( ...
        llr_blocks(coded_index), fec.decoder, fec.max_iterations, ...
        'OutputFormat', 'info', 'DecisionType', 'hard');
    decoded_bits(info_index) = double(decoded(:));
    actual_iterations(block) = iterations;
    final_parity_checks(:, block) = double(checks(:));
    parity_ok(block) = all(checks(:) == 0);
    info_errors(block) = nnz(decoded_bits(info_index) ~= ...
        reference.info_bits(info_index));
end

block_errors = (~parity_ok) | (info_errors > 0);
out.valid = true;
out.status = ternary(any(block_errors), 'BLOCK_ERROR', 'OK');
out.block_count = available_blocks;
out.block_error_count = nnz(block_errors);
out.bler = out.block_error_count / available_blocks;
out.actual_iterations = actual_iterations;
out.final_parity_checks = final_parity_checks;
out.parity_converged_per_block = parity_ok;
out.parity_converged = all(parity_ok);
out.info_bit_errors_per_block = info_errors;
out.decoded_bits = decoded_bits;
out.post_fec_bit_error_count = sum(info_errors);
out.post_fec_bit_count = info_count;
out.post_fec_ber = out.post_fec_bit_error_count / info_count;
end

function out = pre_fec_only(llr_bits, reference, cfg)
% No LDPC matrix, encoder, or decoder is constructed on this path.
spec = msiq.fec.specification(cfg);
out = empty_result();
out.decoder_executed = false;
out.decoder_status = 'NOT_RUN_DEBUG_PRE_FEC_ONLY';
out.block_error_count = NaN;
out.post_fec_bit_error_count = NaN;
out.post_fec_bit_count = NaN;
out.expected_block_count = NaN;
out.status = 'INVALID_REFERENCE';
required = {'block_count','codeword_length','info_length','coded_bits','info_bits'};
if ~isstruct(reference) || ~all(isfield(reference, required))
    return;
end
n = double(reference.block_count);
if ~isscalar(n) || ~isfinite(n) || n < 1 || n ~= fix(n) || ...
        ~isequal(n,double(cfg.waveform.ldpc_blocks_per_frame)) || ...
        ~isequal(double(reference.codeword_length), spec.codeword_length) || ...
        ~isequal(double(reference.info_length), spec.info_length)
    return;
end
out.expected_block_count = n;
coded_count = n * spec.codeword_length;
if numel(reference.coded_bits) ~= coded_count || ...
        numel(reference.info_bits) ~= n * spec.info_length || ...
        any(~ismember(reference.coded_bits(:), [0 1])) || ...
        any(~ismember(reference.info_bits(:), [0 1]))
    return;
end
llr_bits = double(llr_bits(:));
out.block_count = min(n, floor(numel(llr_bits)/spec.codeword_length));
out.incomplete_tail_bits = mod(numel(llr_bits), spec.codeword_length);
out.discarded_llr_bits = max(0, numel(llr_bits)-coded_count);
if numel(llr_bits) < coded_count
    out.status = 'INCOMPLETE_REFERENCE_BLOCKS';
    return;
end
if ~isreal(llr_bits) || any(~isfinite(llr_bits(1:coded_count)))
    out.status = 'NONFINITE_LLR';
    return;
end
out.pre_fec_bit_count = coded_count;
out.pre_fec_bit_error_count = nnz((llr_bits(1:coded_count)<0) ~= ...
    logical(reference.coded_bits(:)));
out.pre_fec_ber = out.pre_fec_bit_error_count/coded_count;
out.valid = true;
out.status = ternary(out.pre_fec_bit_error_count > 0, ...
    'PRE_FEC_BIT_ERROR', 'PRE_FEC_OK');
end

function out = empty_result()
out = struct( ...
    'valid', false, ...
    'status', 'DISABLED', ...
    'block_count', 0, ...
    'block_error_count', 0, ...
    'bler', NaN, ...
    'actual_iterations', [], ...
    'final_parity_checks', [], ...
    'parity_converged_per_block', false(1, 0), ...
    'parity_converged', false, ...
    'info_bit_errors_per_block', [], ...
    'pre_fec_bit_error_count', 0, ...
    'pre_fec_bit_count', 0, ...
    'pre_fec_ber', NaN, ...
    'post_fec_bit_error_count', 0, ...
    'post_fec_bit_count', 0, ...
    'post_fec_ber', NaN, ...
    'incomplete_tail_bits', 0, ...
    'discarded_llr_bits', 0, ...
    'decoded_bits', []);
end

function value = ternary(condition, if_true, if_false)
if condition
    value = if_true;
else
    value = if_false;
end
end
