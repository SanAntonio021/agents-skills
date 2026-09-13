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
transport_queries=0;
assert_fails(@() msiq.instruments.rx_scope_settings(session,@timeout_query),'RX_Workbench:Transport');
assert(transport_queries==1);
report=struct('passed',true,'settings_count',36,'writes_verified',numel(writes),'log_path',opts.log_path);
fprintf('RX scope settings mock PASS: 36 fields, 10 isolated writes, timeout/unsupported/mode validation.\n');
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
