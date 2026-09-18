function report = validate_rx_scope_settings(output_dir)
%VALIDATE_RX_SCOPE_SETTINGS Instrument-free settings and isolation acceptance.
if nargin<1, output_dir=tempname; end
if ~isfolder(output_dir), mkdir(output_dir); end
opts=struct('log_path',fullfile(output_dir,'settings_io.log'), ...
    'failure_path',fullfile(output_dir,'settings_failure.flag'), ...
    'capture_delay_s',0,'record_count',1024);
io=msiq.instruments.mock_rx_scope_io(opts); session=io.open([]);
s=msiq.instruments.rx_scope_settings(session,io.query);
assert(numel(s.fields)==36 && all([s.fields.available]));
assert(strcmp(s.sample_mode,'REALTIME'));
assert(strcmp(field(s,'C1:BWL').value,'OFF'));
assert(isequal(field(s,'C1:CPL').choices,{'D50','GND'}));
assert(field(s,'MSIZ').minimum==500 && field(s,'MSIZ').maximum==32e6);
assert(~field(s,'HTIME').writable && field(s,'HTIME').value==1e-9);
assert_fails(@() apply('HTIME',2e-9),'RX_Workbench:Setting');
before=fileread(opts.log_path);
apply('C3:AVERAGE',4.6); assert(read('C3:AVERAGE')==5);
apply('C4:INTERPOLATION','SINXX'); assert(strcmp(read('C4:INTERPOLATION'),'SINXX'));
apply('C3:CPL','GND'); apply('C2:BWL','200MHZ'); apply('C1:TRA','OFF');
apply('TRSOURCE','C4'); apply('TRLEVEL',.18);
apply('HTYPE','TI'); apply('HTIME',1.3e-9);
assert(abs(read('HTIME')-1.3e-9)<eps);
assert(strcmp(read('TRSOURCE'),'C4'));
apply('MSIZ',1234567); assert(read('MSIZ')==1234567);
after=fileread(opts.log_path); added=after(numel(before)+1:end);
writes=regexp(added,'(?m)^WRITE ([^\r\n]+)','tokens');
assert(numel(writes)==10);
assert(~contains(added,'WRITE STOP') && ~contains(added,'WRITE TRMD AUTO'));
before=fileread(opts.log_path);
assert_fails(@() apply('C1:AVERAGE',Inf));
assert_fails(@() apply('C1:CPL','A1M'));
assert_fails(@() apply('SAMPLEMODE','RIS'));
assert_fails(@() apply('TRLEVEL',.5));
assert_fails(@() apply('C5:TRA','ON'));
after=fileread(opts.log_path);
assert(~contains(after(numel(before)+1:end),'WRITE '));
bad=opts; bad.unsupported_setting='EnhanceResType';
other=msiq.instruments.mock_rx_scope_io(bad);
unsupported=msiq.instruments.rx_scope_settings(session,other.query);
assert(sum(~[unsupported.fields.available])==4);
frozen=opts; frozen.no_new_frame=true; frozen.sample_mode='SEQUENCE';
other=msiq.instruments.mock_rx_scope_io(frozen);
a=other.capture(session,{'C1','C2'}); b=other.capture(session,{'C1','C2'});
assert(isequal(a.channels(1).descriptor.trigger_time_bytes,b.channels(1).descriptor.trigger_time_bytes));
mode=msiq.instruments.rx_scope_settings(session,other.query);
assert(strcmp(mode.sample_mode,'SEQUENCE') && isequal(field(mode,'SAMPLEMODE').choices,{'REALTIME'}));
assert(~field(mode,'SAMPLEMODE').writable && contains(field(mode,'SAMPLEMODE').error,'SEQUENCE'));
assert_fails(@() msiq.instruments.apply_rx_scope_setting(session, ...
    struct('key','SAMPLEMODE','value','REALTIME'),other.query,other.write),'RX_Workbench:Setting');
% A failed capability query is local; the successfully read value survives.
local=msiq.instruments.rx_scope_settings(session,@capability_failure);
assert(field(local,'C2:BWL').available && ~field(local,'C2:BWL').writable);
assert(strcmp(field(local,'C2:BWL').value,'200MHZ'));
assert(field(local,'C1:BWL').writable && field(local,'MSIZ').writable);
retried=msiq.instruments.rx_scope_settings(session,io.query,local,false);
assert(field(retried,'C2:BWL').writable);
unknown=msiq.instruments.rx_scope_settings(session,@unknown_bandwidth);
assert(strcmp(field(unknown,'C2:BWL').value,'30GHZ') && ~field(unknown,'C2:BWL').writable);
% HTIME dependency is re-read even when applying only that one field.
apply('HTYPE','OFF'); old_time=read('HTIME');
assert_fails(@() apply('HTIME',3e-9),'RX_Workbench:Setting');
assert(read('HTIME')==old_time);
edge=msiq.instruments.rx_scope_settings(session,@non_edge);
assert(~field(edge,'HTIME').writable && ~field(edge,'HTYPE').writable);
assert_fails(@() msiq.instruments.apply_rx_scope_setting(session, ...
    struct('key','HTIME','value',3e-9),@non_edge,io.write),'RX_Workbench:Setting');
% Legacy center/width and the new endpoints select the exact same PSD bins.
frequency=(0:10000)'*1e6; psd=1+sin(frequency/1e9).^2;
for pair=[0 2e9; 1e9 4e9; 4e9 2e9]'
    c=pair(1); w=pair(2); [lo,hi]=msiq.rx_observation_band('from_legacy',c,w);
    [c2,w2]=msiq.rx_observation_band('to_legacy',lo,hi);
    old=frequency>=max(0,c-w/2)&frequency<=c+w/2;
    new=frequency>=max(0,c2-w2/2)&frequency<=c2+w2/2;
    assert(isequal(old,new) && trapz(frequency(old),psd(old))==trapz(frequency(new),psd(new)));
end
assert_fails(@() msiq.rx_observation_band('to_legacy',3,2));
transport_queries=0;
assert_fails(@() msiq.instruments.rx_scope_settings(session,@timeout_query),'RX_Workbench:Transport');
assert(transport_queries==1);
report=struct('passed',true,'settings_count',36,'writes_verified',numel(writes),'log_path',opts.log_path);
fprintf('RX scope settings mock PASS: 36 fields, 10 isolated writes, local capabilities, holdoff dependencies and observation-band migration.\n');
    function accepted=apply(key,value)
        accepted=msiq.instruments.apply_rx_scope_setting(session,struct('key',key,'value',value),io.query,io.write);
    end
    function value=read(key)
        one=msiq.instruments.rx_scope_settings(session,io.query,struct('requested_keys',{{key}}));
        value=one.fields.value;
    end
    function reply=timeout_query(~,~)
        reply=''; %#ok<NASGU> Deliberately failing query still declares its output.
        transport_queries=transport_queries+1;
        error('mock:Timeout','Injected timeout');
    end
    function reply=capability_failure(ses,command)
        if contains(command,'C2.BandwidthLimit.GetRangeStringRemote')
            error('mock:Timeout','Injected capability timeout');
        end
        reply=io.query(ses,command);
    end
    function reply=unknown_bandwidth(ses,command)
        if strcmp(command,'VBS? ''return=app.Acquisition.C2.BandwidthLimit''')
            reply='30GHz';
        else, reply=io.query(ses,command); end
    end
    function reply=non_edge(ses,command)
        if strcmp(command,'VBS? ''return=app.Acquisition.Trigger.Type''')
            reply='WIDTH';
        else, reply=io.query(ses,command); end
    end
end
function f=field(s,key)
f=s.fields(strcmp({s.fields.key},key));
end
function assert_fails(fn,identifier)
try
    fn();
catch ex
    if nargin>1, assert(strcmp(ex.identifier,identifier)); end
    return;
end
error('validation:MissingFailure','Expected rejection');
end
