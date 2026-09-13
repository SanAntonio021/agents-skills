function report = awg_memory_capacity(context)
%AWG_MEMORY_CAPACITY Check final M8195A waveform lengths before any write.
% Keysight specifies 256 KSa/channel for FOUR+INT and 2 GSa/module for
% standard EXT memory; option 16G expands the EXT module memory to 16 GSa.

if ~isstruct(context) || ~isscalar(context)
    error('msiq:instrument:AwgMemoryContext', ...
        'AWG memory capacity context must be a scalar struct.');
end
dac_mode = upper(required_text(context, 'dac_mode'));
rdiv = upper(required_text(context, 'rdiv'));
modes = normalize_modes(required_field(context, 'channel_memory_modes'));
channels = double(required_field(context, 'selected_channels'));
required = double(required_field(context, 'required_samples_per_channel'));
channels = channels(:).';
required = required(:).';
validateattributes(channels, {'numeric'}, ...
    {'vector','integer','>=',1,'<=',4});
validateattributes(required, {'numeric'}, ...
    {'vector','integer','positive','finite'});
if numel(channels) ~= numel(required) || numel(unique(channels)) ~= numel(channels)
    error('msiq:instrument:AwgMemoryChannels', ...
        'Selected channels and required sample counts need a one-to-one mapping.');
end

divider = parse_divider(rdiv);
[option_raw, option_query_ok] = option_readback(context);
has_16g = option_query_ok && contains(upper(option_raw), '16G');
if has_16g
    module_ext_samples = 16*2^30;
    capacity_source = 'Keysight 16G 选件（*OPT? 已检出）';
    capacity_source_code = 'keysight_16g_option';
elseif option_query_ok
    module_ext_samples = 2*2^30;
    capacity_source = 'Keysight 标准 2 GSa（*OPT? 未检出 16G）';
    capacity_source_code = 'keysight_standard_no_16g';
elseif isempty(option_raw)
    module_ext_samples = 2*2^30;
    capacity_source = 'Keysight 标准 2 GSa（未连接，采用标准容量）';
    capacity_source_code = 'keysight_standard_offline';
else
    module_ext_samples = 2*2^30;
    capacity_source = 'Keysight 标准 2 GSa（*OPT? 查询失败回退）';
    capacity_source_code = 'keysight_standard_query_fallback';
end

int_samples = 2^18;
ext_samples = module_ext_samples/divider;
available_all = zeros(1, 4);
for channel = 1:4
    if strcmp(modes{channel}, 'INT')
        available_all(channel) = int_samples;
    else
        available_all(channel) = ext_samples;
    end
end
available = available_all(channels);
per_channel = repmat(struct('channel', NaN, 'memory_mode', '', ...
    'required_samples', NaN, 'available_samples', NaN, 'ok', false), ...
    1, numel(channels));
for index = 1:numel(channels)
    per_channel(index) = struct('channel', channels(index), ...
        'memory_mode', modes{channels(index)}, ...
        'required_samples', required(index), ...
        'available_samples', available(index), ...
        'ok', required(index) <= available(index));
end

topology = cellfun(@(value) value(1), modes);
topology = char(topology);
ext_channels = find(strcmp(modes, 'EXT'));
topology_ok = strcmp(dac_mode, 'FOUR') && ...
    numel(ext_channels) <= divider && ...
    (isempty(ext_channels) || isequal(ext_channels, 1:numel(ext_channels)));
total_required = sum(required);
total_available = sum(available);
lengths_ok = all([per_channel.ok]) && total_required <= total_available;
ok = topology_ok && lengths_ok;
if ~topology_ok
    reason_code = 'illegal_memory_topology';
    message = sprintf(['FOUR模式下内存拓扑%s与%s不兼容；EXT必须从CH1开始连续配置，', ...
        '且EXT通道数不能超过RDIV数值。未执行波形下载，AWG输出保持不变。'], ...
        topology, rdiv);
elseif ok
    reason_code = 'capacity_ok';
    message = sprintf('容量检查通过：%s合计需要%d点，合计容量%d点。', ...
        channel_list(channels), total_required, total_available);
elseif all(strcmp(modes(channels), 'INT'))
    requirements = channel_values(channels, required, '需要');
    message = sprintf(['当前%s使用INT内存，每路最多%d点；当前波形%s，', ...
        '合计需要%d点，合计容量%d点，无法装入。DIV1、DIV2和DIV4均不会改变INT容量。', ...
        '未执行波形下载，AWG输出保持不变。'], ...
        channel_list(channels), int_samples, requirements, ...
        total_required, total_available);
    reason_code = 'int_capacity_exceeded';
else
    requirements = channel_values(channels, required, '需要');
    limits = channel_values(channels, available, '上限');
    message = sprintf(['当前%s内存容量不足：%s；%s；合计需要%d点，合计容量%d点。', ...
        '未执行波形下载，AWG输出保持不变。'], ...
        channel_list(channels), requirements, limits, ...
        total_required, total_available);
    reason_code = 'capacity_exceeded';
end

report = struct('ok', logical(ok), 'model', 'M8195A', ...
    'dac_mode', dac_mode, 'rdiv', rdiv, ...
    'channel_memory_modes', {modes}, 'memory_topology', topology, ...
    'selected_channels', channels, ...
    'required_samples_per_channel', required, ...
    'available_samples_per_channel', available, ...
    'available_samples_all_channels', available_all, ...
    'per_channel', per_channel, ...
    'total_required_samples', total_required, ...
    'total_available_samples', total_available, ...
    'int_samples_per_channel', int_samples, ...
    'ext_module_samples', module_ext_samples, ...
    'ext_samples_per_channel', ext_samples, ...
    'option_raw', option_raw, 'option_query_ok', logical(option_query_ok), ...
    'option_16g_detected', logical(has_16g), ...
    'capacity_source', capacity_source, ...
    'capacity_source_code', capacity_source_code, ...
    'topology_ok', logical(topology_ok), 'lengths_ok', logical(lengths_ok), ...
    'reason_code', reason_code, 'message', message);
end

function value = required_field(context, name)
if ~isfield(context, name) || isempty(context.(name))
    error('msiq:instrument:AwgMemoryContext', ...
        'AWG memory capacity context is missing %s.', name);
end
value = context.(name);
end

function value = required_text(context, name)
value = char(string(required_field(context, name)));
end

function modes = normalize_modes(value)
if ischar(value) && isrow(value) && numel(value) == 4 && ...
        all(ismember(upper(value), 'IE'))
    tokens = cellstr(upper(value(:)));
    modes = cellfun(@(token) ternary(token == 'I', 'INT', 'EXT'), ...
        tokens, 'UniformOutput', false).';
else
    modes = cellstr(upper(string(value(:).')));
end
if numel(modes) ~= 4 || ~all(ismember(modes, {'INT','EXT'}))
    error('msiq:instrument:AwgMemoryModes', ...
        'channel_memory_modes must define four INT/EXT values.');
end
end

function divider = parse_divider(rdiv)
token = regexp(rdiv, '^DIV([124])$', 'tokens', 'once');
if isempty(token)
    error('msiq:instrument:AwgMemoryRdiv', ...
        'RDIV must be DIV1, DIV2, or DIV4.');
end
divider = str2double(token{1});
end

function [raw, ok] = option_readback(context)
raw = '';
if isfield(context, 'option_raw') && ~isempty(context.option_raw)
    raw = strtrim(char(string(context.option_raw)));
elseif isfield(context, 'options_raw') && ~isempty(context.options_raw)
    raw = strtrim(char(string(context.options_raw)));
end
ok = ~isempty(raw) && ~contains(raw, 'QUERY_FAILED', 'IgnoreCase', true);
end

function value = channel_list(channels)
parts = arrayfun(@(channel) sprintf('CH%d', channel), channels, ...
    'UniformOutput', false);
value = strjoin(parts, '/');
end

function value = channel_values(channels, samples, word)
parts = arrayfun(@(channel, count) sprintf('CH%d%s%d点', ...
    channel, word, count), channels, samples, 'UniformOutput', false);
value = strjoin(parts, '、');
end

function value = ternary(condition, yes_value, no_value)
if condition
    value = yes_value;
else
    value = no_value;
end
end
