function details = rx_dashboard(output_path, raw, validation, context, result)
%RX_DASHBOARD Eleven receive panels using actual saved observations.
if nargin<5 || ~isstruct(result), result=struct(); end
if nargin<4 || ~isstruct(context), context=struct(); end
if nargin<3 || ~isstruct(validation), validation=struct(); end
if nargin<2 || ~isstruct(raw), raw=struct(); end
output_path=char(string(output_path));
[output_dir,~,ext]=fileparts(output_path);
if isempty(ext), output_path=[output_path '.png']; end
if ~isempty(output_dir) && ~isfolder(output_dir), mkdir(output_dir); end
status=dashboard_status(result,validation); decoded=first_decoded(result);
eq=primary_equalizer(decoded); stream=primary_stream(decoded);
tx_ref=field_or(context,'tx_ref',struct()); cfg=field_or(context,'cfg',struct());
frame=field_or(tx_ref,'frame',struct());
waveform=field_or(tx_ref,'waveform_config',field_or(cfg,'waveform',struct()));
order=field_or(tx_ref,'modulation_order',field_or(frame,'modulation_order',field_or(waveform,'modulation_order',NaN)));
ideal=[];
if isscalar(order) && ismember(order,[4 16 64 256])
    ideal=qammod((0:order-1).',order,'UnitAveragePower',true);
end
modulation='';
if order==4, modulation='QPSK '; elseif ~isempty(ideal), modulation=sprintf('%dQAM ',order); end
figure_title=[modulation '接收处理总览'];
if ~strcmp(status,'decoded'), figure_title=[figure_title '：' status_text(status)]; end
options=field_or(context,'plot_options',struct());
canvas=field_or(options,'figure_size',[1920 1080]);
validateattributes(canvas,{'numeric'},{'vector','numel',2,'positive','finite'});
W=canvas(1); H=canvas(2);
fig=figure('Visible','off','Color','w','Units','pixels','Position',[20 20 W H], ...
    'InvertHardcopy','off','DefaultAxesFontName','Microsoft YaHei UI', ...
    'DefaultTextFontName','Microsoft YaHei UI','DefaultAxesFontSize',8);
cleanup=onCleanup(@() close_if_valid(fig));
setappdata(fig,'canvas_size',canvas);
label(fig,[24 H-43 W-48 37],figure_title,15,true);
margin=10; gap=6; bottom=8; top=H-45;
cw=(W-2*margin-3*gap)/4; heights=(top-bottom-2*gap)*[1 1 1]/3; panels=zeros(11,4);
for row=1:3
    for col=1:4
        index=(row-1)*4+col;
        if row==2 && col>2, continue; end
        if row==3, index=col+6; end
        panels(index,:)=[margin+(col-1)*(cw+gap),top-sum(heights(1:row))-(row-1)*gap,cw,heights(row)];
    end
end
panels(11,:)=[panels(3,1),panels(5,2),2*cw+gap,heights(2)];
titles={'1 原始采集波形','2 通道信号频谱','3 重复ZC同步', ...
    '4 训练窗口对齐搜索','5 均衡后训练星座','6 业务区相位跟踪', ...
    '7 业务星座：均衡前','8 业务星座：固定均衡后', ...
    '9 业务星座：联合跟踪后','10 业务星座：最终导频校正后','11 业务区联合跟踪误差'};
texts=cellfun(@(s) {s},titles,'UniformOutput',false);
for k=1:11
    p=panels(k,:); label(fig,[p(1) p(2)+p(4)-25 p(3) 24],titles{k},10,true);
end
blue=[0 .35 .67]; orange=[.81 .32 .07]; colors=[blue;orange];
[records,channels,origin,time_limits]=msiq.plotting.rx_capture_channels(raw,context,decoded);
rate=field_or(frame,'symbol_rate_hz',field_or(waveform,'symbol_rate_hz',NaN));
rolloff=field_or(frame,'rrc_rolloff',field_or(waveform,'rolloff',NaN));
edge=rate*(1+rolloff)/2;
if ~isfinite(edge), edge=field_or(frame,'occupied_bandwidth_hz',NaN)/2; end
center_hz=field_or(waveform,'if_center_hz',NaN);
band_edges=[];
if isfinite(edge) && isfinite(center_hz)
    band_edges=unique([max(0,abs(center_hz)-edge),abs(center_hz)+edge]);
    band_edges=band_edges(band_edges>0);
end
% Keep the overview readable: show the occupied band plus one equivalent
% signal-band width of adjacent out-of-band spectrum. Full Nyquist traces
% remain available from the captured data for separate diagnostics.
spectrum_limit_hz=NaN;
if isfinite(edge) && edge>0 && isfinite(center_hz)
    spectrum_limit_hz=abs(center_hz)+2*edge;
end
for k=1:2
    a=split_axis(fig,panels(1,:),k);
    b=split_axis(fig,panels(2,:),k);
    if numel(records)<k || channels(k).sample_count<2
        placeholder(a,'采集波形不可用'); placeholder(b,'通道频谱不可用'); continue;
    end
    record=records(k); d=channels(k);
    values=double(record.samples(:)); time=double(field_or(record,'time_axis_s',[])); time=time(:);
    if numel(time)==numel(values) && all(isfinite(time)) && all(diff(time)>0) && isfinite(origin)
        indices=msiq.plotting.rx_envelope_indices(values,2800);
        plot(a,(time(indices)-origin)*1e6,values(indices),'Color',colors(k,:),'LineWidth',.45);
        xlim(a,time_limits); ylim(a,d.voltage_limits);
        ticks=sparse_voltage_ticks(d.voltage_limits,a.YTick);
        yticks(a,ticks); a.YTickLabel=numeric_labels(ticks); a.YAxis.Exponent=0;
        channels(k).voltage_ticks=ticks;
        ylabel(a,'电压（V）','FontSize',8);
        if k==1, a.XTickLabel=[]; else, xlabel(a,'采集时间（μs）'); end
        grid(a,'on');
    else
        placeholder(a,'缺少有效采集时间轴');
    end
    note_value=sprintf('%s  有效值 %.3g V  峰峰值 %.3g V',d.name,d.rms_v,d.vpp_v);
    in_axes_note(a,d.name,'nw');
    in_axes_note(a,sprintf('有效值 %.3g V\n峰峰值 %.3g V',d.rms_v,d.vpp_v),'ne');
    texts{1}{end+1}=note_value;
    if isfinite(d.sample_rate_hz) && d.sample_rate_hz>0 && isreal(values) && all(isfinite(values))
        nfft=min(65536,2^floor(log2(numel(values))));
        [voltage_density,freq]=pwelch(values,hann(nfft),floor(nfft/2),nfft,d.sample_rate_hz,'onesided');
        [channels(k),power_label]=inband_power(channels(k),freq,voltage_density,edge,center_hz);
        texts{2}{end+1}=[d.name '  ' power_label];
        power=voltage_density;
        unit='dB(V²/Hz)';
        if isfinite(d.impedance_ohm), power=power/d.impedance_ohm*1000; unit='dBm/Hz'; end
        psd=10*log10(max(power,realmin));
        plot(b,freq/1e9,psd,'Color',colors(k,:),'LineWidth',.6);
        display_limit_hz=d.frequency_limit_hz;
        if isfinite(spectrum_limit_hz)
            display_limit_hz=min(display_limit_hz,spectrum_limit_hz);
        end
        xlim(b,[0 display_limit_hz/1e9]);
        shown=psd(freq<=display_limit_hz & isfinite(psd));
        if ~isempty(shown)
            lim=[floor((min(shown)-3)/10)*10 ceil((max(shown)+3)/10)*10];
            if diff(lim)<10, lim(1)=lim(2)-10; end
            ylim(b,lim); yticks(b,linspace(lim(1),lim(2),3)); b.YTickLabel=numeric_labels(b.YTick);
        end
        xticks(b,linspace(0,display_limit_hz/1e9,5)); b.XTickLabel=numeric_labels(b.XTick);
        for band_edge=band_edges(band_edges<=display_limit_hz)
            xline(b,band_edge/1e9,'--','Color',[.4 .4 .4]);
        end
        ylabel(b,unit,'Interpreter','none','FontSize',8);
        if k==1, b.XTickLabel=[]; else, xlabel(b,'频率（GHz）'); end
        grid(b,'on');
        in_axes_note(b,d.name,'nw');
        in_axes_note(b,power_label,'ne');
        in_axes_note(b,sprintf('%.3g GSa/s',d.sample_rate_hz/1e9),'se');
        if k==2 && ~isempty(band_edges), in_axes_note(b,'虚线：理论带边','sw'); end
    else
        placeholder(b,'缺少有效样点或采样率');
        channels(k).inband_power_reason='缺少有效样点或采样率';
    end
end
rate_notes=arrayfun(@(d) sprintf('%s %.3g GSa/s',d.name,d.sample_rate_hz/1e9), ...
    channels,'UniformOutput',false);
rate_note=strjoin(rate_notes,'；');
power_note='50 Ω';
in_axes_note(a,power_note,'se'); texts{1}{end+1}=power_note;
spectrum_footer=strjoin({rate_note,'理论带边'},'；');
if isempty(band_edges), spectrum_footer=rate_note; end
texts{2}{end+1}=spectrum_footer;
stage_raw=struct('channels',records);
[stages,stage_info]=msiq.plotting.rx_constellation_stages(stage_raw,context,decoded);
p=panels(3,:); a=plot_axis(fig,p,44,28);
sync=field_or(decoded,'synchronization',struct()); metric=field_or(sync,'repeat_metric_trace',[]);
if ~isempty(metric) && stage_info.time_available && numel(metric)==numel(stage_info.time_us)
    metric=metric(:); time=stage_info.time_us(:);
    map_origin=field_or(stage_info.time_mapping,'capture_origin_s',origin);
    time=time+(map_origin-origin)*1e6;
    plot(a,time,metric,'Color',blue,'LineWidth',.6); hold(a,'on');
    peaks=field_or(sync,'repeat_peak_locations',[]); peaks=peaks(:);
    peaks=peaks(isfinite(peaks)&peaks>=1&peaks<=numel(metric)&peaks==fix(peaks));
    plot(a,time(peaks),metric(peaks),'o','Color',orange,'MarkerSize',4);
    chosen=NaN; selected=field_or(sync,'sync_start_sample',NaN);
    if ~isempty(peaks) && isfinite(selected)
        [~,chosen]=min(abs(peaks-selected));
        plot(a,time(peaks(chosen)),metric(peaks(chosen)),'o','Color',[.75 .1 .13], ...
            'MarkerFaceColor',[.75 .1 .13],'MarkerSize',6);
    end
    xlim(a,time_limits); ylim(a,[0 max(1.2,1.2*max(metric))]); grid(a,'on');
    xlabel(a,'采集时间（μs）'); ylabel(a,'归一化相关度');
    note=sprintf('同步峰 %d 个',numel(peaks));
    if isfinite(chosen), note=sprintf('%s；选中第 %d 个',note,chosen); end
    in_axes_note(a,note,'ne'); texts{3}{end+1}=note;
else
    placeholder(a,'同步曲线或采集时间映射不可用');
end
p=panels(4,:); a=plot_axis(fig,p,66,28);
offsets=field_or(eq,'training_timing_offsets_samples',[]); nmse=field_or(eq,'training_timing_nmse',[]);
if ~isempty(offsets) && numel(offsets)==numel(nmse)
    offsets=offsets(:); nmse=nmse(:); valid=isfinite(offsets)&isfinite(nmse)&nmse>=0;
    offsets=offsets(valid); nmse=10*log10(max(nmse(valid),realmin));
    if ~isempty(offsets)
        plot(a,offsets,nmse,'o','Color',blue,'MarkerSize',4); hold(a,'on');
        best=field_or(eq,'training_timing_offset_samples',NaN);
        plot(a,offsets(offsets==best),nmse(offsets==best),'o','Color',[.75 .1 .13], ...
            'MarkerFaceColor',[.75 .1 .13],'MarkerSize',6);
        xline(a,0,'--','Color',[.5 .5 .5]);
        xlim(a,[min(offsets)-.75 max(offsets)+.75]);
        step=max(1,ceil((max(offsets)-min(offsets))/6)); xticks(a,min(offsets):step:max(offsets));
        center=(min(nmse)+max(nmse))/2; span=max(1,range(nmse)*1.5); ylim(a,center+[-.5 .5]*span);
        grid(a,'on'); ylabel(a,'训练归一化均方误差（dB）');
        xlabel(a,{'相对标称训练位置偏移','（接收处理采样点）'});
        note=sprintf('选中 %+g 点',best); sps=field_or(eq,'processing_samples_per_symbol',NaN);
        if isfinite(sps)&&sps>0, note=sprintf('%s；每点为 %.3g 个符号周期',note,1/sps); end
        in_axes_note(a,note,'ne'); texts{4}{end+1}=note;
    else
        placeholder(a,'没有有效训练窗口搜索结果');
    end
else
    placeholder(a,'训练窗口搜索不可用');
end
p=panels(5,:); a=stage_axis(fig,p,true);
training=field_or(eq,'training_symbols_equalized',[]); training_ideal=training_reference(tx_ref,decoded);
training_nmse_db=10*log10(field_or(eq,'training_nmse',NaN));
if ~isempty(training)
    constellation(a,training,training_ideal,point_limit({training,training_ideal}),orange);
    note=[number_text(training_nmse_db,'%.2f') ' dB'];
    lines={['训练归一化均方误差 ' note],sprintf('训练符号 %d 个',numel(training))};
    texts{5}{end+1}=['训练归一化均方误差 ' note];
    if ~isempty(training_ideal)
        lines{2}=[lines{2} '；□ 理想符号'];
    end
    h=in_axes_note(a,lines,'ne');
    h.Position=[.5 .5 0]; h.HorizontalAlignment='center'; h.VerticalAlignment='middle';
else
    placeholder(a,'训练星座不可用');
end
tracking=field_or(eq,'tracking',struct());
p=panels(6,:); a=plot_axis(fig,p,48,28); phase=field_or(tracking,'phase_log',[]);
if ~isempty(phase) && isfinite(rate) && rate>0 && field_or(tracking,'enabled',true)
    time=(0:numel(phase)-1).'/rate*1e6;
    plot(a,time,phase(:)*180/pi,'Color',blue,'LineWidth',.75);
    xlim(a,[0 max(numel(phase)/rate*1e6,eps)]); grid(a,'on');
    xlabel(a,'业务区时间（μs）'); ylabel(a,'累计相位补偿量（°）');
else
    placeholder(a,'联合相位跟踪不可用');
end
limits=[point_limit([stages(1) {ideal}]),repmat(point_limit([stages(2:4) {ideal}]),1,3)];
for k=1:4
    p=panels(k+6,:); a=stage_axis(fig,p,k==4);
    if stage_info.stage_available(k)
        constellation(a,stages{k},ideal,limits(k),blue);
        note='';
    else
        placeholder(a,'本阶段业务星座不可用'); note='未保存或无法核实本阶段数据';
    end
    if ~isempty(note), foot(fig,p,note,8.5); end
    texts{k+6}{end+1}=note;
    if k==4 && ~isempty(decoded)
        lines=final_metrics(stream);
        setappdata(a,'side_metrics',lines);
        texts{10}=[texts{10} lines];
    end
end
stats=msiq.plotting.rx_tracking_error_stats(tracking,frame,cfg,513);
p=panels(11,:); a=plot_axis(fig,p,58,30);
if stats.available
    hold(a,'on');
    h1=plot(a,stats.window_time_us,stats.window_rms,'Color',blue,'LineWidth',1.6);
    h2=scatter(a,stats.window_peak_time_us,stats.window_peak,24,orange,'^','filled');
    xlim(a,[0 stats.duration_us]); ylim(a,[0 max(.02,1.30*max(stats.window_peak))]); grid(a,'on');
    xlabel(a,'业务区时间（μs）'); ylabel(a,'归一化误差幅度');
    legend(a,[h1 h2],{'窗内均方根误差','窗内最大误差'}, ...
        'Orientation','horizontal','Box','off','Color','w','FontSize',7,'Location','northeast');
    in_axes_note(a,sprintf('窗长 %.3f μs',stats.window_duration_us),'se');
else
    placeholder(a,stats.reason);
end
notice='';
if stats.rejection_visible
    notice=sprintf('拒绝更新：%d 个',stats.rejected_count);
    if isfinite(stats.rejected_fraction), notice=sprintf('%s（%.2f%%）',notice,100*stats.rejected_fraction); end
end
if ~isempty(notice)
    setappdata(a,'footer_clearance',20);
    h=label(fig,[p(1)+68 p(2)+1 p(3)-84 20],notice,8.5,false); h.HorizontalAlignment='left';
    texts{11}{end+1}=notice;
end
payload_counts=cellfun(@numel,stages);
if all(payload_counts==payload_counts(1)) && payload_counts(1)>0
    shared_note=sprintf('业务符号 %d 个',payload_counts(1));
    label(fig,[panels(7,1) panels(7,2)+1 panels(10,1)+panels(10,3)-panels(7,1) 20], ...
        shared_note,8.5,false);
    texts{7}{end+1}=shared_note;
end
drawnow; axes_handles=findall(fig,'Type','axes');
set(axes_handles,'Box','on','TickDir','out','GridAlpha',.13,'Layer','top');
drawnow; fit_stage_axes(fig); place_side_metrics(fig); issues=verify_layout(fig,panels);
set(fig,'PaperUnits','inches','PaperPosition',[0 0 W/120 H/120],'PaperSize',[W/120 H/120]);
archive_dir=fullfile(output_dir,'data');
if ~isfolder(archive_dir), archive_dir=fullfile(output_dir,'diagnostics'); end
msiq.plotting.save_replot_figure(fig,output_path,120);
plot_cleanup=msiq.plot_archive('begin',output_dir,archive_dir); %#ok<NASGU>
if ~msiq.plot_archive('export',fig,output_path,'print',120), print(fig,output_path,'-dpng','-r120'); end
compact_info=rmfield(stage_info,{'time_us','payload_positions_service'});
details=struct('output_path',output_path,'status',status,'panel_count',11, ...
    'axis_count',numel(axes_handles),'decoded_pair_count',double(~isempty(decoded)), ...
    'resolution_dpi',120,'figure_title',figure_title,'modulation_order',order, ...
    'reference_point_count',numel(ideal),'stage_available',stage_info.stage_available, ...
    'stage_symbol_counts',cellfun(@numel,stages),'constellation_counts',cellfun(@numel,stages), ...
    'stages_info',compact_info,'constellation_limits',limits,'channels',channels, ...
    'tracking_error',stats,'training_nmse_db',training_nmse_db, ...
    'failure_reason',field_or(result,'reason',field_or(validation,'reason','')), ...
    'panel_texts',{texts},'layout',struct('issues',{issues}));
clear cleanup;
end

function limit=point_limit(groups)
extent=0;
for k=1:numel(groups)
    values=groups{k}; values=values(isfinite(values));
    if ~isempty(values), extent=max(extent,max([abs(real(values(:)));abs(imag(values(:)))])); end
end
limit=max(1.1,ceil(1.03*extent*10)/10);
end

function ideal=training_reference(tx_ref,decoded)
ideal=[]; pairs=field_or(tx_ref,'pairs',struct([])); name=field_or(decoded,'payload_pair','');
for k=1:numel(pairs)
    candidate=field_or(pairs(k),'name','');
    if numel(pairs)>1 && ~strcmpi(candidate,name) && ~strcmpi(candidate,['pair_' name]), continue; end
    known=field_or(pairs(k),'receiver_known',struct([]));
    if ~isempty(known), ideal=unique(field_or(known(1),'training_symbols',[])); end
    return;
end
end

function lines=final_metrics(stream)
fec=field_or(stream,'fec',struct());
lines={}; evm=field_or(stream,'evm_rms',NaN);
if isfinite(evm), lines{end+1}=sprintf('EVM %.2f%%',100*evm); end
prefixes={'pre_fec','post_fec'}; labels={'前BER','后BER'};
for k=1:2
    ber=field_or(stream,[prefixes{k} '_ber'],NaN);
    metric=sprintf('%s %.3g',labels{k},ber);
    errors=field_or(fec,[prefixes{k} '_bit_error_count'],NaN);
    total=field_or(fec,[prefixes{k} '_bit_count'],NaN);
    if isfinite(errors) && isfinite(total)
        metric=sprintf('%s; %d/%d位',metric,errors,total);
    end
    if isfinite(ber), lines{end+1}=metric; end %#ok<AGROW>
end
errors=field_or(stream,'block_error_count',NaN); total=field_or(stream,'block_count',NaN);
if isfinite(errors) && isfinite(total), lines{end+1}=sprintf('错码块 %d/%d',errors,total); end
if isempty(lines), lines={'解调指标未保存'}; end
end

function value=number_text(value,format)
if isscalar(value) && ~isnan(value), value=sprintf(format,value); else, value='未记录'; end
end

function labels=numeric_labels(values)
values(abs(values)<max(abs(values))*1e-12)=0;
labels=arrayfun(@(v) sprintf('%.3g',v),values,'UniformOutput',false);
end

function [channel,label_text]=inband_power(channel,frequency_hz,voltage_density,edge_hz,center_hz)
channel.inband_power_dbm=NaN;
channel.inband_rms_v=NaN;
channel.inband_frequency_limits_hz=[NaN NaN];
channel.inband_power_available=false;
channel.inband_power_reason='理论带边参数未保存';
label_text='带内功率不可用';
if ~isfinite(edge_hz) || edge_hz<=0 || ~isfinite(center_hz)
    return;
end
center_hz=abs(center_hz);
if center_hz<=eps(max(1,edge_hz))
    requested=[0 edge_hz];
else
    requested=[max(0,center_hz-edge_hz) center_hz+edge_hz];
end
available=[max(requested(1),frequency_hz(1)), ...
    min([requested(2),frequency_hz(end),channel.frequency_limit_hz])];
channel.inband_frequency_limits_hz=available;
if available(2)<=available(1)
    channel.inband_power_reason='理论频段不在采集范围内';
    return;
end
mask=frequency_hz>=available(1) & frequency_hz<=available(2) & isfinite(voltage_density);
if nnz(mask)<2
    channel.inband_power_reason='带内频谱点不足';
    return;
end
voltage_squared=trapz(frequency_hz(mask),voltage_density(mask));
if ~isfinite(voltage_squared) || voltage_squared<0
    channel.inband_power_reason='带内积分失败';
    return;
end
channel.inband_rms_v=sqrt(voltage_squared);
channel.inband_power_available=true;
if available(1)>requested(1) || available(2)<requested(2)
    channel.inband_power_reason='理论频段按可用范围积分';
else
    channel.inband_power_reason='';
end
if isfinite(channel.impedance_ohm) && channel.impedance_ohm>0
    channel.inband_power_dbm=10*log10(max(voltage_squared/channel.impedance_ohm*1000,realmin));
    label_text=sprintf('带内功率 %.2f dBm',channel.inband_power_dbm);
else
    label_text='带内功率不可用';
end
end

function ticks=sparse_voltage_ticks(limits,candidates)
target=diff(limits)/2; decade=10^floor(log10(target));
steps=[1 2 2.5 4 5 10]*decade;
step=steps(find(steps>=target*(1-1e-12),1));
ticks=(ceil(limits(1)/step-1e-10):floor(limits(2)/step+1e-10))*step;
ticks=max(limits(1),min(limits(2),ticks));
if numel(ticks)<2 && numel(candidates)>=2, ticks=candidates([1 end]); end
end

function h = label(fig,rect,value,font_size,bold)
canvas = getappdata(fig,'canvas_size');
h = annotation(fig,'textbox',rect./canvas([1 2 1 2]), ...
    'String',value,'FontName','Microsoft YaHei UI','FontSize',font_size, ...
    'EdgeColor','none','Interpreter','none','Margin',0, ...
    'VerticalAlignment','middle','HorizontalAlignment','center','FitBoxToText','off');
if bold, h.FontWeight = 'bold'; end
setappdata(h,'allocated_rect',rect);
end

function foot(fig,p,value,font_size)
if ~isempty(value), label(fig,[p(1) p(2)+1 p(3) 20],value,font_size,false); end
end

function a = plot_axis(fig,p,bottom,top)
canvas = getappdata(fig,'canvas_size');
% The bottom row has a 10 px outer margin. Reserve a little more room for
% tick labels so the axes and the panel footer cannot touch.
if p(2) <= 12
    bottom = max(bottom,86);
end
a = axes(fig,'Units','normalized','Position', ...
    [p(1)+68 p(2)+bottom p(3)-84 p(4)-bottom-top]./canvas([1 2 1 2]));
setappdata(a,'panel_rect',p);
setappdata(a,'footer_clearance',4);
end

function a = stage_axis(fig,p,has_notes)
canvas = getappdata(fig,'canvas_size');
rect = stage_rect(p,has_notes);
a = axes(fig,'Units','normalized','Position',rect./canvas([1 2 1 2]),'FontSize',7);
setappdata(a,'panel_rect',p);
setappdata(a,'stage_has_notes',has_notes);
if p(2)>20, setappdata(a,'footer_clearance',4); end
end

function fit_stage_axes(fig)
% Fit the complete axes decoration, using MATLAB's measured font extents.
canvas=getappdata(fig,'canvas_size');
for pass=1:3
    drawnow;
    for a=reshape(findall(fig,'Type','axes'),1,[])
        if strcmp(a.Visible,'off'), continue; end
        p=getappdata(a,'panel_rect');
        if isempty(p), continue; end
        inset=a.TightInset.*canvas([1 2 1 2]);
        lower=24;
        if isappdata(a,'footer_clearance'), lower=getappdata(a,'footer_clearance')+4; end
        if ~isappdata(a,'stage_has_notes')
            box=a.Position.*canvas([1 2 1 2]);
            lo=max(box(2),p(2)+lower+inset(2));
            hi=min(box(2)+box(4),p(2)+p(4)-28-inset(4));
            a.Position=[box(1) lo box(3) hi-lo]./canvas([1 2 1 2]);
            continue;
        end
        top=28;
        side=min(p(3)-sum(inset([1 3]))-6,p(4)-lower-top-sum(inset([2 4])));
        left=p(1)+inset(1)+(p(3)-sum(inset([1 3]))-side)/2;
        if isappdata(a,'side_metrics'), left=p(1)+inset(1)+3; end
        a.Position=[left p(2)+lower+inset(2) side side]./canvas([1 2 1 2]);
    end
end
drawnow;
end

function rect = stage_rect(p,has_notes) %#ok<INUSD>
% In-frame notes do not reserve any exterior area.
top=36;
side = min(p(3)-60,p(4)-56-top);
left = p(1)+(p(3)-side)/2;
rect = [left p(2)+56 side side];
end

function h=in_axes_note(a,value,corner,avoid_data)
if nargin<4, avoid_data=false; end
x=.98; y=.97; ha='right'; va='top';
if contains(corner,'w'), x=.02; ha='left'; end
if contains(corner,'s'), y=.03; va='bottom'; end
h=text(a,x,y,value,'Units','normalized','HorizontalAlignment',ha, ...
    'VerticalAlignment',va,'FontName','Microsoft YaHei UI','FontSize',6.5, ...
    'Interpreter','none','BackgroundColor',[1 1 1],'Margin',1,'Clipping','on', ...
    'Tag','rx_in_axes_note');
setappdata(h,'avoid_data',avoid_data);
canvas=getappdata(ancestor(a,'figure'),'canvas_size');
if avoid_data && canvas(1)<1600, h.FontSize=5.5; end
end

function place_side_metrics(fig)
canvas=getappdata(fig,'canvas_size');
for a=reshape(findall(fig,'Type','axes'),1,[])
    if ~isappdata(a,'side_metrics'), continue; end
    p=getappdata(a,'panel_rect'); box=a.Position.*canvas([1 2 1 2]);
    left=box(1)+box(3)+8; width=p(1)+p(3)-left-3;
    h=label(fig,[left box(2)+box(4)-74 width 72],getappdata(a,'side_metrics'),6.5,false);
    h.HorizontalAlignment='left'; h.VerticalAlignment='top';
end
end

function a = split_axis(fig,p,k)
height = (p(4)-92)/2;
y = p(2)+52+(2-k)*(height+10);
canvas = getappdata(fig,'canvas_size');
a = axes(fig,'Units','normalized','Position', ...
    [p(1)+60 y p(3)-72 height]./canvas([1 2 1 2]));
setappdata(a,'panel_rect',p);
end

function constellation(a,symbols,ideal,limit,color)
plot(a,real(symbols),imag(symbols),'.','Color',color,'MarkerSize',2);
hold(a,'on');
plot(a,real(ideal),imag(ideal),'ks','MarkerSize',4,'LineWidth',0.7);
axis(a,'equal'); xlim(a,[-limit limit]); ylim(a,[-limit limit]);
step = 0.5; if limit>2, step = max(1,ceil(limit/3)); end
ticks = -floor(limit/step)*step:step:floor(limit/step)*step;
xticks(a,ticks); yticks(a,ticks); a.XTickLabel=numeric_labels(a.XTick); a.YTickLabel=numeric_labels(a.YTick);
actual_position = getpixelposition(a);
if actual_position(3)<150 && limit<=2, xticks(a,-1:1); a.XTickLabel=numeric_labels(a.XTick); end
xtickangle(a,0); ytickangle(a,0);
xlabel(a,'同相分量 I','FontSize',7); ylabel(a,'正交分量 Q','FontSize',7); grid(a,'on');
end

function problems = verify_layout(fig,panels)
axes_handles = findall(fig,'Type','axes');
canvas = getappdata(fig,'canvas_size');
problems = {};
for k = 1:numel(axes_handles)
    a = axes_handles(k); p = getappdata(a,'panel_rect');
    if strcmp(a.Visible,'off'), continue; end
    insets = a.TightInset; box = a.Position;
    extent = [box(1:2)-insets(1:2),box(3:4)+insets(1:2)+insets(3:4)];
    extent = extent.*canvas([1 2 1 2]);
    if extent(1)<p(1)-1 || sum(extent([1 3]))>sum(p([1 3]))+1
        problems{end+1} = sprintf('Axes width: %s; extent=%s panel=%s', ...
            string(a.YLabel.String),mat2str(extent),mat2str(p)); %#ok<AGROW>
    end
    lower=20;
    if isappdata(a,'footer_clearance'), lower=getappdata(a,'footer_clearance'); end
    if extent(2)<p(2)+lower || sum(extent([2 4]))>sum(p([2 4]))-24
        problems{end+1} = sprintf('Axes height: %s; extent=%s panel=%s', ...
            string(a.YLabel.String),mat2str(extent),mat2str(p)); %#ok<AGROW>
    end
end
annotations = findall(fig,'Type','textboxshape');
for k = 1:numel(annotations)
    h = annotations(k); assigned = getappdata(h,'allocated_rect');
    if isempty(h.String), continue; end
    original = h.Position; h.FitBoxToText = 'on'; drawnow;
    required = h.Position.*canvas([1 2 1 2]);
    if required(3)>assigned(3)+2 || required(4)>assigned(4)+3
        problems{end+1} = sprintf('Text area: %s; required=%s assigned=%s', ...
            strjoin(string(h.String),' '),mat2str(required),mat2str(assigned)); %#ok<AGROW>
    end
    h.FitBoxToText = 'off'; h.Position = original;
end
for h=reshape(findall(fig,'Tag','rx_in_axes_note'),1,[])
    e=h.Extent;
    if any(e(1:2)<-.005) || any(e(1:2)+e(3:4)>1.005)
        problems{end+1}=sprintf('In-frame note outside axes: %s',strjoin(string(h.String),' ')); %#ok<AGROW>
    end
end
assert(size(panels,1)==11);

end

function decoded = first_decoded(result)
% Use a 0x0 struct so capture-only runs are not counted as decoded.
decoded = struct([]);
if ~isstruct(result) || ~isfield(result, 'pairs') || isempty(result.pairs)
    return;
end
for index = 1:numel(result.pairs)
    pair = result.pairs(index);
    if isfield(pair, 'status') && strcmpi(char(string(pair.status)), 'decoded') && ...
            isfield(pair, 'decoded') && isstruct(pair.decoded)
        decoded = pair.decoded;
        return;
    end
end
end

function value = primary_equalizer(decoded)
value = field_or(decoded, 'primary_equalizer', struct());
end

function value = primary_stream(decoded)
streams = field_or(decoded, 'primary_streams', struct([]));
if isempty(streams)
    value = struct();
else
    value = streams(1);
end
end

function value = dashboard_status(result, validation)
if isstruct(result) && isfield(result, 'status') && ~isempty(result.status)
    value = lower(char(string(result.status)));
elseif isstruct(validation) && isfield(validation, 'ok') && validation.ok
    value = 'capture_ready';
else
    value = 'capture_only';
end
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end

function value = status_text(status)
switch lower(char(string(status)))
    case 'decoded'
        value = '解调完成';
    case {'captured_ready_for_demod','capture_ready'}
        value = '采集完成，等待解调';
    case {'captured_not_ready_for_demod', 'blocked'}
        value = '采集不满足解调条件';
    case 'failed'
        value = '处理失败';
    otherwise
        value = '仅采集';
end
end

function close_if_valid(fig)
if isgraphics(fig, 'figure')
    close(fig);
end
end

function placeholder(ax, message)
axis(ax,'off');
text(ax,.5,.5,message,'Units','normalized','HorizontalAlignment','center', ...
    'VerticalAlignment','middle','FontSize',8,'Color',[.45 .2 .2],'Interpreter','none');
end
