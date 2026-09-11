function accepted = apply_rx_scope_setting(session,request,query_fn,write_fn)
%APPLY_RX_SCOPE_SETTING Validate live capabilities, write one field, verify.
if nargin<3 || isempty(query_fn), query_fn=@msiq.instruments.query_scpi; end
if nargin<4 || isempty(write_fn), write_fn=@msiq.instruments.write_scpi; end
assert(isstruct(request)&&isfield(request,'key')&&isfield(request,'value'), ...
    'RX_Workbench:Setting','缺少参数名称或目标值');
key=char(string(request.key));
selector=struct('requested_keys',{{key}});
state=msiq.instruments.rx_scope_settings(session,query_fn,selector,true);
assert(numel(state.fields)==1,'RX_Workbench:Setting','不允许写入参数：%s',key);
f=state.fields;
assert(f.available&&f.writable,'RX_Workbench:Setting','参数 %s 不可写：%s',key,f.error);
value=request.value;
if strcmp(f.kind,'number')
    assert(isnumeric(value)&&isscalar(value)&&isfinite(value),'RX_Workbench:Setting','%s 必须为有限数值',key);
    if f.integer, value=round(value); end
    assert(value>=f.minimum&&value<=f.maximum,'RX_Workbench:Setting','%s 超出仪器范围 %.12g 至 %.12g',key,f.minimum,f.maximum);
    literal=sprintf('%.17g',value);
else
    value=upper(char(string(value)));
    assert(ismember(value,f.choices),'RX_Workbench:Setting','%s 不支持选项 %s',key,value);
    literal=['"' value '"'];
end
if isequal(value,f.value), accepted=f.value; return; end
if endsWith(key,':TRA')||endsWith(key,':CPL')||strcmp(key,'TRMD')
    command=[key ' ' char(value)];
elseif endsWith(key,':BWL')
    command=['BWL ' key(1:2) ',' char(value)];
else
    command=sprintf('VBS ''%s.Value=%s''',f.path,literal);
end
try
    write_fn(session,command);
catch ex
    error('RX_Workbench:Transport','写入 | %s | %s',command,ex.message);
end
after=msiq.instruments.rx_scope_settings(session,query_fn,selector,false);
assert(after.fields.available,'RX_Workbench:Setting','写入后回读 | %s | %s',command,after.fields.error);
accepted=after.fields.value;
if strcmp(f.kind,'enum')
    assert(strcmp(accepted,value),'RX_Workbench:Setting','写入后不一致 | %s | %s',command,char(string(accepted)));
else
    assert(isfinite(accepted)&&accepted>=f.minimum&&accepted<=f.maximum, ...
        'RX_Workbench:Setting','写入后数值无效 | %s',command);
end
end
