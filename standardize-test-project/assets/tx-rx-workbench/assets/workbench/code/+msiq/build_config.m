function cfg = build_config(profile)
%BUILD_CONFIG Load and validate a V2 profile without instrument I/O.

if nargin < 1 || isempty(profile)
    profile = 'v2_default';
end

root = msiq.project_root();
if isstruct(profile)
    cfg = profile;
    profile_path = '';
else
    profile_name = char(string(profile));
    if any(strcmpi(profile_name, {'default', 'v2'}))
        profile_name = 'v2_default';
    end
    if isfile(profile_name)
        profile_path = profile_name;
    else
        profile_path = fullfile(root, 'config', [profile_name, '.json']);
    end
    if ~isfile(profile_path)
        error('msiq:config:ProfileNotFound', ...
            'Configuration profile not found: %s', profile_path);
    end
    cfg = jsondecode(fileread(profile_path));
end

cfg.project_root = root;
cfg.profile_path = profile_path;
cfg.code_root = fullfile(root, 'code');
cfg.results_root = resolve_path(root, cfg.results.root);

local_path = resolve_path(root, cfg.instrument.local_config);
cfg.instrument.local_config_path = local_path;
cfg.instrument.local_loaded = false;
if isfile(local_path)
    local_cfg = jsondecode(fileread(local_path));
    cfg.instrument = merge_recursive(cfg.instrument, local_cfg);
    cfg.instrument.local_loaded = true;
end

cfg.fec.rate = cfg.fec.rate_numerator / cfg.fec.rate_denominator;
cfg.waveform.symbol_rate_hz = ...
    cfg.waveform.master_sample_rate_hz / cfg.waveform.selected_up;
cfg.waveform.master_samples_per_symbol = cfg.waveform.selected_up;
cfg.waveform.awg_samples_per_symbol = ...
    cfg.waveform.awg_sample_rate_hz / cfg.waveform.symbol_rate_hz;
cfg.waveform.bits_per_symbol = log2(cfg.waveform.modulation_order);
cfg.waveform.decimation = ...
    cfg.waveform.master_sample_rate_hz / cfg.waveform.awg_sample_rate_hz;
cfg.receiver.reference_payload_aided = false;

validate_config(cfg);
end

function validate_config(cfg)
required = {'waveform', 'fec', 'receiver', 'channels', 'awg', ...
    'scope', 'experiment', 'results', 'safety', 'instrument'};
for k = 1:numel(required)
    if ~isfield(cfg, required{k})
        error('msiq:config:MissingSection', ...
            'Configuration is missing section %s.', required{k});
    end
end
if cfg.waveform.modulation_order ~= 16
    error('msiq:config:ModulationLocked', ...
        'V2 formal profile is locked to 16QAM.');
end
msiq.fec.specification(cfg);
if ~ismember(cfg.waveform.selected_up, cfg.waveform.up_candidates)
    error('msiq:config:BadUpsampling', ...
        'selected_up must be one of up_candidates.');
end
if abs(cfg.waveform.decimation - round(cfg.waveform.decimation)) > 1e-12
    error('msiq:config:NonIntegerDecimation', ...
        'Master-to-AWG decimation must be an integer.');
end
if numel(cfg.channels.logical_labels) ~= 6
    error('msiq:config:ChannelCount', ...
        'Exactly six logical RF channels are required.');
end
if cfg.experiment.formal_repeats ~= ...
        numel(cfg.experiment.seed_values) * cfg.experiment.captures_per_seed
    error('msiq:config:RepeatPlan', ...
        'formal_repeats must equal seed count times captures_per_seed.');
end
if ~isscalar(cfg.awg.smoke_tone_samples) || ...
        ~isfinite(cfg.awg.smoke_tone_samples) || ...
        cfg.awg.smoke_tone_samples < 128 || ...
        mod(cfg.awg.smoke_tone_samples,128) ~= 0
    error('msiq:config:SmokeToneSamples', ...
        'smoke_tone_samples must be a positive multiple of 128.');
end
if ~isscalar(cfg.scope.vertical_divisions) || ...
        ~isfinite(cfg.scope.vertical_divisions) || cfg.scope.vertical_divisions <= 0
    error('msiq:config:ScopeVerticalDivisions', ...
        'scope.vertical_divisions must be positive.');
end
if ~strcmpi(cfg.receiver.reference_payload_policy, 'metrics_only') || ...
        cfg.receiver.reference_payload_aided
    error('msiq:config:PayloadLeakage', ...
        'Reference payload is permitted only for final metrics.');
end
end

function path = resolve_path(root, value)
path = char(string(value));
if isempty(path)
    return;
end
if isempty(regexp(path, '^[A-Za-z]:[\\/]|^\\\\', 'once'))
    path = fullfile(root, path);
end
end

function out = merge_recursive(base, extra)
out = base;
names = fieldnames(extra);
for k = 1:numel(names)
    name = names{k};
    if isfield(out, name) && isstruct(out.(name)) && ...
            isscalar(out.(name)) && isstruct(extra.(name)) && ...
            isscalar(extra.(name))
        out.(name) = merge_recursive(out.(name), extra.(name));
    else
        out.(name) = extra.(name);
    end
end
end
