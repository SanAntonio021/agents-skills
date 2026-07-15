function details = Test_Project_Plot_Constellation(outputPath, receivedSymbols, idealSymbols, metrics, options)
%TEST_PROJECT_PLOT_CONSTELLATION Plot one or more data streams in one PNG.
% receivedSymbols and idealSymbols may be numeric arrays or cell arrays.
% Each numeric matrix column is treated as one data stream.

if nargin < 4 || isempty(metrics)
    metrics = struct([]);
end
if nargin < 5 || isempty(options)
    options = struct();
end

style = Test_Project_Plot_Style();
received = normalizeSymbolChannels(receivedSymbols, 'receivedSymbols');
ideal = normalizeIdealChannels(idealSymbols, numel(received));
channelCount = numel(received);
channelNames = optionCellText(options, 'ChannelNames', channelCount, '数据流');
figureTitle = optionText(options, 'Title', '星座图');
axisLimits = resolveAxisLimits(options, ideal);
metricList = normalizeMetrics(metrics, channelCount);

if channelCount == 1
    figureSize = style.SingleConstellationSizeInches;
else
    figureSize = style.MultiConstellationSizeInches;
end
fig = figure('Visible', 'off', 'Units', 'inches', ...
    'Position', [1 1 figureSize], 'Color', style.FigureColor);
figureCleanup = onCleanup(@() closeFigure(fig));
layout = tiledlayout(fig, 1, channelCount, ...
    'TileSpacing', 'compact', 'Padding', 'compact');

validCounts = zeros(1, channelCount);
outsideCounts = zeros(1, channelCount);
legendHandles = gobjects(1, 2);
for channelIndex = 1:channelCount
    ax = nexttile(layout, channelIndex);
    hold(ax, 'on');

    rx = received{channelIndex};
    rx = rx(isfinite(real(rx)) & isfinite(imag(rx)));
    ref = ideal{channelIndex};
    ref = ref(isfinite(real(ref)) & isfinite(imag(ref)));
    if isempty(rx)
        error('TestProject:Plot:NoValidSymbols', ...
            '数据流 %d 没有有效接收符号。', channelIndex);
    end
    if isempty(ref)
        error('TestProject:Plot:NoIdealSymbols', ...
            '数据流 %d 没有有效理想星座点。', channelIndex);
    end

    validCounts(channelIndex) = numel(rx);
    outsideCounts(channelIndex) = nnz(real(rx) < axisLimits(1) | ...
        real(rx) > axisLimits(2) | imag(rx) < axisLimits(3) | ...
        imag(rx) > axisLimits(4));
    color = style.Colors(mod(channelIndex - 1, size(style.Colors, 1)) + 1, :);
    receivedHandle = plot(ax, real(rx), imag(rx), '.', ...
        'Color', color, ...
        'MarkerSize', style.ConstellationMarkerSize, ...
        'DisplayName', '接收符号');
    idealHandle = plot(ax, real(ref), imag(ref), 'ks', ...
        'LineStyle', 'none', ...
        'MarkerSize', style.IdealMarkerSize, ...
        'LineWidth', 1.15, ...
        'DisplayName', '理想星座点');
    if channelIndex == 1
        legendHandles = [receivedHandle idealHandle];
    end

    axis(ax, 'equal');
    xlim(ax, axisLimits(1:2));
    ylim(ax, axisLimits(3:4));
    xlabel(ax, '同相分量', 'FontSize', style.AxisLabelFontSize);
    ylabel(ax, '正交分量', 'FontSize', style.AxisLabelFontSize);
    titleLines = [channelNames(channelIndex), ...
        metricTitleLines(metricList(channelIndex), validCounts(channelIndex), ...
        outsideCounts(channelIndex))];
    title(ax, titleLines, ...
        'FontSize', style.FontSize, 'FontWeight', 'normal');
    Test_Project_Apply_Axes_Style(ax, style);
end

legendHandle = legend(legendHandles, {'接收符号', '理想星座点'}, ...
    'Orientation', 'horizontal', ...
    'Box', 'off', ...
    'FontName', style.FontName, ...
    'FontSize', style.FontSize - 1);
legendHandle.Layout.Tile = 'south';

sgtitle(layout, figureTitle, ...
    'FontName', style.FontName, ...
    'FontSize', style.TitleFontSize + 1, ...
    'FontWeight', 'normal', ...
    'Interpreter', 'none');
outputPath = Test_Project_Export_PNG(fig, outputPath, style);

details = struct();
details.OutputPath = outputPath;
details.ChannelCount = channelCount;
details.ValidSymbolCount = validCounts;
details.OutOfRangeCount = outsideCounts;
details.AxisLimits = axisLimits;
details.ResolutionDPI = style.ResolutionDPI;
end

function channels = normalizeSymbolChannels(value, argumentName)
if iscell(value)
    channels = value(:).';
elseif isnumeric(value)
    if isvector(value)
        channels = {value(:)};
    else
        channels = mat2cell(value, size(value, 1), ones(1, size(value, 2)));
    end
else
    error('TestProject:Plot:InvalidSymbols', ...
        '%s 必须是数值数组或 cell 数组。', argumentName);
end
if isempty(channels)
    error('TestProject:Plot:EmptySymbols', '%s 不能为空。', argumentName);
end
for index = 1:numel(channels)
    if ~isnumeric(channels{index}) || ~isvector(channels{index})
        error('TestProject:Plot:InvalidSymbolChannel', ...
            '%s 的每个数据流必须是数值向量。', argumentName);
    end
    channels{index} = channels{index}(:);
end
end

function channels = normalizeIdealChannels(value, channelCount)
channels = normalizeSymbolChannels(value, 'idealSymbols');
if numel(channels) == 1 && channelCount > 1
    channels = repmat(channels, 1, channelCount);
elseif numel(channels) ~= channelCount
    error('TestProject:Plot:IdealChannelCountMismatch', ...
        '理想星座点必须为单个共享向量，或与接收数据流数量一致。');
end
end

function names = optionCellText(options, fieldName, count, prefix)
if isfield(options, fieldName) && ~isempty(options.(fieldName))
    value = options.(fieldName);
    if isstring(value)
        names = cellstr(value(:).');
    elseif iscell(value)
        names = cellfun(@(item) char(string(item)), value(:).', 'UniformOutput', false);
    else
        error('TestProject:Plot:InvalidChannelNames', ...
            '%s 必须是 string 或 cell 数组。', fieldName);
    end
    if numel(names) ~= count
        error('TestProject:Plot:ChannelNameCountMismatch', ...
            '%s 数量必须与数据流数量一致。', fieldName);
    end
else
    names = arrayfun(@(index) sprintf('%s %d', prefix, index), ...
        1:count, 'UniformOutput', false);
end
end

function textValue = optionText(options, fieldName, defaultValue)
if isfield(options, fieldName) && ~isempty(options.(fieldName))
    textValue = char(string(options.(fieldName)));
else
    textValue = defaultValue;
end
end

function axisLimits = resolveAxisLimits(options, ideal)
if isfield(options, 'AxisLimits') && ~isempty(options.AxisLimits)
    requested = double(options.AxisLimits(:).');
    if isscalar(requested) && isfinite(requested) && requested > 0
        axisLimits = [-requested requested -requested requested];
    elseif numel(requested) == 4 && all(isfinite(requested)) && ...
            requested(1) < requested(2) && requested(3) < requested(4)
        axisLimits = requested;
    else
        error('TestProject:Plot:InvalidAxisLimits', ...
            'AxisLimits 必须是正数，或 [xmin xmax ymin ymax]。');
    end
    return;
end

allIdeal = vertcat(ideal{:});
allIdeal = allIdeal(isfinite(real(allIdeal)) & isfinite(imag(allIdeal)));
if isempty(allIdeal)
    error('TestProject:Plot:NoIdealSymbols', '没有可用于确定坐标范围的理想星座点。');
end
extent = max([abs(real(allIdeal)); abs(imag(allIdeal))]);
if ~isfinite(extent) || extent <= 0
    extent = 1;
end
extent = 1.25 * extent;
axisLimits = [-extent extent -extent extent];
end

function metricList = normalizeMetrics(metrics, channelCount)
if isempty(metrics)
    metricList = repmat(struct(), 1, channelCount);
elseif ~isstruct(metrics)
    error('TestProject:Plot:InvalidMetrics', 'metrics 必须是 struct。');
elseif isscalar(metrics)
    metricList = repmat(metrics, 1, channelCount);
elseif numel(metrics) == channelCount
    metricList = reshape(metrics, 1, []);
else
    error('TestProject:Plot:MetricCountMismatch', ...
        'metrics 必须是标量，或与数据流数量一致。');
end
end

function lines = metricTitleLines(metric, validCount, outsideCount)
line1 = sprintf('N = %d', validCount);
if isfield(metric, 'BER') && isfiniteScalar(metric.BER)
    line1 = sprintf('%s    BER = %.3g', line1, metric.BER);
end
line2 = '';
evmValue = metricAlias(metric, {'EVM', 'EVMPercent'});
if isfiniteScalar(evmValue)
    line2 = sprintf('EVM = %.2f%%', evmValue);
end
merValue = metricAlias(metric, {'MER', 'MERdB'});
if isfiniteScalar(merValue)
    if isempty(line2)
        line2 = sprintf('MER = %.2f dB', merValue);
    else
        line2 = sprintf('%s    MER = %.2f dB', line2, merValue);
    end
end
lines = {line1};
if ~isempty(line2)
    lines{end + 1} = line2;
end
if outsideCount > 0
    lines{end + 1} = sprintf('超出显示范围 = %d', outsideCount);
end
end

function value = metricAlias(metric, names)
value = nan;
for index = 1:numel(names)
    if isfield(metric, names{index}) && isfiniteScalar(metric.(names{index}))
        value = metric.(names{index});
        return;
    end
end
end

function tf = isfiniteScalar(value)
tf = isnumeric(value) && isscalar(value) && isfinite(value);
end

function closeFigure(fig)
if isgraphics(fig, 'figure')
    close(fig);
end
end
