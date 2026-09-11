function [data, info] = precompensate_tx_sro(data, waveform)
%PRECOMPENSATE_TX_SRO Apply a measured relative clock calibration to TX samples.
% Positive measured ppm means RX observes longer symbol intervals.
settings = struct('enabled', false, 'measured_sro_ppm', 0, ...
    'calibrated_at', '', 'calibration_source', '');
if isfield(waveform, 'tx_sro_precomp')
    supplied = waveform.tx_sro_precomp;
    if ~isstruct(supplied) || ~isscalar(supplied)
        error('msiq:txSro:Settings', 'tx_sro_precomp must be a scalar struct.');
    end
    names = fieldnames(supplied);
    for k = 1:numel(names)
        if ~isfield(settings, names{k})
            error('msiq:txSro:Settings', 'Unknown TX SRO setting: %s.', names{k});
        end
        settings.(names{k}) = supplied.(names{k});
    end
end
validateattributes(settings.enabled, {'logical','numeric'}, ...
    {'scalar','real','finite','binary'});
validateattributes(settings.measured_sro_ppm, {'numeric'}, ...
    {'scalar','real','finite','>=',-2000,'<=',2000});
for name = {'calibrated_at','calibration_source'}
    value = settings.(name{1});
    if ~(ischar(value) && (isrow(value) || isempty(value))) && ...
            ~(isstring(value) && isscalar(value) && ~ismissing(value))
        error('msiq:txSro:Metadata', '%s must be text.', name{1});
    end
    settings.(name{1}) = char(value);
end
info = settings;
info.enabled = logical(settings.enabled);
info.applied = info.enabled && settings.measured_sro_ppm ~= 0;
info.stage = 'tx_waveform';
info.method = 'cubic_spline_master_rate';
info.time_scale = 1;
info.input_samples = size(data, 1);
info.output_samples = size(data, 1);
info.nominal_master_rate_hz = waveform.master_sample_rate_hz;
info.nominal_symbol_rate_hz = waveform.symbol_rate_hz;
if ~info.enabled
    return;
end
if ~strcmp(waveform.architecture, 'single_complex_stream') || ...
        waveform.modulation_order ~= 16 || waveform.frame_repetitions < 2 || ...
        ~isfield(waveform, 'periodic_rrc') || ~waveform.periodic_rrc
    error('msiq:txSro:Scope', ...
        'TX SRO precompensation requires periodic traditional 16QAM and >=2 frames.');
end
if isempty(strtrim(info.calibrated_at)) || ...
        isempty(strtrim(info.calibration_source))
    error('msiq:txSro:Metadata', ...
        'Enabled TX SRO calibration needs calibrated_at and calibration_source.');
end
if ~info.applied
    return;
end
validateattributes(data, {'double'}, {'2d','real','finite','nonempty'});
clock_scale = 1 + double(settings.measured_sro_ppm)*1e-6;
band_edge = abs(waveform.if_center_hz) + ...
    waveform.symbol_rate_hz*(1+waveform.rolloff)/2;
if band_edge*clock_scale >= waveform.awg_sample_rate_hz/2
    error('msiq:txSro:Bandwidth', 'Precompensated signal exceeds the AWG Nyquist band.');
end
info.time_scale = 1/clock_scale;
info.output_samples = ceil(info.input_samples*info.time_scale);
% Extend the generated period, retaining fractional timing at its last sample.
% Integer length rounding and AWG padding remain explicit at the download stage.
count = info.input_samples;
if count < 8
    error('msiq:txSro:Length', 'TX waveform needs at least eight samples.');
end
extended = [data(end-3:end,:); data; data(1:4,:)];
query = (0:info.output_samples-1).'*clock_scale;
data = interp1((-4:count+3).', extended, query, 'spline');
end
