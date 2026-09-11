function note = validate_plot_export_geometry(output_dir)
%VALIDATE_PLOT_EXPORT_GEOMETRY Screen-independent print and archive compatibility.
own_scope = ~msiq.validation_artifacts('active');
if own_scope, msiq.validation_artifacts('begin','plot_export_geometry'); end
try
    if nargin < 1, output_dir = msiq.validation_artifacts('directory'); end
    if ~isfolder(output_dir), mkdir(output_dir); end
    msiq.instruments.reset_audit();
    for mode = {'auto','manual'}
        check_archive(output_dir,mode{1});
    end
    names = {'tx','rx','rdiv'};
    dimensions = {[3375 3375],[1920 1080],[3938 2625]};
    for k = 1:numel(names)
        folder = fullfile(output_dir,names{k}); mkdir(folder);
        mkdir(fullfile(folder,'data'));
        path = fullfile(folder,'dashboard.png');
        switch names{k}
            case 'tx', msiq.plotting.tx_dashboard(path,struct(),struct());
            case 'rx', msiq.plotting.rx_dashboard(path,struct(),struct(),struct(),struct());
            case 'rdiv', msiq.plotting.rdiv_compare_dashboard(path,struct(),rdiv_fixture());
        end
        check_png(path,dimensions{k});
        archive_path = msiq.artifact_path(folder,'plot_data.mat');
        before = msiq.file_sha256(archive_path);
        output = msiq.replot_run(folder,struct('results_root',fullfile(output_dir,'replots')));
        assert(numel(output.paths)==1 && ~output.dsp_executed);
        assert(isequal(imread(path),imread(output.paths{1})), ...
            'msiq:validation:PlotPixels','%s replot pixels changed.',names{k});
        assert(strcmp(before,msiq.file_sha256(archive_path)));
        retained = getenv('MSIQ_VALIDATION_ARTIFACTS');
        if ~isempty(retained)
            if ~isfolder(retained), mkdir(retained); end
            copyfile(path,fullfile(retained,[names{k} '_geometry.png']));
        end
    end
    audit = msiq.instruments.get_audit();
    assert(all(struct2array(audit)==0));
    note = ['automatic/manual paper geometry, oversized hidden figures, ', ...
        'legacy FIG archives, exact TX/RX/RDIV dimensions and pixel-identical ', ...
        'immutable replots passed with zero instrument I/O'];
    if own_scope, msiq.validation_artifacts('finish',false,''); end
catch exception
    if own_scope, msiq.validation_artifacts('finish',true,exception.message); end
    rethrow(exception);
end
end

function result = rdiv_fixture()
metrics = struct('mer_db',27,'evm_rms',0.045,'post_fec_bit_error_count',0, ...
    'post_fec_ber',0,'pre_fec_bit_error_count',0,'pre_fec_bit_count',64800, ...
    'block_error_count',0,'block_count',1);
trial = struct('rdiv','DIV2','pair_index',1,'status','decoded','metrics',metrics);
trials = repmat(trial,1,10);
for k = 1:10
    trials(k).pair_index = ceil(k/2);
    if mod(k,2)==0, trials(k).rdiv = 'DIV4'; end
    trials(k).metrics.mer_db = 27+0.1*k;
    trials(k).metrics.evm_rms = 10^(-trials(k).metrics.mer_db/20);
end
result = struct('status','completed','trials',trials);
end

function check_archive(root,mode)
folder = fullfile(root,mode); mkdir(folder);
screen = get(groot,'ScreenSize');
fig = figure('Visible','off','Color','w','Units','pixels', ...
    'Position',[20 20 2*screen(3) 2*screen(4)],'InvertHardcopy','off');
cleanup = onCleanup(@() close(fig));
ax = axes('Parent',fig);
plot(ax,linspace(0,1,80),sin(linspace(0,2*pi,80)),'LineWidth',1.2);
xlabel(ax,'Time'); ylabel(ax,'Amplitude'); grid(ax,'on');
drawnow;
set(fig,'PaperUnits','inches');
if strcmp(mode,'manual')
    set(fig,'PaperSize',[9 6],'PaperPosition',[0 0 9 6], ...
        'PaperPositionMode','manual');
else
    set(fig,'PaperPositionMode','auto');
end
position = get(fig,'PaperPosition');
paper_size = get(fig,'PaperSize');
original_mode = get(fig,'PaperPositionMode');
path = fullfile(folder,'original.png');
guard = msiq.plot_archive('begin',folder); %#ok<NASGU>
entry = msiq.plot_archive('record',fig,path,'print',120);
assert(strcmp(get(fig,'PaperPositionMode'),original_mode));
assert(isequal(get(fig,'PaperPosition'),position));
assert(isequal(entry.print_geometry.position,position));
assert(isequal(entry.print_geometry.size,paper_size));
msiq.plot_archive('render',entry,path);
check_png(path,round(position(3:4)*120));
packet_path = msiq.artifact_path(folder,'plot_data.mat');
before = msiq.file_sha256(packet_path);
replot = msiq.replot_run(folder,struct('results_root',fullfile(root,'replots')));
assert(isequal(imread(path),imread(replot.paths{1})));
assert(strcmp(before,msiq.file_sha256(packet_path)));

legacy = rmfield(entry,'print_geometry');
legacy_path = fullfile(folder,'legacy.png');
msiq.plot_archive('render',legacy,legacy_path);
msiq.plot_archive('render',legacy,fullfile(folder,'legacy_repeat.png'));
assert(isequal(imread(legacy_path),imread(fullfile(folder,'legacy_repeat.png'))));
clear cleanup;
end

function check_png(path,dimensions)
info = imfinfo(path);
assert(all(abs([info.Width info.Height]-dimensions)<=1), ...
    'msiq:validation:PlotDimensions','%s: got %dx%d, expected %dx%d.', ...
    path,info.Width,info.Height,dimensions(1),dimensions(2));
pixels = imread(path);
assert(std(double(pixels(:)))>5,'msiq:validation:BlankPlot','Blank plot: %s.',path);
end
