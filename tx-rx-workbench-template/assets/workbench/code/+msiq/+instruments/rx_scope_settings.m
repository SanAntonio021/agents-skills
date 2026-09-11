function settings = rx_scope_settings(session,query_fn,cached,refresh_capabilities)
%RX_SCOPE_SETTINGS Read instrument-backed settings and legal capabilities.
if nargin<2 || isempty(query_fn), query_fn=@msiq.instruments.query_scpi; end
if nargin<3, cached=struct(); end
if nargin<4, refresh_capabilities=false; end
template=struct('key','','kind','enum','value','','choices',{{}}, ...
    'choice_labels',{{}},'minimum',NaN,'maximum',NaN,'step',NaN, ...
    'available',false,'writable',false,'error','','path','','query','','integer',false);
fields=repmat(template,0,1);
names={'TRA','CPL','BWL','AVERAGE','INTERPOLATION','ERES','RESPONSE'};
props={'View','Coupling','BandwidthLimit','AverageSweeps','InterpolateType','EnhanceResType','OptimizeGroupDelay'};
for ch=1:4
    for n=1:numel(names)
        f=template; f.key=sprintf('C%d:%s',ch,names{n});
        f.path=sprintf('app.Acquisition.C%d.%s',ch,props{n});
        if n<=2, f.query=[f.key '?']; end
        if n==4, f.kind='number'; f.integer=true; end
        fields(end+1)=f; %#ok<AGROW>
    end
end
keys={'TRMD','TRSOURCE','TRSLOPE','TRLEVEL','HTYPE','HTIME','MSIZ','SAMPLEMODE'};
paths={'TriggerMode','Trigger.Edge.Source','Trigger.Edge.Slope','Trigger.Edge.Level', ...
    'Trigger.Edge.HoldoffType','Trigger.Edge.HoldoffTime','Horizontal.MaxSamples','Horizontal.SampleMode'};
for n=1:numel(keys)
    f=template; f.key=keys{n}; f.path=['app.Acquisition.' paths{n}];
    if ismember(n,[4 6 7]), f.kind='number'; end
    if n==7, f.integer=true; end
    if n==1, f.query='TRMD?'; end
    fields(end+1)=f; %#ok<AGROW>
end
if isfield(cached,'requested_keys'), fields=fields(ismember({fields.key},cached.requested_keys)); end
settings=struct('fields',fields,'sample_mode','UNKNOWN','trigger_source','UNKNOWN');
if any(ismember({fields.key},{'TRLEVEL','TRSOURCE'}))
    try
        settings.trigger_source=canonical(ask('VBS? ''return=app.Acquisition.Trigger.Edge.Source'''),'TRSOURCE');
    catch exception
        if strcmp(exception.identifier,'RX_Workbench:Transport'), rethrow(exception); end
    end
end
for k=1:numel(fields)
    f=fields(k);
    previous=[];
    if isfield(cached,'fields'), previous=find(strcmp({cached.fields.key},f.key),1); end
    if ~refresh_capabilities && ~isempty(previous) && ~cached.fields(previous).available
        settings.fields(k)=cached.fields(previous);
        continue;
    end
    try
        cmd=f.query;
        if isempty(cmd), cmd=sprintf('VBS? ''return=%s''',f.path); end
        raw=ask(cmd);
        if strcmp(f.kind,'number')
            f.value=parse_number(raw);
        else
            f.value=canonical(raw,f.key);
        end
        if ~refresh_capabilities && ~isempty(previous) && cached.fields(previous).available && ~strcmp(f.key,'TRLEVEL')
            old=cached.fields(previous);
            f.choices=old.choices; f.choice_labels=old.choice_labels;
            f.minimum=old.minimum; f.maximum=old.maximum; f.step=old.step;
        elseif strcmp(f.kind,'enum')
            if endsWith(f.key,':TRA'), f.choices={'ON','OFF'};
            else
                remote=ask(sprintf('VBS? ''return=%s.GetRangeStringRemote''',f.path));
                tokens=regexp(clean(remote),'[,;]','split');
                f.choices=cellfun(@(v) canonical(v,f.key),tokens,'UniformOutput',false);
                f.choices=intersect(f.choices,allowed(f.key),'stable');
            end
            f.choice_labels=cellfun(@label,f.choices,'UniformOutput',false);
            if endsWith(f.key,':BWL')
                f.choice_labels(strcmp(f.choices,'OFF'))={'全带宽'};
                f.choice_labels(strcmp(f.choices,'ON'))={'20 MHz'};
            end
        else
            methods={'GetMinValue','GetMaxValue','GetGrainValue'};
            if endsWith(f.key,':AVERAGE'), methods={'GetMin','GetMax','GetGrain'}; end
            vals=zeros(1,3);
            for j=1:3, vals(j)=parse_number(ask(sprintf('VBS? ''return=%s.%s''',f.path,methods{j}))); end
            f.minimum=vals(1); f.maximum=vals(2); f.step=vals(3);
            assert(f.maximum>=f.minimum,'RX_Workbench:Unsupported','无效参数范围');
        end
        f.available=true;
        f.writable=strcmp(f.kind,'number') || ~isempty(f.choices);
        if ismember(f.key,{'TRSLOPE','TRLEVEL','HTYPE','HTIME','TRSOURCE'})
            trigger_type=canonical(ask('VBS? ''return=app.Acquisition.Trigger.Type'''),'TYPE');
            if ~strcmp(trigger_type,'EDGE'), f.writable=false; f.error='当前不是边沿触发'; end
        end
        if strcmp(f.key,'SAMPLEMODE'), settings.sample_mode=f.value; end
    catch exception
        if strcmp(exception.identifier,'RX_Workbench:Transport'), rethrow(exception); end
        f.available=false; f.writable=false; f.error=exception.message;
    end
    settings.fields(k)=f;
end

    function raw=ask(command)
        try
            raw=char(string(query_fn(session,command)));
        catch ex
            error('RX_Workbench:Transport','回读 | %s | %s',command,ex.message);
        end
        if isempty(strtrim(raw)) || ~isempty(regexpi(raw,'QUERY_FAILED|error|unsupported|unknown|invalid|does.?n.t support|does not support','once'))
            error('RX_Workbench:Unsupported','回读 | %s | %s',command,raw);
        end
    end
end

function value=clean(value)
value=strtrim(regexprep(char(value),'^VBS\s+','','ignorecase'));
value=strrep(strrep(value,'"',''),'''','');
end
function value=parse_number(raw)
token=regexp(clean(raw),'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*(?:[a-zA-Z/]+)?\s*$','tokens','once');
assert(~isempty(token),'RX_Workbench:Unsupported','无效数值：%s',raw);
value=str2double(token{1});
assert(isfinite(value),'RX_Workbench:Unsupported','无效数值：%s',raw);
end
function value=canonical(value,key)
value=upper(strtrim(clean(value)));
value=regexprep(value,'^(?:C[1-4]:)?(?:TRA|CPL|TRMD)\s+','');
switch value
    case {'DC50','DC50OHM'}, value='D50';
    case 'GROUND', value='GND';
    case 'NORMAL', value='NORM';
    case 'POSITIVE', value='POS';
    case 'NEGATIVE', value='NEG';
    case 'TIME', value='TI';
    case 'EXTERNAL', value='EXT';
end
if endsWith(key,':TRA')
    if ismember(value,{'TRUE','1','-1'}), value='ON'; end
    if ismember(value,{'FALSE','0'}), value='OFF'; end
end
if endsWith(key,':BWL')
    if strcmp(value,'FULL'), value='OFF'; end
    if strcmp(value,'20MHZ'), value='ON'; end
end
end
function values=allowed(key)
if endsWith(key,':TRA'), values={'ON','OFF'};
elseif endsWith(key,':CPL'), values={'D50','GND','A50','D1M','A1M'};
elseif endsWith(key,':BWL'), values={'OFF','16GHZ','13GHZ','8GHZ','6GHZ','4GHZ','3GHZ','1GHZ','200MHZ','ON'};
elseif endsWith(key,':INTERPOLATION'), values={'LINEAR','SINXX'};
elseif endsWith(key,':ERES'), values={'NONE','0.5BITS','1BITS','1.5BITS','2BITS','2.5BITS','3BITS'};
elseif endsWith(key,':RESPONSE'), values={'PULSERESPONSE','EYEDIAGRAM','FLATNESS'};
else
    switch key
        case 'TRMD', values={'AUTO','NORM'};
        case 'TRSOURCE', values={'C1','C2','C3','C4','EXT','LINE','FE'};
        case 'TRSLOPE', values={'POS','NEG','EITHER'};
        case 'HTYPE', values={'OFF','TI'};
        case 'SAMPLEMODE', values={'REALTIME'};
        otherwise, values={};
    end
end
end
function text=label(token)
switch token
    case 'ON', text='开启'; case 'OFF', text='关闭';
    case 'D50', text='直流 50 Ω'; case 'GND', text='接地';
    case 'A50', text='交流 50 Ω'; case 'D1M', text='直流 1 MΩ'; case 'A1M', text='交流 1 MΩ';
    case 'AUTO', text='自动'; case 'NORM', text='正常';
    case 'POS', text='上升沿'; case 'NEG', text='下降沿'; case 'EITHER', text='任一边沿';
    case 'TI', text='按时间'; case 'LINEAR', text='线性'; case 'SINXX', text='正弦插值';
    case 'NONE', text='无'; case 'PULSERESPONSE', text='脉冲响应';
    case 'EYEDIAGRAM', text='眼图'; case 'FLATNESS', text='平坦度';
    case 'REALTIME', text='实时'; case 'EXT', text='外部'; case 'LINE', text='电源线';
    otherwise
        text=strrep(strrep(strrep(token,'GHZ',' GHz'),'MHZ',' MHz'),'BITS',' 位');
end
end
