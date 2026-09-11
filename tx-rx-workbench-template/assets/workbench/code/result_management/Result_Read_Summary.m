function rows = Result_Read_Summary(run_or_dir)
%RESULT_READ_SUMMARY Read unrounded observations; first rows are names/units.
path = Result_Artifact_Path(run_or_dir, 'observations.csv');
if ~isfile(path)
    if isstruct(run_or_dir), root = run_or_dir.OutputDir; else, root = char(run_or_dir); end
    path = fullfile(root, 'summary.csv');
end
rows = readcell(path, 'Encoding', 'UTF-8', 'Delimiter', ',');
end
