function report = preflight_waveform(waveforms, cfg, model)
%PREFLIGHT_WAVEFORM Check waveform format and clipping before AWG capacity.

if nargin < 3 || isempty(model)
    model = cfg.awg.model;
end
model = char(string(model));
sample_count = size(waveforms.awg_dac_data, 1);
report = struct('ok', true, 'model', model, ...
    'sample_count', sample_count, ...
    'sample_rate_hz', waveforms.awg_sample_rate_hz, ...
    'formal_mode', ismember(lower(model), ...
    {'m8195a_4ch','m8195a_2ext_div2'}), ...
    'reason', '');

overflow_fraction = field_or(waveforms, 'sample_range_overflow_fraction', ...
    field_or(waveforms, 'clipping_fraction', zeros(1,4)));
if any(overflow_fraction > 0)
    report.ok = false;
    report.reason = 'generated_waveform_sample_range_overflow';
elseif strcmpi(model, 'M8195A_4int')
    if abs(waveforms.awg_sample_rate_hz-cfg.waveform.master_sample_rate_hz) > 1
        report.ok = false;
        report.reason = 'int_requires_full_raster_sample_rate';
    end
elseif strcmpi(model, cfg.awg.diagnostic_model)
    if abs(waveforms.awg_sample_rate_hz - ...
            cfg.waveform.master_sample_rate_hz) < 1
        diagnostic_count = size(waveforms.master_dac_data, 1);
    else
        diagnostic_count = sample_count;
    end
    report.sample_count = diagnostic_count;
    if diagnostic_count > cfg.awg.diagnostic_max_samples
        report.ok = false;
        report.reason = 'diagnostic_256k_memory_exceeded';
    end
elseif strcmpi(model, 'M8195A_4ch')
    if abs(waveforms.awg_sample_rate_hz - ...
            cfg.waveform.master_sample_rate_hz/4) > 1
        report.ok = false;
        report.reason = 'formal_four_dac_requires_div4_sample_rate';
    end
elseif strcmpi(model, 'M8195A_2ext_div2')
    if abs(waveforms.awg_sample_rate_hz - ...
            cfg.waveform.master_sample_rate_hz/2) > 1
        report.ok = false;
        report.reason = 'pair_ext_div2_requires_half_raster_sample_rate';
    end
else
    report.ok = false;
    report.reason = 'unsupported_awg_model';
end
end


function value = field_or(source, name, fallback)
if isstruct(source) && isfield(source, name) && ~isempty(source.(name))
    value = source.(name);
else
    value = fallback;
end
end
