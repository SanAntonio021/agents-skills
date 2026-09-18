function [cfg,profile,simulation]=rx_simulation_config(options)
%RX_SIMULATION_CONFIG Pure software defaults, independent of local instruments.
if nargin<1, options=struct(); end
simulation=struct('symbol_rate_hz',65e9/15,'sample_rate_hz',40e9, ...
    'timebase_s',2.5e-6,'seed',19427,'baseline_snr_db',30, ...
    'iq_imbalance_db',3,'baseline_attenuation_db',20,'base_q_rms_v',.02, ...
    'subband',1,'channels',{{'C3','C4'}},'cache_dir', ...
    fullfile(tempdir,'msiq_rx_simulation_cache'),'test_fixture',false);
names=fieldnames(simulation);
for k=1:numel(names)
    if isfield(options,names{k}), simulation.(names{k})=options.(names{k}); end
end
for key={'symbol_rate_hz','sample_rate_hz','timebase_s','base_q_rms_v'}
    validateattributes(simulation.(key{1}),{'numeric'},{'scalar','positive','finite'});
end
validateattributes(simulation.seed,{'numeric'},{'scalar','integer','nonnegative','<=',2^32-1});
validateattributes(simulation.subband,{'numeric'},{'scalar','integer','>=',1,'<=',6});
validateattributes(simulation.baseline_snr_db,{'numeric'},{'scalar','finite'});
validateattributes(simulation.iq_imbalance_db,{'numeric'},{'scalar','finite'});
validateattributes(simulation.baseline_attenuation_db,{'numeric'},{'scalar','>=',0,'<=',31.5});
simulation.channels=cellstr(upper(string(simulation.channels(:).')));
assert(numel(simulation.channels)==2 && numel(unique(simulation.channels))==2 && ...
    all(ismember(simulation.channels,{'C1','C2','C3','C4'})), ...
    'RX_Workbench:SimulationChannels','通信模拟需要两个不同的物理通道。');
cfg=msiq.rx_mock_config();
cfg.waveform.ldpc_blocks_per_frame=3; cfg.waveform.frame_repetitions=1;
cfg.waveform.modulation_order=16;
cfg.instrument.scope.channels=simulation.channels;
cfg=msiq.build_config(cfg);
cfg.waveform.symbol_rate_hz=simulation.symbol_rate_hz;
cfg.waveform.occupied_bandwidth_hz=simulation.symbol_rate_hz*(1+cfg.waveform.rolloff);
cfg.waveform.awg_samples_per_symbol=cfg.waveform.awg_sample_rate_hz/simulation.symbol_rate_hz;
cfg.source_mode='simulation';
profile=msiq.if_workbench_config(struct('mode','mock','stage','rx_iq'));
profile.source_mode='simulation'; profile.subband=simulation.subband;
profile.scope.channels=simulation.channels;
profile.scope.sample_rate_hz=simulation.sample_rate_hz;
profile.scope.window_s=10*simulation.timebase_s;
profile.scope.vdiv=[.05 .05]; profile.scope.ranges_vdiv=[.01 .02 .05 .1 .2 .5 1];
profile.scope.fresh=struct('verified',true,'timeout_s',5,'poll_s',.01, ...
    'reset_command','MOCK:RESET','start_command','MOCK:START', ...
    'completion_query','MOCK:DONE?','pending_response','0','complete_response','1');
profile.board=struct('mode','mock','role','rx', ...
    'limits',struct('rf',repmat([0 31.5],6,1),'i',repmat([0 31.5],6,1), ...
    'q',repmat([0 31.5],6,1)), ...
    'mapping',struct('i_channel',simulation.channels{1},'q_channel',simulation.channels{2}), ...
    'runtime',struct('protocol_verified',true,'mapping_verified',true,'response_verified',true));
v=repmat(simulation.baseline_attenuation_db,1,6);
profile.initial_settings=struct('rf',v,'i',v,'q',v);
end
