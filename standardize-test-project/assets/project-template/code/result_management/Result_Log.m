function Result_Log(run_or_path, level, message, varargin)
%RESULT_LOG Append a record using the default result-management stage.

Result_Log_Stage(run_or_path, level, 'result_management', message, varargin{:});

end
