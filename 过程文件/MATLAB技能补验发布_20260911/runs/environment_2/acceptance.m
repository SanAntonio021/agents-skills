fprintf('MATLAB_VERSION %s\n',version); disp(ver); fprintf('PREFDIR %s\n',prefdir);
fprintf('SCREEN_SIZE '); disp(get(0,'ScreenSize')); fprintf('MONITORS '); disp(get(0,'MonitorPositions'));
features={'Communication_Toolbox','Signal_Toolbox','Control_Toolbox','Statistics_Toolbox','Instr_Control_Toolbox'};
for k=1:numel(features), assert(license('test',features{k}),['Missing license: ' features{k}]); end

f=figure('Visible','off','Position',[20 -200 1500 900]); drawnow; disp(getpixelposition(f)); close(f);
close all; drawnow; fprintf('ACCEPTANCE_COMPLETE environment\n');
