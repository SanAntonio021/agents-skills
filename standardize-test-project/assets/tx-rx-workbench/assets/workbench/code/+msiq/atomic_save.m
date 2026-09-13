function atomic_save(path, record)
%ATOMIC_SAVE Replace a MAT artifact only after its complete temporary save.
temporary = [tempname(fileparts(path)), '.tmp'];
cleanup = onCleanup(@() remove_temporary(temporary));
save(temporary, '-struct', 'record', '-v7.3');
[ok, message] = movefile(temporary, path, 'f');
if ~ok, error('msiq:artifact:Save', 'Cannot save %s: %s', path, message); end
end

function remove_temporary(path)
if isfile(path), delete(path); end
end
