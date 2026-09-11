function audit = audit_v1_golden(record_dir)
%AUDIT_V1_GOLDEN Recompute BLER/parity from a read-only V1 1 km record.

record_dir = char(string(record_dir));
path = fullfile(record_dir, 'rx_record.mat');
if ~isfile(path)
    error('msiq:golden:RecordMissing', 'Missing V1 rx_record.mat: %s', path);
end
source = load(path, 'MultiPacket', 'Res1', 'Res2');
if ~isfield(source, 'MultiPacket') || ...
        ~isfield(source.MultiPacket, 'PacketResults') || ...
        isempty(source.MultiPacket.PacketResults)
    error('msiq:golden:PacketResultsMissing', ...
        'V1 record has no packet-level decode results.');
end

packets = source.MultiPacket.PacketResults;
streams = repmat(struct(), 1, 2);
for stream = 1:2
    field = sprintf('Res%d', stream);
    parity = false(1, numel(packets));
    info_errors = zeros(1, numel(packets));
    iterations = nan(1, numel(packets));
    final_checks = cell(1, numel(packets));
    for packet = 1:numel(packets)
        result = packets(packet).(field);
        checks = result.LDPC_FinalParityChecks;
        final_checks{packet} = checks;
        parity(packet) = ~isempty(checks) && all(checks(:) == 0);
        info_errors(packet) = result.PostFEC_BitErrCount;
        iterations(packet) = result.LDPC_ActualIterations;
    end
    block_errors = ~parity | info_errors > 0;
    top = source.(field);
    streams(stream).stream = stream;
    streams(stream).block_count = numel(packets);
    streams(stream).block_error_count = nnz(block_errors);
    streams(stream).bler = nnz(block_errors)/numel(packets);
    streams(stream).actual_iterations = iterations;
    streams(stream).final_parity_checks = final_checks;
    streams(stream).parity_converged_per_block = parity;
    streams(stream).parity_converged = all(parity);
    streams(stream).pre_fec_ber = top.PreFEC_BER;
    streams(stream).post_fec_ber = top.PostFEC_BER;
    streams(stream).post_fec_bit_error_count = sum(info_errors);
    streams(stream).pass = all(parity) && all(info_errors == 0);
end
audit = struct('record_dir', record_dir, 'source_modified', false, ...
    'stream_count', 2, 'streams', streams, ...
    'all_streams_pass', all([streams.pass]));
end
