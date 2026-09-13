function spectrum = Test_Project_Compute_PSD(samples, fs_hz, options)
%TEST_PROJECT_COMPUTE_PSD Deterministic Welch PSD, without display decimation.
% Linear density has units of squared input units/Hz. Complex data are never
% doubled. Segment starts are saved as MATLAB one-based sample indices.
if nargin < 3, options = struct(); end
spectrum = struct('frequency_hz', [], 'density_linear', [], 'fs_hz', fs_hz, ...
    'df_hz', NaN, 'window_name', 'periodic Hann', 'window_length', NaN, ...
    'overlap_fraction', NaN, 'overlap_samples', NaN, 'max_segments', NaN, ...
    'segment_starts', [], 'segment_count', 0, 'remove_mean', false, ...
    'sidedness', '', 'available_limit_hz', NaN, 'status', 'failed', 'reason', '');
if ~isnumeric(samples) || ~isvector(samples) || numel(samples) < 2 || any(~isfinite(samples(:)))
    spectrum.reason = 'Samples must be a finite numeric vector with at least two samples.'; return
end
if ~isnumeric(fs_hz) || ~isscalar(fs_hz) || ~isreal(fs_hz) || ~isfinite(fs_hz) || fs_hz <= 0
    spectrum.reason = 'A finite positive sample rate is required.'; return
end
if ~isstruct(options) || ~isscalar(options)
    spectrum.reason = 'Options must be a scalar struct.'; return
end
samples = double(samples(:)); n = numel(samples);
lengthWindow = option(options, 'window_length', []);
if isempty(lengthWindow), lengthWindow = 2^floor(log2(min(n,65536))); end
overlap = option(options, 'overlap_fraction', .5);
maxSegments = option(options, 'max_segments', 8);
removeMean = option(options, 'remove_mean', false);
sidedness = option(options, 'sidedness', 'auto');
if ~ischar(sidedness) || ~ismember(sidedness,{'auto','one-sided','centered-two-sided'})
    spectrum.reason = 'sidedness must be auto, one-sided or centered-two-sided.'; return
end
if strcmp(sidedness,'one-sided') && ~isreal(samples)
    spectrum.reason = 'A one-sided PSD cannot represent complex samples.'; return
end
if ~isscalar(lengthWindow) || ~isfinite(lengthWindow) || lengthWindow < 2 || lengthWindow > n || fix(lengthWindow) ~= lengthWindow
    spectrum.reason = 'window_length must be an integer between 2 and the record length.'; return
end
if ~isscalar(overlap) || ~isfinite(overlap) || overlap < 0 || overlap >= 1
    spectrum.reason = 'overlap_fraction must be in [0,1).'; return
end
if ~isscalar(maxSegments) || isnan(maxSegments) || maxSegments < 1 || (~isinf(maxSegments) && fix(maxSegments) ~= maxSegments)
    spectrum.reason = 'max_segments must be a positive integer or Inf.'; return
end
if ~isscalar(removeMean) || ~(islogical(removeMean) || (isnumeric(removeMean) && ismember(removeMean,[0,1])))
    spectrum.reason = 'remove_mean must be a logical scalar.'; return
end
overlapSamples = floor(lengthWindow*overlap);
allStarts = 1:(lengthWindow-overlapSamples):(n-lengthWindow+1);
if numel(allStarts) > maxSegments
    starts = allStarts(unique(round(linspace(1,numel(allStarts),maxSegments))));
else
    starts = allStarts;
end
window = .5-.5*cos(2*pi*(0:lengthWindow-1)'/lengthWindow);
density = zeros(lengthWindow,1);
for first = starts
    segment = samples(first:first+lengthWindow-1);
    if removeMean, segment = segment-mean(segment); end
    density = density + abs(fft(segment.*window)).^2 / (fs_hz*sum(window.^2));
end
density = density/numel(starts);
if isreal(samples) && ~strcmp(sidedness,'centered-two-sided')
    density = density(1:floor(lengthWindow/2)+1);
    if rem(lengthWindow,2) == 0
        density(2:end-1) = 2*density(2:end-1);
    else
        density(2:end) = 2*density(2:end);
    end
    frequency = (0:floor(lengthWindow/2))'*(fs_hz/lengthWindow);
    spectrum.sidedness = 'one-sided';
else
    density = fftshift(density);
    frequency = (-floor(lengthWindow/2):ceil(lengthWindow/2)-1)'*(fs_hz/lengthWindow);
    spectrum.sidedness = 'centered-two-sided';
end
spectrum.frequency_hz = frequency;
spectrum.density_linear = density;
spectrum.df_hz = fs_hz/lengthWindow;
spectrum.window_length = lengthWindow;
spectrum.overlap_fraction = overlap;
spectrum.overlap_samples = overlapSamples;
spectrum.max_segments = maxSegments;
spectrum.segment_starts = starts;
spectrum.segment_count = numel(starts);
spectrum.remove_mean = logical(removeMean);
spectrum.available_limit_hz = fs_hz/2;
spectrum.status = 'ok';
end

function value = option(options,name,fallback)
if isfield(options,name), value = options.(name); else, value = fallback; end
end
