function output = TX_Workbench(action, selector, varargin)
%TX_WORKBENCH Entry point for the WZ traditional IQ transmit path.
%
% TX_Workbench()                 open the graphical TX workbench
% TX_Workbench('generate')       generate CH1 I/Q waveform
% TX_Workbench('dry_run')        plan CH1 without I/O
% TX_Workbench('awg_plan',[],opts) create a manual TX plan
% TX_Workbench('awg_apply',[],opts) apply a confirmed TX plan
% opts.tx_sro_precomp: enabled, measured_sro_ppm, calibrated_at,
% calibration_source. Waveform-only calibration; the AWG raster is unchanged.
% TX_Workbench('rdiv_compare_plan',[],opts) plan DIV2/DIV4 comparison
% TX_Workbench('rdiv_compare_apply',[],opts) run confirmed comparison
% TX_Workbench('scope_status')   read LeCroy C1/C2 status
% TX_Workbench('capture',[],opts) capture a confirmed TX run
% TX_Workbench('demod_capture',run_dir) offline demodulation
% TX_Workbench('hardware')       gated formal acquisition
% TX_Workbench('replay',run_dir) offline replay

if nargin < 1 || isempty(action)
    action = 'gui';
end
if nargin < 2
    selector = [];
end
root = fileparts(mfilename('fullpath'));
addpath(fullfile(root, 'code'));
addpath(fullfile(root, 'code', 'result_management'));
action = lower(char(string(action)));
tx_actions = {'awg_status','awg_plan','awg_apply','awg_level', ...
    'awg_channel_settings','awg_reuse','awg_stop','preview_plan'};
rx_actions = {'scope_status','capture','demod_capture'};
comparison_actions = {'rdiv_compare_plan','rdiv_compare_apply'};
if ismember(action, tx_actions)
    options = first_options(varargin);
    output = msiq.traditional_tx(action, selector, options);
    return;
end
if strcmp(action, 'gui')
    output = msiq.tx_workbench_app(first_options(varargin));
    return;
end
if ismember(action, rx_actions)
    options = first_options(varargin);
    output = RX_Workbench('__traditional_16qam__', action, selector, options);
    return;
end
if ismember(action, comparison_actions)
    root = fileparts(mfilename('fullpath'));
    addpath(fullfile(root, 'code'));
    addpath(fullfile(root, 'code', 'result_management'));
    options = first_options(varargin);
    output = msiq.traditional_rdiv_compare(action, selector, options);
    return;
end
if strcmp(action, 'iq_loopback')
    error('TX_Workbench:LoopbackDeprecated', ...
        ['iq_loopback was replaced by awg_plan/awg_apply so it cannot ', ...
        'force all outputs off or open the scope during TX download.']);
end
profile = 'v2_traditional_wz';
if strcmp(action, 'simulation')
    output = Multistream_Workbench( ...
        'traditional_simulation', profile, selector, varargin{:});
else
    output = Multistream_Workbench( ...
        action, profile, selector, varargin{:});
end

function options = first_options(values)
options = struct();
if isempty(values)
    return;
end
if ~isstruct(values{1}) || ~isscalar(values{1})
    error('TX_Workbench:Options', ...
        'Traditional hardware actions require one scalar options struct.');
end
options = values{1};
end
end
