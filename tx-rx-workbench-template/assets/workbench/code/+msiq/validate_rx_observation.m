function report=validate_rx_observation()
%VALIDATE_RX_OBSERVATION Mock-only trigger preservation and record freshness.
payload=zeros(362,1,'uint8');
payload=put(payload,34,int16(1));
payload=put(payload,36,uint32(346)); payload=put(payload,60,uint32(16));
payload=put(payload,144,uint32(1)); payload=put(payload,148,uint32(2));
payload=put(payload,156,single(.01)); payload=put(payload,176,single(1e-9));
payload(297:312)=uint8(1:16); payload(347:end)=uint8(1:16);
session=struct('kind','scope','mock',true,'specification', ...
    struct('mock_raw_capture',struct('payloads',{{payload}})));
for observation=[false true]
    for fail=[false true]
        msiq.instruments.io_audit('reset');
        session.specification.fail_stage='';
        if fail, session.specification.fail_stage='raw_read'; end
        failed=false;
        try
            if observation
                raw=msiq.instruments.capture_scope_raw(session,{'C1'},struct('mode','observation'));
            else
                raw=msiq.instruments.capture_scope_raw(session,{'C1'});
            end
        catch exception
            failed=strcmp(exception.identifier,'msiq:instrument:MockRawReadFailure');
            if ~failed, rethrow(exception); end
        end
        assert(failed==fail);
        log=msiq.instruments.io_audit('get_command_history');
        commands=cellfun(@(r) r.command,log,'UniformOutput',false);
        assert(any(strcmp(commands,'STOP'))==~observation);
        assert(any(strcmp(commands,'TRMD AUTO'))==~observation);
        if observation, assert(isempty(commands)); end
    end
end
raw=msiq.rx_observation_freshness(raw,struct(),struct());
assert(raw.new_data && raw.freshness_known);
old=raw; raw.captured_at='later poll';
raw=msiq.rx_observation_freshness(raw,old,struct());
assert(~raw.new_data && strcmp(raw.captured_at,old.captured_at));
raw.channels.descriptor.sweeps_per_acq=3;
raw=msiq.rx_observation_freshness(raw,old,struct());
assert(raw.new_data);
raw.channels.descriptor.trigger_time_bytes(1)=99;
raw=msiq.rx_observation_freshness(raw,old,struct());
assert(raw.new_data);
raw.channels.descriptor=struct('source','mock');
raw=msiq.rx_observation_freshness(raw,old,struct());
assert(raw.new_data && ~raw.freshness_known && ~raw.acquisition_time_confirmed);
session.specification.fail_stage='';
session.specification.mock_raw_capture.payloads={payload};
update_value='1'; update_commands={};
observed=msiq.instruments.capture_scope_raw(session,{'C1'}, ...
    struct('mode','observation','query_fn',@update_query));
assert(strcmp(observed.channels.descriptor.result_update_id,'UpdateTime:1'));
assert(isequal(update_commands,{'VBS? ''return=app.Acquisition.C1.Out.Result.UpdateTime'''}));
prior=msiq.rx_observation_freshness(observed,struct(),struct());
update_value='2';
observed=msiq.instruments.capture_scope_raw(session,{'C1'}, ...
    struct('mode','observation','query_fn',@update_query));
observed=msiq.rx_observation_freshness(observed,prior,struct());
assert(observed.new_data && observed.channels.descriptor.sweeps_per_acq==prior.channels.descriptor.sweeps_per_acq);
update_value='ERROR unsupported'; update_commands={};
observed=msiq.instruments.capture_scope_raw(session,{'C1'}, ...
    struct('mode','observation','query_fn',@update_query));
assert(strcmp(observed.channels.descriptor.result_update_id,'LastEventTime:3'));
assert(numel(update_commands)==2 && contains(update_commands{2},'LastEventTime'));
big=payload;
for entry=[32 2;34 2;36 4;40 4;44 4;48 4;52 4;56 4;60 4; ...
        144 4;148 4;156 4;160 4;176 4;180 8;316 2;318 2].'
    index=entry(1)+(1:entry(2)); big(index)=flip(big(index));
end
big(35:36)=0;
session.specification.mock_raw_capture.payloads={big};
decoded=msiq.instruments.capture_scope_raw(session,{'C1'},struct('mode','observation'));
assert(max(abs(decoded.channels.samples-double(single(.01))*(1:16).'))<1e-12);
for mode={'sequence','ris'}
    altered=payload;
    if strcmp(mode{1},'sequence'), altered=put(altered,144,uint32(2));
    else, altered=put(altered,316,int16(1)); end
    session.specification.mock_raw_capture.payloads={altered};
    failed=false;
    try
        msiq.instruments.capture_scope_raw(session,{'C1'},struct('mode','observation'));
    catch exception
        failed=strcmp(exception.identifier,'RX_Workbench:UnsupportedMode');
    end
    assert(failed);
end
report=struct('passed',true,'hardware_io',false);
fprintf('RX observation PASS: trigger preservation success/failure, descriptor freshness, sequence/RIS rejection\n');
    function reply=update_query(~,command)
        update_commands{end+1}=command;
        if contains(command,'LastEventTime'), reply='3'; else, reply=update_value; end
    end
end

function bytes=put(bytes,offset,value)
encoded=typecast(value,'uint8'); bytes(offset+(1:numel(encoded)))=encoded;
end
