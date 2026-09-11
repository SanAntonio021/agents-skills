function report = safe_shutdown(sessions, cfg)
%SAFE_SHUTDOWN Disable AWG/source outputs, then close owned sessions.

msiq.instruments.io_audit('increment', 'shutdown_calls');
report = struct('awg_off', false, 'awg_readback', false(1,4), ...
    'awg_readback_ok', false, 'source_off', false, 'errors', {{}});
if isempty(sessions)
    return;
end
if isfield(sessions, 'awg') && ~isempty(sessions.awg)
    try
        if cfg.safety.shutdown_awg
            msiq.instruments.set_awg_output(sessions.awg, false);
            report.awg_off = true;
            report.awg_readback = ...
                msiq.instruments.read_awg_output_state(sessions.awg);
            report.awg_readback_ok = ~any(report.awg_readback);
            if ~report.awg_readback_ok
                report.errors{end+1} = ...
                    'AWG shutdown readback reports an enabled DAC.';
            end
        end
    catch exception
        report.errors{end+1} = exception.message;
    end
end
if isfield(sessions, 'source') && ~isempty(sessions.source)
    try
        if cfg.safety.shutdown_signal_generator
            msiq.instruments.configure_source( ...
                sessions.source, sessions.source.specification, false);
            report.source_off = true;
        end
    catch exception
        report.errors{end+1} = exception.message;
    end
end
names = {'scope', 'source', 'awg'};
for k = 1:numel(names)
    if isfield(sessions, names{k}) && ~isempty(sessions.(names{k}))
        msiq.instruments.close_session(sessions.(names{k}));
    end
end
end
