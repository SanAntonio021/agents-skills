function raw = capture_scope_raw(session, requested_channels, options)
%CAPTURE_SCOPE_RAW Read LeCroy WAVEFORM blocks without an IVI/MDD driver.

if nargin<3, options=struct(); end
observation=isfield(options,'mode') && strcmpi(options.mode,'observation');
if isfield(options,'mode') && ~any(strcmpi(options.mode,{'observation','capture'}))
    error('msiq:instrument:ScopeRawMode','Unknown raw capture mode.');
end

if ~strcmpi(session.kind, 'scope')
    error('msiq:instrument:ScopeRawSession', ...
        'A scope session is required.');
end
channels = cellstr(string(requested_channels));
if isempty(channels) || numel(channels) > 4
    error('msiq:instrument:ScopeRawChannels', ...
        'Capture needs one to four scope channels.');
end
msiq.instruments.io_audit('record_capture', session.kind);
if ~observation, restore = onCleanup(@() restore_auto(session)); end
if ~observation
    msiq.instruments.write_scpi(session, 'COMM_HEADER OFF');
    msiq.instruments.write_scpi(session, 'COMM_FORMAT DEF9,BYTE,BIN');
    msiq.instruments.write_scpi(session, 'CORD LO');
end
if ~observation, msiq.instruments.write_scpi(session, 'STOP'); end

if session.mock
    fail_if_requested(session, 'raw_read');
    raw = mock_capture(session, channels, observation);
    if observation && isfield(options,'query_fn')
        for k=1:numel(raw.channels)
            raw.channels(k).descriptor=read_result_update(session,raw.channels(k).descriptor, ...
                channels{k},options.query_fn);
        end
    end
    clear restore;
    return;
end

prepare_buffer(session.interface);
records = repmat(empty_record(), 1, numel(channels));
for k = 1:numel(channels)
    % DAT1 omits WAVEDESC on the SDA845ZI-A. ALL carries the descriptor
    % followed by the raw sample array required for calibrated decoding.
    command = sprintf('%s:WAVEFORM? ALL', channels{k});
    try
        msiq.instruments.write_scpi(session, command);
        payload = read_ieee488_block(session.interface);
        records(k) = decode_waveform(payload, channels{k}, observation);
        if observation
            records(k).descriptor=read_result_update(session,records(k).descriptor, ...
                channels{k},@msiq.instruments.query_scpi);
        end
    catch exception
        identifier = exception.identifier;
        if isempty(identifier), identifier = 'msiq:instrument:ScopeRead'; end
        failure = MException(identifier, ...
            'Capture | %s | %s', command, exception.message);
        failure = addCause(failure, exception);
        throw(failure);
    end
end
raw = struct('schema_version', '1.0', 'channels', records, ...
    'captured_at', char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX')));
raw.observation_mode=observation;
raw.channels_same_trigger_confirmed=false;
clear restore;
end

function descriptor=read_result_update(session,descriptor,channel,query_fn)
% Processing may continue after SWEEPS_PER_ACQ reaches its configured limit.
for property={'UpdateTime','LastEventTime'}
    command=sprintf('VBS? ''return=app.Acquisition.%s.Out.Result.%s''',channel,property{1});
    try
        reply=strtrim(char(string(query_fn(session,command))));
    catch exception
        if contains(lower(exception.identifier),'unsupported'), continue; end
        error('RX_Workbench:Transport','回读 | %s | %s',command,exception.message);
    end
    if isempty(reply) || ~isempty(regexpi(reply, ...
            'error|unsupported|unknown|invalid|does.?n.t support|does not support','once'))
        continue;
    end
    reply=strtrim(regexprep(reply,'^VBS\s+','','ignorecase'));
    reply=strrep(strrep(reply,'"',''),'''','');
    % Require an instrument numeric time or a recognizable date/time value.
    numeric=str2double(reply);
    if ~(isfinite(numeric) || ~isempty(regexp(reply,'\d[/:\-]\d','once'))), continue; end
    descriptor.result_update_id=[property{1} ':' reply];
    return;
end
end

function restore_auto(session)
try
    msiq.instruments.write_scpi(session, 'TRMD AUTO');
catch
end
end

function raw = mock_capture(session, channels, observation)
spec = session.specification;
if isfield(spec, 'mock_raw_capture')
    source = spec.mock_raw_capture;
elseif isfield(spec, 'mock_capture')
    source = spec.mock_capture;
else
    error('msiq:instrument:MockCaptureMissing', ...
        'Mock raw scope requires mock_raw_capture or mock_capture.');
end
if isfield(source, 'channels')
    records = source.channels;
    if numel(records) ~= numel(channels)
        error('msiq:instrument:MockCaptureChannels', ...
            'Mock channel count does not match the request.');
    end
elseif isfield(source, 'payloads')
    payloads = source.payloads;
    if ~iscell(payloads) || numel(payloads) < numel(channels)
        error('msiq:instrument:MockCapturePayloads', ...
            'Mock binary capture needs one payload per requested channel.');
    end
    records = repmat(empty_record(), 1, numel(channels));
    for k = 1:numel(channels)
        records(k) = decode_waveform(uint8(payloads{k}), channels{k}, observation);
        records(k).descriptor.source = 'mock_binary_wavedesc';
    end
else
    samples = double(source.samples);
    time_axes = double(source.time_axes);
    if size(samples,2) < numel(channels) || size(time_axes,2) < numel(channels)
        error('msiq:instrument:MockCaptureChannels', ...
            'Mock capture does not contain requested channels.');
    end
    records = repmat(empty_record(), 1, numel(channels));
    for k = 1:numel(channels)
        records(k) = struct('channel', channels{k}, ...
            'samples', samples(:,k), 'time_axis_s', time_axes(:,k), ...
            'sample_rate_hz', estimate_rate(time_axes(:,k)), ...
            'descriptor', struct('source', 'mock'));
    end
end
for k = 1:numel(records)
    records(k).channel = channels{k};
end
raw = struct('schema_version', '1.0', 'channels', records, ...
    'captured_at', 'mock');
raw.observation_mode=observation;
raw.channels_same_trigger_confirmed=false;
end

function prepare_buffer(interface)
try
    interface.InputBufferSize = max(double(interface.InputBufferSize), 64*1024*1024);
catch
end
end

function payload = read_ieee488_block(interface)
first = uint8([]);
for k = 1:32
    value = uint8(fread(interface, 1, 'uint8'));
    if isempty(value)
        error('msiq:instrument:ScopeReadTimeout', ...
            'No waveform byte received before the VISA read timed out.');
    end
    if value == uint8('#')
        first = value;
        break;
    end
end
if isempty(first)
    error('msiq:instrument:ScopeBlockHeader', ...
        'LeCroy waveform response did not contain an IEEE-488.2 block.');
end
digit_count = str2double(char(uint8(fread(interface, 1, 'uint8'))));
if ~isfinite(digit_count) || digit_count < 1 || digit_count > 9
    error('msiq:instrument:ScopeBlockHeader', 'Invalid IEEE block length field.');
end
length_text = char(uint8(fread(interface, digit_count, 'uint8')).');
payload_length = str2double(length_text);
if ~isfinite(payload_length) || payload_length < 1
    error('msiq:instrument:ScopeBlockHeader', 'Invalid IEEE block payload length.');
end
payload = uint8(fread(interface, payload_length, 'uint8'));
if numel(payload) ~= payload_length
    error('msiq:instrument:ScopeBlockShortRead', ...
        'LeCroy waveform payload was shorter than advertised.');
end
end

function record = decode_waveform(payload, channel, observation)
% WAVEDESC COMM_ORDER is self-identifying (0=high first, 1=low first).
big_endian=observation && numel(payload)>=36 && all(payload(35:36)==0);
if big_endian
    for entry=[32 2;34 2;36 4;40 4;44 4;48 4;52 4;56 4;60 4; ...
            144 4;148 4;156 4;160 4;176 4;180 8;316 2;318 2].'
        index=entry(1)+(1:entry(2));
        if max(index)<=numel(payload), payload(index)=flip(payload(index)); end
    end
end
descriptor_length = number_at(payload, 36, 'uint32');
user_text = number_at(payload, 40, 'uint32');
reserved_1 = number_at(payload, 44, 'uint32');
trigger_array = number_at(payload, 48, 'uint32');
ris_array = number_at(payload, 52, 'uint32');
reserved_2 = number_at(payload, 56, 'uint32');
wave_bytes = number_at(payload, 60, 'uint32');
if observation && (number_at(payload,144,'uint32')>1 || ris_array>0 || ...
        any(number_at(payload,316,'int16')==[1 7]))
    error('RX_Workbench:UnsupportedMode', ...
        'Observation supports real-time single-segment waveforms only; sequence/RIS record received.');
end
data_start = double(descriptor_length) + double(user_text) + ...
    double(reserved_1) + double(trigger_array) + double(ris_array) + ...
    double(reserved_2) + 1;
if data_start < 1 || data_start+double(wave_bytes)-1 > numel(payload)
    error('msiq:instrument:WaveDescBounds', ...
        'WAVEDESC data bounds are invalid.');
end
comm_type = number_at(payload, 32, 'int16');
gain = number_at(payload, 156, 'single');
offset = number_at(payload, 160, 'single');
interval = number_at(payload, 176, 'single');
time_offset = number_at(payload, 180, 'double');
data_bytes = payload(data_start:data_start+double(wave_bytes)-1);
if comm_type == 0
    raw_codes = double(typecast(uint8(data_bytes), 'int8'));
elseif comm_type == 1
    if mod(numel(data_bytes), 2) ~= 0
        error('msiq:instrument:WaveDescWordLength', ...
            'WORD waveform data has an odd byte count.');
    end
    values=typecast(uint8(data_bytes), 'int16');
    if big_endian, values=swapbytes(values); end
    raw_codes = double(values);
else
    error('msiq:instrument:WaveDescCommType', ...
        'Unsupported WAVEDESC COMM_TYPE %d.', comm_type);
end
samples = gain*raw_codes(:) - offset;
time_axis = time_offset + (0:numel(samples)-1).'*interval;
descriptor = struct('wave_descriptor_bytes', double(descriptor_length), ...
    'wave_array_bytes', double(wave_bytes), 'comm_type', double(comm_type), ...
    'vertical_gain', double(gain), 'vertical_offset', double(offset), ...
    'horizontal_interval_s', double(interval), ...
    'horizontal_offset_s', double(time_offset));
if descriptor_length>=322 && numel(payload)>=322
    descriptor.trigger_time_bytes=uint8(payload(297:312));
    descriptor.sweeps_per_acq=number_at(payload,148,'uint32');
    descriptor.subarray_count=number_at(payload,144,'uint32');
    descriptor.record_type=number_at(payload,316,'int16');
    descriptor.processing_done=number_at(payload,318,'int16');
end
record = struct('channel', channel, 'samples', samples, ...
    'time_axis_s', time_axis, 'sample_rate_hz', 1/double(interval), ...
    'descriptor', descriptor);
end

function value = number_at(bytes, zero_offset, type)
width = type_width(type);
first = zero_offset + 1;
last = first + width - 1;
if last > numel(bytes)
    error('msiq:instrument:WaveDescShort', ...
        'WAVEDESC is shorter than required field offset %d.', zero_offset);
end
value = double(typecast(uint8(bytes(first:last)), type));
end

function width = type_width(type)
switch type
    case {'int16', 'uint16'}, width = 2;
    case {'int32', 'uint32', 'single'}, width = 4;
    case 'double', width = 8;
    otherwise
        error('msiq:instrument:WaveDescType', 'Unsupported type %s.', type);
end
end

function rate = estimate_rate(time_axis)
delta = diff(double(time_axis(:)));
delta = delta(isfinite(delta) & delta > 0);
if isempty(delta)
    rate = NaN;
else
    rate = 1/median(delta);
end
end

function record = empty_record()
record = struct('channel', '', 'samples', zeros(0,1), ...
    'time_axis_s', zeros(0,1), 'sample_rate_hz', NaN, 'descriptor', struct());
end

function fail_if_requested(session, stage)
spec = session.specification;
if isfield(spec, 'fail_stage') && strcmpi(char(string(spec.fail_stage)), stage)
    error('msiq:instrument:MockRawReadFailure', ...
        'Injected raw scope failure at %s.', stage);
end
end
