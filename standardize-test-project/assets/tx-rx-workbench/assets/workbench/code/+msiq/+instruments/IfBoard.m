classdef IfBoard < handle
    %IFBOARD Explicit-session six-band control; construction never performs I/O.
    properties (SetAccess=private)
        Config
        State
        Requested
        Sent
        Readback
        History = struct('kind',{},'frame',{},'state',{},'outcome',{},'time',{})
        IsOpen = false
        StateKnown = false
        Cancelled = false
        Confirmation = ''
    end
    properties (Access=private)
        Port = []
        WriteCount = 0
    end
    methods
        function obj = IfBoard(cfg)
            if nargin==0, cfg=struct(); end
            if ~isfield(cfg,'mode'), cfg.mode='mock'; end
            assert(any(strcmp(cfg.mode,{'mock','live'})), ...
                'msiq:ifboard:mode','Mode must be mock or live.');
            obj.Config=cfg;
            obj.State=struct('rf',nan(1,6),'i',nan(1,6),'q',nan(1,6),'agc',nan(1,6));
            obj.Requested=obj.State; obj.Sent=obj.State; obj.Readback=obj.State;
            if isfield(cfg,'initial_state') && isfield(cfg,'initial_state_confirmed') && ...
                    isequal(cfg.initial_state_confirmed,true)
                assert(isfield(cfg,'state_confirmation'),'msiq:ifboard:confirmation','State confirmation text required.');
                obj.confirmState(cfg.initial_state,cfg.state_confirmation);
            end
        end
        function open(obj)
            assert(~obj.Cancelled,'msiq:ifboard:cancelled','Create a new session after cancellation.');
            if obj.IsOpen, return; end
            if strcmp(obj.Config.mode,'live')
                assert(obj.flag('protocol_verified'),'msiq:ifboard:protocolGate', ...
                    'Runtime protocol verification required before serial access.');
                assert(isfield(obj.Config,'serial'),'msiq:ifboard:serialGate','Explicit serial configuration required.');
                s=obj.Config.serial;
                fields={'port','baud_rate','data_bits','parity','stop_bits','flow_control','timeout','protocol_version'};
                for k=1:numel(fields)
                    assert(isfield(s,fields{k}) && ~isempty(s.(fields{k})), ...
                        'msiq:ifboard:serialGate','Missing serial field %s.',fields{k});
                end
                validateattributes(s.baud_rate,{'numeric'},{'scalar','integer','positive','finite'});
                validateattributes(s.timeout,{'numeric'},{'scalar','positive','finite'});
                assert(ismember(s.data_bits,[5 6 7 8]) && ismember(s.stop_bits,[1 1.5 2]) && ...
                    any(strcmpi(s.parity,{'none','odd','even','mark','space'})) && ...
                    any(strcmpi(s.flow_control,{'none','hardware','software'})), ...
                    'msiq:ifboard:serialGate','Invalid serial framing.');
                % This is the only serial constructor in this adapter.
                obj.Port=serialport(s.port,s.baud_rate,'DataBits',s.data_bits, ...
                    'Parity',s.parity,'StopBits',s.stop_bits,'FlowControl',s.flow_control,'Timeout',s.timeout);
            end
            obj.IsOpen=true;
        end
        function confirmState(obj,state,note)
            assert(~isempty(strtrim(char(note))),'msiq:ifboard:confirmation','Describe manual state confirmation.');
            for name={'rf','i','q','agc'}
                key=name{1}; assert(isfield(state,key),'msiq:ifboard:state','All four state arrays required.');
                msiq.instruments.if_board_encode(key,state.(key));
                state.(key)=double(state.(key)(:).');
            end
            obj.State=state; obj.Requested=state; obj.StateKnown=true;
            obj.Confirmation=char(note);
            % Manual confirmation is neither a sent command nor device readback.
        end
        function assertAutomaticReady(obj)
            obj.requireReady();
            obj.checkState(obj.State);
            assert(obj.flag('protocol_verified') && obj.flag('mapping_verified') && ...
                obj.flag('response_verified'),'msiq:ifboard:autoGate', ...
                'Automatic actions require protocol, physical mapping and response verification.');
        end
        function setAttenuation(obj,kind,subband,value)
            obj.requireReady(); kind=lower(char(kind));
            assert(any(strcmp(kind,{'rf','i','q'})),'msiq:ifboard:kind','Attenuation kind required.');
            validateattributes(subband,{'numeric'},{'scalar','integer','>=',1,'<=',6});
            next=obj.State; next.(kind)(subband)=value;
            obj.checkState(next); obj.Requested=next;
            obj.send(kind,next);
        end
        function setIQ(obj,subband,iDb,qDb)
            obj.requireReady();
            validateattributes(subband,{'numeric'},{'scalar','integer','>=',1,'<=',6});
            target=obj.State; target.i(subband)=iDb; target.q(subband)=qDb;
            obj.checkState(target);
            delta=[iDb-obj.State.i(subband),qDb-obj.State.q(subband)];
            order=[find(delta>0),find(delta<0)]; names={'i','q'};
            % Validate every intermediate before any I/O, then preserve order.
            stages=cell(1,numel(order)); next=obj.State;
            for k=1:numel(order)
                key=names{order(k)}; next.(key)=target.(key);
                obj.checkState(next); stages{k}=next;
            end
            obj.Requested=target;
            for k=1:numel(order), obj.send(names{order(k)},stages{k}); end
        end
        function setAGC(obj,subband,value)
            obj.requireReady();
            validateattributes(subband,{'numeric'},{'scalar','integer','>=',1,'<=',6});
            next=obj.State; next.agc(subband)=value;
            msiq.instruments.if_board_encode('agc',next.agc);
            obj.Requested=next; obj.send('agc',next);
        end
        function result = acceptReceived(obj,frame)
            % Pure ingestion: no polling and no attenuation-readback inference.
            result=msiq.instruments.if_board_decode(frame);
            obj.Readback.(result.kind)=result;
        end
        function out=snapshot(obj)
            out=struct('state',obj.State,'requested',obj.Requested,'sent',obj.Sent, ...
                'readback',obj.Readback,'state_known',obj.StateKnown, ...
                'confirmation',obj.Confirmation,'is_open',obj.IsOpen,'cancelled',obj.Cancelled);
        end
        function cancel(obj)
            obj.Cancelled=true; obj.StateKnown=false;
        end
        function close(obj)
            if ~isempty(obj.Port), delete(obj.Port); obj.Port=[]; end
            if obj.IsOpen, obj.StateKnown=false; end
            obj.IsOpen=false;
        end
        function delete(obj), obj.close(); end
    end
    methods (Access=private)
        function yes=flag(obj,name)
            yes=isfield(obj.Config,'runtime') && isfield(obj.Config.runtime,name) && ...
                isequal(obj.Config.runtime.(name),true);
        end
        function requireReady(obj)
            if isfield(obj.Config,'cancel_check')
                drawnow;
                if obj.Config.cancel_check(), obj.cancel(); end
            end
            assert(obj.IsOpen && ~obj.Cancelled,'msiq:ifboard:closed','Session closed or cancelled.');
            assert(obj.StateKnown,'msiq:ifboard:unknown', ...
                'State unconfirmed. Explicit manual confirmation required; never silently retry.');
        end
        function checkState(obj,state)
            assert(isfield(obj.Config,'limits'),'msiq:ifboard:limits','Approved attenuation limits required.');
            for name={'rf','i','q'}
                key=name{1}; msiq.instruments.if_board_encode(key,state.(key));
                assert(isfield(obj.Config.limits,key),'msiq:ifboard:limits','Missing %s limits.',key);
                lim=obj.Config.limits.(key);
                assert(isnumeric(lim) && isequal(size(lim),[6 2]) && all(isfinite(lim(:))) && ...
                    all(lim(:,1)<=lim(:,2)) && all(lim(:)>=0 & lim(:)<=31.5), ...
                    'msiq:ifboard:limits','Limits must be six-by-two bounded approved dB values.');
                v=state.(key)(:);
                assert(all(v>=lim(:,1) & v<=lim(:,2)), ...
                    'msiq:ifboard:limits','Intermediate %s state exceeds approved limits.',key);
            end
        end
        function send(obj,kind,next)
            obj.requireReady(); frame=msiq.instruments.if_board_encode(kind,next.(kind));
            entry=struct('kind',kind,'frame',frame,'state',next,'outcome','pending', ...
                'time',char(datetime('now','Format','yyyy-MM-dd HH:mm:ss.SSS')));
            obj.History(end+1)=entry; obj.WriteCount=obj.WriteCount+1;
            try
                if strcmp(obj.Config.mode,'mock')
                    if isfield(obj.Config,'fail_on_write') && obj.WriteCount==obj.Config.fail_on_write
                        error('msiq:ifboard:injected','Injected possibly partial serial write.');
                    end
                else
                    write(obj.Port,frame,'uint8');
                end
                obj.State=next; obj.Sent.(kind)=next.(kind);
                obj.History(end).outcome='sent_not_readback';
            catch err
                obj.StateKnown=false; obj.History(end).outcome='unknown_after_failure';
                rethrow(err);
            end
        end
    end
end
