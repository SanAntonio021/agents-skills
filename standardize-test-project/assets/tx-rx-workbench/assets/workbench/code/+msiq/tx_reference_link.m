function result = tx_reference_link(action, project_root, options)
%TX_REFERENCE_LINK File-only, machine-local successful TX reference association.
% store_path overrides the association directory (tests must use isolation).
if nargin<3, options=struct(); end
source=char(string(value(options,'source','real')));
if ~ismember(source,{'real','simulation'}), error('msiq:reference:Source','Unknown reference source.'); end
project=char(java.io.File(project_root).getCanonicalPath());
key=msiq.sha256_bytes(lower(project));
base=value(options,'store_path','');
if isempty(base)
    if strcmp(source,'simulation'), base=fullfile(tempdir,'msiq_reference_links');
    else, base=fullfile(prefdir,'msiq_reference_links'); end
end
folder=fullfile(base,key,source);
device=char(string(value(options,'device','')));
result=struct('valid',false,'reason','','path','','hash','','record',struct());
switch lower(action)
    case {'read','read_metadata'}
        if isempty(device), files=dir(fullfile(folder,'*.mat'));
        else, files=dir(fullfile(folder,[msiq.sha256_bytes(device) '.mat'])); end
        if isempty(files), result.reason='没有本机成功发送关联，请选择发送参考。'; return; end
        if numel(files)~=1, result.reason='存在多个发送设备，请明确选择发送参考。'; return; end
        try
            loaded=load(fullfile(files(1).folder,files(1).name),'record'); record=loaded.record;
            if ~strcmp(record.status,'applied'), result.reason='发送状态待确认，请重新成功发送或手动选择参考。'; return; end
            if ~strcmp(record.project,project) || ~strcmp(record.source,source), error('msiq:reference:Identity','关联来源不符。'); end
            if strcmpi(action,'read') && (~isfile(record.path) || ~strcmp(record.hash,msiq.file_sha256(record.path))), error('msiq:reference:Hash','发送参考缺失或内容已经变化。'); end
            result.valid=true; result.path=record.path; result.hash=record.hash; result.record=record;
        catch exception, result.reason=exception.message; end
    case {'publish','invalidate'}
        if isempty(device), error('msiq:reference:Device','Association needs device identity.'); end
        record=struct('schema_version',1,'project',project,'source',source,'device',device, ...
            'status','unconfirmed','path','','hash','','execution_id',value(options,'execution_id',''), ...
            'updated_at',char(datetime('now','Format','yyyy-MM-dd HH:mm:ss.SSS')), ...
            'reason',value(options,'reason','发送状态待确认'));
        if strcmpi(action,'publish')
            record.path=char(java.io.File(options.reference_path).getCanonicalPath());
            loaded=msiq.load_reference_bundle(record.path);
            if ~strcmpi(value(value(loaded.bundle,'execution',struct()),'status',''),'applied')
                error('msiq:reference:NotApplied','Only successfully applied references can be published.');
            end
            record.hash=msiq.file_sha256(record.path); record.status='applied'; record.reason='';
        end
        if ~isfolder(folder), mkdir(folder); end
        msiq.atomic_save(fullfile(folder,[msiq.sha256_bytes(device) '.mat']),struct('record',record));
        result.record=record; result.valid=strcmp(record.status,'applied'); result.path=record.path; result.hash=record.hash;
    otherwise, error('msiq:reference:Action','Unknown association action.');
end
end
function out=value(s,n,f)
out=f; if isstruct(s)&&isfield(s,n)&&~isempty(s.(n)), out=s.(n); end
end
