function index = rx_envelope_indices(samples, maximum)
%RX_ENVELOPE_INDICES Ordered extrema per display bin; preserves narrow peaks.
count = numel(samples);
if count <= maximum, index = (1:count)'; return; end
bins = max(1,floor(maximum/2));
width = ceil(count/bins);
full = floor(count/width);
matrix = reshape(samples(1:full*width),width,full);
[~,lo] = min(matrix,[],1); [~,hi] = max(matrix,[],1);
index = sort([lo+(0:full-1)*width hi+(0:full-1)*width])';
if full*width < count
    tail = samples(full*width+1:end);
    [~,lo] = min(tail); [~,hi] = max(tail);
    index = [index; sort([lo;hi])+full*width];
end
index = unique([1; index; count]);
end
