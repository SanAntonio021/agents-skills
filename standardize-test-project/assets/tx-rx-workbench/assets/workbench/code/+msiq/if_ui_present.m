function v = if_ui_present(out,index)
%IF_UI_PRESENT Pure, backwards-compatible presentation of saved IF results.
% No file or instrument access. Raw diagnostic information stays in detail.
if nargin<1 || ~isstruct(out), out=struct(); end
items=get(out,'observations',{});
if isstruct(items), items=num2cell(items); end
if ~iscell(items), items={}; end
n=numel(items);
if nargin<2 || isempty(index) || ~isnumeric(index) || ~isscalar(index) || ~isfinite(index)
    index=n;
end
index=min(n,max(1,round(index)));
profile=get(out,'profile',struct());
stage=get(profile,'stage','');
isTx=strcmp(stage,'tx_if');
v=struct('summary',{{}},'records',{{}},'metrics',{{}},'state','','detail',{{}});
v.state=stateText(out);
v.summary={v.state};
if strcmp(get(profile,'mode',''),'mock')
    v.summary{end+1}='离线模拟数据；未连接真实仪器';
end
formal=0;
for k=1:n
    o=items{k}; role=get(o,'role',''); m=get(o,'metrics',struct());
    if ismember(role,{'formal','baseline','mode_formal','recovery_baseline'}), formal=formal+1; end
    mark='指标无效';
    if isTx, mark='波形与频谱'; elseif validMetrics(m), mark='指标有效'; end
    v.records{k}=sprintf('%s · %s · %s',number(get(o,'attempt',k),'%.0f'),roleText(role),mark);
end
if n>0
    v.summary{end+1}=sprintf('已保存 %d 条记录，其中正式测量 %d 次',n,formal);
end
elapsed=get(out,'elapsed_s',NaN); remaining=get(out,'estimated_remaining_s',NaN);
if finiteScalar(elapsed), v.summary{end+1}=sprintf('已用时 %.1f 秒',elapsed); end
if finiteScalar(remaining) && remaining>=0 && strcmp(get(out,'status',''),'running')
    v.summary{end+1}=sprintf('预计剩余 %.1f 秒',remaining);
end
if n==0
    v.metrics={'尚无采集记录'};
else
    o=items{index}; m=get(o,'metrics',struct());
    v.metrics={v.records{index}};
    if isTx
        v.metrics{end+1}='本阶段不计算解调指标';
    elseif validMetrics(m)
        v.metrics{end+1}=sprintf('纠错前 BER：%s   错误数 / 统计比特数：%s / %s', ...
            number(get(m,'pre_ber',NaN),'%.6g'), ...
            number(get(m,'pre_error_count',NaN),'%.0f'),number(get(m,'pre_bit_count',NaN),'%.0f'));
        v.metrics{end+1}=sprintf('MER：%s dB',number(get(m,'mer_db',NaN),'%.3f'));
    else
        v.metrics{end+1}=['解调指标无效：' reasonText(get(m,'reason',''))];
        v.metrics{end+1}='纠错前 BER、错误数 / 统计比特数、MER：不可用于比较';
    end
    powers=get(o,'power_dbv2',[]);
    channels=get(get(profile,'scope',struct()),'channels',{});
    if isstring(channels), channels=cellstr(channels); end
    if ischar(channels), channels={channels}; end
    powerParts={};
    if isnumeric(powers)
        for k=1:numel(powers)
            label=sprintf('输入 %d',k);
            if iscell(channels)&&numel(channels)>=k, label=char(string(channels{k})); end
            powerParts{end+1}=sprintf('%s：%s',label,number(powers(k),'%.3f')); %#ok<AGROW>
        end
        if numel(powers)==2 && all(isfinite(powers))
            powerParts{end+1}=sprintf('功率差 %.3f dB',abs(powers(1)-powers(2)));
        end
    end
    if ~isempty(powerParts), v.metrics{end+1}=['带内功率 dB(V²)  ' strjoin(powerParts,'；')]; end
    if isequal(get(o,'clipped',false),true), v.metrics{1}=[v.metrics{1} '；波形削顶，请检查量程']; end
end
errors=get(out,'errors',{});
if isstruct(errors), errors=num2cell(errors); end
replayErrors=get(out,'replay_errors',{});
if isstruct(replayErrors), replayErrors=num2cell(replayErrors); end
if iscell(errors)&&iscell(replayErrors), errors=[errors(:);replayErrors(:)]; end
if iscell(errors) && ~isempty(errors)
    messages=cellfun(@errorText,errors,'UniformOutput',false);
    messages=unique(messages,'stable');
    v.summary{end+1}=['异常原因：' strjoin(messages(1:min(3,numel(messages))),'；')];
end
try
    detail=jsonencode(out,'PrettyPrint',true);
    suffix=sprintf('\n……显示内容已截断，完整信息保留在结果记录中。');
    if numel(detail)>24000, detail=[detail(1:24000-numel(suffix)) suffix]; end
    v.detail=cellstr(splitlines(string(detail)));
catch
    v.detail={'详细记录无法格式化显示'};
end
end

function s=stateText(out)
status=get(out,'status','');
switch status
    case 'preparing', s='正在准备';
    case 'running', s='正在执行';
    case 'completed', s='任务完成';
    case 'paused', s='任务已暂停';
    case 'cancelled', s='任务已停止';
    case 'stop_requested', s='已请求停止';
    case {'stopping','cleanup','shutting_down'}, s='正在收尾';
    case 'shutdown_failed', s='收尾异常';
    case 'save_failed', s='保存失败';
    case 'offline_preview', s='离线发送计划已生成';
    case 'awaiting_apply', s='发送计划已准备，等待执行';
    case 'offline_replay', s='历史记录已载入';
    case 'offline_recomputed', s='离线重新解调完成';
    case 'offline_recomputed_with_errors', s='离线重新解调完成，部分记录失败';
    case {'applied','reused'}, s='AWG 设置已应用';
    case 'ok', s='操作完成';
    case 'stopped', s='AWG 关闭操作结束';
    otherwise, s='等待操作';
end
shutdown=get(out,'shutdown',struct());
if isfield(shutdown,'awg_off_verified')
    if isequal(shutdown.awg_off_verified,true)
        if isequal(get(shutdown,'mock',false),true)
            s=[s '；模拟关闭检查通过'];
        elseif isequal(get(out,'replay',false),true)
            s=[s '；历史记录：当时已核验输出关闭'];
        else
            s=[s '；已核验输出关闭'];
        end
    else
        s=[s '；关闭状态未确认'];
    end
elseif strcmp(status,'stopped')
    state=get(out,'state',struct()); mask=get(state,'outputs',[]);
    if (isnumeric(mask)||islogical(mask)) && numel(mask)==4 && all(isfinite(mask)) && ~any(mask)
        s=[s '；已核验输出关闭'];
    else
        s=[s '；关闭状态未确认'];
    end
end
end

function s=roleText(role)
switch role
    case 'manual', s='单点测量';
    case {'trial','mode_trial'}, s='试采';
    case 'range_trial', s='量程试采';
    case 'balance', s='配平';
    case 'balance_confirmation', s='配平复核';
    case 'power_match', s='功率匹配';
    case 'formal', s='正式测量';
    case 'baseline', s='正式基准';
    case 'mode_formal', s='正式模式比较';
    case 'recovery_baseline', s='恢复基准';
    case 'range_diagnostic', s='量程排查';
    otherwise, s='采集记录';
end
end

function s=reasonText(reason)
r=char(string(reason));
if isempty(r), s='未提供有效的完整统计结果';
elseif contains(r,'sync','IgnoreCase',true), s='同步未通过';
elseif contains(r,'reference','IgnoreCase',true), s='发送参考缺失或不匹配';
elseif contains(r,'block','IgnoreCase',true), s='统计块不完整';
elseif contains(r,'clip','IgnoreCase',true), s='波形削顶';
elseif contains(r,'not_demodulated')||contains(r,'not_recomputed'), s='尚未解调';
elseif contains(r,'denominator','IgnoreCase',true)||contains(r,'bit_count','IgnoreCase',true), s='统计比特数不足';
elseif any(double(r)>127), s=r;
else, s='完整统计检查未通过，具体原因见记录详情';
end
end

function s=errorText(e)
if isstruct(e), r=[char(string(get(e,'identifier',''))) ' ' char(string(get(e,'message','')))];
else, r=char(string(e)); end
r=lower(r);
if contains(r,'cancel'), s='操作被停止';
elseif contains(r,'shutdown')||contains(r,'awg off'), s='AWG 关闭核验失败';
elseif contains(r,'save')||contains(r,'write_json'), s='结果保存失败';
elseif contains(r,'wiring'), s='接线尚未确认或已变化';
elseif contains(r,'authorization'), s='尚未确认设备操作授权';
elseif contains(r,'plandrift'), s='发送设置已变化，需重新准备计划';
elseif contains(r,'planconfirmation'), s='发送计划尚未确认';
elseif contains(r,'amplitude'), s='发送幅度缺失或超出批准范围';
elseif contains(r,'serial')||contains(r,'protocol'), s='板卡通信或协议确认未通过';
elseif contains(r,'mapping'), s='板卡物理通道映射未确认';
elseif contains(r,'fresh')||contains(r,'timeout'), s='未能确认新采集完成';
elseif contains(r,'reference'), s='发送参考缺失或不匹配';
elseif contains(r,'sync'), s='波形同步失败';
elseif contains(r,'block')||contains(r,'denominator')||contains(r,'invalidmetrics'), s='完整统计指标未通过检查';
elseif contains(r,'clip'), s='波形削顶';
elseif contains(r,'range'), s='量程或批准范围检查未通过';
elseif contains(r,'capacity')||contains(r,'memory'), s='播放容量或模式检查未通过';
elseif contains(r,'replaypath'), s='历史结果目录无效';
elseif contains(r,'channel'), s='采集通道设置不符合要求';
elseif contains(r,'rate')||contains(r,'window'), s='实际采样率或采集窗口不符合要求';
elseif contains(r,'board'), s='板卡状态检查或设置失败';
else, s='操作未完成，请查看技术详情定位异常';
end
end

function yes=validMetrics(m)
bits=get(m,'pre_bit_count',NaN); errors=get(m,'pre_error_count',NaN);
ber=get(m,'pre_ber',NaN);
yes=isequal(get(m,'valid',false),true) && finiteScalar(bits) && bits>0 && ...
    finiteScalar(errors) && errors>=0 && errors<=bits && finiteScalar(ber) && ber>=0 && ber<=1;
end
function yes=finiteScalar(x)
yes=isnumeric(x)&&isscalar(x)&&isfinite(x);
end
function s=number(x,format)
if finiteScalar(x), s=sprintf(format,x); else, s='—'; end
end
function value=get(s,name,fallback)
value=fallback;
if isstruct(s)&&isscalar(s)&&isfield(s,name), value=s.(name); end
end
