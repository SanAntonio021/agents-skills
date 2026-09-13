function details = Test_Project_Plot_Test(outputPath, plotData, options)
%TEST_PROJECT_PLOT_TEST Render a saved numerical package, no DSP/instrument I/O.
if nargin<3, options=struct(); end
plotData=Test_Project_Validate_Plot_Data(plotData);
selected=opt(options,'panel_ids',{}); panels=plotData.panels;
if ~isempty(selected)
    selected=cellstr(string(selected)); indices=zeros(size(selected));
    for k=1:numel(selected)
        i=find(strcmp({panels.id},selected{k}),1);
        if isempty(i), error('TestProject:Plot:UnknownPanel','Unknown panel %s.',selected{k}); end
        indices(k)=i;
    end
else, indices=1:numel(panels); end
sizePx=opt(options,'target_size_px',[1920 1080]);
if ~isnumeric(sizePx)||numel(sizePx)~=2||any(sizePx<320)||any(~isfinite(sizePx))
    error('TestProject:Plot:TargetSize','Invalid target pixel size.');
end
outputPath=char(outputPath); [folder,name,ext]=fileparts(outputPath);
if isempty(folder), folder=pwd; end
if isempty(ext), ext='.png'; end
if ~strcmpi(ext,'.png'), error('TestProject:Plot:PNGRequired','PNG output required.'); end
groups=Test_Project_Validate_Plot_Groups(plotData.view,panels);
useGroups=isempty(selected)&&~isempty(groups);
if useGroups, pageCount=ceil(numel(groups)/12); else, pageCount=ceil(numel(indices)/12); end
paths=cell(1,pageCount);
for page=1:pageCount
    suffix=''; if pageCount>1, suffix=sprintf('_p%02d',page); end
    paths{page}=fullfile(folder,[name suffix ext]);
    if isfile(paths{page}), error('TestProject:Plot:OutputExists','Output exists: %s',paths{page}); end
end
archive=fullfile(folder,'data','test_plot_data.mat');
viewPath=fullfile(folder,'data',[name '_view.json']);
if isfile(viewPath), error('TestProject:Plot:OutputExists','Export view record exists: %s',viewPath); end
persist=opt(options,'save_data',true);
if persist && isfile(archive)
    old=Test_Project_Load_Plot_Data(archive);
    if ~isequaln(old,plotData), error('TestProject:Plot:FrameMismatch','Existing archive is a different frame; use a new run.'); end
end
if ~isfolder(folder), mkdir(folder); end
if persist && ~isfile(archive), Test_Project_Save_Plot_Data(archive,plotData); end
frequencyLimits=common_frequency_limits(plotData);
scaleBand=[];
if useGroups
    scaleBand=frequencyLimits;
    if strcmp(plotData.profile,'demodulation')&&isfield(plotData.view,'signal_band_hz')&&~isempty(frequencyLimits)
        band=plotData.view.signal_band_hz; width=diff(band);
        scaleBand=[max(0,band(1)-width/2) min(frequencyLimits(2),band(2)+width/2)];
    end
    scaleBand=opt(options,'frequency_limits_hz',scaleBand);
end
[psdUnit,psdYLimits]=common_spectrum_scale(plotData,scaleBand);
timeLimits=common_time_limits(plotData);
geometry=cell(1,pageCount); panelStatus=cell(1,numel(indices)); statusIndex=0;
for page=1:pageCount
    if useGroups
        pageGroups=groups((page-1)*12+1:min(page*12,numel(groups)));
        ids={}; for g=pageGroups, ids=[ids reshape(g.panel_ids,1,[])]; end %#ok<AGROW>
        [~,take]=ismember(ids,{panels.id});
    else
        take=indices((page-1)*12+1:min(page*12,numel(indices)));
    end
    n=numel(take);
    cols=min(4,n); if ~strcmp(plotData.profile,'demodulation'), cols=min(2,n); end
    rows=ceil(n/cols);
    vis='off'; if opt(options,'visible',false), vis='on'; end
    fig=figure('Visible',vis,'Units','pixels','Position',[50 50 sizePx], ...
        'Color','w','MenuBar','none','ToolBar','none');
    cleanup=onCleanup(@() close(fig));
    if useGroups
        [groupAxes,groupTitles,groupTop]=create_group_axes(fig,pageGroups,plotData.view.grid_size,sizePx);
        annotation(fig,'textbox',[.012 .95 .976 .043],'String', ...
            opt(plotData.view,'title',profile_title(plotData.profile)), ...
            'EdgeColor','none','FontName','Microsoft YaHei','FontSize',max(12,sizePx(2)/65), ...
            'HorizontalAlignment','center','Interpreter','none');
    else
        layout=tiledlayout(fig,rows,cols,'TileSpacing','compact','Padding','compact');
        sgtitle(layout,opt(plotData.view,'title',profile_title(plotData.profile)), ...
            'FontName','Microsoft YaHei','FontSize',max(12,sizePx(2)/65),'Interpreter','none');
    end
    for j=1:n
        p=panels(take(j));
        if useGroups, ax=groupAxes(j); else, ax=nexttile(layout); end
        drawOptions=p.options;
        drawOptions.title=p.title; drawOptions.font_size=max(8,min(12,sizePx(1)/160));
        if useGroups
            drawOptions.font_size=max(7,min(10,sizePx(1)/192));
            if groupTitles(j), drawOptions.title=''; end
        end
        Test_Project_Plot_Util('decorate',ax,drawOptions);
        if ~strcmp(p.status,'ok')
            Test_Project_Plot_Util('placeholder',ax,[p.status ': ' p.reason]);
        else
            data=Test_Project_Resolve_Panel(plotData.analysis,p);
            switch p.kind
                case 'waveform'
                    if ~isempty(timeLimits), drawOptions.time_limits_s=timeLimits; end
                    Test_Project_Draw_Waveform(ax,data,drawOptions);
                case 'spectrum'
                    if isfield(data,'density_v2_hz')
                        drawOptions.unit=psdUnit;
                        if ~isfield(drawOptions,'y_limits'), drawOptions.y_limits=psdYLimits; end
                    end
                    if isfield(data,'density_v2_hz') && ~isempty(frequencyLimits), drawOptions.frequency_limits_hz=frequencyLimits; end
                    if strcmp(plotData.profile,'demodulation') && isfield(plotData.view,'signal_band_hz')
                        band=plotData.view.signal_band_hz; width=diff(band);
                        if isfield(data,'density_v2_hz'), drawOptions.frequency_limits_hz=[max(0,band(1)-width/2) min(frequencyLimits(2),band(2)+width/2)];
                        else, drawOptions.frequency_limits_hz=[band(1)-width/2 band(2)+width/2]; end
                    end
                    if isfield(options,'frequency_limits_hz'), drawOptions.frequency_limits_hz=options.frequency_limits_hz; end
                    Test_Project_Draw_Spectrum(ax,data,drawOptions);
                case 'constellation'
                    if ~isfield(drawOptions,'axis_limits'), drawOptions.axis_limits=common_constellation_limits(plotData,p); end
                    Test_Project_Draw_Constellation(ax,data,drawOptions);
                case 'curve', Test_Project_Draw_Curve(ax,data,drawOptions);
            end
        end
        if useGroups && ismember(p.kind,{'waveform','spectrum'})
            if strcmp(p.kind,'waveform')
                % Keep all scope divisions, but label only major positions.
                ticks=ax.YTick; labels=compose('%.3g',ticks); labels(2:2:end)={''}; ax.YTickLabel=labels;
            else
                yticks(ax,linspace(ax.YLim(1),ax.YLim(2),3));
                if contains(ax.YLabel.String,'dBm/Hz'), ylabel(ax,'dBm/Hz','Interpreter','none');
                elseif contains(ax.YLabel.String,'dB(V²/Hz)'), ylabel(ax,'dB(V²/Hz)','Interpreter','none'); end
            end
            ax.XTickMode='auto'; ax.XTickLabelMode='auto'; ax.XTickLabelRotation=0;
            if groupTop(j), xlabel(ax,''); ax.XTickLabel=[]; end
            if isfield(p.data_ref,'channel_id')
                text(ax,.02,.98,p.data_ref.channel_id,'Units','normalized', ...
                    'VerticalAlignment','top','FontSize',drawOptions.font_size, ...
                    'Interpreter','none','BackgroundColor','w','Margin',1);
            end
        end
        statusIndex=statusIndex+1;
        panelStatus{statusIndex}=struct('id',p.id,'status',p.status,'reason',p.reason);
    end
    drawnow(); set(fig,'PaperPositionMode','auto','InvertHardcopy','off');
    % -r0 preserves requested on-screen pixel geometry instead of scaling by DPI.
    print(fig,paths{page},'-dpng','-r0');
    info=imfinfo(paths{page}); geometry{page}=[info.Width info.Height];
    clear cleanup;
end
details=struct('OutputPaths',{paths},'ArchivePath',archive,'PixelSizes',{geometry}, ...
    'PanelStatus',{panelStatus},'Source',plotData.source,'SpectrumUnit',psdUnit,'SpectrumYLimits',psdYLimits);
exportView=struct('schema_version',1,'panel_ids',{{panels(indices).id}}, ...
    'target_size_px',sizePx,'profile',plotData.profile,'view',plotData.view, ...
    'frequency_limits_hz',opt(options,'frequency_limits_hz',frequencyLimits), ...
    'time_limits_s',timeLimits,'psd_unit',psdUnit,'psd_y_limits',psdYLimits);
if ~isfolder(fileparts(viewPath)), mkdir(fileparts(viewPath)); end
fid=fopen(viewPath,'w','n','UTF-8');
if fid<0, error('TestProject:Plot:ViewWrite','Cannot write export view record.'); end
closer=onCleanup(@() fclose(fid)); fprintf(fid,'%s\n',jsonencode(exportView));
details.ViewPath=viewPath;
end
function [axesList,suppressTitle,hideXLabels]=create_group_axes(fig,groups,gridSize,sizePx)
% Separate logical groups retain the proven reception dashboard hierarchy.
axesList=gobjects(1,0); suppressTitle=false(1,0); hideXLabels=false(1,0);
margin=.008; gap=.008; bottom=.015; top=.945;
cw=(1-2*margin-(gridSize(2)-1)*gap)/gridSize(2);
ch=(top-bottom-(gridSize(1)-1)*gap)/gridSize(1);
for g=groups
    p=g.position;
    rect=[margin+(p(2)-1)*(cw+gap),top-(p(1)+p(3)-1)*ch-(p(1)+p(3)-2)*gap, ...
        p(4)*cw+(p(4)-1)*gap,p(3)*ch+(p(3)-1)*gap];
    container=uipanel(fig,'Units','normalized','Position',rect,'BorderType','none','BackgroundColor','w');
    layout=tiledlayout(container,numel(g.panel_ids),1,'TileSpacing','compact','Padding','compact');
    title(layout,g.title,'FontName','Microsoft YaHei','FontSize',max(9,min(12,sizePx(1)/160)), ...
        'FontWeight','bold','Interpreter','none');
    for k=1:numel(g.panel_ids)
        axesList(end+1)=nexttile(layout); %#ok<AGROW>
        suppressTitle(end+1)=true; %#ok<AGROW>
        hideXLabels(end+1)=k<numel(g.panel_ids); %#ok<AGROW>
    end
end
end
function v=opt(s,k,d), v=Test_Project_Plot_Util('option',s,k,d); end
function title=profile_title(p)
switch p
    case 'single_channel', title='单通道观察';
    case 'iq_observation', title='IQ 观察';
    otherwise, title='解调结果';
end
end
function lim=common_constellation_limits(pd,selected)
extent=1;
group=opt(selected.options,'comparison_group','');
for p=pd.panels
    same=strcmp(p.id,selected.id)||(~isempty(group)&&strcmp(opt(p.options,'comparison_group',''),group));
    if same && strcmp(p.kind,'constellation')&&strcmp(p.status,'ok')
        d=Test_Project_Resolve_Panel(pd.analysis,p); s=d.symbols(:); s=s(isfinite(s));
        if ~isempty(s), extent=max(extent,max([abs(real(s));abs(imag(s))])); end
    end
end
extent=extent*1.08; lim=[-extent extent -extent extent];
end
function lim=common_frequency_limits(pd)
hi=[];
for c=pd.analysis.channels
    if strcmp(c.spectrum.status,'ok'), hi(end+1)=c.spectrum.available_limit_hz; end %#ok<AGROW>
end
lim=[]; if ~isempty(hi), lim=[0 min(hi)]; end
end
function lim=common_time_limits(pd)
lo=[]; hi=[];
for c=pd.analysis.channels
    if strcmp(c.waveform.status,'ok') && ~isempty(c.waveform.time_s)
        range=opt(c.waveform,'time_limits_s',[min(c.waveform.time_s) max(c.waveform.time_s)]);
        lo(end+1)=range(1); hi(end+1)=range(2); %#ok<AGROW>
    end
end
lim=[]; if ~isempty(lo), lim=[min(lo) max(hi)]; end
end
function [unit,lim]=common_spectrum_scale(pd,displayBand)
unit='auto'; lim=[]; lo=Inf; hi=-Inf;
for c=pd.analysis.channels
    if strcmp(c.spectrum.status,'ok')&&isempty(c.spectrum.density_w_hz), unit='voltage'; end
end
for c=pd.analysis.channels
    s=c.spectrum; if ~strcmp(s.status,'ok'), continue; end
    if strcmp(unit,'voltage'), values=s.density_v2_hz; else, values=s.density_w_hz*1000; end
    shown=s.frequency_hz<=s.available_limit_hz;
    if ~isempty(displayBand), shown=shown & s.frequency_hz>=displayBand(1) & s.frequency_hz<=displayBand(2); end
    values=10*log10(max(values(shown),realmin));
    if ~isempty(values), lo=min(lo,min(values)); hi=max(hi,max(values)); end
end
if isfinite(lo)&&isfinite(hi), lim=[floor(lo/10)*10-5 ceil(hi/10)*10+5]; end
lim=opt(pd.view,'psd_y_limits',lim);
end
