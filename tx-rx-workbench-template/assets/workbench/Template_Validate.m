function report = Template_Validate(selection)
%TEMPLATE_VALIDATE Safe wrapper around demonstrations and original tests.
if nargin<1, selection='smoke'; end
selection=validatestring(selection,{'smoke','awg_memory','rx_plots','plot_export','tx_gui','rx_gui'});
guard=Template_NoHardware(); %#ok<NASGU>
if strcmp(selection,'smoke')
    report.demo=Template_Demo;
    report.gui=Template_GUI_Demo;
    report.capacity=run_v2_validation('awg_memory');
else
    report=run_v2_validation(selection);
end
assert(getappdata(0,'TemplateHardwareAttempts')==0,'Unexpected hardware constructor attempt.');
fprintf('TEMPLATE_VALIDATION_PASS %s\n',selection);
end
