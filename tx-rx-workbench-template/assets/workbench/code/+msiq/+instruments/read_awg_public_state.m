function state = read_awg_public_state(session)
%READ_AWG_PUBLIC_STATE Read shared M8195A and per-DAC routing state.

if ~strcmpi(session.kind, 'awg')
    error('msiq:instrument:AwgStateSession', ...
        'An AWG session is required.');
end
state = struct();
state.idn = safe_query(session, '*IDN?');
state.options_raw = safe_query(session, '*OPT?');
state.options_query_ok = ~isempty(state.options_raw) && ...
    ~contains(state.options_raw, 'QUERY_FAILED', 'IgnoreCase', true);
state.dac_mode = upper(safe_query(session, ':INST:DACM?'));
state.rdiv = upper(safe_query(session, ':INST:MEM:EXT:RDIV?'));
state.raster_hz = parse_number(safe_query(session, ':FREQuency:RASTer?'));
state.outputs = msiq.instruments.read_awg_output_state(session);
state.traces = repmat(empty_trace(), 1, 4);
for channel = 1:4
    trace = empty_trace();
    trace.channel = channel;
    trace.memory_mode = upper(safe_query(session, ...
        sprintf(':TRACe%d:MMOD?', channel)));
    trace.selected_segment = parse_number(safe_query(session, ...
        sprintf(':TRACe%d:SELect?', channel)));
    trace.catalog_raw = safe_query(session, ...
        sprintf(':TRACe%d:CATalog?', channel));
    [trace.segment, trace.length] = parse_catalog(trace.catalog_raw, ...
        trace.selected_segment);
    trace.amplitude_vpp = parse_number(safe_query(session, ...
        sprintf(':VOLTage%d:AMPLitude?', channel)));
    trace.offset_v = parse_number(safe_query(session, ...
        sprintf(':VOLTage%d:OFFSet?', channel)));
    trace.sample_clock_delay_samples = parse_number(safe_query(session, ...
        sprintf(':ARM:SDELay%d?', channel)));
    state.traces(channel) = trace;
end
end

function trace = empty_trace()
trace = struct('channel', NaN, 'memory_mode', '', ...
    'selected_segment', NaN, 'catalog_raw', '', 'segment', NaN, ...
    'length', NaN, 'amplitude_vpp', NaN, 'offset_v', NaN, ...
    'sample_clock_delay_samples', NaN);
end

function value = safe_query(session, command)
try
    value = strtrim(char(string(msiq.instruments.query_scpi(session, command))));
catch exception
    value = sprintf('QUERY_FAILED:%s:%s', command, exception.identifier);
end
end

function value = parse_number(text)
token = regexp(char(string(text)), ...
    '[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', 'match', 'once');
if isempty(token)
    value = NaN;
else
    value = str2double(token);
end
end

function [segment, length_value] = parse_catalog(text, selected_segment)
values = regexp(char(string(text)), ...
    '[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', 'match');
if numel(values) >= 2
    numbers = str2double(values);
    segment = numbers(1);
    length_value = numbers(2);
    if isfinite(selected_segment)
        candidates = 1:2:(numel(numbers)-1);
        match = candidates(numbers(candidates) == selected_segment);
        if ~isempty(match)
            segment = numbers(match(1));
            length_value = numbers(match(1)+1);
        end
    end
else
    segment = NaN;
    length_value = NaN;
end
end
