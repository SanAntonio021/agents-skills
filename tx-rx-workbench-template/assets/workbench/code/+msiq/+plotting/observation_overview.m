function observation_overview(path, sequence, channels, evm_percent, mer_db)
%OBSERVATION_OVERVIEW Show every observation without cross-channel averaging.
fig = figure('Visible','off','Color','w');
cleanup = onCleanup(@() close(fig));
layout = tiledlayout(fig,2,1);
channels = string(channels);
groups = unique(channels,'stable');
for metric = 1:2
    ax = nexttile(layout,metric); hold(ax,'on');
    if metric == 1, values = evm_percent; else, values = mer_db; end
    for k = 1:numel(groups)
        selected = channels == groups(k);
        plot(ax,sequence(selected),values(selected),'o','LineStyle','none', ...
            'DisplayName',groups(k));
    end
    grid(ax,'on'); xlabel(ax,'序号'); legend(ax,'Location','best');
    if metric == 1, ylabel(ax,'EVM (%)'); else, ylabel(ax,'MER (dB)'); end
end
Test_Project_Export_PNG(fig,path);
end
