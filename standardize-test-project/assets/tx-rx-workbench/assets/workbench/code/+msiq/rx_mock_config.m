function cfg = rx_mock_config()
%RX_MOCK_CONFIG Shared software profile plus an address-free test scope.
cfg = jsondecode(fileread(fullfile(msiq.project_root(),'config','v2_traditional_wz.json')));
cfg.instrument.local_config = '';
cfg.instrument.scope = struct('mock',true,'resource','MOCK_RX_SCOPE', ...
    'channels',{{'C1','C2'}});
end
