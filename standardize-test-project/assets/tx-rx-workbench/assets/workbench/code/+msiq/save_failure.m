function save_failure(run_dir, data)
%SAVE_FAILURE Preserve available failure data without hiding the original error.
try
    if isfolder(fullfile(run_dir,'data'))
        run_dir = fullfile(run_dir,'data');
    end
    path = fullfile(run_dir,'FAILED_diagnostic.mat');
    if isfile(path)
        path = fullfile(run_dir,['FAILED_',char(datetime('now', ...
            'Format','yyyyMMdd_HHmmss_SSS')),'_diagnostic.mat']);
    end
    msiq.atomic_save(path,data);
catch exception
    warning('msiq:output:FailureSave','Cannot preserve diagnostic in %s: %s', ...
        run_dir,exception.message);
end
end
