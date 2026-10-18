fprintf('MATLAB_VERSION %s\n',version); disp(ver); fprintf('PREFDIR %s\n',prefdir);
fprintf('SCREEN_SIZE '); disp(get(0,'ScreenSize')); fprintf('MONITORS '); disp(get(0,'MonitorPositions'));
features={'Communication_Toolbox','Signal_Toolbox','Control_Toolbox','Statistics_Toolbox','Instr_Control_Toolbox'};
for k=1:numel(features), assert(license('test',features{k}),['Missing license: ' features{k}]); end

cd('D:/BaiduSyncdisk/.agents/skills/过程文件/MATLAB技能补验发布_20260911/isolated_workbench'); r=Template_Validate('tx_gui'); save('D:/BaiduSyncdisk/.agents/skills/过程文件/MATLAB技能补验发布_20260911/runs/tx_gui_1/results.mat','r');
close all; drawnow; fprintf('ACCEPTANCE_COMPLETE tx_gui\n');
