function info = rx_reference_band(project_root, channels, path, search, measurement_context, options)
%RX_REFERENCE_BAND File-only lookup returning small metadata to the GUI.
if nargin<5, measurement_context=struct(); end
if nargin<6, options=struct(); end
info = struct('path','','center_hz',NaN,'bandwidth_hz',NaN,'error','');
if isempty(path)
    if ~search, return; end
    link=msiq.tx_reference_link('read',project_root,options);
    info.reference_link=link;
    if ~link.valid
        info.error=link.reason;
        files=dir(fullfile(project_root,'results','**','tx_reference_bundle.mat'));
        info.candidates=arrayfun(@(x) fullfile(x.folder,x.name),files,'UniformOutput',false);
        return;
    end
    paths={link.path};
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
        wave = field_or(field_or(bundle,'dsp_config',struct()),'waveform',struct());
        if ~msiq.rx_reference_channels_compatible(bundle,channels,measurement_context,true), continue; end
        bandwidth = field_or(wave,'occupied_bandwidth_hz',field_or(frame,'occupied_bandwidth_hz',NaN));
        center = abs(field_or(wave,'if_center_hz',0));
        if ~isscalar(bandwidth) || ~isfinite(bandwidth) || bandwidth<=0 || ...
                ~isscalar(center) || ~isfinite(center), continue; end
        if field_or(measurement_context,'is_real_if',false), center=measurement_context.center_freq_hz; end
        info.real_if_reference=wave; info.real_if_reference.reference_identity=msiq.file_sha256(paths{k});
        info.path = paths{k}; info.center_hz = center; info.bandwidth_hz = bandwidth;
        info.error = '';
        info.reference_identity=msiq.file_sha256(paths{k});
        return;
    catch exception
        info.error = exception.message;
    end
end
if isempty(info.path) && isempty(info.error), info.error='参考发送状态、信号结构或采集通道不匹配。'; end
end

function value = field_or(object,name,fallback)
if isstruct(object) && isfield(object,name) && ~isempty(object.(name))
    value = object.(name);
else
    value = fallback;
end
end
