function note=validate_if_tx_layout(outputdir)
%VALIDATE_IF_TX_LAYOUT Fixed AWG/IF pages under two desktop resolutions.
if nargin<1, outputdir=''; end
if ~isempty(outputdir) && ~isfolder(outputdir), mkdir(outputdir); end
settings=struct('rf',5*ones(1,6));
for resolution=[1280 1920;720 1080]
    options=struct('visible',false,'maximize',false,'auto_connect',false, ...
        'startup_preview',false,'synchronous_startup',true,'persist_parameters',false, ...
        'position',[20 20 resolution.'],'board_options',struct('offline_test',true, ...
        'persist',false,'initial_settings',settings));
    f=msiq.tx_workbench_app(options); cleanup=onCleanup(@()close(f));
    state=getappdata(f,'tx_workbench_state'); original=get(state.ui.axes,'Position');
    outputpos=get(state.ui.output,'Position');
    feval(get(state.ui.if_page,'Callback'),[],[]); drawnow;
    assert(isequal(get(state.ui.axes,'Position'),original));
    assert(isequal(get(state.ui.output,'Position'),outputpos));
    assert(strcmp(get(state.ui.plan_panel,'Visible'),'off'));
    assert(strcmp(get(state.ui.if_board.panel,'Visible'),'on'));
    assert(~state.ui.if_board.getSnapshot().is_open);
    controls=state.ui.if_board.controls;
    for control=reshape([controls.edits(:);controls.minus(:);controls.plus(:);controls.status],1,[])
        rectangle=get(control,'Position'); parentPosition=get(get(control,'Parent'),'Position');
        assert(all(rectangle(1:2)>=0) && rectangle(1)+rectangle(3)<=parentPosition(3) && ...
            rectangle(2)+rectangle(4)<=parentPosition(4));
    end
    if ~isempty(outputdir)
        set(f,'PaperPositionMode','auto');
        print(f,fullfile(outputdir,sprintf('tx_if_%dx%d.png',resolution)),'-dpng','-r96');
    end
    feval(get(state.ui.awg_page,'Callback'),[],[]);
    assert(strcmp(get(state.ui.plan_panel,'Visible'),'on'));
    assert(isequal(get(state.ui.axes,'Position'),original));
    clear cleanup;
end
note='TX 1280x720 and 1920x1080 fixed-page controls passed; no AWG or serial access.';
end
