function result=if_board_ports(source,selected,list_fn,mock_name)
%IF_BOARD_PORTS Enumerate names only. Never construct or connect a serial port.
if nargin<2, selected=''; end
if nargin<3 || isempty(list_fn), list_fn=@()serialportlist('available'); end
if nargin<4, mock_name='MOCK_IF'; end
if strcmp(source,'simulation'), source='mock'; end
if strcmp(source,'measurement'), source='live'; end
if strcmp(source,'mock')
    result=struct('labels',{{'模拟串口'}},'values',{{mock_name}},'index',1, ...
        'available',true,'message',''); return;
end
assert(strcmp(source,'live'),'msiq:ifboard:source','来源必须是 live 或 mock。');
selected=char(string(selected)); message='';
try
    names=cellstr(string(list_fn())); names=names(:).';
    names=unique(names(~cellfun(@isempty,names)),'stable');
catch err
    names={}; message=['串口列表读取失败：' err.message];
end
values=[{''} names]; labels=[{'请选择串口'} names]; index=1; available=false;
if ~isempty(selected)
    found=find(strcmpi(names,selected),1);
    if isempty(found)
        values{end+1}=selected; labels{end+1}=[selected '（不可用）']; index=numel(values);
        if isempty(message), message='原串口不可用，请检查连接后刷新；不会自动换口。'; end
    else
        index=found+1; available=true;
    end
elseif isempty(message)
    if isempty(names), message='未发现可用串口，请检查 USB 连接后刷新。';
    else, message='请选择本次板卡的串口。'; end
end
result=struct('labels',{labels},'values',{values},'index',index,'available',available,'message',message);
end
