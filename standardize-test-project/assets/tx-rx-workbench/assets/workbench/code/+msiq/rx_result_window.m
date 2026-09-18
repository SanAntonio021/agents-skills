function fig=rx_result_window(action,fig,snapshot,visible)
%RX_RESULT_WINDOW Read-only view of saved RX task results; never runs DSP.
% update never creates a window. User closing it has no task side effects.
if nargin<2, fig=[]; end
if nargin<3, snapshot=struct(); end
if nargin<4, visible='on'; end
if islogical(visible), if visible, visible='on'; else, visible='off'; end; end
if strcmp(action,'close')
    if isgraphics(fig), delete(fig); end
    fig=[]; return;
end
if isempty(fig) || ~isgraphics(fig)
    if ~strcmp(action,'open'), fig=[]; return; end
    fig=figure('Name','RX 测试结果','NumberTitle','off','MenuBar','none', ...
        'ToolBar','figure','Position',[80 80 1120 640],'Visible',visible, ...
        'Color',[.96 .97 .98],'Tag','rx_test_results');
    s=struct('snapshot',struct(),'selected',0,'follow',true,'task_id','','source_mode','', ...
        'image_path','','image_key','','rows',{{}});
    s.status=uicontrol(fig,'Style','text','Units','normalized','Position',[.015 .92 .97 .065], ...
        'HorizontalAlignment','left','FontSize',13,'FontWeight','bold');
    s.list=uicontrol(fig,'Style','listbox','Units','normalized','Position',[.015 .31 .22 .60], ...
        'FontSize',12,'String',{'尚无保存记录'},'Callback',@(~,~)select_row(fig));
    s.follow_button=uicontrol(fig,'Style','pushbutton','Units','normalized','Position',[.015 .25 .105 .045], ...
        'String','跟随最新','FontSize',12,'Callback',@(~,~)follow_latest(fig));
    s.folder_button=uicontrol(fig,'Style','pushbutton','Units','normalized','Position',[.13 .25 .105 .045], ...
        'String','打开目录','FontSize',12,'Callback',@(~,~)open_folder(fig));
    s.summary=uicontrol(fig,'Style','text','Units','normalized','Position',[.015 .025 .22 .21], ...
        'HorizontalAlignment','left','FontSize',12);
    s.axes=axes(fig,'Units','normalized','Position',[.25 .08 .735 .82]);
    s.caption=uicontrol(fig,'Style','text','Units','normalized','Position',[.25 .015 .735 .05], ...
        'HorizontalAlignment','left','FontSize',11);
    setappdata(fig,'rx_result_window_state',s);
end
s=getappdata(fig,'rx_result_window_state');
identity=char(string(field(snapshot,'task_id',''))); source=char(string(field(snapshot,'source_mode','unknown')));
if ~strcmp(s.task_id,identity) || ~strcmp(s.source_mode,source)
    s.selected=0; s.follow=true; s.image_key='';
end
s.task_id=identity; s.source_mode=source; s.snapshot=snapshot;
s.rows=field(snapshot,'rows',{}); if isstruct(s.rows), s.rows=num2cell(s.rows); end
if s.follow, s.selected=latest_row(s.rows); end
if s.selected>numel(s.rows), s.selected=numel(s.rows); end
labels=cell(1,numel(s.rows));
for k=1:numel(s.rows), labels{k}=sprintf('%d  %s',k,role_text(field(s.rows{k},'role','formal'))); end
if isempty(labels), labels={'尚无保存记录'}; end
set(s.list,'String',labels,'Value',max(1,s.selected));
phase=phase_text(field(snapshot,'phase',''),field(snapshot,'role',''));
if ~field(snapshot,'active',true), phase=field(snapshot,'reason','任务已结束'); end
set(s.status,'String',sprintf('%s  |  正式完成 %d / %d  |  已用 %.1f 秒',phase, ...
    field(snapshot,'completed',0),field(snapshot,'count',0),field(snapshot,'elapsed_s',0)));
setappdata(fig,'rx_result_window_state',s); render(fig);
if strcmp(action,'open') && strcmp(visible,'on')
    if strcmp(get(fig,'WindowState'),'minimized'), set(fig,'WindowState','normal'); end
    set(fig,'Visible','on'); figure(fig);
end
end
function select_row(fig)
s=getappdata(fig,'rx_result_window_state'); s.selected=get(s.list,'Value'); s.follow=false;
setappdata(fig,'rx_result_window_state',s); render(fig);
end
function follow_latest(fig)
s=getappdata(fig,'rx_result_window_state'); s.follow=true; s.selected=latest_row(s.rows);
set(s.list,'Value',max(1,s.selected)); setappdata(fig,'rx_result_window_state',s); render(fig);
end
function render(fig)
s=getappdata(fig,'rx_result_window_state'); row=struct();
if s.selected>=1 && s.selected<=numel(s.rows), row=s.rows{s.selected}; end
capture=field(row,'capture',struct()); obs=field(row,'observation',struct());
result=field(obs,'result',struct()); analysis=field(row,'analysis',struct());
% Legacy journals retain only the analysis directory. Read its small JSON.
if isempty(fieldnames(result)) && ~isempty(field(analysis,'run_dir',''))
    root=analysis.run_dir; candidates={fullfile(root,'data','demod_result.json'),fullfile(root,'demod_result.json')};
    for k=1:numel(candidates)
        if isfile(candidates{k})
            try, result=jsondecode(fileread(candidates{k})); catch, result=struct(); end
            break;
        end
    end
end
role=field(row,'role',''); failed=ismember(role,{'failed','cancelled'});
reason=field(obs,'attempt_reason',field(s.snapshot,'reason',''));
path='';
if ~failed
    path=field(result,'dashboard_path','');
    if isempty(path), path=field(capture,'dashboard_path',''); end
    if isempty(path)
        root=field(analysis,'run_dir',field(capture,'run_dir',''));
        if ~isempty(root), path=fullfile(root,'overview.png'); end
    end
end
% On failure before a row was saved, never show an earlier attempt as current.
if s.follow && ~field(s.snapshot,'active',true) && ...
        ~isempty(field(s.snapshot,'reason','')) && ...
        ~ismember(field(s.snapshot,'reason',''),{'测量完成','历史记录', ...
        '配平完成，已达到容差','配平停止：达到调整次数上限','配平停止：达到批准边界', ...
        '通信质量确认变差，已恢复此前设置','功率差不再改善，已恢复此前设置'}) && ~failed
    path=''; failed=true; reason=field(s.snapshot,'reason','任务结束');
    capture=field(s.snapshot,'current_capture',struct());
end
key=[path '|' reason '|' num2str(s.selected)];
if ~strcmp(key,s.image_key) || (isempty(s.image_path) && ~isempty(path) && isfile(path))
    cla(s.axes); s.image_path='';
    if ~isempty(path) && isfile(path)
        try
            image(s.axes,imread(path)); axis(s.axes,'image'); axis(s.axes,'off'); s.image_path=path;
        catch exception
            reason=['读取结果图失败：' exception.message];
        end
    end
    if isempty(s.image_path)
        axis(s.axes,[0 1 0 1]); axis(s.axes,'off');
        message='本次尚无可显示的保存图件'; if ~isempty(reason), message=[message newline reason]; end
        text(s.axes,.5,.5,message,'HorizontalAlignment','center','Interpreter','none','FontSize',13);
    end
    s.image_key=key;
end
m=field(obs,'metrics',field(result,'metrics',struct()));
lines={role_text(role)};
context=field(result,'measurement_context',field(capture,'measurement_context',struct()));
if isfield(context,'position') && ~isempty(context.position)
    context=msiq.rx_measurement_context(context);
    label=context.label;
    if isfield(context,'subband'), label=sprintf('%s | 子带 %d',label,context.subband); end
    lines{end+1}=label;
else
    lines{end+1}='位置未记录';
end
channels=field(capture,'actual_scope_channels',{});
if ~isempty(channels), lines{end+1}=['实际通道：' strjoin(cellstr(string(channels)),' / ')]; end
if failed
    lines{end+1}='本次失败或取消，未作为有效测试结果';
elseif ~isempty(fieldnames(m))
    if field(m,'valid',true)
        lines{end+1}=sprintf('纠错前 BER：%g',field(m,'pre_ber',NaN));
        lines{end+1}=sprintf('错误 / 比特：%g / %g',field(m,'pre_error_count',NaN),field(m,'pre_bit_count',NaN));
        lines{end+1}=sprintf('MER：%.3g dB',field(m,'mer_db',NaN));
    else
        lines{end+1}=['指标无效：' field(m,'reason','未取得有效统计')];
    end
else
    lines{end+1}='未取得解调指标（仅采集或尚未完成）';
end
if failed, lines{end+1}=reason; end
set(s.summary,'String',lines);
s.directory=field(capture,'run_dir',field(s.snapshot,'task_dir',''));
set(s.folder_button,'Enable',onoff(~isempty(s.directory)&&isfolder(s.directory)));
set(s.caption,'String',s.directory,'TooltipString',s.directory);
setappdata(fig,'rx_result_window_state',s);
end
function open_folder(fig)
s=getappdata(fig,'rx_result_window_state');
if isfolder(s.directory), if ispc, winopen(s.directory); else, web(s.directory,'-browser'); end; end
end
function out=field(in,key,fallback)
if isstruct(in)&&isfield(in,key), out=in.(key); else, out=fallback; end
end
function index=latest_row(rows)
index=numel(rows);
if index>0 && ismember(field(rows{index},'role',''),{'failed','cancelled'}), return; end
for k=numel(rows):-1:1
    if ismember(field(rows{k},'role',''),{'formal','正式'}), index=k; return; end
end
end
function out=onoff(value)
if value, out='on'; else, out='off'; end
end
function out=role_text(role)
switch role
    case {'formal','正式'}, out='正式测量'; case {'trial','试采'}, out='试采';
    case 'range_trial', out='量程排查'; case 'balance', out='配平';
    case {'confirm','confirmation','balance_confirmation'}, out='退化确认'; case 'failed', out='失败';
    case 'cancelled', out='已取消'; otherwise, out='等待采集';
end
end
function out=phase_text(phase,role)
switch phase
    case 'prepare_reference', out='正在准备发送参考';
    case 'capture', out=['正在采集：' role_text(role)];
    case 'demod', out='正在解调'; case 'range', out='正在调整量程';
    case 'write', out='正在下发配平设置'; case 'board_ready', out='正在核对板卡';
    otherwise, out='正在准备测试';
end
end
