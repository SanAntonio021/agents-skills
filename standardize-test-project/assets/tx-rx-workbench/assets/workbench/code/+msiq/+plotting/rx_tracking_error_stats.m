function stats = rx_tracking_error_stats(tracking, frame, cfg, window_size_symbols)
%RX_TRACKING_ERROR_STATS Disjoint windows of recorded, accepted update errors.
if nargin < 4, window_size_symbols = 513; end
if nargin < 3, cfg = struct(); end
validateattributes(window_size_symbols,{'numeric'},{'scalar','integer','positive'});
stats = struct('available',false,'reason','未保存联合跟踪误差', ...
    'updated_count',0,'initial_wait_count',NaN,'eligible_count',NaN, ...
    'rejected_count',NaN,'rejected_fraction',NaN,'rejection_visible',false, ...
    'window_size_symbols',window_size_symbols,'window_counts',zeros(0,1), ...
    'window_rms',zeros(0,1),'window_peak',zeros(0,1), ...
    'window_peak_time_us',zeros(0,1),'window_time_us',zeros(0,1), ...
    'window_duration_us',NaN,'window_actual_symbols',zeros(0,1), ...
    'error_energy',0,'duration_us',NaN,'count_consistent',true);
if isfield(tracking,'enabled') && ~tracking.enabled
    stats.reason = '联合跟踪未启用'; return;
end
errors = abs(double(get_value(tracking,'error_log',[])));
errors = errors(:); n = numel(errors);
if n == 0, return; end
waveform = get_value(cfg,'waveform',struct());
rate = get_value(frame,'symbol_rate_hz',get_value(waveform,'symbol_rate_hz',NaN));
if ~isscalar(rate) || ~isfinite(rate) || rate <= 0
    stats.reason = '缺少业务区时间标定'; return;
end
recorded = isfinite(errors);
stats.updated_count = nnz(recorded);
stats.error_energy = sum(errors(recorded).^2);
stats.duration_us = n/rate*1e6;
stats.window_duration_us = window_size_symbols/rate*1e6;
reported_updates = get_value(tracking,'update_count',stats.updated_count);
stats.count_consistent = isequal(double(reported_updates),double(stats.updated_count));
rejected = get_value(tracking,'rejected_count',NaN);
if isscalar(rejected) && isfinite(rejected) && rejected >= 0 && rejected == fix(rejected)
    stats.rejected_count = rejected;
    stats.rejection_visible = rejected > 0;
end
receiver = get_value(cfg,'receiver',struct());
acquire = get_value(tracking,'pilot_acquire_count', ...
    get_value(receiver,'track_pilot_acquire_count',NaN));
positions = get_value(frame,'pilot_positions_service',[]);
positions = double(positions(:));
if isscalar(acquire) && isfinite(acquire) && acquire >= 0 && ...
        isfield(frame,'pilot_positions_service') && ...
        all(isfinite(positions) & positions>=1 & positions<=n & positions==fix(positions))
    pilot = false(n,1); pilot(positions) = true;
    valid_position = true(n,1);
    phase = get_value(tracking,'phase_log',[]);
    if numel(phase) == n, valid_position = isfinite(phase(:)); end
    acquired = cumsum(pilot) >= acquire;
    waiting = valid_position & ~recorded & ~pilot & ~acquired;
    eligible = valid_position & ~pilot & acquired;
    stats.initial_wait_count = nnz(waiting);
    stats.eligible_count = nnz(eligible);
    inferred_rejected = nnz(eligible & ~recorded);
    if isfinite(stats.rejected_count)
        stats.count_consistent = stats.count_consistent && inferred_rejected==rejected;
        if stats.eligible_count > 0 && inferred_rejected==rejected
            stats.rejected_fraction = rejected/stats.eligible_count;
        elseif rejected==0 && stats.eligible_count==0
            stats.rejected_fraction = 0;
        end
    end
end
if ~any(recorded)
    stats.reason = '没有参与更新的有效误差'; return;
end
starts = (1:window_size_symbols:n).'; count = numel(starts);
stats.window_counts = zeros(count,1);
stats.window_actual_symbols = zeros(count,1);
stats.window_rms = nan(count,1); stats.window_peak = nan(count,1);
stats.window_time_us = nan(count,1); stats.window_peak_time_us = nan(count,1);
for k = 1:count
    last = min(n,starts(k)+window_size_symbols-1);
    indices = (starts(k):last).';
    stats.window_actual_symbols(k) = numel(indices);
    stats.window_time_us(k) = ((starts(k)+last)/2-1)/rate*1e6;
    indices = indices(recorded(indices));
    stats.window_counts(k) = numel(indices);
    if isempty(indices), continue; end
    values = errors(indices);
    stats.window_rms(k) = sqrt(mean(values.^2));
    [stats.window_peak(k), peak] = max(values);
    stats.window_peak_time_us(k) = (indices(peak)-1)/rate*1e6;
end
assert(sum(stats.window_counts)==stats.updated_count);
energy = sum(stats.window_rms.^2.*stats.window_counts,'omitnan');
assert(abs(energy-stats.error_energy)<=1e-10*max(1,stats.error_energy));
assert(max(stats.window_peak)==max(errors(recorded)));
stats.available = true; stats.reason = '';
end

function value = get_value(value,name,fallback)
if isstruct(value) && isscalar(value) && isfield(value,name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end
