function report = Template_Validate(selection)
%TEMPLATE_VALIDATE Safe independent demos and the included regression cases.
if nargin<1, selection='smoke'; end
selection=validatestring(selection,{'smoke','iq','real_if','rx_workflows', ...
    'awg_memory','rx_plots','plot_export','tx_gui','rx_gui'});
guard=Template_NoHardware(); %#ok<NASGU>
switch selection
    case 'smoke'
        report.iq=Template_Demo('iq');
        report.real_if=Template_Demo('real_if');
        report.gui=Template_GUI_Demo;
        report.capacity=run_v2_validation('awg_memory');
    case {'iq','real_if'}
        report=Template_Demo(selection);
    case 'rx_workflows'
        folder=fullfile(fileparts(mfilename('fullpath')),'analysis', ...
            ['template_workflows_' char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
        mkdir(folder);
        report.output_dir=folder;
        report.simulation=run_case('simulation',@msiq.validate_rx_simulation_workflow);
        report.real_if=msiq.validate_rx_real_if_workflow(fullfile(folder,'real_if'));
        report.computed_range=run_case('computed_range',@msiq.validate_rx_computed_range);
        report.capture_settings=run_case('capture_settings',@msiq.validate_rx_capture_settings);
        report.native_memory=run_case('native_memory',@msiq.validate_rx_native_memory);
        report.daily_worker=run_case('daily_worker',@msiq.validate_rx_daily_worker);
        report.reference_link=run_case('reference_link',@msiq.validate_tx_reference_link);
        save(fullfile(folder,'validation.mat'),'report');
    otherwise
        report=run_v2_validation(selection);
end
assert(getappdata(0,'TemplateHardwareAttempts')==0,'Unexpected hardware constructor attempt.');
fprintf('TEMPLATE_VALIDATION_PASS %s\n',selection);
end
function note=run_case(name,action)
msiq.validation_artifacts('begin',name);
try
    note=action();
catch exception
    msiq.validation_artifacts('finish',true,getReport(exception,'extended'));
    rethrow(exception);
end
msiq.validation_artifacts('finish',false,'');
end