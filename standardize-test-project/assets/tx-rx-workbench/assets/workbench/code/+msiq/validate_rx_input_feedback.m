function note=validate_rx_input_feedback(output_dir)
% Exercise real numeric widgets with an audited mock instrument transport.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
logpath=fullfile(output_dir,'input_io.log');
fid=Result_Open_File_Retry(logpath,'w'); fclose(fid);
io=msiq.instruments.mock_rx_scope_io(struct('capture_delay_s',0,'record_count',2001,'log_path',logpath, ...
    'failure_path',fullfile(output_dir,'no_failure.txt')));
fig=msiq.rx_workbench_app(struct('visible',false,'maximize',false,'synchronous_startup',true, ...
    'use_timer',false,'find_reference',false,'io',io,'config',msiq.rx_mock_config()));
cleanup=onCleanup(@() close(fig)); %#ok<NASGU>
s=getappdata(fig,'rx_workbench_state'); h=s.home.h_vdiv1;
d=get(h,'UserData'); assert(strcmp(get(d.current,'Visible'),'off'));
original=get(h,'String'); before=writes();
key('leftarrow'); tick(); assert(strcmp(get(h,'String'),original),'Navigation changed input text.');
key('delete'); set(h,'String','0.07');
callback=get(h,'Callback'); callback(h,[]); % Native edit callback also fires on blur.
tick(); assert(strcmp(get(h,'String'),'0.07') && writes()==before,'Blur submitted or refresh overwrote draft.');
[blocked,~]=msiq.rx_input_state('blocked',h); assert(blocked);
assert(contains(get(h,'TooltipString'),'尚未提交'));
original_channels=s.channels;
set(s.home.h_ch1,'Value',3); callback=get(s.home.h_ch1,'Callback'); callback(s.home.h_ch1,[]);
current=getappdata(fig,'rx_workbench_state');
assert(isequal(current.channels,original_channels)&&writes()==before,'Draft must block channel rerouting.');
key('return'); assert(writes()==before+1,'Return must write once.');
key('return'); assert(writes()==before+1,'Duplicate return wrote twice.');
assert(~msiq.rx_input_state('blocked',h));
color=get(h,'BackgroundColor'); assert(color(2)>color(1),'Verified input is not green.');
key('backspace'); set(h,'String','0.0'); tick(); assert(strcmp(get(h,'String'),'0.0'));
key('escape'); d=get(h,'UserData'); assert(str2double(get(h,'String'))*d.multiplier==d.actual);
% Late readback retains newer text and its version.
msiq.rx_input_state('pending',h,100);
key('delete'); set(h,'String','0.09');
msiq.rx_input_state('accept',h,struct('revision',100,'value',.07),.07);
assert(strcmp(get(h,'String'),'0.09') && msiq.rx_input_state('blocked',h));
key('escape');
msiq.rx_input_state('pending',h,101);
msiq.rx_input_state('accept',h,struct('revision',101,'value',.09),.08);
assert(msiq.rx_input_state('blocked',h),'Mismatching readback must stay unresolved.');
assert(contains(get(h,'TooltipString'),'实际回读：0.08'));
msiq.rx_input_state('failed',h); assert(msiq.rx_input_state('blocked',h));
key('escape');
assert(isequal(get(h,'BackgroundColor'),[.94 .94 .94]),'Esc must not promote an unknown readback to green.');
% Operate the actual Swing text document/caret without global keyboard injection.
set(fig,'Visible','on'); figure(fig); drawnow;
% The growing scrollable sidebar may initially clip this numeric widget. A
% clipped Swing edit has no useful visual caret navigation geometry.
region=get(s.home.param_panel,'Position'); slider=s.home.scroll;
offset=s.home.content_height-sum(region([2 4]));
set(slider,'Value',max(get(slider,'Min'),get(slider,'Max')-offset));
scroll=get(slider,'Callback'); scroll(slider,[]); drawnow;
rect=getpixelposition(h,true); viewport=getpixelposition(s.home.settings_panel,true);
assert(rect(2)>=viewport(2) && rect(2)+rect(4)<=viewport(2)+viewport(4), ...
    'Native edit test target is outside the visible viewport.');
uicontrol(h); drawnow; pause(.2); drawnow;
manager=java.awt.KeyboardFocusManager.getCurrentKeyboardFocusManager(); owner=javaMethodEDT('getFocusOwner',manager);
assert(~isempty(owner)&&ismethod(owner,'getCaretPosition'),'Numeric edit did not receive native focus.');
assert(logical(javaMethodEDT('isShowing',owner)) && strcmp(char(javaMethodEDT('getText',owner)),get(h,'String')), ...
    'Native focus is not on the visible numeric edit under test.');
javaMethodEDT('selectAll',owner); javaMethodEDT('replaceSelection',owner,'0.0700');
javaMethodEDT('setCaretPosition',owner,4);
perform('caret-backward'); assert(owner.getCaretPosition()==3,'Left arrow moved to beginning.');
tick(); assert(owner.getCaretPosition()==3,'Refresh moved native caret.');
perform('delete-next'); assert(owner.getCaretPosition()==3,'Delete moved native caret.');
text_before=char(owner.getText()); tick();
assert(owner.getCaretPosition()==3&&strcmp(char(owner.getText()),text_before),'Refresh disturbed native delete.');
javaMethodEDT('replaceSelection',owner,'8'); position=owner.getCaretPosition(); tick();
assert(owner.getCaretPosition()==position&&contains(char(owner.getText()),'8'),'Refresh disturbed native replacement.');
perform('end'); assert(owner.getCaretPosition()==numel(char(owner.getText())));
perform('home'); assert(owner.getCaretPosition()==0);
perform('right'); assert(owner.getCaretPosition()==1);
javaMethodEDT('select',owner,2,4); tick();
assert(owner.getSelectionStart()==2&&owner.getSelectionEnd()==4,'Refresh disturbed native selection.');
% Use Swing's paste/import implementation without touching the system clipboard.
transfer=java.awt.datatransfer.StringSelection('89'); handler=owner.getTransferHandler();
types=javaArray('java.lang.Class',2);
types(1)=java.lang.Class.forName('javax.swing.JComponent');
types(2)=java.lang.Class.forName('java.awt.datatransfer.Transferable');
method=java.lang.Class.forName('javax.swing.TransferHandler').getMethod('importData',types);
invoke_args=javaArray('java.lang.Object',2); invoke_args(1)=owner; invoke_args(2)=transfer;
accepted=javaMethodEDT('invoke',method,handler,invoke_args);
assert(logical(accepted),'Native text paste was rejected');
position=owner.getCaretPosition(); text_before=char(owner.getText()); tick();
assert(owner.getCaretPosition()==position&&strcmp(char(owner.getText()),text_before),'Refresh disturbed paste.');
before=writes(); perform('enter'); assert(writes()==before+1,'Native Enter did not write exactly once.');
note='RX numeric controls: native Swing caret/delete/replacement, blur draft, Enter once, Esc, refresh protection, late readback and mismatch passed; mock I/O only.';
    function perform(name)
        if strcmp(name,'caret-backward'), code=java.awt.event.KeyEvent.VK_LEFT;
        elseif strcmp(name,'enter'), code=java.awt.event.KeyEvent.VK_ENTER;
        elseif strcmp(name,'right'), code=java.awt.event.KeyEvent.VK_RIGHT;
        elseif strcmp(name,'home'), code=java.awt.event.KeyEvent.VK_HOME;
        elseif strcmp(name,'end'), code=java.awt.event.KeyEvent.VK_END;
        else, code=java.awt.event.KeyEvent.VK_DELETE; end
        event=java.awt.event.KeyEvent(owner,java.awt.event.KeyEvent.KEY_PRESSED, ...
            java.lang.System.currentTimeMillis(),0,code,java.awt.event.KeyEvent.CHAR_UNDEFINED);
        javaMethodEDT('dispatchEvent',owner,event); drawnow;
    end
    function key(name)
        callback=get(h,'KeyPressFcn'); callback(h,struct('Key',name)); drawnow;
    end
    function tick()
        callback=getappdata(fig,'rx_workbench_tick'); callback([],[]);
    end
    function count=writes()
        count=sum(contains(regexp(fileread(logpath),'\r?\n','split'),'WRITE '));
    end
end
