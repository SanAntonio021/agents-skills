function note=validate_rx_simulation_source()
%VALIDATE_RX_SIMULATION_SOURCE Real coded source, fixed noise, live board transport.
msiq.instruments.io_audit('reset','');
folder=msiq.validation_artifacts('directory');
options=struct('cache_dir',fullfile(folder,'cache'),'test_fixture',true);
[cfg,profile,simulation]=msiq.rx_simulation_config(options);
assert(~cfg.instrument.local_loaded && isempty(cfg.instrument.local_config));
assert(cfg.waveform.ldpc_blocks_per_frame==3 && cfg.waveform.modulation_order==16);
assert(cfg.waveform.symbol_rate_hz==simulation.symbol_rate_hz);
file_worker=msiq.RxScopeWorker(struct(),'',struct(),'reference');
file_guard=onCleanup(@()finish(file_worker));
file_worker.submit(struct('action','prepare_simulation','simulation',options, ...
    'source_epoch',7,'timeout_s',180));
prepared=await(file_worker); assert(prepared.ok,prepared.error);
assert(prepared.source_epoch==7);
source=prepared.simulation_source;
assert(~source.cache_reused && isfile(source.waveform_path) && isfile(source.reference_path));
reused=msiq.rx_simulation_source(options);
assert(reused.cache_reused && strcmp(source.cache_key,reused.cache_key));
assert(strcmp(source.waveform_sha256,reused.waveform_sha256));
cfg=source.cfg;
io_options=struct('simulation_source',source,'log_path',fullfile(folder,'provider.log'), ...
    'failure_path',fullfile(folder,'failure.txt'));
io=msiq.rx_simulation_io(io_options); session=io.open(cfg.instrument.scope);
settings=msiq.instruments.rx_scope_settings(session,io.query);
bwl=settings.fields(endsWith({settings.fields.key},':BWL'));
assert(all(arrayfun(@(f)strcmp(f.value,'OFF')&&isequal(f.choices,{'OFF'}),bwl)));
raw=io.capture(session,source.channels);
same_io=msiq.rx_simulation_io(io_options); same_session=same_io.open(cfg.instrument.scope);
same=same_io.capture(same_session,source.channels);
assert(isequal(raw.channels(1).samples,same.channels(1).samples));
next=io.capture(session,source.channels);
assert(~isequal(raw.channels(1).samples,next.channels(1).samples));
assert(next.simulation.capture_sequence==2 && raw.simulation.seed==simulation.seed);
assert(numel(raw.channels(1).samples)==round(simulation.sample_rate_hz*10*simulation.timebase_s));
powers=arrayfun(@(r)mean(r.samples.^2),raw.channels);
imbalance=10*log10(powers(1)/powers(2));
assert(abs(imbalance-3)<.1);
reference=msiq.load_reference_bundle(source.reference_path);
cfg.receiver.debug_pre_fec_only=true; cfg.receiver.strict_reference_blocks=true;
decoder_raw=struct('samples',[raw.channels(1).samples raw.channels(2).samples], ...
    'time_axes',[raw.channels(1).time_axis_s raw.channels(2).time_axis_s], ...
    'sample_rate_hz',simulation.sample_rate_hz,'payload_pair','A','full_scale',Inf);
decoded=msiq.decode_capture(decoder_raw,reference.bundle.tx_ref,cfg);
assert(decoded.sync_ok && decoded.valid && all([decoded.primary_streams.pre_fec_bit_count]==194400));

% The actual worker updates provider state AFTER successful six-value sends.
worker=msiq.RxScopeWorker(cfg.instrument.scope,'msiq.rx_simulation_io',io_options);
guard=onCleanup(@()finish(worker));
worker.submit(struct('action','connect','source_epoch',8)); response=await(worker); assert(response.ok,response.error);
worker.submit(struct('action','board_connect','payload',struct('cfg',profile.board))); response=await(worker); assert(response.ok,response.error);
worker.submit(struct('action','board_initialize','payload',struct('settings',profile.initial_settings))); response=await(worker); assert(response.ok,response.error);
worker.submit(struct('action','capture','channels',{source.channels})); response=await(worker); assert(response.ok,response.error);
before=response.raw;
worker.submit(struct('action','board_adjust','payload',struct('kind','i','subband',1,'value',23)));
response=await(worker); assert(response.ok,response.error);
worker.submit(struct('action','capture','channels',{source.channels})); response=await(worker); assert(response.ok,response.error);
balanced=response.raw;
assert(balanced.simulation.sent_state.i(1)==23 && ...
    abs(20*log10(before.simulation.signal_gains(1)/balanced.simulation.signal_gains(1))-3)<1e-9);
assert(abs(20*log10(balanced.channels(1).rms_v/balanced.channels(2).rms_v))<.15);
worker.submit(struct('action','board_adjust','payload',struct('kind','rf','subband',1,'value',26)));
response=await(worker); assert(response.ok,response.error);
worker.submit(struct('action','capture','channels',{source.channels})); response=await(worker); assert(response.ok,response.error);
attenuated=response.raw;
assert(attenuated.simulation.noise_sigma_v==before.simulation.noise_sigma_v);
assert(all(abs(20*log10(balanced.simulation.signal_gains./attenuated.simulation.signal_gains)-6)<1e-9));
% Scope window/sample-rate/vertical-range edits affect real returned samples.
io.write(session,'TDIV 1.25e-6'); short=io.capture(session,source.channels);
assert(numel(short.channels(1).samples)==numel(raw.channels(1).samples)/2);
io.write(session,'VBS ''app.Acquisition.Horizontal.SampleRate.Value=20000000000''');
slower=io.capture(session,source.channels); assert(slower.channels(1).sample_rate_hz==20e9);
io.write(session,'C3:VDIV 0.005'); clipped=io.capture(session,source.channels);
assert(max(abs(clipped.channels(1).samples))<=.020001);
assert(sum(abs(clipped.channels(1).samples)>=.01999)>0);
io.close(session); same_io.close(same_session);
clear guard file_guard;
audit=msiq.instruments.get_audit();
assert(audit.connections==0 && audit.queries==0 && audit.writes==0 && audit.captures==0);
note='通信模拟长帧三块解调、3 dB 初始不平衡、实时成功下发、固定噪声底、可复现噪声序列、缓存复用及后台释放通过；真实仪器 I/O 为零。';
end

function r=await(worker)
started=tic;
while true
    [ready,r]=worker.poll(); if ready, return; end
    assert(toc(started)<210,'RX_Workbench:TestTimeout','后台测试超时。'); pause(.05);
end
end
function wait_closed(worker)
started=tic;
while ~worker.process.HasExited && toc(started)<40, pause(.05); end
assert(worker.process.HasExited,'RX_Workbench:TestTimeout','后台未退出。');
end
function finish(worker)
worker.close(); wait_closed(worker);
released=worker.release_status(); assert(released.ok,strjoin(released.errors,'; ')); delete(worker);
end
