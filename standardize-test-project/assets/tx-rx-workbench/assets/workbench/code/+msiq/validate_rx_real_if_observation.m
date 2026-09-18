function note=validate_rx_real_if_observation()
% Full samples feed DDC; four-panel rendering consumes only saved analysis.
msiq.instruments.io_audit('reset','');
folder=msiq.validation_artifacts('directory');
fs=40e9; t=(0:131071)'/fs; fc=6.2e9;
x=.06*cos(2*pi*(fc+.2e9)*t)+.01*cos(2*pi*2e9*t);
raw=struct('channels',struct('channel','C2','samples',x,'time_axis_s',t,'sample_rate_hz',fs));
ctx=msiq.rx_measurement_context('tx_if',1);
o=struct('measurement_context',ctx,'real_if_reference',struct('symbol_rate_hz',2e9,'rolloff',.15));
status=struct('sample_rate_hz',fs,'channels',struct('channel','C2','impedance_ohm',50));
c=msiq.plotting.rx_live_analysis(raw,status,o);
assert(c.real_if_analysis.valid,c.real_if_analysis.reason);
assert(c.channels.original_count==numel(x) && numel(c.channels.samples)<numel(x));
assert(numel(c.real_if_analysis.spectra)==2 && numel(c.live_spectra)==1);
for k=1:2
    p=c.real_if_analysis.spectra{k}; [~,at]=max(p.voltage_dbv2_hz);
    assert(abs(p.frequency_hz(at)-.2e9)<3*p.delta_f_hz);
    assert(~p.impedance_known && all(isnan(p.power_dbm_hz)));
end
f=figure('Visible','off','Position',[10 10 1280 720]); guard=onCleanup(@()delete(f));
h=struct('wave_top',subplot(2,2,1),'spectrum_top',subplot(2,2,2), ...
    'wave_bottom',subplot(2,2,3),'spectrum_bottom',subplot(2,2,4));
s=msiq.plotting.rx_live_dashboard(h,c,status,struct(),struct());
assert(s.is_real_if && ~isempty(findobj(h.wave_bottom,'Tag','rx_spectrum_line')));
assert(contains(h.wave_bottom.Title.String,'数字 I') && contains(h.spectrum_bottom.Title.String,'数字 Q'));
assert(contains(h.wave_bottom.YLabel.String,'V^2'));
missing=msiq.plotting.rx_live_analysis(raw,status,struct('measurement_context',ctx));
assert(~missing.real_if_analysis.valid && contains(missing.real_if_analysis.reason,'参考'));
disabled=status; disabled.channels.trace_state='OFF';
closed=msiq.plotting.rx_live_analysis(raw,disabled,o);
assert(~closed.real_if_analysis.valid && contains(closed.real_if_analysis.reason,'关闭'));
[~,d]=msiq.plotting.rx_capture_channels(raw,struct('measurement_context',ctx));
assert(numel(d)==1 && isnan(d.impedance_ohm));
msiq.plotting.rx_live_dashboard(h,missing,status,struct(),s);
assert(isempty(findobj(h.wave_bottom,'Tag','rx_spectrum_line')),'Stale digital spectrum retained');
msiq.plotting.rx_live_dashboard(h,c,status,struct(),s);
exportgraphics(f,fullfile(folder,'real_if_observation.png'));
a=msiq.instruments.get_audit(); assert(a.connections+a.queries+a.writes+a.captures==0);
note='单路全量DDC、数字I/Q电压频谱、同帧四图、缺参考清空及零仪器I/O通过。';
end
