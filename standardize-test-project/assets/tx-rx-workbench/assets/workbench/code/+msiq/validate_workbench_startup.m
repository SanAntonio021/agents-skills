function note = validate_workbench_startup()
%VALIDATE_WORKBENCH_STARTUP Real default settings with hardware constructors denied.
folder = msiq.validation_artifacts('directory');
guard_path = fullfile(folder,'constructor_guard'); mkdir(guard_path);
marker = fullfile(folder,'hardware_attempt.txt');
names = {'serialport','visa','visadev','tcpclient','udpport','gpib'};
for k=1:numel(names)
    fid=Result_Open_File_Retry(fullfile(guard_path,[names{k} '.m']),'w');
    fprintf(fid,['function varargout=%s(varargin)\n' ...
        'fid=fopen(''%s'',''a''); fprintf(fid,''%s\\n''); fclose(fid);\n' ...
        'error(''msiq:validation:HardwareDenied'',''Real instrument construction forbidden.'');\nend\n'], ...
        names{k},strrep(marker,'''',''''''),names{k});
    fclose(fid);
end
figures=findall(groot,'Type','figure');
addpath(guard_path,'-begin');
cleanup=onCleanup(@restore);
tx=TX_Workbench('gui',[],struct('visible',false,'startup_preview',false, ...
    'synchronous_startup',true,'persist_parameters',false, ...
    'parameter_record_path',fullfile(folder,'tx_preferences.mat'), ...
    'board_options',struct('persist',false)));
rx=RX_Workbench('gui',struct('visible',false,'maximize',false, ...
    'synchronous_startup',true,'use_timer',false,'find_reference',false,'preferences_path',''));
live_rx=RX_Workbench('gui',struct('source_mode','measurement','visible',false,'maximize',false, ...
    'synchronous_startup',true,'use_timer',false,'find_reference',false,'preferences_path',''));
drawnow;
t=getappdata(tx,'tx_workbench_state'); r=getappdata(rx,'rx_workbench_state');
assert(~t.connected && ~r.connected && ~r.running);
live_state=getappdata(live_rx,'rx_workbench_state');
assert(strcmp(r.source_mode,'simulation') && strcmp(live_state.source_mode,'measurement'));
assert(~live_state.connected && ~live_state.running);
assert(~isfile(marker),'Startup attempted real instrument I/O, even if the UI caught its error.');
close(tx); close(rx); close(live_rx); drawnow;
assert(~isfile(marker),'Closing an unconnected workbench attempted instrument I/O.');
note='TX及RX模拟/实测启动、未连接关闭：真实仪器构造器拒绝保护下零访问。';
clear cleanup;
    function restore()
        remaining=setdiff(findall(groot,'Type','figure'),figures);
        for f=reshape(remaining,1,[]), if isgraphics(f), close(f); end; end
        rmpath(guard_path);
    end
end
