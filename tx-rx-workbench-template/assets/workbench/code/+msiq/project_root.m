function root = project_root()
%PROJECT_ROOT Return the isolated V2 project root.

root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
end
