function note = validate_if_migration()
%VALIDATE_IF_MIGRATION Public GUI retirement and explicit offline API contract.
before = msiq.instruments.get_audit();
figures = findall(groot,'Type','figure');
text = evalc('result = IF_Workbench();');
assert(strcmp(result.status,'migrated') && ~result.hardware_accessed);
assert(contains(text,'TX_Workbench') && contains(text,'RX_Workbench'));
% Even a stale live GUI profile cannot create a window or a hardware session.
text = evalc("result = IF_Workbench('gui',struct('profile',struct('mode','live')));");
assert(contains(text,'未打开工作台或连接仪器'));
assert(strcmp(result.status,'migrated'));
assert(isequal(figures,findall(groot,'Type','figure')));
p = IF_Workbench('config');
p.scan = struct('pre_start_db',20,'pre_stop_db',19,'pre_step_db',-1, ...
    'post_start_db',20,'post_stop_db',18,'post_step_db',-1);
plan = IF_Workbench('plan',struct('profile',p));
assert(isequal(plan.points,[20 20;20 19;20 18;19 20;19 19;19 18]));
assert(isequal(before,msiq.instruments.get_audit()));
note = 'IF no-argument/gui migration is window-free and I/O-free; explicit config/plan retained.';
end
