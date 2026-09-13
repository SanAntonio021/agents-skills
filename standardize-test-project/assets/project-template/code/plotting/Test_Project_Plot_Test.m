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
pageCount=ceil(numel(indices)/12); paths=cell(1,pageCount);
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
[psdUnit,psdYLimits]=common_spectrum_scale(plotData);
timeLimits=common_time_limits(plotData);
geometry=cell(1,pageCount); panelStatus=cell(1,numel(indices));
for page=1:pageCount
    take=indices((page-1)*12+1:min(page*12,numel(indices))); n=numel(take);
    cols=min(4,n); if ~strcmp(plotData.profile,'demodulation'), cols=min(2,n); end
    rows=ceil(n/cols);
    vis='off'; if opt(options,'visible',false), vis='on'; end
    fig=figure('Visible',vis,'Units','pixels','Position',[50 50 sizePx], ...
        'Color','w','MenuBar','none','ToolBar','none');
    cleanup=onCleanup(@() close(fig));
    layout=tiledlayout(fig,rows,cols,'TileSpacing','compact','Padding','compact');
    sgtitle(layout,opt(plotData.view,'title',profile_title(plotData.profile)), ...
        'FontName','Microsoft YaHei','FontSize',max(12,sizePx(2)/65),'Interpreter','none');
    for j=1:n
        p=panels(take(j)); ax=nexttile(layout); drawOptions=p.options;
        drawOptions.title=p.title; drawOptions.font_size=max(8,min(12,sizePx(1)/160));
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
        panelStatus{(page-1)*12+j}=struct('id',p.id,'status',p.status,'reason',p.reason);
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
function [unit,lim]=common_spectrum_scale(pd)
unit='auto'; lim=[]; lo=Inf; hi=-Inf;
for c=pd.analysis.channels
    if strcmp(c.spectrum.status,'ok')&&isempty(c.spectrum.density_w_hz), unit='voltage'; end
end
for c=pd.analysis.channels
    s=c.spectrum; if ~strcmp(s.status,'ok'), continue; end
    if strcmp(unit,'voltage'), values=s.density_v2_hz; else, values=s.density_w_hz*1000; end
    values=10*log10(max(values(s.frequency_hz<=s.available_limit_hz),realmin));
    if ~isempty(values), lo=min(lo,min(values)); hi=max(hi,max(values)); end
end
if isfinite(lo)&&isfinite(hi), lim=[floor(lo/10)*10-5 ceil(hi/10)*10+5]; end
lim=opt(pd.view,'psd_y_limits',lim);
end
