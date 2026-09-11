function value = shared_tx_data(action, varargin)
%SHARED_TX_DATA Content-verified waveform storage confined to one run tree.
switch action
    case 'save'
        root = canonical(varargin{1}); owner = canonical(varargin{2}); data = varargin{3};
        if ~inside(owner,root), error('msiq:sharedTx:Scope','TX owner is outside its run.'); end
        key = msiq.sha256_bytes(getByteStreamFromArray(data));
        path = fullfile(root,['shared_tx_',lower(key),'.mat']);
        if isfile(path)
            old = load(path);
            if ~isequaln(old,data), error('msiq:sharedTx:Conflict','Shared TX content differs: %s',path); end
        else
            msiq.atomic_save(path,data);
        end
        value = make_reference(owner,root,path,msiq.file_sha256(path));
    case 'load'
        [path,~] = resolve(varargin{1},varargin{2});
        value = load(path);
    case 'relocate'
        [path,root] = resolve(varargin{1},varargin{2});
        owner = canonical(varargin{3});
        if ~inside(owner,root)
            error('msiq:sharedTx:Scope','Shared reference destination must remain inside its run.');
        end
        value = make_reference(owner,root,path,varargin{2}.sha256);
    otherwise
        error('msiq:sharedTx:Action','Unknown shared TX action.');
end
end

function [path,root] = resolve(owner,reference)
owner = canonical(owner);
if ~all(isfield(reference,{'scope','file','sha256'})) ...
        || ~isempty(regexp(reference.scope,'^[A-Za-z]:|^[/\\]','once'))
    error('msiq:sharedTx:Reference','Invalid relative shared TX reference.');
end
root = canonical(fullfile(owner,reference.scope));
if ~inside(owner,root) || ~strcmp(reference.file,char(java.io.File(reference.file).getName())) ...
        || isempty(regexp(reference.file,'^shared_tx_[0-9a-f]+\.mat$','once'))
    error('msiq:sharedTx:Scope','Invalid shared TX scope or filename.');
end
path = canonical(fullfile(root,reference.file));
if ~strcmpi(fileparts(path),root) || ~isfile(path)
    error('msiq:sharedTx:Missing','Missing shared TX data: %s',path);
end
if ~strcmpi(msiq.file_sha256(path),reference.sha256)
    error('msiq:sharedTx:Hash','Shared TX data SHA-256 mismatch: %s',path);
end
end

function value = make_reference(owner,root,path,hash)
scope = char(java.io.File(owner).toPath().relativize(java.io.File(root).toPath()).toString());
if isempty(scope), scope = '.'; end
[~,name,ext] = fileparts(path);
value = struct('scope',scope,'file',[name,ext],'sha256',hash);
end

function tf = inside(path,root)
tf = strcmpi(path,root) || startsWith(lower(path),[lower(root),filesep]);
end

function path = canonical(path)
path = char(java.io.File(char(path)).getCanonicalPath());
end
