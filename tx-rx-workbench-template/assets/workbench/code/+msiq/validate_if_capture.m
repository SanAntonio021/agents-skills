function report=validate_if_capture()
%VALIDATE_IF_CAPTURE Numeric capture validation only; no sessions or I/O.
p=msiq.if_workbench_config(); p.mode='live';
cfg=msiq.build_config('v2_traditional_wz');
n=1000; fs=p.scope.sample_rate_hz; p.scope.window_s=n/fs;
t=(0:n-1)'/fs; codes=round(70*sin(2*pi*(0:n-1)'/20));
d=struct('vertical_gain',.001,'vertical_offset',.02,'comm_type',0);
r=struct('channel','C3','samples',codes*.001-.02,'time_axis_s',t, ...
    'sample_rate_hz',fs,'descriptor',d);
q=r; q.channel='C4'; q.time_axis_s=t+.1/fs;
raw=struct('channels',[r q],'fresh_confirmed',true);
[v,~]=msiq.if_capture_observation(raw,p,cfg,[.1 .1]);
assert(~v.clipped && all(abs(v.windows_s-p.scope.window_s)<1e-15));
bad=raw; bad.channels(1).samples(:)=127*.001-.02;
v=msiq.if_capture_observation(bad,p,cfg,[.1 .1]);
assert(v.clipped && v.clip_fraction(1)==1); % DC rail must not disappear after mean removal.
bad=raw; bad.fresh_confirmed=false;
reject(@()msiq.if_capture_observation(bad,p,cfg,[.1 .1]),'msiq:if:StaleCapture');
bad=raw; bad.channels(1).time_axis_s(8)=NaN;
reject(@()msiq.if_capture_observation(bad,p,cfg,[.1 .1]),'msiq:if:Waveform');
bad=raw; bad.channels(1).sample_rate_hz=fs/2;
reject(@()msiq.if_capture_observation(bad,p,cfg,[.1 .1]),'msiq:if:SampleRate');
p.scope.window_s=2*n/fs;
reject(@()msiq.if_capture_observation(raw,p,cfg,[.1 .1]),'msiq:if:Window');
report=struct('ok',true,'details','axes, actual rate/window, fresh flag, DC rail clipping; no I/O');
end
function reject(f,id)
try, f(); catch ex, assert(strcmp(ex.identifier,id)); return; end
error('msiq:if:ValidationExpectedFailure','Expected %s.',id);
end
