function cfg = if_board_vendor_defaults(role)
%IF_BOARD_VENDOR_DEFAULTS File-only manufacturer communication preset.
% No COM port, attenuation, approved limits or runtime verification is inferred.
% Evidence and its boundary are recorded in docs/if_board_protocol.md.
if nargin < 1, role = 'rx'; end
role = lower(char(role));
assert(any(strcmp(role,{'tx','rx'})), 'msiq:ifboard:role', ...
    'Board role must be tx or rx.');
cfg = struct();
cfg.role = role;
cfg.serial = struct('baud_rate',115200,'data_bits',8,'parity','none', ...
    'stop_bits',1,'flow_control','none','timeout',2, ...
    'protocol_version','jh005_v01_config');
cfg.runtime = struct('protocol_verified',false);
cfg.evidence_note = ['厂家《上位机操作说明》第2页及TX/RX FPGA源码：115200、8位、无校验、1停止位。' ...
    '无流控和2秒超时为本程序默认值，非厂家规定。' ...
    'jh005_v01_config为配置标识，非板卡固件版本；尚未确认现场板卡。'];
end
