function raw = capture_scope(session, requested_channels)
%CAPTURE_SCOPE Read up to four LeCroy traces through the installed driver.

msiq.instruments.io_audit('record_capture', session.kind);
if session.mock
    fail_if_requested(session, 'capture');
    if isfield(session.specification, 'mock_capture')
        raw = session.specification.mock_capture;
        return;
    end
    error('msiq:instrument:MockCaptureMissing', ...
        'Mock scope requires specification.mock_capture.');
end
if isempty(session.device)
    error('msiq:instrument:ScopeDriver', ...
        'LeCroy driver session is unavailable.');
end
channels = cellstr(string(requested_channels));
group = get(session.device, 'Waveform');
msiq.instruments.write_scpi(session, 'STOP');
samples = cell(1, numel(channels));
times = cell(1, numel(channels));
for k = 1:numel(channels)
    driver_channel = lower(regexprep(channels{k}, '^C', 'channel'));
    [samples{k}, times{k}] = invoke(group, 'readwaveform', driver_channel);
end
count = min(cellfun(@numel, samples));
raw.samples = zeros(count, numel(channels));
raw.time_axes = zeros(count, numel(channels));
for k = 1:numel(channels)
    raw.samples(:,k) = samples{k}(1:count);
    raw.time_axes(:,k) = times{k}(1:count);
end
raw.sample_rate_hz = 1/median(diff(raw.time_axes(:,1)));
raw.full_scale = NaN;
msiq.instruments.write_scpi(session, 'TRMD AUTO');
end

function fail_if_requested(session, stage)
specification = session.specification;
if isfield(specification, 'fail_stage') && ...
        strcmpi(char(string(specification.fail_stage)), stage)
    error('msiq:instrument:MockCaptureFailure', ...
        'Injected mock failure at %s.', stage);
end
end
