classdef IfBoardDispatch < handle
    %IFBOARDDISPATCH Lazy board-only use of the existing instrument worker.
    properties (Access=private)
        Worker = []
        Timer = []
        Completion = []
        MockBoard = []
        Offline = false
    end
    methods
        function obj=IfBoardDispatch(offline)
            if nargin, obj.Offline=logical(offline); end
        end
        function send(obj,action,payload,completion)
            assert(isempty(obj.Completion),'msiq:ifboard:busy','上一项板卡操作尚未完成。');
            if obj.Offline
                response=struct('ok',false,'snapshot',struct(),'error','');
                try
                    switch action
                        case 'board_connect'
                            if ~isempty(obj.MockBoard), obj.MockBoard.close(); end
                            payload.cfg.mode='mock';
                            obj.MockBoard=msiq.instruments.IfBoard(payload.cfg); obj.MockBoard.open();
                        case 'board_initialize', obj.MockBoard.initialize(payload.settings);
                        case 'board_adjust', obj.MockBoard.setAttenuation(payload.kind,payload.subband,payload.value);
                        case 'board_close', obj.MockBoard.close();
                    end
                    response.ok=true;
                catch err, response.error=err.message;
                end
                if ~isempty(obj.MockBoard), response.snapshot=obj.MockBoard.snapshot(); end
                completion(response); return;
            end
            if ~isempty(obj.Worker) && obj.Worker.closing
                assert(obj.Worker.process.HasExited,'msiq:ifboard:closing', ...
                    '后台仍在释放串口，请等待完成后再连接。');
                delete(obj.Worker); obj.Worker=[];
                if strcmp(action,'board_close')
                    completion(struct('ok',true,'snapshot',struct('is_open',false,'state_known',false),'error',''));
                    return;
                end
            end
            if isempty(obj.Worker)
                assert(strcmp(action,'board_connect'),'msiq:ifboard:closed','请先连接板卡。');
                obj.Worker=msiq.RxScopeWorker(struct(),[],struct(),'board');
            end
            request=payload; request.action=action;
            obj.Worker.submit(request); obj.Completion=completion;
            if isempty(obj.Timer) || ~isvalid(obj.Timer)
                obj.Timer=timer('ExecutionMode','fixedSpacing','Period',0.1, ...
                    'BusyMode','drop','TimerFcn',@(~,~) obj.poll());
            end
            start(obj.Timer);
        end
        function close(obj)
            if ~isempty(obj.Timer) && isvalid(obj.Timer), stop(obj.Timer); delete(obj.Timer); end
            obj.Timer=[];
            if ~isempty(obj.Worker), obj.Worker.close(); end
            if ~isempty(obj.MockBoard), obj.MockBoard.close(); end
        end
        function delete(obj), obj.close(); end
    end
    methods (Access=private)
        function poll(obj)
            try
                [ready,response]=obj.Worker.poll();
            catch err
                ready=true; response=struct('ok',false,'error',err.message,'snapshot',struct());
            end
            if ~ready, return; end
            stop(obj.Timer); callback=obj.Completion; obj.Completion=[];
            if ~isempty(callback), callback(response); end
        end
    end
end
