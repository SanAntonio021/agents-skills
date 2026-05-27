# MATLAB Figure 中文显示

### Pattern: matlab-figure-font-chinese
- scenario: MATLAB figure 标题、坐标轴、图例、文本标注中的中文字符显示为方框
- use_when: 代码中使用了 `set(0, 'DefaultAxesFontName', 'Arial')` 或其他不支持 CJK 的西文字体，导致中文全部渲染为 □□□
- shell: MATLAB
- validated_shape: `set(0, 'DefaultAxesFontName', 'Microsoft YaHei UI');`
- substitute_only: 无
- preflight: `any(strcmpi(listfonts, 'Microsoft YaHei UI'))` 在目标 MATLAB 上返回 true；返回 false 时换 `'SimHei'` 或 `'Microsoft JhengHei'` 等候选并复测
- env: none
- avoid: 使用 `'Arial'`、`'Helvetica'`、`'Times New Roman'` 等纯西文字体作为 DefaultAxesFontName；这些字体不包含中文字形，MATLAB 不会自动回退到系统中文字体。也不要直接写 `'Microsoft YaHei'`（不带 UI 后缀）——R2023b on Windows 的 `listfonts` 看不到不带 UI 的版本，set 后会静默回退到默认西文字体，中文仍然方框
- success_signal: figure 中所有中文标题、坐标轴标签、图例、文本标注正常显示为汉字
- capture_rule: 任何 MATLAB 绘图脚本如果需要显示中文，都要在绘图前设置支持中文的字体；Windows + MATLAB R2023b 实测可用的是 `'Microsoft YaHei UI'`（带 UI 后缀），备选 `'Microsoft JhengHei'`、`'SimHei'`；写入前先 `any(strcmpi(listfonts, '<候选>'))` 验证字体真的可用

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

### Pattern: matlab-figure-modal-to-normal-pitfall
- scenario: MATLAB R2023b on Windows 上，figure 一开始用 `'WindowStyle','modal'`，后续在 callback 里 `set(fig,'WindowStyle','normal')` 想"OK 后保留窗口给用户继续查看"，结果 figure 在切换瞬间被销毁
- use_when: 设计 GUI 弹窗想做"用户点 OK 后窗口转为只读快照保留"的工作流；OK 后控件 disable + 改标题没问题，但切换 WindowStyle 失败
- shell: MATLAB
- validated_shape: `f = figure('WindowStyle','normal', ..., 'CloseRequestFcn', @on_cancel); ...; uiwait(f);`（一开始就用 normal，配 `uiwait` 也能阻塞主程序，OK 时不必切换 WindowStyle）
- substitute_only: 无
- preflight: 无
- env: none
- avoid: `set(fig,'WindowStyle','normal')` 中途切换；以为 modal→normal 是 GUI 风格转换的标准做法；用 modal 是为了"必须先回应弹窗才能继续"，但 normal + uiwait 已经达到同样阻塞效果
- success_signal: 用户点 OK 后 figure 仍保留在屏幕上，主程序继续往下跑而不是被切换销毁
- capture_rule: R2023b on Windows 设计交互弹窗时默认用 `'WindowStyle','normal'`；要"必须阻塞"的语义靠 `uiwait`，不靠 `modal` 风格

### Pattern: matlab-batch-gui-envvar-bypass
- scenario: 脚本顶部有 `listdlg(...)` 或 `questdlg(...)` 等模态对话框，要在 `matlab -batch` 模式下自动跑到某个分支但 batch headless 没法点击
- use_when: 想用 batch 跑端到端测试，又不想临时改源码注释掉 listdlg；脚本是 production code 不该为测试改
- shell: MATLAB + PowerShell
- validated_shape: 脚本设计成 `mode_override = getenv('<SCRIPT>_MODE'); if ~isempty(mode_override), idx = parse_mode(mode_override); else [idx, ok] = listdlg(...); end`；batch 调用前 `setenv('<SCRIPT>_MODE','SIM')`
- substitute_only: `<SCRIPT>_MODE`, `SIM`
- preflight: 确认脚本顶部已有 env var bypass 分支；没有就先在脚本里加一段
- env: 任务相关的环境变量（如 `IQMIMO_RX_MODE=SIM/OBSERVE/CAPTURE` 或 `USE_GUI_CONFIG=false`）
- avoid: 临时改源码注释掉 listdlg 再 batch 跑（污染主代码）；在 base workspace 用 assignin 注入变量再 run script（script 顶部的 `clear variables` 会清掉）；忘记跑完后 `setenv('<SCRIPT>_MODE','')` 清空，污染下次手动跑同一脚本
- success_signal: batch 模式 stdout 显示进入指定分支，不弹任何 GUI；跑完后再手动跑脚本时 listdlg 正常弹出
- capture_rule: 任何含 listdlg/questdlg 的脚本，设计期就为 env var bypass 留 hook；workbench 等总入口跑完子脚本后主动 `setenv('<SCRIPT>_MODE','')` 清场
