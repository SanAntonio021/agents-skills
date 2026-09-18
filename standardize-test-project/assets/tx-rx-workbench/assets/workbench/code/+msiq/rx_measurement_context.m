function context = rx_measurement_context(position, subband)
%RX_MEASUREMENT_CONTEXT Canonical acquisition meaning, independent of wiring.
if nargin < 1, position = ''; end
if isstruct(position)
    saved = position;
    if isfield(saved,'position'), position=saved.position; else, position=''; end
    if nargin < 2 && isfield(saved,'subband'), subband=saved.subband; end
end
ids = {'awg_direct','tx_if','thz_if','rx_if','rx_if_thz'};
labels = {'AWG 直连','中频上变频输出','太赫兹下变频输出', ...
    '中频下变频输出（未经过太赫兹）','中频下变频输出（已经过太赫兹）'};
if isnumeric(position) && ~isempty(position)
    validateattributes(position,{'numeric'},{'scalar','integer','>=',1,'<=',5});
    position=ids{position};
end
position=char(string(position));
index=find(strcmp(ids,position),1);
if isempty(index) && ~isempty(position)
    error('msiq:measurement:Position','未知测量位置：%s',position);
end
label='位置未记录';
if ~isempty(index), label=labels{index}; end
real_if=ismember(position,{'tx_if','thz_if'});
has_subband=~isempty(position) && ~strcmp(position,'awg_direct');
if has_subband
    assert(exist('subband','var') && ~isempty(subband), ...
        'msiq:measurement:Subband','中频测量需要选择目标子带。');
    validateattributes(subband,{'numeric'},{'scalar','integer','>=',1,'<=',6});
end
fc=0;
if real_if, centers=msiq.if_subband_frequencies(); fc=centers(subband); end
context=struct('schema_version',2,'position',position,'label',label, ...
    'through_thz',ismember(position,{'thz_if','rx_if_thz'}), ...
    'is_real_if',real_if,'center_freq_hz',fc);
if has_subband, context.subband=double(subband); end
end
