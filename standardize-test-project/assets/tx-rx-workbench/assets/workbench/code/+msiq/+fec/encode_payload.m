function [transmitted_bits, reference] = encode_payload(cfg, seed, block_count)
%ENCODE_PAYLOAD Generate, encode, and scramble complete LDPC blocks.

if nargin < 3 || isempty(block_count)
    block_count = cfg.waveform.ldpc_blocks_per_frame;
end
validateattributes(block_count, {'numeric'}, ...
    {'scalar', 'integer', 'positive'});

fec = msiq.fec.build(cfg);
source_stream = RandStream('mt19937ar', 'Seed', double(seed));
scramble_stream = RandStream('mt19937ar', 'Seed', double(seed) + 104729);
info_bits = randi(source_stream, [0 1], fec.info_length * block_count, 1);
coded_bits = zeros(fec.codeword_length * block_count, 1);
for block = 1:block_count
    source_index = (block-1)*fec.info_length + (1:fec.info_length);
    coded_index = (block-1)*fec.codeword_length + (1:fec.codeword_length);
    coded_bits(coded_index) = double(ldpcEncode( ...
        logical(info_bits(source_index)), fec.encoder));
end

scramble_bits = randi(scramble_stream, [0 1], numel(coded_bits), 1);
transmitted_bits = xor(logical(coded_bits), logical(scramble_bits));
transmitted_bits = double(transmitted_bits);

reference = struct();
reference.info_bits = double(info_bits);
reference.coded_bits = double(coded_bits);
reference.transmitted_bits = transmitted_bits;
reference.scramble_bits = double(scramble_bits);
reference.block_count = block_count;
reference.codeword_length = fec.codeword_length;
reference.info_length = fec.info_length;
reference.seed = double(seed);
end
