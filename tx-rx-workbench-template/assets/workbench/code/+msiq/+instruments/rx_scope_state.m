function status = rx_scope_state(session, query_fn, cached, selected)
%RX_SCOPE_STATE Read live scope state without changing acquisition settings.
if nargin < 2, query_fn = @msiq.instruments.query_scpi; end
if nargin >= 3 && isfield(cached,'channels')
    status = cached;
    status.timebase = number('TDIV?',true);
    status.trigger_delay_s = number('TRDL?',true);
    status.sample_rate_hz = number('VBS? ''return=app.Acquisition.Horizontal.SampleRate''',true);
    status.memory_depth = number('MSIZ?',false);
    bandwidth = ask('BWL?',false);
    if status.timebase<=0 || status.sample_rate_hz<=0
        error('RX_Workbench:Readback','回读 | TDIV? / SampleRate | 必须为正数');
    end
    for k=1:numel(status.channels)
        ch = status.channels(k).channel;
        if ~ismember(ch,selected), continue; end
        trace = ask([ch ':TRA?'],true);
        token = regexp(upper(trace),'(ON|OFF)\s*$','tokens','once');
        if isempty(token), error('RX_Workbench:Readback','回读 | %s:TRA? | %s',ch,trace); end
        status.channels(k).trace_state = token{1};
        scale = number([ch ':VDIV?'],true);
        if scale<=0, error('RX_Workbench:Readback','回读 | %s:VDIV? | 必须为正数',ch); end
        status.channels(k).vertical_scale_v_per_div = scale;
        status.channels(k).offset_v = number([ch ':OFST?'],true);
        coupling = ask([ch ':CPL?'],false);
        status.channels(k).coupling = coupling;
        status.channels(k).impedance_ohm = impedance_value(coupling);
        [status.channels(k).bandwidth_limit_hz,status.channels(k).bandwidth_text] = band_value(bandwidth,ch);
    end
    status.readback_at = datetime('now');
    return;
end
idn = ask('*IDN?', true);
if numel(strsplit(idn, ',')) < 3
    error('RX_Workbench:Readback', '回读 | *IDN? | 无效设备标识：%s', idn);
end
status = struct('idn', idn, 'timebase', number('TDIV?', true), ...
    'trigger_delay_s', number('TRDL?', true), ...
    'sample_rate_hz', number('VBS? ''return=app.Acquisition.Horizontal.SampleRate''', true), ...
    'memory_depth', number('MSIZ?', false), 'vertical_divisions', 8);
if status.timebase <= 0 || status.sample_rate_hz <= 0
    error('RX_Workbench:Readback', '回读 | TDIV? / Horizontal.SampleRate | 必须为正数');
end
bandwidth = ask('BWL?', false);
for k = 1:4
    ch = sprintf('C%d', k);
    trace = ask([ch ':TRA?'], true);
    trace_token = regexp(upper(trace), '(ON|OFF)\s*$', 'tokens', 'once');
    if isempty(trace_token)
        error('RX_Workbench:Readback', '回读 | %s:TRA? | 无效输出：%s', ch, trace);
    end
    scale = number([ch ':VDIV?'], true);
    if scale <= 0
        error('RX_Workbench:Readback', '回读 | %s:VDIV? | 量程必须为正数', ch);
    end
    coupling = ask([ch ':CPL?'], false);
    impedance = impedance_value(coupling);
    [limit,band_text] = band_value(bandwidth,ch);
    status.channels(k) = struct('channel', ch, 'trace_state', trace_token{1}, ...
        'vertical_scale_v_per_div', scale, 'offset_v', number([ch ':OFST?'], true), ...
        'coupling', coupling, 'impedance_ohm', impedance, ...
        'bandwidth_limit_hz', limit, 'bandwidth_text', band_text, ...
        'interpolation', property(ch, 'InterpolateType'), ...
        'average_sweeps', number(vbs(ch, 'AverageSweeps'), false), ...
        'enhance_resolution', property(ch, 'EnhanceResType'), ...
        'optimize_group_delay', property(ch, 'OptimizeGroupDelay'));
end
status.readback_at = datetime('now');

    function value = property(ch, name)
        value = ask(vbs(ch, name), false);
        value = regexprep(value, '^VBS\s+', '', 'ignorecase');
        value = strrep(value, '"', '');
        if isempty(value), value = '未知'; end
    end

    function value = number(command, required)
        raw = ask(command, required);
        % Reject error strings before parsing; channel numbers are not values.
        number_token = regexp(raw, '([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?:[a-zA-Z/]+)?\s*$', 'tokens', 'once');
        value = NaN;
        if ~isempty(number_token), value = str2double(number_token{1}); end
        if required && ~isfinite(value)
            error('RX_Workbench:Readback', '回读 | %s | 无效数值：%s', command, raw);
        end
    end

    function raw = ask(command, required)
        try
            raw = strtrim(char(string(query_fn(session, command))));
        catch exception
            % A transport timeout is never an unsupported-property fallback.
            error('RX_Workbench:Transport', '回读 | %s | %s', command, exception.message);
        end
        bad = isempty(raw) || ~isempty(regexpi(raw, ...
            'QUERY_FAILED|error|doesn.t support|does not support|unknown|invalid|unsupported', 'once'));
        if bad
            if required
                error('RX_Workbench:Readback', '回读 | %s | %s', command, raw);
            end
            raw = '';
        end
    end
end

function command = vbs(channel, property)
command = sprintf('VBS? ''return=app.Acquisition.%s.%s''', channel, property);
end

function value = impedance_value(coupling)
value = NaN;
if ~isempty(regexp(upper(coupling),'(A|D)50\s*$','once')), value=50; end
if ~isempty(regexp(upper(coupling),'(A|D)1M\s*$','once')), value=1e6; end
end

function [limit,label] = band_value(response,channel)
limit=NaN; label='未知';
token=regexp(upper(response),[channel '\s*,\s*([^,\s]+)'],'tokens','once');
if isempty(token), return; end
label=token{1};
if ismember(label,{'OFF','FULL'}), limit=Inf; return; end
parts=regexp(label,'^(\d+(?:\.\d+)?)\s*([GMK]?)HZ$','tokens','once');
if isempty(parts), return; end
multiplier=1;
switch parts{2}
    case 'G', multiplier=1e9;
    case 'M', multiplier=1e6;
    case 'K', multiplier=1e3;
end
limit=str2double(parts{1})*multiplier;
end
