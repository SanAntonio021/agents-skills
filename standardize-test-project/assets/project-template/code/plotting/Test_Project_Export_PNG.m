function outputPath = Test_Project_Export_PNG(fig, outputPath, style)
%TEST_PROJECT_EXPORT_PNG Export a white-background PNG at the shared resolution.

if nargin < 3 || isempty(style)
    style = Test_Project_Plot_Style();
end
if ~isgraphics(fig, 'figure')
    error('TestProject:Plot:InvalidFigure', 'fig 必须是有效的 MATLAB figure。');
end

outputPath = char(string(outputPath));
[outputDir, baseName, extension] = fileparts(outputPath);
if isempty(baseName)
    error('TestProject:Plot:MissingFileName', '输出路径必须包含文件名。');
end
if isempty(extension)
    outputPath = [outputPath '.png'];
elseif ~strcmpi(extension, '.png')
    error('TestProject:Plot:PNGRequired', '自动测试图只输出 PNG 文件。');
end
if ~isempty(outputDir) && ~isfolder(outputDir)
    [ok, message] = mkdir(outputDir);
    if ~ok
        error('TestProject:Plot:CreateDirectoryFailed', ...
            '无法创建图片目录 %s：%s', outputDir, message);
    end
end
if isfile(outputPath)
    error('TestProject:Plot:OutputExists', ...
        '输出图片已存在，不会覆盖：%s', outputPath);
end

set(fig, 'Color', style.FigureColor, 'InvertHardcopy', 'off');
drawnow();
exportgraphics(fig, outputPath, ...
    'Resolution', style.ResolutionDPI, ...
    'BackgroundColor', style.FigureColor);
end
