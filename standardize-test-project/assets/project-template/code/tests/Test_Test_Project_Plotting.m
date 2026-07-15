function tests = Test_Test_Project_Plotting
%TEST_TEST_PROJECT_PLOTTING Offline tests for the shared plotting layer.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
testFile = mfilename('fullpath');
testDir = fileparts(testFile);
projectRoot = fileparts(fileparts(testDir));
plottingDir = fullfile(projectRoot, 'code', 'plotting');
outputDir = [tempname, '_plotting_standard'];
mkdir(outputDir);
addpath(plottingDir);
testCase.TestData.PlottingDir = plottingDir;
testCase.TestData.OutputDir = outputDir;
rng(20260715, 'twister');
end

function teardownOnce(testCase)
rmpath(testCase.TestData.PlottingDir);
if isfolder(testCase.TestData.OutputDir)
    rmdir(testCase.TestData.OutputDir, 's');
end
end

function testSharedStyle(testCase)
style = Test_Project_Plot_Style();
verifyEqual(testCase, style.ResolutionDPI, 300);
verifyEqual(testCase, style.FontName, 'Microsoft YaHei');
verifyGreaterThan(testCase, style.LineWidth, 1);
verifySize(testCase, style.Colors, [6 3]);
end

function testMultiChannelConstellation(testCase)
levels = [-3 -1 1 3];
[inPhase, quadrature] = meshgrid(levels, levels);
ideal = (inPhase(:) + 1i * quadrature(:)) / sqrt(10);
symbolCount = 5000;
tx1 = ideal(randi(numel(ideal), symbolCount, 1));
tx2 = ideal(randi(numel(ideal), symbolCount, 1));
rx1 = tx1 + 0.055 * (randn(symbolCount, 1) + 1i * randn(symbolCount, 1));
rx2 = tx2 + 0.075 * (randn(symbolCount, 1) + 1i * randn(symbolCount, 1));
rx1(1:2) = [2 + 2i; -2 - 2i];
metrics(1) = struct('BER', 1.2e-4, 'EVM', [], 'EVMPercent', 7.3, ...
    'MER', [], 'MERdB', 22.7);
metrics(2) = struct('BER', 3.1e-4, 'EVM', 8.1, 'EVMPercent', [], ...
    'MER', 21.8, 'MERdB', []);
options = struct( ...
    'Title', '双数据流 16QAM 星座图', ...
    'ChannelNames', {{'数据流 1', '数据流 2'}});
outputPath = fullfile(testCase.TestData.OutputDir, 'constellation_16qam_dual_stream.png');

details = Test_Project_Plot_Constellation( ...
    outputPath, {rx1, rx2}, ideal, metrics, options);

verifyEqual(testCase, details.ChannelCount, 2);
verifyEqual(testCase, details.ValidSymbolCount, [symbolCount symbolCount]);
verifyGreaterThanOrEqual(testCase, details.OutOfRangeCount(1), 2);
verifyEqual(testCase, details.ResolutionDPI, 300);
verifyEqual(testCase, details.AxisLimits(1:2), -details.AxisLimits(2:-1:1), ...
    'AbsTol', 1e-12);
verifyReadableImage(testCase, outputPath, 1500, 700);
end

function testSpectrum(testCase)
frequencyGHz = linspace(1.8, 2.2, 1601).';
noiseFloor1 = -91 + 0.35 * randn(size(frequencyGHz));
noiseFloor2 = -93 + 0.35 * randn(size(frequencyGHz));
trace1 = noiseFloor1 + 53 * exp(-0.5 * ((frequencyGHz - 2.000) / 0.006).^2);
trace2 = noiseFloor2 + 48 * exp(-0.5 * ((frequencyGHz - 2.018) / 0.008).^2);
options = struct( ...
    'Title', '接收中频频谱', ...
    'TraceNames', {{'数据流 1', '数据流 2'}}, ...
    'XName', '中频频率', ...
    'XUnit', 'GHz', ...
    'YName', '功率', ...
    'YUnit', 'dBm');
outputPath = fullfile(testCase.TestData.OutputDir, 'spectrum_dual_trace.png');

details = Test_Project_Plot_Spectrum( ...
    outputPath, frequencyGHz, [trace1 trace2], options);

verifyEqual(testCase, details.TraceCount, 2);
verifyEqual(testCase, details.ValidPointCount, [1601 1601]);
verifyEqual(testCase, details.ResolutionDPI, 300);
verifyReadableImage(testCase, outputPath, 1500, 900);
verifyError(testCase, @() Test_Project_Plot_Spectrum( ...
    outputPath, frequencyGHz, [trace1 trace2], options), ...
    'TestProject:Plot:OutputExists');
end

function testDryRunPlanOverview(testCase)
plannedValues = [1 2 3];
options = struct('Title', 'dry-run 计划检查', ...
    'XName', '计划点序号', 'XUnit', '-', ...
    'PlannedCount', 6, ...
    'Stages', {{'计划检查', '路径检查', '保存检查'}});
outputPath = fullfile(testCase.TestData.OutputDir, 'dry_run_plan.png');

details = Test_Project_Plot_Plan(outputPath, plannedValues, options);

verifyEqual(testCase, details.PlannedPointCount, 3);
verifyEqual(testCase, details.PlannedCount, 6);
verifyEqual(testCase, details.ResolutionDPI, 300);
verifyReadableImage(testCase, outputPath, 1400, 900);
end

function testLogZeroRequiresBitCount(testCase)
metrics = struct('Name', 'BER', 'Unit', '-', ...
    'Values', [0 1e-4], 'YScale', 'log');
options = struct('XName', '控制变量', 'XUnit', '-', ...
    'SuccessMask', [true true], 'PlannedCount', 2);
outputPath = fullfile(testCase.TestData.OutputDir, 'missing_bit_count.png');
verifyError(testCase, @() Test_Project_Plot_Scan_Summary( ...
    outputPath, [1 2], metrics, options), ...
    'TestProject:Plot:MissingBitCounts');
end

function testScanSummaryWithMissingGroup(testCase)
controlValue = repelem((1.0:0.1:1.4).', 4);
repeatIndex = repmat((1:4).', 5, 1);
successMask = true(size(controlValue));
successMask(abs(controlValue - 1.1) < 1e-10 & repeatIndex == 4) = false;
successMask(abs(controlValue - 1.3) < 1e-10) = false;
successMask(abs(controlValue - 1.2) < 1e-10 & repeatIndex > 1) = false;

responseDb = -47 + 2.2 * (controlValue - 1.0) + 0.25 * randn(size(controlValue));
merDb = 18.5 + 1.4 * sin((controlValue - 1.0) * pi / 0.4) + ...
    0.18 * randn(size(controlValue));
ber = 10.^(-3.3 - 0.9 * (merDb - mean(merDb)));
ber(abs(controlValue - 1.0) < 1e-10) = 0;
responseDb(~successMask) = nan;
merDb(~successMask) = nan;
ber(~successMask) = nan;

metrics(1) = struct('Name', '响应指标', 'Unit', 'dB', ...
    'Values', responseDb, 'YScale', 'linear', 'BitCounts', []);
metrics(2) = struct('Name', '调制误差比', 'Unit', 'dB', ...
    'Values', merDb, 'YScale', 'linear', 'BitCounts', []);
metrics(3) = struct('Name', 'BER', 'Unit', '-', ...
    'Values', ber, 'YScale', 'log', 'BitCounts', 1e6 * ones(size(ber)));
options = struct( ...
    'Title', '控制变量扫描汇总', ...
    'XName', '控制变量', ...
    'XUnit', '-', ...
    'SuccessMask', successMask, ...
    'PlannedCount', numel(controlValue));
outputPath = fullfile(testCase.TestData.OutputDir, 'scan_summary_control.png');

stats = Test_Project_Plot_Scan_Summary( ...
    outputPath, controlValue, metrics, options);

verifyEqual(testCase, stats.SuccessfulCount, 12);
verifyEqual(testCase, stats.PlannedCount, 20);
missingIndex = find(abs(stats.Metrics(1).X - 1.3) < 1e-12, 1);
verifyNotEmpty(testCase, missingIndex);
verifyTrue(testCase, isnan(stats.Metrics(1).Mean(missingIndex)));
verifyEqual(testCase, stats.Metrics(1).ValidCount(missingIndex), 0);
singleIndex = find(abs(stats.Metrics(1).X - 1.2) < 1e-12, 1);
verifyEqual(testCase, stats.Metrics(1).ValidCount(singleIndex), 1);
verifyTrue(testCase, isnan(stats.Metrics(1).Std(singleIndex)));
zeroIndex = find(abs(stats.Metrics(3).X - 1.0) < 1e-12, 1);
verifyEqual(testCase, stats.Metrics(3).Mean(zeroIndex), 0, 'AbsTol', 0);
verifyEqual(testCase, stats.Metrics(3).ZeroCount, 4);
verifyEqual(testCase, stats.Metrics(3).YScale, 'log');
verifyReadableImage(testCase, outputPath, 1500, 1500);
end

function verifyReadableImage(testCase, path, minimumWidth, minimumHeight)
verifyTrue(testCase, isfile(path), sprintf('图片不存在：%s', path));
info = imfinfo(path);
verifyGreaterThanOrEqual(testCase, info.Width, minimumWidth);
verifyGreaterThanOrEqual(testCase, info.Height, minimumHeight);
imageData = imread(path);
verifyGreaterThan(testCase, std(double(imageData(:))), 2);
end
