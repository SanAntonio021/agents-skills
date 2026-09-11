function info = rx_reference_band(project_root, channels, path, search)
%RX_REFERENCE_BAND File-only lookup returning small metadata to the GUI.
info = struct('path','','center_hz',NaN,'bandwidth_hz',NaN,'error','');
if isempty(path)
    if ~search, return; end
    files = dir(fullfile(project_root,'results','**','tx_reference_bundle.mat'));
    [~,order] = sort([files.datenum],'descend');
    paths = arrayfun(@(k) fullfile(files(k).folder,files(k).name),order,'UniformOutput',false);
else
    paths = {path};
end
for k=1:numel(paths)
    try
        data = msiq.load_reference_bundle(paths{k});
        bundle = data.bundle;
        if ~all(isfield(bundle,{'route','desired','tx_ref','execution'})), continue; end
        if ~strcmpi(field_or(bundle.execution,'status',''),'applied'), continue; end
        frame = field_or(bundle.tx_ref,'frame',struct());
        if ~strcmpi(field_or(bundle,'reference_payload_policy',''),'metrics_only') || ...
                ~strcmpi(field_or(frame,'reference_payload_policy',''),'metrics_only'), continue; end
        saved = field_or(bundle.route,'scope_channels',{});
        if ~isequal(reshape(upper(string(saved)),1,[]),reshape(upper(string(channels)),1,[])), continue; end
        wave = field_or(field_or(bundle,'dsp_config',struct()),'waveform',struct());
        bandwidth = field_or(wave,'occupied_bandwidth_hz',field_or(frame,'occupied_bandwidth_hz',NaN));
        center = abs(field_or(wave,'if_center_hz',0));
        if ~isscalar(bandwidth) || ~isfinite(bandwidth) || bandwidth<=0 || ...
                ~isscalar(center) || ~isfinite(center), continue; end
        info.path = paths{k}; info.center_hz = center; info.bandwidth_hz = bandwidth;
        info.error = '';
        return;
    catch exception
        info.error = exception.message;
    end
end
end

function value = field_or(object,name,fallback)
if isstruct(object) && isfield(object,name) && ~isempty(object.(name))
    value = object.(name);
else
    value = fallback;
end
end
