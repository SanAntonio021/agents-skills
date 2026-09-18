function source=rx_simulation_source(options)
%RX_SIMULATION_SOURCE Prepare and cache actual coded communication waveforms.
% Run in the file worker; the scope provider only consumes this saved source.
if nargin<1, options=struct(); end
[cfg,profile,simulation]=msiq.rx_simulation_config(options);
identity=simulation; identity=rmfield(identity,{'cache_dir','test_fixture'});
code_root=fileparts(mfilename('fullpath'));
identity.schema_version=1;
identity.waveform_config=cfg.waveform;
identity.receiver_config=cfg.receiver;
identity.fec_config=cfg.fec;
identity.source_sha256=msiq.file_sha256([mfilename('fullpath') '.m']);
identity.generator_sha256=msiq.file_sha256(fullfile(code_root,'generate_waveforms.m'));
identity.tx_sha256=msiq.file_sha256(fullfile(code_root,'traditional_tx.m'));
key=msiq.sha256_bytes(jsonencode(identity));
folder=fullfile(simulation.cache_dir,key);
manifest=fullfile(folder,'source.mat');
if isfile(manifest)
    saved=load(manifest,'source'); source=saved.source;
    if strcmp(source.cache_key,key) && isfile(source.waveform_path) && isfile(source.reference_path) && ...
            strcmp(msiq.file_sha256(source.waveform_path),source.waveform_sha256) && ...
            strcmp(msiq.file_sha256(source.reference_path),source.reference_sha256)
        source.cache_reused=true; source.simulation=simulation; source.if_profile=profile;
        return;
    end
    error('RX_Workbench:SimulationCache','通信模拟缓存已变化；请选择新的缓存目录。');
end
if ~isfolder(folder), mkdir(folder); end
plan=msiq.traditional_tx('preview_plan',[],struct('cfg_override',cfg, ...
    'symbol_rate_hz',simulation.symbol_rate_hz,'rate_authority','symbol_rate', ...
    'scope_channels',{simulation.channels}, ...
    'awg_channels',cellfun(@(c)str2double(c(2)),simulation.channels), ...
    'rdiv','DIV4','memory_mode','EXT', ...
    'frame_repetitions',1));
cfg=plan.cfg; cfg.source_mode='simulation';
signal=complex(plan.waveforms.master_dac_data(:,1),plan.waveforms.master_dac_data(:,2));
% Set the baseline Q RMS while retaining the actual frame, training and payload.
signal=complex(real(signal)/sqrt(mean(real(signal).^2)), ...
    imag(signal)/sqrt(mean(imag(signal).^2)))*simulation.base_q_rms_v;
master_rate_hz=plan.waveforms.master_sample_rate_hz;
waveform_path=fullfile(folder,'waveform.mat');
msiq.atomic_save(waveform_path,struct('signal',signal,'master_rate_hz',master_rate_hz));
bundle=struct('route',plan.route,'desired',plan.desired,'tx_ref',plan.tx_ref, ...
    'reference_payload_policy','metrics_only','source_mode','simulation', ...
    'execution',struct('status','applied','simulated',true,'hardware_executed',false), ...
    'dsp_config',struct('waveform',cfg.waveform,'receiver',cfg.receiver));
reference_path=fullfile(folder,'tx_reference_bundle.mat');
msiq.atomic_save(reference_path,struct('bundle',bundle));
source=struct('schema_version',1,'source_mode','simulation','cache_key',key, ...
    'cache_reused',false,'waveform_path',waveform_path,'reference_path',reference_path, ...
    'waveform_sha256',msiq.file_sha256(waveform_path), ...
    'reference_sha256',msiq.file_sha256(reference_path), ...
    'cfg',cfg,'if_profile',profile,'simulation',simulation,'channels',{simulation.channels}, ...
    'fresh',profile.scope.fresh,'symbol_rate_hz',cfg.waveform.symbol_rate_hz, ...
    'sample_count',numel(signal),'frame_period_s',numel(signal)/master_rate_hz);
msiq.atomic_save(manifest,struct('source',source));
end
