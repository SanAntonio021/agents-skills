function layout = Test_Project_IQ_Demod_Layout()
%TEST_PROJECT_IQ_DEMOD_LAYOUT Approved complex-IQ overview geometry (v1).
% Layout only: callers supply saved observations and actual DSP results.
layout.id = 'complex_iq_overview_v1';
layout.figure_size = [1600 1100];
layout.waveform = [.05 .70 .27 .225];
layout.spectrum_full = [.385 .70 .26 .225];
layout.spectrum_band = [.715 .70 .255 .225];
layout.matched_iq = [.05 .39 .27 .225];
layout.synchronization = [.385 .39 .26 .225];
layout.training = [.715 .39 .255 .225];
layout.tracking = [.05 .07 .27 .235];
layout.stream = [.385 .065 .585 .255];
layout.constellation_fraction = .62;
layout.header = [.04 .956 .92 .035];
layout.footer = [.04 .012 .92 .025];
layout.title_font = 12;
layout.note_font = 10;
layout.axis_font = 9;
layout.header_font = 17;
end
