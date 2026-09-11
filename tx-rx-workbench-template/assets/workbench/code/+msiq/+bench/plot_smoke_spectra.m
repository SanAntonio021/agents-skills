function output_path = plot_smoke_spectra(output_path, records)
%PLOT_SMOKE_SPECTRA Plot unsmoothed one-sided PSD for all V213 ON captures.

if isempty(records)
    error('msiq:bench:NoSpectrumRecords', ...
        'At least one successful ON capture is required.');
end
style = Test_Project_Plot_Style();
fig = figure('Visible','off','Units','inches', ...
    'Position',[1 1 7.1 11.5],'Color',style.FigureColor);
cleanup = onCleanup(@() close_figure(fig));
layout = tiledlayout(fig,4,2,'TileSpacing','compact','Padding','compact');
for k = 1:numel(records)
    raw = records(k).raw;
    samples = double(raw.samples(:,1));
    count = numel(samples);
    if count < 2
        error('msiq:bench:SpectrumSamples', ...
            'Spectrum capture must contain at least two samples.');
    end
    window = 0.5-0.5*cos(2*pi*(0:count-1).'/(count-1));
    spectrum = fft(samples.*window);
    one_count = floor(count/2)+1;
    psd_w_hz = abs(spectrum(1:one_count)).^2 / ...
        (raw.sample_rate_hz*sum(window.^2)*50);
    if one_count > 2
        psd_w_hz(2:end-1) = 2*psd_w_hz(2:end-1);
    end
    frequency_ghz = (0:one_count-1).'/count*raw.sample_rate_hz/1e9;
    ax = nexttile(layout,k);
    plot(ax,frequency_ghz,10*log10(max(psd_w_hz*1000,realmin)), ...
        'Color',style.Colors(1,:),'LineWidth',style.LineWidth);
    title(ax,records(k).label,'Interpreter','none', ...
        'FontSize',style.TitleFontSize,'FontWeight','normal');
    xlabel(ax,'频率 (GHz)','FontSize',style.AxisLabelFontSize);
    ylabel(ax,'功率谱密度 (dBm/Hz)','FontSize',style.AxisLabelFontSize);
    Test_Project_Apply_Axes_Style(ax,style);
end
sgtitle(layout,'V213 单 DAC ON 原始频谱', ...
    'FontName',style.FontName,'FontSize',style.TitleFontSize+1, ...
    'FontWeight','normal');
output_path = Test_Project_Export_PNG(fig,output_path,style);
end

function close_figure(fig)
if isgraphics(fig), close(fig); end
end
