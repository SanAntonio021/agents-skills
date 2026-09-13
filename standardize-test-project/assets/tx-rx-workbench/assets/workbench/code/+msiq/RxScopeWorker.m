classdef RxScopeWorker < handle
    %RXScopeWorker One independent process owns VISA; GUI never waits for I/O.
    properties (SetAccess=private)
        folder
        process
        sequence = 0
        pending = false
        closing = false
        started
    end
    methods
        function obj = RxScopeWorker(specification, factory, factory_options, worker_kind)
            if nargin<4, worker_kind='scope'; end
            obj.folder = tempname;
            mkdir(obj.folder);
            obj.started = tic;
            project_code = fileparts(fileparts(mfilename('fullpath')));
            parent_pid = feature('getpid');
            save(fullfile(obj.folder,'bootstrap.mat'),'specification','factory', ...
                'factory_options','parent_pid','worker_kind');
            expression = sprintf('addpath(''%s''); msiq.rx_scope_worker(''%s'');', ...
                strrep(project_code,'''',''''''),strrep(obj.folder,'''',''''''));
            info = System.Diagnostics.ProcessStartInfo();
            info.FileName = fullfile(matlabroot,'bin','win64','MATLAB.exe');
            info.Arguments = sprintf('-nosplash -nodesktop -batch "%s" -logfile "%s"', ...
                expression,fullfile(obj.folder,'worker.log'));
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden;
            % MATLAB Desktop has no console to inherit. VISA startup warnings
            % otherwise throw "Error writing to output stream" in the child.
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            obj.process = System.Diagnostics.Process.Start(info);
            % Drain both pipes even without listeners; -logfile retains output.
            obj.process.BeginOutputReadLine();
            obj.process.BeginErrorReadLine();
        end
        function submit(obj, request)
            assert(~obj.pending,'RX_Workbench:WorkerBusy','Only one scope request may be active.');
            obj.sequence = obj.sequence+1;
            request.sequence = obj.sequence;
            temporary = fullfile(obj.folder,'request.tmp.mat');
            save(temporary,'request','-v7');
            movefile(temporary,fullfile(obj.folder,'request.mat'),'f');
            obj.pending = true;
            obj.started = tic;
        end
        function [ready,response] = poll(obj)
            ready = false; response = struct();
            path = fullfile(obj.folder,'response.mat');
            if obj.pending && isfile(path)
                data = load(path,'response');
                delete(path);
                if data.response.sequence ~= obj.sequence
                    error('RX_Workbench:WorkerSequence','Background result sequence does not match.');
                end
                response = data.response;
                obj.pending = false;
                ready = true;
            elseif obj.pending && obj.process.HasExited
                error('RX_Workbench:WorkerExited','后台进程退出；日志：%s',fullfile(obj.folder,'worker.log'));
            elseif obj.pending && toc(obj.started)>90
                obj.close(); obj.pending=false;
                phase='后台请求';
                progress=fullfile(obj.folder,'progress.txt');
                if isfile(progress), phase=strtrim(fileread(progress)); end
                error('RX_Workbench:WorkerTimeout','%s | 超时，等待后台安全释放会话',phase);
            end
        end
        function message = progress(obj)
            message = '';
            path = fullfile(obj.folder,'progress.txt');
            if isfile(path)
                try message = strtrim(fileread(path)); catch, end
            end
        end
        function close(obj)
            obj.closing=true;
            if isempty(obj.folder) || ~isfolder(obj.folder), return; end
            fid = fopen(fullfile(obj.folder,'close.flag'),'w');
            if fid >= 0, fclose(fid); end
        end
        function delete(obj)
            obj.close();
        end
    end
end
