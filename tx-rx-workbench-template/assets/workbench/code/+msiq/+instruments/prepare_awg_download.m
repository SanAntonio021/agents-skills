function prepared = prepare_awg_download(source_data, awg_channels, ...
        waveform_columns, granularity_samples)
%PREPARE_AWG_DOWNLOAD Build the exact per-channel payload sent to the AWG.

if nargin < 4 || isempty(granularity_samples)
    granularity_samples = 128;
end
channels = double(awg_channels(:).');
columns = double(waveform_columns(:).');
validateattributes(channels, {'numeric'}, ...
    {'vector','integer','>=',1,'<=',4});
validateattributes(columns, {'numeric'}, {'vector','integer','>=',1});
validateattributes(granularity_samples, {'numeric'}, ...
    {'scalar','integer','positive','finite'});
if numel(channels) ~= numel(columns) || numel(unique(channels)) ~= numel(channels)
    error('msiq:instrument:AwgDownloadMapping', ...
        'AWG channels and waveform columns need a one-to-one mapping.');
end

channel_data = cell(1, numel(channels));
source_counts = zeros(1, numel(channels));
final_counts = zeros(1, numel(channels));
for index = 1:numel(channels)
    samples = waveform_column(source_data, columns(index));
    samples = double(samples(:));
    if isempty(samples) || any(~isfinite(samples)) || max(abs(samples)) > 1+1e-12
        error('msiq:instrument:AwgWaveformRange', ...
            'CH%d waveform is empty, nonfinite, or outside [-1, 1].', ...
            channels(index));
    end
    samples = min(max(samples, -1), 1);
    source_counts(index) = numel(samples);
    final_counts(index) = ceil(numel(samples)/granularity_samples)* ...
        granularity_samples;
    if final_counts(index) > numel(samples)
        samples(end+1:final_counts(index), 1) = 0;
    end
    channel_data{index} = samples;
end

prepared = struct('channels', channels, 'waveform_columns', columns, ...
    'granularity_samples', double(granularity_samples), ...
    'source_sample_counts', source_counts, ...
    'final_sample_counts', final_counts, ...
    'channel_data', {channel_data});
end

function samples = waveform_column(source_data, column)
if iscell(source_data)
    if column > numel(source_data)
        error('msiq:instrument:AwgDownloadColumn', ...
            'Waveform column %d is unavailable.', column);
    end
    samples = source_data{column};
elseif isnumeric(source_data) && ismatrix(source_data)
    if column > size(source_data, 2)
        error('msiq:instrument:AwgDownloadColumn', ...
            'Waveform column %d is unavailable.', column);
    end
    samples = source_data(:, column);
else
    error('msiq:instrument:AwgDownloadData', ...
        'AWG waveform data must be a numeric matrix or a cell array.');
end
end
