function [source,category]=rx_capture_source(raw,options)
%RX_CAPTURE_SOURCE Preserve acquisition provenance independently of GUI mode.
if nargin<2, options=struct(); end
declared=read_mode(options); acquired=read_mode(raw);
if ~isempty(declared) && ~isempty(acquired) && ~strcmp(declared,'unknown') && ...
        ~strcmp(acquired,'unknown') && ~strcmp(declared,acquired)
    error('msiq:rx:SourceConflict','保存设置的数据来源与原始采集不一致。');
end
source=acquired;
if isempty(source) || strcmp(source,'unknown'), source=declared; end
is_mock=mock_marker(raw) || mock_marker(options);
if strcmp(source,'measurement') && is_mock
    error('msiq:rx:SourceConflict','模拟采集不能保存为实测。');
end
if isempty(source) || strcmp(source,'unknown')
    if is_mock, source='simulation'; else, source='unknown'; end
end
category=source;
if strcmp(category,'unknown'), category='measurement'; end % Legacy directory contract, not evidence of source.
% Existing lightweight mock fixtures remain validation artifacts. Explicit
% communication simulation is a user run unless a validation scope owns it.
if (is_mock && isempty(declared) && isempty(acquired)) || ...
        (isfield(options,'test_fixture') && isequal(options.test_fixture,true)) || ...
        msiq.validation_artifacts('active')
    category='checks';
end
end

function value=read_mode(input)
value='';
if ~isfield(input,'source_mode') || isempty(input.source_mode), return; end
candidate=input.source_mode;
if ~((ischar(candidate) && isrow(candidate)) || (isstring(candidate) && isscalar(candidate)))
    error('msiq:rx:SourceMode','数据来源必须是 simulation 或 measurement。');
end
value=char(candidate);
if ~ismember(value,{'simulation','measurement','unknown'})
    error('msiq:rx:SourceMode','数据来源必须是 simulation 或 measurement。');
end
end

function yes=mock_marker(value)
yes=false;
if ~isstruct(value) || ~isscalar(value), return; end
if isfield(value,'mock') && isequal(value.mock,true), yes=true; return; end
for key={'captured_at','source'}
    if isfield(value,key{1}) && (ischar(value.(key{1})) || isstring(value.(key{1}))) && ...
            isscalar(string(value.(key{1}))) && strcmpi(string(value.(key{1})),"mock")
        yes=true; return;
    end
end
if isfield(value,'idn') && (ischar(value.idn) || (isstring(value.idn) && isscalar(value.idn)))
    yes=~isempty(regexpi(char(value.idn),'(^|[,\s])MOCK([,\s]|$)|^SIMULATION,','once'));
    if yes, return; end
end
for key={'scope_status','scope_status_before','descriptor'}
    if isfield(value,key{1}) && mock_marker(value.(key{1})), yes=true; return; end
end
if isfield(value,'channels') && isstruct(value.channels)
    yes=any(arrayfun(@mock_marker,value.channels));
end
end
