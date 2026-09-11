function configure_source(session, specification, enabled)
%CONFIGURE_SOURCE Configure E8257D and explicitly control RF output.

if nargin < 3
    enabled = false;
end
if isfield(specification, 'frequency_hz') && ...
        ~isempty(specification.frequency_hz) && ...
        isfinite(specification.frequency_hz)
    msiq.instruments.write_scpi(session, sprintf( ...
        ':FREQuency %.15g', specification.frequency_hz));
end
if isfield(specification, 'power_dbm') && ...
        ~isempty(specification.power_dbm) && isfinite(specification.power_dbm)
    msiq.instruments.write_scpi(session, sprintf( ...
        ':POWer %.15g DBM', specification.power_dbm));
end
if enabled
    msiq.instruments.write_scpi(session, ':OUTPut ON');
else
    msiq.instruments.write_scpi(session, ':OUTPut OFF');
end
end
