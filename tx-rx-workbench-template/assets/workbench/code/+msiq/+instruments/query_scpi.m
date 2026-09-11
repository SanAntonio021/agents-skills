function response = query_scpi(session, command)
%QUERY_SCPI Execute one read-only query.

msiq.instruments.io_audit('record_query', session.kind);
if session.mock
    fail_if_requested(session, 'query');
    output_token = regexp(char(string(command)), ...
        '^\s*:OUTPut\s*([1-4])\?\s*$', 'tokens', 'once', 'ignorecase');
    scope_scale_query = contains(char(string(command)), '.VerScale', ...
        'IgnoreCase', true);
    scope_sample_rate_query = contains(char(string(command)), ...
        'app.Acquisition.Horizontal.SampleRate', 'IgnoreCase', true);
    scope_preprocessing_query = regexp(char(string(command)), ...
        'app\.Acquisition\.(C[1-4])\.(InterpolateType|AverageSweeps|EnhanceResType|OptimizeGroupDelay)', ...
        'tokens', 'once', 'ignorecase');
    if isfield(session.specification, 'mock_idn') && ...
            strcmpi(strtrim(char(string(command))), '*IDN?')
        response = char(string(session.specification.mock_idn));
    elseif strcmpi(session.kind, 'awg') && ...
            strcmpi(strtrim(char(string(command))), '*OPT?') && ...
            isfield(session.specification, 'mock_options_query_failure') && ...
            logical(session.specification.mock_options_query_failure)
        error('msiq:instrument:MockOptionQueryFailure', ...
            'Injected mock *OPT? failure.');
    elseif strcmpi(session.kind, 'awg') && ~isempty(output_token)
        if isfield(session.specification,'mock_fail_readback_after_binary_writes')
            audit = msiq.instruments.get_audit();
            if audit.binary_writes >= session.specification.mock_fail_readback_after_binary_writes
                error('msiq:instrument:MockReadbackFailure', ...
                    'Injected output readback failure after waveform transfer.');
            end
        end
        fail_if_requested(session, 'readback');
        channel = str2double(output_token{1});
        response = char(string(double(msiq.instruments.io_audit( ...
            'get_awg_output', channel))));
    elseif strcmpi(session.kind, 'awg')
        [response, handled] = msiq.instruments.io_audit( ...
            'mock_awg_query', char(string(command)));
        if handled
            return;
        end
    elseif strcmpi(session.kind, 'scope') && scope_scale_query && ...
            isfield(session.specification, 'mock_vertical_scale_v_per_div')
        fail_if_requested(session, 'readback');
        response = char(string( ...
            session.specification.mock_vertical_scale_v_per_div));
    elseif strcmpi(session.kind, 'scope') && scope_sample_rate_query && ...
            isfield(session.specification, 'mock_horizontal_sample_rate_hz')
        fail_if_requested(session, 'readback');
        response = char(string( ...
            session.specification.mock_horizontal_sample_rate_hz));
    elseif strcmpi(session.kind, 'scope') && ~isempty(scope_preprocessing_query)
        [response, handled] = mock_scope_preprocessing_query( ...
            session.specification, scope_preprocessing_query);
        if handled
            fail_if_requested(session, 'readback');
            return;
        end
    else
        response = ['MOCK,', upper(session.kind), ',0,2.0'];
    end
    return;
end
response = strtrim(query(session.interface, char(string(command))));
end

function [response, handled] = mock_scope_preprocessing_query(specification, tokens)
response = '';
handled = false;
if ~isfield(specification, 'mock_scope_preprocessing') || ...
        ~isstruct(specification.mock_scope_preprocessing)
    return;
end

channel = char(tokens{1});
property = char(tokens{2});
data = get_case_insensitive_field( ...
    specification.mock_scope_preprocessing, channel, []);
if ~isstruct(data)
    response = sprintf('Object doesn''t support this property or method: ''app.Acquisition.%s.%s''', ...
        channel, property);
    handled = true;
    return;
end

switch lower(property)
    case 'interpolatetype'
        field = 'interpolation';
    case 'averagesweeps'
        field = 'average_sweeps';
    case 'enhancerestype'
        field = 'enhance_resolution';
    case 'optimizegroupdelay'
        field = 'optimize_group_delay';
    otherwise
        return;
end

value = get_case_insensitive_field(data, field, []);
if isempty(value)
    response = sprintf('Object doesn''t support this property or method: ''app.Acquisition.%s.%s''', ...
        channel, property);
else
    response = char(string(value));
end
handled = true;
end

function value = get_case_insensitive_field(structure, requested, default_value)
value = default_value;
fields = fieldnames(structure);
index = find(strcmpi(fields, requested), 1, 'first');
if ~isempty(index)
    value = structure.(fields{index});
end
end

function fail_if_requested(session, stage)
specification = session.specification;
if isfield(specification, 'fail_stage') && ...
        strcmpi(char(string(specification.fail_stage)), stage)
    identifier = 'msiq:instrument:MockFailure';
    if strcmpi(stage, 'readback')
        identifier = 'msiq:instrument:MockReadbackFailure';
    end
    error(identifier, ...
        'Injected mock failure at %s.', stage);
end
end
