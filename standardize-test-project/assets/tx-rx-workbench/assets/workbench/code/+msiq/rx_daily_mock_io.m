function io=rx_daily_mock_io(options)
%RX_DAILY_MOCK_IO Deterministic verified acquisition handshake, no instrument I/O.
base=msiq.instruments.mock_rx_scope_io(options); ready=false;
io=base; io.query=@query; io.write=@write;
    function value=query(session,command)
        if strcmp(command,'MOCK:DONE?'), value=num2str(ready); else, value=base.query(session,command); end
    end
    function write(session,command)
        switch command
            case 'MOCK:RESET', ready=false;
            case 'MOCK:START', ready=true;
            otherwise, base.write(session,command);
        end
    end
end
