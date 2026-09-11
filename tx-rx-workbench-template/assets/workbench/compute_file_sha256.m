function hash = compute_file_sha256(filepath)
%COMPUTE_FILE_SHA256 Return SHA256 hex digest for a local file.

    if nargin < 1 || isempty(filepath) || ~isfile(filepath)
        hash = 'UNKNOWN';
        return;
    end

    try
        md = java.security.MessageDigest.getInstance('SHA-256');
        fid = fopen(filepath, 'rb');
        if fid < 0
            hash = 'UNKNOWN';
            return;
        end
        cleanup = onCleanup(@() fclose(fid));

        while true
            bytes = fread(fid, 1024*1024, '*uint8');
            if isempty(bytes)
                break;
            end
            md.update(typecast(bytes(:), 'int8'));
        end

        digest = typecast(int8(md.digest()), 'uint8');
        hash = lower(reshape(dec2hex(digest, 2).', 1, []));
    catch
        hash = 'UNKNOWN';
    end
end
