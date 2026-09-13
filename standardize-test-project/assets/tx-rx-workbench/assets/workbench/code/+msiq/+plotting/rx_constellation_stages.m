function [stages, info] = rx_constellation_stages(raw, context, decoded)
%RX_CONSTELLATION_STAGES Matched payload observations with verified legacy replay.
stages = {[], [], [], []};
info = struct('stage_available',false(1,4), ...
    'stage_symbol_counts',zeros(1,4), ...
    'stage_reasons',{{'缺少均衡前业务样点','缺少固定均衡结果', ...
    '缺少联合跟踪结果','缺少最终导频校正结果'}}, ...
    'stage_sources',{{'unavailable','unavailable','unavailable','unavailable'}}, ...
    'payload_positions_service',[], 'additional_display_normalization',false, ...
    'time_us',[], 'time_available',false, 'time_reason','缺少采集时间映射信息', ...
    'time_mapping',struct(), 'replay',struct('attempted',false,'ok',false,'reason',''));
if ~isstruct(decoded) || ~isfield(decoded,'primary_equalizer') || ...
        ~isfield(decoded,'primary_streams') || isempty(decoded.primary_streams)
    return;
end
try
    frame = context.tx_ref.frame;
    positions = double(frame.payload_positions_service(:));
    require(~isempty(positions) && all(isfinite(positions)) && ...
        all(positions >= 1 & positions <= frame.service_length) && ...
        all(positions == round(positions)) && numel(unique(positions)) == numel(positions), ...
        '业务符号位置无效');
    if isfield(frame,'pilot_positions_service')
        require(isempty(intersect(positions,frame.pilot_positions_service)), ...
            '业务符号位置包含导频');
    end
catch exception
    info.stage_reasons(:) = {['缺少有效帧位置：',exception.message]};
    return;
end
info.payload_positions_service = positions;
eq = decoded.primary_equalizer;
stream = decoded.primary_streams(1);
fields = {'service_symbols_before_equalization', ...
    'service_symbols_before_tracking','service_symbols_after_tracking'};
for k = 1:3
    if isfield(eq,fields{k}) && numel(eq.(fields{k})) == frame.service_length
        values = eq.(fields{k});
        stages{k} = values(positions);
        stages{k} = stages{k}(:);
        info.stage_sources{k} = ['saved.',fields{k}];
        info.stage_reasons{k} = '';
    end
end
if isfield(stream,'constellation_symbols') && ...
        numel(stream.constellation_symbols) == numel(positions)
    stages{4} = stream.constellation_symbols(:);
    info.stage_sources{4} = 'saved.constellation_symbols';
    info.stage_reasons{4} = '';
end
% decode_soft preserves payload order; check its input against the saved service.
if ~isempty(stages{3}) && isfield(stream,'pre_tracking_symbols') && ...
        ~same_values(stages{3},stream.pre_tracking_symbols)
    stages{3} = [];
    stages{4} = [];
    info.stage_reasons{3} = '联合跟踪结果与导频校正输入不一致';
    info.stage_reasons{4} = '无法确认最终结果使用同一组业务符号';
end
try
    pair_raw = normalize_raw(raw, context, decoded);
    [info.time_us,info.time_mapping] = capture_time(pair_raw,raw,context,decoded);
    info.time_available = true;
    info.time_reason = '';
catch exception
    info.time_reason = ['无法映射原始采集时间：',exception.message];
end
if isempty(stages{1}) && isfield(eq,'name') && strcmp(eq.name,'wz_wl_fse_nlms')
    info.replay.attempted = true;
    try
        pair_raw = normalize_raw(raw, context, decoded);
        [before,check] = replay_before(pair_raw,context,decoded);
        stages{1} = before(positions);
        info.stage_sources{1} = 'verified_saved_parameter_replay';
        info.stage_reasons{1} = '';
        info.replay = check;
    catch exception
        info.replay.reason = exception.message;
        info.stage_reasons{1} = ['均衡前数据不可恢复：',exception.message];
    end
end
for k = 1:4
    info.stage_available(k) = ~isempty(stages{k}) && any(isfinite(stages{k}));
    if ~info.stage_available(k) && isempty(info.stage_reasons{k})
        info.stage_reasons{k} = '本阶段没有有效业务样点';
    end
end
info.stage_symbol_counts = cellfun(@numel,stages);
end

function pair = normalize_raw(raw, context, decoded)
if isfield(raw,'samples') && ~isempty(raw.samples)
    pair = raw;
    require(isfield(pair,'time_axes') && ~isempty(pair.time_axes), ...
        '未保存原始样点时间轴');
    require(size(pair.samples,1) == size(pair.time_axes,1), '样点与时间轴长度不一致');
    require(all(all(isfinite(pair.time_axes))) && all(diff(pair.time_axes(:,1)) > 0), ...
        '原始时间轴无效');
    require(all(max(abs(pair.time_axes-pair.time_axes(:,1)),[],1) < ...
        1e-6/pair.sample_rate_hz), '原始通道尚未映射到公共时间轴');
    return;
end
require(isfield(raw,'channels') && numel(raw.channels) >= 2,'未保存双通道原始波形');
indices = [];
if isfield(context,'route') && isfield(context.route,'waveform_columns') && ...
        isfield(context.route,'scope_channels') && isfield(decoded,'payload_pair')
    desired = [];
    if strcmpi(decoded.payload_pair,'A'), desired = [1 2]; end
    if strcmpi(decoded.payload_pair,'B'), desired = [3 4]; end
    route_columns = context.route.waveform_columns;
    route_channels = cellstr(string(context.route.scope_channels));
    for column = desired
        location = find(route_columns == column);
        require(isscalar(location),'发送路由不能唯一确定接收通道');
        channel_index = find(strcmpi({raw.channels.channel},route_channels{location}));
        require(isscalar(channel_index),'原始波形缺少路由指定通道');
        indices(end+1) = channel_index; %#ok<AGROW>
    end
elseif numel(raw.channels) == 2
    indices = [1 2];
end
require(numel(indices) == 2,'无法确定本接收流对应的双通道');
channels = raw.channels(indices);
times = {double(channels(1).time_axis_s(:)),double(channels(2).time_axis_s(:))};
values = {double(channels(1).samples(:)),double(channels(2).samples(:))};
for k = 1:2
    require(numel(times{k}) >= 2 && numel(times{k}) == numel(values{k}) && ...
        all(isfinite(times{k})) && all(isfinite(values{k})) && all(diff(times{k}) > 0), ...
        '原始通道时间轴或样点无效');
end
rates = cellfun(@(t) 1/median(diff(t)),times);
same_grid = numel(times{1}) == numel(times{2}) && ...
    max(abs(times{1}-times{2})) <= 0.05/min(rates);
if same_grid
    common = times{1};
    samples = [values{1},values{2}];
else
    first = max(times{1}(1),times{2}(1));
    last = min(times{1}(end),times{2}(end));
    rate = min(rates);
    count = floor((last-first)*rate)+1;
    require(count >= 2,'双通道没有公共时间窗口');
    common = first+(0:count-1).'/rate;
    samples = [interp1(times{1},values{1},common,'linear'), ...
        interp1(times{2},values{2},common,'linear')];
end
require(all(isfinite(samples(:))),'公共时间轴插值失败');
pair = struct('samples',samples,'time_axes',repmat(common,1,2), ...
    'sample_rate_hz',1/median(diff(common)),'full_scale',NaN);
if isfield(decoded,'payload_pair'), pair.payload_pair = decoded.payload_pair; end
end

function [before, check] = replay_before(raw, context, decoded)
cfg = context.cfg;
frame = context.tx_ref.frame;
eq = decoded.primary_equalizer;
saved = decoded.preparation;
sync = decoded.synchronization;
require(strcmp(cfg.waveform.architecture,'single_complex_stream') && ...
    strcmp(cfg.receiver.single_equalizer,'wz_wl_fse_nlms'),'不是广义线性分数间隔均衡路径');
require(isfield(saved,'raw_sro_correction'),'未保存原始采样率偏差校正状态');
correction = saved.raw_sro_correction;
require(~field_or(sync,'sro_low_rate_resample_applied',false), ...
    '旧式低采样率重采样路径不支持严格重放');
require(size(raw.samples,1) == correction.input_samples,'原始公共时间轴长度与保存记录不一致');
if correction.applied
    [raw,actual] = msiq.dsp.correct_raw_sro(raw,correction.sro_ppm);
    require(actual.output_samples == correction.output_samples && ...
        abs(actual.inverse_resample_scale-correction.inverse_resample_scale) < 1e-14, ...
        '原始采样率偏差校正结果不一致');
end
[baseband,prep] = msiq.dsp.prepare_capture(raw,cfg);
require(prep.output_samples == saved.output_samples && ...
    prep.resample_p == saved.resample_p && prep.resample_q == saved.resample_q && ...
    prep.processing_samples_per_symbol == eq.processing_samples_per_symbol, ...
    '前处理长度或重采样参数与保存记录不一致');
require(isfield(saved,'baseband_preview_indices') && ...
    ~isempty(saved.baseband_preview_indices),'缺少前处理校验样点');
preview = baseband(saved.baseband_preview_indices,:);
require(same_values(preview,saved.baseband_preview),'重放前处理样点与保存记录不一致');
% Older records predate orientation selection; accept their direct orientation
% only after the independent training and fixed-service checks below agree.
if isfield(decoded,'iq_orientation') && ...
        field_or(decoded.iq_orientation,'conjugate_applied',false)
    baseband = conj(baseband);
end
corrected = baseband(:).*exp(-1j*2*pi*sync.total_cfo_hz/prep.output_sample_rate_hz * ...
    (0:numel(baseband)-1).');
sps = eq.processing_samples_per_symbol;
first = sync.frame_start_sample;
last = first+frame.symbol_count*sps-1;
require(first >= 1 && last <= numel(corrected),'保存帧范围超出原始波形');
samples = corrected(first:last);
service_start = (frame.service_start-1)*sps+1+eq.training_timing_offset_samples;
training_start = (frame.training_start-1)*sps+1+eq.training_timing_offset_samples;
fixed = replay_fixed(samples,service_start,frame.service_length,sps,eq);
training = replay_fixed(samples,training_start,frame.training_length,sps,eq);
require(same_values(fixed,eq.service_symbols_before_tracking), ...
    '固定均衡业务输出与保存记录不一致');
require(same_values(training,eq.training_symbols_equalized), ...
    '训练均衡输出与保存记录不一致');
centers = service_start+(0:frame.service_length-1)*sps;
before = nan(frame.service_length,1);
valid = centers >= 1 & centers <= numel(samples);
before(valid) = samples(centers(valid));
check = struct('attempted',true,'ok',true,'reason','', ...
    'preparation_max_abs_error',max_error(preview,saved.baseband_preview), ...
    'fixed_equalizer_max_abs_error',max_error(fixed,eq.service_symbols_before_tracking), ...
    'training_max_abs_error',max_error(training,eq.training_symbols_equalized));
end

function values = replay_fixed(samples,first,count,sps,eq)
main = eq.main_taps(:);
image = eq.image_taps(:);
half = (numel(main)-1)/2;
require(half == round(half) && numel(main) == numel(image),'均衡抽头格式不支持重放');
values = nan(count,1);
for k = 1:count
    center = first+(k-1)*sps;
    if center-half < 1 || center+half > numel(samples), continue; end
    input = samples(center+half:-1:center-half);
    input = input(:);
    values(k) = main'*input+image'*conj(input);
end
end

function [time_us, map] = capture_time(pair, original, context, decoded)
prep = decoded.preparation;
sync = decoded.synchronization;
frame = context.tx_ref.frame;
require(strcmp(prep.architecture,'single_complex_stream') && ...
    strcmp(decoded.primary_equalizer.name,'wz_wl_fse_nlms'), ...
    '没有本路径的采集时间映射定义');
require(~field_or(sync,'sro_low_rate_resample_applied',false), ...
    '旧式低采样率重采样缺少原始时间反映射');
require(isfield(prep,'raw_sro_correction'),'未保存原始采样率偏差校正状态');
correction = prep.raw_sro_correction;
require(correction.input_samples == size(pair.samples,1),'原始样点数与校正记录不一致');
interval = 1/pair.sample_rate_hz;
time_steps = diff(pair.time_axes(:,1));
time_tolerance = max(interval*1e-4,32*eps(max(abs(pair.time_axes(:,1)))));
require(all(abs(time_steps-interval) <= time_tolerance), ...
    '原始公共时间轴不均匀，不能使用线性采集时间映射');
require(prep.input_samples == correction.output_samples && ...
    prep.output_samples == ceil(prep.input_samples*prep.resample_p/prep.resample_q), ...
    '保存的校正和前处理长度不一致');
scale = 1;
if correction.applied, scale = correction.inverse_resample_scale; end
require(isscalar(scale) && isfinite(scale) && scale > 0,'采样率偏差反映射比例无效');
require(abs(prep.source_sample_rate_hz-pair.sample_rate_hz) <= ...
    max(1,1e-9*pair.sample_rate_hz),'原始采样率与前处理记录不一致');
require(prep.resample_p > 0 && prep.resample_q > 0,'重采样比例无效');
origin = min(pair.time_axes(1,:));
if isfield(original,'channels')
    origin = min(arrayfun(@(c) c.time_axis_s(1),original.channels));
end
common_origin = pair.time_axes(1,1);
sps = prep.processing_samples_per_symbol;
waveform = field_or(context.tx_ref,'waveform_config',struct());
if isfield(context,'cfg') && isfield(context.cfg,'waveform')
    waveform = context.cfg.waveform;
end
span = field_or(waveform,'rrc_span_symbols',field_or(frame,'rrc_span_symbols',NaN));
require(isscalar(span) && isfinite(span) && span > 0 && ...
    mod(span*sps,2) == 0,'没有有效的已保存RRC滤波器长度');
delay = span*sps/2;
% The DDC FIR is zero-phase only on captures long enough for filtfilt.
if ~prep.already_baseband && prep.output_samples <= 579
    center_hz = field_or(waveform,'if_center_hz',NaN);
    require(isscalar(center_hz) && isfinite(center_hz), ...
        '短记录缺少已保存数字下变频配置');
    if center_hz ~= 0, delay = delay+96; end
end
window = numel(frame.sync_symbols)*frame.sync_repeats*sps;
count = numel(sync.repeat_metric_trace);
require(count > 0 && count == prep.output_samples-window+1, ...
    '相关曲线长度不符合保存的前处理和同步窗口');
seconds = prep.resample_q/(prep.resample_p*prep.source_sample_rate_hz*scale);
offset = common_origin-origin-delay*seconds;
time_us = (offset+(0:count-1).'*seconds)*1e6;
map = struct('capture_origin_s',origin,'common_origin_s',common_origin, ...
    'resample_p',prep.resample_p,'resample_q',prep.resample_q, ...
    'sro_inverse_resample_scale',scale,'retained_filter_delay_samples',delay, ...
    'seconds_per_processing_sample_on_raw_axis',seconds, ...
    'first_processing_sample_time_us',offset*1e6, ...
    'definition','sliding correlation window start on original capture axis');
end

function value = field_or(input,name,fallback)
value = fallback;
if isfield(input,name) && ~isempty(input.(name)), value = input.(name); end
end

function equal = same_values(a,b)
a = a(:); b = b(:);
equal = numel(a) == numel(b) && isequal(isfinite(a),isfinite(b));
if ~equal, return; end
finite = isfinite(a);
equal = any(finite) && max(abs(a(finite)-b(finite))) < 1e-10 && ...
    isequaln(a(~finite),b(~finite));
end

function value = max_error(a,b)
a = a(:); b = b(:);
finite = isfinite(a) & isfinite(b);
value = max(abs(a(finite)-b(finite)));
end

function require(condition,message)
if ~condition, error('msiq:rxPlot:StageData','%s',message); end
end
