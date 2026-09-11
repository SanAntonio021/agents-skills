function simulation_plots(run, raw, decoded, cfg, condition, prefix)
%SIMULATION_PLOTS Shared simulation figure generation and legacy replot.
if nargin < 6, prefix = ''; end
streams = decoded.primary_streams;
count = numel(streams);
x = (1:count).';
pre_counts = arrayfun(@(value) value.fec.pre_fec_bit_count, streams).';
post_counts = arrayfun(@(value) value.fec.post_fec_bit_count, streams).';
metric_template = struct('Name', '', 'Unit', '', 'Values', [], ...
    'YScale', 'linear', 'BitCounts', []);
metrics = repmat(metric_template, 1, 5);
metrics(1).Name = 'EVM';
metrics(1).Unit = '%';
metrics(1).Values = 100*[streams.evm_rms].';
metrics(2).Name = 'MER';
metrics(2).Unit = 'dB';
metrics(2).Values = [streams.mer_db].';
metrics(3).Name = 'pre-FEC BER';
metrics(3).Values = [streams.pre_fec_ber].';
metrics(3).YScale = 'log';
metrics(3).BitCounts = pre_counts;
metrics(4).Name = 'post-FEC BER';
metrics(4).Values = [streams.post_fec_ber].';
metrics(4).YScale = 'log';
metrics(4).BitCounts = post_counts;
metrics(5).Name = 'BLER';
metrics(5).Values = [streams.bler].';
Test_Project_Plot_Scan_Summary(fullfile(run.OutputDir, [prefix,'metrics_overview.png']), ...
    x, metrics, struct('Title', sprintf('%s synthetic channel', ...
    condition.condition_id), 'XName', '数据流', 'XUnit', '-', ...
    'PlannedCount', count, 'SuccessMask', [streams.valid].'));

received = arrayfun(@(value) value.constellation_symbols, streams, ...
    'UniformOutput', false);
ideal = qammod((0:15).', 16, 'UnitAveragePower', true);
constellation_metrics = repmat(struct(), 1, count);
for stream_index = 1:count
    constellation_metrics(stream_index).BER = ...
        streams(stream_index).pre_fec_ber;
    constellation_metrics(stream_index).EVM = ...
        100*streams(stream_index).evm_rms;
    constellation_metrics(stream_index).MER = streams(stream_index).mer_db;
end
    if strcmpi(condition.architecture, 'single_complex_stream')
        constellation_title = sprintf( ...
            '16QAM 传统复数零中频\nWZ WL-FSE-NLMS\n软判决 LDPC');
        channel_names = {'传统复数流'};
    else
        constellation_title = '16QAM 双独立流：2x2 RZF + 软判决 LDPC';
        channel_names = {'数据流 1', '数据流 2'};
    end
    Test_Project_Plot_Constellation(fullfile(run.OutputDir, ...
        [prefix,'constellation.png']), received, ideal, constellation_metrics, ...
        struct('Title', constellation_title, ...
        'ChannelNames', {channel_names}));
for stream_index = 1:count
    name = sprintf('%s001_Channel%d_星座图.png',prefix,stream_index);
    Test_Project_Plot_Constellation(fullfile(run.OutputDir,name), ...
        received(stream_index),ideal,constellation_metrics(stream_index), ...
        struct('Title',constellation_title, ...
        'ChannelNames',{channel_names(stream_index)}));
end
msiq.plotting.demod_dashboard(fullfile(run.OutputDir, [prefix,'overview.png']), ...
    raw, decoded, cfg, condition);
end
