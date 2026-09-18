function value = if_board_quantize(input,limits)
%IF_BOARD_QUANTIZE Nearest approved half-dB step; ties increase attenuation.
if ischar(input) || isstring(input), input=str2double(input); end
validateattributes(input,{'numeric'},{'scalar','real','finite'});
validateattributes(limits,{'numeric'},{'numel',2,'real','finite','>=',0,'<=',31.5});
lower=ceil(limits(1)*2)/2; upper=floor(limits(2)*2)/2;
assert(lower<=upper,'msiq:ifboard:limits','批准范围内没有合法的 0.5 dB 档位。');
value=min(upper,max(lower,floor(input*2+0.5)/2));
end
