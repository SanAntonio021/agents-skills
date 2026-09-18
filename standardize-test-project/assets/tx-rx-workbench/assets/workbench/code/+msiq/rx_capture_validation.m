function result=rx_capture_validation(run_dir,evidence)
%RX_CAPTURE_VALIDATION Finalize post-read evidence without changing raw/reference.
% Only an opted-in new acquisition may transition pending -> validated/rejected.
addpath(fullfile(fileparts(fileparts(mfilename('fullpath'))),'result_management'));
assert(isstruct(evidence) && isscalar(evidence) && isfield(evidence,'valid'), ...
    'msiq:traditionalRx:ValidationEvidence','采集校验结果必须包含 valid。');
validateattributes(evidence.valid,{'logical','numeric'},{'scalar','binary'});
path=msiq.artifact_path(run_dir,'capture_validation.json','read');
metadata_path=msiq.artifact_path(run_dir,'capture_metadata.json','read');
assert(isfile(metadata_path),'msiq:traditionalRx:ValidationEvidence','采集元数据不存在。');
metadata=jsondecode(fileread(metadata_path));
assert(isfield(metadata,'requires_capture_validation') && ...
    isequal(metadata.requires_capture_validation,true), ...
    'msiq:traditionalRx:ValidationEvidence','历史采集不能追加或改写最终校验。');
if ~isfile(path)
    % Read fallback is for historical lookup, never a new artifact destination.
    path=msiq.artifact_path(run_dir,'capture_validation.json','write');
end
result=evidence; result.valid=logical(result.valid);
if isfield(result,'status') && strcmp(result.status,'pending')
    assert(~result.valid,'msiq:traditionalRx:ValidationEvidence','待校验状态不能标为有效。');
else
    assert(isfile(msiq.artifact_path(run_dir,'raw_capture.mat','read')), ...
        'msiq:traditionalRx:ValidationEvidence','完整原始波形尚未保存。');
    if result.valid, result.status='validated'; else, result.status='rejected'; end
end
if ~isfield(result,'reason'), result.reason=''; end
if isfile(path)
    prior=jsondecode(fileread(path));
    assert(strcmp(prior.status,'pending'),'msiq:traditionalRx:ValidationFinal', ...
        '已完成的采集校验不能覆盖；请创建新的采集尝试。');
end
result.schema_version='1.0';
result.recorded_at=char(datetime('now','Format','yyyy-MM-dd HH:mm:ss.SSS'));
Result_Atomic_Write_Json(path,result);
end
