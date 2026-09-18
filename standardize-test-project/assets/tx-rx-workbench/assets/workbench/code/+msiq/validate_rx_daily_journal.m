function note=validate_rx_daily_journal()
%VALIDATE_RX_DAILY_JOURNAL Attempt/control failures survive without copying raw.
folder=msiq.validation_artifacts('directory');
cfg=msiq.build_config('v2_traditional_wz'); cfg.results_root=folder;
task=struct('id',9,'profile',struct('mode','mock'),'channels',{{'C3','C4'}}, ...
    'options',struct('enable_ldpc',false,'capture_then_demod',true), ...
    'balance',false,'count',3,'completed',0,'rows',{{}},'phase','capture', ...
    'active',true,'stopped',false,'reason','','started',tic,'board',struct());
run=msiq.rx_daily_journal('begin',cfg,task);
observation=struct('metrics',struct('pre_bit_count',194400,'pre_error_count',2, ...
    'pre_ber',2/194400,'mer_db',30),'display_raw',ones(10000,2),'attempt_reason','保留本次诊断原因');
task.rows={struct('role','trial','capture',struct('run_dir','source_1','raw_path','source_1/raw.mat'), ...
    'observation',observation)};
msiq.rx_daily_journal('update',cfg,task,run,struct('action','formal_capture','ok',true));
msiq.rx_daily_journal('update',cfg,task,run,struct('action','board_adjust', ...
    'payload',struct('kind','i','subband',2,'value',20.5)));
task.active=false; task.reason='串口中断，状态未确认';
msiq.rx_daily_journal('finalize',cfg,task,run, ...
    struct('action','board_adjust','ok',false,'error',task.reason));
loaded=load(fullfile(run.DataDir,'task_state.mat'),'state');
assert(numel(loaded.state.rows)==1 && numel(loaded.state.events)==4);
assert(~isfield(loaded.state.rows{1}.observation,'display_raw'));
assert(strcmp(loaded.state.rows{1}.observation.attempt_reason,'保留本次诊断原因'));
assert(loaded.state.events{3}.request.value==20.5);
info=jsondecode(fileread(run.RunInfoPath));
assert(strcmp(info.status,'failed') && info.counts.executed==1 && info.counts.failed==1);
assert(info.task.formal_completed==0);
assert(contains(fileread(fullfile(run.OutputDir,'summary.csv')),'194400'));
task.id=10; task.stopped=true; task.reason='已停止任务';
second=msiq.rx_daily_journal('begin',cfg,task);
msiq.rx_daily_journal('finalize',cfg,task,second);
assert(~strcmp(run.OutputDir,second.OutputDir));
info=jsondecode(fileread(second.RunInfoPath));
assert(strcmp(info.status,'stopped') && strcmp(info.stop_reason,'user_stop'));
task.id=11; task.stopped=false; task.reason='配平失败：统计分母无效';
third=msiq.rx_daily_journal('begin',cfg,task);
msiq.rx_daily_journal('finalize',cfg,task,third);
info=jsondecode(fileread(third.RunInfoPath));
assert(strcmp(info.status,'failed'),'配平失败不能因文字前缀被记为完成。');
note='任务日志持久保存尝试、控制请求、统计分母和失败/停止原因；不复制显示或原始波形。';
end
