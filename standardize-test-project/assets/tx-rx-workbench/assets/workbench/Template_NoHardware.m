function guard = Template_NoHardware()
%TEMPLATE_NOHARDWARE Protect only this MATLAB scope; restore the prior path.
root=fileparts(mfilename('fullpath'));
previous=path;
addpath(root,fullfile(root,'code'),fullfile(root,'code','result_management'), ...
    fullfile(root,'code','plotting'));
addpath(fullfile(root,'template_support','no_hardware'),'-begin');
setappdata(0,'TemplateHardwareAttempts',0);
guard=onCleanup(@() path(previous));
end
