function H = short_parity_check(cfg)
%SHORT_PARITY_CHECK Read licensed, local MathWorks data with public APIs.
% Do not redistribute the support MAT file in this repository.
path = getenv('MSIQ_DVBS2_MATRIX_FILE');
if isfield(cfg.fec, 'matrix_file') && ~isempty(cfg.fec.matrix_file)
    path = char(string(cfg.fec.matrix_file));
end
if isempty(path) || ~isfile(path)
    error('msiq:fec:ShortMatrixMissing', ...
        ['Set MSIQ_DVBS2_MATRIX_FILE or cfg.fec.matrix_file to the licensed ' ...
        'MathWorks dvbs2xLDPCParityMatrices.mat file on this computer.']);
end
fid = fopen(path, 'rb');
if fid < 0, error('msiq:fec:ShortMatrixRead', 'Cannot read the matrix file.'); end
cleanup = onCleanup(@() fclose(fid));
digest = msiq.sha256_bytes(fread(fid, Inf, '*uint8'));
clear cleanup;
expected = 'D5BBCBE41183707A806CD9928A1D90EEAF06C8B273B482175121C6F02258A941';
if ~strcmpi(digest, expected)
    error('msiq:fec:ShortMatrixHash', ...
        'Matrix file differs from the independently verified MathWorks support file.');
end
data = load(path, 'PT_8_9_S');
ij = double(data.PT_8_9_S);
H = logical(sparse(ij(:,1), ij(:,2), 1, 1800, 16200));
end
