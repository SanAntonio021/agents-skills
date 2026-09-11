function report=validate_if_fresh()
f=struct('verified',true,'reset_command','RESET','start_command','START', ...
    'completion_query','DONE?','pending_response','0','complete_response','1','timeout_s',.1,'poll_s',.001);
commands={}; responses={'0','0','1'}; calls=0;
v=msiq.if_confirm_fresh(f,@write,@read,@check,@pause);
assert(v.fresh_confirmed&&v.poll_count==2&&isequal(commands,{'RESET','START'}));
commands={}; responses={'1'}; calls=0;
expect(@()msiq.if_confirm_fresh(f,@write,@read,@check,@pause),'msiq:if:StaleCapture');
assert(isequal(commands,{'RESET'}));
commands={}; responses={'0','bad'}; calls=0;
expect(@()msiq.if_confirm_fresh(f,@write,@read,@check,@pause),'msiq:if:Completion');
commands={}; responses={'0'}; calls=0; f.timeout_s=.005;
expect(@()msiq.if_confirm_fresh(f,@write,@read,@check,@pause),'msiq:if:Timeout');
f.verified=false;
expect(@()msiq.if_confirm_fresh(f,@write,@read,@check,@pause),'msiq:if:FreshGate');
report=struct('ok',true,'checks',{{'pending_before_start','new_completion','stale','unknown','bounded_timeout','verification_gate'}});
    function write(command), commands{end+1}=command; end
    function response=read(~), calls=calls+1; response=responses{min(calls,numel(responses))}; end
    function check(), end
end
function expect(fn,id)
try, fn(); catch ex, assert(strcmp(ex.identifier,id),ex.message); return; end
error('msiq:if:Validation','Expected %s.',id);
end
