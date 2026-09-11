function raw=rx_observation_freshness(raw,previous,status)
%RX_OBSERVATION_FRESHNESS Identify repeated instrument records, not poll times.
if nargin<2 || isempty(previous), previous=struct(); end
if nargin<3, status=struct(); end
raw.new_data=false;
raw.freshness_known=true;
active_count=0;
for k=1:numel(raw.channels)
    record=raw.channels(k);
    active=~isempty(record.samples);
    if isfield(status,'channels')
        n=find(strcmp({status.channels.channel},record.channel),1);
        if ~isempty(n), active=active && strcmpi(status.channels(n).trace_state,'ON'); end
    end
    [signature,known]=record_signature(record);
    fresh=active;
    if known && isfield(previous,'channels') && ~isempty(previous.channels)
        n=find(strcmp({previous.channels.channel},record.channel),1);
        if ~isempty(n)
            [old_signature,old_known]=record_signature(previous.channels(n));
            fresh=active && (~old_known || ~isequaln(signature,old_signature));
        end
    end
    raw.channels(k).fresh=fresh;
    raw.channels(k).freshness_known=known;
    raw.channels(k).freshness_signature=signature;
    if active
        active_count=active_count+1;
        raw.new_data=raw.new_data || fresh;
        raw.freshness_known=raw.freshness_known && known;
    end
end
if active_count==0
    raw.observation_status='所选通道未开启或无数据';
elseif ~raw.freshness_known
    raw.observation_status='观察中，采集时间未确认';
elseif ~raw.new_data
    raw.observation_status='等待新触发或平均更新';
else
    raw.observation_status='已读取新波形';
end
% Polling wall-clock time is never promoted to a physical trigger time.
if isfield(raw,'captured_at'), raw.observed_at=raw.captured_at; end
if ~raw.new_data && isfield(previous,'captured_at')
    raw.captured_at=previous.captured_at;
end
raw.acquisition_time_confirmed=false;
raw.channels_same_trigger_confirmed=false;
% Separate local arrival time from the instrument's physical trigger time.
if raw.new_data
    raw.last_new_data_at=datetime('now');
elseif isfield(previous,'last_new_data_at')
    raw.last_new_data_at=previous.last_new_data_at;
else
    raw.last_new_data_at=NaT;
end
end

function [signature,known]=record_signature(record)
signature=struct(); known=false;
if ~isfield(record,'descriptor'), return; end
d=record.descriptor;
if isfield(d,'trigger_time_bytes') && numel(d.trigger_time_bytes)==16 && any(d.trigger_time_bytes)
    signature.trigger_time_bytes=uint8(d.trigger_time_bytes(:)); known=true;
end
if isfield(d,'result_update_id') && ~isempty(d.result_update_id)
    signature.result_update_id=d.result_update_id; known=true;
end
if isfield(d,'sweeps_per_acq')
    signature.sweeps_per_acq=d.sweeps_per_acq;
end
% Include calibration/record geometry so a setting change refreshes the plot.
for name={'horizontal_interval_s','horizontal_offset_s','vertical_gain','vertical_offset'}
    if isfield(d,name{1}), signature.(name{1})=d.(name{1}); end
end
signature.sample_count=numel(record.samples);
end
