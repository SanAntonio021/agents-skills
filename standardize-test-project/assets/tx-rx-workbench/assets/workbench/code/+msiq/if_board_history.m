function [settings,port,note]=if_board_history(path,source,role)
%IF_BOARD_HISTORY Source-aware draft restoration; old unmarked files are live only.
settings=struct(); port=''; note='';
if strcmp(source,'simulation'), source='mock'; end
if strcmp(source,'measurement'), source='live'; end
assert(any(strcmp(source,{'mock','live'})),'msiq:ifboard:source','历史来源无效。');
if ~isfile(path), return; end
try
    saved=load(path);
    markedMock=isMock(saved); tagged='';
    if isfield(saved,'source_mode'), tagged=char(string(saved.source_mode)); end
    if isempty(tagged) && isfield(saved,'mode'), tagged=char(string(saved.mode)); end
    if any(strcmp(tagged,{'simulation','mock'})), tagged='mock'; markedMock=true; end
    if any(strcmp(tagged,{'measurement','live'})), tagged='live'; end
    if ~isempty(tagged) && ~any(strcmp(tagged,{'mock','live'}))
        note='历史来源无法识别，未加载。'; return;
    end
    if strcmp(source,'live') && markedMock
        note='模拟历史不能用于实测，当前数值保持空白。'; return;
    end
    if strcmp(source,'mock') && (~markedMock || strcmp(tagged,'live'))
        note='未加载其他来源的历史，使用模拟初值。'; return;
    end
    if isfield(saved,'role') && ~strcmp(char(string(saved.role)),role)
        note='历史板卡角色不匹配，未加载。'; return;
    end
    if isfield(saved,'settings') && isstruct(saved.settings) && isscalar(saved.settings)
        settings=saved.settings;
        if isfield(saved,'port') && (ischar(saved.port) || (isstring(saved.port) && isscalar(saved.port)))
            port=char(saved.port);
        end
        note='已载入历史设置，尚未下发。';
    end
catch
    note='历史设置无法读取，未自动填入数值。';
end
end
function yes=isMock(value)
yes=false;
if ~isstruct(value) || ~isscalar(value), return; end
for key={'mock','offline_test'}
    if isfield(value,key{1}) && isequal(value.(key{1}),true), yes=true; return; end
end
for key={'mode','source_mode','source'}
    if isfield(value,key{1}) && (ischar(value.(key{1})) || isstring(value.(key{1}))) && ...
            any(strcmp(string(value.(key{1})),["mock","simulation"]))
        yes=true; return;
    end
end
for key={'metadata','config','cfg'}
    if isfield(value,key{1}) && isMock(value.(key{1})), yes=true; return; end
end
end
