function states = set_awg_selected_outputs(session, channels)
%SET_AWG_SELECTED_OUTPUTS Enable selected DACs without touching other DACs.

channels = unique(double(channels(:).'), 'stable');
validateattributes(channels, {'numeric'}, ...
    {'vector','integer','>=',1,'<=',4,'nonempty'});

try
    states = msiq.instruments.set_awg_channels_output(session, channels, true);
    if ~all(states(channels))
        error('msiq:safety:SelectedOutputReadback', ...
            'Selected AWG outputs did not enable. Readback: %s.', ...
            mat2str(states));
    end
catch exception
    for channel = channels
        try
            msiq.instruments.write_scpi(session, ...
                sprintf(':OUTPut%d OFF', channel));
        catch
        end
    end
    rethrow(exception);
end
end
