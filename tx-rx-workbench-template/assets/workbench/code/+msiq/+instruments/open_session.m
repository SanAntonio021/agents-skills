function session = open_session(kind, specification, session_mode)
%OPEN_SESSION Open one owned VISA session or a test-only mock session.

if nargin < 3 || isempty(session_mode)
    session_mode = 'full';
end
kind = lower(char(string(kind)));
session_mode = lower(char(string(session_mode)));
if ~ismember(session_mode, {'full', 'query_only', 'raw'})
    error('msiq:instrument:SessionMode', ...
        'Unsupported session mode: %s.', session_mode);
end
msiq.instruments.io_audit('record_connection', kind);
if isfield(specification, 'mock') && logical(specification.mock)
    fail_if_requested(specification, ['connect_', kind]);
    if strcmp(kind, 'scope') && strcmp(session_mode, 'full')
        msiq.instruments.io_audit('increment', 'driver_initializations');
    end
    session = struct('kind', kind, 'mock', true, ...
        'mode', session_mode, 'specification', specification, ...
        'interface', [], 'device', []);
    return;
end
if ~isfield(specification, 'resource') || isempty(specification.resource)
    error('msiq:instrument:MissingResource', ...
        'Missing VISA resource for %s.', kind);
end

timeout_s = session_timeout(specification);
interface = [];
device = [];
try
    interface = visa('KEYSIGHT', char(string(specification.resource)));
    % Bound both the initial open and subsequent VISA I/O. Without this,
    % an unreachable scope can leave the MATLAB GUI in a permanent wait.
    interface.Timeout = timeout_s;
    if strcmp(kind, 'awg')
        % One external-memory waveform can exceed the legacy VISA 512-byte default.
        interface.OutputBufferSize = 4*1024*1024;
    elseif strcmp(kind, 'scope')
        % LeCroy DAT1 replies carry the complete WAVEFORM block in one read.
        % This must be set before fopen; legacy VISA otherwise defaults to 512 B.
        interface.InputBufferSize = 64*1024*1024;
    end
    fopen(interface);
    if strcmp(kind, 'scope') && strcmp(session_mode, 'full')
        msiq.instruments.io_audit('increment', 'driver_initializations');
        device = icdevice('lecroy_8600a.mdd', interface);
        connect(device);
    end
catch exception
    if ~isempty(device)
        try disconnect(device); catch, end
        try delete(device); catch, end
    end
    if ~isempty(interface)
        try fclose(interface); catch, end
        try delete(interface); catch, end
    end
    rethrow(exception);
end
session = struct('kind', kind, 'mock', false, ...
    'mode', session_mode, 'specification', specification, ...
    'interface', interface, 'device', device, 'timeout_s', timeout_s);
end

function timeout_s = session_timeout(specification)
% Keep hardware entry points responsive when a configured resource is offline.
timeout_s = 3;
if isfield(specification, 'timeout_s') && ~isempty(specification.timeout_s)
    value = double(specification.timeout_s);
    if ~isscalar(value) || ~isfinite(value) || value <= 0
        error('msiq:instrument:Timeout', ...
            'timeout_s must be a positive finite scalar.');
    end
    timeout_s = value;
end
end

function fail_if_requested(specification, stage)
if isfield(specification, 'fail_stage') && ...
        strcmpi(char(string(specification.fail_stage)), stage)
    error('msiq:instrument:MockFailure', ...
        'Injected mock failure at %s.', stage);
end
end
