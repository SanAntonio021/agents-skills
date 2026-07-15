function report = Result_Check_Flat_Directory(run_or_path)
%RESULT_CHECK_FLAT_DIRECTORY Report files and forbidden subdirectories.

if isstruct(run_or_path) && isfield(run_or_path, 'OutputDir')
    output_dir = run_or_path.OutputDir;
elseif ischar(run_or_path) || (isstring(run_or_path) && isscalar(run_or_path))
    output_dir = char(run_or_path);
else
    error('Result_Check_Flat_Directory:BadTarget', ...
        'Target must be a run struct or run directory.');
end
if ~isfolder(output_dir)
    error('Result_Check_Flat_Directory:MissingDirectory', ...
        'Run directory does not exist: %s', output_dir);
end

listing = dir(output_dir);
is_special = ismember({listing.name}, {'.', '..'});
listing = listing(~is_special);
report = struct();
report.OutputDir = output_dir;
report.Files = {listing(~[listing.isdir]).name};
report.Subdirectories = {listing([listing.isdir]).name};
report.IsFlat = isempty(report.Subdirectories);

end
