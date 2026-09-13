function cfg = apply_condition(cfg, condition)
%APPLY_CONDITION Bind waveform settings to one experiment condition.

if nargin < 1 || isempty(cfg)
    cfg = msiq.build_config('v2_default');
elseif ~isstruct(cfg)
    cfg = msiq.build_config(cfg);
end
if ~isstruct(condition) || ~isscalar(condition)
    error('msiq:config:ConditionFormat', ...
        'condition must be a scalar struct.');
end
required = {'architecture', 'up'};
for k = 1:numel(required)
    if ~isfield(condition, required{k}) || isempty(condition.(required{k}))
        error('msiq:config:ConditionField', ...
            'condition.%s is required.', required{k});
    end
end

architecture = lower(char(string(condition.architecture)));
if ~ismember(architecture, {'dual_iq_mimo', 'single_complex_stream'})
    error('msiq:config:ConditionArchitecture', ...
        'Unsupported condition architecture: %s.', architecture);
end
up = double(condition.up);
if ~isscalar(up) || ~isfinite(up) || up ~= round(up) || ...
        ~ismember(up, double(cfg.waveform.up_candidates(:)).')
    error('msiq:config:ConditionUpsampling', ...
        'condition.up must be one of the configured UP candidates.');
end

symbol_rate = double(cfg.waveform.master_sample_rate_hz) / up;
if isfield(condition, 'symbol_rate_hz') && ...
        ~isempty(condition.symbol_rate_hz) && isfinite(condition.symbol_rate_hz)
    tolerance = max(1, 1e-12*symbol_rate);
    if abs(double(condition.symbol_rate_hz)-symbol_rate) > tolerance
        error('msiq:config:ConditionSymbolRate', ...
            'condition.symbol_rate_hz is inconsistent with master rate / UP.');
    end
end

cfg.waveform.architecture = architecture;
cfg.waveform.selected_up = up;
cfg.waveform.symbol_rate_hz = symbol_rate;
cfg.waveform.master_samples_per_symbol = up;
cfg.waveform.awg_samples_per_symbol = ...
    double(cfg.waveform.awg_sample_rate_hz) / symbol_rate;
end
