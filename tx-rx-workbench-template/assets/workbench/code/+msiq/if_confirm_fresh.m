function evidence=if_confirm_fresh(f,writeCommand,readResponse,check,wait)
%IF_CONFIRM_FRESH Verified reset/pending/start/complete handshake, injectable I/O.
names={'reset_command','start_command','completion_query','pending_response','complete_response'};
assert(isequal(f.verified,true)&&all(isfinite([f.timeout_s f.poll_s]))&& ...
    f.timeout_s>0&&f.poll_s>0,'msiq:if:FreshGate','Verified finite acquisition timing required.');
for k=1:numel(names), assert(~isempty(f.(names{k})),'msiq:if:FreshGate','Missing acquisition field.'); end
assert(~strcmp(f.pending_response,f.complete_response),'msiq:if:FreshGate','Pending must differ from complete.');
check(); writeCommand(f.reset_command);
assert(strcmp(strtrim(readResponse(f.completion_query)),f.pending_response), ...
    'msiq:if:StaleCapture','Completion reset was not observed.');
check(); writeCommand(f.start_command); started=tic; polls=0;
while true
    check(); assert(toc(started)<f.timeout_s,'msiq:if:Timeout','New acquisition timed out.');
    response=strtrim(readResponse(f.completion_query)); polls=polls+1;
    assert(toc(started)<=f.timeout_s,'msiq:if:Timeout','Completion arrived after the acquisition deadline.');
    if strcmp(response,f.complete_response), break; end
    assert(strcmp(response,f.pending_response),'msiq:if:Completion','Unknown completion response.');
    wait(min(f.poll_s,max(0,f.timeout_s-toc(started))));
end
check(); evidence=struct('fresh_confirmed',true,'completion_response',response, ...
    'poll_count',polls,'wait_s',toc(started));
end
