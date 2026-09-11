function report=validate_rx_observation_worker(options)
%VALIDATE_RX_OBSERVATION_WORKER Exercise actual worker refresh with mock I/O.
if nargin>0
    report=mock_factory(options); return;
end
own_scope=~msiq.validation_artifacts('active');
if own_scope, msiq.validation_artifacts('begin','rx_observation_worker'); end
completion=containers.Map({'passed'},{false});
artifact_guard=onCleanup(@() finish_artifacts(own_scope,completion));
folder=msiq.validation_artifacts('directory');
options=struct('capture_delay_s',0,'record_count',1000, ...
    'log_path',fullfile(folder,'audit.log'),'failure_path',fullfile(folder,'failure.txt'), ...
    'external_path',fullfile(folder,'external.mat'),'no_new_frame',true);
worker=msiq.RxScopeWorker(struct(),'msiq.validate_rx_observation_worker',options);
msiq.validation_artifacts('defer',worker.folder);
guard=onCleanup(@() worker.close());
response=run(worker,struct('action','connect'));
assert(response.ok,response.error);
response=run(worker,struct('action','capture','channels',{{'C1','C2'}}));
assert(response.ok,response.error);
assert(strcmp(value(response.status.settings,'C1:TRA'),'ON'));
assert(strcmp(value(response.status.settings,'TRMD'),'AUTO'));
first=fileread(options.log_path);
external=struct('commands',{{'C1:TRA?','TRMD?', ...
    'VBS? ''return=app.Acquisition.Horizontal.SampleMode'''}}, ...
    'replies',{{'OFF','NORM','RIS'}});
save(options.external_path,'external');
response=run(worker,struct('action','capture','channels',{{'C1','C2'}}));
assert(response.ok && response.raw.unsupported_mode);
assert(strcmp(response.status.settings.sample_mode,'RIS'));
assert(strcmp(value(response.status.settings,'SAMPLEMODE'),'RIS'));
% A capture before the full refresh must not query every advanced option.
middle=fileread(options.log_path);
assert(count(middle,'AverageSweeps')==count(first,'AverageSweeps'));
pause(5.1);
response=run(worker,struct('action','capture','channels',{{'C1','C2'}}));
assert(response.ok && response.raw.unsupported_mode);
assert(strcmp(value(response.status.settings,'C1:TRA'),'OFF'));
assert(strcmp(value(response.status.settings,'TRMD'),'NORM'));
final=fileread(options.log_path);
assert(count(final,'GetRangeStringRemote')==count(first,'GetRangeStringRemote'));
assert(count(final,'AverageSweeps')>count(middle,'AverageSweeps'));
assert(~contains(final,'WRITE '));
worker.close(); started=tic;
while ~worker.process.HasExited && toc(started)<15, pause(.05); end
assert(worker.process.HasExited,'Mock worker did not close cooperatively.');
completion('passed')=true; %#ok<NASGU> Handle state is consumed by artifact cleanup.
report=struct('passed',true,'hardware_io',false);
fprintf('RX worker refresh PASS: external channel/trigger changes, per-frame sample mode, cached ranges, zero writes\n');
end

function finish_artifacts(own_scope,completion)
if own_scope
    msiq.validation_artifacts('finish',~completion('passed'),'Observation worker validation failed.');
end
end

function response=run(worker,request)
worker.submit(request); started=tic;
while toc(started)<80
    [ready,response]=worker.poll();
    if ready, return; end
    pause(.05);
end
error('msiq:validation:WorkerTimeout','Mock worker response timeout.');
end

function out=value(settings,key)
index=find(strcmp({settings.fields.key},key),1); assert(~isempty(index));
out=settings.fields(index).value;
end

function io=mock_factory(options)
io=msiq.instruments.mock_rx_scope_io(options);
original_query=io.query;
io.query=@query;
    function reply=query(session,command)
        reply=original_query(session,command);
        if isfile(options.external_path)
            data=load(options.external_path,'external');
            index=find(strcmp(data.external.commands,command),1);
            if ~isempty(index), reply=data.external.replies{index}; end
        end
    end
end
