function state = set_mock_awg_state(state)
%SET_MOCK_AWG_STATE Seed shared AWG state for hardware-free tests.

state = msiq.instruments.io_audit('set_mock_awg_state', state);
end
