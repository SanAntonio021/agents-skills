function [records, diagnostics, origin, limits_us] = rx_capture_channels(raw,context,decoded)
%RX_CAPTURE_CHANNELS Resolve the observed pair and its saved physical limits.
if nargin < 2 || ~isstruct(context), context = struct(); end
if nargin < 3 || ~isstruct(decoded), decoded = struct(); end
records = raw_records(raw,context);
diagnostics = struct([]);
origin = NaN;
limits_us = [0 1];
if isempty(records), return; end
indices = selected_channels(records,context,decoded);
records = records(indices);
if isempty(records), return; end
scope = field_or(context,'scope_status',struct());
scope_channels = field_or(scope,'channels',struct([]));
template = struct('name','','sample_count',0,'sample_rate_hz',NaN, ...
    'frequency_limit_hz',NaN,'bandwidth_known',false,'impedance_ohm',NaN, ...
    'power_dbm',NaN,'rms_v',NaN,'vpp_v',NaN,'voltage_limits',[-1 1], ...
    'inband_power_dbm',NaN,'inband_rms_v',NaN, ...
    'inband_frequency_limits_hz',[NaN NaN], ...
    'inband_power_available',false,'inband_power_reason','未计算');
diagnostics = repmat(template,1,numel(records));
starts = [];
stops = [];
for k = 1:numel(records)
    record = records(k);
    name = record_name(record,k);
    samples = double(field_or(record,'samples',[]));
    samples = samples(:);
    time = double(field_or(record,'time_axis_s',[]));
    time = time(:);
    rate = positive(field_or(record,'sample_rate_hz',NaN));
    if numel(time) == numel(samples) && numel(time) >= 2 && ...
            all(isfinite(time)) && all(diff(time) > 0)
        rate = 1/median(diff(time));
        starts(end+1) = time(1); %#ok<AGROW>
        stops(end+1) = time(end); %#ok<AGROW>
    elseif ~isempty(time)
        % A malformed stored axis must not be relabeled using a nominal rate.
        rate = NaN;
    end
    records(k).channel = name;
    records(k).sample_rate_hz = rate;
    channel = matching_channel(scope_channels,name);
    constraints = [bandwidth_values(record),bandwidth_values(channel), ...
        bandwidth_values(scope)];
    known_bandwidth = ~isempty(constraints);
    limit = rate/2;
    if isfinite(limit) && known_bandwidth, limit = min([limit,constraints]); end
    impedance = channel_impedance(record,channel);
    finite = samples(isfinite(samples));
    rms_v = NaN; vpp_v = NaN; power_dbm = NaN;
    if ~isempty(finite)
        rms_v = sqrt(mean(abs(finite).^2));
        if isreal(finite), vpp_v = max(finite)-min(finite); end
        if isfinite(impedance)
            power_dbm = 10*log10(max(rms_v^2/impedance*1000,realmin));
        end
    end
    diagnostics(k) = struct('name',name,'sample_count',numel(samples), ...
        'sample_rate_hz',rate,'frequency_limit_hz',limit, ...
        'bandwidth_known',known_bandwidth,'impedance_ohm',impedance, ...
        'power_dbm',power_dbm,'rms_v',rms_v,'vpp_v',vpp_v, ...
        'voltage_limits',voltage_limits(record,channel,context,finite), ...
        'inband_power_dbm',NaN,'inband_rms_v',NaN, ...
        'inband_frequency_limits_hz',[NaN NaN], ...
        'inband_power_available',false,'inband_power_reason','未计算');
end
if ~isempty(starts) && max(stops) > min(starts)
    origin = min(starts);
    limits_us = [0,max(stops)-origin]*1e6;
end
end

function records = raw_records(raw,context)
records = struct([]);
if ~isstruct(raw), return; end
if isfield(raw,'channels') && isstruct(raw.channels) && ~isempty(raw.channels)
    records = raw.channels;
    return;
end
samples = field_or(raw,'samples',[]);
if ~isnumeric(samples) || isempty(samples), return; end
samples = double(samples);
if isvector(samples), samples = samples(:); end
if size(samples,1) < size(samples,2), samples = samples.'; end
count = size(samples,2);
rate = positive(field_or(raw,'sample_rate_hz',NaN));
time = field_or(raw,'time_axes',[]);
if isvector(time), time = time(:); end
if ~isempty(time) && size(time,1) ~= size(samples,1) && size(time,2) == size(samples,1)
    time = time.';
end
if isempty(time) && isfinite(rate)
    time = (0:size(samples,1)-1).'/rate;
end
if ~isempty(time) && (size(time,1) ~= size(samples,1) || ...
        ~ismember(size(time,2),[1,count]))
    return;
end
names = field_or(raw,'scope_channels',field_or(raw,'channel_names',{}));
if isempty(names)
    route = field_or(context,'route',struct());
    names = field_or(route,'scope_channels',{});
end
names = cellstr(string(names));
records = repmat(struct('channel','','samples',[], ...
    'time_axis_s',[],'sample_rate_hz',rate),1,count);
for k = 1:count
    if numel(names) == count
        records(k).channel = char(names{k});
    else
        records(k).channel = sprintf('通道%d',k);
    end
    records(k).samples = samples(:,k);
    if ~isempty(time), records(k).time_axis_s = time(:,min(k,size(time,2))); end
end
end

function indices = selected_channels(records,context,decoded)
indices = [];
route = field_or(context,'route',struct());
columns = field_or(route,'waveform_columns',[]);
channels = cellstr(string(field_or(route,'scope_channels',{})));
has_route = ~isempty(columns) && numel(columns) == numel(channels);
if ~has_route
    if numel(records) == 2, indices = [1 2]; end
    return;
end
pair = char(string(field_or(decoded,'payload_pair','')));
if isempty(pair) && numel(columns) == 2
    selected = 1:2;
else
    desired = [];
    if strcmpi(pair,'A'), desired = [1 2]; end
    if strcmpi(pair,'B'), desired = [3 4]; end
    if isempty(desired), return; end
    selected = zeros(1,2);
    for k = 1:2
        hit = find(columns == desired(k));
        if ~isscalar(hit), return; end
        selected(k) = hit;
    end
end
names = arrayfun(@(k) record_name(records(k),k),1:numel(records), ...
    'UniformOutput',false);
indices = zeros(1,2);
for k = 1:2
    hit = find(strcmpi(names,channels{selected(k)}));
    if ~isscalar(hit), indices = []; return; end
    indices(k) = hit;
end
end

function channel = matching_channel(channels,name)
channel = struct();
if ~isstruct(channels), return; end
names = arrayfun(@(k) record_name(channels(k),k),1:numel(channels), ...
    'UniformOutput',false);
hit = find(strcmpi(names,name));
if isscalar(hit), channel = channels(hit); end
end

function values = bandwidth_values(input)
values = [];
fields = {'bandwidth_limit_hz','bandwidth_hz','analog_bandwidth_hz'};
for k = 1:numel(fields)
    value = positive(field_or(input,fields{k},NaN));
    if isfinite(value), values(end+1) = value; end %#ok<AGROW>
end
end

function value = channel_impedance(record,channel)
% The bench default is a 50-ohm scope termination. Explicit 1 Mohm or
% another saved termination still takes precedence below.
value = 50;
fields = {'input_impedance_ohm','impedance_ohm','termination_ohm'};
sources = {record,channel};
for k = 1:numel(sources)
    candidates = [];
    for n = 1:numel(fields)
        candidate = positive(field_or(sources{k},fields{n},NaN));
        if isfinite(candidate), candidates(end+1) = candidate; end %#ok<AGROW>
    end
    if ~isempty(candidates)
        if all(abs(candidates-candidates(1)) <= 1e-9*candidates(1))
            value = candidates(1);
        end
        return;
    end
end
end

function limits = voltage_limits(record,channel,context,samples)
limits = [-1 1];
if ~isempty(samples) && isreal(samples)
    first = min(samples); last = max(samples);
    pad = max((last-first)*0.08,max(abs(samples))*0.02);
    if pad == 0, pad = 1e-3; end
    limits = [first-pad,last+pad];
end
vdiv = positive(field_or(record,'vertical_scale_v_per_div', ...
    field_or(channel,'vertical_scale_v_per_div',NaN)));
offset = number(field_or(record,'offset_v',field_or(channel,'offset_v',NaN)));
cfg = field_or(context,'cfg',struct());
scope_cfg = field_or(cfg,'scope',struct());
divisions = positive(field_or(scope_cfg,'vertical_divisions',8));
if isfinite(vdiv) && isfinite(offset) && isfinite(divisions)
    limits = -offset+[-1 1]*divisions*vdiv/2;
end
end

function value = record_name(record,index)
value = char(string(field_or(record,'channel',field_or(record,'name',''))));
if isempty(value), value = sprintf('通道%d',index); end
end

function value = positive(input)
value = number(input);
if value <= 0, value = NaN; end
end

function value = number(input)
value = NaN;
if isnumeric(input) && isscalar(input) && isreal(input) && isfinite(input)
    value = double(input);
end
end

function value = field_or(input,name,fallback)
value = fallback;
if isstruct(input) && isscalar(input) && isfield(input,name) && ~isempty(input.(name))
    value = input.(name);
end
end
