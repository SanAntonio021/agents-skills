function spectrum = Test_Project_Complex_Spectrum(input, options)
%TEST_PROJECT_COMPLEX_SPECTRUM Gate raw IQ combination on proven alignment.
% Alternatively accept DSP-aligned samples with explicit stage provenance.
if nargin < 2, options = struct(); end
spectrum = Test_Project_Compute_PSD([],NaN,options);
spectrum.reason = ''; spectrum.density_unit = ''; spectrum.stage_id = '';
spectrum.alignment_basis = ''; spectrum.amplitude_unit = '';
if ~isstruct(input) || ~isscalar(input)
    spectrum.reason = 'Input must be a scalar struct.'; return
end
if isfield(input,'channels')
    channels = input.channels;
    if ~isstruct(channels) || numel(channels) ~= 2 || ~isfield(channels,'role')
        spectrum.reason = 'Raw IQ requires exactly one I and one Q channel.'; return
    end
    iIndex = find(strcmpi({channels.role},'I')); qIndex = find(strcmpi({channels.role},'Q'));
    if numel(iIndex) ~= 1 || numel(qIndex) ~= 1 || ~isfield(channels,'sync_verified') || ...
            ~isequal(channels(iIndex).sync_verified,true) || ~isequal(channels(qIndex).sync_verified,true)
        spectrum.reason = 'Both raw I and Q channels must explicitly confirm synchronization.'; return
    end
    analysis = Test_Project_Analyze_Capture(channels,options);
    iChannel = analysis.channels(iIndex); qChannel = analysis.channels(qIndex);
    if ~strcmp(iChannel.spectrum.status,'ok') || ~strcmp(qChannel.spectrum.status,'ok')
        spectrum.reason = 'Both raw I and Q channels require valid samples and uniform timing.'; return
    end
    ti = iChannel.waveform.time_s; tq = qChannel.waveform.time_s;
    tolerance = min(1/iChannel.spectrum.fs_hz,1/qChannel.spectrum.fs_hz)*1e-6;
    if numel(ti) ~= numel(tq) || any(abs(ti-tq) > tolerance)
        spectrum.reason = 'Raw I and Q time grids do not match; alignment is required upstream.'; return
    end
    samples = complex(iChannel.waveform.samples_v,qChannel.waveform.samples_v);
    fs = iChannel.spectrum.fs_hz; unit = 'V';
    basis = 'capture_verified'; stage = 'raw_iq';
elseif isfield(input,'samples') && isfield(input,'fs_hz')
    if ~isfield(input,'alignment_basis') || ~strcmp(input.alignment_basis,'dsp_aligned') || ...
            ~isfield(input,'stage_id') || strlength(string(input.stage_id)) == 0
        spectrum.reason = 'DSP samples require alignment_basis=dsp_aligned and a nonempty stage_id.'; return
    end
    if ~isfield(input,'amplitude_unit') || ~ismember(string(input.amplitude_unit),["V","dimensionless"])
        spectrum.reason = 'amplitude_unit must be V or dimensionless.'; return
    end
    samples = input.samples; fs = input.fs_hz; unit = char(input.amplitude_unit);
    basis = 'dsp_aligned'; stage = char(input.stage_id);
else
    spectrum.reason = 'Provide raw channels or DSP-aligned samples and fs_hz.'; return
end
% Explicitly preserve complex semantics even if the imaginary samples are zero.
options.sidedness = 'centered-two-sided';
spectrum = Test_Project_Compute_PSD(samples,fs,options);
spectrum.stage_id = stage; spectrum.alignment_basis = basis; spectrum.amplitude_unit = unit;
if strcmp(unit,'V'), spectrum.density_unit = 'V^2/Hz'; else, spectrum.density_unit = '1/Hz'; end
end
