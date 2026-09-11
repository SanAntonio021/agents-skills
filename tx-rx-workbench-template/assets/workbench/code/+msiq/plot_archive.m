function output = plot_archive(action, varargin)
%PLOT_ARCHIVE Archive the exact plotted data using MATLAB graphics serialization.
% Only explicitly registered run directories participate; GUI previews do not.
persistent roots destinations ids next_id
if isempty(next_id), roots = {}; destinations = {}; ids = []; next_id = 0; end
output = [];
switch action
    case 'begin'
        next_id = next_id + 1;
        token = next_id;
        roots{end+1} = canonical(varargin{1});
        destinations{end+1} = roots{end};
        if numel(varargin) > 1, destinations{end} = canonical(varargin{2}); end
        ids(end+1) = token;
        output = onCleanup(@() msiq.plot_archive('end', token));
    case 'end'
        selected = ids == varargin{1};
        roots(selected) = []; destinations(selected) = []; ids(selected) = [];
    case {'record','data'}
        path = varargin{2};
        [directory, name, extension] = fileparts(path);
        if startsWith(name,'replot_'), return; end
        session = find(strcmpi(roots,canonical(directory)),1,'last');
        if isempty(session), return; end
        destination = destinations{session};
        if ~isfolder(destination), mkdir(destination); end
        archive = fullfile(destination, 'plot_data.mat');
        record = struct('schema_version','2.0','matlab_release',version('-release'), ...
            'plots',{{}});
        if isfile(archive), record = load(archive); end
        record.schema_version = '2.0';
        index = find(cellfun(@(p) strcmp(p.file,[name,extension]),record.plots),1);
        if strcmp(action,'data')
            entry = struct('file',[name,extension],'renderer','function', ...
                'function_name',varargin{1},'arguments',varargin(3));
        else
            if ~isempty(index) && strcmp(record.plots{index}.renderer,'function'), return; end
            entry = struct('file',[name,extension],'renderer',varargin{3}, ...
                'resolution_dpi',varargin{4},'graphics_format','matlab-fig', ...
                'figure_bytes',serialize_figure(varargin{1}));
            if strcmp(entry.renderer,'print')
                fig = varargin{1};
                entry.print_geometry = struct('units',get(fig,'PaperUnits'), ...
                    'position',get(fig,'PaperPosition'),'size',get(fig,'PaperSize'));
            end
        end
        if isempty(index), index = numel(record.plots)+1; end
        record.plots{index} = entry;
        msiq.atomic_save(archive, record);
        output = entry;
    case 'export'
        entry = msiq.plot_archive('record',varargin{:});
        output = ~isempty(entry);
        if output, msiq.plot_archive('render',entry,varargin{2}); end
    case 'render'
        entry = varargin{1}; path = varargin{2};
        if strcmp(entry.renderer,'function')
            allowed = {'Test_Project_Plot_Scan_Summary','Test_Project_Plot_Constellation', ...
                'Test_Project_Plot_Plan'};
            if ~ismember(entry.function_name,allowed)
                error('msiq:replot:Renderer','Unknown saved renderer: %s.',entry.function_name);
            end
            feval(entry.function_name,path,entry.arguments{:});
        else
            fig = msiq.plot_archive('restore',entry);
            cleanup = onCleanup(@() close(fig));
            set(fig,'Visible','off');
            drawnow;
            if strcmp(entry.renderer,'print')
                if isfield(entry,'print_geometry')
                    % openfig can fit a hidden figure to the receiving screen.
                    geometry = entry.print_geometry;
                    set(fig,'PaperUnits',geometry.units,'PaperSize',geometry.size, ...
                        'PaperPosition',geometry.position,'PaperPositionMode','manual');
                end
                print(fig,path,'-dpng',sprintf('-r%d',entry.resolution_dpi));
            else
                exportgraphics(fig,path,'Resolution',entry.resolution_dpi,'BackgroundColor','w');
            end
        end
    case 'restore'
        entry = varargin{1};
        if isfield(entry,'figure_bytes')
            temporary = [tempname,'.fig'];
            cleanup = onCleanup(@() delete_temporary(temporary));
            fid = fopen(temporary,'wb');
            if fid < 0, error('msiq:plotArchive:Open','Cannot create %s.',temporary); end
            file_cleanup = onCleanup(@() fclose(fid));
            fwrite(fid,entry.figure_bytes,'uint8');
            clear file_cleanup;
            output = openfig(temporary,'new','invisible');
        else
            output = struct2handle(entry.graphics,0,'convert');
        end
    otherwise
        error('msiq:plotArchive:Action', 'Unknown action: %s', action);
end
end

function path = canonical(path)
path = char(java.io.File(char(path)).getCanonicalPath());
end

function bytes = serialize_figure(fig)
% Native FIG serialization preserves tiled layouts and all plotted samples.
temporary = [tempname,'.fig'];
cleanup = onCleanup(@() delete_temporary(temporary));
objects = findall(fig);
saved = cell(numel(objects),1);
for k = 1:numel(objects)
    values = get(objects(k));
    names = fieldnames(values);
    names = names(endsWith(names,'Fcn') | endsWith(names,'Callback') | strcmp(names,'UserData'));
    saved{k} = struct();
    for j = 1:numel(names)
        name = names{j};
        saved{k}.(name) = values.(name);
    end
end
restore = onCleanup(@() restore_properties(objects,saved));
for k = 1:numel(objects)
    names = fieldnames(saved{k});
    for j = 1:numel(names), set(objects(k),names{j},[]); end
end
savefig(fig,temporary,'compact');
fid = fopen(temporary,'rb');
if fid < 0, error('msiq:plotArchive:Open','Cannot read %s.',temporary); end
file_cleanup = onCleanup(@() fclose(fid));
bytes = fread(fid,Inf,'*uint8');
clear file_cleanup;
end

function restore_properties(objects,saved)
for k = 1:numel(objects)
    if isgraphics(objects(k)) && ~isempty(saved{k}), set(objects(k),saved{k}); end
end
end

function delete_temporary(path)
if isfile(path), delete(path); end
end
