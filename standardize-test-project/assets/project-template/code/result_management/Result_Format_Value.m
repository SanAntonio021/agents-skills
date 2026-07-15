function text = Result_Format_Value(value, precision)
%RESULT_FORMAT_VALUE Format a finite scalar with fixed decimal precision.

validateattributes(value, {'numeric'}, {'real', 'finite', 'scalar'});
validateattributes(precision, {'numeric'}, ...
    {'real', 'finite', 'scalar', 'integer', '>=', 0, '<=', 15});

if abs(value) < 0.5 * 10^(-precision)
    value = 0;
end
text = sprintf(['%0.', num2str(precision), 'f'], value);

end
