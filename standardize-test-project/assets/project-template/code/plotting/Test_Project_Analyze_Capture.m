function analysis = Test_Project_Analyze_Capture(channels, options)
%TEST_PROJECT_ANALYZE_CAPTURE Preserve raw voltage data and analyze each channel.
% A waveform can remain inspectable when its time grid cannot support a PSD.
if nargin < 2, options = struct(); end
if ~isstruct(channels) || ~isstruct(options) || ~isscalar(options)
    error('TestProject:CaptureInput','channels and options must be structs.');
end
result = repmat(channelTemplate(),size(channels));
for k = 1:numel(channels)
    input = channels(k); current = channelTemplate();
    for field = {'id','role'}
        name = field{1};
        if ~isfield(input,name) || ~(ischar(input.(name)) || (isstring(input.(name)) && isscalar(input.(name)))) || isempty(strtrim(char(input.(name)))) || ~isrow(char(input.(name)))
            error('TestProject:ChannelIdentity','Each channel requires a nonempty id and role.');
        end
        current.(name) = char(input.(name));
    end
    if ~ismember(current.role,{'signal','I','Q'})
        error('TestProject:ChannelRole','Channel role must be signal, I or Q.');
    end
    if k > 1 && any(strcmp(current.id,{result(1:k-1).id}))
        error('TestProject:DuplicateChannelId','Channel ids must be unique.');
    end
    current.impedance_ohm = getOption(input,'impedance_ohm',NaN);
    current.bandwidth_hz = getOption(input,'bandwidth_hz',NaN);
    current.sync_verified = isequal(getOption(input,'sync_verified',false),true);
    [current.waveform.voltage_limits_v, voltageReason] = validatedLimits(input,'voltage_limits_v');
    [current.waveform.time_limits_s, limitTimeReason] = validatedLimits(input,'time_limits_s');
    if ~isempty(current.waveform.voltage_limits_v), current.waveform.voltage_limits_source = 'scope'; end
    limitsReason = strtrim(strjoin({voltageReason,limitTimeReason},' '));
    if ~isfield(input,'samples') || ~isnumeric(input.samples) || ~isreal(input.samples) || ~iscolumn(input.samples) || isempty(input.samples)
        current.waveform.reason = 'Raw samples must be a nonempty real numeric column vector in volts.';
        current.spectrum.reason = current.waveform.reason; result(k) = current; continue
    end
    samples = double(input.samples); n = numel(samples);
    current.waveform.samples_v = samples;
    current.stats.sample_count = n;
    [time,fs,timeReason,timeSource] = resolveTime(input,n);
    current.waveform.time_s = time;
    current.waveform.source = timeSource;
    current.waveform.status = 'ok';
    if ~isempty(limitsReason)
        current.waveform.status = 'failed';
        current.waveform.reason = limitsReason;
    end
    if any(~isfinite(samples))
        current.waveform.status = 'failed';
        current.waveform.reason = strtrim([current.waveform.reason ' Raw samples contain NaN or Inf; samples have been preserved.']);
    else
        current.stats.rms_v = sqrt(mean(samples.^2));
        current.stats.vpp_v = max(samples)-min(samples);
    end
    if ~isempty(timeReason)
        current.spectrum.reason = timeReason;
        current.waveform.reason = strtrim([current.waveform.reason ' ' timeReason]);
        result(k) = current; continue
    end
    psd = Test_Project_Compute_PSD(samples,fs,options);
    names = fieldnames(psd);
    for j = 1:numel(names), current.spectrum.(names{j}) = psd.(names{j}); end
    current.spectrum.density_v2_hz = psd.density_linear;
    current.spectrum.density_unit = 'V^2/Hz';
    if ~strcmp(psd.status,'ok'), result(k) = current; continue; end
    if isnumeric(current.bandwidth_hz) && isreal(current.bandwidth_hz) && isscalar(current.bandwidth_hz) && isfinite(current.bandwidth_hz) && current.bandwidth_hz > 0
        current.spectrum.available_limit_hz = min(fs/2,current.bandwidth_hz);
        current.spectrum.bandwidth_known = true;
    end
    if isscalar(current.impedance_ohm) && isfinite(current.impedance_ohm) && current.impedance_ohm > 0
        current.spectrum.density_w_hz = psd.density_linear/current.impedance_ohm;
    end
    band = getOption(options,'power_band_hz',[]);
    current.spectrum.power_band_hz = band;
    if isempty(band)
        current.spectrum.power_reason = 'No integration band requested.';
    elseif ~isnumeric(band) || ~isreal(band) || numel(band) ~= 2 || any(~isfinite(band)) || band(1) > band(2)
        current.spectrum.power_status = 'failed';
        current.spectrum.power_reason = 'power_band_hz must contain two ordered finite bounds.';
    elseif band(1) < 0 || band(2) > current.spectrum.available_limit_hz
        current.spectrum.power_status = 'failed';
        current.spectrum.power_reason = 'Requested band extends beyond the usable frequency range.';
    else
        selected = psd.frequency_hz >= band(1) & psd.frequency_hz <= band(2);
        if ~any(selected)
            current.spectrum.power_status = 'failed';
            current.spectrum.power_reason = 'Requested band contains no frequency bins.';
        else
            bins = psd.frequency_hz(selected);
            current.spectrum.actual_power_band_hz = [bins(1),bins(end)];
            current.spectrum.band_bin_count = numel(bins);
            current.spectrum.band_voltage_v2 = sum(psd.density_linear(selected))*psd.df_hz;
            if ~isempty(current.spectrum.density_w_hz)
                current.spectrum.band_power_w = sum(current.spectrum.density_w_hz(selected))*psd.df_hz;
            end
            current.spectrum.power_status = 'ok';
            current.spectrum.power_reason = '';
        end
    end
    result(k) = current;
end
analysis = struct('channels',result,'options',options);
end

function current = channelTemplate()
current = struct('id','','role','','waveform',struct('time_s',[], ...
    'samples_v',[],'voltage_limits_v',[],'time_limits_s',[],'voltage_limits_source','data_adapted', ...
    'source','','status','failed','reason',''), ...
    'stats',struct('rms_v',NaN,'vpp_v',NaN,'sample_count',0), ...
    'spectrum',emptySpectrum(),'sync_verified',false,'impedance_ohm',NaN,'bandwidth_hz',NaN);
end

function value = emptySpectrum()
value = Test_Project_Compute_PSD([],NaN);
value.reason = '';
value.density_v2_hz = []; value.density_w_hz = []; value.density_unit = 'V^2/Hz';
value.power_band_hz = []; value.actual_power_band_hz = [];
value.band_bin_count = 0; value.band_power_w = NaN; value.band_voltage_v2 = NaN;
value.power_status = 'skipped'; value.power_reason = 'Spectrum unavailable.';
value.bandwidth_known = false;
end

function [time,fs,reason,source] = resolveTime(input,n)
time = []; fs = NaN; reason = ''; source = '';
if isfield(input,'time_s') && ~isempty(input.time_s)
    time = input.time_s(:); source = 'time_s';
    if ~isnumeric(time) || ~isreal(time) || numel(time) ~= n || n < 2 || any(~isfinite(time))
        reason = 'time_s must be a finite real vector matching samples, with at least two points.'; return
    end
    delta = diff(double(time)); interval = median(delta);
    if interval <= 0 || any(delta <= 0) || any(abs(delta-interval) > abs(interval)*1e-6)
        reason = 'time_s must increase uniformly (relative interval tolerance 1e-6).'; return
    end
    fs = 1/interval;
    if isfield(input,'fs_hz') && ~isempty(input.fs_hz)
        candidate = input.fs_hz;
        if ~isnumeric(candidate) || ~isreal(candidate) || ~isscalar(candidate) || ~isfinite(candidate) || candidate <= 0 || abs(candidate-fs)/fs > 1e-6
            reason = 'Sampling source conflict: explicit fs_hz disagrees with time_s (relative tolerance 1e-6).'; return
        end
    end
else
    candidate = getOption(input,'fs_hz',NaN);
    provenance = getOption(input,'fs_source','');
    if ~isnumeric(candidate) || ~isreal(candidate) || ~isscalar(candidate) || ~isfinite(candidate) || candidate <= 0 || ...
            ~(ischar(provenance) || (isstring(provenance) && isscalar(provenance))) || isempty(strtrim(char(provenance)))
        reason = 'Missing trustworthy timing: provide time_s or positive fs_hz with fs_source.'; return
    end
    fs = candidate; time = (0:n-1)'/fs; source = char(provenance);
end
end

function [limits,reason] = validatedLimits(input,name)
limits = getOption(input,name,[]); reason = '';
if isempty(limits), return; end
if ~isnumeric(limits) || ~isreal(limits) || ~isvector(limits) || numel(limits) ~= 2 || any(~isfinite(limits)) || limits(1) >= limits(2)
    limits = [];
    reason = [name ' must be a finite strictly increasing two-element vector; invalid limits were rejected.'];
else
    limits = double(limits(:)');
end
end

function value = getOption(input,name,fallback)
if isfield(input,name), value = input.(name); else, value = fallback; end
end
