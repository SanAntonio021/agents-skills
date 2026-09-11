function finalize_failure(run, exception, reason, updates)
%FINALIZE_FAILURE Retain diagnostics and close a failed staged run.

if nargin < 4, updates = struct(); end
try
    if ~isempty(fieldnames(updates))
        Result_Update_Run_Info(run, updates);
    end
catch
end
try
    Result_Log_Stage(run, 'ERROR', 'failure', '%s: %s', ...
        exception.identifier, exception.message);
catch
end
try
    create_failure_overview(run, exception);
catch
end
try
    Result_Finalize_Run(run, 'failed', reason, [], exception.message);
catch
end
end

function create_failure_overview(run, exception)
path = fullfile(run.OutputDir, 'overview.png');
if isfile(path)
    return;
end
identifier = exception.identifier;
if isempty(identifier)
    identifier = 'unhandled_exception';
end
Test_Project_Plot_Plan(path, 1, struct( ...
    'Title', ['FAILED: ', identifier], ...
    'XName', '失败运行', 'XUnit', '-', 'PlannedCount', 1, ...
    'Stages', {{'运行失败','查看 run_log.txt 和 run_info.json'}}));
end
