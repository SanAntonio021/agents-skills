function state = reset_audit()
%RESET_AUDIT Reset instrument-side-effect counters.
state = msiq.instruments.io_audit('reset', '');
end
