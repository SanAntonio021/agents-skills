function frame = if_board_encode(kind, values)
%IF_BOARD_ENCODE Pure encoder for the supplied JH005 configuration.
% Evidence: config/UpCommputerDb.db SerialSendBytes. Static evidence is
% not runtime protocol verification. Values always describe all six bands.
kind = lower(char(kind));
if nargin < 2, values = []; end
switch kind
    case {'rf','i','q'}
        assert(isnumeric(values) && isreal(values) && numel(values)==6 && ...
            all(isfinite(values(:))) && all(values(:)>=0 & values(:)<=31.5) && ...
            all(values(:)*2==round(values(:)*2)), ...
            'msiq:ifboard:values','Supply six known 0:0.5:31.5 dB values.');
        names = {'rf','i','q'}; codes = [1 4 6];
        opcode = codes(strcmp(kind,names)); payload = 2*values(:).';
    case 'agc'
        assert((isnumeric(values)||islogical(values)) && numel(values)==6 && ...
            all(values(:)==0 | values(:)==1), ...
            'msiq:ifboard:values','Supply six explicit AGC bits.');
        opcode = 2; payload = double(values(:).');
    case 'status'
        assert(isempty(values),'msiq:ifboard:values','Status has no payload argument.');
        opcode = 9; payload = zeros(1,6);
    otherwise
        error('msiq:ifboard:kind','Unsupported command kind.');
end
frame = uint8([170 187 opcode payload 204]);
end
