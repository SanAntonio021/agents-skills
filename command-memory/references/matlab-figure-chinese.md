# MATLAB Figure 中文显示

### Pattern: matlab-figure-font-chinese
- scenario: MATLAB figure 标题、坐标轴、图例、文本标注中的中文字符显示为方框
- use_when: 代码中使用了 `set(0, 'DefaultAxesFontName', 'Arial')` 或其他不支持 CJK 的西文字体，导致中文全部渲染为 □□□
- shell: MATLAB
- validated_shape: `set(0, 'DefaultAxesFontName', 'Microsoft YaHei');`
- substitute_only: 无
- preflight: 无
- env: none
- avoid: 使用 `'Arial'`、`'Helvetica'`、`'Times New Roman'` 等纯西文字体作为 DefaultAxesFontName；这些字体不包含中文字形，MATLAB 不会自动回退到系统中文字体
- success_signal: figure 中所有中文标题、坐标轴标签、图例、文本标注正常显示为汉字
- capture_rule: 任何 MATLAB 绘图脚本如果需要显示中文，都要在绘图前设置支持中文的字体；Windows 上推荐 `'Microsoft YaHei'`（微软雅黑），备选 `'SimHei'`（黑体）

### Pattern: matlab-text-font-chinese
- scenario: MATLAB `text()` 或 `annotation()` 中单独指定了 `'FontName', 'Consolas'` 等等宽西文字体，导致该文本对象中的中文显示为方框，即使 DefaultAxesFontName 已设为中文字体
- use_when: figure 大部分中文正常，但某个 text/annotation 对象的中文仍为方框
- shell: MATLAB
- validated_shape: `text(..., 'FontName', 'Microsoft YaHei');`
- substitute_only: 无
- preflight: 无
- env: none
- avoid: 在需要显示中文的 text 对象上指定 `'Consolas'`、`'Courier New'`、`'Monospaced'` 等纯西文等宽字体
- success_signal: 该 text 对象中的中文正常显示
- capture_rule: 如果既需要等宽对齐又需要中文，可以用 `'NSimSun'`（新宋体，等宽且支持中文）

### Pattern: matlab-batch-saveas-figure
- scenario: 通过 `matlab -batch "script"` 运行脚本后看不到任何 figure 窗口
- use_when: 脚本在 MATLAB 桌面模式下正常弹出 figure，但 `-batch` 模式下没有图形输出
- shell: PowerShell
- validated_shape: `matlab -batch "my_script; saveas(gcf, 'output.png')"`
- substitute_only: `my_script`, `output.png`
- preflight: `Get-Command "matlab"`; 确认脚本路径可达
- env: none
- avoid: 期望 `-batch` 模式弹出交互式 figure 窗口；`-batch` 模式下 MATLAB 以 headless 方式运行，figure 创建后不会显示在屏幕上，脚本结束后 figure 即被销毁
- success_signal: 脚本运行完成后在工作目录生成 `output.png`，内容与桌面模式下的 figure 一致
- capture_rule: 如果需要更高分辨率或矢量图，用 `print(gcf, 'output', '-dpng', '-r300')` 或 `exportgraphics(gcf, 'output.pdf')`
