function save_replot_figure(fig, output_path, resolution)
%SAVE_REPLOT_FIGURE Preserve the native inputs of an owned live dashboard.
if nargin < 3, resolution = 180; end
[directory,name] = fileparts(output_path);
data_dir = fullfile(directory,'data');
if ~isfolder(data_dir), return; end
setappdata(fig,'msiq_export',struct('method','print','resolution',resolution));
setappdata(fig,'TestProjectOriginalGeometry',struct('Units',fig.Units, ...
    'Position',fig.Position,'PaperUnits',fig.PaperUnits, ...
    'PaperPosition',fig.PaperPosition,'PaperPositionMode',fig.PaperPositionMode));
savefig(fig,fullfile(data_dir,[name '.fig']),'compact');
end
