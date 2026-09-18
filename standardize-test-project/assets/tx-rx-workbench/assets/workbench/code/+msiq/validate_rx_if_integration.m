function note=validate_rx_if_integration(output_dir)
%VALIDATE_RX_IF_INTEGRATION Offline controls, full task counts, bounded decisions.
if nargin<1, output_dir=msiq.validation_artifacts('directory'); end
if ~isfolder(output_dir), mkdir(output_dir); end
[~,location]=fileattrib(output_dir); output_dir=location.Name;
p=msiq.if_workbench_config(struct('mode','mock'));
p.scope.fresh=struct('verified',true,'timeout_s',1,'poll_s',.01,'reset_command','RESET', ...
    'start_command','START','completion_query','DONE?','pending_response','0','complete_response','1');
p.board=struct('runtime',struct('protocol_verified',true,'mapping_verified',true,'response_verified',true),'mapping',struct('i_channel','C1','q_channel','C2'), ...
    'limits',struct('i',repmat([0 31.5],6,1),'q',repmat([0 31.5],6,1)));
o=struct('capture_then_demod',false,'cfg_override',msiq.rx_mock_config(),'enable_ldpc',false);
t=msiq.RxDailyTask(1,o,p,{'C1','C2'},3,false);
for k=1:3
    req=t.next(); assert(strcmp(req.action,'formal_capture'));
    t.accept(capture_response(k,[0 0]));
end
assert(~t.active && t.completed==3 && numel(t.rows)==3);
assert(all(cellfun(@(r)strcmp(r.role,'正式'),t.rows)));
t=msiq.RxDailyTask(2,o,p,{'C1'},1,false); t.stop(); assert(isempty(t.next()));
board=struct('state_known',true,'state',struct('agc',zeros(1,6),'rf',20*ones(1,6),'i',20*ones(1,6),'q',20*ones(1,6)));
t=msiq.RxDailyTask(3,o,p,{'C1','C2'},1,true,board);
t.accept(struct('ok',true,'options',o)); t.accept(struct('ok',true)); t.accept(capture_response(1,[1 0])); t.accept(decoded_response(0,30));
req=t.next(); assert(strcmp(req.action,'board_adjust') && strcmp(req.payload.kind,'i') && req.payload.value==20.5);
board.state.i(1)=20.5; t.accept(struct('ok',true,'snapshot',board));
t.accept(capture_response(2,[.1 0])); t.accept(decoded_response(0,30));
assert(~t.active && t.completed==0 && t.adjustments==1,'Balance must not trigger formal captures');
% Candidate and two confirmations all worse -> explicit rollback, RF untouched.
t=msiq.RxDailyTask(4,o,p,{'C1','C2'},1,true,board);
t.accept(struct('ok',true,'options',o)); t.accept(struct('ok',true)); t.accept(capture_response(1,[1 0])); t.accept(decoded_response(0,30));
req=t.next(); old=board.state.i(1); board.state.i(1)=req.payload.value;
t.accept(struct('ok',true,'snapshot',board));
for k=1:3, t.accept(capture_response(k+1,[.1 0])); t.accept(decoded_response(50,20)); end
req=t.next(); assert(req.payload.value==old && strcmp(t.role,'revert'));
assert(numel(t.rows)==4 && t.completed==0);
bad_result=decoded_response(0,NaN); bad_metrics=msiq.rx_pre_fec_metrics(bad_result.result);
assert(~bad_metrics.valid && contains(bad_metrics.reason,'MER'));
% GUI creation cannot call any injected hardware function.
io=struct('open',@forbidden,'query',@forbidden,'write',@forbidden,'capture',@forbidden,'close',@(~)[]);
fig=msiq.rx_workbench_app(struct('config',msiq.rx_mock_config(),'io',io, ...
    'visible',false,'maximize',false,'auto_connect',false,'use_timer',false,'find_reference',false));
guard=onCleanup(@()close(fig)); state=getappdata(fig,'rx_workbench_state');
assert(~state.connected && ~state.running && isempty(state.worker));
assert(get(state.home.h_demod,'Value')==1 && get(state.home.h_ldpc,'Value')==0);
assert(numel(state.home.board.controls.edits)==18);
% Saved results keep compact pre-FEC metrics and complete evidence in the tooltip.
% Neither presentation may depend on the current LDPC checkbox.
pre=struct('valid',true,'pre_ber',.001,'pre_error_count',100,'pre_bit_count',100000,'mer_db',30);
fec=struct('decoder_executed',true,'decoder_status','EXECUTED', ...
    'post_fec_bit_count',10000,'post_fec_bit_error_count',2);
stream=struct('fec',fec);
observation=struct('metrics',pre,'result',struct('primary_streams',stream),'power_dbv2',[-15 -15.2]);
row=struct('role','正式','capture',struct('run_dir','saved_mock'),'observation',observation);
setappdata(state.home.h_history,'records',{row}); set(state.home.h_history,'String',{'正式'},'Value',1);
callback=get(state.home.h_history,'Callback'); callback(state.home.h_history,[]);
label=join(string(get(state.home.h_metrics,'String')),newline);
detail=join(string(get(state.home.h_metrics,'TooltipString')),newline);
assert(contains(label,'纠错前 BER 0.001') && contains(label,'MER 30.000 dB'));
assert(~contains(label,'100 / 100000') && ~contains(label,'纠错后 BER') && contains(label,'功率差'),'Sidebar keeps only core metrics');
assert(contains(detail,'100 / 100000'),'Full statistics remain in details');
assert(contains(detail,'纠错后 BER 0.0002') && contains(detail,'2 / 10000') && contains(detail,'LDPC 已执行'), ...
    'Compact display must not discard saved post-FEC evidence');
assert(get(state.home.h_ldpc,'Value')==0,'History presentation must not use or alter the current LDPC checkbox');
rect=get(state.home.h_metrics,'Position'); extent=get(state.home.h_metrics,'Extent');
assert(extent(4)<=rect(4)+2,'Compact metric lines must fit: extent=%s rect=%s label=%s',mat2str(extent),mat2str(rect),char(label));
bad_post=row.observation.result; bad_post.primary_streams.fec.post_fec_bit_count=NaN;
assert(contains(msiq.rx_decoder_summary(bad_post),'纠错后指标无效'));
row.observation.result.primary_streams.fec.decoder_executed=false;
row.observation.result.primary_streams.fec.decoder_status='NOT_RUN_DEBUG_PRE_FEC_ONLY';
row.observation.result.primary_streams.fec.post_fec_bit_count=NaN;
row.observation.result.primary_streams.fec.post_fec_bit_error_count=NaN;
setappdata(state.home.h_history,'records',{row}); callback(state.home.h_history,[]);
detail=join(string(get(state.home.h_metrics,'TooltipString')),newline); assert(contains(detail,'LDPC 未执行') && ~contains(detail,'纠错后 BER 0'));
label=join(string(get(state.home.h_metrics,'String')),newline); assert(contains(label,'纠错前 BER 0.001') && ~contains(label,'纠错后 BER'));
row.observation.result.primary_streams.fec.decoder_status='NOT_RUN_INVALID_REFERENCE_OR_CAPTURE';
setappdata(state.home.h_history,'records',{row}); callback(state.home.h_history,[]);
assert(contains(join(string(get(state.home.h_metrics,'TooltipString')),newline),'参考或采集无效'));

for size_value={[1280 720],[1920 1080]}
    sz=size_value{1}; set(fig,'Position',[20 20 sz]); drawnow;
    callback=get(fig,'SizeChangedFcn'); callback(fig,[]); state=getappdata(fig,'rx_workbench_state');
    before=getpixelposition(state.home.plot_panel,true);
    slider=state.home.scroll; set(slider,'Value',get(slider,'Min')); cb=get(slider,'Callback'); cb(slider,[]);
    after=getpixelposition(state.home.plot_panel,true); assert(isequal(before,after));
    stop=getpixelposition(state.home.h_stop,true); assert(stop(1)>=0 && stop(2)>=0 && stop(1)+stop(3)<=sz(1));
    assert(before(1)>=420 && before(3)>700 && before(4)>500);
    set(slider,'Value',get(slider,'Max')); cb(slider,[]);
    set(fig,'Visible','on'); drawnow; frame=getframe(fig);
    imwrite(frame.cdata,fullfile(output_dir,sprintf('rx_if_%dx%d.png',sz)));
end
note='PASS: idle GUI zero I/O; fixed sidebar; checkbox defaults; 3 formal without unconditional trial; balance no formal; 3 bad confirmation rollback; cooperative stop; compact pre-FEC metrics and complete saved post-FEC execution / not-run / invalid detail';
end
function varargout=forbidden(varargin) %#ok<STOUT,INUSD>
error('validation:HardwareAccess','Unexpected instrument access');
end
function r=capture_response(k,power)
r=struct('ok',true,'capture',struct('run_dir',sprintf('mock_%d',k),'demod_ready',true), ...
    'raw',struct(),'status',struct(),'observation',struct('scale_vdiv',[.1 .1], ...
    'peaks_v',[.15 .15],'clipped',false,'power_dbv2',power));
r.observation.range_decision=struct('valid',true,'needs_adjustment',false,'current_vdiv',[.1 .1],'reason','量程合适');
end
function r=decoded_response(errors,mer)
s=struct('pre_fec_bit_count',100000,'pre_fec_bit_error_count',errors,'pre_fec_ber',errors/100000,'mer_db',mer,'valid',true);
r=struct('ok',true,'result',struct('primary_streams',s));
end
