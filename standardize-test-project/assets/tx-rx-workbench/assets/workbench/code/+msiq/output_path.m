function path = output_path(run, name)
%OUTPUT_PATH Keep figures visible and put machine-readable artifacts in data.
name = char(string(name));
[~, ~, extension] = fileparts(name);
if strcmp(name, 'summary.csv') || ismember(lower(extension), ...
        {'.png', '.jpg', '.jpeg', '.svg', '.pdf', '.tif', '.tiff'})
    path = fullfile(run.OutputDir, name);
else
    path = fullfile(run.DataDir, name);
end
end
