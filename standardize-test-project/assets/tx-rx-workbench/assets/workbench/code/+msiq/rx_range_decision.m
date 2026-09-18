function out=rx_range_decision(raw,status,policy)
%RX_RANGE_DECISION Full-frame display occupancy and independent ADC clipping.
out=struct('valid',false,'reason','','needs_adjustment',false,'target_vdiv',[], ...
    'current_vdiv',[],'channels',{{}},'per_channel',struct([]));
try
    target=field(policy,'target_divisions',7); margin=field(policy,'edge_margin_divisions',.5);
    divisions=field(status,'vertical_divisions',8);
    computed=strcmp(field(policy,'range_strategy','legacy'),'computed');
    legal=sort(unique(field(policy,'ranges_vdiv',[])));
    assert(isfinite(target)&&target>0&&isfinite(margin)&&margin>=0&& ...
        target<=divisions-2*margin && (computed || (~isempty(legal)&&all(isfinite(legal)&legal>0))), ...
        'RX_Workbench:RangePolicy','量程档位、目标占格或边缘余量无效');
    assert(isfield(raw,'channels')&&~isempty(raw.channels),'RX_Workbench:RangeData','缺少完整波形');
    out.channels={raw.channels.channel};
    for k=1:numel(raw.channels)
        r=raw.channels(k); x=double(r.samples(:));
        assert(numel(x)>1&&isreal(x)&&all(isfinite(x)),'RX_Workbench:RangeData','波形无效');
        c=status.channels(strcmp({status.channels.channel},r.channel));
        assert(isscalar(c)&&isfinite(c.offset_v)&&isfinite(c.vertical_scale_v_per_div)&& ...
            c.vertical_scale_v_per_div>0,'RX_Workbench:RangeReadback','缺少可信量程或偏移');
        scale=c.vertical_scale_v_per_div; low=min(x); high=max(x); clipped=false; known=false;
        d=field(r,'descriptor',struct());
        if all(isfield(d,{'vertical_gain','vertical_offset','comm_type'}))
            assert(isfinite(d.vertical_gain)&&d.vertical_gain>0&&isfinite(d.vertical_offset)&& ...
                ismember(d.comm_type,[0 1]),'RX_Workbench:RangeData','ADC 描述符无效');
            bits=8+8*d.comm_type; codes=(x+d.vertical_offset)/d.vertical_gain;
            clipped=any(codes<=-2^(bits-1)+.5|codes>=2^(bits-1)-1-.5); known=true;
        elseif isequal(field(raw,'mock',false),true)
            known=true; clipped=any(abs(x+c.offset_v)>=divisions*scale/2);
        end
        assert(known,'RX_Workbench:RangeData','缺少 ADC 削顶判据');
        assert(clipped || high>low,'RX_Workbench:RangeData','无交流信号，不能自动调量程');
        needed=max([(high-low)/target,abs(low+c.offset_v)/(divisions/2-margin), ...
            abs(high+c.offset_v)/(divisions/2-margin)]);
        safe_needed=max(abs([low high]+c.offset_v))/(divisions/2-margin);
        safe=~clipped && scale>=safe_needed-max(1e-12,safe_needed*1e-8);
        if computed
            next=needed; reason='按完整波形计算量程';
            if clipped, next=2*scale; reason='ADC 削顶，扩大量程后重新检查'; end
            if safe && ismember(r.channel,field(policy,'accept_actual_channels',{}))
                next=scale; reason='实际回读量程的新波形满足余量';
            end
            assert(isfinite(next)&&next>0,'RX_Workbench:RangeBoundary','计算量程无效');
        elseif clipped
            index=find(legal>scale*(1+1e-8),1); reason='ADC 削顶，逐档扩大';
        else
            index=find(legal>=needed*(1-1e-10),1); reason='按波形边界选择最小合适量程';
        end
        if ~computed
            assert(~isempty(index),'RX_Workbench:RangeBoundary','没有满足余量的批准量程');
            next=legal(index);
        end
        different=abs(next-scale)>max(1e-12,scale*1e-8);
        out.current_vdiv(k)=scale; out.target_vdiv(k)=next;
        item=struct('channel',r.channel,'minimum_v',low,'maximum_v',high, ...
            'scope_offset_v',c.offset_v,'adc_clipped',clipped,'occupied_divisions',(high-low)/scale, ...
            'safe',safe,'needed_vdiv',needed,'safe_vdiv',safe_needed, ...
            'reason',reason,'needs_adjustment',different);
        if k==1, out.per_channel=item; else, out.per_channel(k)=item; end
    end
    out.valid=true; out.safe=all([out.per_channel.safe]); out.needs_adjustment=any([out.per_channel.needs_adjustment]);
    if out.needs_adjustment
        reasons={};
        for k=1:numel(out.channels)
            if out.target_vdiv(k)>out.current_vdiv(k), why='波形过大';
            elseif out.target_vdiv(k)<out.current_vdiv(k), why='波形偏小'; else, continue; end
            reasons{end+1}=[out.channels{k} ' ' why]; %#ok<AGROW>
        end
        out.reason=strjoin(reasons,'；');
    else, out.reason='量程合适'; end
catch ex
    out.reason=ex.message;
end
end
function v=field(s,k,f)
v=f; if isfield(s,k)&&~isempty(s.(k)),v=s.(k);end
end
