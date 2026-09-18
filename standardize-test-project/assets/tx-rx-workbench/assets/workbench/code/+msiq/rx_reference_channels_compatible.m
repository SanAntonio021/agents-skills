function compatible=rx_reference_channels_compatible(bundle,channels,measurement,allow_rebind)
%RX_REFERENCE_CHANNELS_COMPATIBLE Keep logical reference separate from wiring.
if nargin<4, allow_rebind=false; end
route=field(bundle,'route',struct());
saved=reshape(upper(string(field(route,'scope_channels',{}))),1,[]);
actual=reshape(upper(string(channels)),1,[]);
compatible=isequal(saved,actual);
if ~isstruct(measurement) || isempty(fieldnames(measurement)), return; end
measurement=msiq.rx_measurement_context(measurement);
wave=field(field(bundle,'dsp_config',struct()),'waveform',struct());
single=strcmp(field(wave,'architecture',''),'single_complex_stream') && ...
    numel(field(route,'awg_channels',[]))==2 && ...
    (isequal(reshape(field(route,'waveform_columns',[]),1,[]),[1 2]) || ...
     isequal(reshape(field(route,'waveform_columns',[]),1,[]),[3 4]));
if measurement.is_real_if
    compatible=single && numel(actual)==1 && field(wave,'if_center_hz',0)==0;
elseif allow_rebind && ~isempty(measurement.position) && single
    compatible=numel(actual)==2 && numel(unique(actual))==2 && ...
        all(ismember(actual,["C1","C2","C3","C4"]));
end
end
function value=field(object,name,fallback)
value=fallback;
if isstruct(object) && isfield(object,name), value=object.(name); end
end
