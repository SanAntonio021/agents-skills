function validate_rx_mock_config(output_dir)
%VALIDATE_RX_MOCK_CONFIG Local JSON must not enter an injected software run.
cfg = msiq.rx_mock_config();
options = struct('config',cfg,'injected_io',true, ...
    'asynchronous',false,'worker_factory','');
baseline = msiq.rx_workbench_config(options);
assert(~baseline.instrument.local_loaded && isempty(baseline.instrument.local_config_path));
assert(baseline.instrument.scope.mock && strcmp(baseline.instrument.scope.resource,'MOCK_RX_SCOPE'));
folder = tempname(output_dir); mkdir(folder);
fixtures = {'missing.json','malformed.json','unexpected.json'};
write_fixture(fullfile(folder,fixtures{2}),'{invalid local JSON');
write_fixture(fullfile(folder,fixtures{3}), ...
    '{"scope":{"mock":false,"channels":["C4","C3"],"resource":"SHOULD_NOT_BE_LOADED"}}');
for k = 1:numel(fixtures)
    options.config.instrument.local_config = fullfile(folder,fixtures{k});
    actual = msiq.rx_workbench_config(options);
    assert(isequaln(actual,baseline),'Injected RX configuration read a local fixture.');
end
options.asynchronous = true;
options.worker_factory = 'msiq.instruments.mock_rx_scope_io';
assert(isequaln(msiq.rx_workbench_config(options),baseline));
options.worker_factory = '';
expect_error(options,'RX_Workbench:TestConfig');
options.asynchronous = false; options.injected_io = false;
expect_error(options,'RX_Workbench:TestConfig');
options.worker_factory = 'msiq.instruments.mock_rx_scope_io';
expect_error(options,'RX_Workbench:TestConfig');
options.injected_io = true;
options.config.instrument = rmfield(options.config.instrument,'scope');
expect_error(options,'RX_Workbench:ScopeConfig');
% Exercise the public entry: user-supplied flags cannot enable injected config.
gui_options = struct('config',cfg,'visible',false,'use_timer',false, ...
    'auto_connect',false,'asynchronous',false,'injected_io',true,'offline_test',true);
expect_app_error(gui_options,'RX_Workbench:TestConfig');
gui_options.worker_factory = 'msiq.instruments.mock_rx_scope_io';
expect_app_error(gui_options,'RX_Workbench:TestConfig');
mock = struct('capture_delay_s',0,'record_count',1000, ...
    'log_path',fullfile(folder,'config_mock.log'), ...
    'failure_path',fullfile(folder,'config_mock_failure.txt'));
gui_options.io = msiq.instruments.mock_rx_scope_io(mock);
gui_options.worker_factory = '';
gui_options.find_reference = false;
gui_options.synchronous_startup = true;
gui_options.auto_connect = true;
gui_options.config.instrument.local_config = fullfile(folder,fixtures{2});
fig = msiq.rx_workbench_app(gui_options);
guard = onCleanup(@() close(fig));
state = getappdata(fig,'rx_workbench_state');
assert(state.connected && state.session.mock && state.offline_test);
assert(isequaln(state.cfg,baseline));
assert(contains(fileread(mock.log_path),'OPEN') && ~contains(fileread(mock.log_path),'WRITE '));
clear guard;
assert(contains(fileread(mock.log_path),'CLOSE'));
gui_options.config.instrument = rmfield(gui_options.config.instrument,'scope');
expect_app_error(gui_options,'RX_Workbench:ScopeConfig');
fprintf('RX config isolation PASS: missing/malformed/unexpected local JSON ignored; mock-only injection; missing scope rejected\n');
end

function write_fixture(path,content)
fid = fopen(path,'w'); assert(fid>=0);
guard = onCleanup(@() fclose(fid));
fprintf(fid,'%s',content);
end

function expect_error(options,identifier)
try
    msiq.rx_workbench_config(options);
catch exception
    assert(strcmp(exception.identifier,identifier),'Unexpected failure: %s',exception.message);
    return;
end
error('validation:ExpectedError','Expected %s.',identifier);
end

function expect_app_error(options,identifier)
before = findall(0,'Type','figure');
try
    msiq.rx_workbench_app(options);
catch exception
    assert(strcmp(exception.identifier,identifier),'Unexpected failure: %s',exception.message);
    assert(isequal(findall(0,'Type','figure'),before),'Rejected config created a figure.');
    return;
end
error('validation:ExpectedError','Expected %s.',identifier);
end
