function summary=if_compare_contract(plans)
%IF_COMPARE_CONTRACT Compare physical playback clocks and identical frame bits.
assert(iscell(plans)&&numel(plans)==2,'msiq:if:ComparisonPlan','Two mode plans are required.');
rates=zeros(1,2); baud=rates; bits=cell(1,2);
for k=1:2
    p=plans{k};
    assert(p.memory_capacity.ok,'msiq:if:Capacity','A mode exceeds final aligned waveform capacity.');
    rates(k)=p.actual_waveform_sample_rate_hz;
    baud(k)=p.cfg.waveform.symbol_rate_hz;
    assert(isfinite(rates(k))&&rates(k)>0&&isfinite(baud(k))&&baud(k)>0, ...
        'msiq:if:Rates','Invalid effective waveform rate.');
    assert(abs(rates(k)/p.cfg.waveform.awg_samples_per_symbol-baud(k))<1, ...
        'msiq:if:Baud','Playback clock and samples per symbol do not yield the requested baud.');
    bits{k}=p.tx_ref.pairs(1).metrics_only(1).fec.coded_bits;
end
assert(abs(baud(1)-baud(2))<1&&abs(baud(1)-65e9/15)<1,'msiq:if:Baud','Both modes must use the approved symbol rate.');
assert(isequal(bits{1},bits{2}),'msiq:if:FrameMismatch','Mode comparison requires identical encoded frame content.');
assert(isequal(plans{1}.route.awg_channels,plans{2}.route.awg_channels), ...
    'msiq:if:RouteMismatch','Mode comparison requires the same physical channel pair.');
assert(abs(rates(2)/rates(1)-4)<1e-9,'msiq:if:Rates','EXT/DIV4 and INT must use their actual distinct playback rates.');
summary=struct('valid',true,'playback_rates_hz',rates,'symbol_rate_hz',baud(1), ...
    'reference_bits',numel(bits{1}),'reference_hash',msiq.sha256_bytes(bits{1}));
end
