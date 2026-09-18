function details = Test_Project_Plot_Spectrum(outputPath, frequency, spectra, options)
%TEST_PROJECT_PLOT_SPECTRUM Plot one or more spectrum traces in one PNG.
% frequency and spectra must already use the display units named in options.

if nargin < 4 || isempty(options)
    options = struct();
end

style = Test_Project_Plot_Style();
frequency = validateVector(frequency, 'frequency');
traces = normalizeTraces(spectra, numel(frequency));
traceCount = numel(traces);
traceNames = optionCellText(options, 'TraceNames', traceCount, '曲线');
figureTitle = optionText(options, 'Title', '频谱图');
xLabel = quantityLabel(optionText(options, 'XName', '横轴变量'), ...
    optionText(options, 'XUnit', '-'));
yLabel = quantityLabel(optionText(options, 'YName', '纵轴变量'), ...
    optionText(options, 'YUnit', '-'));

figureSize = style.SinglePanelSizeInches;
fig = figure('Visible', 'off', 'Units', 'inches', ...
    'Position', [1 1 figureSize], 'Color', style.FigureColor);
figureCleanup = onCleanup(@() closeFigure(fig));
ax = axes(fig);
hold(ax, 'on');

pointCounts = zeros(1, traceCount);
for traceIndex = 1:traceCount
    values = traces{traceIndex};
    valid = isfinite(frequency) & isfinite(values);
    if ~any(valid)
        error('TestProject:Plot:NoValidSpectrumData', ...
            '频谱曲线 %d 没有有效数据。', traceIndex);
    end
    pointCounts(traceIndex) = nnz(valid);
    color = style.Colors(mod(traceIndex - 1, size(style.Colors, 1)) + 1, :);
    lineStyle = style.LineStyles{mod(traceIndex - 1, numel(style.LineStyles)) + 1};
    plot(ax, frequency(valid), values(valid), ...
        'Color', color, ...
        'LineStyle', lineStyle, ...
        'LineWidth', style.LineWidth, ...
        'DisplayName', traceNames{traceIndex});
end

xlabel(ax, xLabel, 'FontSize', style.AxisLabelFontSize);
ylabel(ax, yLabel, 'FontSize', style.AxisLabelFontSize);
title(ax, figureTitle, ...
    'FontName', style.FontName, ...
    'FontSize', style.TitleFontSize + 1, ...
    'FontWeight', 'normal', ...
    'Interpreter', 'none');
Test_Project_Apply_Axes_Style(ax, style);
if traceCount > 1
    legend(ax, 'Location', 'best', 'Box', 'off', ...
        'FontName', style.FontName, 'FontSize', style.FontSize - 1);
end
axis(ax, 'tight');
outputPath = Test_Project_Export_PNG(fig, outputPath, style);

details = struct();
details.OutputPath = outputPath;
details.TraceCount = traceCount;
details.ValidPointCount = pointCounts;
details.ResolutionDPI = style.ResolutionDPI;
end

function vector = validateVector(value, name)
if ~isnumeric(value) || ~isvector(value) || isempty(value)
    error('TestProject:Plot:InvalidVector', '%s 必须是非空数值向量。', name);
end
vector = value(:);
end

function traces = normalizeTraces(value, pointCount)
if iscell(value)
    traces = value(:).';
elseif isnumeric(value)
    if isvector(value)
        traces = {value(:)};
    elseif size(value, 1) == pointCount
        traces = mat2cell(value, pointCount, ones(1, size(value, 2)));
    elseif size(value, 2) == pointCount
        value = value.';
        traces = mat2cell(value, pointCount, ones(1, size(value, 2)));
    else
        error('TestProject:Plot:SpectrumSizeMismatch', ...
            'spectra 的行数或列数必须与 frequency 长度一致。');
    end
else
    error('TestProject:Plot:InvalidSpectra', ...
        'spectra 必须是数值数组或 cell 数组。');
end
if isempty(traces)
    error('TestProject:Plot:EmptySpectra', 'spectra 不能为空。');
end
for index = 1:numel(traces)
    if ~isnumeric(traces{index}) || ~isvector(traces{index}) || ...
            numel(traces{index}) ~= pointCount
        error('TestProject:Plot:SpectrumSizeMismatch', ...
            '每条频谱曲线必须是与 frequency 等长的数值向量。');
    end
    traces{index} = traces{index}(:);
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
        error('TestProject:Plot:InvalidTraceNames', ...
            '%s 必须是 string 或 cell 数组。', fieldName);
    end
    if numel(names) ~= count
        error('TestProject:Plot:TraceNameCountMismatch', ...
            '%s 数量必须与频谱曲线数量一致。', fieldName);
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
