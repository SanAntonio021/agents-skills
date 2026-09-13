function plan = if_workbench_plan(p)
%IF_WORKBENCH_PLAN Complete explicit grid, gates and acquisition accounting.
blockers={}; points=zeros(0,2);
try
    a=axis_values(p.scan.pre_start_db,p.scan.pre_stop_db,p.scan.pre_step_db);
    b=axis_values(p.scan.post_start_db,p.scan.post_stop_db,p.scan.post_step_db);
    points=[reshape(repelem(a(:),numel(b)),[],1),repmat(b(:),numel(a),1)];
catch ex
    blockers{end+1}=ex.message;
end
names=fieldnames(p.policy);
for k=1:numel(names)
    v=p.policy.(names{k});
    if ~isscalar(v)||~isfinite(v)||v<0, blockers{end+1}=['Missing policy: ' names{k}]; end
end
if isempty(p.scope.ranges_vdiv)||any(~isfinite(p.scope.vdiv))|| ...
        ~isfinite(p.scope.headroom)||p.scope.headroom<=0||p.scope.headroom>=1|| ...
        ~isfinite(p.scope.max_adjustments)
    blockers{end+1}='Scope ranges, headroom and adjustment budget are required.';
end
if strcmp(p.mode,'live')
    if ~p.scope.fresh.verified, blockers{end+1}='Fresh acquisition completion is not verified.'; end
    if isempty(p.wiring.id)||isempty(p.wiring.confirmed_at), blockers{end+1}='Wiring confirmation is required.'; end
    if ~isfield(p.board,'runtime')||~all_flags(p.board.runtime)
        blockers{end+1}='Board protocol, physical mapping and response must be verified.';
    end
    try
        msiq.if_workbench_validate_profile(p,'scan');
        assert(~p.mock_fixture_applied,'Live profile contains synthetic mock defaults.');
        assert(isfile(p.reference_bundle),'Saved reference bundle is missing.');
        assert(all(ismember({'awg','scope','board'},p.authorized_devices)),'Required devices are not authorized.');
        f=p.scope.fresh;
        assert(isscalar(f.timeout_s)&&isfinite(f.timeout_s)&&f.timeout_s>0&& ...
            isscalar(f.poll_s)&&isfinite(f.poll_s)&&f.poll_s>0,'Fresh capture timing is missing.');
        for field={'reset_command','start_command','completion_query','pending_response','complete_response'}
            assert(~isempty(f.(field{1})),'Fresh capture handshake is incomplete.');
        end
        assert(~strcmp(f.pending_response,f.complete_response),'Pending and completion responses are identical.');
    catch ex
        blockers{end+1}=ex.message;
    end
end
identity=p;
% Confirmations and current target state may change during explicit recovery.
identity=rmfield(identity,intersect(fieldnames(identity),{'initial','mock'}));
if isfield(identity.board,'state_confirmation'), identity.board=rmfield(identity.board,'state_confirmation'); end
if isfield(identity.board,'initial_state_confirmed'), identity.board=rmfield(identity.board,'initial_state_confirmed'); end
if isfield(identity.board,'initial_state')
    for key={'rf','i','q'}, identity.board.initial_state.(key{1})(p.subband)=NaN; end
end
identity.wiring=rmfield(identity.wiring,intersect(fieldnames(identity.wiring),{'confirmed_at','photo_index','notes'}));
plan=struct('status','planned','points',points,'blockers',{blockers}, ...
    'automatic_ready',isempty(blockers),'formal_per_point',1,'suspect_total',3, ...
    'baseline_count',3,'mode_order',{{'EXT','INT','EXT','INT','EXT','INT'}}, ...
    'signature',msiq.sha256_bytes(jsonencode(identity)), ...
    'scope_side',p.scope.side,'scope_channels',{p.scope.channels});
end
function a=axis_values(first,last,step)
assert(isscalar(first)&&isscalar(last)&&isscalar(step), ...
    'msiq:if:Axis','Fill the start, end and step for both attenuation axes.');
if ~all(isfinite([first last step]))||step==0|| ...
        any([first last]<0)||any([first last]>31.5)|| ...
        any(abs([first last step]*2-round([first last step]*2))>1e-9)|| ...
        (last-first)*step<0
    error('msiq:if:Axis','Specify attenuation endpoints and signed 0.5 dB grid step.');
end
n=(last-first)/step;
if abs(n-round(n))>1e-9, error('msiq:if:Axis','Endpoint must lie on the specified grid.'); end
a=first+(0:round(n))*step;
end
function ok=all_flags(r)
ok=isfield(r,'protocol_verified')&&isequal(r.protocol_verified,true)&& ...
    isfield(r,'mapping_verified')&&isequal(r.mapping_verified,true)&& ...
    isfield(r,'response_verified')&&isequal(r.response_verified,true);
end
