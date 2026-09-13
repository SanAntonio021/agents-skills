function diagnostics=rx_capture_consistency(raw,before,after,channels)
%RX_CAPTURE_CONSISTENCY Reject a frame whose acquisition settings changed.
diagnostics=struct('channel',{},'scope_offset_v',{},'waveform_offset_v',{}, ...
    'offset_delta_v',{});
for name={'timebase','trigger_delay_s','sample_rate_hz','memory_depth'}
    check(field_or(before,name{1},NaN),field_or(after,name{1},NaN),name{1});
end
for ch=channels
    a=before.channels(strcmp({before.channels.channel},ch{1}));
    b=after.channels(strcmp({after.channels.channel},ch{1}));
    for name={'trace_state','vertical_scale_v_per_div','offset_v','coupling','bandwidth_limit_hz'}
        check(a.(name{1}),b.(name{1}),[ch{1} ' ' name{1}]);
    end
    % A capture with no enabled requested trace is a valid no-data result.
    % Do not dereference an untyped/empty channel list here; the readback
    % snapshot above is still checked for acquisition-setting drift.
    records=field_or(raw,'channels',struct([]));
    if isempty(records) || ~isstruct(records) || ~isfield(records,'channel'), continue; end
    index=find(strcmp({records.channel},ch{1}),1);
    if isempty(index), continue; end
    record=records(index);
    descriptor=field_or(record,'descriptor',struct());
    offset=field_or(descriptor,'vertical_offset',NaN);
    % WAVEDESC supplies the ADC decoding coefficient, OFST the display setting.
    % A calibrated waveform need not make these two different quantities equal.
    diagnostics(end+1)=struct('channel',ch{1},'scope_offset_v',b.offset_v, ...
        'waveform_offset_v',offset,'offset_delta_v',offset-b.offset_v); %#ok<AGROW>
    origin=field_or(descriptor,'horizontal_offset_s',NaN);
    if isfinite(origin) && ~isempty(record.time_axis_s) && ...
            abs(origin-record.time_axis_s(1))>max(1e-15,before.timebase*1e-6)
        changed([ch{1} ' WAVEDESC / 时间原点'],origin,record.time_axis_s(1));
    end
end
end

function check(a,b,name)
if isnumeric(a) && isnumeric(b) && isscalar(a) && isscalar(b)
    if isequaln(a,b), return; end
    if isfinite(a) && isfinite(b) && abs(a-b)<=max(1e-15,max(abs([a b]))*1e-8), return; end
elseif isequaln(a,b)
    return;
end
changed(name,a,b);
end

function changed(name,a,b)
if isnumeric(a), a=mat2str(a,17); else, a=char(string(a)); end
if isnumeric(b), b=mat2str(b,17); else, b=char(string(b)); end
error('RX_Workbench:CaptureChanged','%s 不一致：%s -> %s；本帧未采用',name,a,b);
end

function value=field_or(s,name,fallback)
if isstruct(s) && isfield(s,name) && ~isempty(s.(name)), value=s.(name);
else, value=fallback; end
end
