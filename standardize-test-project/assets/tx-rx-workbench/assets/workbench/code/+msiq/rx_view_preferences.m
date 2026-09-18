function record = rx_view_preferences(action, path, record)
%RX_VIEW_PREFERENCES Persist only ordered channels and display preferences.
if nargin < 3, record = struct(); end
if strcmp(action,'load')
    record = struct();
    if ~isempty(path) && isfile(path)
        try
            saved = load(path,'preferences');
            record = saved.preferences;
        catch
            % A damaged local preference file must not prevent observation.
        end
    end
end
clean = struct('version',3,'channels',{{}},'views',struct(),'measurement_position','','measurement_subband',1, ...
    'measurement_routes',struct(),'measurement_second_enabled',struct(),'channel_selection_explicit',false,'second_enabled',true);
if isstruct(record) && isscalar(record)
    if isfield(record,'measurement_position') && any(strcmp(record.measurement_position,{'','awg_direct','tx_if','thz_if','rx_if','rx_if_thz'}))
        clean.measurement_position=char(record.measurement_position);
    end
    if isfield(record,'measurement_subband') && number(record.measurement_subband) && ismember(record.measurement_subband,1:6)
        clean.measurement_subband=record.measurement_subband;
    end
    if isfield(record,'measurement_routes') && isstruct(record.measurement_routes) && isscalar(record.measurement_routes)
        for id={'awg_direct','tx_if','thz_if','rx_if','rx_if_thz'}
            if isfield(record.measurement_routes,id{1}) && valid_channels(record.measurement_routes.(id{1}))
                clean.measurement_routes.(id{1})=record.measurement_routes.(id{1});
            end
        end
    end
    if isfield(record,'channels') && valid_channels(record.channels)
        clean.channels = reshape(cellstr(string(record.channels)),1,2);
        clean.channel_selection_explicit = true;
    end
    if isfield(record,'channel_selection_explicit') && binary(record.channel_selection_explicit)
        clean.channel_selection_explicit=logical(record.channel_selection_explicit);
    end
    if isfield(record,'second_enabled') && binary(record.second_enabled)
        clean.second_enabled=logical(record.second_enabled);
    end
    if isfield(record,'measurement_second_enabled') && isstruct(record.measurement_second_enabled) && isscalar(record.measurement_second_enabled)
        for id={'awg_direct','tx_if','thz_if','rx_if','rx_if_thz'}
            if isfield(record.measurement_second_enabled,id{1}) && binary(record.measurement_second_enabled.(id{1}))
                clean.measurement_second_enabled.(id{1})=logical(record.measurement_second_enabled.(id{1}));
            end
        end
    end
    if isfield(record,'views') && isstruct(record.views) && isscalar(record.views)
        names = fieldnames(record.views);
        for k=1:numel(names)
            pair = strsplit(names{k},'_');
            view = record.views.(names{k});
            if ~valid_channels(pair) || ~isstruct(view) || ~isscalar(view), continue; end
            required = {'manual_band','center_hz','bandwidth_hz','psd_ylim','psd_locked'};
            if ~all(isfield(view,required)), continue; end
            if ~binary(view.manual_band) || ~binary(view.psd_locked) || ...
                    ~number(view.center_hz) || view.center_hz<0 || ...
                    ~number(view.bandwidth_hz) || view.bandwidth_hz<=0
                continue;
            end
            limits = view.psd_ylim;
            if ~isnumeric(limits) || ~isreal(limits) || numel(limits)~=2, continue; end
            if view.psd_locked && (~all(isfinite(limits)) || limits(2)<=limits(1)), continue; end
            clean.views.(names{k}) = struct('manual_band',logical(view.manual_band), ...
                'center_hz',double(view.center_hz),'bandwidth_hz',double(view.bandwidth_hz), ...
                'psd_ylim',reshape(double(limits),1,2),'psd_locked',logical(view.psd_locked));
            unit='dbm';
            if isfield(view,'psd_unit') && isequal(view.psd_unit,'voltage'), unit='voltage'; end
            clean.views.(names{k}).psd_unit=unit;
        end
    end
end
record = clean;
if strcmp(action,'save') && ~isempty(path)
    parent = fileparts(path);
    if ~isfolder(parent), mkdir(parent); end
    msiq.atomic_save(path,struct('preferences',record));
end
end

function yes = valid_channels(channels)
yes = (iscellstr(channels) || isstring(channels)) && numel(channels)==2;
if yes
    values = string(channels);
    yes = all(ismember(values,["C1","C2","C3","C4"])) && values(1)~=values(2);
end
end

function yes = number(value)
yes = isnumeric(value) && isreal(value) && isscalar(value) && isfinite(value);
end

function yes = binary(value)
yes = (islogical(value) || isnumeric(value)) && isscalar(value) && any(value==[0 1]);
end
