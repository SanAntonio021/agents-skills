function out=if_workbench_replay(options)
%IF_WORKBENCH_REPLAY Read saved runs, or recompute into a distinct analysis run.
assert(isfield(options,'run_dir')&&isfolder(options.run_dir), ...
    'msiq:if:ReplayPath','An existing IF run directory is required.');
checkpoint=msiq.artifact_path(options.run_dir,'if_checkpoint.mat','read');
saved=load(checkpoint,'out'); out=saved.out;
out.replay=true; out.status='offline_replay';
if ~isfield(options,'redecode') || ~isequal(options.redecode,true), return; end
debug=true;
if isfield(options,'debug_pre_fec_only'), debug=logical(options.debug_pre_fec_only); end
assert(isscalar(debug),'msiq:if:ReplayOption','debug_pre_fec_only must be scalar.');
cfg=msiq.build_config('v2_traditional_wz');
if isfield(options,'cfg_override'), cfg=options.cfg_override; end
analysis=msiq.create_output_run(cfg,'analysis','IF_redecode');
source=saved.out; out.source_run=options.run_dir; out.run_dir=analysis.OutputDir;
out.status='offline_recomputed'; out.debug_pre_fec_only=debug;
out.source_checkpoint_hash=msiq.sha256_bytes(jsonencode(source));
out.observations={}; out.replay_errors={};
for k=1:numel(source.observations)
    obs=source.observations{k}; item=obs;
    item.metrics=invalid('not_recomputed');
    item.replay_source_raw=obs.raw_path;
    try
        [~,name,ext]=fileparts(obs.raw_path);
        local=msiq.artifact_path(options.run_dir,[name ext],'read');
        if isfile(local), raw_path=local; else, raw_path=obs.raw_path; end
        value=load(raw_path,'raw'); raw=value.raw;
        item.replay_source_raw=raw_path;
        item.source_raw_hash=msiq.sha256_bytes(jsonencode(raw));
        reference='tx_reference_bundle.mat';
        candidate=['reference_' obs.memory_mode '.mat'];
        mode_path=msiq.artifact_path(options.run_dir,candidate,'read');
        has_mode_refs=isfile(msiq.artifact_path(options.run_dir,'reference_EXT.mat','read')) || ...
            isfile(msiq.artifact_path(options.run_dir,'reference_INT.mat','read'));
        if isfile(mode_path)||has_mode_refs, reference=candidate; end
        ref_path=msiq.artifact_path(options.run_dir,reference,'read');
        if isfield(obs,'reference_path')&&~isempty(obs.reference_path)
            [~,referenceName,referenceExtension]=fileparts(obs.reference_path);
            ref_path=msiq.artifact_path(options.run_dir,[referenceName referenceExtension],'read');
        end
        if isfield(options,'reference_bundle') && ~isempty(options.reference_bundle)
            ref_path=options.reference_bundle;
        end
        if strcmp(source.profile.mode,'mock') && ~isfile(ref_path)
            % Voltage-only fixtures have no transmitted symbols to decode.
            item.metrics=invalid('mock_fixture_has_no_symbol_reference');
            item.replay_status='not_demodulated';
            out.observations{end+1}=item;
            continue;
        end
        reference_data=msiq.load_reference_bundle(ref_path); bundle=reference_data.bundle;
        item.replay_reference_path=ref_path;
        item.source_reference_hash=msiq.sha256_bytes(jsonencode(bundle));
        rx_cfg=cfg;
        rx_cfg.waveform=bundle.dsp_config.waveform;
        rx_cfg.receiver=bundle.dsp_config.receiver;
        rx_cfg=restore_fec(rx_cfg,bundle.tx_ref);
        rx_cfg.receiver.debug_pre_fec_only=debug;
        [measurement,spectrum]=msiq.if_capture_observation(raw,source.profile,rx_cfg,obs.scale_vdiv);
        item.recomputed_observation=measurement;
        decoded=struct();
        if strcmp(source.profile.stage,'tx_if')
            item.replay_status='spectrum_only';
            item.metrics=invalid('tx_if_direct_demodulation_not_implemented');
        else
            records=raw.channels;
            assert(numel(records)==2&&numel(records(1).samples)==numel(records(2).samples), ...
                'msiq:if:ReplayChannels','Two equal-length I/Q records are required.');
            input=struct('samples',[records(1).samples(:),records(2).samples(:)], ...
                'time_axes',[records(1).time_axis_s(:),records(2).time_axis_s(:)], ...
                'sample_rate_hz',records(1).sample_rate_hz,'payload_pair','A', ...
                'already_baseband',strcmp(source.profile.stage,'rx_iq'), ...
                'iq_pair',true,'clip_fraction',measurement.clip_fraction);
            decoded=msiq.decode_capture(input,bundle.tx_ref,rx_cfg);
            streams=decoded.primary_streams;
            item.metrics=invalid('');
            item.metrics.valid=decoded.sync_ok&&~measurement.clipped&&all([streams.valid]);
            item.metrics.pre_error_count=sum([streams.pre_fec_bit_error_count]);
            item.metrics.pre_bit_count=sum([streams.pre_fec_bit_count]);
            item.metrics.valid=item.metrics.valid&&item.metrics.pre_bit_count>0;
            if item.metrics.valid
                item.metrics.pre_ber=item.metrics.pre_error_count/item.metrics.pre_bit_count;
            end
            item.metrics.mer_db=mean([streams.mer_db]);
            item.metrics.evm_rms=mean([streams.evm_rms]);
            item.replay_status='demodulated';
        end
        destination=msiq.artifact_path(out.run_dir,sprintf('redecode_%05d.mat',obs.attempt),'write');
        save(destination,'decoded','spectrum','item','rx_cfg','-v7.3');
        item.redecode_path=destination;
    catch ex
        item.metrics=invalid(ex.message); item.replay_status='invalid';
        out.replay_errors{end+1}=struct('attempt',obs.attempt, ...
            'identifier',ex.identifier,'message',ex.message);
    end
    out.observations{end+1}=item;
end
if ~isempty(out.replay_errors), out.status='offline_recomputed_with_errors'; end
destination=msiq.artifact_path(out.run_dir,'if_checkpoint.mat','write');
temporary=[destination '.tmp']; save(temporary,'out','-v7.3'); movefile(temporary,destination);
end
function m=invalid(reason)
m=struct('valid',false,'pre_error_count',NaN,'pre_bit_count',NaN, ...
    'pre_ber',NaN,'mer_db',NaN,'evm_rms',NaN,'reason',reason);
end
function cfg=restore_fec(cfg,ref)
if isfield(ref,'fec_config')
    cfg=msiq.fec.apply_reference(cfg,ref);
else
    f=ref.pairs(1).metrics_only(1).fec;
    cfg.fec.family='DVB-S2';
    if f.codeword_length==64800 && f.info_length==58320
        cfg.fec.frame_type='normal'; cfg.fec.rate_numerator=9; cfg.fec.rate_denominator=10;
    elseif f.codeword_length==16200 && f.info_length==14400
        cfg.fec.frame_type='short'; cfg.fec.rate_numerator=8; cfg.fec.rate_denominator=9;
    else
        error('msiq:if:ReplayReference','Unknown reference FEC dimensions.');
    end
    cfg.fec.rate=cfg.fec.rate_numerator/cfg.fec.rate_denominator;
    msiq.fec.specification(cfg);
end
end
