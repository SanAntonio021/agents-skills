function varargout=rx_input_state(action,h,varargin)
% Keep drafts separate from instrument readback; never rewrite active text.
if strcmp(action,'blocked')
    blocked=false; reason='';
    for item=h
        s=state(item);
        if s.dirty || s.pending || s.mismatch
            blocked=true; reason='示波器设置尚未提交或回读未确认，请回车下发或按 Esc 恢复'; break;
        end
    end
    varargout={blocked,reason}; return;
end
s=state(h);
switch action
    case 'bind'
        s.submit=varargin{1};
        set(h,'Callback',@(src,~) msiq.rx_input_state('draft',src), ...
            'KeyPressFcn',@(src,e) msiq.rx_input_state('key',src,e), ...
            'KeyReleaseFcn',@(src,e) msiq.rx_input_state('released',src,e));
    case 'key'
        e=varargin{1};
        if ismember(e.Key,{'return','enter'})
            % MATLAB's String can lag the Swing document until focus loss.
            if usejava('awt') && isequal(get(ancestor(h,'figure'),'CurrentObject'),h)
                owner=java.awt.KeyboardFocusManager.getCurrentKeyboardFocusManager().getFocusOwner();
                if ~isempty(owner) && ismethod(owner,'getText')
                    set(h,'String',char(owner.getText()));
                end
            end
            setappdata(h,'rx_input_state',s); s.submit(); return;
        elseif strcmp(e.Key,'escape')
            d=get(h,'UserData');
            if isnumeric(d.actual)&&isscalar(d.actual)&&isfinite(d.actual)
                text=sprintf('%.12g',d.actual/d.multiplier);
                set(h,'String',text); d.displayed=text; set(h,'UserData',d);
                s.dirty=false; s.mismatch=false; s.version=s.version+1;
            end
        elseif ~ismember(e.Key,{'leftarrow','rightarrow','uparrow','downarrow','home','end','shift','control','alt','tab'})
            s.dirty=true; s.version=s.version+1;
        end
    case {'released','draft'}
        d=get(h,'UserData');
        if ~strcmp(get(h,'String'),d.displayed) && ~s.pending, s.dirty=true; end
    case 'pending'
        s.pending=true; s.request=varargin{1}; s.request_version=s.version;
        s.dirty=false; s.mismatch=false;
    case 'accept'
        request=varargin{1}; value=varargin{2};
        s.known=true;
        if s.request==request.revision
            s.pending=false;
            if s.version==s.request_version && ~s.dirty
                s.mismatch=~equal_value(request.value,value);
                d=get(h,'UserData'); d.actual=value; set(h,'UserData',d);
                if ~s.mismatch
                    % Retain user's spelling and caret; only move the baseline.
                    if strcmp(get(h,'Style'),'edit'), d.displayed=get(h,'String');
                    else, d.displayed=char(string(value)); end
                    set(h,'UserData',d);
                end
            end
        end
    case 'known'
        s.known=logical(varargin{1});
    case 'observed'
        s.known=true;
        if ~s.dirty && ~s.pending && strcmp(get(h,'Style'),'edit')
            d=get(h,'UserData'); requested=str2double(get(h,'String'))*d.multiplier;
            s.mismatch=~equal_value(requested,d.actual);
        end
    case 'protected'
        varargout={s.dirty||s.pending||s.mismatch}; return;
    case 'editing'
        fig=ancestor(h,'figure'); focused=false;
        if ~isempty(fig), focused=isequal(get(fig,'CurrentObject'),h); end
        varargout={s.dirty||s.pending||s.mismatch||focused}; return;
    case 'failed'
        s.pending=false; s.known=false; s.dirty=true;
    otherwise
        error('RX_Workbench:InputState','Unknown input action.');
end
setappdata(h,'rx_input_state',s);
if s.dirty || s.pending || s.mismatch
    color=[1 .88 .86];
elseif s.known, color=[.87 .97 .88];
else, color=[.94 .94 .94]; end
set(h,'BackgroundColor',color);
if s.pending
    set(h,'TooltipString','已提交，等待仪器回读确认');
elseif s.mismatch
    d=get(h,'UserData'); actual=d.actual;
    if isnumeric(actual), actual=sprintf('%.12g',actual/d.multiplier); else, actual=char(string(actual)); end
    unit=''; if isfield(d,'unit') && isgraphics(d.unit), unit=char(string(get(d.unit,'String'))); end
    set(h,'TooltipString',['输入与回读不一致；实际回读：' actual ' ' unit]);
elseif s.dirty && ~strcmp(action,'failed')
    set(h,'TooltipString','尚未提交；按 Enter 下发，按 Esc 恢复最近可信回读');
elseif ~s.dirty && s.known
    set(h,'TooltipString','已回读确认，与输入值一致');
elseif ~s.dirty && ~s.known && startsWith(get(h,'TooltipString'), ...
        {'已回读确认','已提交','尚未提交','输入与回读不一致'})
    set(h,'TooltipString','未连接或回读未知，尚未确认');
end
end
function s=state(h)
s=getappdata(h,'rx_input_state');
if isempty(s), s=struct('dirty',false,'pending',false,'mismatch',false,'known',false, ...
        'version',0,'request',-1,'request_version',0,'submit',[]); end
end
function yes=equal_value(a,b)
if isnumeric(a)&&isnumeric(b), yes=isscalar(a)&&isscalar(b)&&isfinite(a)&&isfinite(b)&&abs(a-b)<=32*eps(max([abs(a) abs(b) realmin]));
else, yes=isequaln(a,b); end
end
