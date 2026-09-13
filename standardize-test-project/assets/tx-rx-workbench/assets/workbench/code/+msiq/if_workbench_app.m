function fig = if_workbench_app(options)
%IF_WORKBENCH_APP Explicit-action UI. No instrument objects are created here.
if nargin < 1, options = struct(); end
profile = msiq.if_workbench('config',struct());
if isfield(options,'profile'), profile = msiq.if_workbench_config(options.profile); end
liveProfileLoaded = strcmp(profile.mode,'live');
busy = false;
closePending = false;
confirmedAt=''; boardDirty=false;
activeAction=''; stopPending=false; ownedAwg=false; cleanupProfile=[];
closingOff=false;
cachedRawPath=''; cachedRaw=struct();
displayResult=[];
txPlan = [];
visible = 'on';
if isfield(options,'Visible'), visible = options.Visible; end
fig = uifigure('Name','中频实验工作台','Position',[20 40 1240 660], ...
    'Visible','off','CloseRequestFcn',@closeWindow,'Color',[.96 .97 .98],'AutoResizeChildren','off');
if isfield(options,'Position'), fig.Position=options.Position; end
root=uigridlayout(fig,[3 1]); root.RowHeight={42,'1x',42}; root.Padding=[12 10 12 10];
header=uigridlayout(root,[1 3]); header.ColumnWidth={150,150,'1x'}; header.Padding=[0 0 0 0];
appTitle=uilabel(header,'Text','中频实验工作台','FontSize',16,'FontWeight','bold');
mode=uidropdown(header,'Items',{'离线模拟','真实设备'},'ItemsData',{'mock','live'},'ValueChangedFcn',@modeChanged);
status=uilabel(header,'Text','离线模拟 · 尚未连接仪器','FontWeight','bold','WordWrap','on');
main=uigridlayout(root,[1 2]); main.ColumnWidth={480,'1x'}; main.Padding=[0 0 0 0];
leftHost=uipanel(main,'BorderType','none','Scrollable','on','AutoResizeChildren','off');
leftContent=uipanel(leftHost,'BorderType','none','Position',[0 0 460 1100]);
left=uigridlayout(leftContent,[9 1]); left.Padding=[0 0 8 0];
left.RowHeight={330,320,285,32,0,32,0,32,0}; left.RowSpacing=8;
stagePanel=section(left,'阶段与接线');
s=uigridlayout(stagePanel,[9 2]); s.ColumnWidth={140,'1x'}; s.RowHeight={28,28,28,28,38,42,28,28,28}; s.RowSpacing=5;
uilabel(s,'Text','实验阶段');
stage=uidropdown(s,'Items',{'AWG直连','发端上变频输出','接收端I/Q'}, ...
    'ItemsData',{'direct','tx_if','rx_iq'},'ValueChangedFcn',@stageChanged);
uilabel(s,'Text','AWG 输出通道对');
awgPair=uidropdown(s,'Items',{'CH1 / CH2（I / Q）','CH3 / CH4（I / Q）','请选择支持的通道对'}, ...
    'ItemsData',{'pair_a_ch1_ch2','pair_b_ch3_ch4',''},'ValueChangedFcn',@wiringChanged);
uilabel(s,'Text','示波器输入 1');
scopeOne=uidropdown(s,'Items',{'CH1','CH2','CH3','CH4'}, ...
    'ItemsData',{'C1','C2','C3','C4'},'ValueChangedFcn',@wiringChanged);
scopeTwoLabel=uilabel(s,'Text','示波器输入 2');
scopeTwo=uidropdown(s,'Items',{'CH1','CH2','CH3','CH4'}, ...
    'ItemsData',{'C1','C2','C3','C4'},'ValueChangedFcn',@wiringChanged);
uibutton(s,'Text','确认当前接线','ButtonPushedFcn',@confirmWiring);
confirmed=uilabel(s,'Text','','WordWrap','on');
inputHint=uilabel(s,'Text','','WordWrap','on'); inputHint.Layout.Column=[1 2];
uibutton(s,'Text','加载本地配置','ButtonPushedFcn',@loadProfile);
configHint=uilabel(s,'Text','尚未加载实机配置','WordWrap','on');
hardwareConfirm=uicheckbox(s,'Text','已核对本次设备、接线与批准范围','Value',false,'ValueChangedFcn',@refreshReadiness);
hardwareConfirm.Layout.Column=[1 2];
wiringHint=uilabel(s,'Text','','WordWrap','on'); wiringHint.Layout.Column=[1 2];
awgPanel=section(left,'AWG 发送');
a=uigridlayout(awgPanel,[7 2]); a.ColumnWidth={'1x','1x'}; a.RowHeight={26,30,32,32,32,65,35}; a.RowSpacing=5;
uilabel(a,'Text','I 路幅度 / Vpp'); uilabel(a,'Text','Q 路幅度 / Vpp');
ampI=uieditfield(a,'text','ValueChangedFcn',@txChanged); ampQ=uieditfield(a,'text','ValueChangedFcn',@txChanged);
uilabel(a,'Text','播放模式'); memory=uidropdown(a,'Items',{'EXT / DIV4','INT'},'ItemsData',{'EXT','INT'},'ValueChangedFcn',@txChanged);
txPreview=uibutton(a,'Text','离线波形预览','ButtonPushedFcn',@(~,~) runAction('tx_plan'));
txPrepare=uibutton(a,'Text','读取状态并生成计划','ButtonPushedFcn',@(~,~) runAction('tx_prepare'));
txApply=uibutton(a,'Text','执行计划并开启输出','Enable','off','ButtonPushedFcn',@(~,~) runAction('tx_apply'));
txLevel=uibutton(a,'Text','下发 AWG 幅度','ButtonPushedFcn',@(~,~) runAction('tx_level'));
awgPlanBox=uitextarea(a,'Editable','off','Value',{'尚未生成 AWG 执行计划。'}); awgPlanBox.Layout.Column=[1 2];
awgHint=uilabel(a,'Text','','WordWrap','on'); awgHint.Layout.Column=[1 2];
controlPanel=section(left,'调节与采集');
c=uigridlayout(controlPanel,[6 1]); c.RowHeight={60,32,62,32,32,42}; c.RowSpacing=5;
boardInputs=uigridlayout(c,[2 3]); boardInputs.Padding=[0 0 0 0]; boardInputs.RowHeight={25,30};
uilabel(boardInputs,'Text','前级衰减 / dB'); uilabel(boardInputs,'Text','后级 I / dB'); uilabel(boardInputs,'Text','后级 Q / dB');
pre=uieditfield(boardInputs,'text','ValueChangedFcn',@boardEdited); iv=uieditfield(boardInputs,'text','ValueChangedFcn',@boardEdited); qv=uieditfield(boardInputs,'text','ValueChangedFcn',@boardEdited);
boardSet=uibutton(c,'Text','下发板卡设定','ButtonPushedFcn',@(~,~) runAction('board_set'));
boardState=uilabel(c,'Text','板卡状态尚未确认','WordWrap','on');
measureBar=uigridlayout(c,[1 2]); measureBar.Padding=[0 0 0 0];
captureButton=uibutton(measureBar,'Text','采集单点','ButtonPushedFcn',@(~,~) runAction('manual_capture'));
balanceButton=uibutton(measureBar,'Text','I/Q 自动配平','ButtonPushedFcn',@(~,~) runAction('balance'));
formalBar=uigridlayout(c,[1 2]); formalBar.Padding=[0 0 0 0];
compareButton=uibutton(formalBar,'Text','比较播放模式','ButtonPushedFcn',@(~,~) runAction('mode_compare'));
finalButton=uibutton(formalBar,'Text','固定设置测量 3 次','ButtonPushedFcn',@(~,~) runAction('final_capture'));
measureHint=uilabel(c,'Text','','WordWrap','on');
scanToggle=uibutton(left,'Text','展开：可选二维扫描','ButtonPushedFcn',@(~,~) toggleSection(5,310));
scanPanel=section(left,'可选二维扫描'); scanPanel.Visible='off';
g=uigridlayout(scanPanel,[5 4]); g.ColumnWidth={95,'1x','1x','1x'}; g.RowHeight={25,32,32,32,'1x'};
uilabel(g,'Text','衰减 / dB'); uilabel(g,'Text','起点'); uilabel(g,'Text','终点'); uilabel(g,'Text','步进');
uilabel(g,'Text','下变频前'); scanFields=cell(2,3);
for k=1:3, scanFields{1,k}=uieditfield(g,'text','ValueChangedFcn',@refreshReadiness); end
uilabel(g,'Text','下变频后');
for k=1:3, scanFields{2,k}=uieditfield(g,'text','ValueChangedFcn',@refreshReadiness); end
mockButton=uibutton(g,'Text','模拟扫描','Enable','off','ButtonPushedFcn',@(~,~) runAction('mock')); mockButton.Layout.Column=[1 2];
scanButton=uibutton(g,'Text','开始扫描','Enable','off','ButtonPushedFcn',@(~,~) runAction('scan')); scanButton.Layout.Column=[3 4];
planBox=uitextarea(g,'Editable','off','Value',{'尚未填写扫描范围。'}); planBox.Layout.Column=[1 4];
historyToggle=uibutton(left,'Text','展开：历史回放与恢复','ButtonPushedFcn',@(~,~) toggleSection(7,180));
historyPanel=section(left,'历史回放与恢复'); historyPanel.Visible='off';
h=uigridlayout(historyPanel,[4 2]); h.RowHeight={30,30,30,35};
uibutton(h,'Text','选择历史结果','ButtonPushedFcn',@chooseRun);
uibutton(h,'Text','打开结果文件夹','ButtonPushedFcn',@openRun);
uibutton(h,'Text','回放已保存结果','ButtonPushedFcn',@(~,~) runAction('replay'));
uibutton(h,'Text','离线重新解调','ButtonPushedFcn',@(~,~) runAction('replay_redecode'));
resumeButton=uibutton(h,'Text','确认状态后续扫','Enable','off','ButtonPushedFcn',@(~,~) runAction('resume')); resumeButton.Layout.Column=[1 2];
historyHint=uilabel(h,'Text','尚未选择历史结果','WordWrap','on'); historyHint.Layout.Column=[1 2];
detailToggle=uibutton(left,'Text','展开：记录详情','ButtonPushedFcn',@(~,~) toggleSection(9,330));
detailPanel=section(left,'记录详情'); detailPanel.Visible='off';
dg=uigridlayout(detailPanel,[6 2]); dg.ColumnWidth={120,'1x'}; dg.RowHeight={28,30,32,32,32,'1x'};
uilabel(dg,'Text','自动记录编号'); wiring=uilabel(dg,'Text','');
uilabel(dg,'Text','备注（选填）'); notes=uieditfield(dg,'text','ValueChangedFcn',@txChanged);
uibutton(dg,'Text','选择接线照片','ButtonPushedFcn',@choosePhoto); photos=uilabel(dg,'Text','','WordWrap','on');
uilabel(dg,'Text','完整结果路径'); runPath=uieditfield(dg,'text','ValueChangedFcn',@refreshReadiness);
uibutton(dg,'Text','检查扫描计划','ButtonPushedFcn',@(~,~) runAction('plan'));
uilabel(dg,'Text','以下为技术详情');
techBox=uitextarea(dg,'Editable','off'); techBox.Layout.Column=[1 2];
resultPanel=section(main,'波形与测量结果');
r=uigridlayout(resultPanel,[5 1]); r.RowHeight={30,110,'1x',65,42}; r.RowSpacing=8; r.Scrollable='on';
viewBar=uigridlayout(r,[1 2]); viewBar.Padding=[0 0 0 0]; viewBar.ColumnWidth={145,'1x'};
view=uidropdown(viewBar,'Items',{'原始波形','保存的频谱','MER趋势'},'ItemsData',{'waveform','spectrum','mer'},'Value','waveform','ValueChangedFcn',@changeView);
recordPicker=uidropdown(viewBar,'Items',{'尚无记录'},'ItemsData',0,'ValueChangedFcn',@changeView);
metricsBox=uitextarea(r,'Editable','off','Value',{'尚无测量结果。接线确认后，可进行单点采集。'});
chartPanel=uipanel(r,'BorderType','none','BackgroundColor',[1 1 1],'AutoResizeChildren','off');
ax=uiaxes(chartPanel,'Units','normalized','OuterPosition',[0 0 1 1],'PositionConstraint','outerposition'); title(ax,'等待采集'); xlabel(ax,'时间 / μs'); ylabel(ax,'电压 / V');
chartPanel.SizeChangedFcn=@layoutChart;
results=uitextarea(r,'Editable','off','Value',{'试采、配平、正式测量和排查分别记录。'});
progressLabel=uilabel(r,'Text','尚未开始测量','WordWrap','on');
footer=uigridlayout(root,[1 3]); footer.ColumnWidth={'1x',160,180}; footer.Padding=[0 0 0 0];
uilabel(footer,'Text','换线前，请先关闭输出并核对关闭结果。','WordWrap','on');
stopButton=uibutton(footer,'Text','停止当前任务','FontColor',[.7 .1 .1],'Enable','off','ButtonPushedFcn',@stopRun);
offButton=uibutton(footer,'Text','关闭 AWG 全部输出','FontWeight','bold','ButtonPushedFcn',@(~,~) runAction('awg_stop'));
fontControls=findall(root,'-property','FontSize'); set(fontControls,'FontSize',13);
appTitle.FontSize=16;
set([stagePanel awgPanel controlPanel scanPanel historyPanel detailPanel resultPanel],'FontSize',16,'FontWeight','bold');
set([inputHint configHint wiringHint awgHint measureHint historyHint progressLabel],'FontSize',12);
controls = findall(root,'-property','Enable');
controls(controls == stopButton) = [];
populate();
fig.SizeChangedFcn=@resizeLayout;
resizeLayout();
leftHost.SizeChangedFcn=@layoutLeft;
scroll(leftHost,'top');
fig.UserData = struct('getProfile',@gather,'lastResult',[], ...
    'runAction',@runAction,'stage',stage,'mode',mode,'status',status,'view',view, ...
    'scanButton',scanButton,'resumeButton',resumeButton,'mockButton',mockButton, ...
    'scanFields',{scanFields},'refreshReadiness',@refreshReadiness, ...
    'awgPair',awgPair,'scopeOne',scopeOne,'scopeTwo',scopeTwo, ...
    'wiringChanged',@wiringChanged,'confirmWiring',@confirmWiring, ...
    'ampI',ampI,'ampQ',ampQ,'runPath',runPath,'awgPlanBox',awgPlanBox,'planBox',planBox, ...
    'recordPicker',recordPicker,'metricsBox',metricsBox,'results',results,'wiring',wiring, ...
    'confirmed',confirmed,'txChanged',@txChanged,'showAwgPlan',@showAwgPlan, ...
    'captureButton',captureButton,'offButton',offButton,'stopButton',stopButton, ...
    'boardState',boardState,'pre',pre,'boardEdited',@boardEdited,'present',@present, ...
    'left',left,'scrollHost',leftHost,'root',root,'toggleSection',@toggleSection);
drawnow;
resizeLayout();
scroll(leftHost,'top');
fig.Visible=visible;

    function populate()
        stage.Value = get(profile,{'stage'},'rx_iq');
        mode.Value = 'mock';
        route = get(profile,{'tx_options','route'},'pair_a_ch1_ch2');
        if ~ismember(route,awgPair.ItemsData), route=''; end
        if ~isempty(route)
            try
                actual=msiq.resolve_awg_route(profile.tx_options);
                canonical=msiq.resolve_awg_route(struct('route',route));
                if ~isequal(actual,canonical), route=''; end
            catch
                route='';
            end
        end
        awgPair.Value = route;
        ch = profile.scope.channels;
        scopeOne.Value = ch{1};
        if numel(ch)==2, scopeTwo.Value=ch{2}; else, scopeTwo.Value='C4'; end
        wiring.Text = char(string(get(profile,{'wiring','id'},'')));
        confirmedAt = char(string(get(profile,{'wiring','confirmed_at'},'')));
        notes.Value = char(string(get(profile,{'wiring','notes'},'')));
        photos.Text = char(string(get(profile,{'wiring','photo_index'},'')));
        pre.Value = numtext(get(profile,{'initial','pre_db'},[]));
        iv.Value = numtext(get(profile,{'initial','i_db'},[]));
        qv.Value = numtext(get(profile,{'initial','q_db'},[]));
        amp=get(profile,{'tx_options','amplitude_vpp'},[]);
        if numel(amp)==2, ampI.Value=numtext(amp(1)); ampQ.Value=numtext(amp(2));
        else, ampI.Value=''; ampQ.Value=''; end
        memory.Value=upper(get(profile,{'tx_options','memory_mode'},'EXT'));
        names = {'pre_start_db','pre_stop_db','pre_step_db';'post_start_db','post_stop_db','post_step_db'};
        for row=1:2
            for col=1:3
                v = get(profile,{'scan',names{row,col}},[]);
                scanFields{row,col}.Value = numtext(v);
            end
        end
        updateWiringView();
        refreshReadiness();
    end
    function stageChanged(~,~)
        if strcmp(stage.Value,'tx_if'), scopeOne.Value='C2'; end
        wiringChanged();
    end
    function updateWiringView()
        if isempty(confirmedAt), confirmed.Text='尚未确认接线'; confirmed.FontColor=[.65 .3 .05];
        else, confirmed.Text=['已确认：' confirmedAt]; confirmed.FontColor=[.1 .4 .25]; end
        isTx=strcmp(stage.Value,'tx_if'); isDirect=strcmp(stage.Value,'direct');
        scopeTwo.Visible=onoff(~isTx); scopeTwoLabel.Visible=onoff(~isTx);
        heights=s.RowHeight; if isTx, heights{4}=0; else, heights{4}=28; end; s.RowHeight=heights;
        boardInputs.Visible=onoff(~isDirect); boardSet.Visible=onoff(~isDirect); boardState.Visible=onoff(~isDirect);
        balanceButton.Visible=onoff(strcmp(stage.Value,'rx_iq'));
        compareButton.Visible=onoff(isDirect); finalButton.Visible=onoff(strcmp(stage.Value,'rx_iq'));
        rows=c.RowHeight; if isDirect, rows(1:3)={0,0,0}; else, rows(1:3)={60,32,62}; end; c.RowHeight=rows;
        lr=left.RowHeight; if isDirect, lr{3}=155; else, lr{3}=309; end; left.RowHeight=lr;
        scanToggle.Visible=onoff(strcmp(stage.Value,'rx_iq'));
        if ~strcmp(stage.Value,'rx_iq'), scanPanel.Visible='off'; lr=left.RowHeight; lr{5}=0; left.RowHeight=lr; end
        layoutLeft();
        if strcmp(stage.Value,'tx_if')
            scopeOne.Enable='off'; scopeTwo.Enable='off';
            inputHint.Text = '下侧 CH2（已确定的测量通道）；需手动切换输入侧并接线。';
        else
            scopeOne.Enable='on'; scopeTwo.Enable='on';
            inputHint.Text = sprintf('上侧 %s / %s；需手动接线。输入顺序不代表板卡物理 I/Q 映射。',scopeOne.Value,scopeTwo.Value);
        end
    end
    function wiringChanged(~,~)
        wiring.Text=''; confirmedAt=''; hardwareConfirm.Value=false; txPlan=[]; awgPlanBox.Value={'接线已变更，请重新生成 AWG 计划。'};
        updateWiringView();
        refreshReadiness();
    end
    function confirmWiring(~,~)
        try
            gather(false,false); % Reject duplicate inputs before recording a confirmation.
            if isempty(wiring.Text)
                wiring.Text=['W_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))];
            end
            confirmedAt=char(datetime('now','Format','yyyy-MM-dd HH:mm:ss.SSS'));
            updateWiringView(); txChanged();
            refreshReadiness();
        catch err
            status.Text=err.message;
        end
    end
    function p = gather(includeScan,includeTx)
        if nargin<1, includeScan=true; end
        if nargin<2, includeTx=true; end
        p = profile; p.stage = stage.Value; p.mode = mode.Value;
        if ~isfield(p,'wiring'), p.wiring = struct(); end
        p.wiring.id = wiring.Text; p.wiring.confirmed_at = confirmedAt;
        p.wiring.notes = notes.Value; p.wiring.photo_index = photos.Text;
        if ~isfield(p,'tx_options'), p.tx_options=struct(); end
        assert(~isempty(awgPair.Value),'msiq:if:Wiring','请选择 AWG 支持的通道对。');
        p.tx_options.route=awgPair.Value;
        % Use the selected canonical route; stale legacy overrides must not win.
        for key={'awg_channels','waveform_columns','scope_channels','labels'}
            if isfield(p.tx_options,key{1}), p.tx_options=rmfield(p.tx_options,key{1}); end
        end
        if strcmp(stage.Value,'tx_if')
            p.scope.channels={'C2'}; p.scope.side='lower';
        else
            assert(~strcmp(scopeOne.Value,scopeTwo.Value),'msiq:if:Wiring','示波器两路输入不能选择同一通道。');
            p.scope.channels={scopeOne.Value,scopeTwo.Value}; p.scope.side='upper';
        end
        p.wiring.connections=struct('awg_route',awgPair.Value, ...
            'scope_channels',{p.scope.channels},'scope_side',p.scope.side,'stage',p.stage);
        if includeTx, p.tx_options.amplitude_vpp=[number(ampI.Value) number(ampQ.Value)]; end
        p.tx_options.offset_v=[0 0]; p.tx_options.memory_mode=memory.Value;
        if ~isfield(p,'scan'), p.scan = struct(); end
        names = {'pre_start_db','pre_stop_db','pre_step_db';'post_start_db','post_stop_db','post_step_db'};
        for row=1:2
            for col=1:3
                if includeScan, p.scan.(names{row,col}) = number(scanFields{row,col}.Value); end
            end
        end
    end
    function runAction(action)
        if busy, return; end
        try
            if ismember(action,{'awg_stop','replay','replay_redecode'})
                % Closing all outputs does not depend on valid routing edits.
                stopProfile=profile; stopProfile.mode=mode.Value;
                opts=struct('profile',stopProfile);
            else
                opts = struct('profile',gather(ismember(action,{'plan','scan','mock','resume'}), ...
                    ismember(action,{'tx_plan','tx_prepare','tx_apply','tx_level','mode_compare'})));
            end
            opts.run_dir = runPath.Value;
            opts.progress_callback=@showProgress;
            if strcmp(action,'board_set')
                opts.setting = struct('pre_db',number(pre.Value),'i_db',number(iv.Value),'q_db',number(qv.Value));
            end
            if strcmp(action,'mock'), opts.profile.mode = 'mock'; end
            if strcmp(action,'tx_apply')
                if isempty(txPlan), error('msiq:if:Plan','请先读取状态并生成执行计划。'); end
                opts.plan=txPlan;
                opts.confirmation_phrase=txPlan.required_confirmation;
            end
            liveAction = strcmp(opts.profile.mode,'live') && ~ismember(action,{'plan','replay','replay_redecode','mock','tx_plan'});
            if liveAction
                if ~liveProfileLoaded
                    error('msiq:if:LiveProfile','请加载本地真实设备配置；离线模拟参数不能用于真实操作。');
                end
                if ~hardwareConfirm.Value
                    error('msiq:if:Confirmation','请先核对并勾选本次真实操作确认。');
                end
                opts.hardware_confirmed = true;
                cleanupProfile=opts.profile;
                if strcmp(action,'tx_apply'), ownedAwg=true; end
                hardwareConfirm.Value = false;
            end
            if ~liveAction, opts.hardware_confirmed = false; end
            busy = true; activeAction=action; stopPending=false;
            status.Text = '运行中；可请求停止';
            if ismember(action,{'tx_prepare','tx_level','awg_stop'})
                status.Text='正在进行设备操作；停止请求将在当前步骤返回后收尾';
            end
            set(controls,'Enable','off'); stopButton.Enable='on';
            cleanup = onCleanup(@finish); %#ok<NASGU>
            drawnow;
            backendAction=action;
            if strcmp(action,'replay_redecode'), backendAction='replay'; opts.redecode=true; end
            out = msiq.if_workbench(backendAction,opts);
            drawnow; % Deliver stop/close requests queued during a blocking device step.
            if ~isvalid(fig), return; end
            if stopPending&&liveAction&&ismember(action,{'tx_prepare','tx_apply','tx_level','awg_stop'})
                [closed,report]=closeOwnedAwg();
                out.shutdown=report;
                if closed, out.status='cancelled'; else, out.status='shutdown_failed'; end
            end
            if get(out,{'shutdown','awg_off_verified'},false)&&liveAction, ownedAwg=false; end
            if strcmp(action,'awg_stop')&&isfield(out,'state')&&~any(out.state.outputs), ownedAwg=false; end
            if isfield(out,'board_final') && ~strcmp(backendAction,'replay')
                if ~isfield(profile,'board'), profile.board=struct(); end
                if get(out.board_final,{'state_known'},false)&&isfield(out.board_final,'state')
                    profile.board.initial_state=out.board_final.state;
                    profile.board.initial_state_confirmed=true;
                    profile.board.state_confirmation='prior sent state, manually confirmed by next action checkbox';
                    if isfield(out,'final_setting')
                        profile.initial=out.final_setting;
                        if ~boardDirty||ismember(action,{'board_set','balance','final_capture','scan','resume'})
                            pre.Value=numtext(profile.initial.pre_db);
                            iv.Value=numtext(profile.initial.i_db);
                            qv.Value=numtext(profile.initial.q_db); boardDirty=false;
                        end
                    end
                    if strcmp(opts.profile.mode,'mock')
                        % Never carry synthetic board state into a loaded live profile.
                        liveProfileLoaded=false;
                        profile.mock_fixture_applied=true;
                    end
                else
                    profile.board.initial_state_confirmed=false;
                    if ~strcmp(opts.profile.stage,'direct'), liveProfileLoaded=false; end
                end
            end
            data = fig.UserData; data.lastResult = out; fig.UserData = data;
            present(out);
            if isfield(out,'run_dir') && ~isempty(out.run_dir), runPath.Value=char(string(out.run_dir)); end
            if isfield(out,'plan')&&ismember(action,{'tx_plan','tx_prepare'}), showAwgPlan(out.plan); end
            if strcmp(action,'tx_prepare')&&isfield(out,'plan'), txPlan=out.plan; end
            if strcmp(action,'tx_apply'), txPlan=[]; awgPlanBox.Value={'计划已执行；再次开启前须重新生成计划。'}; end
            if strcmp(action,'plan'), planBox.Value=scanSummary(out); end
            if ~strcmp(action,'plan'), v=msiq.if_ui_present(out); status.Text=v.state; end
            if strcmp(action,'board_set'), boardDirty=false; end
            if ~ismember(action,{'replay','replay_redecode','plan'}), showBoardState(out); end
            plotResult(out);
        catch err
            drawnow;
            if isvalid(fig), status.Text='操作未完成'; results.Value={friendlyError(err)}; techBox.Value={err.message}; end
            if stopPending&&~isempty(cleanupProfile)&&ismember(activeAction,{'tx_prepare','tx_apply','tx_level','awg_stop'})
                closeOwnedAwg();
            end
        end
    end
    function finish()
        busy = false;
        if isvalid(fig), set(controls(isvalid(controls)),'Enable','on'); stopButton.Enable='off'; end
        if isvalid(fig), updateWiringView(); refreshReadiness(); end
        if closePending && isvalid(fig)
            if ownedAwg
                [closed,~]=closeOwnedAwg();
                if ~closed, closePending=false; return; end
            end
            delete(fig);
        end
    end
    function stopRun(~,~)
        try
            stopPending=true;
            msiq.if_workbench('stop',struct());
            status.Text='已请求停止，等待当前操作安全收尾';
        catch err
            status.Text='停止请求失败'; results.Value={friendlyError(err)}; techBox.Value={err.message};
        end
    end
    function closeWindow(~,~)
        if closingOff, return; end
        if busy
            closePending = true; stopRun();
        else
            if ownedAwg
                [closed,~]=closeOwnedAwg();
                if ~closed, return; end
            end
            delete(fig);
        end
    end
    function [closed,report]=closeOwnedAwg()
        closed=false;
        report=struct('awg_off_verified',false,'errors',{{}});
        if isempty(cleanupProfile)||~strcmp(cleanupProfile.mode,'live'), return; end
        if closingOff, return; end
        closingOff=true; offGuard=onCleanup(@endClosingOff); %#ok<NASGU>
        status.Text='正在收尾，核验 AWG 全部输出关闭'; drawnow;
        try
            receipt=msiq.if_workbench('awg_stop',struct('profile',cleanupProfile,'hardware_confirmed',true));
            closed=isfield(receipt,'state')&&numel(receipt.state.outputs)==4&&~any(receipt.state.outputs);
            report.awg_off_verified=closed; report.receipt=receipt;
            if ~closed, report.errors={'关闭后的输出状态核验未通过。'}; end
        catch err
            report.errors={err.message};
        end
        if closed, ownedAwg=false; status.Text='已停止；已核验 AWG 全部输出关闭';
        else, ownedAwg=true; status.Text='关闭状态未确认；窗口保留，请检查设备'; end
        report.parent_run=runPath.Value;
        try
            logRun=msiq.create_output_run(msiq.build_config('v2_traditional_wz'),'measurement','IF_UI_shutdown');
            Result_Atomic_Write_Json(fullfile(logRun.DataDir,'shutdown.json'),report);
        catch err
            report.errors{end+1}=['关断记录保存失败：' err.message];
            results.Value={'关断记录保存失败，请查看技术详情。'};
        end
        techBox.Value=describe(report);
    end
    function endClosingOff()
        closingOff=false;
    end
    function loadProfile(~,~)
        if busy, return; end
        [file,path]=uigetfile({'*.json;*.mat','本地配置 (*.json, *.mat)'});
        if isequal(file,0), return; end
        try
            [~,~,ext]=fileparts(file);
            if strcmpi(ext,'.json')
                loaded=jsondecode(fileread(fullfile(path,file)));
            else
                loaded=load(fullfile(path,file));
            end
            if isfield(loaded,'profile'), loaded=loaded.profile; end
            if ~isstruct(loaded) || ~isscalar(loaded), error('配置必须是一个结构体。'); end
            profile=msiq.if_workbench_config(loaded);
            txPlan=[];
            liveProfileLoaded=strcmp(profile.mode,'live');
            populate();
            hardwareConfirm.Value=false;
            status.Text='已加载；仍为离线模拟，请检查计划';
        catch err
            results.Value={friendlyError(err)}; techBox.Value={err.message};
        end
    end
    function chooseRun(~,~)
        if busy, return; end
        folder=uigetdir(pwd,'选择已有结果目录');
        if ~isequal(folder,0), runPath.Value=folder; refreshReadiness(); end
    end
    function refreshReadiness(~,~)
        if busy, return; end
        scanButton.Enable='off'; resumeButton.Enable='off'; mockButton.Enable='off';
        isLive=strcmp(mode.Value,'live');
        mode.FontColor=[.1 .35 .55]; if isLive, mode.FontColor=[.7 .22 .05]; end
        if liveProfileLoaded, configHint.Text='已加载本地实机配置'; else, configHint.Text='未加载实机配置；可离线模拟'; end
        liveOK=isLive&&liveProfileLoaded&&hardwareConfirm.Value;
        offButton.Enable=onoff(liveOK&&ismember('awg',profile.authorized_devices));
        txPrepare.Enable='off'; txApply.Enable='off'; txLevel.Enable='off';
        for button=[captureButton balanceButton finalButton compareButton boardSet], button.Enable='off'; end
        try
            p=gather(false,false);
            try, p.tx_options.amplitude_vpp=[number(ampI.Value) number(ampQ.Value)];
            catch, p.tx_options.amplitude_vpp=[NaN NaN]; end
            wiringHint.Text='';
            if isempty(confirmedAt), wiringHint.Text='实机操作前，请核对并确认实际接线。'; end
            amp=p.tx_options.amplitude_vpp; lim=p.comparison.amplitude_bounds_vpp;
            ampOK=numel(amp)==2&&all(isfinite(amp))&&all(amp>0);
            txPreview.Enable=onoff(ampOK);
            awgHint.Text='填写两路幅度后可离线预览；实机控制需加载配置并确认。';
            if numel(lim)==2&&all(isfinite(lim))
                prefix='本地批准幅度'; if ~isLive, prefix='模拟幅度范围'; end
                awgHint.Text=sprintf('%s：%.3g～%.3g Vpp；零偏置。',prefix,lim(1),lim(2));
                ampOK=ampOK&&all(amp>=lim(1)&amp<=lim(2));
            elseif isLive
                ampOK=false; awgHint.Text='本地批准幅度范围尚未配置。';
            end
            txOK=liveOK&&ampOK&&~isempty(confirmedAt)&&ismember('awg',p.authorized_devices);
            txPrepare.Enable=onoff(txOK); txLevel.Enable=onoff(txOK);
            txApply.Enable=onoff(txOK&&~isempty(txPlan));
            if ~isempty(txPlan)&&(~isequaln(get(txPlan,{'if_requested_tx'},struct()),p.tx_options)|| ...
                    ~isequaln(get(txPlan,{'if_wiring'},struct()),p.wiring))
                txPlan=[]; txApply.Enable='off'; awgPlanBox.Value={'设置已变更，请重新生成 AWG 计划。'};
            end
            measureHint.Text='先试采和配平，再固定设置测量；无需填写扫描范围。';
            if isLive && ~liveOK, measureHint.Text='加载实机配置，并勾选本次操作确认后才能采集。'; end
            buttons=[captureButton balanceButton finalButton compareButton boardSet];
            actions={'manual_capture','balance','final_capture','mode_compare','board_set'};
            for k=1:numel(buttons)
                try
                    [checked,devices]=msiq.if_workbench_validate_profile(p,actions{k}); %#ok<ASGLU>
                    ok=~isLive||liveOK;
                    if isLive
                        ok=ok&&~p.mock_fixture_applied&&~isempty(confirmedAt)&&all(ismember(devices,p.authorized_devices));
                        if ~strcmp(actions{k},'board_set')
                            referenceOK=strcmp(actions{k},'mode_compare')||isfile(p.reference_bundle);
                            ok=ok&&referenceOK&&p.scope.fresh.verified;
                            if ~referenceOK, buttons(k).Tooltip='请先配置有效的发送参考文件。'; end
                            if ~p.scope.fresh.verified, buttons(k).Tooltip='新采集完成判据尚未验证。'; end
                            if k==1&&~ok&&liveOK, measureHint.Text=buttons(k).Tooltip; end
                        end
                    end
                    if strcmp(actions{k},'mode_compare'), ok=ok&&strcmp(p.stage,'direct'); end
                    if ismember(actions{k},{'balance','final_capture'}), ok=ok&&strcmp(p.stage,'rx_iq'); end
                    buttons(k).Enable=onoff(ok);
                catch ex
                    buttons(k).Tooltip=friendlyError(ex);
                    if k==1, measureHint.Text=friendlyError(ex); end
                end
            end
        catch ex
            txPreview.Enable='off'; wiringHint.Text=friendlyError(ex); measureHint.Text=friendlyError(ex);
        end
        try
            p=gather(true,false); readiness=msiq.if_workbench('plan',struct('profile',p));
            planBox.Value=scanSummary(readiness);
            ready=readiness.automatic_ready&&strcmp(p.stage,'rx_iq');
            if isLive, ready=ready&&liveOK; end
            scanButton.Enable=onoff(ready);
            resumeButton.Enable=onoff(ready&&isfolder(runPath.Value));
            p.mode='mock'; mockReady=msiq.if_workbench('plan',struct('profile',p));
            mockButton.Enable=onoff(mockReady.automatic_ready&&strcmp(p.stage,'rx_iq'));
        catch ex
            planBox.Value={friendlyError(ex)};
        end
        for k=1:3
            edits=[pre iv qv]; keys={'rf','i','q'};
            lim=get(profile,{'board','limits',keys{k}},[]);
            if ~isempty(lim)
                edits(k).Tooltip=sprintf('本地批准范围：%.1f～%.1f dB',lim(profile.subband,1),lim(profile.subband,2));
            else
                edits(k).Tooltip='尚未配置本地批准范围；模拟可使用合成设置。';
            end
        end
        if ~isempty(runPath.Value), [~,name]=fileparts(runPath.Value); historyHint.Text=['已选择：' name]; end
    end
    function p=section(parent,titleText)
        p=uipanel(parent,'Title',titleText,'FontSize',16,'FontWeight','bold', ...
            'BackgroundColor',[.98 .985 .99],'BorderType','line');
    end
    function resizeLayout(~,~)
        width=fig.Position(3); height=fig.Position(4);
        main.ColumnWidth={min(480,max(360,round(width*.39))),'1x'};
        if height<600, r.RowHeight={30,110,160,65,42};
        else, r.RowHeight={30,110,'1x',65,42}; end
        drawnow nocallbacks;
        layoutLeft();
        layoutChart();
    end
    function layoutLeft(~,~)
        height=sum(cell2mat(left.RowHeight))+left.RowSpacing*(numel(left.RowHeight)-1)+left.Padding(2)+left.Padding(4);
        leftContent.Position=[0 0 max(300,main.ColumnWidth{1}-20) height];
    end
    function layoutChart(~,~)
        chartWidth=fig.Position(3)-main.ColumnWidth{1}-54;
        if fig.Position(4)<600, chartWidth=chartWidth-20; chartHeight=160;
        else, chartHeight=max(160,fig.Position(4)-448); end
        ax.Units='pixels'; ax.PositionConstraint='innerposition';
        ax.Position=[60 38 max(120,chartWidth-80) max(60,chartHeight-68)];
        if ~busy&&~isempty(displayResult), plotResult(displayResult); end
    end
    function toggleSection(row,height)
        lr=left.RowHeight;
        panels={scanPanel,historyPanel,detailPanel}; toggles={scanToggle,historyToggle,detailToggle};
        ix=(row-3)/2; labels={'可选二维扫描','历史回放与恢复','记录详情'};
        if lr{row}==0
            lr{row}=height; panels{ix}.Visible='on'; toggles{ix}.Text=['收起：' labels{ix}];
        else
            lr{row}=0; panels{ix}.Visible='off'; toggles{ix}.Text=['展开：' labels{ix}];
        end
        left.RowHeight=lr;
        layoutLeft();
    end
    function modeChanged(~,~)
        hardwareConfirm.Value=false; txChanged();
        if strcmp(mode.Value,'mock'), status.Text='离线模拟 · 不连接仪器';
        else, status.Text='真实设备模式 · 等待显式操作'; end
    end
    function txChanged(~,~)
        txPlan=[]; txApply.Enable='off';
        awgPlanBox.Value={'设置已变更；请重新生成 AWG 执行计划。'};
        refreshReadiness();
    end
    function boardEdited(~,~)
        boardDirty=true; boardState.Text='待下发设置已修改，尚未下发。';
        try
            values=[number(pre.Value),number(iv.Value),number(qv.Value)];
            assert(numel(values)==3&&all(values>=0&values<=31.5)&&all(abs(values*2-round(values*2))<1e-9), ...
                'msiq:if:Setting','衰减必须填写为 0～31.5 dB 内的 0.5 dB 档位。');
            b=profile.board; keys={'rf','i','q'};
            for k=1:3
                lim=get(b,{'limits',keys{k}},[]);
                if ~isempty(lim)
                    bounds=lim(profile.subband,:);
                    assert(values(k)>=bounds(1)&&values(k)<=bounds(2),'msiq:if:Setting','设置超出本地批准范围。');
                end
            end
            refreshReadiness();
        catch ex
            boardSet.Enable='off'; measureHint.Text=friendlyError(ex);
        end
    end
    function showBoardState(out)
        if ~isfield(out,'board_final'), return; end
        b=out.board_final;
        if ~get(b,{'state_known'},false), boardState.Text='板卡状态未确认；禁止静默重发。'; return; end
        st=get(b,{'state'},struct()); n=profile.subband;
        if ~all(isfield(st,{'rf','i','q'})), return; end
        sent=get(b,{'sent'},struct()); keys={'rf','i','q'}; labels={'前级','I','Q'}; parts=cell(1,3);
        for k=1:3
            sentValues=get(sent,{keys{k}},[]); source='人工确认';
            if numel(sentValues)>=n&&isfinite(sentValues(n)), source='已发送'; end
            if strcmp(get(out,{'profile','mode'},mode.Value),'mock'), source='模拟'; end
            parts{k}=sprintf('%s %.1f dB（%s）',labels{k},st.(keys{k})(n),source);
        end
        boardState.Text=[strjoin(parts,' / ') '；无可信衰减回读。'];
        rb=get(b,{'readback'},struct());
        if isstruct(rb)&&any(isfield(rb,{'lock_status','i_power_raw','q_power_raw'}))
            boardState.Text=[boardState.Text ' 已接收状态报文，见详情。'];
        end
        if boardDirty, boardState.Text=['待输入修改尚未下发。' boardState.Text]; end
    end
    function choosePhoto(~,~)
        [name,path]=uigetfile({'*.png;*.jpg;*.jpeg;*.bmp','接线照片'},'选择接线照片');
        if isequal(name,0), return; end
        photos.Text=fullfile(path,name); photos.Tooltip=photos.Text; txChanged();
    end
    function openRun(~,~)
        if isfolder(runPath.Value), winopen(runPath.Value);
        else, historyHint.Text='请先选择存在的结果目录。'; end
    end
    function showAwgPlan(plan)
        amps=get(plan,{'levels','amplitude_vpp'},get(profile,{'tx_options','amplitude_vpp'},[]));
        play=get(plan,{'desired','memory_mode'},memory.Value);
        awgPlanBox.Value={['AWG 通道对：' awgPair.Items{strcmp(awgPair.ItemsData,awgPair.Value)}]; ...
            ['播放模式：' char(string(play)) '；幅度 / Vpp：' num2str(amps)]; ...
            '执行顺序：关闭全部输出并核验 → 配置与下载 → 核对 → 开启选定通道。'};
        techBox.Value=describe(plan);
    end
    function present(out)
        v=msiq.if_ui_present(out); results.Value=v.summary; techBox.Value=v.detail;
        if ~isempty(v.records)
            displayResult=out; metricsBox.Value=v.metrics;
            metricsBox.Tooltip=['测量来源：' char(string(get(out,{'run_dir'},'')))];
            recordPicker.Items=v.records; recordPicker.ItemsData=1:numel(v.records); recordPicker.Value=numel(v.records);
        end
    end
    function showProgress(p)
        if ~isvalid(fig), return; end
        phase='正在测量';
        if ismember(p.phase,{'completed','cancelled','paused','shutdown_failed','save_failed'}), phase='本次操作已结束';
        elseif strcmp(p.phase,'shutting_down'), phase='正在收尾，核验输出关闭';
        elseif startsWith(p.phase,'capture_'), phase='正在采集';
        elseif strcmp(p.phase,'shutdown_complete'), phase='关断检查完成'; end
        progressLabel.Text=sprintf('%s；已采集 %d 条，正式 %d 次；耗时 %.1f 秒', ...
            phase,p.observation_count,p.formal_count,p.elapsed_s);
        if isfield(p,'estimated_remaining_s')&&isfinite(p.estimated_remaining_s)
            progressLabel.Text=[progressLabel.Text sprintf('；预计剩余 %.1f 秒',p.estimated_remaining_s)];
        end
        if strcmp(p.phase,'shutting_down'), status.Text=phase; end
    end
    function lines=scanSummary(p)
        lines={sprintf('计划点位：%d；正常点正式采 1 次，疑似退化复测至 3 次。',size(p.points,1))};
        if isempty(p.blockers), lines{end+1}='扫描参数检查通过；扫描为可选操作。';
        else
            for k=1:numel(p.blockers), lines{end+1}=friendlyError(p.blockers{k}); end
        end
    end
    function plotResult(out)
        if ~isfield(out,'observations') || isempty(out.observations), return; end
        obs=out.observations;
        if iscell(obs), obs=[obs{:}]; end
        if ~isstruct(obs), return; end
        cla(ax); legend(ax,'off'); ax.YScale='linear';
        if ~strcmp(view.Value,'mer')
            selected=max(1,min(numel(obs),recordPicker.Value));
            path=get(obs(selected),{'raw_path'},'');
            if isempty(path)||~isfile(path)
                title(ax,'找不到已保存的原始波形文件'); return;
            end
            if ~strcmp(cachedRawPath,path)
                cachedRaw=load(path,'raw','spectrum'); cachedRawPath=path;
            end
            saved=cachedRaw;
            hold(ax,'on'); cleanupPlot=onCleanup(@() hold(ax,'off')); %#ok<NASGU>
            if strcmp(view.Value,'waveform')
                if ~isfield(saved,'raw')||~isfield(saved.raw,'channels'), return; end
                for k=1:numel(saved.raw.channels)
                    ch=saved.raw.channels(k);
                    stride=max(1,ceil(numel(ch.samples)/10000)); ix=1:stride:numel(ch.samples);
                    plot(ax,ch.time_axis_s(ix)*1e6,ch.samples(ix),'DisplayName',ch.channel);
                end
                xlabel(ax,'时间 / μs'); ylabel(ax,'电压 / V');
                title(ax,'所选记录原始波形');
            else
                if ~isfield(saved,'spectrum')||~iscell(saved.spectrum), return; end
                for k=1:numel(saved.spectrum)
                    sp=saved.spectrum{k};
                    plot(ax,sp.frequency_hz/1e9,max(realmin,sp.power_v2_bin), ...
                        'DisplayName',saved.raw.channels(k).channel);
                end
                ax.YScale='log'; xlabel(ax,'频率 / GHz'); ylabel(ax,'每频点电压平方 / V²/bin');
                title(ax,'保存的双边频谱（未换算为 dBm）');
            end
            legend(ax,'show'); return;
        end
        values=nan(1,numel(obs));
        for n=1:numel(obs)
            if get(obs(n),{'metrics','valid'},false)
                values(n)=get(obs(n),{'mer_db'},get(obs(n),{'metrics','mer_db'},NaN));
            end
        end
        if any(isfinite(values))
            plot(ax,1:numel(values),values,'o-'); title(ax,'逐次 MER（详细有效性见结果）');
        else
            title(ax,'尚无有效 MER');
        end
        xlabel(ax,'采集序号'); ylabel(ax,'MER / dB');
    end
    function changeView(~,~)
        out=displayResult;
        if isempty(out), return; end
        try, v=msiq.if_ui_present(out,recordPicker.Value); metricsBox.Value=v.metrics; plotResult(out); catch err, title(ax,'无法显示保存的数据'); results.Value={friendlyError(err)}; techBox.Value={err.message}; end
    end
end

function value = get(s,path,fallback)
value=s;
for k=1:numel(path)
    if ~isstruct(value) || ~isscalar(value) || ~isfield(value,path{k})
        value=fallback; return;
    end
    value=value.(path{k});
end
end
function n = number(text)
if isempty(strtrim(text)), n=[]; return; end
n=str2double(text);
if ~isscalar(n) || ~isfinite(n), error('msiq:if:UIValue','请输入有限数值，或留空。'); end
end
function text = numtext(n)
if isempty(n) || (isnumeric(n) && any(~isfinite(n(:))))
    text='';
else
    text=num2str(n);
end
end
function lines = describe(value)
if isstruct(value) && isscalar(value) && isfield(value,'observations')
    lines={['状态：' char(string(get(value,{'status'},'')))]; ...
        ['结果目录：' char(string(get(value,{'run_dir'},'')))]};
    obs=value.observations;
    if iscell(obs), obs=[obs{:}]; end
    for k=1:numel(obs)
        valid=get(obs(k),{'metrics','valid'},false);
        role=char(string(get(obs(k),{'role'},get(obs(k),{'kind'},'采集'))));
        if valid
            lines{end+1}=sprintf('%d · %s · MER %.3f dB · 纠错前 BER %.5g', ...
                k,role,get(obs(k),{'metrics','mer_db'},NaN),get(obs(k),{'metrics','pre_ber'},NaN)); %#ok<AGROW>
        else
            lines{end+1}=sprintf('%d · %s · 解调指标无效或未计算',k,role); %#ok<AGROW>
        end
    end
    errors=get(value,{'errors'},{});
    if isfield(value,'baseline_summary')
        b=value.baseline_summary;
        lines{end+1}=sprintf('固定设置基准：%d次；MER均值 %.3f dB，标准差 %.3f dB，极差 %.3f dB', ...
            b.count,b.mer_mean_db,b.mer_std_db,b.mer_range_db);
        lines{end+1}=sprintf('纠错前 BER：均值 %.5g，标准差 %.5g；全部逐次结果保留',b.ber_mean,b.ber_std);
    end
    for k=1:numel(errors)
        if iscell(errors), e=errors{k}; else, e=errors(k); end
        lines{end+1}=['说明：' char(string(get(e,{'message'},'')))]; %#ok<AGROW>
    end
    return;
end
try
    text=jsonencode(value,'PrettyPrint',true);
catch
    text=evalc('disp(value)');
end
% Do not flood the panel with raw waveform arrays; the full result is on disk.
if numel(text)>24000, text=[text(1:24000) newline '…完整内容见结果目录。']; end
lines=cellstr(splitlines(string(text)));
end

function v=onoff(ok)
if ok, v='on'; else, v='off'; end
end
function text=friendlyError(err)
if isa(err,'MException'), message=err.message; else, message=char(string(err)); end
if ~isempty(regexp(message,'[\x{4E00}-\x{9FFF}]','once')), text=message; return; end
pairs={...
    'start, end and step','请填写两级衰减的起点、终点和步进。'; ...
    '0.5 dB grid','衰减端点和步进须符合 0.5 dB 档位，步进方向须正确。'; ...
    'Endpoint','终点必须能由起点按所填步进到达。'; ...
    'Missing policy','本地运行策略尚未填全，请检查稳定等待、配平及退化容差。'; ...
    'Scope ranges','请配置示波器量程档位、余量及调整次数上限。'; ...
    'Fresh','新采集完成判据或握手尚未配置并验证。'; ...
    'Wiring','请先核对实际接线并点击确认。'; ...
    'physical mapping','板卡协议、物理通道映射和控制响应尚未全部确认。'; ...
    'mapping','所选接收通道与已确认的板卡物理映射不一致。'; ...
    'reference','发送参考缺失或不一致，请检查本地参考文件。'; ...
    'authorized','本次操作所需设备尚未在本地配置中授权。'; ...
    'synthetic','模拟参数不能用于真实设备，请重新加载实机配置。'; ...
    'six-band','请先确认完整六路板卡状态。'; ...
    'serial','串口配置不完整，请检查本地设备配置。'; ...
    'protocol','板卡协议尚未验证，暂不能自动控制。'; ...
    'Board transport','板卡运行方式与本次操作不一致。'; ...
    'Board scanning','二维扫描仅适用于接收端 I/Q 阶段。'; ...
    'Direct wiring','直连阶段不使用板卡控制。'; ...
    'matrix','缺少发送波形所需的授权编码矩阵，请检查本地配置。'; ...
    'capacity','波形超出当前模式容量，不能下载。'; ...
    'clipp','波形发生削顶，请检查批准量程和输入幅度。'; ...
    'cancel','任务已请求停止，等待收尾。'};
text='操作条件未满足，请展开记录详情查看具体原因。';
for k=1:size(pairs,1)
    if contains(message,pairs{k,1},'IgnoreCase',true), text=pairs{k,2}; return; end
end
end
