function gate = hardware_gate(cfg, specs, stage)
%HARDWARE_GATE Validate direct-electrical-output V212/V213 authorization.

stage = lower(char(string(stage)));
if ~ismember(stage, {'awg_off_check','single_dac_smoke'})
    error('msiq:safety:BenchStage', 'Unsupported bench stage: %s.', stage);
end
if ~cfg.safety.hardware_enabled
    error('msiq:safety:HardwareDisabled', ...
        'Hardware mode is disabled in the active configuration.');
end
if ~isfield(cfg.instrument, 'manual_setup') || ...
        ~isstruct(cfg.instrument.manual_setup)
    error('msiq:safety:ManualSetupMissing', ...
        'Local manual_setup is required before V212/V213 hardware access.');
end
manual = cfg.instrument.manual_setup;
required_true(manual, 'direct_electrical_output_only');
required_true(manual, 'wiring_verified');
required_number(manual, 'protection_attenuation_db', 0);

amplitudes = nan(1,4);
if strcmp(stage, 'single_dac_smoke')
    if ~isfield(specs.awg, 'smoke_amplitude_vpp') || ...
            isempty(specs.awg.smoke_amplitude_vpp)
        error('msiq:safety:SmokeAmplitudeMissing', ...
            'Set awg.smoke_amplitude_vpp in instruments.local.json.');
    end
    value = double(specs.awg.smoke_amplitude_vpp);
    if isscalar(value), value = repmat(value, 1, 4); end
    if ~isvector(value) || numel(value) ~= 4 || ...
            any(~isfinite(value)) || any(value <= 0)
        error('msiq:safety:SmokeAmplitudeInvalid', ...
            'smoke_amplitude_vpp must be one positive value or four values.');
    end
    amplitudes = reshape(value, 1, 4);
end

show_wiring(stage, specs, manual, amplitudes);
test_mode = isfield(cfg.safety, 'test_mode') && cfg.safety.test_mode;
granted = isfield(cfg.safety, 'confirmation_granted') && ...
    cfg.safety.confirmation_granted;
if test_mode && granted
    gate = struct('manual_setup', manual, ...
        'smoke_amplitude_vpp', amplitudes, 'confirmation', 'mock_granted');
    return;
end
if ~cfg.safety.interactive_confirmation
    error('msiq:safety:ConfirmationRequired', ...
        'Interactive confirmation is required for V212/V213 hardware access.');
end
if strcmp(stage, 'single_dac_smoke')
    phrase = cfg.safety.smoke_confirmation_phrase;
else
    phrase = cfg.safety.awg_off_confirmation_phrase;
end
reply = input(sprintf('Type exactly "%s" to continue: ', phrase), 's');
if ~strcmp(reply, phrase)
    error('msiq:safety:ConfirmationRejected', ...
        'Bench-stage confirmation was not granted.');
end
gate = struct('manual_setup', manual, ...
    'smoke_amplitude_vpp', amplitudes, 'confirmation', 'interactive_granted');
end

function required_true(value, field)
if ~isfield(value, field) || ~isscalar(value.(field)) || ...
        ~logical(value.(field))
    error('msiq:safety:ManualSetupIncomplete', ...
        'manual_setup.%s must be true.', field);
end
end

function required_number(value, field, minimum)
if ~isfield(value, field) || isempty(value.(field)) || ...
        ~isscalar(value.(field)) || ~isfinite(double(value.(field))) || ...
        double(value.(field)) < minimum
    error('msiq:safety:ManualSetupIncomplete', ...
        'manual_setup.%s must be a finite value >= %.15g.', field, minimum);
end
end

function show_wiring(stage, specs, manual, amplitudes)
channel = msiq.bench.scope_channel(specs.scope);
fprintf('\n%s direct electrical-output wiring\n', upper(stage));
fprintf('M8195A selected DAC -> protection/attenuation -> LeCroy %s\n', channel);
fprintf('Do not connect the transmit IF board, RF front end, or E8257D.\n');
fprintf('Protection attenuation: %.6g dB\n', manual.protection_attenuation_db);
if strcmp(stage, 'single_dac_smoke')
    fprintf('Local smoke amplitudes [DAC1..DAC4]: %s Vpp\n', mat2str(amplitudes));
end
fprintf('Only one DAC may be ON at any time.\n\n');
end
