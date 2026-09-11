function report=validate_if_compatibility()
%VALIDATE_IF_COMPATIBILITY Public API inventory and syntax; not a target-runtime claim.
root=msiq.project_root();
files=[dir(fullfile(root,'code','+msiq','if_*.m'));dir(fullfile(root,'code','+msiq','IfRun.m')); ...
    dir(fullfile(root,'code','+msiq','+instruments','IfBoard.m')); ...
    dir(fullfile(root,'code','+msiq','+instruments','if_board_*.m'))];
messages={};
for k=1:numel(files)
    file=fullfile(files(k).folder,files(k).name); source=fileread(file);
    assert(~contains(source,'getByteStreamFromArray'),'msiq:if:PrivateAPI','Use public serialization APIs.');
    found=checkcode(file,'-id');
    assert(~any(ismember({found.id},{'SYNER','PARSE','ENDCT'})),'msiq:if:Syntax','Syntax error in %s',file);
    messages{end+1}=struct('file',files(k).name,'analyzer_messages',found);
end
apis={'uifigure','uigridlayout','uiaxes','jsonencode','serialport','save','movefile','onCleanup'};
available=cellfun(@(x)exist(x,'file')~=0||exist(x,'builtin')~=0,apis);
assert(all(available),'msiq:if:API','Required host API is unavailable.');
report=struct('ok',true,'host_release',version('-release'),'target_release','R2023a', ...
    'R2023a_executed',strcmp(version('-release'),'2023a'), ...
    'target_runtime_status','pending execution on R2023a', ...
    'scope','Public API inventory and current-host syntax inspection only', ...
    'apis',{apis},'host_available',available,'source_checks',{messages});
run=msiq.create_output_run(msiq.build_config('v2_traditional_wz'),'checks','IF_API_compatibility');
Result_Atomic_Write_Json(fullfile(run.DataDir,'api_compatibility.json'),report);
report.run_dir=run.OutputDir;
end
