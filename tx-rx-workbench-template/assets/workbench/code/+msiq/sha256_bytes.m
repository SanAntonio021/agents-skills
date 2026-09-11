function hash = sha256_bytes(varargin)
%SHA256_BYTES Hash numeric/logical/text inputs as a deterministic byte stream.

digest = java.security.MessageDigest.getInstance('SHA-256');
for k = 1:nargin
    value = varargin{k};
    if ischar(value) || isstring(value)
        bytes = unicode2native(char(string(value)), 'UTF-8');
    elseif islogical(value)
        bytes = uint8(value(:));
    elseif isnumeric(value)
        bytes = typecast(value(:), 'uint8');
    else
        error('msiq:hash:UnsupportedType', ...
            'Unsupported hash input type: %s', class(value));
    end
    digest.update(typecast(bytes(:), 'int8'));
end
raw = typecast(int8(digest.digest()), 'uint8');
hash = lower(reshape(dec2hex(raw, 2).', 1, []));
end
