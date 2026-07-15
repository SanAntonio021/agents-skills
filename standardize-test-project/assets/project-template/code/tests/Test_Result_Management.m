function tests = Test_Result_Management
%TEST_RESULT_MANAGEMENT Hardware-free tests for the result-management API.

tests = functiontests(localfunctions);

end

function setupOnce(test_case)
test_root = [tempname, '_result_management'];
mkdir(test_root);
test_case.TestData.TestRoot = test_root;
test_case.TestData.CodeRoot = fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(test_case.TestData.CodeRoot, 'result_management'));
end

function teardownOnce(test_case)
rmpath(fullfile(test_case.TestData.CodeRoot, 'result_management'));
if isfolder(test_case.TestData.TestRoot)
    rmdir(test_case.TestData.TestRoot, 's');
end
end

function testScanDirectoryAndMetadata(test_case)
cfg = base_config(test_case.TestData.TestRoot, 'scan', '20260715_143000');
cfg.Parameters = struct('X', [1.0, 2.0], 'step', 0.1, 'fixed', 2.0);
cfg.Precision = struct('X', 1, 'step', 1, 'fixed', 1);
cfg.Units = struct('X', '', 'step', '', 'fixed', '');
cfg.RunPurpose = 'formal';
cfg.ExecutionMode = 'live';
cfg.CodeVersion = 'test-version';
cfg.ProjectName = 'template_test_project';
cfg.TestName = '通用控制变量扫描';
cfg.EntryPoint = 'Run_Test.m';
cfg.PrimaryVariable = struct('name', '控制变量', 'symbol', 'X', ...
    'unit', '-', 'start', 1.0, 'stop', 2.0, 'step', 0.1);
cfg.Counts = struct('planned', 11);
cfg.Safety = struct('preflight', 'passed');
run = Result_Create_Run(cfg);

expected_name = 'X1.0-2.0_step0.1_fixed2.0_20260715_143000';
verifyEqual(test_case, run.RunName, expected_name);
verifyEqual(test_case, run.OutputDir, ...
    fullfile(test_case.TestData.TestRoot, 'results', 'scan', expected_name));
verifyTrue(test_case, isfile(run.RunInfoPath));
verifyTrue(test_case, isfile(run.LogPath));

info = read_json(run.RunInfoPath);
required = {'schema_version', 'run_id', 'project_name', 'test_name', ...
    'run_kind', 'planned_run_kind', 'purpose', 'execution_mode', ...
    'status', 'stop_reason', 'stop_detail', 'started_at', 'finished_at', ...
    'entry_point', 'code', 'runtime', 'primary_variable', 'parameters', ...
    'inputs', 'instruments', 'counts', 'safety', 'source_runs', 'artifacts'};
verifyTrue(test_case, all(isfield(info, required)));
verifyFalse(test_case, any(isfield(info, ...
    {'run_type', 'run_purpose', 'start_time', 'end_time', 'sources'})));
verifyEqual(test_case, info.status, 'running');
verifyEqual(test_case, info.run_kind, 'scan');
verifyEqual(test_case, info.purpose, 'formal');
verifyEqual(test_case, info.execution_mode, 'hardware');
verifyEqual(test_case, info.project_name, 'template_test_project');
verifyEqual(test_case, info.test_name, '通用控制变量扫描');
verifyEqual(test_case, info.entry_point, 'Run_Test.m');
verifyEqual(test_case, info.code.version, 'test-version');
verifyTrue(test_case, all(isfield(info.code, ...
    {'git_commit', 'git_dirty', 'entry_file_sha256'})));
verifyEqual(test_case, info.runtime.name, 'MATLAB');
verifyEqual(test_case, info.runtime.version, 'R2023b');
verifyEqual(test_case, info.primary_variable.unit, '-');
verifyEqual(test_case, info.counts.planned, 11);
verifyEqual(test_case, info.counts.executed, 0);
verifyEqual(test_case, info.safety.preflight, 'passed');
verifyEqual(test_case, info.safety.shutdown, 'pending');
verifyNotEmpty(test_case, regexp(info.started_at, ...
    '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$', 'once'));
raw_info = read_text_utf8(run.RunInfoPath);
verifyNotEmpty(test_case, regexp(raw_info, '"finished_at"\s*:\s*null', 'once'));
verifyNotEmpty(test_case, regexp(raw_info, '"planned_run_kind"\s*:\s*null', 'once'));

columns = {'控制变量', '实验指标', 'BER', 'EVM', 'MER', ...
    '状态', 'repeat', 'attempt', '原始数据文件', '错误信息'};
units = {'-', '-', '-', '%', 'dB', '-', '-', '-', '-', '-'};
Result_Summary_Initialize(run, columns, units);
point_file = Result_Build_Point_Filename('X1.0', 1, 1, 'mat', false);
row = {Result_Format_Value(1.0, 1), 2.5, 1.2e-4, 6.8, 23.4, ...
    '成功', 1, 1, point_file, ''};
Result_Summary_Append(run, row);
lines = readlines(run.SummaryPath, 'EmptyLineRule', 'skip');
verifyEqual(test_case, numel(lines), 3);
verifyEqual(test_case, lines(1), ...
    "控制变量,实验指标,BER,EVM,MER,状态,repeat,attempt,原始数据文件,错误信息");
verifyEqual(test_case, lines(2), "-,-,-,%,dB,-,-,-,-,-");
verifyTrue(test_case, startsWith(lines(3), "1.0,2.5,"));

Result_Log(run, 'WARNING', 'Synthetic warning %d.', 1);
Result_Log_Stage(run, 'ERROR', 'acquisition', ...
    sprintf('Synthetic line 1\nSynthetic line 2'));
updated_counts = struct('planned', 11, 'executed', 11, ...
    'succeeded', 10, 'failed', 1, 'invalid', 0);
Result_Update_Run_Info(run, struct('counts', updated_counts));
info = Result_Finalize_Run(run, 'COMPLETED_WITH_FAILURES', ...
    'normal_completion', [], '');
verifyEqual(test_case, info.status, 'completed_with_failures');
verifyNotEmpty(test_case, info.finished_at);
verifyEqual(test_case, info.stop_reason, 'normal_completion');
verifyTrue(test_case, any(strcmp({info.artifacts.file}, 'summary.csv')));
log_lines = readlines(run.LogPath, 'EmptyLineRule', 'skip');
log_pattern = "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2} \| " + ...
    "(DEBUG|INFO|WARNING|ERROR) \| [a-z][a-z0-9_]* \| .+$";
verifyTrue(test_case, all(~cellfun(@isempty, ...
    regexp(cellstr(log_lines), char(log_pattern), 'once'))));
verifyTrue(test_case, any(contains(log_lines, ' | startup | ')));
verifyTrue(test_case, any(contains(log_lines, ' | result_management | ')));
verifyTrue(test_case, any(contains(log_lines, ' | acquisition | ')));
verifyTrue(test_case, any(contains(log_lines, ' | finish | ')));
verifyTrue(test_case, any(contains(log_lines, ...
    'Synthetic line 1 | Synthetic line 2')));
verifyTrue(test_case, Result_Check_Flat_Directory(run).IsFlat);
end

function testRunTypesAndAnalysisSources(test_case)
types = {'single_point', 'dry_run', 'simulation', 'analysis'};
runs = cell(size(types));
for k = 1:numel(types)
    cfg = base_config(test_case.TestData.TestRoot, types{k}, ...
        sprintf('20260715_15%02d00', k));
    cfg.NameParts = {['case', num2str(k)]};
    if strcmp(types{k}, 'dry_run')
        cfg.PlannedRunKind = 'scan';
    end
    runs{k} = Result_Create_Run(cfg);
    verifyTrue(test_case, isfolder(fullfile(test_case.TestData.TestRoot, ...
        'results', types{k})));
end

sources_path = Result_Write_Sources(runs{4}, ...
    {runs{1}.OutputDir, runs{2}.OutputDir});
verifyTrue(test_case, isfile(sources_path));
source_lines = readlines(sources_path, 'EmptyLineRule', 'skip');
expected_sources = string({fullfile('results', 'single_point', runs{1}.RunName); ...
    fullfile('results', 'dry_run', runs{2}.RunName)});
expected_sources = replace(expected_sources, '\', '/');
verifyEqual(test_case, source_lines, expected_sources);
analysis_info = read_json(runs{4}.RunInfoPath);
verifyEqual(test_case, numel(analysis_info.source_runs), 2);
verifyEqual(test_case, analysis_info.source_runs(1).path, ...
    char(expected_sources(1)));
dry_info = read_json(runs{2}.RunInfoPath);
verifyEqual(test_case, dry_info.planned_run_kind, 'scan');
verifyEqual(test_case, dry_info.execution_mode, 'dry_run');
verifyTrue(test_case, Result_Check_Flat_Directory(runs{4}).IsFlat);
end

function testPointNamesAndFormatting(test_case)
verifyEqual(test_case, Result_Format_Value(1, 1), '1.0');
verifyEqual(test_case, Result_Format_Value(-0.0001, 2), '0.00');
verifyEqual(test_case, ...
    Result_Format_Parameter('X', [1, 2], 1, ''), ...
    'X1.0-2.0');
verifyEqual(test_case, ...
    Result_Format_Parameter('P', [-10, 4], 1, 'dBm'), ...
    'P-10.0_to_4.0dBm');
verifyEqual(test_case, ...
    Result_Build_Point_Filename('X1.0', 1, 2, '.mat', false), ...
    'X1.0_repeat01_attempt02.mat');
verifyEqual(test_case, ...
    Result_Build_Point_Filename('X1.0', 1, 2, '.mat', true), ...
    'FAILED_X1.0_repeat01_attempt02.mat');
verifyEqual(test_case, Result_Format_Parameter('scan', 1, 0, ''), ...
    'scan1');
verifyError(test_case, ...
    @() Result_Format_Parameter('bad name', 1, 0, ''), ...
    'Result_Format_Parameter:UnsafeNamePart');
verifyEqual(test_case, ...
    Result_Build_Point_Filename('analysis', 1, 1, '.mat', false), ...
    'analysis_repeat01_attempt01.mat');
verifyError(test_case, ...
    @() Result_Build_Point_Filename('bad name', 1, 1, '.mat', false), ...
    'Result_Build_Point_Filename:UnsafeNamePart');
end

function testInvalidConfigLeavesNoRunDirectory(test_case)
cfg = base_config(test_case.TestData.TestRoot, 'dry_run', '20260715_155500');
cfg.NameParts = {'invalid_dry'};
cfg.PlannedRunKind = 'scan';
cfg.ExecutionMode = 'hardware';
expected = fullfile(test_case.TestData.TestRoot, 'results', 'dry_run', ...
    'invalid_dry_20260715_155500');
verifyError(test_case, @() Result_Create_Run(cfg), ...
    'Result_Create_Run:UnsafeDryRun');
verifyFalse(test_case, isfolder(expected));

cfg = base_config(test_case.TestData.TestRoot, 'scan', '20260715_155501');
cfg.NameParts = {'bad name'};
verifyError(test_case, @() Result_Create_Run(cfg), ...
    'Result_Create_Run:UnsafeNamePart');

cfg = base_config(test_case.TestData.TestRoot, 'scan', '20260715_155502');
cfg.NameParts = {'analysis'};
verifyError(test_case, @() Result_Create_Run(cfg), ...
    'Result_Create_Run:ReservedNamePart');
end

function testExplicitOutputAndNoOverwrite(test_case)
explicit_dir = fullfile(test_case.TestData.TestRoot, 'explicit_output');
cfg = base_config(test_case.TestData.TestRoot, 'dry_run', '20260715_160000');
cfg.NameParts = {'ignored_for_explicit_path'};
cfg.PlannedRunKind = 'scan';
cfg.OutputDir = explicit_dir;
run = Result_Create_Run(cfg);
verifyEqual(test_case, run.OutputDir, explicit_dir);
info = Result_Finalize_Run(run.RunInfoPath, 'DRY_RUN', ...
    'normal_completion', [], 'offline check');
verifyEqual(test_case, info.status, 'completed');
verifyEqual(test_case, info.stop_detail, 'offline check');
verifyEqual(test_case, read_json(run.RunInfoPath).status, 'completed');
verifyNotEmpty(test_case, readlines(run.LogPath, 'EmptyLineRule', 'skip'));
verifyError(test_case, @() Result_Create_Run(cfg), ...
    'Result_Create_Run:OutputExists');
end

function testCustomResultsRoot(test_case)
custom_root = fullfile(test_case.TestData.TestRoot, 'custom_results');
cfg = base_config(test_case.TestData.TestRoot, 'scan', '20260715_160500');
cfg.ResultsRoot = custom_root;
cfg.NameParts = {'custom_root'};
run = Result_Create_Run(cfg);
verifyEqual(test_case, run.ResultsRoot, custom_root);
verifyEqual(test_case, run.OutputDir, fullfile(custom_root, 'scan', ...
    'custom_root_20260715_160500'));
verifyTrue(test_case, isfolder(run.OutputDir));
end

function testSummaryCsvEscapingAndColumnCheck(test_case)
cfg = base_config(test_case.TestData.TestRoot, 'single_point', '20260715_161000');
cfg.NameParts = {'csv_escape'};
run = Result_Create_Run(cfg);
Result_Summary_Initialize(run, {'指标', '状态', '错误信息'}, {'dB', '-', '-'});
Result_Summary_Append(run, {1.25, '失败,重试', '包含"引号"'});
text = fileread(run.SummaryPath);
fid = fopen(run.SummaryPath, 'r');
bom = fread(fid, 3, '*uint8').';
fclose(fid);
verifyEqual(test_case, bom, uint8([239, 187, 191]));
verifyNotEmpty(test_case, regexp(text, '"失败,重试"', 'once'));
verifyNotEmpty(test_case, regexp(text, '"包含""引号"""', 'once'));
verifyError(test_case, @() Result_Summary_Append(run, {1, 2}), ...
    'Result_Summary_Append:ColumnCountMismatch');
end

function testFlatDirectoryDetection(test_case)
cfg = base_config(test_case.TestData.TestRoot, 'simulation', '20260715_162000');
cfg.NameParts = {'flat_check'};
run = Result_Create_Run(cfg);
subdir = fullfile(run.OutputDir, 'forbidden_subdir');
mkdir(subdir);
report = Result_Check_Flat_Directory(run);
verifyFalse(test_case, report.IsFlat);
verifyEqual(test_case, report.Subdirectories, {'forbidden_subdir'});
rmdir(subdir);
end

function testFailedRunKeepsRequiredRecords(test_case)
cfg = base_config(test_case.TestData.TestRoot, 'scan', '20260715_163000');
cfg.NameParts = {'failed_case'};
run = Result_Create_Run(cfg);
Result_Summary_Initialize(run, ...
    {'控制变量', '状态', 'repeat', 'attempt', '原始数据文件', '错误信息'}, ...
    {'-', '-', '-', '-', '-', '-'});
failed_file = Result_Build_Point_Filename('X1.0', 1, 2, '.mat', true);
Result_Summary_Append(run, ...
    {'1.0', '失败', 1, 2, failed_file, 'synthetic failure'});
Result_Log_Stage(run, 'ERROR', 'acquisition', ...
    'Synthetic failure for offline test.');
info = Result_Finalize_Run(run, 'FAILED', ...
    'unhandled_exception', [], 'synthetic failure');

verifyEqual(test_case, info.status, 'failed');
verifyEqual(test_case, info.stop_reason, 'unhandled_exception');
verifyEqual(test_case, info.stop_detail, 'synthetic failure');
verifyTrue(test_case, isfile(run.RunInfoPath));
verifyTrue(test_case, isfile(run.SummaryPath));
verifyTrue(test_case, isfile(run.LogPath));
verifyTrue(test_case, Result_Check_Flat_Directory(run).IsFlat);
end

function testRepeatedAtomicJsonUpdatesLeaveNoTemporaryFiles(test_case)
cfg = base_config(test_case.TestData.TestRoot, 'dry_run', '20260715_164000');
cfg.NameParts = {'atomic_updates'};
cfg.PlannedRunKind = 'scan';
run = Result_Create_Run(cfg);
for executed = 1:20
    Result_Update_Run_Info(run, struct('counts', struct('executed', executed)));
    verifyEqual(test_case, read_json(run.RunInfoPath).counts.executed, executed);
end
listing = dir(run.OutputDir);
listing = listing(~[listing.isdir]);
verifyEqual(test_case, sort({listing.name}), ...
    sort({'run_info.json', 'run_log.txt'}));
end

function cfg = base_config(project_root, run_type, timestamp)
cfg = struct();
cfg.ProjectRoot = project_root;
cfg.RunType = run_type;
cfg.RunTimestamp = timestamp;
end

function value = read_json(path)
fid = fopen(path, 'r', 'n', 'UTF-8');
cleanup = onCleanup(@() fclose(fid));
value = jsondecode(fread(fid, '*char').');
end

function text = read_text_utf8(path)
fid = fopen(path, 'r', 'n', 'UTF-8');
cleanup = onCleanup(@() fclose(fid));
text = fread(fid, '*char').';
end
