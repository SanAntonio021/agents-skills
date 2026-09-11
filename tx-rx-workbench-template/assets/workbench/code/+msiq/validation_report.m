function guard = validation_report(action, varargin)
%VALIDATION_REPORT Persist only the small suite report, never successful fixtures.
persistent suites
if isempty(suites), suites = {}; end
guard = [];
switch action
    case 'begin'
        suites{end+1} = struct('root',varargin{1},'selection',varargin{2},'report',table());
        guard = onCleanup(@() msiq.validation_report('finish'));
    case 'set'
        if ~isempty(suites), suites{end}.report = varargin{1}; end
    case 'finish'
        suite = suites{end}; suites(end) = [];
        if isempty(suite.report), return; end
        try
            report = suite.report;
            success = report.Status == "PASS";
            failure = report.Status == "FAIL";
            run = Result_Create_Run(struct('ProjectRoot',suite.root, ...
                'ResultsRoot',suite.root,'OutputCategory','checks','RunType','checks', ...
                'NameParts',{{['validation_',suite.selection]}}, ...
                'ProjectName','multistream_iq_SC','TestName','software_validation', ...
                'ExecutionMode','dry_run','RunPurpose','validation', ...
                'EntryPoint','run_v2_validation.m','Parameters',struct('selection',suite.selection), ...
                'Counts',struct('planned',height(report),'executed',height(report), ...
                'succeeded',nnz(success),'failed',nnz(failure),'invalid',nnz(~success & ~failure))));
            Result_Summary_Initialize(run,{'case','status','seconds','note'},{'-','-','s','-'});
            Result_Summary_Append(run,table2cell(report(:,{'Name','Status','Seconds','Note'})));
            status = 'completed';
            if any(failure), status = 'completed_with_failures'; end
            metrics = struct('Name','耗时','Unit','s','Values',report.Seconds);
            plot_cleanup = msiq.plot_archive('begin',run.OutputDir,run.DataDir); %#ok<NASGU>
            Test_Project_Plot_Scan_Summary(fullfile(run.OutputDir,'overview.png'), ...
                (1:height(report)).',metrics,struct('Title','软件验证结果', ...
                'XName','用例','XUnit','-','PlannedCount',height(report),'SuccessMask',success));
            Result_Finalize_Run(run,status,'normal_completion',[],'Hardware-free validation.');
            fprintf('Validation report: %s\n',run.OutputDir);
        catch exception
            warning('msiq:validation:Report','Cannot save validation report: %s',exception.message);
        end
end
end
