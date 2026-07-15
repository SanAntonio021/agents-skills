function stats = Test_Project_Plot_Scan_Summary(outputPath, scanValues, metrics, options)
%TEST_PROJECT_PLOT_SCAN_SUMMARY Plot repeated observations and grouped statistics.
% metrics is a struct array with Name, Unit and Values fields. Optional
% YScale may be 'linear' or 'log'. Failed rows are excluded with SuccessMask.

if nargin < 4 || isempty(options)
    options = struct();
end

style = Test_Project_Plot_Style();
scanValues = validateVector(scanValues, 'scanValues');
metricList = validateMetrics(metrics, numel(scanValues));
metricCount = numel(metricList);
successMask = resolveSuccessMask(options, numel(scanValues));
plannedCount = resolvePlannedCount(options, numel(scanValues));
successfulCount = nnz(successMask);
scanName = optionText(options, 'XName', '扫描变量');
scanUnit = optionText(options, 'XUnit', '-');
figureTitle = optionText(options, 'Title', '扫描汇总');

finiteScan = isfinite(scanValues);
groupValues = unique(scanValues(finiteScan), 'sorted');
if isempty(groupValues)
    error('TestProject:Plot:NoValidScanValues', 'scanValues 没有有效数值。');
end

figureWidth = 7.1;
figureHeight = max(4.8, 2.35 * metricCount + 0.9);
fig = figure('Visible', 'off', 'Units', 'inches', ...
    'Position', [1 1 figureWidth figureHeight], 'Color', style.FigureColor);
figureCleanup = onCleanup(@() closeFigure(fig));
layout = tiledlayout(fig, metricCount, 1, ...
    'TileSpacing', 'compact', 'Padding', 'compact');

metricStats = repmat(struct( ...
    'Name', '', 'Unit', '', 'X', [], 'Mean', [], 'Std', [], ...
    'ValidCount', [], 'YScale', '', 'ZeroCount', 0), 1, metricCount);

for metricIndex = 1:metricCount
    metric = metricList(metricIndex);
    values = metric.Values(:);
    displayValues = values;
    yScale = metricYScale(metric);
    statsValid = successMask & finiteScan & isfinite(values);
    zeroMask = false(size(values));
    if strcmp(yScale, 'log')
        statsValid = statsValid & values >= 0;
        zeroMask = statsValid & values == 0;
        if any(zeroMask)
            bitCounts = metricBitCounts(metric, numel(values));
            if any(~isfinite(bitCounts(zeroMask)) | bitCounts(zeroMask) <= 0)
                error('TestProject:Plot:InvalidBitCounts', ...
                    '对数指标的零值需要对应的正有效 bit 数。');
            end
            displayValues(zeroMask) = 1 ./ bitCounts(zeroMask);
        end
    end
    valid = statsValid & isfinite(displayValues);
    if strcmp(yScale, 'log')
        valid = valid & displayValues > 0;
    end

    [means, deviations, counts] = groupedStatistics( ...
        scanValues, values, groupValues, statsValid);
    metricStats(metricIndex).Name = metric.Name;
    metricStats(metricIndex).Unit = metric.Unit;
    metricStats(metricIndex).X = groupValues;
    metricStats(metricIndex).Mean = means;
    metricStats(metricIndex).Std = deviations;
    metricStats(metricIndex).ValidCount = counts;
    metricStats(metricIndex).YScale = yScale;
    metricStats(metricIndex).ZeroCount = nnz(zeroMask);

    ax = nexttile(layout, metricIndex);
    hold(ax, 'on');
    regularMask = valid & ~zeroMask;
    rawHandle = scatter(ax, scanValues(regularMask), displayValues(regularMask), ...
        style.RawMarkerArea, style.RawPointColor, 'filled', ...
        'Marker', 'o', ...
        'DisplayName', '单次结果');
    zeroHandle = gobjects(1);
    if any(zeroMask)
        zeroHandle = scatter(ax, scanValues(zeroMask), displayValues(zeroMask), ...
            style.RawMarkerArea * 1.25, style.RawPointColor, ...
            'Marker', 'v', 'MarkerFaceColor', 'none', 'LineWidth', 1.0, ...
            'DisplayName', '0 BER（显示位置为 1/N）');
    end

    meanColor = style.Colors(mod(metricIndex - 1, size(style.Colors, 1)) + 1, :);
    plotMeans = means;
    if strcmp(yScale, 'log')
        plotMeans(plotMeans <= 0) = nan;
    end
    meanHandle = plotContiguousMeans(ax, groupValues, plotMeans, meanColor, style);
    meanValid = isfinite(plotMeans);
    errorValid = meanValid & isfinite(deviations);
    negativeError = deviations(errorValid);
    if strcmp(yScale, 'log')
        negativeError = min(negativeError, means(errorValid) * (1 - 1e-9));
    end
    errorHandle = gobjects(1);
    if any(errorValid)
        errorHandle = errorbar(ax, groupValues(errorValid), means(errorValid), ...
            negativeError, deviations(errorValid), ...
            'LineStyle', 'none', ...
            'Color', meanColor, ...
            'LineWidth', 1.0, ...
            'CapSize', 6, ...
            'DisplayName', '均值 ±1 标准差');
    end

    set(ax, 'YScale', yScale);
    ylabel(ax, quantityLabel(metric.Name, metric.Unit), ...
        'FontSize', style.AxisLabelFontSize);
    if metricIndex == metricCount
        xlabel(ax, quantityLabel(scanName, scanUnit), ...
            'FontSize', style.AxisLabelFontSize);
    else
        ax.XTickLabel = [];
    end
    if metricIndex == 1
        title(ax, {metric.Name, ...
            sprintf('成功采集：%d/%d', successfulCount, plannedCount)}, ...
            'FontSize', style.TitleFontSize, 'FontWeight', 'normal');
    else
        title(ax, metric.Name, ...
            'FontSize', style.TitleFontSize, 'FontWeight', 'normal');
    end
    legendHandles = gobjects(0);
    legendNames = {};
    if any(regularMask)
        legendHandles(end + 1) = rawHandle; %#ok<AGROW>
        legendNames{end + 1} = '单次结果'; %#ok<AGROW>
    end
    if any(zeroMask)
        legendHandles(end + 1) = zeroHandle; %#ok<AGROW>
        legendNames{end + 1} = '0 BER（显示位置为 1/N）'; %#ok<AGROW>
    end
    if any(meanValid)
        legendHandles(end + 1) = meanHandle; %#ok<AGROW>
        legendNames{end + 1} = '均值'; %#ok<AGROW>
    end
    if any(errorValid)
        legendHandles(end + 1) = errorHandle; %#ok<AGROW>
        legendNames{end + 1} = '均值 ±1 标准差'; %#ok<AGROW>
    end
    if ~isempty(legendHandles)
        legend(ax, legendHandles, legendNames, ...
            'Location', 'best', 'Box', 'off', ...
            'FontName', style.FontName, 'FontSize', style.FontSize - 1);
    end
    Test_Project_Apply_Axes_Style(ax, style);
    setScanXLimits(ax, groupValues);
end

sgtitle(layout, figureTitle, ...
    'FontName', style.FontName, ...
    'FontSize', style.TitleFontSize + 1, ...
    'FontWeight', 'normal', ...
    'Interpreter', 'none');
outputPath = Test_Project_Export_PNG(fig, outputPath, style);

stats = struct();
stats.OutputPath = outputPath;
stats.SuccessfulCount = successfulCount;
stats.PlannedCount = plannedCount;
stats.Metrics = metricStats;
stats.ResolutionDPI = style.ResolutionDPI;
end

function vector = validateVector(value, name)
if ~isnumeric(value) || ~isvector(value) || isempty(value)
    error('TestProject:Plot:InvalidVector', '%s 必须是非空数值向量。', name);
end
vector = value(:);
end

function metricList = validateMetrics(metrics, rowCount)
if ~isstruct(metrics) || isempty(metrics)
    error('TestProject:Plot:InvalidMetrics', 'metrics 必须是非空 struct 数组。');
end
metricList = reshape(metrics, 1, []);
requiredFields = {'Name', 'Unit', 'Values'};
for metricIndex = 1:numel(metricList)
    for fieldIndex = 1:numel(requiredFields)
        if ~isfield(metricList(metricIndex), requiredFields{fieldIndex})
            error('TestProject:Plot:MissingMetricField', ...
                'metrics(%d) 缺少字段 %s。', ...
                metricIndex, requiredFields{fieldIndex});
        end
    end
    metricList(metricIndex).Name = char(string(metricList(metricIndex).Name));
    metricList(metricIndex).Unit = char(string(metricList(metricIndex).Unit));
    values = metricList(metricIndex).Values;
    if ~isnumeric(values) || ~isvector(values) || numel(values) ~= rowCount
        error('TestProject:Plot:MetricSizeMismatch', ...
            'metrics(%d).Values 必须与 scanValues 等长。', metricIndex);
    end
    metricList(metricIndex).Values = values(:);
end
end

function successMask = resolveSuccessMask(options, rowCount)
if isfield(options, 'SuccessMask') && ~isempty(options.SuccessMask)
    value = options.SuccessMask;
    if ~(islogical(value) || isnumeric(value)) || ~isvector(value) || ...
            numel(value) ~= rowCount || any(~isfinite(double(value(:))))
        error('TestProject:Plot:InvalidSuccessMask', ...
            'SuccessMask 必须是与 scanValues 等长的逻辑向量。');
    end
    successMask = logical(value(:));
else
    successMask = true(rowCount, 1);
end
end

function plannedCount = resolvePlannedCount(options, rowCount)
if isfield(options, 'PlannedCount') && ~isempty(options.PlannedCount)
    plannedCount = double(options.PlannedCount);
    if ~isscalar(plannedCount) || ~isfinite(plannedCount) || ...
            plannedCount < rowCount || plannedCount ~= fix(plannedCount)
        error('TestProject:Plot:InvalidPlannedCount', ...
            'PlannedCount 必须是不小于现有记录数的非负整数。');
    end
else
    plannedCount = rowCount;
end
end

function textValue = optionText(options, fieldName, defaultValue)
if isfield(options, fieldName) && ~isempty(options.(fieldName))
    textValue = char(string(options.(fieldName)));
else
    textValue = defaultValue;
end
end

function yScale = metricYScale(metric)
if isfield(metric, 'YScale') && ~isempty(metric.YScale)
    yScale = lower(char(string(metric.YScale)));
else
    yScale = 'linear';
end
if ~ismember(yScale, {'linear', 'log'})
    error('TestProject:Plot:InvalidYScale', ...
        'YScale 只能是 linear 或 log。');
end
end

function bitCounts = metricBitCounts(metric, rowCount)
if isfield(metric, 'BitCounts') && ~isempty(metric.BitCounts)
    value = metric.BitCounts;
elseif isfield(metric, 'BitCount') && ~isempty(metric.BitCount)
    value = metric.BitCount;
else
    error('TestProject:Plot:MissingBitCounts', ...
        '对数指标的零值需要 BitCounts 或 BitCount。');
end
if ~isnumeric(value) || ~isvector(value) || ...
        ~(isscalar(value) || numel(value) == rowCount)
    error('TestProject:Plot:InvalidBitCounts', ...
        'BitCounts 必须是标量或与 Values 等长的数值向量。');
end
if isscalar(value)
    bitCounts = repmat(double(value), rowCount, 1);
else
    bitCounts = double(value(:));
end
end

function [means, deviations, counts] = groupedStatistics(x, y, groupValues, valid)
groupCount = numel(groupValues);
means = nan(groupCount, 1);
deviations = nan(groupCount, 1);
counts = zeros(groupCount, 1);
for groupIndex = 1:groupCount
    groupMask = valid & x == groupValues(groupIndex);
    groupData = y(groupMask);
    counts(groupIndex) = numel(groupData);
    if ~isempty(groupData)
        means(groupIndex) = mean(groupData);
    end
    if numel(groupData) >= 2
        deviations(groupIndex) = std(groupData, 0);
    end
end
end

function handle = plotContiguousMeans(ax, x, means, color, style)
valid = isfinite(means);
starts = find(diff([false; valid; false]) == 1);
stops = find(diff([false; valid; false]) == -1) - 1;
handle = gobjects(1);
for segmentIndex = 1:numel(starts)
    indices = starts(segmentIndex):stops(segmentIndex);
    segmentHandle = plot(ax, x(indices), means(indices), '-o', ...
        'Color', color, ...
        'LineWidth', style.LineWidth, ...
        'MarkerSize', style.MeanMarkerSize, ...
        'MarkerFaceColor', [1 1 1], ...
        'DisplayName', '均值');
    if segmentIndex == 1
        handle = segmentHandle;
    else
        segmentHandle.HandleVisibility = 'off';
    end
end
if ~isgraphics(handle)
    handle = plot(ax, nan, nan, '-o', ...
        'Color', color, ...
        'LineWidth', style.LineWidth, ...
        'MarkerSize', style.MeanMarkerSize, ...
        'MarkerFaceColor', [1 1 1], ...
        'DisplayName', '均值');
end
end

function setScanXLimits(ax, groupValues)
if numel(groupValues) == 1
    margin = max(abs(groupValues(1)) * 0.01, 0.5);
else
    spacing = diff(groupValues);
    margin = 0.35 * min(spacing(spacing > 0));
    if isempty(margin) || ~isfinite(margin)
        margin = 0.5;
    end
end
xlim(ax, [groupValues(1) - margin, groupValues(end) + margin]);
end

function label = quantityLabel(name, unit)
if isempty(unit) || strcmp(unit, '-')
    label = name;
else
    label = sprintf('%s (%s)', name, unit);
end
end

function closeFigure(fig)
if isgraphics(fig, 'figure')
    close(fig);
end
end
