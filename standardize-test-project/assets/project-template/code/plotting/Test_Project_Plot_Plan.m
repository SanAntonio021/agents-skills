function details = Test_Project_Plot_Plan(outputPath, plannedValues, options)
%TEST_PROJECT_PLOT_PLAN Plot dry-run plan points without fake measurements.

if nargin < 3 || isempty(options)
    options = struct();
end
if ~isnumeric(plannedValues) || ~isvector(plannedValues) || ...
        isempty(plannedValues)
    error('TestProject:Plot:InvalidPlanValues', ...
        'plannedValues 必须是非空数值向量。');
end
plannedValues = plannedValues(:);
plannedValues = plannedValues(isfinite(plannedValues));
if isempty(plannedValues)
    error('TestProject:Plot:NoValidPlanValues', ...
        'plannedValues 没有有效数值。');
end

style = Test_Project_Plot_Style();
titleText = optionText(options, 'Title', 'dry-run 计划检查');
xName = optionText(options, 'XName', '计划变量');
xUnit = optionText(options, 'XUnit', '-');
plannedCount = optionNumber(options, 'PlannedCount', numel(plannedValues));
stages = optionTextList(options, 'Stages', {'计划检查', '路径检查', '保存检查'});

fig = figure('Visible', 'off', 'Units', 'inches', ...
    'Position', [1 1 6.30 3.94], 'Color', style.FigureColor);
figureCleanup = onCleanup(@() closeFigure(fig));
ax = axes(fig);
scatter(ax, plannedValues, ones(size(plannedValues)), ...
    style.RawMarkerArea, style.Colors(1, :), 'filled', ...
    'Marker', 'o', 'DisplayName', '计划点');
xlabel(ax, quantityLabel(xName, xUnit), ...
    'FontSize', style.AxisLabelFontSize);
yticks(ax, []);
ylim(ax, [0.7 1.3]);
title(ax, {titleText, sprintf('计划观测数：%d', plannedCount)}, ...
    'FontSize', style.TitleFontSize, 'FontWeight', 'normal');
legend(ax, 'Location', 'best', 'Box', 'off', ...
    'FontName', style.FontName, 'FontSize', style.FontSize - 1);
Test_Project_Apply_Axes_Style(ax, style);
ax.YGrid = 'off';
text(ax, 0.01, 0.04, ['阶段：', strjoin(stages, '、')], ...
    'Units', 'normalized', 'VerticalAlignment', 'bottom', ...
    'HorizontalAlignment', 'left', 'FontName', style.FontName, ...
    'FontSize', style.FontSize - 1, 'Interpreter', 'none');
setPlanXLimits(ax, plannedValues);

outputPath = Test_Project_Export_PNG(fig, outputPath, style);
details = struct('OutputPath', outputPath, ...
    'PlannedPointCount', numel(plannedValues), ...
    'PlannedCount', plannedCount, ...
    'Stages', {stages}, 'ResolutionDPI', style.ResolutionDPI);

end

function textValue = optionText(options, name, defaultValue)
if isfield(options, name) && ~isempty(options.(name))
    textValue = char(string(options.(name)));
else
    textValue = defaultValue;
end
end

function value = optionNumber(options, name, defaultValue)
if isfield(options, name) && ~isempty(options.(name))
    value = options.(name);
else
    value = defaultValue;
end
validateattributes(value, {'numeric'}, ...
    {'real', 'finite', 'scalar', 'integer', 'nonnegative'});
end

function values = optionTextList(options, name, defaultValue)
if isfield(options, name) && ~isempty(options.(name))
    value = options.(name);
else
    value = defaultValue;
end
if ischar(value) || (isstring(value) && isscalar(value))
    values = {char(value)};
elseif isstring(value)
    values = cellstr(value(:).');
elseif iscell(value)
    values = cellfun(@char, value(:).', 'UniformOutput', false);
else
    error('TestProject:Plot:InvalidStages', ...
        'Stages 必须是文本或文本列表。');
end
end

function labelText = quantityLabel(name, unit)
if isempty(unit) || strcmp(unit, '-')
    labelText = name;
else
    labelText = sprintf('%s (%s)', name, unit);
end
end

function setPlanXLimits(ax, values)
minimum = min(values);
maximum = max(values);
if minimum == maximum
    margin = max(abs(minimum) * 0.05, 0.5);
else
    margin = 0.03 * (maximum - minimum);
end
xlim(ax, [minimum - margin, maximum + margin]);
end

function closeFigure(fig)
if isgraphics(fig)
    close(fig);
end
end
