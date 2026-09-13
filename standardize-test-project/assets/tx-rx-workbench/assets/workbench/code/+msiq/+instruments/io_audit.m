function [value, extra] = io_audit(action, field)
%IO_AUDIT Track instrument I/O and AWG output state for safety tests.

persistent state command_history mock_awg
if isempty(state)
    state = initial_state();
    command_history = {};
    mock_awg = initial_mock_awg();
end
extra = [];
switch lower(action)
    case 'reset'
        state = initial_state();
        command_history = {};
        mock_awg = initial_mock_awg();
        value = state;
    case 'increment'
        if ~isfield(state, field)
            error('msiq:instrument:AuditField', ...
                'Unknown I/O audit field: %s', field);
        end
        state.(field) = state.(field) + 1;
        value = state;
    case 'record_connection'
        role = normalize_role(field);
        state.connections = state.connections + 1;
        state.([role, '_connections']) = ...
            state.([role, '_connections']) + 1;
        value = state;
    case 'record_query'
        role = normalize_role(field);
        state.queries = state.queries + 1;
        state.([role, '_queries']) = state.([role, '_queries']) + 1;
        value = state;
    case 'record_write'
        role = normalize_role(field);
        state.writes = state.writes + 1;
        state.([role, '_writes']) = state.([role, '_writes']) + 1;
        value = state;
    case 'record_command'
        if ~isstruct(field) || ~isfield(field, 'role') || ~isfield(field, 'command')
            error('msiq:instrument:AuditCommand', ...
                'record_command requires role and command.');
        end
        command_history{end+1,1} = struct( ...
            'role', normalize_role(field.role), ...
            'command', char(string(field.command)));
        value = numel(command_history);
    case 'get_command_history'
        value = command_history;
    case 'record_capture'
        role = normalize_role(field);
        state.captures = state.captures + 1;
        state.([role, '_captures']) = state.([role, '_captures']) + 1;
        value = state;
    case 'record_binary_write'
        role = normalize_role(field);
        state.binary_writes = state.binary_writes + 1;
        state.([role, '_binary_writes']) = ...
            state.([role, '_binary_writes']) + 1;
        value = state;
    case 'record_close'
        role = normalize_role(field);
        state.closes = state.closes + 1;
        state.([role, '_closes']) = state.([role, '_closes']) + 1;
        value = state;
    case 'apply_awg_command'
        state = apply_awg_command(state, char(string(field)));
        mock_awg = apply_mock_awg_command(mock_awg, char(string(field)));
        value = state;
    case 'mock_awg_query'
        [value, extra] = mock_awg_query(mock_awg, char(string(field)));
    case 'set_mock_awg_state'
        if ~isstruct(field) || ~isscalar(field)
            error('msiq:instrument:MockAwgState', ...
                'Mock AWG state must be a scalar struct.');
        end
        mock_awg = merge_struct(mock_awg, field);
        mock_awg = normalize_mock_awg(mock_awg);
        value = mock_awg;
    case 'get_mock_awg_state'
        value = mock_awg;
    case 'get_awg_output'
        channel = double(field);
        validateattributes(channel, {'numeric'}, ...
            {'scalar','integer','>=',1,'<=',4});
        value = bitget(uint8(state.awg_output_mask), channel) ~= 0;
    case 'get'
        value = state;
    otherwise
        error('msiq:instrument:AuditAction', ...
            'Unknown I/O audit action: %s', action);
end
end

function state = initial_state()
state = struct('connections', 0, 'queries', 0, 'writes', 0, ...
    'captures', 0, 'binary_writes', 0, 'driver_initializations', 0, ...
    'shutdown_calls', 0, 'closes', 0, ...
    'awg_connections', 0, 'scope_connections', 0, 'source_connections', 0, ...
    'awg_queries', 0, 'scope_queries', 0, 'source_queries', 0, ...
    'awg_writes', 0, 'scope_writes', 0, 'source_writes', 0, ...
    'awg_captures', 0, 'scope_captures', 0, 'source_captures', 0, ...
    'awg_binary_writes', 0, 'scope_binary_writes', 0, ...
    'source_binary_writes', 0, ...
    'awg_closes', 0, 'scope_closes', 0, 'source_closes', 0, ...
    'awg_output_mask', 0, 'max_awg_outputs_enabled', 0, ...
    'awg_output_transitions', 0, 'multi_output_events', 0);
end

function state = initial_mock_awg()
trace = struct('memory_mode', 'EXT', 'segment', 1, ...
    'selected_segment', 1, 'length', 0);
state = struct('dac_mode', 'FOUR', 'rdiv', 'DIV4', 'raster_hz', 65e9, ...
    'options_raw', '0', ...
    'traces', repmat(trace, 1, 4), ...
    'amplitude_vpp', 0.2*ones(1,4), 'offset_v', zeros(1,4), ...
    'sample_clock_delay_samples', zeros(1,4), ...
    'ignore_sdel_writes', false(1,4));
end

function role = normalize_role(value)
role = lower(char(string(value)));
if strcmp(role, 'signal_generator')
    role = 'source';
end
if ~ismember(role, {'awg','scope','source'})
    error('msiq:instrument:AuditRole', ...
        'Unsupported instrument audit role: %s.', role);
end
end

function state = apply_awg_command(state, command)
tokens = regexp(command, ...
    ':OUTPut\s*([1-4])\s+(ON|OFF|1|0)', 'tokens', 'ignorecase');
for k = 1:numel(tokens)
    channel = str2double(tokens{k}{1});
    enabled = ismember(upper(tokens{k}{2}), {'ON','1'});
    state.awg_output_mask = double(bitset( ...
        uint8(state.awg_output_mask), channel, enabled));
    enabled_count = nnz(bitget(uint8(state.awg_output_mask), 1:4));
    state.max_awg_outputs_enabled = max( ...
        state.max_awg_outputs_enabled, enabled_count);
    state.awg_output_transitions = state.awg_output_transitions + 1;
    if enabled_count > 1
        state.multi_output_events = state.multi_output_events + 1;
    end
end
end

function state = apply_mock_awg_command(state, command)
mode = regexp(command, ':INST:DACM\s+([A-Za-z0-9_]+)', ...
    'tokens', 'once', 'ignorecase');
if ~isempty(mode)
    state.dac_mode = upper(mode{1});
end
rdiv = regexp(command, ':INST:MEM:EXT:RDIV\s+([A-Za-z0-9_]+)', ...
    'tokens', 'once', 'ignorecase');
if ~isempty(rdiv)
    state.rdiv = upper(rdiv{1});
end
raster = regexp(command, ':FREQuency:RASTer\s+([-+0-9.eE]+)', ...
    'tokens', 'once', 'ignorecase');
if ~isempty(raster)
    value = str2double(raster{1});
    if isfinite(value), state.raster_hz = value; end
end
memory = regexp(command, ':TRACe([1-4]):MMOD\s+([A-Za-z0-9_]+)', ...
    'tokens', 'ignorecase');
for k = 1:numel(memory)
    channel = str2double(memory{k}{1});
    state.traces(channel).memory_mode = upper(memory{k}{2});
end
deleted = regexp(command, ':TRACe([1-4]):DELete\s+([0-9]+)', ...
    'tokens', 'ignorecase');
for k = 1:numel(deleted)
    channel = str2double(deleted{k}{1});
    segment = str2double(deleted{k}{2});
    if state.traces(channel).segment == segment
        state.traces(channel).length = 0;
    end
end
defined = regexp(command, ':TRACe([1-4]):DEFine\s+([0-9]+)\s*,\s*([0-9]+)', ...
    'tokens', 'ignorecase');
for k = 1:numel(defined)
    channel = str2double(defined{k}{1});
    state.traces(channel).segment = str2double(defined{k}{2});
    state.traces(channel).length = str2double(defined{k}{3});
end
selected = regexp(command, ':TRACe([1-4]):SELect\s+([0-9]+)', ...
    'tokens', 'ignorecase');
for k = 1:numel(selected)
    channel = str2double(selected{k}{1});
    state.traces(channel).selected_segment = str2double(selected{k}{2});
end
amplitude = regexp(command, ':VOLTage([1-4]):AMPLitude\s+([-+0-9.eE]+)', ...
    'tokens', 'ignorecase');
for k = 1:numel(amplitude)
    channel = str2double(amplitude{k}{1});
    state.amplitude_vpp(channel) = str2double(amplitude{k}{2});
end
offset = regexp(command, ':VOLTage([1-4]):OFFSet\s+([-+0-9.eE]+)', ...
    'tokens', 'ignorecase');
for k = 1:numel(offset)
    channel = str2double(offset{k}{1});
    state.offset_v(channel) = str2double(offset{k}{2});
end
sdel = regexp(command, ':ARM:SDELay([1-4])\s+([0-9]+)', ...
    'tokens', 'ignorecase');
for k = 1:numel(sdel)
    channel = str2double(sdel{k}{1});
    if ~state.ignore_sdel_writes(channel)
        state.sample_clock_delay_samples(channel) = str2double(sdel{k}{2});
    end
end
state = normalize_mock_awg(state);
end

function [response, handled] = mock_awg_query(state, command)
response = '';
handled = true;
command = upper(strtrim(command));
if strcmp(command, ':INST:DACM?')
    response = state.dac_mode;
elseif strcmp(command, '*OPT?')
    response = state.options_raw;
elseif strcmp(command, ':INST:MEM:EXT:RDIV?')
    response = state.rdiv;
elseif strcmp(command, ':FREQUENCY:RASTER?')
    response = num2str(state.raster_hz, '%.15g');
else
    token = regexp(command, '^:TRACE([1-4]):MMOD\?$', 'tokens', 'once');
    if ~isempty(token)
        response = state.traces(str2double(token{1})).memory_mode;
        return;
    end
    token = regexp(command, '^:TRACE([1-4]):SELECT\?$', 'tokens', 'once');
    if ~isempty(token)
        response = num2str(state.traces(str2double(token{1})).selected_segment);
        return;
    end
    token = regexp(command, '^:TRACE([1-4]):CATALOG\?$', 'tokens', 'once');
    if ~isempty(token)
        trace = state.traces(str2double(token{1}));
        response = sprintf('%d,%d', trace.segment, trace.length);
        return;
    end
    token = regexp(command, '^:VOLTAGE([1-4]):AMPLITUDE\?$', 'tokens', 'once');
    if ~isempty(token)
        response = num2str(state.amplitude_vpp(str2double(token{1})), '%.15g');
        return;
    end
    token = regexp(command, '^:VOLTAGE([1-4]):OFFSET\?$', 'tokens', 'once');
    if ~isempty(token)
        response = num2str(state.offset_v(str2double(token{1})), '%.15g');
        return;
    end
    token = regexp(command, '^:ARM:SDELAY([1-4])\?$', 'tokens', 'once');
    if ~isempty(token)
        response = num2str(state.sample_clock_delay_samples( ...
            str2double(token{1})), '%.15g');
        return;
    end
    handled = false;
end
end

function state = normalize_mock_awg(state)
if ~isfield(state, 'traces') || numel(state.traces) ~= 4
    error('msiq:instrument:MockAwgState', ...
        'Mock AWG state needs four trace records.');
end
state.dac_mode = upper(char(string(state.dac_mode)));
state.rdiv = upper(char(string(state.rdiv)));
state.options_raw = char(string(state.options_raw));
state.raster_hz = double(state.raster_hz);
state.amplitude_vpp = double(state.amplitude_vpp(:).');
state.offset_v = double(state.offset_v(:).');
state.sample_clock_delay_samples = double( ...
    state.sample_clock_delay_samples(:).');
state.ignore_sdel_writes = logical(state.ignore_sdel_writes(:).');
if numel(state.amplitude_vpp) ~= 4 || numel(state.offset_v) ~= 4 || ...
        numel(state.sample_clock_delay_samples) ~= 4 || ...
        numel(state.ignore_sdel_writes) ~= 4
    error('msiq:instrument:MockAwgState', ...
        'Mock AWG levels and delays need four elements.');
end
if any(~isfinite(state.sample_clock_delay_samples)) || ...
        any(state.sample_clock_delay_samples < 0) || ...
        any(state.sample_clock_delay_samples > 95) || ...
        any(abs(state.sample_clock_delay_samples- ...
        round(state.sample_clock_delay_samples)) > 1e-9)
    error('msiq:instrument:MockAwgState', ...
        'Mock AWG sample-clock delays must be integers in [0, 95].');
end
state.sample_clock_delay_samples = round(state.sample_clock_delay_samples);
for k = 1:4
    state.traces(k).memory_mode = upper(char(string(state.traces(k).memory_mode)));
    state.traces(k).segment = double(state.traces(k).segment);
    state.traces(k).selected_segment = double(state.traces(k).selected_segment);
    state.traces(k).length = double(state.traces(k).length);
end
end

function out = merge_struct(base, extra)
out = base;
names = fieldnames(extra);
for k = 1:numel(names)
    out.(names{k}) = extra.(names{k});
end
end
