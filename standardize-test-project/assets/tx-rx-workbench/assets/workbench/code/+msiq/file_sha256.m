function value = file_sha256(path)
fid = fopen(path,'rb');
if fid < 0, error('msiq:artifact:Missing','Cannot read %s.',path); end
cleanup = onCleanup(@() fclose(fid));
digest = java.security.MessageDigest.getInstance('SHA-256');
while ~feof(fid)
    bytes = fread(fid,1024*1024,'*uint8');
    if ~isempty(bytes), digest.update(typecast(bytes,'int8')); end
end
value = lower(reshape(dec2hex(typecast(digest.digest(),'uint8'),2).',1,[]));
end
