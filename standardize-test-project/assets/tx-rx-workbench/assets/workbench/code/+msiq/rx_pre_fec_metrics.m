function m=rx_pre_fec_metrics(result)
%RX_PRE_FEC_METRICS Strict workbench display and comparison numerator/denominator.
m=struct('valid',false,'pre_error_count',NaN,'pre_bit_count',NaN,'pre_ber',NaN,'mer_db',NaN,'reason','未取得完整纠错前指标');
streams=struct([]);
if isfield(result,'pairs')
    for p=result.pairs
        if isfield(p,'decoded') && isfield(p.decoded,'valid') && ~p.decoded.valid, return; end
        if isfield(p,'decoded') && isfield(p.decoded,'sync_ok') && ~p.decoded.sync_ok, return; end
        if isfield(p,'decoded') && isfield(p.decoded,'primary_streams')
            streams=[streams p.decoded.primary_streams]; %#ok<AGROW>
        end
    end
elseif isfield(result,'primary_streams'), streams=result.primary_streams; end
if isempty(streams), return; end
if isfield(streams,'valid') && ~all([streams.valid]), return; end
if ~all(isfield(streams,{'pre_fec_bit_count','pre_fec_bit_error_count','pre_fec_ber','mer_db'})), return; end
n=[streams.pre_fec_bit_count]; e=[streams.pre_fec_bit_error_count]; b=[streams.pre_fec_ber];
if any(~isfinite([n e b])) || any(n<=0) || any(e<0) || any(e>n), return; end
m.pre_bit_count=sum(n); m.pre_error_count=sum(e); m.pre_ber=sum(e)/sum(n);
m.mer_db=mean([streams.mer_db]); m.valid=isfinite(m.mer_db);
if m.valid, m.reason=''; else, m.reason='MER 不是有效的有限数值'; end
end
