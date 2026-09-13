function note=validate_rx_settings_gui(output_dir)
%VALIDATE_RX_SETTINGS_GUI Check real controls against a query/write mock.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
logpath=fullfile(output_dir,'settings_gui_io.log');
fid=fopen(logpath,'w'); assert(fid>=0,'Cannot initialize GUI test audit.'); fclose(fid);
mock=struct('capture_delay_s',0,'record_count',2001,'log_path',logpath, ...
    'failure_path',fullfile(output_dir,'settings_gui_failure.txt'),'no_new_frame',true, ...
    'timebase_s',2.5e-9,'observation_mode',true);
io=msiq.instruments.mock_rx_scope_io(mock);
opts=struct('visible',false,'maximize',false,'position',[30 30 1500 900], ...
    'synchronous_startup',true,'use_timer',false,'find_reference',false, ...
    'io',io,'config',msiq.rx_mock_config());
fig=msiq.rx_workbench_app(opts);
cleanup=onCleanup(@() close_gui(fig));
state=getappdata(fig,'rx_workbench_state');
assert(state.connected && state.running,'Extended settings prevented startup.');
assert(isempty(writes()),'Startup wrote hardware targets.');
tick(); state=getappdata(fig,'rx_workbench_state');
assert(isfield(state.raw,'channels') && all([state.raw.channels.wave_valid]));
tick(); state=getappdata(fig,'rx_workbench_state');
assert(~state.raw.new_data,'Repeated mock frame was marked as new acquisition.');
invoke(state.home.h_pause);

% Each physical switch writes precisely that channel and preserves route.
h=find_setting('TRA',1); choose(h,'OFF');
lines=writes(); assert(numel(lines)==1 && contains(lines{end},'C1:TRA OFF'));
state=getappdata(fig,'rx_workbench_state');
assert(isequal(state.channels,{'C1','C2'}));
choose(h,'ON');
before=numel(writes());
set(state.home.h_ch1,'Value',3); invoke(state.home.h_ch1);
assert(numel(writes())==before,'Changing selected channel enabled it.');
h=find_setting('TRA',1); choose(h,'OFF');
lines=writes(); assert(numel(lines)==before+1 && contains(lines{end},'C3:TRA OFF'));
choose(h,'ON');

% Both OFF clears both channel curves; old traces must not masquerade as live.
choose(find_setting('TRA',1),'OFF'); choose(find_setting('TRA',2),'OFF');
state=getappdata(fig,'rx_workbench_state'); invoke(state.home.h_play); tick();
state=getappdata(fig,'rx_workbench_state');
assert(all(arrayfun(@(r) isempty(r.samples),state.raw.channels)));
invoke(state.home.h_pause);
choose(find_setting('TRA',1),'ON'); choose(find_setting('TRA',2),'ON');

% Native enumerations, readback and numeric edits go through same queue.
state=getappdata(fig,'rx_workbench_state'); invoke(state.home.h_settings);
before=numel(writes());
h=find_setting('AVERAGE',1); set(h,'String','8'); invoke(h);
lines=writes(); assert(numel(lines)==before+1 && contains(lines{end},'C3.AverageSweeps.Value=8'));
assert(str2double(get(h,'String'))==8);
h=find_setting('BWL',1); choose(h,'200MHZ');
lines=writes(); assert(contains(lines{end},'BWL C3,200MHZ'));
assert(~any(contains(lines,{'STOP','TRMD AUTO','*RST'})),'Hidden disruptive control.');
before=numel(lines);
set(state.home.h_psd_min,'String','-125'); invoke(state.home.h_psd_min);
assert(numel(writes())==before,'Display setting wrote instrument.');

% A failed write retains the typed value; inline retry reconnects and applies it.
h=find_setting('AVERAGE',1);
fid=fopen(mock.failure_path,'w'); assert(fid>=0);
fprintf(fid,'%s','VBS ''app.Acquisition.C3.AverageSweeps.Value'); fclose(fid);
set(h,'String','9'); invoke(h);
state=getappdata(fig,'rx_workbench_state'); data=get(h,'UserData');
assert(~state.connected && strcmp(get(h,'String'),'9'));
assert(isgraphics(data.retry) && strcmp(get(data.retry,'Visible'),'on'));
fid=fopen(mock.failure_path,'w'); assert(fid>=0); fclose(fid);
invoke(data.retry);
state=getappdata(fig,'rx_workbench_state');
assert(state.connected && str2double(get(h,'String'))==9,'Inline retry did not reconnect and apply.');
choose(find_setting('BWL',1),'OFF');
invoke(state.home.h_auto_psd);

for dim={[1500 900],[1100 700]}
    d=dim{1}; set(fig,'Position',[30 30 d]); drawnow;
    state=getappdata(fig,'rx_workbench_state');
    set(state.home.scroll,'Value',get(state.home.scroll,'Max')); invoke(state.home.scroll);
    verify_rows();
    snapshot(sprintf('settings_expanded_%dx%d_top.png',d));
    set(state.home.scroll,'Value',get(state.home.scroll,'Min')); invoke(state.home.scroll);
    snapshot(sprintf('settings_expanded_%dx%d_bottom.png',d));
    invoke(state.home.h_settings); invoke(state.home.h_play); tick(); invoke(state.home.h_pause);
    snapshot(sprintf('settings_home_%dx%d.png',d));
    invoke(state.home.h_settings);
end
note='Extended GUI: query-only startup, single-field writes, channel switches, freshness, settings scrolling and screenshots passed.';
disp(note);

    function tick()
        callback=getappdata(fig,'rx_workbench_tick'); callback([],[]);
        s=getappdata(fig,'rx_workbench_state');
        if isfield(s,'last_exception'), rethrow(s.last_exception); end
    end
    function out=writes()
        if ~isfile(logpath), out={}; return; end
        all_lines=regexp(fileread(logpath),'\r?\n','split');
        out=all_lines(contains(all_lines,'WRITE '));
    end
    function h=find_setting(key,index)
        if nargin<2, index=0; end
        s=getappdata(fig,'rx_workbench_state'); h=[];
        for item=s.home.extended_edits
            data=get(item,'UserData');
            match=strcmp(data.key,key) || endsWith(data.key,[':' key]);
            if match && (~isfield(data,'index') || data.index==index)
                h=item; break;
            end
        end
        assert(~isempty(h),'Missing GUI setting %s index %d',key,index);
    end
    function choose(h,token)
        data=get(h,'UserData');
        assert(isfield(data,'choices'),'Enum control must retain remote tokens.');
        n=find(strcmp(data.choices,token),1);
        assert(~isempty(n),'Missing device option %s',token);
        set(h,'Value',n); invoke(h);
    end
    function verify_rows()
        s=getappdata(fig,'rx_workbench_state');
        for item=s.home.extended_edits
            data=get(item,'UserData');
            if ~isfield(data,'current'), continue; end
            a=getpixelposition(item,true); b=getpixelposition(data.current,true);
            assert(b(1)+b(3)<=a(1)+1,'Current readback overlaps target input.');
            assert(abs(a(2)-b(2))<8,'Current and target rows are misaligned.');
        end
    end
    function snapshot(name)
        set(fig,'Visible','on'); drawnow;
        f=getframe(fig); assert(std(double(f.cdata(:)))>10);
        imwrite(f.cdata,fullfile(output_dir,name));
    end
end
function invoke(h)
callback=get(h,'Callback'); callback(h,[]); drawnow;
end
function close_gui(fig)
if isgraphics(fig), close(fig); end
end
