function guard = Template_NoHardware()
%TEMPLATE_NOHARDWARE Protect this MATLAB process and retain nested attempt counts.
% New worker processes must separately use explicit simulation factories.
root=fileparts(mfilename('fullpath'));
previous=path; previous_marker=getenv('MSIQ_TEMPLATE_NO_HARDWARE_ROOT');
setenv('MSIQ_TEMPLATE_NO_HARDWARE_ROOT',root);
addpath(root,fullfile(root,'code'),fullfile(root,'code','result_management'), ...
    fullfile(root,'code','plotting'));
addpath(fullfile(root,'template_support','no_hardware'),'-begin');
if ~isappdata(0,'TemplateHardwareAttempts'), setappdata(0,'TemplateHardwareAttempts',0); end
guard=onCleanup(@() restore(previous,previous_marker,root));
end

function restore(previous,marker,root)
path(previous);
% Native GUI callbacks / .NET worker handle destructors can outlive the caller.
% Retain this copied project's code until MATLAB releases those handles; only
% the constructor-shadow guard is scope-local. No external project is added.
addpath(root,fullfile(root,'code'),fullfile(root,'code','result_management'),fullfile(root,'code','plotting'));
setenv('MSIQ_TEMPLATE_NO_HARDWARE_ROOT',marker);
end
