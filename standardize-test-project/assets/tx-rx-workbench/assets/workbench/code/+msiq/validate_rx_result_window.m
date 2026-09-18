function note=validate_rx_result_window()
% Read-only saved-image viewer with actual controls, no instrument sessions.
folder=msiq.validation_artifacts('directory');
msiq.instruments.io_audit('reset','');
first=fullfile(folder,'first.png'); second=fullfile(folder,'second.png');
imwrite(uint8(ones(30,60,3)*80),first); imwrite(uint8(ones(30,60,3)*180),second);
m=struct('valid',true,'pre_ber',.001,'pre_error_count',1,'pre_bit_count',1000,'mer_db',24);
r=struct('role','正式','capture',struct('run_dir',folder,'dashboard_path',first), ...
    'observation',struct('metrics',m));
x=struct('task_id','a','source_mode','simulation','phase','capture','role','formal', ...
    'completed',1,'count',3,'elapsed_s',2,'active',true,'reason','','rows',{{r}});
f=msiq.rx_result_window('open',[],x,'off'); cleanup=onCleanup(@()close_safe(f));
s=getappdata(f,'rx_result_window_state'); assert(strcmp(s.image_path,first));
assert(strcmp(get(f,'Visible'),'off')); assert(contains(get(s.status,'String'),'1 / 3'));
set(s.list,'Value',1); callback=get(s.list,'Callback'); callback(s.list,[]);
r2=r; r2.capture.dashboard_path=second; x.rows={r,r2}; x.completed=2;
msiq.rx_result_window('update',f,x); s=getappdata(f,'rx_result_window_state');
assert(s.selected==1 && strcmp(s.image_path,first),'Manual selection lost on update');
callback=get(s.follow_button,'Callback'); callback(s.follow_button,[]);
s=getappdata(f,'rx_result_window_state'); assert(s.selected==2&&strcmp(s.image_path,second));
trial=r2; trial.role='trial'; x.rows={r,r2,trial};
msiq.rx_result_window('update',f,x); s=getappdata(f,'rx_result_window_state');
assert(s.selected==2,'Follow should prefer the latest formal record');
failed=trial; failed.role='failed'; x.rows{end+1}=failed;
x.active=false; x.reason='解调失败';
msiq.rx_result_window('update',f,x); s=getappdata(f,'rx_result_window_state');
assert(isempty(s.image_path),'Failure displayed prior successful result');
x.task_id='b'; x.source_mode='measurement'; x.rows={}; x.active=true; x.reason='';
msiq.rx_result_window('update',f,x); s=getappdata(f,'rx_result_window_state');
assert(s.selected==0 && isempty(s.image_path));
msiq.rx_result_window('close',f); assert(isempty(msiq.rx_result_window('update',f,x)));
a=msiq.instruments.get_audit(); assert(a.connections==0&&a.queries==0&&a.writes==0&&a.captures==0);
note='保存图件显示、手动选择保持、最新跟随、失败清空、来源隔离及关闭不重开通过；零仪器I/O。';
end
function close_safe(f)
if isgraphics(f), delete(f); end
end
