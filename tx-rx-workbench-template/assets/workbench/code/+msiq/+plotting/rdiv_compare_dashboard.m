function details = rdiv_compare_dashboard(output_path, plan, result)
%RDIV_COMPARE_DASHBOARD Export the compact Chinese DIV2/DIV4 comparison.

if nargin < 2 || ~isstruct(plan)
    plan = struct();
end
if nargin < 3 || ~isstruct(result)
    result = struct();
end
output_path = char(string(output_path));
[output_dir, ~, extension] = fileparts(output_path);
if isempty(extension)
    output_path = [output_path, '.png'];
end
if ~isempty(output_dir) && ~isfolder(output_dir)
    mkdir(output_dir);
end

fig = figure('Visible', 'off', 'Color', 'w', ...
    'Position', [80 80 2100 1400], 'InvertHardcopy', 'off');
cleanup = onCleanup(@() close_if_valid(fig));
set(fig, 'DefaultAxesFontName', 'Microsoft YaHei UI', ...
    'DefaultTextFontName', 'Microsoft YaHei UI', ...
    'DefaultAxesFontSize', 9);
status = lower(char(string(field_or(result, 'status', 'planned'))));
layout = tiledlayout(fig, 2, 2, 'Padding', 'loose', 'TileSpacing', 'compact');
sgtitle(fig, sprintf('DIV2 / DIV4 传统 16QAM 回环对比 | %s', upper(status)), ...
    'FontName', 'Microsoft YaHei UI', 'FontSize', 17, ...
    'FontWeight', 'bold', 'Interpreter', 'none');

trials = field_or(result, 'trials', struct([]));
draw_paired_mer(nexttile(layout, 1), trials);
draw_paired_evm(nexttile(layout, 2), trials);
draw_fec(nexttile(layout, 3), trials);
draw_summary(nexttile(layout, 4), plan, result);
draw_footer(fig, plan, result);
% Preserve the designed 96-dpi canvas independently of screen fitting.
set(fig,'PaperUnits','inches','PaperSize',[2100 1400]/96, ...
    'PaperPosition',[0 0 2100 1400]/96,'PaperPositionMode','manual');
archive_dir=fullfile(output_dir,'data');
if ~isfolder(archive_dir), archive_dir=fullfile(output_dir,'diagnostics'); end
msiq.plotting.save_replot_figure(fig,output_path,180);
plot_cleanup=msiq.plot_archive('begin',output_dir,archive_dir); %#ok<NASGU>
if ~msiq.plot_archive('export',fig,output_path,'print',180)
    print(fig, output_path, '-dpng', '-r180');
end
details = struct('output_path', output_path, 'status', status, ...
    'panel_count', 4, 'resolution_dpi', 180);
clear cleanup;
end

function draw_paired_mer(ax, trials)
[div2, div4] = paired_values(trials, 'mer_db');
if ~any(isfinite(div2)) && ~any(isfinite(div4))
    placeholder(ax, unavailable_text(trials, '没有成功解调的 MER 数据'));
    return;
end
hold(ax, 'on');
plot(ax, 1:5, div2, 'o-', 'LineWidth', 1.1, 'MarkerSize', 5, ...
    'Color', [0.00 0.35 0.75], 'DisplayName', 'DIV2');
plot(ax, 1:5, div4, 's-', 'LineWidth', 1.1, 'MarkerSize', 5, ...
    'Color', [0.85 0.30 0.05], 'DisplayName', 'DIV4');
hold(ax, 'off');
grid(ax, 'on');
xlim(ax, [0.7 5.3]);
xticks(ax, 1:5);
title(ax, '1. 五组相邻配对 MER（越高越好）', 'FontWeight', 'bold');
xlabel(ax, '配对序号');
ylabel(ax, 'MER (dB)');
legend(ax, 'Location', 'best', 'Box', 'off');
end

function draw_paired_evm(ax, trials)
[div2, div4] = paired_values(trials, 'evm_rms');
if ~any(isfinite(div2)) && ~any(isfinite(div4))
    placeholder(ax, unavailable_text(trials, '没有成功解调的 EVM 数据'));
    return;
end
hold(ax, 'on');
plot(ax, 1:5, 100*div2, 'o-', 'LineWidth', 1.1, 'MarkerSize', 5, ...
    'Color', [0.00 0.35 0.75], 'DisplayName', 'DIV2');
plot(ax, 1:5, 100*div4, 's-', 'LineWidth', 1.1, 'MarkerSize', 5, ...
    'Color', [0.85 0.30 0.05], 'DisplayName', 'DIV4');
hold(ax, 'off');
grid(ax, 'on');
xlim(ax, [0.7 5.3]);
xticks(ax, 1:5);
title(ax, '2. 五组相邻配对 EVM（越低越好）', 'FontWeight', 'bold');
xlabel(ax, '配对序号');
ylabel(ax, 'RMS EVM (%)');
legend(ax, 'Location', 'best', 'Box', 'off');
end

function draw_fec(ax, trials)
[div2, div4] = paired_values(trials, 'post_fec_ber');
if ~any(isfinite(div2)) && ~any(isfinite(div4))
    placeholder(ax, unavailable_text(trials, '没有有效的 FEC 记录'));
    return;
end
plot(ax, 1:5, div2, 'o-', 'DisplayName', 'DIV2');
hold(ax, 'on');
plot(ax, 1:5, div4, 's-', 'DisplayName', 'DIV4');
hold(ax, 'off');
ylabel(ax, 'post-FEC BER');
xlabel(ax, '配对序号');
xticks(ax, 1:5);
grid(ax, 'on');
title(ax, '3. 逐次 FEC 误码率', 'FontWeight', 'bold');
legend(ax, 'Location', 'best', 'Box', 'off');
end

function draw_summary(ax, plan, result)
axis(ax, 'off');
route = field_or(plan, 'route', struct());
levels = field_or(plan, 'levels', struct());
minimum = numeric_or(field_or(plan, 'minimum_capture_window_s', NaN), NaN);
conclusion = field_or(result, 'conclusion', struct());
message = char(string(field_or(conclusion, 'message', '等待执行。')));
failure = field_or(result, 'failure', struct());
failure_text = char(string(field_or(failure, 'error_message', '')));
condition = sprintf(['路由：%s\nFOUR + CH1/CH2 EXT + CH3/CH4 INT\n', ...
    'raster：65 GSa/s\n电平：%s Vpp；offset：%s V\n', ...
    '最低物理时间窗：%.4f us\n\n结论：%s'], ...
    char(string(field_or(route, 'name', 'pair_a_ch1_ch2'))), ...
    vector_text(field_or(levels, 'amplitude_vpp', [])), ...
    vector_text(field_or(levels, 'offset_v', [])), minimum*1e6, message);
if ~isempty(failure_text)
    condition = sprintf('%s\n\n中止原因：%s', condition, failure_text);
end
text(ax, 0.04, 0.94, condition, 'Units', 'normalized', ...
    'VerticalAlignment', 'top', 'FontName', 'Microsoft YaHei UI', ...
    'FontSize', 10, 'Interpreter', 'none', 'BackgroundColor', [0.97 0.97 0.97], ...
    'Margin', 9);
title(ax, '4. 固定条件、时间窗与判定', 'FontWeight', 'bold');
end

function draw_footer(fig, plan, result)
status = upper(char(string(field_or(result, 'status', 'planned'))));
seed = numeric_or(field_or(plan, 'seed', NaN), NaN);
line = sprintf(['状态：%s | 固定顺序：DIV2, DIV4 x 5 | seed：%s | ', ...
    '每轮下载使用一次 :ABOR；结束仅关闭 CH1/CH2'], ...
    status, number_text(seed));
annotation(fig, 'textbox', [0.020 0.008 0.960 0.026], 'String', line, ...
    'EdgeColor', [0.80 0.80 0.80], 'BackgroundColor', [0.97 0.97 0.97], ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
    'FontName', 'Microsoft YaHei UI', 'FontSize', 8.5, 'Interpreter', 'none');
end

function [div2, div4] = paired_values(trials, field)
div2 = nan(1, 5);
div4 = nan(1, 5);
for pair_index = 1:5
    for rdiv_index = 1:2
        rdiv = {'DIV2','DIV4'};
        selected = trials(strcmpi({trials.rdiv}, rdiv{rdiv_index}) & ...
            [trials.pair_index] == pair_index & ...
            strcmpi({trials.status}, 'decoded'));
        if numel(selected) == 1 && isfield(selected.metrics, field)
            if rdiv_index == 1
                div2(pair_index) = numeric_or(selected.metrics.(field), NaN);
            else
                div4(pair_index) = numeric_or(selected.metrics.(field), NaN);
            end
        end
    end
end
end

function text = unavailable_text(trials, fallback)
failed = trials(~strcmpi({trials.status}, 'decoded'));
if isempty(failed)
    text = fallback;
    return;
end
reason = char(string(field_or(failed(1), 'error_message', '')));
if isempty(reason)
    text = fallback;
else
    text = sprintf('%s\n%s', fallback, reason);
end
end

function value = sum_finite(values)
values = double(values(:));
if any(~isfinite(values))
    value = NaN;
else
    value = sum(values);
end
end

function value = ratio(numerator, denominator)
numerator = sum_finite(numerator);
denominator = sum_finite(denominator);
if isfinite(numerator) && isfinite(denominator) && denominator > 0
    value = numerator/denominator;
else
    value = NaN;
end
end

function text = vector_text(value)
value = double(value(:).');
if isempty(value)
    text = 'n/a';
else
    pieces = arrayfun(@(item) sprintf('%.3g', item), value, ...
        'UniformOutput', false);
    text = ['[', strjoin(pieces, ' '), ']'];
end
end

function value = field_or(value, name, fallback)
if isstruct(value) && isfield(value, name) && ~isempty(value.(name))
    value = value.(name);
else
    value = fallback;
end
end

function value = numeric_or(value, fallback)
if isempty(value) || ~isscalar(value) || ~isfinite(double(value))
    value = fallback;
else
    value = double(value);
end
end

function text = number_text(value)
if ~isfinite(value)
    text = 'n/a';
else
    text = sprintf('%.12g', value);
end
end

function placeholder(ax, message)
axis(ax, 'off');
text(ax, 0.5, 0.5, message, 'HorizontalAlignment', 'center', ...
    'VerticalAlignment', 'middle', 'FontName', 'Microsoft YaHei UI', ...
    'FontSize', 10, 'Color', [0.55 0.10 0.10], 'Interpreter', 'none');
end

function close_if_valid(fig)
if isgraphics(fig, 'figure')
    close(fig);
end
end
