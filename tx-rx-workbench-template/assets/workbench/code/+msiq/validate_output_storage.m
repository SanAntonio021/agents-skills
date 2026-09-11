function note = validate_output_storage(selection)
%VALIDATE_OUTPUT_STORAGE Exercise compact output, replot, and portable sharing.
if nargin < 1, selection = 'all'; end
root = tempname; mkdir(root);
cleanup = onCleanup(@() cleanup_root(root));
parts = {};
if ismember(selection,{'all','simulation'})
    parts{end+1} = simulation_case(root);
end
if ismember(selection,{'all','shared'})
    parts{end+1} = sharing_case(root);
end
if ismember(selection,{'all','analysis'})
    parts{end+1} = analysis_case(root);
end
if ismember(selection,{'all','sro'})
    parts{end+1} = sro_case(root);
end
if ismember(selection,{'all','lifecycle'})
    parts{end+1} = lifecycle_case(root);
end
note = strjoin(parts,'; ');
fprintf('%s\n',note);
end

function note = simulation_case(root)
cfg = msiq.build_config('v2_traditional_wz');
cfg.results.parameter_roundtrip_probe = [NaN,Inf,-Inf];
cfg.results_root = fullfile(root,'simulations');
matrix = msiq.build_experiment_matrix(cfg);
condition = matrix.conditions(find(strcmp({matrix.conditions.architecture},'single_complex_stream'),1));
msiq.instruments.reset_audit();
compact = msiq.run_condition(cfg,condition,'simulation');
cfg.results.output_level = 'full';
full = msiq.rerun_simulation(compact.run_dir,struct('output_level','full', ...
    'results_root',cfg.results_root));
assert(isequaln(metrics(compact),metrics(full)));
assert(~isfile(msiq.artifact_path(compact.run_dir,'raw_capture.mat')));
assert(~isfile(msiq.artifact_path(compact.run_dir,'decoded_result.mat')));
assert(isfile(msiq.artifact_path(full.run_dir,'raw_capture.mat')));
assert(isfile(msiq.artifact_path(full.run_dir,'decoded_result.mat')));
rerun_info = jsondecode(fileread(msiq.artifact_path(full.run_dir,'run_info.json')));
assert(contains(jsonencode(rerun_info.source_runs),strrep(compact.run_dir,'\','\\')));
source_info = jsondecode(fileread(msiq.artifact_path(compact.run_dir,'run_info.json')));
assert(isfield(source_info.parameters,'effective_config'));
packet = load(msiq.artifact_path(compact.run_dir,'plot_data.mat'));
assert(strcmp(packet.schema_version,'2.0') && numel(packet.plots)==4);
expected_plots = {'metrics_overview.png','constellation.png', ...
    '001_Channel1_星座图.png','overview.png'};
saved_plots = cellfun(@(p) p.file,packet.plots,'UniformOutput',false);
assert(isequal(sort(saved_plots(:)),sort(expected_plots(:))));
full_packet = load(msiq.artifact_path(full.run_dir,'plot_data.mat'));
full_plots = cellfun(@(p) p.file,full_packet.plots,'UniformOutput',false);
assert(isequal(sort(full_plots(:)),sort(expected_plots(:))));
assert(isequaln(full_packet.effective_config.results.parameter_roundtrip_probe, ...
    cfg.results.parameter_roundtrip_probe));
[compact_bytes,compact_files] = footprint(compact.run_dir);
[full_bytes,full_files] = footprint(full.run_dir);
assert(compact_bytes < full_bytes && compact_files < full_files);
before_hash = msiq.file_sha256(msiq.artifact_path(compact.run_dir,'plot_data.mat'));
replot = msiq.replot_run(compact.run_dir,struct('results_root',fullfile(root,'replots')));
assert(numel(replot.paths)==numel(packet.plots) && ~replot.dsp_executed);
for k = 1:numel(packet.plots)
    [~,replot_name,replot_extension] = fileparts(replot.paths{k});
    assert(strcmp([replot_name replot_extension],packet.plots{k}.file));
    original = imread(fullfile(compact.run_dir,packet.plots{k}.file));
    restored = imread(replot.paths{k});
    assert(isequal(size(original),size(restored)));
    assert(std(double(restored(:)))>5);
    difference = mean(abs(double(original(:))-double(restored(:))));
    assert(difference < 2,sprintf('Replot pixel difference: %.3f',difference));
end
assert(strcmp(before_hash,msiq.file_sha256(msiq.artifact_path(compact.run_dir,'plot_data.mat'))));
expect_error(@() msiq.replay_run(compact.run_dir),'msiq:replay:RerunSimulation');
legacy_dir = fullfile(root,'legacy'); mkdir(legacy_dir);
for name = {'raw_capture.mat','decoded_result.mat','run_info.json'}
    copyfile(msiq.artifact_path(full.run_dir,name{1}),fullfile(legacy_dir,name{1}));
end
legacy = msiq.replot_run(legacy_dir,struct('results_root',fullfile(root,'replots')));
assert(isfile(legacy.paths{1}));
cfg.results.write_results = false;
cfg.results_root = fullfile(root,'no_output');
none = msiq.run_condition(cfg,condition,'simulation');
assert(isempty(none.run_dir) && ~isfolder(cfg.results_root));
assert(isequaln(metrics(compact),metrics(none)));
cfg.results.write_results = true;
cfg.results_root = fullfile(root,'failure');
cfg.simulation.payload_pair = 'invalid_pair';
threw = false;
try
    msiq.run_condition(cfg,condition,'simulation');
catch
    threw = true;
end
assert(threw);
failed = dir(fullfile(cfg.results_root,'**','FAILED_diagnostic.mat'));
assert(numel(failed)==1);
audit = msiq.instruments.get_audit();
assert(all(struct2array(audit)==0));
note = sprintf('simulation compact %d files %.2f MiB / full %d files %.2f MiB; 4 independent replots', ...
    compact_files,compact_bytes/2^20,full_files,full_bytes/2^20);
end

function note = sharing_case(root)
batch = fullfile(root,'batch'); mkdir(batch);
plan = struct('waveforms',struct('awg_dac_data',reshape(1:20000,[],2)), ...
    'download',struct('channel_data',{{int8(1:100),int8(101:200)}}), ...
    'tx_ref',struct('symbols',(1:500).','seed',42), ...
    'route',struct('name','test'),'desired',struct('rdiv','DIV2'), ...
    'cfg',struct(),'storage_run_root',batch);
for k = 1:2
    tx = fullfile(batch,sprintf('tx%d',k)); mkdir(tx);
    plan.run_dir = tx;
    msiq.save_tx_manifest(tx,plan,struct('status','applied'));
    packet = load(msiq.artifact_path(tx,'tx_manifest.mat'));
    assert(~isfield(packet.plan,'waveforms'));
    waveform = msiq.load_tx_waveform(tx);
    assert(isequaln(waveform.waveforms,plan.waveforms));
    path = msiq.artifact_path(tx,'tx_reference_bundle.mat','write');
    bundle = struct('tx_ref',plan.tx_ref,'shared_data',packet.plan.shared_data);
    msiq.save_reference_bundle(path,bundle,path);
    loaded = msiq.load_reference_bundle(path);
    assert(isequaln(loaded.bundle.tx_ref,plan.tx_ref));
end
assert(numel(dir(fullfile(batch,'shared_tx_*.mat')))==1);
plan.waveforms.awg_dac_data(1) = -1;
third = fullfile(batch,'tx3'); mkdir(third);
msiq.save_tx_manifest(third,plan,struct('status','applied'));
assert(numel(dir(fullfile(batch,'shared_tx_*.mat')))==2);
moved = fullfile(root,'moved');
movefile(batch,moved);
second = fullfile(moved,'tx2');
loaded = msiq.load_tx_waveform(second);
assert(loaded.waveforms.awg_dac_data(1)==1);
bundle = msiq.load_reference_bundle(msiq.artifact_path(second,'tx_reference_bundle.mat'));
assert(isequaln(bundle.bundle.tx_ref,plan.tx_ref));
packet = load(msiq.artifact_path(fullfile(moved,'tx3'),'tx_manifest.mat'));
bad_path = fullfile(moved,packet.plan.shared_data.file);
fid = fopen(bad_path,'ab'); fwrite(fid,uint8('corruption')); fclose(fid);
expect_error(@() msiq.load_tx_waveform(fullfile(moved,'tx3')),'msiq:sharedTx:Hash');
delete(bad_path);
expect_error(@() msiq.load_tx_waveform(fullfile(moved,'tx3')),'msiq:sharedTx:Missing');
note = 'shared TX: identical/different arrays, bundle, move, corruption and missing reference passed';
end

function note = analysis_case(root)
opts = struct('results_root',fullfile(root,'equalrate'),'matched_snr_db',22, ...
    'sro_ppm',0,'time_axis_skew_samples',0,'prepend_samples',0);
compact = msiq.run_equal_rate_comparison('matched',opts);
assert(~isfile(msiq.artifact_path(compact.matched.run_dir,'iqmimo_raw_capture.mat')));
assert(~isfile(msiq.artifact_path(compact.matched.run_dir,'matched_result.mat')));
assert(isfile(msiq.artifact_path(compact.matched.run_dir,'plot_data.mat')));
replot = msiq.replot_run(compact.matched.run_dir,struct('results_root',fullfile(root,'replots')));
expected = {'overview.png','constellation.png', ...
    '001_SNR22dB_iqmimo_Channel1_星座图.png', ...
    '001_SNR22dB_iqmimo_Channel2_星座图.png', ...
    '002_SNR22dB_traditional_Channel1_星座图.png', ...
    '002_SNR22dB_traditional_Channel2_星座图.png'};
assert(numel(replot.paths)==numel(expected) && ~replot.dsp_executed);
for k = 1:numel(expected)
    assert(isfile(fullfile(replot.run_dir,expected{k})));
end
opts.write_results = false; opts.results_root = fullfile(root,'equalrate_none');
none = msiq.run_equal_rate_comparison('matched',opts);
assert(~isfolder(opts.results_root) && isempty(none.matched.run_dir));
assert(isequaln(compact.matched.iqmimo.aggregate,none.matched.iqmimo.aggregate));
assert(msiq.output_policy(struct('save_raw',true)).save_raw);
assert(~msiq.output_policy(struct('output_level','full','save_raw',false)).save_raw);
data = struct('rows',struct('mode_c',struct('sync',struct('large',ones(1000,1)), ...
    'metrics',struct('mer_db',30))),'trials',struct('raw',ones(1000,1),'cfg',opts));
saved = msiq.analysis_record(data);
assert(~isfield(saved.trials,'raw') && ~isfield(saved.rows.mode_c,'sync'));
assert(saved.rows.mode_c.metrics.mer_db==30);
note = 'equal-rate compact/no-write/replot and derived-only SRO record passed';
end

function note = lifecycle_case(root)
success = fullfile(root,'success'); mkdir(success);
msiq.validation_artifacts('begin','success_fixture');
assert(msiq.validation_artifacts('defer',success));
msiq.validation_artifacts('finish',false,'');
assert(~isfolder(success));
failed = fullfile(root,'failed'); mkdir(failed);
msiq.validation_artifacts('begin','failure_fixture');
assert(msiq.validation_artifacts('defer',failed));
retained = msiq.validation_artifacts('finish',true,'expected failure');
assert(numel(retained)==1 && isfile(fullfile(failed,'FAILED_validation.json')));
note = 'test success cleanup and failure retention passed';
end

function note = sro_case(root)
opts = struct('source','synthetic','families',{{'clean'}}, ...
    'results_root',fullfile(root,'sro_compact'));
compact = msiq.run_wz_sro_distortion_stress(opts);
opts.results_root = fullfile(root,'sro_full'); opts.save_raw = true;
full = msiq.run_wz_sro_distortion_stress(opts);
assert(isequaln(compact.rows,full.rows));
a = load(msiq.artifact_path(compact.run_dir,'wz_sro_distortion_stress.mat'));
b = load(msiq.artifact_path(full.run_dir,'wz_sro_distortion_stress.mat'));
assert(~isfield(a.trials,'raw') && ~isfield(a.rows.mode_c,'sync'));
assert(isfield(b.trials,'raw') && isfield(b.rows.mode_c,'sync'));
assert(~isfile(msiq.artifact_path(compact.run_dir,'summary.md')));
assert(~isfile(msiq.artifact_path(compact.run_dir,'FAILED_diagnostic.mat')));
check_replot_pixels(compact.run_dir);
opts.candidates_samples = 1.25;
opts.results_root = fullfile(root,'scan_full');
scan = msiq.run_wz_sro_interval_scan(opts);
assert(isfile(msiq.artifact_path(scan.run_dir,'candidate001.mat')));
assert(isfile(msiq.artifact_path(scan.run_dir,'synthetic_trials.mat')));
check_replot_pixels(scan.run_dir);
opts.save_raw = false; opts.results_root = fullfile(root,'scan_compact');
compact_scan = msiq.run_wz_sro_interval_scan(opts);
assert(isequaln(scan.rows,compact_scan.rows));
assert(~isfile(msiq.artifact_path(compact_scan.run_dir,'candidate001.mat')));
assert(~isfile(msiq.artifact_path(compact_scan.run_dir,'synthetic_trials.mat')));
check_replot_pixels(compact_scan.run_dir);
info = jsondecode(fileread(msiq.artifact_path(compact_scan.run_dir,'run_info.json')));
assert(~isempty(info.code.git_commit) && ~isempty(info.code.entry_file_sha256));
assert(isfield(info.parameters,'effective_trials'));
note = 'SRO stress/scan compact/full metric parity, exact replot and provenance passed';
end

function check_replot_pixels(root)
packet = load(msiq.artifact_path(root,'plot_data.mat'));
restored = msiq.replot_run(root,struct('results_root',fullfile(fileparts(root),'replots')));
for k = 1:numel(packet.plots)
    a = imread(fullfile(root,packet.plots{k}.file));
    b = imread(restored.paths{k});
    assert(isequal(a,b) && std(double(b(:)))>5);
end
end

function value = metrics(run)
value = [[run.streams.evm_rms];[run.streams.mer_db]; ...
    [run.streams.pre_fec_ber];[run.streams.post_fec_ber];[run.streams.bler]];
end

function [bytes,count] = footprint(path)
items = dir(fullfile(path,'**','*')); items = items(~[items.isdir]);
bytes = sum([items.bytes]); count = numel(items);
end

function expect_error(callback,id)
try
    callback();
catch exception
    assert(strcmp(exception.identifier,id),exception.message);
    return;
end
error('msiq:validation:ExpectedError','Expected %s.',id);
end

function cleanup_root(root)
if isfolder(root)
    if msiq.validation_artifacts('defer',root), return; end
    rmdir(root,'s');
end
end
