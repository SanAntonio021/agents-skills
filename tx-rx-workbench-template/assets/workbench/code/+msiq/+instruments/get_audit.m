function state = get_audit()
%GET_AUDIT Return instrument-side-effect counters.
state = msiq.instruments.io_audit('get', '');
end
