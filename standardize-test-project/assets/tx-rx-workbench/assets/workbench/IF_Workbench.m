function output = IF_Workbench(action, options)
%IF_WORKBENCH Compatibility entry for explicit IF backend actions.
% IF_Workbench() / 'gui' prints migration guidance without opening a window.
% Other actions delegate to msiq.if_workbench with options.profile.
if nargin < 1 || isempty(action), action = 'gui'; end
if nargin < 2 || isempty(options), options = struct(); end
if ~isstruct(options) || ~isscalar(options)
    error('msiq:if:Options','options must be a scalar struct.');
end
root = fileparts(mfilename('fullpath'));
addpath(fullfile(root,'code'));
addpath(fullfile(root,'code','result_management'));
action = lower(char(string(action)));
if strcmp(action,'gui')
    message = ['中频日常操作已迁入 TX_Workbench 和 RX_Workbench。', newline, ...
        '发射中频衰减请使用 TX；接收中频、采集和自动配平请使用 RX。', newline, ...
        '二维扫描、模式比较及历史回放仍可通过 IF_Workbench 的显式动作调用。', newline, ...
        '本次仅显示说明，未打开工作台或连接仪器。'];
    fprintf('%s\n', message);
    output = struct('status','migrated','message',message, ...
        'tx_entry','TX_Workbench','rx_entry','RX_Workbench','hardware_accessed',false);
else
    output = msiq.if_workbench(action, options);
end
end
