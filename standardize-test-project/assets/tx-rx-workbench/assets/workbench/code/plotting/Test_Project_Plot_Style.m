function style = Test_Project_Plot_Style()
%TEST_PROJECT_PLOT_STYLE Return the shared style for automatic test figures.

style = struct();
style.ResolutionDPI = 300;
style.FontName = 'Microsoft YaHei';
style.FontSize = 10;
style.AxisLabelFontSize = 11;
style.TitleFontSize = 12;
style.LineWidth = 1.35;
style.AxisLineWidth = 0.85;
style.GridAlpha = 0.18;
style.MinorGridAlpha = 0.08;
style.RawMarkerArea = 20;
style.MeanMarkerSize = 5.5;
style.ConstellationMarkerSize = 5;
style.IdealMarkerSize = 7;
style.FigureColor = [1 1 1];
style.RawPointColor = [0.18 0.18 0.18];
style.Colors = [
    0.0000 0.4470 0.7410
    0.8500 0.3250 0.0980
    0.4660 0.6740 0.1880
    0.4940 0.1840 0.5560
    0.3010 0.7450 0.9330
    0.6350 0.0780 0.1840];
style.LineStyles = {'-', '--', '-.', ':'};
style.SinglePanelSizeInches = [6.8 4.4];
style.MultiConstellationSizeInches = [7.1 4.2];
style.SingleConstellationSizeInches = [4.4 4.4];
end
