function report = validate_if_board()
%VALIDATE_IF_BOARD No-hardware board protocol and state transition checks.
details={};
enc=@msiq.instruments.if_board_encode;
assert(isequal(enc('rf',[0 .5 1 2 30 31.5]),uint8([170 187 1 0 1 2 4 60 63 204])));
mustFail(@()enc('i',[nan 1 1 1 1 1]),'msiq:ifboard:values');
mustFail(@()enc('q',[.1 1 1 1 1 1]),'msiq:ifboard:values');
mustFail(@()enc('rf',[32 1 1 1 1 1]),'msiq:ifboard:values');
mustFail(@()enc('agc',[2 0 0 0 0 0]),'msiq:ifboard:values');
details{end+1}='Pure six-band codec rejects unknown, fractional and excessive values.';
rx=msiq.instruments.if_board_decode(uint8([170 187 9 1 2 3 0 0 0 204]));
assert(isequal(rx.values,logical([1 0 1 0 0 0])) && ~rx.attenuation_readback);
rx=msiq.instruments.if_board_decode(uint8([170 187 3 250 0 0 0 0 0 204]));
assert(strcmp(rx.kind,'i_power_raw') && isempty(rx.values));
mustFail(@()msiq.instruments.if_board_decode(enc('i',ones(1,6))),'msiq:ifboard:receiveType');
details{end+1}='Receive parser accepts evidenced status/power only, never attenuation ACK.';
c=configuration(); b=msiq.instruments.IfBoard(c); cleanup=onCleanup(@()b.close());
assert(~b.IsOpen && isempty(b.History) && all(isnan(b.State.i)));
b.open(); mustFail(@()b.setIQ(1,10,10),'msiq:ifboard:unknown');
b.confirmState(state(),'fixture manually confirmed');
mustFail(@()b.assertAutomaticReady(),'msiq:ifboard:autoGate');
b.setIQ(1,9,11); assert(isequal({b.History.kind},{'q','i'}));
assert(all(b.State.i(2:6)==10) && all(b.State.q(2:6)==10));
assert(all(isnan(b.Readback.i)) && b.Sent.i(1)==9);
b.setIQ(1,10,12); assert(isequal({b.History(3:4).kind},{'i','q'}));
n=numel(b.History); mustFail(@()b.setIQ(1,8,21),'msiq:ifboard:limits'); assert(numel(b.History)==n);
details{end+1}='Explicit session, manual state, five-band preservation and increase-first I/Q ordering.';
c.fail_on_write=2; f=msiq.instruments.IfBoard(c); f.open(); f.confirmState(state(),'fixture');
mustFail(@()f.setIQ(1,11,12),'msiq:ifboard:injected');
assert(~f.StateKnown && numel(f.History)==2 && strcmp(f.History(2).outcome,'unknown_after_failure'));
mustFail(@()f.setIQ(1,11,12),'msiq:ifboard:unknown'); assert(numel(f.History)==2); f.close();
b.cancel(); mustFail(@()b.setAttenuation('rf',1,11),'msiq:ifboard:closed');
details{end+1}='Partial write and cancellation prevent silent retry.';
c=configuration(); c.mode='live'; live=msiq.instruments.IfBoard(c);
mustFail(@()live.open(),'msiq:ifboard:protocolGate'); assert(~live.IsOpen);
c.runtime.protocol_verified=true; live=msiq.instruments.IfBoard(c);
mustFail(@()live.open(),'msiq:ifboard:serialGate'); assert(~live.IsOpen);
c=configuration(); c.runtime=struct('protocol_verified',true,'mapping_verified',true,'response_verified',true);
b2=msiq.instruments.IfBoard(c); b2.open(); b2.confirmState(state(),'fixture'); b2.assertAutomaticReady(); b2.close();
details{end+1}='Live preflight fails before serial constructor; automatic verification gates tested in mock.';
report=struct('ok',true,'details',{details});
end
function c=configuration()
lim=repmat([0 20],6,1);
c=struct('mode','mock','limits',struct('rf',lim,'i',lim,'q',lim));
end
function s=state()
s=struct('rf',10*ones(1,6),'i',10*ones(1,6),'q',10*ones(1,6),'agc',zeros(1,6));
end
function mustFail(f,id)
try
    f();
catch err
    assert(strcmp(err.identifier,id),'Unexpected error: %s instead of %s',err.identifier,id); return;
end
error('msiq:ifboard:test','Expected error %s.',id);
end
