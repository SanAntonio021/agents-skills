function out = if_workbench(action, options)
%IF_WORKBENCH Offline-first IF controller. No session is opened by config/plan.
persistent active cancelled
if isempty(active), active = false; cancelled = false; end
if nargin < 1, action = 'config'; end
if nargin < 2, options = struct(); end
switch lower(char(action))
    case 'stop'
        cancelled = true; out = struct('status','stop_requested'); return;
    case 'cancelled'
        out = cancelled; return;
    case 'config'
        out = msiq.if_workbench_config(field(options,'profile',struct())); return;
    case 'plan'
        p = msiq.if_workbench_config(field(options,'profile',struct()));
        out = msiq.if_workbench_plan(p); return;
    case 'replay'
        out=msiq.if_workbench_replay(options); return;
end
if active, error('msiq:if:Busy','An IF operation is already running.'); end
active = true; cancelled = false;
guard = onCleanup(@release);
p = msiq.if_workbench_config(field(options,'profile',struct()));
if strcmpi(action,'mock')&&(~strcmp(p.mode,'mock')|| ...
        (isfield(p.board,'mode')&&strcmp(p.board.mode,'live')))
    % An explicit mock action can never reach a live transport, even when the
    % caller supplies a live profile and a hardware confirmation by mistake.
    p=msiq.if_workbench_config(struct('mode','mock','stage',p.stage,'scan',p.scan));
    options.hardware_confirmed=false;
end
if ismember(lower(char(action)),{'tx_plan','tx_prepare','tx_apply','tx_level','awg_stop'})
    options.profile=p;
    out=msiq.if_awg_action(lower(char(action)),options); return;
end
runner = msiq.IfRun(p, options);
out = runner.execute(lower(char(action)));
clear guard
    function release()
        active = false;
    end
end
function value = field(s,n,d)
if isfield(s,n), value=s.(n); else, value=d; end
end
