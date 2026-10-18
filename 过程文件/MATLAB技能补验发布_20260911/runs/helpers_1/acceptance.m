fprintf('MATLAB_VERSION %s\n',version); disp(ver); fprintf('PREFDIR %s\n',prefdir);
fprintf('SCREEN_SIZE '); disp(get(0,'ScreenSize')); fprintf('MONITORS '); disp(get(0,'MonitorPositions'));
features={'Communication_Toolbox','Signal_Toolbox','Control_Toolbox','Statistics_Toolbox','Instr_Control_Toolbox'};
for k=1:numel(features), assert(license('test',features{k}),['Missing license: ' features{k}]); end

r=runtests('D:/BaiduSyncdisk/.agents/skills/过程文件/MATLAB技能补验发布_20260911/candidate/standardize-test-project/assets/project-template/code/tests'); disp(r); assert(all([r.Passed]),'Helper tests failed or incomplete.'); save('D:/BaiduSyncdisk/.agents/skills/过程文件/MATLAB技能补验发布_20260911/runs/helpers_1/results.mat','r');
close all; drawnow; fprintf('ACCEPTANCE_COMPLETE helpers\n');
