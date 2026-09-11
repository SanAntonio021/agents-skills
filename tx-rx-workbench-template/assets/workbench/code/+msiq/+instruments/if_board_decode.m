function result = if_board_decode(frame)
%IF_BOARD_DECODE Decode only receive types evidenced in supplied GUI.
% Power bytes are deliberately raw: no unverified engineering conversion.
assert(isnumeric(frame) && isreal(frame) && numel(frame)==10 && ...
    all(isfinite(frame(:))) && all(frame(:)>=0 & frame(:)<=255) && ...
    all(frame(:)==round(frame(:))), 'msiq:ifboard:frame','Expected ten bytes.');
frame = uint8(frame(:).');
assert(isequal(frame([1 2 10]),uint8([170 187 204])), ...
    'msiq:ifboard:frame','Invalid frame envelope.');
result = struct('kind','','raw',frame,'payload_raw',frame(4:9), ...
    'attenuation_readback',false,'values',[],'units','raw byte');
switch frame(3)
    case 9
        result.kind = 'lock_status';
        result.values = logical(bitget(frame(4:9),1));
        result.units = 'lock bit 0';
    case 3
        result.kind = 'i_power_raw';
    case 5
        result.kind = 'q_power_raw';
    otherwise
        error('msiq:ifboard:receiveType', ...
            'No evidenced receive decoder for opcode %d; not an attenuation ACK.',frame(3));
end
end
