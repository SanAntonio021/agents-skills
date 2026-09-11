function output = RX_Workbench(varargin)
%RX_WORKBENCH Receive-side workbench and compatibility dispatcher.
%
% RX_Workbench() opens the interactive scope workbench.
% RX_Workbench('__traditional_16qam__', action, selector, options) keeps
% the programmatic Traditional RX entry used by the existing runners.

root = fileparts(mfilename('fullpath'));
addpath(fullfile(root, 'code'));
addpath(fullfile(root, 'code', 'result_management'));

if nargin == 0
    output = msiq.rx_workbench_app();
    return;
end
if nargin == 2 && (ischar(varargin{1}) || isstring(varargin{1})) ...
        && strcmpi(varargin{1},'replot')
    output = msiq.replot_run(varargin{2});
    return;
end

if ~ischar(varargin{1}) && ~(isstring(varargin{1}) && isscalar(varargin{1})) || ...
        ~strcmp(char(string(varargin{1})), '__traditional_16qam__')
    error('RX_Workbench:ProgrammaticAction', ...
        'The programmatic RX entry is reserved for TX_Workbench.');
end
if nargin < 4
    error('RX_Workbench:ProgrammaticAction', ...
        'Traditional RX dispatch needs action, selector, and options.');
end
output = msiq.traditional_rx(varargin{2}, varargin{3}, varargin{4});
end
