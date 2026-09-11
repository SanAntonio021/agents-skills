function save_tx_manifest(run_dir, plan, receipt, staged_receipt)
%SAVE_TX_MANIFEST Keep one complete TX plan, replacing it only after save.
path = msiq.artifact_path(run_dir, 'tx_manifest.mat', 'write');
if isfield(plan,'storage_run_root') && ~isempty(plan.storage_run_root)
    data = struct('waveforms',plan.waveforms,'download',plan.download,'tx_ref',plan.tx_ref);
    plan.shared_data = msiq.shared_tx_data('save',plan.storage_run_root,fileparts(path),data);
    plan = rmfield(plan,{'waveforms','download','tx_ref'});
end
temporary = [tempname(fileparts(path)), '.tmp'];
cleanup = onCleanup(@() remove_temporary(temporary));
record = struct('route', plan.route, 'plan', plan, 'receipt', receipt);
if nargin >= 4
    record.staged_receipt = staged_receipt;
end
save(temporary, '-struct', 'record', '-v7.3');
[ok, message] = movefile(temporary, path, 'f');
if ~ok
    error('msiq:txArtifact:Save', 'Cannot replace TX manifest: %s', message);
end
clear cleanup;
end

function remove_temporary(path)
if isfile(path), delete(path); end
end
