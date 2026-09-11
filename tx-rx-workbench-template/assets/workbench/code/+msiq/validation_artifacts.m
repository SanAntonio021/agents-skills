function output = validation_artifacts(action, varargin)
%VALIDATION_ARTIFACTS Defer temporary cleanup until the enclosing case is known.
persistent scopes
if isempty(scopes), scopes = {}; end
output = false;
switch action
    case 'active'
        output = ~isempty(scopes);
    case 'directory'
        if isempty(scopes), error('msiq:validation:Scope','No active validation case.'); end
        output = tempname;
        mkdir(output);
        scopes{end}.paths{end+1} = canonical(output);
    case 'begin'
        scopes{end+1} = struct('name',varargin{1},'paths',{{}});
    case 'defer'
        path = canonical(varargin{1});
        if ~safe_temp(path), error('msiq:validation:TempScope','Not a temporary child: %s',path); end
        if ~isempty(scopes)
            scopes{end}.paths = unique([scopes{end}.paths,{path}],'stable');
            output = true;
        end
    case 'finish'
        scope = scopes{end}; scopes(end) = [];
        output = {};
        failed = logical(varargin{1});
        for k = 1:numel(scope.paths)
            path = scope.paths{k};
            if ~safe_temp(path), error('msiq:validation:TempScope','Temporary path changed.'); end
            if ~isfolder(path), continue; end
            if failed
                Result_Atomic_Write_Json(fullfile(path,'FAILED_validation.json'), ...
                    struct('case',scope.name,'error',varargin{2},'retained_at',char(datetime('now'))));
                output{end+1} = path; %#ok<AGROW>
            else
                rmdir(path,'s');
            end
        end
end
end

function value = safe_temp(path)
root = canonical(tempdir);
value = startsWith(lower(path),[lower(root),filesep]);
end

function path = canonical(path)
path = char(java.io.File(char(path)).getCanonicalPath());
end
