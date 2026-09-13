function tests = Test_Test_Project_Capture
tests = functiontests(localfunctions);
end

function setupOnce(testCase)
root = fileparts(fileparts(mfilename('fullpath')));
testCase.TestData.oldpath = path;
addpath(fullfile(root,'plotting'));
end

function teardownOnce(testCase)
path(testCase.TestData.oldpath);
end

function testConstantAndRemoval(testCase)
ch = channel(2*ones(1024,1),1024);
result = Test_Project_Analyze_Capture(ch,struct('power_band_hz',[0,512]));
verifyEqual(testCase,result.channels.stats.rms_v,2,'AbsTol',1e-12);
verifyEqual(testCase,result.channels.stats.vpp_v,0);
verifyEqual(testCase,result.channels.spectrum.band_voltage_v2,4,'RelTol',1e-10);
verifyTrue(testCase,isnan(result.channels.spectrum.band_power_w));
removed = Test_Project_Compute_PSD(ch.samples,1024,struct('remove_mean',true));
verifyEqual(testCase,removed.density_linear,zeros(513,1));
end

function testToneAndImpedance(testCase)
fs = 1024; t = (0:1023)'/fs;
ch = channel(cos(2*pi*100*t),fs); ch.impedance_ohm = 50;
result = Test_Project_Analyze_Capture(ch,struct('power_band_hz',[99,101]));
s = result.channels.spectrum;
verifyEqual(testCase,s.band_voltage_v2,.5,'RelTol',1e-10);
verifyEqual(testCase,s.band_power_w,.01,'RelTol',1e-10);
verifyEqual(testCase,s.actual_power_band_hz,[99,101]);
verifyEqual(testCase,s.band_bin_count,3);
verifyEqual(testCase,s.density_w_hz,s.density_v2_hz/50);
end

function testIndependentReferenceOddEvenAndSegments(testCase)
rng(918,'twister'); samples = randn(4097,1);
for lengthWindow = [127,128]
    options = struct('window_length',lengthWindow,'max_segments',8,'remove_mean',true);
    s = Test_Project_Compute_PSD(samples,1000,options);
    starts = 1:(lengthWindow-floor(lengthWindow/2)):(numel(samples)-lengthWindow+1);
    starts = starts(round(linspace(1,numel(starts),8)));
    window = .5-.5*cos(2*pi*(0:lengthWindow-1)'/lengthWindow);
    blocks = zeros(lengthWindow,numel(starts));
    for k = 1:numel(starts)
        x = samples(starts(k):starts(k)+lengthWindow-1);
        blocks(:,k) = (x-mean(x)).*window;
    end
    reference = mean(abs(fft(blocks)).^2,2)/(1000*(window'*window));
    reference = reference(1:floor(lengthWindow/2)+1);
    last = numel(reference)-(rem(lengthWindow,2)==0);
    reference(2:last) = 2*reference(2:last);
    verifyEqual(testCase,s.segment_starts,starts);
    verifyLessThan(testCase,norm(s.density_linear-reference)/norm(reference),1e-10);
end
full = Test_Project_Compute_PSD(samples,1000,struct('window_length',128,'max_segments',Inf));
verifyEqual(testCase,full.segment_count,numel(1:64:(numel(samples)-127)));
end

function testInvalidTimingAndSamplesPreserved(testCase)
ch = channel((1:16)',10); ch.time_s = (0:15)'/10; ch.time_s(8) = ch.time_s(8)+.01;
result = Test_Project_Analyze_Capture(ch);
verifyEqual(testCase,result.channels.waveform.status,'ok');
verifyEqual(testCase,result.channels.waveform.samples_v,ch.samples);
verifyEqual(testCase,result.channels.spectrum.status,'failed');
ch = channel((1:16)',10); ch.samples(4) = NaN;
result = Test_Project_Analyze_Capture(ch);
verifyTrue(testCase,isnan(result.channels.waveform.samples_v(4)));
verifyTrue(testCase,isnan(result.channels.stats.rms_v));
verifyEqual(testCase,result.channels.spectrum.status,'failed');
ch = channel(ones(16,1),10); ch.fs_source = '';
result = Test_Project_Analyze_Capture(ch);
verifyEqual(testCase,result.channels.spectrum.status,'failed');
ch.time_s = (0:15)'/20;
result = Test_Project_Analyze_Capture(ch);
verifyEqual(testCase,result.channels.spectrum.status,'failed');
verifySubstring(testCase,result.channels.spectrum.reason,'source conflict');
ch.fs_hz = 20;
result = Test_Project_Analyze_Capture(ch);
verifyEqual(testCase,result.channels.spectrum.fs_hz,20,'RelTol',1e-12);
end

function testBandBoundaryAndUnavailable(testCase)
ch = channel(ones(1024,1),1024); ch.bandwidth_hz = 400;
result = Test_Project_Analyze_Capture(ch,struct('power_band_hz',[0,401]));
verifyEqual(testCase,result.channels.spectrum.status,'ok');
verifyEqual(testCase,result.channels.spectrum.power_status,'failed');
verifyTrue(testCase,isnan(result.channels.spectrum.band_voltage_v2));
result = Test_Project_Analyze_Capture(ch,struct('power_band_hz',[.1,.2]));
verifyEqual(testCase,result.channels.spectrum.power_status,'failed');
result = Test_Project_Analyze_Capture(ch,struct('power_band_hz',[0,0]));
verifyEqual(testCase,result.channels.spectrum.power_status,'ok');
verifyEqual(testCase,result.channels.spectrum.band_bin_count,1);
end

function testRawIQGateAndNegativeFrequency(testCase)
fs = 1024; t = (0:1023)'/fs;
iChannel = channel(cos(2*pi*100*t),fs); iChannel.role = 'I'; iChannel.id = 'CH1';
qChannel = channel(-sin(2*pi*100*t),fs); qChannel.role = 'Q'; qChannel.id = 'CH2';
input = struct('channels',[iChannel,qChannel]);
s = Test_Project_Complex_Spectrum(input); verifyEqual(testCase,s.status,'failed');
input.channels(1).sync_verified = true; input.channels(2).sync_verified = true;
s = Test_Project_Complex_Spectrum(input);
verifyEqual(testCase,s.status,'ok');
verifyEqual(testCase,s.alignment_basis,'capture_verified');
[~,index] = max(s.density_linear); verifyEqual(testCase,s.frequency_hz(index),-100);
verifyEqual(testCase,sum(s.density_linear)*s.df_hz,1,'RelTol',1e-10);
input.channels(1).time_s = t; input.channels(2).time_s = t+1e-5;
s = Test_Project_Complex_Spectrum(input); verifyEqual(testCase,s.status,'failed');
end

function testDSPProvenanceAndZeroImaginary(testCase)
input = struct('samples',ones(128,1),'fs_hz',128,'amplitude_unit','dimensionless');
s = Test_Project_Complex_Spectrum(input); verifyEqual(testCase,s.status,'failed');
input.alignment_basis = 'dsp_aligned'; input.stage_id = 'equalized';
s = Test_Project_Complex_Spectrum(input);
verifyEqual(testCase,s.status,'ok');
verifyEqual(testCase,s.sidedness,'centered-two-sided');
verifyEqual(testCase,s.frequency_hz,(-64:63)');
verifyEqual(testCase,s.density_unit,'1/Hz');
verifyFalse(testCase,isfield(s,'density_w_hz'));
end

function testInvalidPSDOptions(testCase)
for options = {struct('window_length',1),struct('window_length',17), ...
        struct('overlap_fraction',1),struct('max_segments',0)}
    s = Test_Project_Compute_PSD(ones(16,1),100,options{1});
    verifyEqual(testCase,s.status,'failed');
end
end

function testIdentityAndLimitsContract(testCase)
ch = channel(ones(16,1),10);
verifyError(testCase,@() Test_Project_Analyze_Capture([ch,ch]),'TestProject:DuplicateChannelId');
invalid = ch; invalid.role = 'voltage';
verifyError(testCase,@() Test_Project_Analyze_Capture(invalid),'TestProject:ChannelRole');
ch.voltage_limits_v = [1,-1]; ch.time_limits_s = [0,Inf];
a = Test_Project_Analyze_Capture(ch);
verifyEqual(testCase,a.channels.waveform.status,'failed');
verifyEmpty(testCase,a.channels.waveform.voltage_limits_v);
verifyEmpty(testCase,a.channels.waveform.time_limits_s);
verifyEqual(testCase,a.channels.spectrum.status,'ok');
verifyFalse(testCase,a.channels.spectrum.bandwidth_known);
verifyEqual(testCase,a.channels.waveform.voltage_limits_source,'data_adapted');
ch.voltage_limits_v = [-2;2]; ch.time_limits_s = [0,1.5]; ch.bandwidth_hz = 4;
a = Test_Project_Analyze_Capture(ch);
verifyEqual(testCase,a.channels.waveform.status,'ok');
verifyEqual(testCase,a.channels.waveform.voltage_limits_v,[-2,2]);
verifyEqual(testCase,a.channels.waveform.voltage_limits_source,'scope');
verifyTrue(testCase,a.channels.spectrum.bandwidth_known);
verifyEqual(testCase,a.channels.spectrum.available_limit_hz,4);
end

function value = channel(samples,fs)
value = struct('id','CH1','role','signal','samples',samples, ...
    'fs_hz',fs,'fs_source','synthetic known sampling clock','sync_verified',false);
end
