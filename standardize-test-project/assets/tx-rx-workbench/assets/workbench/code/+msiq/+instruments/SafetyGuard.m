classdef SafetyGuard < handle
    %SAFETYGUARD Ensure owned AWG/source sessions are shut down on errors.

    properties
        Sessions
        Config
        Done = false
        Report
    end

    methods
        function object = SafetyGuard(cfg)
            object.Config = cfg;
            object.Sessions = struct('awg', [], 'scope', [], 'source', []);
            object.Report = struct('awg_off', false, ...
                'awg_readback', false(1,4), 'awg_readback_ok', false, ...
                'source_off', false, 'errors', {{}});
        end

        function report = shutdown(object)
            if ~object.Done
                object.Report = msiq.instruments.safe_shutdown( ...
                    object.Sessions, object.Config);
                object.Done = true;
            end
            report = object.Report;
        end

        function delete(object)
            object.shutdown();
        end
    end
end
