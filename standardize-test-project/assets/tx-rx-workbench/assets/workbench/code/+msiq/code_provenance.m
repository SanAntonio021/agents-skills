function value = code_provenance(repo, entry)
%CODE_PROVENANCE Record the checkout and entry point used for a new run.
value = struct('git_commit','','git_dirty',true,'entry_file_sha256','');
if contains(repo,'"'), error('msiq:provenance:Path','Invalid repository path.'); end
[status,commit] = system(sprintf('git -C "%s" rev-parse HEAD',repo));
if status == 0, value.git_commit = strtrim(commit); end
[status,changes] = system(sprintf('git -C "%s" status --porcelain',repo));
if status == 0, value.git_dirty = ~isempty(strtrim(changes)); end
path = which(entry);
if isempty(path), path = fullfile(repo,entry); end
if isfile(path), value.entry_file_sha256 = msiq.file_sha256(path); end
end
