function preprocessing = read_scope_preprocessing(session, channels)
%READ_SCOPE_PREPROCESSING Read LeCroy preprocessing properties per channel.
%
% LeCroy exposes these properties below app.Acquisition.<channel>.  Some
% firmware builds omit one or more properties; this helper therefore keeps
% the raw response and reports partial/unavailable status instead of making
% a read-only scope status call fail.

if nargin < 2 || isempty(channels)
    channels = {'C1', 'C2'};
end
channels = cellstr(string(channels));

records = repmat(empty_record(), 1, numel(channels));
all_warnings = {};
for k = 1:numel(channels)
    channel = normalize_channel(channels{k});
    record = empty_record();
    record.channel = channel;
    record.source = 'channel_vbs';

    [record.interpolation, record.raw.interpolation, ok, warning_text] = ...
        query_text_property(session, channel, 'InterpolateType');
    record.valid.interpolation = ok;
    record.warnings = append_warning(record.warnings, warning_text);

    [record.average_sweeps, record.raw.average_sweeps, ok, warning_text] = ...
        query_numeric_property(session, channel, 'AverageSweeps');
    record.valid.average_sweeps = ok;
    record.warnings = append_warning(record.warnings, warning_text);

    [record.enhance_resolution, record.raw.enhance_resolution, ok, warning_text] = ...
        query_text_property(session, channel, 'EnhanceResType');
    record.valid.enhance_resolution = ok;
    record.warnings = append_warning(record.warnings, warning_text);

    [record.optimize_group_delay, record.raw.optimize_group_delay, ok, warning_text] = ...
        query_text_property(session, channel, 'OptimizeGroupDelay');
    record.valid.optimize_group_delay = ok;
    record.warnings = append_warning(record.warnings, warning_text);

    valid_count = double(record.valid.interpolation) + ...
        double(record.valid.average_sweeps) + ...
        double(record.valid.enhance_resolution) + ...
        double(record.valid.optimize_group_delay);
    if valid_count == 4
        record.status = 'ok';
    elseif valid_count == 0
        record.status = 'unavailable';
    else
        record.status = 'partial';
    end
    records(k) = record;
    all_warnings = [all_warnings, record.warnings]; %#ok<AGROW>
end

statuses = {records.status};
if isempty(records) || all(strcmp(statuses, 'unavailable'))
    overall_status = 'unavailable';
elseif all(strcmp(statuses, 'ok'))
    overall_status = 'ok';
else
    overall_status = 'partial';
end

preprocessing = struct( ...
    'status', overall_status, ...
    'source', 'channel_vbs', ...
    'channels', records, ...
    'warnings', {all_warnings}, ...
    'interpolation', aggregate_text(records, 'interpolation'), ...
    'average_sweeps', aggregate_numeric(records, 'average_sweeps'), ...
    'enhance_resolution', aggregate_text(records, 'enhance_resolution'), ...
    'optimize_group_delay', aggregate_text(records, 'optimize_group_delay'));
end

function record = empty_record()
record = struct('channel', '', 'status', 'unavailable', 'source', '', ...
    'interpolation', '', 'average_sweeps', NaN, ...
    'enhance_resolution', '', 'optimize_group_delay', '', ...
    'raw', struct('interpolation', '', 'average_sweeps', '', ...
        'enhance_resolution', '', 'optimize_group_delay', ''), ...
    'valid', struct('interpolation', false, 'average_sweeps', false, ...
        'enhance_resolution', false, 'optimize_group_delay', false), ...
    'warnings', {{}});
end

function channel = normalize_channel(channel)
channel = upper(strtrim(char(string(channel))));
channel = regexprep(channel, '^CHANNEL\s*', 'C');
channel = regexprep(channel, '^CH\s*', 'C');
if isempty(regexp(channel, '^C[1-4]$', 'once'))
    error('msiq:instrument:ScopeChannel', ...
        'Unsupported LeCroy channel: %s.', channel);
end
end

function [value, raw, ok, warning_text] = query_text_property(session, channel, property)
[raw, warning_text] = query_property(session, channel, property);
value = normalize_vbs_text(raw);
ok = ~isempty(value);
if ~ok && isempty(warning_text)
    warning_text = sprintf('%s.%s unavailable.', channel, property);
end
end

function [value, raw, ok, warning_text] = query_numeric_property(session, channel, property)
[raw, warning_text] = query_property(session, channel, property);
value = parse_number(raw);
ok = isfinite(value);
if ~ok && isempty(warning_text)
    warning_text = sprintf('%s.%s unavailable.', channel, property);
end
end

function [raw, warning_text] = query_property(session, channel, property)
command = sprintf('VBS? ''return=app.Acquisition.%s.%s''', channel, property);
try
    raw = strtrim(char(string(msiq.instruments.query_scpi(session, command))));
catch exception
    raw = ['QUERY_FAILED:', exception.identifier];
    warning_text = sprintf('%s.%s query failed (%s).', ...
        channel, property, exception.identifier);
    return;
end
warning_text = '';
if is_vbs_error(raw)
    warning_text = sprintf('%s.%s unavailable: %s', channel, property, raw);
end
end

function value = normalize_vbs_text(raw)
value = strtrim(char(string(raw)));
value = regexprep(value, '^.*return\s*=\s*', '', 'ignorecase');
value = strrep(value, '"', '');
if is_vbs_error(value) || starts_with_query_failure(value)
    value = '';
end
end

function value = parse_number(raw)
raw = normalize_vbs_text(raw);
token = regexp(raw, '[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', ...
    'match', 'once');
if isempty(token)
    value = NaN;
else
    value = str2double(token);
end
end

function tf = is_vbs_error(raw)
text = upper(strtrim(char(string(raw))));
tf = contains(text, 'OBJECT DOES NOT SUPPORT') || ...
    contains(text, 'PROPERTY OR METHOD') || ...
    contains(text, 'UNKNOWN PROPERTY') || ...
    contains(text, 'INVALID PROPERTY');
end

function tf = starts_with_query_failure(raw)
tf = strncmpi(strtrim(char(string(raw))), 'QUERY_FAILED:', 13);
end

function warnings = append_warning(warnings, warning_text)
if isempty(warning_text)
    return;
end
warnings{end+1} = warning_text;
end

function value = aggregate_text(records, field)
values = {};
for k = 1:numel(records)
    candidate = strtrim(char(string(records(k).(field))));
    if ~isempty(candidate)
        values{end+1} = candidate; %#ok<AGROW>
    end
end
if isempty(values)
    value = 'unavailable';
elseif all(strcmpi(values, values{1}))
    value = values{1};
else
    value = 'per_channel';
end
end

function value = aggregate_numeric(records, field)
values = arrayfun(@(record) double(record.(field)), records);
values = values(isfinite(values));
if isempty(values)
    value = NaN;
elseif all(abs(values - values(1)) <= max(1e-12, abs(values(1))*1e-9))
    value = values(1);
else
    value = NaN;
end
end
