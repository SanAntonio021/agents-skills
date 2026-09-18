function note=validate_rx_source_records()
%VALIDATE_RX_SOURCE_RECORDS Provenance survives saving independently of UI mode.
folder=msiq.validation_artifacts('directory');
msiq.instruments.io_audit('reset','');
t=(0:12002)'/40e9;
channel=struct('channel','C3','samples',.03*cos(2*pi*1e9*t), ...
    'time_axis_s',t,'sample_rate_hz',40e9);
raw=struct('channels',channel,'mock',true,'source_mode','simulation');
options=struct('results_root',folder,'measurement_role','formal','source_mode','simulation');
saved=msiq.traditional_rx('save_capture',raw,options);
actual=load(saved.raw_path,'raw');
assert(isequaln(actual.raw,raw),'Saving altered the full raw input.');
meta=jsondecode(fileread(saved.metadata_path));
assert(strcmp(meta.source_mode,'simulation') && strcmp(saved.source_mode,'simulation'));
assert(contains(fileread(fullfile(saved.run_dir,'summary.csv')),'模拟'));
info=jsondecode(fileread(fullfile(saved.diagnostics_dir,'run_info.json')));
assert(strcmp(info.capture_metadata.source_mode,'simulation'));
hash=compute_file_sha256(saved.raw_path);
bad=options; bad.source_mode='measurement';
expect(@()msiq.traditional_rx('save_capture',raw,bad),'msiq:rx:SourceConflict');
bad.source_mode='other';
expect(@()msiq.rx_capture_source(raw,bad),'msiq:rx:SourceMode');
legacy=rmfield(raw,'source_mode');
[source,category]=msiq.rx_capture_source(legacy,struct());
assert(strcmp(source,'simulation') && strcmp(category,'checks'));
expect(@()msiq.rx_capture_source(legacy,struct('source_mode','measurement')),'msiq:rx:SourceConflict');
old=struct('channels',channel,'captured_at','mock');
assert(strcmp(msiq.rx_capture_source(old,struct()),'simulation'));
old=struct('channels',channel); old.channels.descriptor=struct('source','mock');
assert(strcmp(msiq.rx_capture_source(old,struct()),'simulation'));
assert(strcmp(msiq.rx_capture_source(struct('channels',channel),struct()),'unknown'));
assert(strcmp(msiq.rx_capture_source(struct('channels',channel), ...
    struct('scope_status',struct('idn','LECROY,SDA845ZI-A,MOCK,8.1'))),'simulation'));
assert(strcmp(hash,compute_file_sha256(saved.raw_path)));
audit=msiq.instruments.get_audit();
assert(audit.connections==0 && audit.queries==0 && audit.writes==0 && audit.captures==0);
note='模拟来源写入元数据及CSV、原始数据保持、来源冲突拒绝、旧mock兼容，零仪器I/O。';
end
function expect(action,id)
try, action(); catch exception, assert(strcmp(exception.identifier,id),exception.message); return; end
error('msiq:validation:ExpectedFailure','Expected %s',id);
end
