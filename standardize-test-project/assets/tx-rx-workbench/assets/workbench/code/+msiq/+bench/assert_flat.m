function assert_flat(run)
%ASSERT_FLAT Enforce the standard one-run flat-directory contract.

report = Result_Check_Flat_Directory(run);
if ~report.IsFlat
    error('msiq:run:NonFlatResult', ...
        'Run directory contains nested content.');
end
end
