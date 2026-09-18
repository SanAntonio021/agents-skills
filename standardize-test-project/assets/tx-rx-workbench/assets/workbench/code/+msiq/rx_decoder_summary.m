function label=rx_decoder_summary(result)
%RX_DECODER_SUMMARY Present saved FEC evidence; never rerun or infer execution.
streams={};
if isfield(result,'pairs')
    for pair=result.pairs
        if isfield(pair,'decoded') && isfield(pair.decoded,'primary_streams')
            for stream=pair.decoded.primary_streams, streams{end+1}=stream; end %#ok<AGROW>
        end
    end
elseif isfield(result,'primary_streams')
    for stream=result.primary_streams, streams{end+1}=stream; end %#ok<AGROW>
end
if isempty(streams), label='LDPC：未取得执行记录'; return; end
executed=nan(1,numel(streams)); errors=executed; bits=executed; statuses=cell(1,numel(streams));
for k=1:numel(streams)
    stream=streams{k}; fec=field(stream,'fec',stream);
    flag=field(fec,'decoder_executed',NaN);
    if isscalar(flag) && (isequal(flag,true) || isequal(flag,false) || isequal(flag,1) || isequal(flag,0)), executed(k)=double(flag); end
    errors(k)=number(fec,'post_fec_bit_error_count'); bits(k)=number(fec,'post_fec_bit_count');
    statuses{k}=char(string(field(fec,'decoder_status','')));
end
if all(executed==0)
    if any(strcmp(statuses,'NOT_RUN_INVALID_REFERENCE_OR_CAPTURE'))
        label='LDPC 未执行：参考或采集无效';
    elseif all(strcmp(statuses,'NOT_RUN_DEBUG_PRE_FEC_ONLY'))
        label='LDPC 未执行：本次仅计算纠错前指标';
    else, label='LDPC 未执行：未取得有效译码结果'; end
    return;
end
if any(isnan(executed)), label='LDPC：历史记录未注明是否执行'; return; end
if any(executed==0), label='LDPC 部分执行：纠错后统计不完整'; return; end
if any(~isfinite([errors bits])) || any(bits<=0) || any(errors<0) || any(errors>bits)
    label='LDPC 已执行；纠错后指标无效：统计块不完整'; return;
end
label=sprintf('LDPC 已执行 | 纠错后 BER %.4g\n纠错后错误数 / 比特数：%.0f / %.0f', ...
    sum(errors)/sum(bits),sum(errors),sum(bits));
end
function value=number(s,name)
value=field(s,name,NaN); if ~isnumeric(value) || ~isscalar(value), value=NaN; end
end
function value=field(s,name,fallback)
value=fallback; if isstruct(s) && isfield(s,name), value=s.(name); end
end
